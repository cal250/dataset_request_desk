# Dataset Request Desk

Internal platform for a robotics data-collection company. Clients submit dataset
requests ("200 episodes of pick cup by December"); operators fulfil them by
assigning imported robot episodes; clients accept or reject the delivery.

Python + FastAPI + PostgreSQL + HTMX/Jinja. One Compose stack serves the UI,
the JSON API, and the database. No stretch item was taken: the full budget went
into the required scope, tested.

## Quick start (from a clean clone)

```bash
docker compose up --build
```

Open http://localhost:8000 (redirects to `/login`). Migrations, seed users, and
the web server start automatically via `docker/entrypoint.sh`.

## Demo accounts (seeded, password hashed with Argon2 in the DB)

| Email | Password | Role |
|---|---|---|
| `admin@example.com` | `admin123` | admin |
| `ops1@example.com` | `ops123` | operator |
| `ops2@example.com` | `ops123` | operator |
| `client-a@example.com` | `client123` | client |
| `client-b@example.com` | `client123` | client |

## What each role does

- **Client:** lands on *My requests*, creates requests, watches progress
  (`assigned / requested`), accepts or rejects a delivered request.
- **Operator:** sees all requests, moves `submitted → in_progress → delivered`,
  filters the episode pool by task/quality, assigns episodes, imports CSVs,
  views analytics.
- **Admin:** all operator powers plus *Users* (create, change role, deactivate).

Interactive API docs: http://localhost:8000/docs (same auth: log in first, the
session cookie is reused).

## Tests and lint (one command each, same environment)

```bash
docker compose run --rm api python -m pytest -q
docker compose run --rm api python -m ruff check app tests
```

Tests use an isolated `*_test` database with per-test savepoint rollback, plus
per-role fixtures. They cover: login/sessions/role guards, client ownership,
every valid and invalid status transition, the delivery threshold, `bad`
rejection, double-assignment conflicts, import normalization/reporting/double
imports, analytics aggregates, admin rules, and page rendering. CI
(`.github/workflows/ci.yml`) runs build + lint + tests on pushes to `main`
and pull requests.

## Episode import

```bash
docker compose run --rm api python -m app.cli.import_episodes /app/seed/episodes.csv
# or: upload a CSV in Episodes → Import episodes from CSV (operator only)
```

Safe to rerun: canonical `episode_id` (trimmed, uppercased) is unique, so a
second run inserts 0. Every skipped row is reported with its row number and
reason. On the supplied file: **171 inserted, 15 invalid, 2 conflicts, 2
in-file duplicates**. Rejected: unknown robots/qualities, ambiguous dates
(`14/08/2026`), bad durations (`N/A`, `45.5`, `-5`, `999999`), blank fields.
Normalized, never guessed: `USABLE → usable`, `  Pick Cup  → pick cup`.

## Analytics

`GET /analytics?start=YYYY-MM-DD&end=YYYY-MM-DD` (operator/admin, ≤366 days):
episodes per day per robot, request counts by status, median
submitted→delivered seconds (`percentile_cont`), top-5 tasks by good episodes.
All aggregated in PostgreSQL. The *Analytics* page shows the same tables.

At 5M episodes the day/robot and top-task scans are the pressure point: keep
the `(recorded_at, robot_id)` and `(quality, task_name)` access paths indexed,
check `EXPLAIN ANALYZE`, then add a daily rollup/materialized view before any
new infrastructure.

## Configuration

All settings are environment variables with local defaults (see
`.env.example`); no `.env` file is needed to run. Never commit `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://desk:desk-local-password@db:5432/dataset_request_desk` | App database |
| `SESSION_SECRET` | dev-only placeholder | Signs session cookies (replace in production) |
| `SESSION_HTTPS_ONLY` | `false` | Set `true` behind HTTPS so cookies are `Secure` |
| `LOG_LEVEL` | `INFO` | Structured per-request JSON logs |

## Troubleshooting

- `docker compose up --build` fails on `entrypoint.sh: permission denied`
  (Linux/CI): fixed via the executable bit in git; if it recurs,
  `git update-index --chmod=+x docker/entrypoint.sh`.
- `connection refused` on `:8000`: wait for `db` healthy, then check
  `docker compose logs api`.
- Test/dev database mixups: tests always use the `*_test` database; the dev
  database keeps demo/imported data. `docker compose down -v` wipes both
  volumes (dev data must be re-imported afterwards).
- `422` on episode search with `quality=`: only `good|usable|bad` or empty
  (Any) are accepted.
