# infraService

Shared infrastructure for the livs_website services. Right now that is just the
single DynamoDB table (`livs-table-<stage>`) that every app service uses.

The table lives in its own stack so that removing or redeploying an app service
can never delete the data, and so no two app stacks try to create the same table.

## Table layout

Single-table design, keyed on `PK` (hash) + `SK` (range):

| PK       | SK       | other attributes |
| -------- | -------- | ---------------- |
| `TODO`   | `<uuid>` | `todo`           |

Each app service claims its own `PK` value (`TODO`, `HABIT`, `RECIPE`, ...) and
lists its items with a single `Query` on that partition.

## Deploy

```
serverless deploy
```

This must run before any app service, which reference the outputs as
`${cf:infraService-<stage>.LivsTableName}` and `.LivsTableArn`.
