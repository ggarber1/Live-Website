from flask import Blueprint, abort, jsonify

from api import json_body
from database.db import execute, fetch_all, insert

bp = Blueprint('blog', __name__)

@bp.route('/blog', methods=['GET'])
def get_blog():
    return jsonify(fetch_all("SELECT * FROM blog ORDER BY created_at DESC, id DESC"))

@bp.route('/blog', methods=['POST'])
def create_blog():
    title, content = json_body('title', 'content')
    new_id = insert(
        "INSERT INTO blog (title, content) VALUES (?, ?)",
        (title, content)
    )
    return {"id": new_id}, 201

@bp.route('/blog/<int:post_id>', methods=['PUT'])
def update_blog(post_id):
    title, content = json_body('title', 'content')
    updated = execute(
        "UPDATE blog SET title = ?, content = ? WHERE id = ?",
        (title, content, post_id)
    )
    if not updated:
        abort(404, description=f"no blog post with id {post_id}")
    return "", 204

@bp.route('/blog/<int:post_id>', methods=['DELETE'])
def delete_blog(post_id):
    if not execute("DELETE FROM blog WHERE id = ?", (post_id,)):
        abort(404, description=f"no blog post with id {post_id}")
    return "", 204
