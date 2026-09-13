import json

from flask import Blueprint, abort, jsonify

from api import json_body
from database.db import execute, fetch_all, insert

bp = Blueprint('recipes', __name__)

# Columns stored as SQL JSON. The API takes and returns real arrays; these are
# the only places the serialized form exists.
JSON_COLUMNS = ('ingredients', 'instructions')


def to_json_column(name, value):
    """Serialize an array of strings for storage, or 400 if it isn't one.

    Passing a Python list straight to the driver doesn't work: it stringifies
    with repr(), producing ['bread'] with single quotes, which the server
    rejects as invalid JSON text.
    """
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        abort(400, description=f"{name} must be an array of strings")
    return json.dumps(value)


def from_json_columns(row):
    """Turn a row's stored JSON columns back into real lists.

    MySQL returns JSON columns as bytes; MariaDB, where JSON is an alias for
    LONGTEXT, returns str. Both have to decode, or the Pi and this laptop
    disagree.
    """
    decoded = dict(row)
    for column in JSON_COLUMNS:
        value = decoded.get(column)
        if isinstance(value, (bytes, bytearray)):
            value = value.decode()
        if isinstance(value, str):
            decoded[column] = json.loads(value)
    return decoded


@bp.route('/recipes', methods=['GET'])
def get_recipes():
    rows = fetch_all("SELECT * FROM recipes ORDER BY id")
    return jsonify([from_json_columns(row) for row in rows])

@bp.route('/recipes', methods=['POST'])
def create_recipe():
    title, ingredients, instructions = json_body('title', 'ingredients', 'instructions')
    new_id = insert(
        "INSERT INTO recipes (title, ingredients, instructions) VALUES (?, ?, ?)",
        (title,
         to_json_column('ingredients', ingredients),
         to_json_column('instructions', instructions))
    )
    return {"id": new_id}, 201

@bp.route('/recipes/<int:recipe_id>', methods=['PUT'])
def update_recipe(recipe_id):
    title, ingredients, instructions = json_body('title', 'ingredients', 'instructions')
    updated = execute(
        "UPDATE recipes SET title = ?, ingredients = ?, instructions = ? WHERE id = ?",
        (title,
         to_json_column('ingredients', ingredients),
         to_json_column('instructions', instructions),
         recipe_id)
    )
    if not updated:
        abort(404, description=f"no recipe with id {recipe_id}")
    return "", 204

@bp.route('/recipes/<int:recipe_id>', methods=['DELETE'])
def delete_recipe(recipe_id):
    if not execute("DELETE FROM recipes WHERE id = ?", (recipe_id,)):
        abort(404, description=f"no recipe with id {recipe_id}")
    return "", 204
