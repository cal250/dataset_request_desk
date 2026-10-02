# Dataset Request Desk

Internal platform for a robotics data-collection company. Clients submit dataset
requests ("200 episodes of pick cup by December"); operators fulfil them by
assigning imported robot episodes; clients accept or reject the delivery.

Python + FastAPI + PostgreSQL + HTMX/Jinja. One Compose stack serves the UI,
the JSON API, and the database. No stretch item was taken: the full budget went
into the required scope, tested.

## Step 0 — Start the system (from a clean clone)

```bash
docker compose up --build
```

Open http://localhost:8000 (redirects to `/login`). Migrations, seed users, and
the web server start automatically via `docker/entrypoint.sh`. No `.env` file
is needed; every setting has a local default (see `.env.example`). Never commit
`.env`.

## Step 1 — Log in (pick your role)

Seeded demo accounts (passwords are Argon2 hashes in the DB):

| Email | Password | Role | You will… |
|---|---|---|---|
| `client-a@example.com` | `client123` | client | create + review own requests |
| `client-b@example.com` | `client123` | client | same, separate data |
| `ops1@example.com` | `ops123` | operator | fulfil all requests, import, analytics |
| `ops2@example.com` | `ops123` | operator | same |
| `admin@example.com` | `admin123` | admin | operator powers + *Users* |

## Step 2 — Client walkthrough (log in as `client-a`)

1. You land on **My requests** (empty at first).
2. Click **Create request** → fill task name, episode count, deadline →
   **Create request**. Status is `submitted`.
3. Open the request: watch **Progress** (`assigned / requested`) and
   **History** as the operator works.
4. When status becomes `delivered`, choose **Accept delivery** or
   **Request rework** (rework sends it back to `in_progress`).

## Step 3 — Operator walkthrough (log in as `ops1`)

1. **Requests** shows every client's requests with progress and status.
2. Open one → **Start work** (`submitted → in_progress`).
3. In **Assign eligible episodes**, filter by task/quality → **Assign** each
   episode (only `good`/`usable`, one episode per request; `bad` is refused).
4. When progress reads `requested / requested`, **Mark delivered** (the button
   stays disabled before that; the server enforces it too).
5. **Episodes** page: search the pool (`task_name` + `quality`, paginated), or
   import a new export — see Step 5.
6. **Analytics** page: pick a date range → episodes per day/robot, requests by
   status, median fulfilment time, top tasks.

## Step 4 — Admin walkthrough (log in as `admin`)

1. Everything in Step 3, plus the **Users** page.
2. **Create user**: email + name + role + password (≥8 chars).
3. **Set role** per row; **Deactivate** removes access immediately (even
   mid-session). You cannot deactivate yourself.

## Step 5 — Import episode metadata (operator/admin)

Browser: **Episodes → Import episodes from CSV** → choose file → read the
result panel (inserted / already up to date / invalid / conflicts + per-row
reasons). Or CLI:

```bash
docker compose run --rm api python -m app.cli.import_episodes /app/seed/episodes.csv
```

Safe to rerun: canonical `episode_id` (trimmed, uppercased) is unique, so a
second run inserts 0. On the supplied file: **171 inserted, 15 invalid, 2
conflicts, 2 in-file duplicates**. Rejected: unknown robots/qualities,
ambiguous dates (`14/08/2026`), bad durations (`N/A`, `45.5`, `-5`, `999999`),
blank fields. Normalized, never guessed: `USABLE → usable`,
`  Pick Cup  → pick cup`.

## Step 6 — Run the checks (same environment, one command each)

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
and pull requests. Interactive API docs: http://localhost:8000/docs (log in
first; the session cookie is reused).

## Step 7 — Configure for real use

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://desk:desk-local-password@db:5432/dataset_request_desk` | App database |
| `SESSION_SECRET` | dev-only placeholder | Signs session cookies (replace in production) |
| `SESSION_HTTPS_ONLY` | `false` | Set `true` behind HTTPS so cookies are `Secure` |
| `LOG_LEVEL` | `INFO` | Structured per-request JSON logs |

At 5M episodes the day/robot and top-task scans are the pressure point: keep
the `(recorded_at, robot_id)` and `(quality, task_name)` access paths indexed,
check `EXPLAIN ANALYZE`, then add a daily rollup/materialized view before any
new infrastructure. Measured numbers are in `NOTES.md` §5.

## Troubleshooting (in the order you'll hit it)

1. `entrypoint.sh: permission denied` (Linux/CI): fixed via the executable bit
   in git; if it recurs, `git update-index --chmod=+x docker/entrypoint.sh`.
2. `connection refused` on `:8000`: wait for `db` healthy
   (`docker compose ps`), then `docker compose logs api`.
3. Empty app after `down -v`: that wipes both database volumes by design —
   re-run Step 0 and re-import (Step 5). Tests are unaffected (separate test
   database).
4. `422` on episode search: `quality` accepts only `good|usable|bad` or empty
   (Any).
5. `403 Forbidden` on a button you can see: you shouldn't see it — note the
   page, role, and status and file it as a UI bug (server rules are listed in
   Step 2–4).
