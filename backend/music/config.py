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
    if not os.path.isabs(value):
        raise RuntimeError(
            f"MUSIC_DIR must be an absolute path, got {value!r}. "
            "A relative path resolves against the process's working directory, "
            "which differs between the CLI and systemd."
        )
    return os.path.realpath(value)


def resolve_inside(root, path):
    """Resolve `path`, returning it only if it stays inside `root`.

    Returns None when it escapes. Scanners index whatever is on disk, so a
    symlink planted in a library would otherwise turn a file-serving endpoint
    into an arbitrary-file read. Comparison is against root + separator so that
    /music does not appear to contain /music-backup. `root` must already be a
    realpath, which music_dir() and photos_dir() guarantee.
    """
    if not path:
        return None
    resolved = os.path.realpath(path)
    if resolved != root and not resolved.startswith(root + os.sep):
        return None
    return resolved


def resolve_inside_music_dir(path):
    # An empty path is refused before the root is read, so a missing variable
    # is not the error a caller sees for bad input.
    if not path:
        return None
    return resolve_inside(music_dir(), path)
