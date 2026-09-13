import datetime

from flask import Blueprint, abort, jsonify

from api import json_body
from database.db import execute, fetch_all, fetch_one, insert

bp = Blueprint('habits', __name__)


def next_streak(last_completed, streak, today):
    """The streak after completing a habit on `today`.

    Completing again the same day leaves the streak alone, the day after
    continues it, and any longer gap (or a habit never completed) starts over
    at 1.
    """
    if last_completed == today:
        return streak
    if last_completed == today - datetime.timedelta(days=1):
        return streak + 1
    return 1

@bp.route('/habits', methods=['GET'])
def get_habits():
    return jsonify(fetch_all("SELECT * FROM habits ORDER BY id"))

@bp.route('/habits', methods=['POST'])
def create_habit():
    name, = json_body('name')
    new_id = insert("INSERT INTO habits (name) VALUES (?)", (name,))
    return {"id": new_id}, 201

@bp.route('/habits/<int:habit_id>', methods=['PUT'])
def update_habit(habit_id):
    name, = json_body('name')
    if not execute("UPDATE habits SET name = ? WHERE id = ?", (name, habit_id)):
        abort(404, description=f"no habit with id {habit_id}")
    return "", 204

@bp.route('/habits/<int:habit_id>', methods=['DELETE'])
def delete_habit(habit_id):
    if not execute("DELETE FROM habits WHERE id = ?", (habit_id,)):
        abort(404, description=f"no habit with id {habit_id}")
    return "", 204

@bp.route('/habits/<int:habit_id>/complete', methods=['POST'])
def complete_habit(habit_id):
    """Mark a habit done today. Calling it twice in a day changes nothing.

    Existence comes from the SELECT rather than the UPDATE's rowcount, because
    a same-day repeat writes identical values and so affects zero rows.
    """
    habit = fetch_one("SELECT * FROM habits WHERE id = ? LIMIT 1", (habit_id,))
    if habit is None:
        abort(404, description=f"no habit with id {habit_id}")

    today = datetime.date.today()
    streak = next_streak(habit['last_completed'], habit['streak'], today)
    execute(
        "UPDATE habits SET streak = ?, last_completed = ? WHERE id = ?",
        (streak, today, habit_id)
    )
    return jsonify({**habit, 'streak': streak, 'last_completed': today})
