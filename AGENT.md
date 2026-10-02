# Agent Guide — Dataset Request Desk

Internal robotics dataset platform. Python + FastAPI + PostgreSQL + HTMX/Jinja. All runtime/test work happens in Docker Compose. Do not require host Postgres/Python.

## Commands (in `docker compose run --rm api ...`)

- Start: `docker compose up --build`
- Tests: `docker compose run --rm api python -m pytest -q`
- Single test: `docker compose run --rm api python -m pytest tests/test_health.py -q`
- Lint: `docker compose run --rm api python -m ruff check app tests`
- Migrate: `alembic upgrade head` (via entrypoint; new schema change = new Alembic revision)
- Seed users: `python -m app.cli.seed_users`
- Import: `python -m app.cli.import_episodes /app/seed/episodes.csv`

## Structure

- `app/main.py` — app factory, middleware, route registration (thin)
- `app/config.py` — env-only settings (`DATABASE_URL`, `SESSION_SECRET`, `SESSION_HTTPS_ONLY`, `LOG_LEVEL`)
- `app/db.py` — engine/`SessionLocal`/`get_db_session`, `Base`
- `app/models/` — SQLAlchemy entities + DB constraints (users, requests, episodes, assignments, status_history)
- `app/schemas/` — Pydantic/form validation
- `app/routes/` — thin HTTP/HTML handlers, no business rules
- `app/services/` — domain rules: auth, transitions, assignments, import, analytics
- `app/templates/`, `app/static/` — Jinja + HTMX partials, small custom CSS per `DESIGN.md`
- `app/cli/` — seed/import commands
- `tests/conftest.py` — isolated `_test` DB, rollback, `client/client_user/operator_user/admin_user` fixtures. Never touch dev DB.
- `alembic/versions/` — one revision per schema change, idempotent upgrade/downgrade
- `seed/` — messy `episodes.csv`, `users.json` (plaintext in, Argon2 hash in DB)

## Governance — follow PLAN, ARCHITECTURE, DESIGN on every feature

Before implementing any feature, fix, or refactor, you MUST:

1. Read the relevant sections of `PLAN.md` (build sequence, domain/CSV rules, commit strategy), `ARCHITECTURE.md` (container topology, layers, transactions, import/analytics path), and `DESIGN.md` (layout, tokens, components, HTMX contract).
2. Implement in PLAN order (foundation → auth/domain → import/analytics → HTMX → quality/delivery); do not skip ahead to stretch items.
3. Keep the ARCHITECTURE layering: route → authZ → validation → service → SQLAlchemy → Postgres → HTML/JSON. Put business rules only in services + DB constraints.
4. Match DESIGN tokens/components (teal/slate, 4px spacing, status badges with text not color alone, sidebar shell, table-first workspaces, `hx-indicator` partial swaps).
5. If a doc conflicts with a shortcut, the doc wins. If the doc is wrong/ambiguous, implement the smallest reasonable choice and note it for `NOTES.md`.

## Rules

1. Server-enforced authZ: every route except login requires auth; check `is_active`, role, ownership in dependency/service, not templates. Roles: `client` (own requests only, accept/reject delivered), `operator` (all requests, transitions, assign, import), `admin` (operator + users).
2. Status machine only: `submitted→in_progress→delivered→accepted|rejected→in_progress`. Validate role + pair + delivery threshold (`assigned >= requested`) + write `status_history` in same transaction. Else `409/422`.
3. Assignments: only `good|usable`, one episode → one request (`unique` constraint is the race guard, map `IntegrityError` → conflict).
4. Import: deterministic, idempotent on canonical `episode_id` (trim+uppercase). Normalize formatting only (`USABLE→usable`, whitespace/case); reject semantic guesses (`excellent`, `arm-99`, ambiguous dates, `N/A`, negative/absurd durations). Return `inserted/already_exists/skipped_invalid/skipped_conflict` + row errors.
5. Analytics in SQL, not Python loops. Bounded date range. Explain 5M-row plan via indexes/`EXPLAIN ANALYZE`.
6. Layers: route → authZ → Pydantic/form validation → service → SQLAlchemy → Postgres → HTML partial/JSON. No SQL/policy in routes, no auth in templates.
7. Logging: JSON line per request (`method,path,status,duration_ms,user_id`); never log passwords/cookies/headers. `GET /health` checks DB.
8. Tests per feature in same change: success + failure + authZ + invalid input. Target: transitions, ownership, assignment guards, import idempotency/reporting.
9. Env: never commit `.env` (see `.env.example`); Compose `:-defaults` let clean clone run without it.
10. Style: `ruff` line-length 100, py312, names from domain (`request/episode/assignment`), comments explain why/race/policy, not what.

## References

- Brief: `candidate-pack/candidate-pack/WORK_TASK.md`
- Plan/arch/design: `PLAN.md`, `ARCHITECTURE.md`, `DESIGN.md`
