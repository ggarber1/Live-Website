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

Habit names are stripped of surrounding whitespace and may not be blank. They are
not unique — the `id` is the identity, so two habits may share a name.

Deleting a habit also deletes its completions. Unmarking a date that was never
marked returns `200`, since the requested end state already holds; a missing
*habit* is a `404`.

## Deploy

`infraService` must be deployed first — this service resolves the table name and
ARN from that stack's CloudFormation outputs, so `sls deploy` here fails with an
unresolvable `${cf:...}` variable until that stack exists.

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

Three of them assert on call arguments rather than observable results, because
moto cannot reproduce the behaviour they guard: that `habit_exists` asks for a
strongly consistent read, that the cascade delete chunks at 25 items, and that
`_query_all` follows its pagination token. Each would pass against a broken
implementation if written as a normal behavioural test.

## Layout

| File | Responsibility |
| ---- | -------------- |
| `dates.py` | Date rules. Pure — no AWS, no Flask. |
| `store.py` | Every DynamoDB call, and the PK/SK layout. |
| `app.py` | Flask routes: parse, delegate, map failures to status codes. |

## Local development

Run DynamoDB locally with the [`serverless-dynamodb`](https://github.com/raisenational/serverless-dynamodb)
plugin, then `serverless wsgi serve`. `store.py` redirects the boto3 client to
`http://localhost:8000` when `IS_OFFLINE` is set.
