import re

# Jellyfin writes ApiKey=<the key> into every URI inside an HLS playlist,
# even when the playlist was fetched without credentials. The key is the
# whole API; it must not reach a browser. The proxy mirrors Jellyfin's path
# shape so the relative URIs still resolve; only this parameter goes.
_KEY_NOT_LAST = re.compile(r'ApiKey=[^&\s]*&')
_KEY_LAST = re.compile(r'[?&]ApiKey=[^&\s]*')


def strip_api_key(text):
    """Remove every ApiKey query parameter from a playlist body."""
    return _KEY_LAST.sub('', _KEY_NOT_LAST.sub('', text))
