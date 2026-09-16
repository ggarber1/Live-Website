import os

REQUIRED = ('JELLYFIN_URL', 'JELLYFIN_API_KEY', 'JELLYFIN_USER_ID')


def jellyfin_config():
    """Where Jellyfin is and how to talk to it, from the environment.

    Read at use time like db_config(), so a missing variable is a clear
    error on first use and the rest of the site is unaffected by it.
    """
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            f"missing environment variable(s): {', '.join(missing)}. "
            "See backend/.env.example; scripts/jellyfin-dev.sh prints them."
        )
    return {
        'url': os.environ['JELLYFIN_URL'].rstrip('/'),
        'api_key': os.environ['JELLYFIN_API_KEY'],
        'user_id': os.environ['JELLYFIN_USER_ID'],
    }
