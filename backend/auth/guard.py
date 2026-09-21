"""Everything under /api needs the session, except logging in and asking."""
from flask import abort, request

from auth.auth import is_logged_in

OPEN_ENDPOINTS = {'auth.login', 'auth.me'}


def install(app, api_prefix):
    @app.before_request
    def require_login():
        path = request.path
        if not (path == api_prefix or path.startswith(api_prefix + '/')):
            return  # the SPA shell and its assets: the login page has to load
        if request.endpoint in OPEN_ENDPOINTS:
            return
        if not is_logged_in():
            abort(401, description="log in first")
