import logging
import os

import mutagen

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.ogg', '.wav')

# track_no and duration_seconds are INT columns. Tags hold arbitrary garbage,
# and MySQL in strict mode rejects an out-of-range value outright — which would
# abort an entire scan over a single mistagged file.
MAX_SIGNED_INT = 2147483647
MAX_TRACK_NUMBER = 9999

logger = logging.getLogger(__name__)


def track_number(raw):
    """Parse a track number, which arrives as "3", "03" or "3/12".

    Returns None for anything outside 1..MAX_TRACK_NUMBER — negatives, zero,
    and absurd values from malformed tags. The column is INT, and a value that
    does not fit fails the insert and takes the rest of the scan with it.
    """
    if raw is None:
        return None
    text = str(raw).split('/')[0].strip()
    try:
        number = int(text)
    except ValueError:
        return None
    if not 1 <= number <= MAX_TRACK_NUMBER:
        return None
    return number


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
        # A corrupt header can claim an implausible length, and the column is
        # INT. Note this also drops a genuine 0.0-second file, which is
        # degenerate data either way.
        if length is not None and 0 < length <= MAX_SIGNED_INT:
            duration = int(length)

    return {
        'title': title or os.path.splitext(os.path.basename(path))[0],
        'artist': artist,
        'album': album,
        'track_no': number,
        'duration_seconds': duration,
    }
