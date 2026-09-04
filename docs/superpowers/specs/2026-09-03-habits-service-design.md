# habitsService design

Date: 2026-09-03

## Purpose

A simple habit tracker API. A habit has a name and can be created, renamed, and
deleted. For each habit the user records the dates on which they did it — a habit
is either done on a given day or it isn't, so a habit's history is just a set of
dates.

## Scope

In scope: the five CRUD operations on habits and completions listed under
[API](#api), backed by the shared DynamoDB table.

Explicitly out of scope, decided during design:

- Counts or timestamps per day. A completion is one date, idempotent.
- Habit attributes beyond `name` — no color, archive flag, or target/goal.
- Streak or "3 of 5 this week" calculation. The API returns dates; any rollup is
  the frontend's job.
- Multi-user partitioning. Habits live under a single `HABIT` partition, matching
  the single-user assumption already made in todoService.

## Architecture

Identical in shape to `services/todoService`, so the repo has one pattern rather
than two:

- Flask app in `app.py`, packaged by `serverless-wsgi`.
- One Lambda, `api`, handling `ANY /` and `ANY /{proxy+}`; Flask routes internally.
- Table name and ARN resolve from the infraService stack outputs
  (`${cf:infraService-${sls:stage}.LivsTableName}` and `.LivsTableArn`), so
  infraService must be deployed first.

The boto3 client setup and the query paginator are duplicated from todoService
rather than extracted into a shared module. Sharing Python between serverless
services requires a Lambda layer or a build-time copy, which is disproportionate
machinery for ~10 lines. If a third service needs the same code, that is the
point to extract a layer.

## Data model

Two item types in the shared table, both owned by this service:

| Item       | PK                | SK             | Attributes |
| ---------- | ----------------- | -------------- | ---------- |
| Habit      | `HABIT`           | `<uuid4>`      | `name` (S) |
| Completion | `HABIT#<habitId>` | `2026-09-03`   | –          |

Listing habits is one `Query` on `PK='HABIT'`. A habit's completions in a window
is one `Query` on `PK='HABIT#<id>'` with `SK BETWEEN :from AND :to`, so DynamoDB
reads only the requested range instead of the full history.

A completion carries no attributes; the existence of the item is the fact being
recorded. Marking a habit done is a `PutItem` on that key, which makes repeat
marks idempotent with no read-modify-write.

### Date canonicalisation

Dates are parsed with `datetime.date.fromisoformat()` and then **re-emitted with
`.isoformat()`** before being used as an `SK`.

This is required for correctness, not cosmetic. Python 3.11+ `fromisoformat()`
accepts non-canonical forms such as `20260903`. If such a string reached the `SK`,
the lexical ordering that `BETWEEN` depends on would break silently — `20260903`
does not sort among `2026-09-01`-style keys. Canonicalising on the way in
guarantees every `SK` is zero-padded `YYYY-MM-DD`.

## API

| Method   | Path                              | Body / query   | Success | Errors      |
| -------- | --------------------------------- | -------------- | ------- | ----------- |
| `GET`    | `/habits`                         | `?from=&to=`   | `200 [{id, name, dates: [...]}]` | `400` |
| `POST`   | `/habits`                         | `{"name"}`     | `201 {id, name}`                 | `400` |
| `PUT`    | `/habits/<id>`                    | `{"name"}`     | `200 {id, name}`                 | `400`, `404` |
| `DELETE` | `/habits/<id>`                    | –              | `200 {message}`                  | `404` |
| `PUT`    | `/habits/<id>/completions/<date>` | –              | `200 {id, date}`                 | `400`, `404` |
| `DELETE` | `/habits/<id>/completions/<date>` | –              | `200 {message}`                  | `400`, `404` |

Marking a completion uses `PUT`, not `POST`, because one-per-day idempotency maps
exactly onto putting a named resource at a known path.

`dates` in a `GET /habits` response is sorted ascending and contains only dates
within the requested window. A habit with no completions in that window is still
listed, with `dates: []`.

`POST` and `PUT` return `{id, name}` rather than including `dates`, matching
todoService's create/update responses. A newly created habit has no completions,
and on rename the client already knows the dates it is displaying — including
them would cost an extra query per write for no new information.

Habit names are stripped of surrounding whitespace and must be non-empty
afterwards. Names are not unique: the `id` is the identity, so two habits may
share a name.

### Default window

Both `from` and `to` are optional. `to` defaults to today in UTC; `from` defaults
to `to − 29 days`, giving a 30-day window inclusive of both ends.

This uses a server-side UTC "today", which the design otherwise avoids. It is
acceptable here because the consequence is bounded: a window boundary being a few
hours out shows the user the same grid. Mis-dating a *completion* was the real
failure mode, and the client still supplies that date explicitly. A client that
needs an exact window sends both parameters.

### Idempotency of unmarking

`DELETE /habits/<id>/completions/<date>` returns `200` whether or not that date
was marked, because for a toggle UI the desired end state is what matters. A
missing *habit* is still `404`.

This deliberately differs from todoService, where `DELETE` of an unknown todo
returns `404`. The justification: a todo id is opaque and a `404` signals a real
client bug, whereas a completion key is `(habit, date)` — constructed by the
client from data it already has — and "not marked" is the requested end state.

### Orphan prevention

`PUT /habits/<id>/completions/<date>` does a `GetItem` on the habit first and
returns `404` if it is absent. Without this check, completion rows can be written
under a habit id that does not exist; they would be invisible to every read path
(which starts from the habit list) and never cleaned up by the cascade delete.

This is a check-then-write race: a habit deleted between the `GetItem` and the
`PutItem` leaves one orphan row. For a single-user tracker this is accepted rather
than reaching for `TransactWriteItems`.

### Validation

`400` is returned for:

- `POST`/`PUT /habits` with a missing or empty `name`
- a non-JSON request body where a body is required
- a `date`, `from`, or `to` that is not a valid ISO date
- `from > to`

Future dates are allowed. Rejecting them would require a trusted server-side
"today", which is exactly what this design decided not to rely on.

## Cascade delete

`DELETE /habits/<id>` removes the habit item and every completion under
`PK='HABIT#<id>'`:

1. Query the completion partition, projecting `SK` only.
2. `BatchWriteItem` delete requests in chunks of 25 (the API limit), retrying
   `UnprocessedItems` — a partial batch is a normal response, not an error.
3. Delete the habit item itself, with `ConditionExpression='attribute_exists(SK)'`
   so an unknown id yields `404`.

Completions are removed before the habit item, so an interrupted delete leaves a
habit with fewer dates rather than an unreachable orphan partition.

The `404` for an unknown id therefore surfaces from step 3, after steps 1–2 have
already run. That costs one wasted query on a request that was going to fail
anyway, which is the right trade for keeping the interruption-safe ordering — an
existence check up front would either duplicate the read or reintroduce the
orphan window.

## Pagination

Both the habit list query and the completion queries page on `LastEvaluatedKey`
through one shared helper. A single `Query` returns at most 1MB; a habit with
several years of history plus a growing habit list will exceed that, and silently
truncating would drop dates from the middle of a range.

## IAM

The service role needs, scoped to the shared table ARN:

`dynamodb:Query`, `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:UpdateItem`,
`dynamodb:DeleteItem`, `dynamodb:BatchWriteItem`.

`BatchWriteItem` is new relative to todoService and is required by the cascade
delete. No `Scan` — nothing scans.

## File layout

```
services/habitsService/
  serverless.yml        rewritten: single api function, cf refs to infraService
  app.py                rewritten from the template's users CRUD
  requirements.txt      Flask + boto3
  requirements-dev.txt  stubs, moto, pytest
  package.json          description fixed (still says "Example of a ...")
  README.md             rewritten from the template
  tests/conftest.py     moto-backed table fixture, mirrors todoService
  tests/test_app.py
```

`requirements.txt` currently lists only `Flask`. `boto3` is present in the Lambda
runtime by default, so the template happened to work, but relying on the
runtime-provided version invites version drift; it gets pinned explicitly as in
todoService.

## Testing

`moto`-backed tests against the real Flask app via `app.test_client()`, using the
same conftest pattern as todoService: a fixture creates a fresh empty `PK`/`SK`
table inside `mock_aws()` and reloads `app` so its module-level client is built
inside the mock. No AWS credentials, nothing real touched.

Happy path plus at least one failure case per endpoint, and specifically:

- marking the same date twice leaves exactly one completion and returns `200` both times
- `from` and `to` are inclusive at both boundaries
- a date outside the window is excluded from `dates`
- omitting `from`/`to` returns the last 30 days
- deleting a habit leaves no completion rows behind
- marking a completion on an unknown habit returns `404` and writes nothing
- `20260903` is rejected with `400` rather than stored as an `SK`
- `from > to` returns `400`
- unmarking a date that was never marked returns `200`
- unmarking under an unknown habit returns `404`

## Deployment order

1. `infraService` — owns the table.
2. `habitsService` — resolves the table from infraService's outputs.

`sls deploy` on habitsService fails with an unresolvable `${cf:...}` variable if
infraService has not been deployed to the same stage.
