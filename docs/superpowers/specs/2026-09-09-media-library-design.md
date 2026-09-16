# Media library design — music and cinema

Date: 2026-09-09
Status: phases 1 and 2 specified, phase 3 outlined

## Problem

An external drive on the Pi will hold a library of films, shows and music. Liv's
website should make that library browsable and playable from a browser, for her
and a few invited people, from outside the house.

The existing services (todo, recipes, habits, blog) are CRUD over a local
database. Media is a different shape and needs one new pattern.

## Core principle: two kinds of truth

The boundary is **per-table, not per-service**:

| Source of truth | Tables | Meaning |
| --- | --- | --- |
| Database | `todo`, `recipes`, `habits`, `blog` | Typed by a human; the only copy |
| Disk | `track` | Derived by a scanner; dropping it loses nothing |
| Database | future `playlist`, favourites, notes | Curated; exists nowhere on disk |

`track` is machine-owned and rebuildable — delete the table, rescan, get it back
exactly. Anything curated is precious and a scan must never touch it. Keeping
these in separate tables means the scanner can be given blanket delete rights on
its own table without a flag to get wrong.

## Phase 1 — Music library, LAN only

Ships a usable music library with no networking work. Music is the right first
target: browsers play mp3 and FLAC natively, so there is no transcoding,
remuxing or codec negotiation — the hard parts of video are absent, and the
scanner pattern gets proven cheaply.

### In scope

- `scan-music` CLI command indexing an on-disk music directory into `track`
- Paginated, searchable track listing
- Byte-range streaming endpoint, playable in `<audio>`
- Minimal browse-and-play UI

### Out of scope

Deferred deliberately, listed so they are not accidentally designed out:
playlists, favourites, artwork extraction, authentication, public exposure,
video, and any write path to the media files. The library is read-only; nothing
in this phase modifies or deletes a file on the drive.

### Configuration

| Variable | Required | Default | Meaning |
| --- | --- | --- | --- |
| `MUSIC_DIR` | yes | — | Absolute path to the music root |

Follows the existing `db_config()` pattern: read at use time, not import time,
so a missing value is a clear error rather than an `ImportError`. Absent or
empty raises `RuntimeError` naming the variable.

### Schema

Added to `TABLE_DDL` in `database/db.py`:

```sql
CREATE TABLE IF NOT EXISTS track (
    id INT AUTO_INCREMENT PRIMARY KEY,
    path VARCHAR(768) NOT NULL UNIQUE,
    title VARCHAR(255),
    artist VARCHAR(255),
    album VARCHAR(255),
    track_no INT,
    duration_seconds INT,
    format VARCHAR(16) NOT NULL,
    size_bytes BIGINT NOT NULL,
    mtime BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

Notes:

- `path` is the natural key and is `UNIQUE`. Rows are **updated in place**, never
  deleted and reinserted, so ids stay stable for future playlist references.
- Only `path`, `format`, `size_bytes` and `mtime` are `NOT NULL`. Tags are
  frequently missing or malformed in real libraries; a file with no tags must
  still be indexed and playable, falling back to its filename for display.
- `VARCHAR(768)` is not arbitrary. InnoDB caps an index at 3072 bytes, and
  `utf8mb4` reserves 4 bytes per character, so 768 is the longest column that
  can carry a full `UNIQUE` index. A prefix index such as `path(255)` would fit
  a longer column but only enforces uniqueness over the first 255 characters —
  two files in deep directory trees sharing that prefix would collide into one
  track. Exact uniqueness matters more than supporting very long paths.
- A path exceeding 768 characters is **skipped with a logged error**, never
  silently truncated. MySQL outside strict mode truncates on overflow, which
  would produce a wrong `path` that then fails to stream.
- `mtime` is stored as an integer epoch, not a `TIMESTAMP`, to avoid timezone
  conversion corrupting the change-detection comparison.

### Scanner

`scan_music()` in a new `music/scanner.py`:

1. Walk `MUSIC_DIR` recursively for extensions `.mp3`, `.flac`, `.m4a`, `.ogg`,
   `.wav`.
2. For each file, `stat()` it. If a row exists with matching `size_bytes` and
   `mtime`, skip without reading tags — this makes rescans cheap.
3. Otherwise read tags with `mutagen` and upsert by `path`.
4. Delete rows whose `path` no longer exists on disk.
5. Return counts: added, updated, unchanged, removed.

**Safety rail.** If the walk finds zero files while `track` holds rows, abort
without deleting anything and raise. An unmounted drive is indistinguishable
from an emptied one by file count alone, and the naive behaviour is to delete
the entire library. This rule is a required test, not an optional guard.

**Tag failures are per-file.** A corrupt file that raises inside `mutagen` is
logged and indexed with null tags. One bad file must not abort a 5,000-file
scan.

**Not reachable over HTTP.** A full scan takes minutes and would pin a gunicorn
worker. Invoked as `flask --app app scan-music`, matching the existing `init-db`
pattern, plus a nightly systemd timer.

### Endpoints

| Method | Path | Behaviour |
| --- | --- | --- |
| `GET` | `/music/tracks` | Paginated list. `?q=`, `?limit=` (default 50, max 200), `?offset=` |
| `GET` | `/music/tracks/<id>` | One track's metadata, or 404 |
| `GET` | `/music/tracks/<id>/stream` | The audio file, byte ranges supported |

`GET /music/tracks` returns `{"tracks": [...], "total": N, "limit": L, "offset": O}`
rather than a bare array. This is a deliberate departure from the existing
services, which return bare arrays — a library of thousands of rows cannot
return everything, and the client needs the total to paginate.

`?q=` matches `title`, `artist` and `album` with `LIKE %q%`, parameterised.

### Streaming and path safety

**The client never supplies a path.** It sends a track id; the server looks up
the stored path. There is no endpoint that accepts a filename. This is the
single most important security property of the feature — an endpoint taking a
client path is a read-anything-on-the-Pi hole.

Defence in depth: before serving, resolve the stored path and confirm it is
still inside `MUSIC_DIR` after symlink resolution. A row whose path escapes the
root is refused with 404, not served. This matters because the scanner follows
whatever is on disk, and a symlink planted in the music directory would
otherwise become an arbitrary-file-read primitive.

Phase 1 serves bytes with Flask's `send_file(..., conditional=True)`, which
handles `Range` and returns `206 Partial Content` — required for seeking. This
is acceptable on a LAN with a couple of listeners and is replaced in phase 3.

Missing file on disk (indexed but since deleted) returns 404 with a clear
message, not a 500.

### Error handling

Follows existing conventions: `abort(404, description=...)` for unknown ids,
400 for bad query parameters, and the existing 500 handler for anything
unexpected. Query errors propagate rather than being swallowed.

### Testing

Unit tests, database stubbed, in the existing style:

- Tag extraction, including files with missing and malformed tags
- Incremental skip logic: unchanged `mtime`/`size` does not re-read tags
- Removal detection
- **The zero-files abort rail**
- Pagination bounds: `limit` clamped, negative `offset` rejected
- Search parameterisation
- Path containment: a `track` row pointing outside `MUSIC_DIR` is refused
- Over-length paths are skipped and logged, not truncated

Integration tests (`-m integration`, real database and real temp files):

- Round trip: write real mp3/FLAC files to a temp dir, scan, list, stream
- `Range` request returns `206` with correct bytes and `Content-Range`
- Rescan after renaming a file keeps the row count stable
- Unicode paths and tags survive the round trip

The existing `test_schema.py` guard extends to the new table automatically.

### Dependencies

Adds `mutagen` to `requirements.txt`, pinned.

### Naming

The empty `playlist/` directory is renamed `music/`. Phase 1 has no playlists;
playlists become a later addition inside that module.

## Phase 2 — Cinema, LAN only

Specified 2026-09-16 in `2026-09-16-cinema-design.md`, after measuring Jellyfin 12.1.0 locally. The paragraphs below are the original outline and still hold, with one change: playback happens inside our own page (hls.js against a Flask proxy), not by handing off to Jellyfin's player.

Torrented video is almost always `.mkv` with AC3, E-AC3 or DTS audio, none of
which browsers can play, and increasingly x265 video. Direct play is therefore
not viable, and the remux-versus-transcode decision per file is the entire
problem. **Jellyfin solves it and will be adopted rather than rebuilt.**

Shape: Jellyfin installed via apt, pointed at the films directory, owning
scanning, metadata, artwork and transcoding. Flask gains an API client and
renders its own browse pages. No `film` table until there is a curated field to
store, at which point it holds only that field keyed by Jellyfin's id.

Hardware note: the Pi 5 has no hardware video encoder, so x265 → x264
transcoding is software-only and will not sustain 1080p. Favouring x264
releases keeps playback in the cheap lane — video stream copied, audio
transcoded to AAC — which the Pi handles comfortably. This is worth deciding
before downloading, not after.

## Phase 3 — Public access

Not specified in detail.

```
                    Route 53  ─┐
                               ↓
  internet ──▶ Caddy :443  (TLS, single auth boundary)
                 ├─ /                  ─▶ Flask :5000
                 ├─ /music/…/stream    ─▶ Flask → X-Accel-Redirect → Caddy
                 └─ /cinema/*          ─▶ Jellyfin :8096
```

Components: a `users` table and session handling; Caddy `forward_auth` calling
`GET /auth/verify` on Flask so one login covers everything; Jellyfin's own auth
retained as defence in depth with Flask holding an API key; Route 53 dynamic DNS
via a scoped IAM user; Caddy DNS-01 challenge so certificates do not depend on
inbound port 80.

`X-Accel-Redirect` replaces `send_file` here. Gunicorn's sync workers each
handle one request at a time, so a worker streaming a file is a worker serving
nothing else; with three workers, three concurrent listeners would hang the
site. Handing the file to Caddy makes streaming cost approximately no Python
time.

**Ingress is the only open question and does not affect anything above it.**
Without CGNAT, forward 443 to the Pi. With CGNAT, Caddy moves to a small VPS
with WireGuard back to the Pi, or a Tailscale funnel. Determine by comparing
`curl -4 ifconfig.me` (VPN off) against the router's WAN IP; a WAN address in
`100.64.0.0/10` means CGNAT. If CGNAT is present the Route 53 dynamic DNS work
is pointless, since the published address would not be reachable — so do not
build that part first.

Serving the library publicly requires authentication on every media route. An
open media server is both a security exposure and, for this content, the
difference between personal use and distribution.

## Decisions made

| Decision | Rationale |
| --- | --- |
| Jellyfin for video, build music | Transcoding is the hard, solved problem; music needs none |
| Music first | No codec work, so the scanner pattern is proven cheaply |
| Library only in v1, no playlists | Smaller; playlists are purely additive |
| No `film` table in phase 2 | Jellyfin is already the index |
| Path is the natural key | Keeps ids stable so playlists can reference them later |
| Scan via CLI, not HTTP | Minutes-long work must not occupy a worker |
| Abort scan on zero files | An unmounted drive must not empty the library |
