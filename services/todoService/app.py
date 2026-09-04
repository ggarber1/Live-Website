import os
import uuid
from typing import TYPE_CHECKING

import boto3
from flask import Flask, jsonify, make_response, request

if TYPE_CHECKING:
    from types_boto3_dynamodb import DynamoDBClient

app = Flask(__name__)


dynamodb_client: 'DynamoDBClient' = boto3.client('dynamodb')

if os.environ.get('IS_OFFLINE'):
    dynamodb_client = boto3.client(
        'dynamodb', region_name='localhost', endpoint_url='http://localhost:8000'
    )

LIVS_TABLE = os.environ['LIVS_TABLE']

# Partition this service owns in the shared table. Items are keyed
# (PK='TODO', SK=<uuid>), so one Query returns every todo.
TODO_PK = 'TODO'


@app.route('/todo')
def get_todo():
    try:
        response = dynamodb_client.query(
            TableName=LIVS_TABLE,
            # Define the condition for the Partition Key
            KeyConditionExpression='PK = :pk_val',
            # Map the placeholder token to the actual value and type
            ExpressionAttributeValues={':pk_val': {'S': TODO_PK}},
        )
    except Exception:
        app.logger.exception('Error fetching todo items')
        return make_response(jsonify({'error': 'Failed to fetch todo items'}), 500)

    return jsonify(
        [
            {'id': item['SK']['S'], 'todo': item.get('todo', {}).get('S')}
            for item in response.get('Items', [])
        ]
    )


def _json_object_body():
    """Return the request body as a dict, or {} if it isn't a JSON object.

    Not `get_json(silent=True) or {}`: valid JSON that parses to a truthy
    non-dict (a list, string, number) would pass through and blow up on .get()
    with an AttributeError, which escapes as an HTML 500 rather than a JSON 400.
    """
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


@app.route('/todo', methods=['POST'])
def create_todo():
    todo_data = _json_object_body()
    todo_text = todo_data.get('todo')

    if not todo_text:
        return make_response(jsonify({'error': 'Missing "todo" in request body'}), 400)

    todo_id = str(uuid.uuid4())
    try:
        dynamodb_client.put_item(
            TableName=LIVS_TABLE,
            Item={
                'PK': {'S': TODO_PK},
                'SK': {'S': todo_id},
                'todo': {'S': todo_text},
            },
        )
    except Exception:
        app.logger.exception('Error creating todo item')
        return make_response(jsonify({'error': 'Failed to create todo item'}), 500)

    return make_response(jsonify({'id': todo_id, 'todo': todo_text}), 201)


@app.route('/todo', methods=['PUT'])
def update_todo():
    todo_data = _json_object_body()
    todo_id = todo_data.get('id')
    todo_text = todo_data.get('todo')

    if not todo_id or not todo_text:
        return make_response(
            jsonify({'error': 'Missing "id" or "todo" in request body'}), 400
        )

    try:
        dynamodb_client.update_item(
            TableName=LIVS_TABLE,
            Key={'PK': {'S': TODO_PK}, 'SK': {'S': todo_id}},
            UpdateExpression='SET todo = :todo_val',
            ExpressionAttributeValues={':todo_val': {'S': todo_text}},
            # Without this an update to an unknown id silently creates a todo.
            ConditionExpression='attribute_exists(SK)',
        )
    except dynamodb_client.exceptions.ConditionalCheckFailedException:
        return make_response(jsonify({'error': 'No todo item with provided "id"'}), 404)
    except Exception:
        app.logger.exception('Error updating todo item')
        return make_response(jsonify({'error': 'Failed to update todo item'}), 500)

    return jsonify({'id': todo_id, 'todo': todo_text})


@app.route('/todo', methods=['DELETE'])
def delete_todo():
    todo_data = _json_object_body()
    todo_id = todo_data.get('id')

    if not todo_id:
        return make_response(jsonify({'error': 'Missing "id" in request body'}), 400)

    try:
        dynamodb_client.delete_item(
            TableName=LIVS_TABLE,
            Key={'PK': {'S': TODO_PK}, 'SK': {'S': todo_id}},
            ConditionExpression='attribute_exists(SK)',
        )
    except dynamodb_client.exceptions.ConditionalCheckFailedException:
        return make_response(jsonify({'error': 'No todo item with provided "id"'}), 404)
    except Exception:
        app.logger.exception('Error deleting todo item')
        return make_response(jsonify({'error': 'Failed to delete todo item'}), 500)

    return jsonify({'message': 'Todo item deleted successfully'})


@app.errorhandler(404)
def resource_not_found(e):
    return make_response(jsonify(error='Not found!'), 404)
