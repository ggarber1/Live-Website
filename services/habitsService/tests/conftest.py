import importlib
import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

# The service modules live one directory up from tests/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TABLE_NAME = 'livs-table-test'

# Assigned, not setdefault: store.py reads LIVS_TABLE at import time, and an
# ambient LIVS_TABLE from the developer's shell would point it at a table the
# fixture never creates -- a ResourceNotFoundException only they can reproduce.
os.environ['LIVS_TABLE'] = TABLE_NAME

# setdefault is fine for these: moto ignores the values, it just needs them set.
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

        import app

        # Reload so store's module-level client and LIVS_TABLE are rebuilt
        # inside this mock_aws block. moto patches botocore globally, so a
        # client built in an earlier block would still be intercepted -- the
        # reload just keeps this fixture from depending on that detail.
        importlib.reload(app.store)
        app.app.config.update(TESTING=True)

        yield app.app.test_client()
