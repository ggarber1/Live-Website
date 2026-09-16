"""A thin client for the parts of Jellyfin's API the cinema section uses.

Facts this rests on, measured against Jellyfin 12.1.0 (see the spec):
the only accepted auth is the MediaBrowser header; with an API key and no
device fields Jellyfin uses its own id as the device, which two viewers
must not share; playback sessions are keyed by device id and play session.
"""
import requests

from cinema.config import jellyfin_config

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30


class JellyfinError(Exception):
    def __init__(self, status, message=None):
        super().__init__(message or f"Jellyfin answered {status}")
        self.status = status


class JellyfinNotFound(JellyfinError):
    def __init__(self):
        super().__init__(404, "Jellyfin has no such item")


class JellyfinUnavailable(Exception):
    """Could not reach Jellyfin at all. Routes turn this into a 503."""


def auth_header(api_key, device_id):
    """The MediaBrowser header. Device fields are what keep viewers apart."""
    return (
        f'MediaBrowser Token="{api_key}", Client="livs", Device="browser", '
        f'DeviceId="{device_id}", Version="1"'
    )


class Jellyfin:
    def __init__(self, device_id='livs-server'):
        config = jellyfin_config()
        self.base = config['url']
        self.user_id = config['user_id']
        self.session = requests.Session()
        self.session.headers['Authorization'] = auth_header(config['api_key'], device_id)

    def get_json(self, path, params=None):
        return self._request('GET', path, params=params).json()

    def post_json(self, path, body=None, params=None):
        return self._request('POST', path, json=body, params=params).json()

    def delete(self, path, params=None):
        self._request('DELETE', path, params=params)

    def stream(self, path, params=None, range_header=None):
        """An open response for proxying bytes; the caller iterates and closes."""
        headers = {'Range': range_header} if range_header else None
        return self._request('GET', path, params=params, headers=headers,
                             stream=True, timeout=(CONNECT_TIMEOUT, None))

    def _request(self, method, path, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), **kwargs):
        try:
            response = self.session.request(method, self.base + path, timeout=timeout, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as err:
            raise JellyfinUnavailable(f"cannot reach Jellyfin at {self.base}: {err}") from err
        if response.status_code == 404:
            raise JellyfinNotFound()
        if response.status_code >= 400:
            raise JellyfinError(response.status_code)
        return response
