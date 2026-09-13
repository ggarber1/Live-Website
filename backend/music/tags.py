import logging
import os

import mutagen

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.ogg', '.wav')

logger = logging.getLogger(__name__)


def track_number(raw):
    """Parse a track number, which arrives as "3", "03" or "3/12"."""
    if raw is None:
        return None
    text = str(raw).split('/')[0].strip()
    try:
        return int(text)
    except ValueError:
        return None


def _first(audio, key):
    """Easy-mode tags are lists; take the first non-empty value."""
    values = audio.get(key) or []
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return None


def read_tags(path):
    """Metadata for one audio file. Never raises.

    A corrupt or untagged file must still be indexed and playable, so failures
    degrade to nulls with the filename as the title. mutagen raises a wide
    variety of exception types across formats, hence the broad except.
    """
    audio = None
    try:
        audio = mutagen.File(path, easy=True)
    except Exception as err:
        logger.warning("could not read tags from %s: %s", path, err)

    title = artist = album = None
    number = duration = None

    if audio is not None:
        title = _first(audio, 'title')
        artist = _first(audio, 'artist')
        album = _first(audio, 'album')
        number = track_number(_first(audio, 'tracknumber'))
        length = getattr(getattr(audio, 'info', None), 'length', None)
        if length:
            duration = int(length)

    return {
        'title': title or os.path.splitext(os.path.basename(path))[0],
        'artist': artist,
        'album': album,
        'track_no': number,
        'duration_seconds': duration,
    }
