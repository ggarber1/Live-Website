# habitsService Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a habit tracker API in `services/habitsService` where habits can be created, renamed and deleted, and each habit carries the set of dates it was completed on.

**Architecture:** A Flask app packaged by `serverless-wsgi` into a single Lambda, following `services/todoService`. Split into three modules by responsibility: `dates.py` (pure date rules, no AWS), `store.py` (all DynamoDB access and the item layout), `app.py` (HTTP routing and status-code mapping). Data lives in the shared table owned by `infraService`, with habits at `PK='HABIT', SK='<uuid>'` and completions at `PK='HABIT#<id>', SK='<YYYY-MM-DD>'`.

**Tech Stack:** Python 3.14 on Lambda (arm64), Flask 3.1.3, boto3, Serverless Framework v4 with `serverless-wsgi`, DynamoDB. Tests use pytest + moto.

**Design spec:** `docs/superpowers/specs/2026-09-03-habits-service-design.md`

---

## Before you start

**Branch first.** The repo's default branch is `main` and this plan commits after
every task. Create a feature branch before Task 1:

```bash
git checkout -b habits-service
```

**Two environment facts that will bite you if you miss them:**

1. **The local venv is Python 3.9** (`activate/` at the repo root), while
   `provider.runtime` is `python3.14`. Tests run on 3.9, so do not use `X | Y`
   union annotations. Every module below starts with
   `from __future__ import annotations`, which makes the 3.9+ builtin generics
   and 3.10+ union syntax safe as annotations.

2. **`name` is a DynamoDB reserved word.** An `UpdateExpression` of
   `SET name = :name` fails with a `ValidationException`. The rename in Task 4
   uses `ExpressionAttributeNames={'#name': 'name'}`. Do not "simplify" it away.

Run everything from `services/habitsService`. The venv python is
`../../activate/bin/python`.

## File structure

| File | Responsibility |
| ---- | -------------- |
| `services/habitsService/dates.py` | **Create.** Pure date rules: canonical ISO validation, default window resolution. No AWS, no Flask, unit-testable with no mocking. |
| `services/habitsService/store.py` | **Create.** Every DynamoDB call, plus the PK/SK layout and the `HabitNotFound` error. The only module that knows the table shape. |
| `services/habitsService/app.py` | **Rewrite.** Flask routes only: parse request, delegate, map failures to status codes. Currently the template's users CRUD. |
| `services/habitsService/requirements.txt` | **Modify.** Currently `Flask` only; add `boto3`. |
| `services/habitsService/requirements-dev.txt` | **Create.** Type stubs, moto, pytest. |
| `services/habitsService/serverless.yml` | **Rewrite.** Single `api` function, cf refs to infraService, no `resources` block. |
| `services/habitsService/package.json` | **Modify.** Fix the template description. |
| `services/habitsService/README.md` | **Rewrite.** Currently the upstream template readme. |
| `services/habitsService/tests/conftest.py` | **Create.** `sys.path` + env setup, and the moto-backed `client` fixture. |
| `services/habitsService/tests/test_dates.py` | **Create.** Unit tests for `dates.py`. |
| `services/habitsService/tests/test_habits.py` | **Create.** HTTP tests for habit CRUD, plus the one direct test of `store._query_all` (unreachable over HTTP without a 1MB result set). |
| `services/habitsService/tests/test_completions.py` | **Create.** HTTP tests for marking/unmarking and window filtering. |

`store.py` is not tested directly — it is covered through the Flask test client,
which is what the spec's test list describes. Only `dates.py` gets unit tests,
because it is pure and its edge cases are tedious to reach over HTTP.

`services/todoService/app.py` stays a single file. Do not refactor it to match
this three-module split; that is unrequested work.

---

### Task 1: Dependencies and test scaffolding

**Files:**
- Modify: `services/habitsService/requirements.txt`
- Create: `services/habitsService/requirements-dev.txt`
- Create: `services/habitsService/tests/conftest.py`

- [ ] **Step 1: Pin boto3 as a real dependency**

`requirements.txt` currently contains only `Flask==3.1.3`. boto3 happens to be
present in the Lambda runtime, so the template worked by accident; relying on the
runtime-provided version invites silent drift. Replace the whole file with:

```
Flask==3.1.3
boto3
```

- [ ] **Step 2: Create the dev requirements**

Create `services/habitsService/requirements-dev.txt`:

```
-r requirements.txt

# Type stubs -- imported under TYPE_CHECKING only, so they must stay out of
# requirements.txt or they get packaged into the Lambda for nothing.
types-boto3-dynamodb

moto[dynamodb]
pytest
werkzeug
```

- [ ] **Step 3: Install them**

```bash
../../activate/bin/pip install -q -r requirements-dev.txt
```

Expected: no output beyond a possible pip-upgrade notice.

- [ ] **Step 4: Create the test scaffolding**

Create `services/habitsService/tests/conftest.py`. The `client` fixture is added
in Task 3; this task only sets up imports and fake credentials.

```python
import os
import sys
from pathlib import Path

# The service modules live one directory up from tests/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TABLE_NAME = 'livs-table-test'

os.environ.setdefault('LIVS_TABLE', TABLE_NAME)
os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
os.environ.setdefault('AWS_ACCESS_KEY_ID', 'testing')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'testing')
```

- [ ] **Step 5: Verify pytest collects cleanly with no tests yet**

Run: `../../activate/bin/python -m pytest tests/ -q`
Expected: `no tests ran` (exit code 5). Not an import error — if you see
`ModuleNotFoundError`, the install in Step 3 failed.

- [ ] **Step 6: Commit**

```bash
git add services/habitsService/requirements.txt \
        services/habitsService/requirements-dev.txt \
        services/habitsService/tests/conftest.py
git commit -m "chore(habits): add test scaffolding and pin boto3

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `dates.py` — canonical dates and the default window

**Files:**
- Create: `services/habitsService/dates.py`
- Test: `services/habitsService/tests/test_dates.py`

Why this module exists: a completion date becomes a DynamoDB **sort key**, and
the range query uses lexical `BETWEEN`. `date.fromisoformat()` on Python 3.11+
accepts `20260903`, which would sort nowhere near `2026-09-03` and silently
corrupt every range read. So dates are parsed, re-emitted via `.isoformat()`, and
**rejected** if the round trip does not match the input.

- [ ] **Step 1: Write the failing tests**

Create `services/habitsService/tests/test_dates.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from dates import DEFAULT_WINDOW_DAYS, InvalidDate, canonical_date, resolve_window


def test_canonical_date_accepts_canonical_iso():
    assert canonical_date('2026-09-03') == '2026-09-03'


@pytest.mark.parametrize(
    'value', ['20260903', '2026-9-3', '03/09/2026', 'today', '', '2026-13-01']
)
def test_canonical_date_rejects_anything_non_canonical(value):
    with pytest.raises(InvalidDate):
        canonical_date(value)


def test_canonical_date_rejects_non_string():
    with pytest.raises(InvalidDate):
        canonical_date(None)


def test_resolve_window_uses_both_params_when_given():
    assert resolve_window('2026-01-01', '2026-01-31') == ('2026-01-01', '2026-01-31')


def test_resolve_window_allows_a_single_day_range():
    assert resolve_window('2026-01-05', '2026-01-05') == ('2026-01-05', '2026-01-05')


def test_resolve_window_defaults_from_to_a_window_ending_at_to():
    # 30 days inclusive of both ends, so Jan 31 back to Jan 2.
    assert resolve_window(None, '2026-01-31') == ('2026-01-02', '2026-01-31')


def test_resolve_window_defaults_to_to_utc_today():
    today = datetime.now(timezone.utc).date()
    from_date, to_date = resolve_window(None, None)

    assert to_date == today.isoformat()
    assert from_date == (today - timedelta(days=DEFAULT_WINDOW_DAYS - 1)).isoformat()


def test_resolve_window_keeps_explicit_from_with_default_to():
    today = datetime.now(timezone.utc).date()

    assert resolve_window('2026-01-01', None) == ('2026-01-01', today.isoformat())


def test_resolve_window_rejects_a_reversed_range():
    with pytest.raises(InvalidDate):
        resolve_window('2026-02-01', '2026-01-01')


def test_resolve_window_rejects_a_malformed_param():
    with pytest.raises(InvalidDate):
        resolve_window('20260101', '2026-01-31')
```

Note on `'20260903'`: on Python 3.9 it fails at the `fromisoformat` parse; on
3.11+ it parses and then fails the canonical-form comparison. The test passes
either way, which is what we want given the local/Lambda version split.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../activate/bin/python -m pytest tests/test_dates.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'dates'`.

- [ ] **Step 3: Write the implementation**

Create `services/habitsService/dates.py`:

```python
"""Date rules for habit completions.

A completion date becomes a DynamoDB sort key and the range read uses lexical
BETWEEN, so only canonical zero-padded YYYY-MM-DD is allowed through.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# Inclusive of both ends, so the default window is `to` and the 29 days before it.
DEFAULT_WINDOW_DAYS = 30


class InvalidDate(ValueError):
    """Raised when a caller-supplied date is not a canonical ISO date."""


def canonical_date(value: str) -> str:
    """Return `value` unchanged if it is canonical YYYY-MM-DD, else raise.

    date.fromisoformat() is lenient on Python 3.11+ and accepts forms such as
    '20260903'. Such a string would parse fine and then sort nowhere near its
    neighbours as a sort key, so anything that does not survive an
    isoformat() round trip is rejected rather than quietly rewritten.
    """
    if not isinstance(value, str):
        raise InvalidDate(f'Expected an ISO date string, got {type(value).__name__}')

    try:
        parsed = date.fromisoformat(value)
    except ValueError as e:
        raise InvalidDate(f'"{value}" is not a valid date, expected YYYY-MM-DD') from e

    if parsed.isoformat() != value:
        raise InvalidDate(f'"{value}" is not canonical, expected {parsed.isoformat()}')

    return value


def resolve_window(from_param, to_param) -> tuple[str, str]:
    """Turn optional from/to params into an inclusive (from, to) date range.

    `to` defaults to today in UTC and `from` to a DEFAULT_WINDOW_DAYS window
    ending at `to`. A server-side UTC "today" is deliberate here: a window
    boundary being a few hours out shows the same grid, whereas mis-dating a
    completion would be a real bug, and the client always supplies that date.
    """
    to_date = canonical_date(to_param) if to_param else _utc_today().isoformat()

    if from_param:
        from_date = canonical_date(from_param)
    else:
        window_start = date.fromisoformat(to_date) - timedelta(
            days=DEFAULT_WINDOW_DAYS - 1
        )
        from_date = window_start.isoformat()

    if from_date > to_date:
        raise InvalidDate(f'"from" ({from_date}) is after "to" ({to_date})')

    return from_date, to_date


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `../../activate/bin/python -m pytest tests/test_dates.py -q`
Expected: `20 passed` (the parametrized rejection test counts as eight).

- [ ] **Step 5: Commit**

```bash
git add services/habitsService/dates.py services/habitsService/tests/test_dates.py
git commit -m "feat(habits): add canonical date parsing and window resolution

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `store.py` foundation, plus `GET` and `POST /habits`

**Files:**
- Create: `services/habitsService/store.py`
- Rewrite: `services/habitsService/app.py`
- Modify: `services/habitsService/tests/conftest.py`
- Test: `services/habitsService/tests/test_habits.py`

- [ ] **Step 1: Add the `client` fixture to conftest**

Append to `services/habitsService/tests/conftest.py`:

```python
import importlib

import boto3
import pytest
from moto import mock_aws


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

        # store builds its boto3 client at import time. reload() re-executes it
        # in the module's existing dict, so app.store -- the same module object --
        # picks up a client created inside this mock_aws block. Without this,
        # every test after the first would talk to an expired mock.
        importlib.reload(app.store)
        app.app.config.update(TESTING=True)

        yield app.app.test_client()
```

Move the `import importlib`, `import boto3`, `import pytest` and
`from moto import mock_aws` lines up to the existing import block at the top of
the file rather than leaving them mid-file.

- [ ] **Step 2: Write the failing tests**

Create `services/habitsService/tests/test_habits.py`:

```python
def test_create_habit_returns_id_and_name(client):
    response = client.post('/habits', json={'name': 'floss'})

    assert response.status_code == 201
    body = response.get_json()
    assert body['name'] == 'floss'
    assert body['id']


def test_create_habit_strips_surrounding_whitespace(client):
    response = client.post('/habits', json={'name': '  floss  '})

    assert response.status_code == 201
    assert response.get_json()['name'] == 'floss'


def test_create_habit_without_a_name_is_rejected(client):
    response = client.post('/habits', json={})

    assert response.status_code == 400
    assert 'name' in response.get_json()['error']


def test_create_habit_with_a_blank_name_is_rejected(client):
    response = client.post('/habits', json={'name': '   '})

    assert response.status_code == 400


def test_create_habit_without_a_json_body_is_rejected_not_crashed(client):
    response = client.post('/habits', data='name=floss')

    assert response.status_code == 400


def test_list_habits_is_empty_before_anything_is_created(client):
    response = client.get('/habits')

    assert response.status_code == 200
    assert response.get_json() == []


def test_list_habits_returns_created_habits_with_no_dates(client):
    client.post('/habits', json={'name': 'floss'})

    response = client.get('/habits')

    assert response.status_code == 200
    body = response.get_json()
    assert len(body) == 1
    assert body[0]['name'] == 'floss'
    assert body[0]['dates'] == []


def test_habits_may_share_a_name_and_stay_distinct(client):
    first = client.post('/habits', json={'name': 'floss'}).get_json()['id']
    second = client.post('/habits', json={'name': 'floss'}).get_json()['id']

    assert first != second
    assert len(client.get('/habits').get_json()) == 2


def test_list_habits_rejects_a_malformed_date_param(client):
    response = client.get('/habits?from=20260101')

    assert response.status_code == 400


def test_list_habits_rejects_a_reversed_range(client):
    response = client.get('/habits?from=2026-02-01&to=2026-01-01')

    assert response.status_code == 400


def test_query_all_follows_the_continuation_token(client, monkeypatch):
    """A Query returning LastEvaluatedKey must be followed, or dates go missing.

    Not reachable over HTTP without pushing a habit past 1MB, so the paginator
    is driven directly with a stubbed client.
    """
    import store

    pages = [
        {'Items': [{'SK': {'S': 'a'}}], 'LastEvaluatedKey': {'SK': {'S': 'a'}}},
        {'Items': [{'SK': {'S': 'b'}}]},
    ]
    calls = []

    def fake_query(**kwargs):
        calls.append(kwargs)
        return pages[len(calls) - 1]

    monkeypatch.setattr(store.dynamodb_client, 'query', fake_query)

    assert store._query_all(TableName='t') == [{'SK': {'S': 'a'}}, {'SK': {'S': 'b'}}]
    assert 'ExclusiveStartKey' not in calls[0]
    assert calls[1]['ExclusiveStartKey'] == {'SK': {'S': 'a'}}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `../../activate/bin/python -m pytest tests/test_habits.py -q`
Expected: every test errors in the fixture with
`ModuleNotFoundError: No module named 'store'` (raised while importing `app`).

- [ ] **Step 4: Write `store.py`**

Create `services/habitsService/store.py`:

```python
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
```

- [ ] **Step 5: Write `app.py`**

Replace the entire contents of `services/habitsService/app.py` (currently the
template's users CRUD) with:

```python
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
    # Not `or {}`: valid JSON that parses to a truthy non-dict (a list, string,
    # number) would pass through and blow up on .get() with an AttributeError,
    # which escapes as an HTML 500 rather than a JSON 400.
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


@app.errorhandler(404)
def resource_not_found(e):
    return make_response(jsonify(error='Not found!'), 404)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `../../activate/bin/python -m pytest tests/ -q`
Expected: `32 passed` (20 from Task 2, 12 here).

- [ ] **Step 7: Commit**

```bash
git add services/habitsService/store.py services/habitsService/app.py \
        services/habitsService/tests/conftest.py \
        services/habitsService/tests/test_habits.py
git commit -m "feat(habits): list and create habits

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `PUT /habits/<id>` — rename

**Files:**
- Modify: `services/habitsService/store.py`
- Modify: `services/habitsService/app.py`
- Test: `services/habitsService/tests/test_habits.py`

- [ ] **Step 1: Write the failing tests**

Append to `services/habitsService/tests/test_habits.py`:

```python
def test_rename_habit_changes_the_name(client):
    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']

    response = client.put(f'/habits/{habit_id}', json={'name': 'floss nightly'})

    assert response.status_code == 200
    assert response.get_json() == {'id': habit_id, 'name': 'floss nightly'}
    assert client.get('/habits').get_json()[0]['name'] == 'floss nightly'


def test_rename_habit_with_unknown_id_is_404_and_creates_nothing(client):
    response = client.put('/habits/not-a-real-id', json={'name': 'ghost'})

    assert response.status_code == 404
    assert client.get('/habits').get_json() == []


def test_rename_habit_without_a_name_is_rejected(client):
    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']

    response = client.put(f'/habits/{habit_id}', json={})

    assert response.status_code == 400
    assert client.get('/habits').get_json()[0]['name'] == 'floss'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../activate/bin/python -m pytest tests/test_habits.py -q`
Expected: `2 failed, 13 passed`. With no `/habits/<habit_id>` rule registered at
all, Flask 404s on the path rather than returning `405 Method Not Allowed`, so
`test_rename_habit_changes_the_name` and `test_rename_habit_without_a_name_is_rejected`
fail — but `test_rename_habit_with_unknown_id_is_404_and_creates_nothing` passes
*coincidentally*, since a routing 404 satisfies its only status assertion.

That coincidence means the test cannot tell our `_habit_not_found` 404 apart from
Flask's router 404, so Step 5 strengthens it to assert on the response body.

- [ ] **Step 3: Add `rename_habit` to `store.py`**

Append to `services/habitsService/store.py`:

```python
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
```

- [ ] **Step 4: Add the route to `app.py`**

Insert into `services/habitsService/app.py`, after `create_habit` and before the
`@app.errorhandler(404)` handler:

```python
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
```

- [ ] **Step 5: Strengthen the unknown-id test, then run the suite**

Because a Flask routing 404 and our `_habit_not_found` 404 are indistinguishable
by status code alone, add a body assertion to
`test_rename_habit_with_unknown_id_is_404_and_creates_nothing` so it can only
pass via our handler. Our handler returns `{'error': 'No habit with id "..."'}`;
Flask's router returns `{'error': 'Not found!'}`.

```python
def test_rename_habit_with_unknown_id_is_404_and_creates_nothing(client):
    response = client.put('/habits/not-a-real-id', json={'name': 'ghost'})

    assert response.status_code == 404
    # Body, not just status: a Flask routing 404 would also be 404, so this is
    # what proves the response came from our handler rather than the router.
    assert 'not-a-real-id' in response.get_json()['error']
    assert client.get('/habits').get_json() == []
```

Run: `../../activate/bin/python -m pytest tests/ -q`
Expected: `35 passed`.

- [ ] **Step 6: Verify the reserved-word handling is load-bearing**

Temporarily change `UpdateExpression='SET #name = :name'` to
`UpdateExpression='SET name = :name'` and drop the `ExpressionAttributeNames`
line, then run:

Run: `../../activate/bin/python -m pytest tests/test_habits.py -q`
Expected: `test_rename_habit_changes_the_name` fails with a 500, because moto
raises `ValidationException` on the reserved word. Restore the `#name` version
and confirm `35 passed` again. This step exists so nobody later "cleans up" the
alias.

- [ ] **Step 7: Commit**

```bash
git add services/habitsService/store.py services/habitsService/app.py \
        services/habitsService/tests/test_habits.py
git commit -m "feat(habits): rename a habit

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Completions — mark, unmark, and window filtering

**Files:**
- Modify: `services/habitsService/store.py`
- Modify: `services/habitsService/app.py`
- Test: `services/habitsService/tests/test_completions.py`

- [ ] **Step 1: Write the failing tests**

Create `services/habitsService/tests/test_completions.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def habit_id(client):
    return client.post('/habits', json={'name': 'floss'}).get_json()['id']


def _dates_for(client, habit_id, query=''):
    body = client.get(f'/habits{query}').get_json()
    return next(habit['dates'] for habit in body if habit['id'] == habit_id)


def test_mark_done_records_the_date(client, habit_id):
    response = client.put(f'/habits/{habit_id}/completions/2026-09-03')

    assert response.status_code == 200
    assert response.get_json() == {'id': habit_id, 'date': '2026-09-03'}
    assert _dates_for(
        client, habit_id, '?from=2026-09-01&to=2026-09-30'
    ) == ['2026-09-03']


def test_mark_done_twice_leaves_exactly_one_date(client, habit_id):
    first = client.put(f'/habits/{habit_id}/completions/2026-09-03')
    second = client.put(f'/habits/{habit_id}/completions/2026-09-03')

    assert first.status_code == 200
    assert second.status_code == 200
    assert _dates_for(
        client, habit_id, '?from=2026-09-01&to=2026-09-30'
    ) == ['2026-09-03']


def test_dates_come_back_sorted_ascending(client, habit_id):
    for day in ('2026-09-07', '2026-09-02', '2026-09-05'):
        client.put(f'/habits/{habit_id}/completions/{day}')

    assert _dates_for(client, habit_id, '?from=2026-09-01&to=2026-09-30') == [
        '2026-09-02',
        '2026-09-05',
        '2026-09-07',
    ]


def test_window_boundaries_are_inclusive(client, habit_id):
    for day in ('2026-09-01', '2026-09-15', '2026-09-30'):
        client.put(f'/habits/{habit_id}/completions/{day}')

    assert _dates_for(client, habit_id, '?from=2026-09-01&to=2026-09-30') == [
        '2026-09-01',
        '2026-09-15',
        '2026-09-30',
    ]


def test_dates_outside_the_window_are_excluded(client, habit_id):
    client.put(f'/habits/{habit_id}/completions/2026-08-31')
    client.put(f'/habits/{habit_id}/completions/2026-09-15')
    client.put(f'/habits/{habit_id}/completions/2026-10-01')

    assert _dates_for(
        client, habit_id, '?from=2026-09-01&to=2026-09-30'
    ) == ['2026-09-15']


def test_default_window_is_the_last_30_days(client, habit_id):
    today = datetime.now(timezone.utc).date()
    inside = today - timedelta(days=5)
    outside = today - timedelta(days=40)
    client.put(f'/habits/{habit_id}/completions/{inside.isoformat()}')
    client.put(f'/habits/{habit_id}/completions/{outside.isoformat()}')

    assert _dates_for(client, habit_id) == [inside.isoformat()]


def test_future_dates_are_allowed(client, habit_id):
    """Rejecting them would need a trusted server-side "today", which this
    design deliberately does not rely on."""
    future = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()

    response = client.put(f'/habits/{habit_id}/completions/{future}')

    assert response.status_code == 200
    assert _dates_for(client, habit_id, f'?from={future}&to={future}') == [future]


def test_mark_done_rejects_a_non_canonical_date(client, habit_id):
    response = client.put(f'/habits/{habit_id}/completions/20260903')

    assert response.status_code == 400
    assert _dates_for(client, habit_id, '?from=2026-09-01&to=2026-09-30') == []


def test_mark_done_on_unknown_habit_is_404_and_writes_nothing(client):
    response = client.put('/habits/not-a-real-id/completions/2026-09-03')

    assert response.status_code == 404
    # An orphan completion row would be invisible to the list endpoint, so
    # confirm the habit list is still genuinely empty.
    assert client.get('/habits').get_json() == []


def test_unmark_done_removes_the_date(client, habit_id):
    client.put(f'/habits/{habit_id}/completions/2026-09-03')

    response = client.delete(f'/habits/{habit_id}/completions/2026-09-03')

    assert response.status_code == 200
    assert _dates_for(client, habit_id, '?from=2026-09-01&to=2026-09-30') == []


def test_unmark_done_is_idempotent_when_never_marked(client, habit_id):
    response = client.delete(f'/habits/{habit_id}/completions/2026-09-03')

    assert response.status_code == 200


def test_unmark_done_on_unknown_habit_is_404(client):
    response = client.delete('/habits/not-a-real-id/completions/2026-09-03')

    assert response.status_code == 404


def test_unmark_done_rejects_a_non_canonical_date(client, habit_id):
    response = client.delete(f'/habits/{habit_id}/completions/20260903')

    assert response.status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../activate/bin/python -m pytest tests/test_completions.py -q`
Expected: `13 failed`. The completion URLs return `404` from Flask routing
because no route matches that path yet.

- [ ] **Step 3: Add the completion functions to `store.py`**

Append to `services/habitsService/store.py`:

```python
def habit_exists(habit_id: str) -> bool:
    response = dynamodb_client.get_item(
        TableName=LIVS_TABLE,
        Key={'PK': {'S': HABIT_PK}, 'SK': {'S': habit_id}},
        ProjectionExpression='SK',
    )
    return 'Item' in response


def mark_done(habit_id: str, completion_date: str) -> dict:
    """Record that `habit_id` was done on `completion_date`.

    The existence check keeps completions from being written under a habit id
    that does not exist: such rows are unreachable from the list endpoint and
    would never be cleaned up by delete_habit. This is a check-then-write race,
    accepted for a single-user tracker rather than reaching for
    TransactWriteItems.
    """
    if not habit_exists(habit_id):
        raise HabitNotFound(habit_id)

    dynamodb_client.put_item(
        TableName=LIVS_TABLE,
        Item={
            'PK': {'S': _completions_pk(habit_id)},
            'SK': {'S': completion_date},
        },
    )
    return {'id': habit_id, 'date': completion_date}


def unmark_done(habit_id: str, completion_date: str) -> None:
    if not habit_exists(habit_id):
        raise HabitNotFound(habit_id)

    # No ConditionExpression on purpose: unmarking a date that was never marked
    # is a no-op, because the end state the caller asked for already holds.
    dynamodb_client.delete_item(
        TableName=LIVS_TABLE,
        Key={
            'PK': {'S': _completions_pk(habit_id)},
            'SK': {'S': completion_date},
        },
    )
```

- [ ] **Step 4: Add the routes to `app.py`**

Insert into `services/habitsService/app.py`, after `rename_habit` and before the
`@app.errorhandler(404)` handler:

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `../../activate/bin/python -m pytest tests/ -q`
Expected: `50 passed`.

- [ ] **Step 6: Commit**

```bash
git add services/habitsService/store.py services/habitsService/app.py \
        services/habitsService/tests/test_completions.py
git commit -m "feat(habits): mark and unmark habit completions

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `DELETE /habits/<id>` — with cascade

**Files:**
- Modify: `services/habitsService/store.py`
- Modify: `services/habitsService/app.py`
- Test: `services/habitsService/tests/test_habits.py`

- [ ] **Step 1: Write the failing tests**

Append to `services/habitsService/tests/test_habits.py`:

```python
def test_delete_habit_removes_it(client):
    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']

    response = client.delete(f'/habits/{habit_id}')

    assert response.status_code == 200
    assert client.get('/habits').get_json() == []


def test_delete_habit_with_unknown_id_is_404(client):
    response = client.delete('/habits/not-a-real-id')

    assert response.status_code == 404


def test_delete_habit_leaves_no_completions_behind(client):
    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']
    for day in ('2026-09-01', '2026-09-02', '2026-09-03'):
        client.put(f'/habits/{habit_id}/completions/{day}')

    assert client.delete(f'/habits/{habit_id}').status_code == 200

    # Recreating a habit cannot resurrect the old dates, so prove the rows are
    # gone by reading the completion partition directly.
    import store

    assert store._completion_dates(habit_id, '2026-01-01', '2026-12-31') == []


def test_delete_habit_cascades_past_one_batch_write(client):
    """BatchWriteItem caps at 25 items, so a cascade must chunk correctly."""
    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']
    for day in range(1, 29):
        client.put(f'/habits/{habit_id}/completions/2026-09-{day:02d}')

    assert client.delete(f'/habits/{habit_id}').status_code == 200

    import store

    assert store._completion_dates(habit_id, '2026-01-01', '2026-12-31') == []


def test_deleting_one_habit_leaves_another_habits_dates_alone(client):
    keep = client.post('/habits', json={'name': 'floss'}).get_json()['id']
    drop = client.post('/habits', json={'name': 'run'}).get_json()['id']
    client.put(f'/habits/{keep}/completions/2026-09-03')
    client.put(f'/habits/{drop}/completions/2026-09-03')

    client.delete(f'/habits/{drop}')

    body = client.get('/habits?from=2026-09-01&to=2026-09-30').get_json()
    assert body == [{'id': keep, 'name': 'floss', 'dates': ['2026-09-03']}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `../../activate/bin/python -m pytest tests/test_habits.py -q`
Expected: `5 failed, 15 passed` — the deletes return `405 Method Not Allowed`,
since `/habits/<habit_id>` currently only registers `PUT`.

- [ ] **Step 3: Add the cascade to `store.py`**

Add `import time` to the imports, and these two constants directly below the
existing `HABIT_PK = 'HABIT'` line:

```python
BATCH_WRITE_LIMIT = 25
# Bounded because the shared table is provisioned capacity, so a cascade of any
# size can get throttled and hand back UnprocessedItems as a matter of course.
BATCH_WRITE_MAX_ATTEMPTS = 5
```

Then append to `services/habitsService/store.py`:

```python
def delete_habit(habit_id: str) -> None:
    """Delete a habit and every completion recorded against it.

    Completions go first, so an interrupted delete leaves a habit with fewer
    dates rather than an orphan partition no read path can reach. The
    HabitNotFound for an unknown id therefore surfaces from the final
    delete_item, after an empty cascade has already run -- one wasted query on
    a request that was going to fail anyway, in exchange for keeping the
    interruption-safe ordering.
    """
    completions = _query_all(
        TableName=LIVS_TABLE,
        KeyConditionExpression='PK = :pk',
        ExpressionAttributeValues={':pk': {'S': _completions_pk(habit_id)}},
        ProjectionExpression='SK',
    )
    _delete_completions(habit_id, [item['SK']['S'] for item in completions])

    try:
        dynamodb_client.delete_item(
            TableName=LIVS_TABLE,
            Key={'PK': {'S': HABIT_PK}, 'SK': {'S': habit_id}},
            ConditionExpression='attribute_exists(SK)',
        )
    except dynamodb_client.exceptions.ConditionalCheckFailedException as e:
        raise HabitNotFound(habit_id) from e


def _delete_completions(habit_id: str, completion_dates: list) -> None:
    """Batch-delete completion items, retrying whatever DynamoDB defers."""
    pk = _completions_pk(habit_id)

    for start in range(0, len(completion_dates), BATCH_WRITE_LIMIT):
        chunk = completion_dates[start : start + BATCH_WRITE_LIMIT]
        requests = [
            {'DeleteRequest': {'Key': {'PK': {'S': pk}, 'SK': {'S': day}}}}
            for day in chunk
        ]
        attempt = 0
        while requests:
            response = dynamodb_client.batch_write_item(
                RequestItems={LIVS_TABLE: requests}
            )
            # A partial batch is a normal response, not an error.
            requests = response.get('UnprocessedItems', {}).get(LIVS_TABLE, [])
            if not requests:
                break

            attempt += 1
            if attempt >= BATCH_WRITE_MAX_ATTEMPTS:
                raise RuntimeError(
                    f'{len(requests)} completions still unprocessed after '
                    f'{attempt} batch_write_item attempts'
                )
            time.sleep(0.05 * 2**attempt)
```

Raising is the right failure mode: completions are deleted *before* the habit
item, so a raise leaves the habit intact with fewer dates and the client can
retry to finish. The route maps it to a 500.

- [ ] **Step 4: Add the route to `app.py`**

Insert into `services/habitsService/app.py`, after `rename_habit` and before
`mark_done`:

```python
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
```

- [ ] **Step 5: Assert the chunking on call shape, because moto won't enforce it**

The obvious mutation check here does **not** work, and this was verified during
execution: setting `BATCH_WRITE_LIMIT = 100` so the cascade sends all 28 items in
one call leaves the suite green. moto 5.1.22 accepts an oversized
`batch_write_item` and returns `UnprocessedItems: {}` instead of the
`ValidationException` real DynamoDB raises. So
`test_delete_habit_cascades_past_one_batch_write` proves that 28 completions all
get deleted, but proves *nothing* about chunk size — it would pass with no
chunking loop at all.

When the backend won't enforce a constraint, assert on the call arguments
instead. Add these two tests to `tests/test_habits.py`:

```python
def test_cascade_never_sends_more_than_25_items_per_batch(client):
    """moto accepts oversized batches, so only the call args can prove chunking.

    Real BatchWriteItem caps at 25 and would raise ValidationException.
    """
    import store

    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']
    for day in range(1, 29):
        client.put(f'/habits/{habit_id}/completions/2026-09-{day:02d}')

    batch_sizes = []
    real_batch_write = store.dynamodb_client.batch_write_item

    def recording_batch_write(**kwargs):
        batch_sizes.append(len(kwargs['RequestItems'][store.LIVS_TABLE]))
        return real_batch_write(**kwargs)

    store.dynamodb_client.batch_write_item = recording_batch_write
    try:
        assert client.delete(f'/habits/{habit_id}').status_code == 200
    finally:
        store.dynamodb_client.batch_write_item = real_batch_write

    assert batch_sizes == [25, 3]
    assert max(batch_sizes) <= store.BATCH_WRITE_LIMIT


def test_cascade_gives_up_instead_of_retrying_forever(client):
    """A backend that never drains UnprocessedItems must not busy-loop."""
    import store

    habit_id = client.post('/habits', json={'name': 'floss'}).get_json()['id']
    client.put(f'/habits/{habit_id}/completions/2026-09-03')

    stuck = {
        'UnprocessedItems': {
            store.LIVS_TABLE: [
                {'DeleteRequest': {'Key': {'PK': {'S': 'x'}, 'SK': {'S': 'y'}}}}
            ]
        }
    }
    calls = []
    real_batch_write = store.dynamodb_client.batch_write_item

    def never_drains(**kwargs):
        calls.append(kwargs)
        return stuck

    store.dynamodb_client.batch_write_item = never_drains
    try:
        response = client.delete(f'/habits/{habit_id}')
    finally:
        store.dynamodb_client.batch_write_item = real_batch_write

    assert response.status_code == 500
    assert len(calls) == store.BATCH_WRITE_MAX_ATTEMPTS
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `../../activate/bin/python -m pytest tests/ -q`
Expected: `57 passed` (20 dates, 22 habits, 15 completions).

- [ ] **Step 7: Commit**

```bash
git add services/habitsService/store.py services/habitsService/app.py \
        services/habitsService/tests/test_habits.py
git commit -m "feat(habits): delete a habit and cascade its completions

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Wire up `serverless.yml`

**Files:**
- Rewrite: `services/habitsService/serverless.yml`
- Modify: `services/habitsService/package.json`

- [ ] **Step 1: Replace `serverless.yml`**

The current file is the template: it declares its own `UsersTable` with a
`userId` key and exports `USERS_TABLE`. Replace the entire contents with:

```yaml
# "org" ensures this Service is used with the correct Serverless Framework Access Key.
org: ggarb
# "service" is the name of this project. This will also be added to your AWS resource names.
service: habitsService

plugins:
  - serverless-wsgi

custom:
  wsgi:
    app: app.app
    # serverless-wsgi decides whether to pip-install requirements itself by
    # checking for "serverless-python-requirements" in the plugins list; with
    # that plugin removed this must be pinned false so wsgi defers to the
    # built-in python requirements packaging (activated by custom.pythonRequirements below).
    packRequirements: false
  # Built-in python requirements packaging activates on this key.
  pythonRequirements: {}

provider:
  name: aws
  runtime: python3.14
  architecture: arm64
  iam:
    role:
      statements:
        - Effect: Allow
          Action:
            - dynamodb:Query
            - dynamodb:GetItem
            - dynamodb:PutItem
            - dynamodb:UpdateItem
            - dynamodb:DeleteItem
            # Required by the cascade in delete_habit.
            - dynamodb:BatchWriteItem
          Resource:
            - ${cf:infraService-${sls:stage}.LivsTableArn}
  environment:
    LIVS_TABLE: ${cf:infraService-${sls:stage}.LivsTableName}

functions:
  # One Lambda for the whole service: serverless-wsgi's generated shim adapts the
  # API Gateway proxy event to WSGI and Flask's own routing takes it from there.
  api:
    handler: wsgi_handler.handler
    # Explicit, because the Serverless Framework default is 6s and a cascade
    # delete of a long-running habit can spend several seconds in bounded
    # BatchWriteItem retries. 29s is the ceiling API Gateway allows for a REST
    # `http` integration, so there is no point going higher.
    timeout: 29
    events:
      - http:
          path: /
          method: ANY
      - http:
          path: /{proxy+}
          method: ANY
```

There is no `resources` block: the table belongs to `infraService`.

The `timeout: 29` was added during execution, not in the original plan. Task 6's
quality review computed that a habit with ~100+ completions hitting the
worst-case retry pattern on every chunk would exceed the framework's 6s default
while still inside `_delete_completions`. Both numbers were verified against the
docs: 6s is the Serverless Framework default (AWS's own native default is 3s),
and 29s is the effective ceiling for a REST `http` integration. `todoService`
deliberately keeps the default — it has no cascade path that sleeps.

- [ ] **Step 2: Fix the package.json description**

In `services/habitsService/package.json`, change the `description` field from
`"Example of a Python Flask API service backed by DynamoDB with traditional Serverless Framework"`
to `"Habit tracker API for livs_website"`. Leave `name`, `version`, `author` and
`devDependencies` alone.

- [ ] **Step 3: Verify the YAML parses**

```bash
../../activate/bin/python -c "import yaml; yaml.safe_load(open('serverless.yml')); print('valid YAML')"
```
Expected: `valid YAML`

- [ ] **Step 4: Confirm the tests still pass**

Config changes should not touch behaviour, but the env var name is shared with
`store.py`, so re-run:

Run: `../../activate/bin/python -m pytest tests/ -q`
Expected: `57 passed`.

- [ ] **Step 5: Commit**

```bash
git add services/habitsService/serverless.yml services/habitsService/package.json
git commit -m "feat(habits): point service at the shared infra table

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: README

**Files:**
- Rewrite: `services/habitsService/README.md`

- [ ] **Step 1: Replace the README**

The current file is the upstream Serverless template readme and documents a
users API that no longer exists. Replace the entire contents with:

```markdown
# habitsService

A Flask API for the habit tracker, running on Lambda behind API Gateway and
stored in the shared DynamoDB table owned by [`infraService`](../infraService).

A habit has a name. For each habit you record the dates you did it — one date is
either recorded or it isn't, so a habit's history is a set of dates.

## Storage

| Item       | PK                | SK             | Attributes |
| ---------- | ----------------- | -------------- | ---------- |
| Habit      | `HABIT`           | `<uuid>`       | `name`     |
| Completion | `HABIT#<habitId>` | `2026-09-03`   | –          |

A completion has no attributes; the item existing *is* the record. That makes
marking a habit done idempotent without a read-modify-write.

## Endpoints

| Method   | Path                              | Body / query  | Response |
| -------- | --------------------------------- | ------------- | -------- |
| `GET`    | `/habits`                         | `?from=&to=`  | `200 [{"id", "name", "dates": [...]}]` |
| `POST`   | `/habits`                         | `{"name"}`    | `201 {"id", "name"}` |
| `PUT`    | `/habits/<id>`                    | `{"name"}`    | `200 {"id", "name"}` |
| `DELETE` | `/habits/<id>`                    | –             | `200 {"message"}` |
| `PUT`    | `/habits/<id>/completions/<date>` | –             | `200 {"id", "date"}` |
| `DELETE` | `/habits/<id>/completions/<date>` | –             | `200 {"message"}` |

Marking a habit done uses `PUT`, not `POST`, because one-per-day means putting a
named resource at a known path.

Dates must be canonical `YYYY-MM-DD`. `20260903` is rejected rather than
normalised, because a non-canonical sort key would break the range read.

`from` and `to` are inclusive and both optional; the default is the last 30 days
ending today (UTC). The client supplies completion dates itself so that an
evening habit is not logged to tomorrow, and so you can backfill a day you forgot.

Deleting a habit also deletes its completions. Unmarking a date that was never
marked returns `200`, since the requested end state already holds; a missing
*habit* is a `404`.

## Deploy

`infraService` must be deployed first — this service resolves the table name and
ARN from that stack's CloudFormation outputs.

```
npm install
serverless deploy
```

`provider.runtime` is `python3.14`, so the built-in Python requirements packaging
needs a local `python3.14`; otherwise set `dockerizePip: true` under
`custom.pythonRequirements`.

## Tests

```
python -m venv ./venv && source ./venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest tests/
```

The tests run the real Flask app against a `moto`-mocked DynamoDB, so they need
no AWS credentials and touch nothing real.

## Local development

Run DynamoDB locally with the [`serverless-dynamodb`](https://github.com/raisenational/serverless-dynamodb)
plugin, then `serverless wsgi serve`. `store.py` redirects the boto3 client to
`http://localhost:8000` when `IS_OFFLINE` is set.
```

- [ ] **Step 2: Final full test run**

Run: `../../activate/bin/python -m pytest tests/ -q`
Expected: `57 passed`.

- [ ] **Step 3: Commit**

```bash
git add services/habitsService/README.md
git commit -m "docs(habits): document the habit tracker API

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Definition of done

- [ ] `../../activate/bin/python -m pytest tests/ -q` reports `57 passed` from `services/habitsService`
- [ ] `services/habitsService/serverless.yml` has no `resources` block and no `USERS_TABLE`
- [ ] `grep -r "userId" services/habitsService` returns nothing
- [ ] `grep -n "UpdateExpression='SET #name" services/habitsService/store.py` returns a hit (the reserved-word alias is intact). Assert the positive: a `grep` for the *absence* of `SET name` fails on the cautionary comment that explains why the alias exists.
- [ ] The README documents six endpoints, not the template's users API

Deploying is out of scope for this plan and needs AWS credentials this
environment does not have. `serverless deploy` on `infraService` then
`habitsService` is a separate, manual step.
