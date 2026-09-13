from flask import Blueprint, abort, jsonify

from api import json_body
from database.db import execute, fetch_all, insert

bp = Blueprint('todo', __name__)

@bp.route('/todo', methods=['GET'])
def get_todo():
    return jsonify(fetch_all("SELECT * FROM todo ORDER BY id"))

@bp.route('/todo', methods=['POST'])
def create_todo():
    task, = json_body('task')
    new_id = insert("INSERT INTO todo (task) VALUES (?)", (task,))
    return {"id": new_id}, 201

@bp.route('/todo/<int:todo_id>', methods=['PUT'])
def update_todo(todo_id):
    task, = json_body('task')
    if not execute("UPDATE todo SET task = ? WHERE id = ?", (task, todo_id)):
        abort(404, description=f"no todo with id {todo_id}")
    return "", 204

@bp.route('/todo/<int:todo_id>', methods=['DELETE'])
def delete_todo(todo_id):
    if not execute("DELETE FROM todo WHERE id = ?", (todo_id,)):
        abort(404, description=f"no todo with id {todo_id}")
    return "", 204
