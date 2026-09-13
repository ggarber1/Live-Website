import os

import flask
from dotenv import load_dotenv
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

# Before anything reads DB_* or CORS_ORIGINS out of the environment.
load_dotenv()

from blog.blog import bp as blog_bp
from database import db
from habits.habits import bp as habits_bp
from music.scanner import scan_music_command
from recipes.recipes import bp as recipes_bp
from todo.todo import bp as todo_bp

# Local dev servers. Set CORS_ORIGINS in .env to the real frontend origin.
DEFAULT_CORS_ORIGINS = 'http://localhost:5173,http://localhost:3000'


def cors_origins():
    """Allowed browser origins, comma-separated in CORS_ORIGINS.

    An explicit list rather than "*": a wildcard lets any page on the network
    call this API with the browser's credentials attached.
    """
    raw = os.environ.get('CORS_ORIGINS', DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(',') if origin.strip()]


app = flask.Flask(__name__)
CORS(app, origins=cors_origins())

db.init_app(app)
app.cli.add_command(scan_music_command)

app.register_blueprint(blog_bp)
app.register_blueprint(habits_bp)
app.register_blueprint(recipes_bp)
app.register_blueprint(todo_bp)


@app.errorhandler(HTTPException)
def json_error(err):
    return {"error": err.description}, err.code


@app.errorhandler(500)
def unexpected_error(err):
    """Return JSON for crashes instead of Werkzeug's HTML page.

    With DEBUG off there's no interactive traceback, so the detail goes to the
    log and the client gets a generic message rather than internals. Registered
    on 500 rather than Exception so PROPAGATE_EXCEPTIONS still applies and tests
    keep seeing real tracebacks.
    """
    app.logger.exception("unhandled error serving %s", flask.request.path)
    return {"error": "internal server error"}, 500


@app.route('/', methods=['GET'])
def howdy():
    return "Howdy!"


if __name__ == "__main__":
    # Under gunicorn this block never runs — use `flask --app app init-db`.
    with app.app_context():
        db.create_tables()
    # 0.0.0.0 so other machines on the network can reach the Pi. Debug stays off
    # unless FLASK_DEBUG is set: the Werkzeug console is remote code execution
    # for anyone who can reach it.
    app.run(host=os.environ.get('HOST', '0.0.0.0'),
            port=int(os.environ.get('PORT', '5000')))
