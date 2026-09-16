"""The cinema section: a translating proxy in front of Jellyfin.

The browser never learns where Jellyfin is or what the key is. Listings are
reshaped, images and bytes are proxied, and HLS playlists have the key
stripped out of them. The proxy's path shape mirrors Jellyfin's
(/api/cinema/videos/<vid>/...) so the relative URIs inside playlists resolve
without rewriting.
"""
from flask import Blueprint, Response, abort, request, stream_with_context

from api import json_body
from cinema.client import Jellyfin, JellyfinError, JellyfinNotFound, JellyfinUnavailable
from cinema.films import LIST_FIELDS, to_film
from cinema.playlist import strip_api_key
from cinema.profile import DEVICE_PROFILE

bp = Blueprint('cinema', __name__)

PLAYLIST_TYPE = 'application/vnd.apple.mpegurl'
PASSTHROUGH_HEADERS = ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges')
CHUNK = 65536


@bp.errorhandler(JellyfinUnavailable)
def unavailable(err):
    return {'error': f'Jellyfin is not reachable: {err}'}, 503


@bp.errorhandler(JellyfinNotFound)
def not_found(err):
    return {'error': 'no such film'}, 404


@bp.errorhandler(JellyfinError)
def upstream_error(err):
    """Jellyfin rejected the request.

    A 400 means the id we forwarded was not one of its ids (it wants a GUID),
    which from the browser's side is simply no such film. Anything else is
    Jellyfin's problem, reported as a bad gateway rather than our crash.
    """
    if err.status == 400:
        return {'error': 'no such film'}, 404
    return {'error': f'Jellyfin answered {err.status}'}, 502


@bp.route('/cinema/films')
def films():
    """Every film Jellyfin knows, sorted by title."""
    page = Jellyfin().get_json('/Items', params={
        'IncludeItemTypes': 'Movie', 'Recursive': 'true',
        'Fields': LIST_FIELDS, 'SortBy': 'SortName',
    })
    return [to_film(item) for item in page.get('Items', [])]


@bp.route('/cinema/films/<item_id>')
def film(item_id):
    # Unlike the listing, the single-item endpoint answers 400 without a userId.
    jellyfin = Jellyfin()
    item = jellyfin.get_json(f'/Items/{item_id}',
                             params={'userId': jellyfin.user_id, 'Fields': LIST_FIELDS})
    return to_film(item)


@bp.route('/cinema/films/<item_id>/play', methods=['POST'])
def play(item_id):
    """Ask Jellyfin how this browser can play this film.

    Returns a /api/cinema URL the player can use directly: the file itself
    for direct play, or an HLS master playlist for a remux or transcode.
    """
    device_id, = json_body('device_id')
    if not isinstance(device_id, str) or not device_id.strip():
        abort(400, description='device_id must be a non-empty string')
    jellyfin = Jellyfin(device_id)
    info = jellyfin.post_json(f'/Items/{item_id}/PlaybackInfo', body={
        'UserId': jellyfin.user_id,
        'AutoOpenLiveStream': False,
        'DeviceProfile': DEVICE_PROFILE,
    })
    sources = info.get('MediaSources') or []
    if not sources:
        abort(502, description=f"Jellyfin offered no way to play this film ({info.get('ErrorCode')})")
    source = sources[0]
    session = info.get('PlaySessionId')
    if source.get('SupportsDirectPlay'):
        url = f"/api/cinema/films/{item_id}/file?mediaSourceId={source['Id']}"
        return {'kind': 'direct', 'url': url, 'play_session_id': session}
    transcoding_url = source.get('TranscodingUrl')
    if not transcoding_url:
        abort(502, description='Jellyfin can neither play nor transcode this film')
    return {'kind': 'hls', 'url': '/api/cinema' + strip_api_key(transcoding_url),
            'play_session_id': session}


@bp.route('/cinema/films/<item_id>/file')
def file(item_id):
    """Direct play: the bytes, with Range forwarded and 206 passed back."""
    media_source = request.args.get('mediaSourceId', item_id)
    upstream = Jellyfin().stream(
        f'/Videos/{item_id}/stream',
        params={'static': 'true', 'mediaSourceId': media_source},
        range_header=request.headers.get('Range'),
    )
    return proxied(upstream)


@bp.route('/cinema/videos/<vid>/<path:rest>')
def hls(vid, rest):
    """HLS playlists and segments, keyed exactly as Jellyfin keys them."""
    query = request.query_string.decode()
    path = f'/videos/{vid}/{rest}' + (f'?{query}' if query else '')
    upstream = Jellyfin().stream(path)
    if rest.endswith('.m3u8') or 'mpegurl' in upstream.headers.get('Content-Type', ''):
        body = strip_api_key(upstream.text)
        return Response(body, status=upstream.status_code, content_type=PLAYLIST_TYPE)
    return proxied(upstream)


@bp.route('/cinema/play/<session_id>/stop', methods=['POST'])
def stop(session_id):
    """End a transcode. POST so navigator.sendBeacon can fire it on unload."""
    device_id, = json_body('device_id')
    Jellyfin(device_id).delete('/Videos/ActiveEncodings',
                               params={'deviceId': device_id, 'playSessionId': session_id})
    return '', 204


def proxied(upstream):
    """Stream an upstream response through, copying only the headers that describe bytes."""
    headers = {name: upstream.headers[name] for name in PASSTHROUGH_HEADERS if name in upstream.headers}
    return Response(stream_with_context(upstream.iter_content(CHUNK)),
                    status=upstream.status_code, headers=headers)
