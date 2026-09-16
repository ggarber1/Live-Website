"""Jellyfin items → the film shape the frontend sees. Pure."""
from cinema.profile import _streams, playback_kind

TICKS_PER_SECOND = 10_000_000
LIST_FIELDS = 'Overview,Genres,ProductionYear,RunTimeTicks,MediaSources'


def to_film(item):
    sources = item.get('MediaSources') or []
    source = sources[0] if sources else None
    video, audio = _streams(source) if source else (None, None)
    ticks = item.get('RunTimeTicks')
    return {
        'id': item['Id'],
        'title': item.get('Name') or '',
        'year': item.get('ProductionYear'),
        'runtime_seconds': ticks // TICKS_PER_SECOND if ticks else None,
        'overview': item.get('Overview') or '',
        'genres': list(item.get('Genres') or []),
        'has_poster': 'Primary' in (item.get('ImageTags') or {}),
        'playback': playback_kind(source) if source else 'unknown',
        'video_codec': (video or {}).get('Codec'),
        'audio_codec': (audio or {}).get('Codec'),
        'container': (source or {}).get('Container'),
    }
