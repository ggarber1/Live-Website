import importlib
import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

# app.py reads LIVS_TABLE and builds its boto3 client at import time, so both the
# env and the mock have to be in place before the fixture imports it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TABLE_NAME = 'livs-table-test'

os.environ.setdefault('LIVS_TABLE', TABLE_NAME)
os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
os.environ.setdefault('AWS_ACCESS_KEY_ID', 'testing')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'testing')


@pytest.fixture
def client():
    """Flask test client wired to a fresh, empty mock livs table."""
    with mock_aws():
        boto3.client('dynamodb').create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[
                {'AttributeName': 'PK', 'AttributeType': 'S'},
                {'AttributeName': 'SK', 'AttributeType': 'S'},
            ],
            KeySchema=[
                {'AttributeName': 'PK', 'KeyType': 'HASH'},
                {'AttributeName': 'SK', 'KeyType': 'RANGE'},
            ],
            ProvisionedThroughput={'ReadCapacityUnits': 1, 'WriteCapacityUnits': 1},
        )

        # Reload so the module-level client is rebuilt inside this mock_aws block.
        import app

        importlib.reload(app)
        app.app.config.update(TESTING=True)

        yield app.app.test_client()
