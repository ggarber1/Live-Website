import os

# track.path is VARCHAR(768) — the longest utf8mb4 column that still fits a full
# UNIQUE index in InnoDB's 3072-byte limit. See the design spec.
MAX_PATH_LENGTH = 768


def music_dir():
    """Absolute path to the music library root, from MUSIC_DIR.

    Read at use time rather than import time, matching db_config(), so a missing
    value is a clear error on first use instead of an ImportError.
    """
    value = os.environ.get('MUSIC_DIR')
    if not value:
        raise RuntimeError(
            "missing environment variable: MUSIC_DIR. "
            "Copy backend/.env.example to backend/.env and fill it in."
        )
    return os.path.realpath(value)


def resolve_inside_music_dir(path):
    """Resolve `path`, returning it only if it stays inside the music root.

    Returns None when it escapes. The scanner indexes whatever is on disk, so a
    symlink planted in the library would otherwise turn the streaming endpoint
    into an arbitrary-file read. Comparison is against root + separator so that
    /music does not appear to contain /music-backup.
    """
    root = music_dir()
    resolved = os.path.realpath(path)
    if resolved != root and not resolved.startswith(root + os.sep):
        return None
    return resolved
