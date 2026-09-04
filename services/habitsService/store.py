"""DynamoDB access for habits and their completions.

Item layout in the shared table, both types owned by this service:

    habit       PK='HABIT'        SK='<uuid4>'      name
    completion  PK='HABIT#<id>'   SK='2026-09-03'

A completion carries no attributes -- the existence of the item is the fact
being recorded, which makes marking a habit done idempotent for free.
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from types_boto3_dynamodb import DynamoDBClient

dynamodb_client: DynamoDBClient = boto3.client('dynamodb')

if os.environ.get('IS_OFFLINE'):
    dynamodb_client = boto3.client(
        'dynamodb', region_name='localhost', endpoint_url='http://localhost:8000'
    )

LIVS_TABLE = os.environ['LIVS_TABLE']

HABIT_PK = 'HABIT'


class HabitNotFound(LookupError):
    """Raised when an operation names a habit id that does not exist."""


def _completions_pk(habit_id: str) -> str:
    return f'{HABIT_PK}#{habit_id}'


def _query_all(**kwargs) -> list:
    """Run a Query, following LastEvaluatedKey until the result set is done.

    A single Query returns at most 1MB. Ignoring the continuation token would
    silently drop items -- dates out of the middle of a requested range.
    """
    items = []
    while True:
        response = dynamodb_client.query(**kwargs)
        items.extend(response.get('Items', []))

        last_key = response.get('LastEvaluatedKey')
        if not last_key:
            return items

        kwargs = {**kwargs, 'ExclusiveStartKey': last_key}


def create_habit(name: str) -> dict:
    habit_id = str(uuid.uuid4())
    dynamodb_client.put_item(
        TableName=LIVS_TABLE,
        Item={
            'PK': {'S': HABIT_PK},
            'SK': {'S': habit_id},
            'name': {'S': name},
        },
    )
    return {'id': habit_id, 'name': name}


def list_habits(from_date: str, to_date: str) -> list:
    """Every habit, each with its completion dates inside the given window."""
    habits = _query_all(
        TableName=LIVS_TABLE,
        KeyConditionExpression='PK = :pk',
        ExpressionAttributeValues={':pk': {'S': HABIT_PK}},
    )
    return [
        {
            'id': habit['SK']['S'],
            'name': habit.get('name', {}).get('S'),
            'dates': _completion_dates(habit['SK']['S'], from_date, to_date),
        }
        for habit in habits
    ]


def rename_habit(habit_id: str, name: str) -> dict:
    try:
        dynamodb_client.update_item(
            TableName=LIVS_TABLE,
            Key={'PK': {'S': HABIT_PK}, 'SK': {'S': habit_id}},
            # "name" is a DynamoDB reserved word, so it has to go through an
            # expression attribute name. SET name = :name is a ValidationException.
            UpdateExpression='SET #name = :name',
            ExpressionAttributeNames={'#name': 'name'},
            ExpressionAttributeValues={':name': {'S': name}},
            # Without this, renaming an unknown id silently creates a habit.
            ConditionExpression='attribute_exists(SK)',
        )
    except dynamodb_client.exceptions.ConditionalCheckFailedException as e:
        raise HabitNotFound(habit_id) from e

    return {'id': habit_id, 'name': name}


def _completion_dates(habit_id: str, from_date: str, to_date: str) -> list:
    items = _query_all(
        TableName=LIVS_TABLE,
        KeyConditionExpression='PK = :pk AND SK BETWEEN :from_date AND :to_date',
        ExpressionAttributeValues={
            ':pk': {'S': _completions_pk(habit_id)},
            ':from_date': {'S': from_date},
            ':to_date': {'S': to_date},
        },
        ProjectionExpression='SK',
    )
    # Query returns sort-key order, so these come back ascending already.
    return [item['SK']['S'] for item in items]
