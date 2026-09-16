import os

from music.config import resolve_inside  # noqa: F401  (re-exported for callers)


def photos_dir():
    """Absolute path to the photos root, from PHOTOS_DIR. Read at use time."""
    value = os.environ.get('PHOTOS_DIR')
    if not value:
        raise RuntimeError(
            "missing environment variable: PHOTOS_DIR. "
            "Copy backend/.env.example to backend/.env and fill it in."
        )
    return os.path.realpath(value)


def thumbs_dir():
    """Where thumbnails are cached: PHOTOS_THUMBS_DIR, or a dot-directory
    under the photos root that the scanner skips."""
    value = os.environ.get('PHOTOS_THUMBS_DIR')
    if value:
        return os.path.realpath(value)
    return os.path.join(photos_dir(), '.thumbnails')


def resolve_inside_photos_dir(path):
    # An empty path is refused before the root is read, so a missing variable
    # is not the error a caller sees for bad input.
    if not path:
        return None
    return resolve_inside(photos_dir(), path)
