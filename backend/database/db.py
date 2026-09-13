import os

import click
import mariadb
from flask import g
from flask.cli import with_appcontext

REQUIRED_ENV = ('DB_USER', 'DB_PASSWORD', 'DB_NAME')


def db_config():
    """Connection settings from the environment.

    Read at connect time rather than import time, so a missing variable is a
    clear error on the first query instead of an ImportError that takes the
    whole app — and so the test suite can import this module without a .env.
    """
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            f"missing environment variable(s): {', '.join(missing)}. "
            "Copy backend/.env.example to backend/.env and fill it in."
        )
    return {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'port': int(os.environ.get('DB_PORT', '3306')),
        'user': os.environ['DB_USER'],
        'password': os.environ['DB_PASSWORD'],
        'database': os.environ['DB_NAME'],
    }


def init_app(app):
    """Wire connection cleanup and the init-db command into the app."""
    app.teardown_appcontext(close_connection)
    app.cli.add_command(init_db_command)


def get_connection():
    """Return this request's connection, opening one on first use.

    The connection and its cursors are scoped to the app context, so concurrent
    requests never share them. A single module-level connection would let two
    requests interleave on one cursor and read each other's rowcount/lastrowid.
    """
    if 'db_conn' not in g:
        g.db_conn = mariadb.connect(**db_config())
    return g.db_conn


def close_connection(exc=None):
    conn = g.pop('db_conn', None)
    if conn is not None:
        conn.close()


def _write(query, params, result):
    """Run a statement, commit, and return result(cursor) before the cursor closes.

    A failed statement is rolled back and re-raised — callers must not see a
    discarded write as a success.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params or ())
        conn.commit()
        return result(cursor)
    except mariadb.Error:
        conn.rollback()
        raise
    finally:
        cursor.close()


def execute(query, params=None):
    """Run a write and commit it. Returns the number of rows affected."""
    return _write(query, params, lambda c: c.rowcount)


def insert(query, params=None):
    """Run an INSERT and commit it. Returns the new row's id."""
    return _write(query, params, lambda c: c.lastrowid)


def fetch_all(query, params=None):
    """Run a SELECT and return every row as a dict keyed by column name.

    Query errors propagate rather than being swallowed, so a broken read fails
    loudly instead of looking like an empty result.
    """
    cursor = get_connection().cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        return cursor.fetchall()
    finally:
        cursor.close()


def fetch_one(query, params=None):
    """Run a SELECT and return its first row as a dict, or None if there is none."""
    rows = fetch_all(query, params)
    return rows[0] if rows else None


# Table names and columns here have to match the SQL in the service modules.
# tests/test_schema.py enforces that.
TABLE_DDL = {
    # A to-do list of string tasks.
    'todo': """
    CREATE TABLE IF NOT EXISTS todo (
        id INT AUTO_INCREMENT PRIMARY KEY,
        task VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # ingredients and instructions are JSON arrays of strings.
    'recipes': """
    CREATE TABLE IF NOT EXISTS recipes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        ingredients JSON NOT NULL,
        instructions JSON NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # streak is how many days in a row the habit has been completed.
    # last_completed is a DATE, not a TIMESTAMP: streaks are counted in whole
    # days, and a timestamp could never compare equal to "today".
    'habits': """
    CREATE TABLE IF NOT EXISTS habits (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        streak INT DEFAULT 0,
        last_completed DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    'blog': """
    CREATE TABLE IF NOT EXISTS blog (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # Disk is the source of truth for this table: scan-music rebuilds it, and
    # dropping it loses nothing. path is the natural key and rows are updated in
    # place so ids stay stable for future playlist references.
    # VARCHAR(768) is the longest utf8mb4 column that fits a full UNIQUE index
    # inside InnoDB's 3072-byte limit — 768 * 4 bytes lands exactly on it, with
    # no slack. On a server defaulting to ROW_FORMAT=COMPACT (767-byte cap)
    # create_tables() fails loudly with an index-too-long error rather than
    # silently truncating, which is the failure mode we want.
    'track': """
    CREATE TABLE IF NOT EXISTS track (
        id INT AUTO_INCREMENT PRIMARY KEY,
        path VARCHAR(768) NOT NULL UNIQUE,
        title VARCHAR(255),
        artist VARCHAR(255),
        album VARCHAR(255),
        track_no INT,
        duration_seconds INT,
        format VARCHAR(16) NOT NULL,
        size_bytes BIGINT NOT NULL,
        mtime BIGINT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
}


def create_tables():
    """Create every table in TABLE_DDL if it doesn't already exist.

    Runs outside a request, so call it inside `with app.app_context():`.
    """
    for ddl in TABLE_DDL.values():
        execute(ddl)


@click.command('init-db')
@with_appcontext
def init_db_command():
    """Create any tables that don't exist yet."""
    create_tables()
    click.echo(f"Tables ready: {', '.join(TABLE_DDL)}")
