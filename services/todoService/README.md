# todoService

A Flask API for the todo list, running on Lambda behind API Gateway and stored in
the shared DynamoDB table owned by [`infraService`](../infraService).

`serverless-wsgi` packages the whole Flask app behind a single Lambda (`api`),
which catches `ANY /` and `ANY /{proxy+}`; Flask does the routing from there.

## Storage

Items live in the shared table under the `TODO` partition:

| PK     | SK       | todo               |
| ------ | -------- | ------------------ |
| `TODO` | `<uuid>` | `"water plants"`   |

The `SK` is the `id` the API returns and that `PUT`/`DELETE` expect.

## Endpoints

| Method   | Path    | Body                       | Response                      |
| -------- | ------- | -------------------------- | ----------------------------- |
| `GET`    | `/todo` | –                          | `200` `[{"id", "todo"}, ...]` |
| `POST`   | `/todo` | `{"todo": "..."}`          | `201` `{"id", "todo"}`        |
| `PUT`    | `/todo` | `{"id": "...", "todo": ""}`| `200` `{"id", "todo"}`        |
| `DELETE` | `/todo` | `{"id": "..."}`            | `200` `{"message"}`           |

`PUT` and `DELETE` return `404` for an unknown `id`, and all four return `400`
when required fields are missing.

## Deploy

`infraService` must be deployed first — this service resolves the table name and
ARN from that stack's CloudFormation outputs.

```
npm install
serverless deploy
```

Note that `provider.runtime` is `python3.14`, so the built-in Python requirements
packaging needs a local `python3.14`; otherwise set `dockerizePip: true` under
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
plugin, then `serverless wsgi serve`. `app.py` already redirects the boto3 client
to `http://localhost:8000` when `IS_OFFLINE` is set.
