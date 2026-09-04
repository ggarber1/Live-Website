import os
import sys
from pathlib import Path

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
