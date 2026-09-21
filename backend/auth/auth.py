"""One password in front of the site.

Two people, one house: a household password and a signed session cookie,
not accounts. The hash lives in .env (SITE_PASSWORD_HASH, made by
`flask hash-password`); the password itself is never stored.
"""
import os
import time

import click
from flask import Blueprint, abort, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from api import json_body

bp = Blueprint('auth', __name__)

SESSION_KEY = 'livs'
MAX_FAILURES = 5
LOCKOUT_SECONDS = 30

# Failed attempts per address, in memory. Reset on restart, which is fine:
# this slows an idle scanner down; the password is the defence.
_failures = {}


def is_logged_in():
    return session.get(SESSION_KEY) is True


def _password_hash():
    value = os.environ.get('SITE_PASSWORD_HASH')
    if not value:
        # Never fail open: with no hash configured nobody can log in.
        abort(503, description="SITE_PASSWORD_HASH is not set; run `flask hash-password`")
    return value


def _throttled(address, now):
    count, until = _failures.get(address, (0, 0))
    return count >= MAX_FAILURES and now < until


def _record_failure(address, now):
    count, _ = _failures.get(address, (0, 0))
    count += 1
    until = now + LOCKOUT_SECONDS if count >= MAX_FAILURES else 0
    _failures[address] = (count, until)


@bp.route('/auth/login', methods=['POST'])
def login():
    password, = json_body('password')
    address = request.remote_addr or '?'
    now = time.monotonic()
    if _throttled(address, now):
        abort(429, description="too many tries; wait half a minute")
    if _failures.get(address, (0, 0))[0] >= MAX_FAILURES:
        _failures.pop(address, None)  # lockout expired
    if not isinstance(password, str) or not check_password_hash(_password_hash(), password):
        _record_failure(address, now)
        abort(401, description="that's not it")
    _failures.pop(address, None)
    session.clear()
    session[SESSION_KEY] = True
    session.permanent = True
    return '', 204


@bp.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return '', 204


@bp.route('/auth/me', methods=['GET'])
def me():
    return jsonify({'authenticated': is_logged_in()})


@click.command('hash-password')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
def hash_password_command(password):
    """Print the SITE_PASSWORD_HASH line for .env."""
    click.echo(f"SITE_PASSWORD_HASH={generate_password_hash(password)}")
