import logging
import os

import mutagen
import mutagen.id3

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.ogg', '.wav')

# track_no and duration_seconds are INT columns, and title/artist/album are
# VARCHAR(255). Tags hold arbitrary garbage, and MySQL in strict mode rejects
# an out-of-range or over-length value outright — which would abort an entire
# scan over a single mistagged file.
MAX_SIGNED_INT = 2147483647
MAX_TRACK_NUMBER = 9999
MAX_TEXT_LENGTH = 255

# mutagen's easy=True covers MP3, MP4 and the Vorbis-comment formats but not
# WAV: a tagged .wav comes back with raw ID3 frames, so the easy keys find
# nothing and the file is indexed under its filename with no artist.
ID3_FRAMES = {'title': 'TIT2', 'artist': 'TPE1', 'album': 'TALB',
              'tracknumber': 'TRCK'}

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
    """Easy-mode tags are lists; take the first non-empty value.

    Truncated to MAX_TEXT_LENGTH because the columns are VARCHAR(255) and a
    longer value fails the insert under strict mode, taking the rest of the
    scan with it. Truncating keeps a usable, searchable value where rejecting
    would lose the field entirely.
    """
    for value in _values(audio, key):
        text = str(value).strip()
        if text:
            return text[:MAX_TEXT_LENGTH]
    return None


def _values(audio, key):
    tags = getattr(audio, 'tags', None)
    if isinstance(tags, mutagen.id3.ID3):
        frame = tags.get(ID3_FRAMES[key])
        return list(frame.text) if frame is not None else []
    return audio.get(key) or []


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

    # Filesystems cap a single name at 255 bytes, so today this cannot actually
    # truncate. It is here so the fallback still honours MAX_TEXT_LENGTH if that
    # ever drops below 255 because the column narrowed.
    fallback = os.path.splitext(os.path.basename(path))[0][:MAX_TEXT_LENGTH]

    # Untagged downloads are usually named "Artist - Title". With no tags at
    # all, that is better than a title with a dash in it and no artist.
    if title is None and artist is None and ' - ' in fallback:
        left, right = fallback.split(' - ', 1)
        if left.strip() and right.strip():
            artist, fallback = left.strip(), right.strip()

    return {
        'title': title or fallback,
        'artist': artist,
        'album': album,
        'track_no': number,
        'duration_seconds': duration,
    }
