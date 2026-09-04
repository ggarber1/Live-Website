"""Habit tracker API.

A thin HTTP layer: parse the request, delegate, map failures to status codes.
The DynamoDB item layout lives in store.py and the date rules in dates.py.
"""

from __future__ import annotations

from flask import Flask, jsonify, make_response, request

import dates
import store

app = Flask(__name__)


def _habit_name_from_body():
    """Pull a validated habit name out of the request body.

    Returns (name, None) on success or (None, response) on a bad request.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, make_response(
            jsonify({'error': 'Expected a JSON object request body'}), 400
        )

    name = body.get('name')
    if not isinstance(name, str) or not name.strip():
        return None, make_response(
            jsonify({'error': 'Missing "name" in request body'}), 400
        )
    return name.strip(), None


def _habit_not_found(habit_id):
    return make_response(jsonify({'error': f'No habit with id "{habit_id}"'}), 404)


@app.route('/habits')
def list_habits():
    try:
        from_date, to_date = dates.resolve_window(
            request.args.get('from'), request.args.get('to')
        )
    except dates.InvalidDate as e:
        return make_response(jsonify({'error': str(e)}), 400)

    try:
        return jsonify(store.list_habits(from_date, to_date))
    except Exception:
        app.logger.exception('Error listing habits')
        return make_response(jsonify({'error': 'Failed to list habits'}), 500)


@app.route('/habits', methods=['POST'])
def create_habit():
    name, error = _habit_name_from_body()
    if error:
        return error

    try:
        return make_response(jsonify(store.create_habit(name)), 201)
    except Exception:
        app.logger.exception('Error creating habit')
        return make_response(jsonify({'error': 'Failed to create habit'}), 500)


@app.route('/habits/<habit_id>', methods=['PUT'])
def rename_habit(habit_id):
    name, error = _habit_name_from_body()
    if error:
        return error

    try:
        return jsonify(store.rename_habit(habit_id, name))
    except store.HabitNotFound:
        return _habit_not_found(habit_id)
    except Exception:
        app.logger.exception('Error renaming habit')
        return make_response(jsonify({'error': 'Failed to rename habit'}), 500)


@app.route('/habits/<habit_id>', methods=['DELETE'])
def delete_habit(habit_id):
    try:
        store.delete_habit(habit_id)
    except store.HabitNotFound:
        return _habit_not_found(habit_id)
    except Exception:
        app.logger.exception('Error deleting habit')
        return make_response(jsonify({'error': 'Failed to delete habit'}), 500)

    return jsonify({'message': 'Habit deleted successfully'})


@app.route('/habits/<habit_id>/completions/<completion_date>', methods=['PUT'])
def mark_done(habit_id, completion_date):
    try:
        completion_date = dates.canonical_date(completion_date)
    except dates.InvalidDate as e:
        return make_response(jsonify({'error': str(e)}), 400)

    try:
        return jsonify(store.mark_done(habit_id, completion_date))
    except store.HabitNotFound:
        return _habit_not_found(habit_id)
    except Exception:
        app.logger.exception('Error marking habit done')
        return make_response(jsonify({'error': 'Failed to mark habit done'}), 500)


@app.route('/habits/<habit_id>/completions/<completion_date>', methods=['DELETE'])
def unmark_done(habit_id, completion_date):
    try:
        completion_date = dates.canonical_date(completion_date)
    except dates.InvalidDate as e:
        return make_response(jsonify({'error': str(e)}), 400)

    try:
        store.unmark_done(habit_id, completion_date)
    except store.HabitNotFound:
        return _habit_not_found(habit_id)
    except Exception:
        app.logger.exception('Error unmarking habit')
        return make_response(jsonify({'error': 'Failed to unmark habit'}), 500)

    return jsonify({'message': 'Completion removed successfully'})


@app.errorhandler(404)
def resource_not_found(e):
    return make_response(jsonify(error='Not found!'), 404)
