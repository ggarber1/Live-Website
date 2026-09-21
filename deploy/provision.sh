#!/bin/bash
# Provision a fresh Ubuntu 24.04 host as Liv's site: MariaDB, gunicorn,
# Jellyfin, Caddy, the media volume, and the systemd units. Idempotent: safe
# to re-run after a failure or to pick up changes.
#
#   sudo LIVS_DOMAIN=livs.example.com ./deploy/provision.sh
#
# Environment:
#   LIVS_DOMAIN     required. The site's hostname; Caddy gets its certificate.
#   LIVS_REPO       git URL to clone if /opt/livs is absent
#                   (default: this checkout's origin).
#   LIVS_MEDIA_DEV  block device for the media volume (default: the first
#                   unformatted, unmounted disk; skipped if none, e.g. a Pi
#                   whose drive is already mounted at /mnt/media).
#   LIVS_PASSWORD   the household password. Prompted for if unset and
#                   .env has no hash yet.
#   LIVS_DRY_RUN=1  print what would be done and exit before changing anything.
set -euo pipefail

LIVS_USER=livs
LIVS_HOME=/opt/livs
MEDIA=/mnt/media
ENV_FILE=$LIVS_HOME/backend/.env

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'provision: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root (sudo)"
: "${LIVS_DOMAIN:?set LIVS_DOMAIN to the hostname of the site}"
LIVS_REPO=${LIVS_REPO:-$(git -C "$(dirname "$0")/.." remote get-url origin 2>/dev/null || echo https://github.com/ggarber1/Live-Website.git)}

find_media_device() {
  # The first whole disk with no partitions, no filesystem and no mount
  # anywhere on it: on EC2 the attached EBS volume; nothing on a Pi whose
  # drive is already in use. The root disk shows a blank filesystem at the
  # disk level while its partitions carry one, so children are checked too.
  for disk in $(lsblk -dnpo NAME,TYPE | awk '$2=="disk" {print $1}'); do
    if [ "$(lsblk -no NAME "$disk" | wc -l)" = 1 ] && [ -z "$(lsblk -no FSTYPE,MOUNTPOINT "$disk" | tr -d '[:space:]')" ]; then
      echo "$disk"
      return 0
    fi
  done
  return 1
}

if [ "${LIVS_DRY_RUN:-0}" = 1 ]; then
  echo "domain:        $LIVS_DOMAIN"
  echo "repo:          $LIVS_REPO"
  echo "media device:  ${LIVS_MEDIA_DEV:-$(find_media_device || true)}"
  echo "app user/home: $LIVS_USER $LIVS_HOME"
  exit 0
fi

log "packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q mariadb-server libmariadb-dev python3-venv python3-dev build-essential \
  ffmpeg git curl debian-keyring debian-archive-keyring apt-transport-https ufw
# Ubuntu's packaged Node is 18; the frontend build needs 20 or newer.
if ! command -v node >/dev/null || [ "$(node -e 'console.log(process.versions.node.split(".")[0])')" -lt 20 ]; then
  apt-get remove -y -q nodejs npm >/dev/null 2>&1 || true
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null
  apt-get install -y -q nodejs
fi
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q && apt-get install -y -q caddy
fi
if ! command -v jellyfin >/dev/null && [ ! -x /usr/bin/jellyfin ]; then
  curl -fsSL https://repo.jellyfin.org/install-debuntu.sh | bash
fi

log "app user"
id -u $LIVS_USER >/dev/null 2>&1 || useradd --system --create-home --home-dir $LIVS_HOME --shell /usr/sbin/nologin $LIVS_USER

log "media volume at $MEDIA"
mkdir -p $MEDIA
DEV=${LIVS_MEDIA_DEV:-$(find_media_device || true)}
if [ -n "${DEV:-}" ] && ! mountpoint -q $MEDIA; then
  [ "$(lsblk -no NAME "$DEV" | wc -l)" = 1 ] || die "$DEV has partitions; refusing to touch it"
  if [ -z "$(lsblk -no FSTYPE "$DEV" | tr -d '[:space:]')" ]; then
    log "formatting $DEV (it has no filesystem)"
    mkfs.ext4 -q -L media "$DEV"
  fi
  # A fresh filesystem's UUID can take a moment to appear in blkid.
  UUID=""
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    udevadm settle 2>/dev/null || true
    UUID=$(blkid -s UUID -o value "$DEV" || true)
    [ -n "$UUID" ] && break
    sleep 1
  done
  [ -n "$UUID" ] || die "no UUID for $DEV after formatting"
  grep -q "UUID=$UUID" /etc/fstab || echo "UUID=$UUID $MEDIA ext4 defaults,nofail 0 2" >> /etc/fstab
  mount $MEDIA
fi
mkdir -p $MEDIA/music $MEDIA/films $MEDIA/photos $MEDIA/backups
chown $LIVS_USER:$LIVS_USER $MEDIA/music $MEDIA/films $MEDIA/photos $MEDIA/backups
chmod 755 $MEDIA $MEDIA/music $MEDIA/films $MEDIA/photos   # jellyfin reads films
chmod 750 $MEDIA/backups

log "checkout at $LIVS_HOME"
if [ ! -d $LIVS_HOME/.git ]; then
  # The home directory already exists (useradd made it), so clone in place.
  sudo -u $LIVS_USER git -C $LIVS_HOME init -q -b main
  sudo -u $LIVS_USER git -C $LIVS_HOME remote add origin "$LIVS_REPO"
  sudo -u $LIVS_USER git -C $LIVS_HOME fetch -q origin main
  sudo -u $LIVS_USER git -C $LIVS_HOME checkout -q -t origin/main
fi
sudo -u $LIVS_USER git -C $LIVS_HOME pull -q --ff-only || true

log "python"
[ -d $LIVS_HOME/backend/venv ] || sudo -u $LIVS_USER python3 -m venv $LIVS_HOME/backend/venv
sudo -u $LIVS_USER $LIVS_HOME/backend/venv/bin/pip install -q -r $LIVS_HOME/backend/requirements.txt

log "frontend"
sudo -u $LIVS_USER bash -c "cd $LIVS_HOME/frontend && npm ci --silent && npm run build --silent"

log "configuration"
if [ ! -f $ENV_FILE ]; then
  DB_PASSWORD=$(openssl rand -hex 24)
  cat > $ENV_FILE <<CONF
DB_USER=livs
DB_PASSWORD=$DB_PASSWORD
DB_NAME=livs
MUSIC_DIR=$MEDIA/music
PHOTOS_DIR=$MEDIA/photos
SECRET_KEY=$(openssl rand -hex 32)
SITE_HTTPS=1
JELLYFIN_URL=http://127.0.0.1:8096
JELLYFIN_API_KEY=
JELLYFIN_USER_ID=
CONF
  chown $LIVS_USER:$LIVS_USER $ENV_FILE
  chmod 600 $ENV_FILE
fi
if ! grep -q '^SITE_PASSWORD_HASH=.\+' $ENV_FILE; then
  if [ -z "${LIVS_PASSWORD:-}" ]; then
    read -rsp "Household password for the site: " LIVS_PASSWORD; echo
  fi
  HASH=$(cd $LIVS_HOME/backend && sudo -u $LIVS_USER ./venv/bin/flask --app app hash-password --password "$LIVS_PASSWORD" | sed 's/^SITE_PASSWORD_HASH=//')
  sed -i '/^SITE_PASSWORD_HASH=/d' $ENV_FILE
  echo "SITE_PASSWORD_HASH=$HASH" >> $ENV_FILE
fi

log "database"
set -a; . $ENV_FILE; set +a
mysql -e "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -e "CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD'; ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD'; GRANT ALL ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost'; FLUSH PRIVILEGES;"
(cd $LIVS_HOME/backend && sudo -u $LIVS_USER ./venv/bin/flask --app app init-db)

log "jellyfin on loopback only"
JF_NET=/etc/jellyfin/network.xml
if [ -f "$JF_NET" ] && ! grep -q '<string>127.0.0.1</string>' "$JF_NET"; then
  sed -i 's#<LocalNetworkAddresses />#<LocalNetworkAddresses><string>127.0.0.1</string></LocalNetworkAddresses>#' "$JF_NET"
  systemctl restart jellyfin
fi
usermod -aG $LIVS_USER jellyfin 2>/dev/null || true

log "services"
for unit in livs-api livs-scan livs-backup; do
  sed -e "s#/home/pi/livs_website#$LIVS_HOME#g" -e "s#^User=pi#User=$LIVS_USER#" -e "s#^Group=pi#Group=$LIVS_USER#" \
      -e "s#--bind 0.0.0.0:5000#--bind 127.0.0.1:5000#" \
      $LIVS_HOME/deploy/$unit.service > /etc/systemd/system/$unit.service
done
cp $LIVS_HOME/deploy/livs-scan.timer $LIVS_HOME/deploy/livs-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now mariadb jellyfin livs-api livs-scan.timer livs-backup.timer
systemctl restart livs-api

log "caddy for $LIVS_DOMAIN"
sed "s#{\$LIVS_DOMAIN}#$LIVS_DOMAIN#" $LIVS_HOME/deploy/Caddyfile > /etc/caddy/Caddyfile
systemctl enable --now caddy
systemctl reload caddy

log "firewall"
ufw allow 22/tcp >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

log "done"
echo "site:     https://$LIVS_DOMAIN"
echo "jellyfin: not yet configured; tunnel with  ssh -L 8096:127.0.0.1:8096 <host>  then run scripts/jellyfin-dev.sh $MEDIA/films"
echo "media:    rsync into $MEDIA/{music,films,photos} as $LIVS_USER, then scan-music / scan-photos"
