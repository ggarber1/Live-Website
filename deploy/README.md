# Deploying the API to the Pi

Assumes Raspberry Pi OS. Replace `pi` and `/home/pi/livs_website` throughout if
your user or checkout path differ — the same two values are marked `EDIT` in
`livs-api.service`.

## 1. System packages

`mariadb` (the Python driver) builds against the MariaDB client library, so the
dev headers have to be present *before* pip runs.

```bash
sudo apt update
sudo apt install -y mariadb-server libmariadb-dev python3-venv python3-dev build-essential
```

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

Expect `Tables ready: todo, recipes, habits, blog`. It is safe to re-run.

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

## 7. Install the service

```bash
sudo cp /home/pi/livs_website/deploy/livs-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now livs-api
```

## 8. Verify

```bash
systemctl status livs-api
curl localhost:5000/todo          # -> []
curl http://<pi-ip>:5000/todo     # from another machine on the network
```

Logs: `journalctl -u livs-api -f`

## Updating

```bash
cd /home/pi/livs_website && git pull
./backend/venv/bin/pip install -r backend/requirements.txt
./backend/venv/bin/flask --app app init-db   # only if the schema changed
sudo systemctl restart livs-api
```

## Notes

- **Workers.** `--workers 3` suits a 4-core Pi. Each worker opens its own
  database connection per request, so worker count multiplies concurrent
  connections against MariaDB's `max_connections` (151 by default) — fine here.
- **HTTPS.** This serves plain HTTP on the LAN. Putting it on the public
  internet means a reverse proxy (Caddy or nginx) terminating TLS in front,
  and `--bind 127.0.0.1:5000` so only the proxy can reach gunicorn.
- **`ProtectHome=read-only`** lets the service read its checkout under `/home`
  but not write there. If you later add file uploads, add the target directory
  to `ReadWritePaths`.
