# Cinema design — Phase 2 of the media library

Status: specified 2026-09-16, against Jellyfin 12.1.0 running locally. Parent: `2026-09-09-media-library-design.md`.

## Scope

Films only, on the LAN, played inside our own page. Jellyfin owns the library; we own the look. Greg chose "play inside our page" over handing off to Jellyfin's player, and "films only" over films plus TV.

Out of scope, deliberately: TV series, subtitles (see Gaps), ratings or notes of our own, public access. (Resume was added the same day; see below.) Nothing in this phase writes to Jellyfin or to the media files.

## Two kinds of truth, again

| Truth | Owner | Notes |
| --- | --- | --- |
| Which films exist, their metadata, posters, codecs | Jellyfin | It scans the films directory, matches TMDB, downloads artwork, probes streams. |
| Whether a given browser can play a given file, and the bytes | Jellyfin | Direct play, remux or transcode, decided per request from a device profile we send. |
| The API key | Flask | Never leaves the server. Every browser request goes through Flask. |
| Curated things (notes, "watched", lists) | a future `film` table keyed by Jellyfin id | Not in this phase; there is nothing curated yet. |

No `film` table now. Flask is a translating proxy.

## What Jellyfin actually does (measured)

Recorded against 12.1.0 with three generated films. These are the facts the design rests on.

- **Auth header.** `Authorization: MediaBrowser Token="<key>"`. The older `X-Emby-Token` header is rejected with 401.
- **Listing.** `GET /Items?IncludeItemTypes=Movie&Recursive=true&Fields=Overview,Genres,ProductionYear,RunTimeTicks,MediaSources&SortBy=SortName` returns `{Items, TotalRecordCount}`. Runtime is in ticks (10,000,000 per second). `ImageTags.Primary` present means a poster exists.
- **One item.** `GET /Items/{id}?userId=<user>` works; without `userId` it answers 400 "Error processing request", unlike the listing. `/Users/{user}/Items/{id}` is equivalent.
- **Images.** `GET /Items/{id}/Images/Primary?maxWidth=N` and `/Images/Backdrop/0` return JPEG. They need no auth.
- **Playback decision.** `POST /Items/{id}/PlaybackInfo` with `{UserId, DeviceProfile}` returns `MediaSources[0]` with `SupportsDirectPlay`, `TranscodingUrl` (an HLS master playlist path when transcoding or remuxing) and `TranscodeReasons`, plus a `PlaySessionId`.
- **Three outcomes, three costs:**

  | Source | Result | ffmpeg did | Pi cost |
  | --- | --- | --- | --- |
  | mp4, h264 + aac | direct play, `GET /Videos/{id}/stream?static=true&mediaSourceId=..`, byte ranges honoured | nothing | none |
  | mkv, h264 + ac3 | HLS, "DirectStream" | `-codec:v:0 copy -codec:a:0 aac` | audio only: cheap |
  | mkv, hevc + ac3 | HLS, "Transcode" | `-codec:v:0 libx264 -codec:a:0 aac` | software video encode: will not sustain 1080p |

  The device profile must list h264 profiles `high|main|baseline|constrained baseline` and level ≤ 51, or a High-profile source is needlessly re-encoded to constrained baseline. The profile lives in code, not config.
- **HLS playlists embed the API key.** Every URI inside `master.m3u8` and `main.m3u8` carries `ApiKey=<the key>` as a query parameter, even when the playlist was fetched without auth. Playlists cannot be handed to a browser unmodified.
- **Media is served without auth, and with `Access-Control-Allow-Origin: *`.** Streams, playlists, segments and images all answered 200 with no credentials. On the LAN this is harmless. In Phase 3 Jellyfin's port must be reachable only from Caddy (bind to localhost or firewall it), because Jellyfin will not protect the bytes itself.
- **Stopping.** `DELETE /Videos/ActiveEncodings?deviceId=..&playSessionId=..` ends a transcode. Without it ffmpeg keeps running until Jellyfin's own timeout.
- **Device identity.** With API-key auth and no device fields in the header, Jellyfin used the server's own id as `DeviceId`. Concurrent viewers must not share one, or one viewer's stop kills the other's stream. Flask sends `Client`, `Device`, `DeviceId` and `Version` in the header, with `DeviceId` supplied per browser.

## Configuration

| Variable | Required | Meaning |
| --- | --- | --- |
| `JELLYFIN_URL` | yes | e.g. `http://localhost:8096`. No trailing slash. |
| `JELLYFIN_API_KEY` | yes | Created in Jellyfin's dashboard (or by `scripts/jellyfin-dev.sh`). |
| `JELLYFIN_USER_ID` | yes | The Jellyfin user playback is attributed to. One household, one user. |

Read at use time like `db_config()` and `music_dir()`. Missing or blank raises `RuntimeError` naming the variable. The cinema endpoints return 503 with a clear message when Jellyfin is unreachable, and the rest of the site is unaffected.

## Endpoints

All under `/api/cinema`. The browser never learns `JELLYFIN_URL` or the key.

| Method | Path | Does |
| --- | --- | --- |
| GET | `/films` | `[{id, title, year, runtime_seconds, overview, genres, has_poster, playback}]` sorted by title. `playback` is `direct`, `remux` or `transcode`, derived from container and codecs so the UI can warn about the expensive one. |
| GET | `/films/<id>` | One film, same shape plus `video_codec`, `audio_codec`, `container`. 404 if unknown. |
| GET | `/films/<id>/poster?w=` | Proxied JPEG, `Cache-Control: public, max-age=86400`. 404 if none. |
| GET | `/films/<id>/backdrop` | Same, for the backdrop. |
| POST | `/films/<id>/play` | Body `{device_id}`. Calls PlaybackInfo with the device profile. Returns `{kind: "direct" \| "hls", url, play_session_id}` where `url` is a `/api/cinema/...` path. |
| GET | `/films/<id>/file` | Direct play. Proxies `/Videos/{id}/stream?static=true`, forwarding `Range` and returning Jellyfin's 206, `Content-Range` and `Accept-Ranges` untouched. |
| GET | `/videos/<vid>/<path:rest>` | HLS. Proxies `/videos/<vid>/<rest>` with the query string, adding the auth header. Responses whose type is a playlist have every `ApiKey=...` parameter stripped from the body before it is sent. Segments are streamed through unchanged. |
| POST | `/play/<play_session_id>/stop` | Body `{device_id}`. Ends the transcode. POST rather than DELETE so `navigator.sendBeacon` can fire it on page unload. |

The HLS proxy mirrors Jellyfin's path shape on purpose: the URIs inside the playlists are relative (`main.m3u8?..`, `hls1/main/0.ts?..`), so they resolve against `/api/cinema/videos/<vid>/` without rewriting. Only the key is removed.

Byte-range direct play and HLS segments both flow through gunicorn's threads, the same trade the music stream makes. Segments are 10 seconds each, so a stalled client holds a thread for one segment, not a film. Phase 3 moves the bytes to Caddy.

## The device profile

One profile, in `backend/cinema/profile.py`, for "a modern browser":

- Direct play: `mp4`/`m4v` with h264 + aac or mp3; `webm` with vp9/av1 + opus/vorbis.
- Transcoding: HLS, `ts` segments, h264 + aac, stereo, `BreakOnNonKeyFrames`.
- Codec conditions: h264 profiles `high|main|baseline|constrained baseline`, level ≤ 51, SDR, not anamorphic. These are what stop a copyable stream from being re-encoded.
- Max bitrate 20 Mbit/s.

Safari plays HLS natively; everything else uses hls.js. The profile does not differ between them.

## Frontend

Route `/cinema`, nav label "Cinema", in the paper language.

- **Grid.** Posters at 2:3 in a responsive grid, title and year beneath in the display face. A small italic "will transcode" note on the ones whose `playback` is `transcode`, because on the Pi that one will stutter and Liv should know why before pressing play rather than after.
- **Film page.** Backdrop faded into the paper behind the title; poster, year, runtime, genres, overview; a single Play button. Edit and delete do not exist: Jellyfin owns the data.
- **Player.** Same page, replacing the poster area with a `<video controls>` at 16:9, fullscreen via the native controls. `kind: "direct"` sets `src`; `kind: "hls"` attaches hls.js (or sets `src` on Safari). On unmount, route change or `pagehide`, POST the stop endpoint via `sendBeacon`. Errors from hls.js surface as one line under the video, not a modal.
- **Music and cinema do not play at once.** Pressing Play on a film pauses the music player if it is playing. The reverse is not needed; a film page unmounts its player when you leave.

## Resume (added 2026-09-16, the day Greg asked)

The position is Jellyfin's per-user data, written with `POST /UserItems/{id}/UserData?userId=..` `{PlaybackPositionTicks, Played}` and read back as `UserData` on any item fetched with `userId`. `POST /api/cinema/films/<id>/position {seconds, finished}` wraps it. The player reports on pause, every 30 s, and on leaving (by beacon); `ended` sends `finished`, which clears the position and marks the film played. The film page offers "Resume from <time>" and "Start over" when more than 30 s is stored and the film is not played. Jellyfin's own apps see the same position.

## CLI: `flask --app app cinema-audit`

Lists every film whose video codec is not h264, with its container and audio codec. This is the spec's "favour x264 releases" advice made checkable: run it after adding files, before the film night. Exit 0 always; it is a report, not a gate.

## Deployment (Pi)

Jellyfin from the official apt repository, bound to `127.0.0.1:8096` and `[::1]` only (`network.xml`), so nothing on the LAN talks to it except Flask on the same host. Transcoding settings: no hardware acceleration (the Pi 5 has none), encoder preset `veryfast`, thread count 0 (auto). Films directory on the same drive as music, as `/mnt/media/films`, added as a Movies library in Jellyfin's dashboard. The `livs-api` unit gains `After=jellyfin.service`.

`deploy/README.md` gets a section. The API key and user id are created in Jellyfin's dashboard and pasted into `backend/.env`.

## Development

`scripts/jellyfin-dev.sh` reproduces the local setup: completes the first-run wizard over the API, creates a user and an API key, adds a Movies library pointing at a directory, waits for the scan, and prints the three `JELLYFIN_*` lines for `.env`. `scripts/make-test-films.sh` generates the three codec cases with ffmpeg (45 seconds each; Jellyfin fetches real TMDB metadata for them by name and year). Jellyfin itself is `brew install --cask jellyfin` on a Mac.

## Testing

- **Unit.** `backend/cinema/client.py` is tested against recorded Jellyfin responses (`tests/fixtures/jellyfin/*.json`, captured from 12.1.0), with `requests` stubbed. Playlist key-stripping has its own tests, including a playlist with the key in several URIs and one with no key at all.
- **Route tests** stub the client, as the music routes stub the database.
- **Integration**, marked `jellyfin`, deselected by default, run when `JELLYFIN_URL` is reachable: list the three films, get playback info for each and assert the kind, fetch the master playlist through Flask and assert no `ApiKey` appears, fetch one segment, stop the session.
- **Frontend.** hls.js is mocked; tests cover the grid, the film page, the play flow for both kinds, and that leaving the page fires the stop beacon.

## Gaps, recorded

- **Subtitles.** Jellyfin serves external subtitles as WebVTT at `/Videos/{id}/{mediaSourceId}/Subtitles/{index}/Stream.vtt`. Proxying them and adding `<track>` elements is a contained follow-up; burned-in subtitles for image formats (PGS) mean a video transcode and are worth avoiding on the Pi.
- **Search.** The grid is one page. Jellyfin supports `searchTerm`; add when the library is big enough to need it.

## Decisions

| Decision | Rationale |
| --- | --- |
| Play in our page, via hls.js | Greg's choice; keeps one look. Costs a proxy and a stop endpoint. |
| Flask proxies everything, including bytes | The key must not reach the browser, and the playlists embed it. Also one origin, which Phase 3 needs. |
| Strip the key from playlists rather than rewrite URIs | Relative URIs already resolve against a mirrored path; only the secret needs removing. |
| Device profile in code | It is a correctness matter (copy vs re-encode), not a preference. |
| `playback` computed server-side and shown | The Pi's one real limit, made visible before the fact. |
| Per-browser device id | Two viewers must not share a Jellyfin device, or a stop kills the wrong stream. |
| Jellyfin bound to localhost on the Pi | It serves media without auth. Flask is the door. |
| No film table | Nothing curated yet. Same rule as Phase 1. |
