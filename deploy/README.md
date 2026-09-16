# Deploying the API to the Pi

Assumes Raspberry Pi OS. Replace `pi` and `/home/pi/livs_website` throughout if
your user or checkout path differ — the same two values are marked `EDIT` in
`livs-api.service`.

## 1. System packages

`mariadb` (the Python driver) builds against the MariaDB client library, so the
dev headers have to be present *before* pip runs.

```bash
sudo apt update
sudo apt install -y mariadb-server libmariadb-dev python3-venv python3-dev build-essential nodejs npm
```

`nodejs` and `npm` build the frontend; they are not needed at runtime.

## 2. Database and user

```bash
sudo mariadb
```

```sql
CREATE DATABASE livs;
CREATE USER 'livs'@'localhost' IDENTIFIED BY 'PICK_A_PASSWORD';
GRANT ALL PRIVILEGES ON livs.* TO 'livs'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

## 3. Checkout and virtualenv

```bash
git clone <repo> /home/pi/livs_website
cd /home/pi/livs_website/backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## 4. Configuration

```bash
cp .env.example .env
```

Fill in `DB_USER`, `DB_PASSWORD`, `DB_NAME`, and set `CORS_ORIGINS` to wherever
the frontend is actually served from — for example:

```
CORS_ORIGINS=http://livs-pi.local,http://192.168.1.50
```

systemd's `EnvironmentFile` is not a shell: write `DB_PASSWORD=s3cret` with no
quotes and no spaces around the `=`. Quotes become part of the value.

## 5. Create the tables

Gunicorn never runs `app.py`'s `__main__` block, so this does not happen on its
own:

```bash
./venv/bin/flask --app app init-db
```

Expect `Tables ready: todo, recipes, habits, blog, track`. It is safe to re-run.

## 6. Index the music library

`MUSIC_DIR` must point at the music directory — a subdirectory of the mount,
not the filesystem root. Pointing it at a drive root pulls in directories like
`lost+found` that the service user cannot read, which disables removal
detection on every scan.

```bash
cd /home/pi/livs_website/backend
./venv/bin/flask --app app scan-music
```

A healthy run prints one line:

```
added 1240, updated 0, unchanged 0, removed 0
```

A run that skipped files prints a second line breaking them down by reason,
because each needs a different fix — rename the file, repair permissions,
correct the tag data:

```
skipped 4 (too long 1, unreadable files 2, rejected 1)
```

Exit codes matter here, because this is meant to run unattended:

| Exit | Meaning |
| --- | --- |
| 0 | The scan completed. Individual skipped files do not fail the run — one permanently broken file must not fail the timer every night. |
| non-zero | Either the scan refused to delete a large share of the table, or a directory could not be read so removal detection was skipped and the index is now knowingly stale. Read the message; do not just re-run. |

If it refuses because too much would be deleted, that is usually `MUSIC_DIR`
pointing somewhere new, or the drive mounted at a different path. Confirm the
path is right before overriding:

```bash
./venv/bin/flask --app app scan-music --force-removals
```

### Running it nightly

```bash
sudo cp /home/pi/livs_website/deploy/livs-scan.service /etc/systemd/system/
sudo cp /home/pi/livs_website/deploy/livs-scan.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now livs-scan.timer
```

Check it: `systemctl list-timers livs-scan` and `journalctl -u livs-scan -n 50`.

## 6b. Photos

`PHOTOS_DIR` points at the photos subdirectory of the mount, like
`MUSIC_DIR`. Two differences from music:

- **The site writes here.** Uploads land in `PHOTOS_DIR/YYYY/MM/` and
  deletes remove files, so the `pi` user needs write access to the
  directory (`sudo chown -R pi:pi /mnt/media/photos`).
- **Thumbnails are cached on the drive**, in `PHOTOS_DIR/.thumbnails/`
  (or `PHOTOS_THUMBS_DIR`). The dot-directory is skipped by the scanner.
  It is safe to delete; it is rebuilt on demand.

Index anything copied in by hand, and index again nightly (the timer runs
both scans):

```bash
./venv/bin/flask --app app scan-photos
```

The same safety rails as music apply: an empty directory with a populated
table, or a scan that would remove more than half the rows, is refused
without `--force-removals`.

## 7. Build the frontend

Flask serves `frontend/dist/` on the same origin as the API, so there is no
second server and `CORS_ORIGINS` is irrelevant in production. The build is
not checked in; do this on every deploy that touches `frontend/`.

```bash
cd /home/pi/livs_website/frontend
npm ci
npm run build
```

Until this has run, `GET /` answers 404 with a message saying so.

## 8. Cinema: Jellyfin

Jellyfin owns the film library, metadata, artwork and transcoding; Flask
proxies it under `/api/cinema`. Install it from the official repository:

```bash
curl -fsSL https://repo.jellyfin.org/install-debuntu.sh | sudo bash
```

Then, in `/etc/jellyfin/network.xml`, bind it to the loopback only and
restart it:

```xml
<LocalNetworkAddresses>
  <string>127.0.0.1</string>
</LocalNetworkAddresses>
```

Why: Jellyfin serves streams, playlists and images **without any
authentication** and with `Access-Control-Allow-Origin: *` (measured on
12.1.0). On the LAN that is merely untidy; once anything is public it is
a hole. Flask on the same host is the only client it needs.

Open `http://<pi-ip>:8096` once through an SSH tunnel
(`ssh -L 8096:127.0.0.1:8096 pi@<pi-ip>`) to run the first-time wizard, then:

1. Dashboard → Libraries → Add: content type Movies, folder `/mnt/media/films`.
2. Dashboard → Playback → Transcoding: hardware acceleration **None** (the
   Pi 5 has no video encoder), encoding preset `veryfast`, thread count 0.
3. Dashboard → API Keys → add one named `livs`.
4. Dashboard → Users → the user → the id is in the page URL.

Put the three values in `backend/.env`:

```
JELLYFIN_URL=http://127.0.0.1:8096
JELLYFIN_API_KEY=...
JELLYFIN_USER_ID=...
```

**Codecs.** An h264 film in an MKV is remuxed (video copied, audio
re-encoded) and plays fine. An HEVC/x265 film has to be re-encoded in
software and will stutter at 1080p. Before a film night:

```bash
./backend/venv/bin/flask --app app cinema-audit   # lists the films that will transcode video
```

Prefer x264 releases, or convert the listed ones once with ffmpeg.

## 9. Install the service

```bash
sudo cp /home/pi/livs_website/deploy/livs-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now livs-api
```

## 10. Verify

```bash
systemctl status livs-api
curl -s localhost:5000/ | head -c 80   # -> <!doctype html>...
curl localhost:5000/api/todo          # -> []
curl http://<pi-ip>:5000/api/todo     # from another machine on the network
```

Logs: `journalctl -u livs-api -f`

## Updating

```bash
cd /home/pi/livs_website && git pull
./backend/venv/bin/pip install -r backend/requirements.txt
./backend/venv/bin/flask --app app init-db   # only if the schema changed
(cd frontend && npm ci && npm run build)    # only if frontend/ changed
./backend/venv/bin/flask --app app cinema-audit  # after adding films
./backend/venv/bin/flask --app app scan-photos   # after copying photos in by hand
sudo systemctl restart livs-api
```

## Notes

- **Workers.** `--workers 3` suits a 4-core Pi, with `--worker-class gthread
  --threads 8`. Threads rather than the default sync worker because streaming
  a track holds its handler for the entire transfer — a 40 MB FLAC over weak
  wifi is minutes, not milliseconds. With sync workers, three people pressing
  play would block every other request, including `/todo`, until a transfer
  finished. Phase 3 removes the problem properly by handing the bytes to the
  reverse proxy with `X-Accel-Redirect`.
- **Database connections.** One per request, not per worker, and `flask.g` is
  thread-local, so threads never share a connection. The ceiling is
  `workers × threads` = 24, against MariaDB's default `max_connections` of
  151 — comfortable.
- **HTTPS.** This serves plain HTTP on the LAN. Putting it on the public
  internet means a reverse proxy (Caddy or nginx) terminating TLS in front,
  and `--bind 127.0.0.1:5000` so only the proxy can reach gunicorn.
- **`ProtectHome=read-only`** lets the service read its checkout under `/home`
  but not write there. If you later add file uploads, add the target directory
  to `ReadWritePaths`.
