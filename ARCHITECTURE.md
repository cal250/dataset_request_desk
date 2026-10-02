# Dataset Request Desk: Architecture

## Architectural Intent

Dataset Request Desk is a small internal web application for managing robotics dataset requests and their episode fulfilment workflow. The architecture favors correctness, a small operational footprint, and a repeatable reviewer experience.

**All application development, testing, migrations, seeding, and runtime behavior happens through Docker Compose.** We will not depend on a host-installed Python interpreter, Node.js runtime, PostgreSQL instance, package cache, or manually configured environment. The repository and Docker Compose configuration are the single source of truth for a working system.

The reviewer path must be:

```bash
git clone <repository-url>
cd <repository-directory>
docker compose up --build
```

That command builds the application image, starts PostgreSQL, applies migrations, creates demo users, and starts the web application. The same Compose-defined environment runs the test suite and any import commands.

## System Context

```text
Client / Operator / Admin browser
                |
                | HTTPS in production; HTTP on local Docker Compose
                v
      FastAPI web application container
      - Jinja-rendered HTML pages
      - HTMX partial page updates
      - authentication and authorization
      - request, assignment, import, analytics services
      - structured request logging
                |
                | SQLAlchemy database connection
                v
        PostgreSQL database container
        - application data
        - constraints and indexes
        - migration-managed schema
```

There is no standalone JavaScript frontend service. FastAPI serves the HTML, CSS, HTMX library, and small static assets. This keeps the browser-to-server flow simple and avoids an unnecessary API-authentication/CORS boundary for the available time budget.

## Container Topology

### `db`

PostgreSQL service with a named Docker volume for local data persistence.

Responsibilities:

- Stores users, requests, episodes, assignments, and status history.
- Enforces foreign keys, uniqueness, check constraints, and indexes.
- Exposes its port only to the Compose network by default; optional host mapping is for local diagnostics, not application operation.
- Has a health check so dependent services do not start database work prematurely.

### `api`

FastAPI application image built from the repository's Python dependency manifest and application source.

Responsibilities:

- Serves browser pages and HTMX partial responses.
- Serves JSON endpoints where appropriate, including health and analytics.
- Performs password verification, session handling, server-side authorization, input validation, and domain rules.
- Uses SQLAlchemy to access PostgreSQL.
- Emits structured logs to standard output, so Docker captures them consistently.

The API container starts only after the database health check succeeds. Its entrypoint runs the following sequence:

```text
1. alembic upgrade head
2. seed demo users idempotently
3. start the FastAPI/Uvicorn server
```

Migrations and user seeds must be idempotent: restarting the stack does not duplicate schema objects or users.

### One-off Compose Commands

Some actions are intentionally not automatic startup tasks because they modify business data or are needed only in development/testing.

```bash
# Run the full automated test suite in the application image.
docker compose run --rm api pytest

# Import supplied episode metadata from inside the application image.
docker compose run --rm api python -m app.cli.import_episodes /app/seed/episodes.csv

# Generate optional large clean data and import it, entirely in containers.
docker compose run --rm api python /app/seed/generate_episodes.py 200000
```

The final paths/module names may differ, but the invariant is fixed: commands execute inside Compose services, never through undocumented host tooling.

## Application Layers

```text
HTTP route or HTML form handler
  -> authentication and authorization dependency
  -> Pydantic/form validation
  -> domain service
  -> SQLAlchemy repository/query
  -> PostgreSQL transaction
  -> HTML partial/page or JSON response
```

### Presentation Layer

FastAPI routes render Jinja templates. HTMX form submissions request small HTML fragments so the server can update a request row, assignment list, validation error area, or filter results without a full browser refresh.

Presentation code may hide unavailable controls for clarity, but it is never responsible for access control or business-rule enforcement.

### Authentication and Authorization Layer

Login is the only public action. The server validates the user's password against an Argon2 hash and creates a signed, HTTP-only session cookie.

Every protected route resolves the authenticated user and checks current `is_active` state, role, and request ownership where required. This makes role changes and account deactivation effective even for an existing browser session.

State-changing browser requests use CSRF protection. Production configuration also marks cookies `Secure` and requires HTTPS.

### Domain Service Layer

This layer owns the rules that matter most:

- valid request status transitions and the role that owns each transition;
- client ownership boundaries;
- assignment quality eligibility;
- assignment uniqueness;
- delivery only after enough episodes are assigned;
- CSV normalization, validation, conflict detection, and reporting.

It makes transactions explicit when a business action changes more than one table, such as transitioning status and writing audit history.

### Persistence Layer

SQLAlchemy models map the relational schema. Alembic migrations are the only mechanism for schema change. The application never creates tables ad hoc at runtime.

PostgreSQL constraints complement service validation:

- `users.email` is unique.
- `episodes.episode_id` is unique after canonicalization.
- `assignments.episode_id` is unique, guaranteeing one active assignment per episode.
- Foreign keys protect relationships.
- enum/check constraints protect controlled values and positive counts.

The database is the final protection against concurrent or out-of-band writes; application validation provides understandable user-facing errors.

## Maintainability Standards

The application is designed to be read, changed, and operated by someone other than its original author. Maintainability is a functional requirement.

### Project Structure

The exact filenames may evolve, but ownership remains explicit:

```text
app/
  main.py              application creation, middleware, route registration
  config.py            typed environment configuration
  db.py                engine, session lifecycle, transaction helpers
  models/              SQLAlchemy entities and database constraints
  schemas/             request/form and response validation models
  routes/              thin HTTP/HTML handlers grouped by feature
  services/            domain rules: auth, requests, assignments, imports
  repositories/        reusable database queries where they reduce duplication
  templates/           Jinja pages and HTMX fragments
  static/              CSS and small browser assets
  cli/                 repeatable seed/import commands
  tests/               tests mirroring feature ownership
alembic/               migration scripts
seed/                  supplied import and demo-user inputs
```

Routes translate HTTP/forms into service calls; they do not contain workflow policy or complex SQL. Services own business rules and transactions. Models own database shape and invariants. This separation makes a change such as adding a request status traceable across a small number of predictable places.

### Code Quality Rules

- Use names from the business domain: `request`, `episode`, `assignment`, `status_history`, `client`, and `operator`; avoid vague names such as `data`, `item`, or `helper` for domain behavior.
- Keep functions narrow: one clear purpose, explicit inputs/outputs, and no hidden global state.
- Prefer simple, typed Pydantic models and SQLAlchemy relationships over unstructured dictionaries or hand-built SQL strings.
- Centralize cross-cutting policy such as status transitions, authorization checks, canonicalization, and error responses. Do not copy those rules across routes.
- Keep configuration in typed settings read from environment variables; commit `.env.example`, never a real secret file.
- Pin dependencies and use a formatter/linter/type-checker that runs in the container and CI.
- Use Alembic migrations for every schema change. Never alter the database manually and rely on undocumented state.
- Log meaningful operational context without logging secrets or sensitive content.

### Commenting Policy

Comments explain **why**, constraints, or non-obvious business/concurrency reasoning. Code itself should make ordinary mechanics clear through naming and structure.

Good examples:

```python
# The unique database constraint closes the race between two operators assigning one episode.
assignment = Assignment(request_id=request.id, episode_id=episode.id, assigned_by=user.id)

# Treat conflicting source rows as errors; overwriting could change a delivered dataset's metadata.
return ImportRowError(row_number, "episode_id conflicts with an earlier row")
```

Avoid comments that repeat the code:

```python
# Set the request status.
request.status = target_status
```

Public service functions, configuration choices, and non-obvious import/analytics logic receive concise docstrings or comments. Tests use descriptive names so they document the intended business rule.

### Change Discipline

For each feature or bug fix:

1. Locate the owning route, service, model/migration, template, and tests.
2. Make the smallest coherent change across those boundaries.
3. Add a migration for any schema evolution.
4. Add/update automated tests in the same commit.
5. Run formatter, linter/type checks, and tests in Docker Compose.
6. Write a concise commit message describing intent, not just files changed.

Avoid speculative abstractions, broad refactors mixed with features, duplicated permission checks, and large modules that combine routing, SQL, workflow policy, and rendering. Refactor only when current duplication or complexity makes the next change materially harder.

## Core Data Model

```text
User (client) 1 ---- * Request 1 ---- * Assignment * ---- 1 Episode
                           |
                           *
                           |
                           1 StatusHistory

User (operator/admin) 1 ---- * Assignment
User (operator/admin/client) 1 ---- * StatusHistory
```

### Main Entities

| Entity | Core fields | Purpose |
| --- | --- | --- |
| User | email, password_hash, role, is_active | Authentication and role-based access |
| Episode | external episode ID, robot, task, time, duration, quality | Imported recording metadata |
| Request | client, task, requested count, deadline, notes, status | Dataset demand and workflow state |
| Assignment | request, episode, assigned_by, assigned_at | Records episode allocation to fulfilment |
| Status history | request, old/new status, actor, time | Immutable workflow audit record |

## Request Workflow and Transactions

```text
submitted --operator/admin--> in_progress --operator/admin, enough episodes--> delivered
                                                                     |
                                             client owner -----------+
                                             |                       |
                                         accepted                 rejected
                                                                      |
                                                           operator/admin
                                                                      v
                                                                 in_progress
```

The transition service checks role, request ownership, allowed status pair, and (for delivery) assignment count. It then updates the request and inserts `status_history` in one transaction.

An episode assignment similarly verifies that the episode is `good` or `usable` and has no prior assignment. The database unique constraint makes simultaneous assignment attempts safe: one succeeds; the other returns a conflict rather than corrupting data.

## Import Pipeline

```text
CSV file mounted/available in api container
  -> parse each row with standard CSV parser
  -> normalize formatting-only values
  -> validate required fields and business constraints
  -> insert valid canonical record or classify as duplicate/conflict
  -> produce counts and row-level error report
```

The importer is deterministic, idempotent, and intentionally not ML-driven. It only normalizes values that are clearly formatting differences. It rejects semantic uncertainty rather than guessing.

Examples:

- `"  PICK CUP "` becomes `pick cup`.
- `USABLE` becomes `usable`.
- `excellent` is rejected; it is not guessed to mean `good`.
- `arm-99` is rejected; it is not mapped to an existing robot.
- ambiguous dates are rejected rather than inferred.
- duplicate canonical episode IDs with differing details are reported as conflicts and never silently overwritten.

The unique episode-ID index makes re-importing a file safe. The import result distinguishes inserted records, already-existing records, invalid rows, and conflicts.

## Analytics Path

Analytics are SQL aggregation queries with a validated date range:

- recordings by day and robot;
- request count by status and median submitted-to-delivered duration;
- five most frequent task names among good episodes.

Rows remain in PostgreSQL; Python receives only aggregate results. The initial indexes target date/robot grouping, good-task grouping, client/status listing, request assignments, and assignment uniqueness. Query plans are inspected before adding indexes or more complicated data structures.

At higher episode volume, response measurements and `EXPLAIN ANALYZE` guide changes such as revised composite indexes, daily aggregate/materialized views, date partitioning, or read replicas. We will not introduce Redis, queues, partitions, or replicas before data shows they are necessary.

## Local Development and Verification Contract

The following rules prevent an "it works on my machine" submission:

1. Application dependencies are pinned in the repository and installed in the image build.
2. Every runtime setting has a documented environment variable and an `.env.example` with safe local defaults.
3. No developer-specific absolute paths, local databases, or manually seeded state are required.
4. Database schema is created only by Alembic migrations.
5. Demo users are created by an idempotent seed command run in the container.
6. Tests run in the same application image and against a Compose-defined database.
7. Every behavioral feature includes automated success, failure, and authorization tests in the same change; a manual UI check alone does not complete the feature.
8. GitHub Actions runs the Compose-based full test suite on every push and pull request.
9. The README gives only Compose commands for normal setup, execution, tests, and import.
10. Before submission, verify from a fresh checkout or after `docker compose down -v` that `docker compose up --build` creates a usable system.

`docker compose down -v` removes the local named database volume. It is useful for final clean-start verification and must never be used against a database containing data we need to keep.

## Observability and Failure Handling

- `GET /health` verifies the application is running and database connectivity is available.
- One JSON log line per request includes method, path, response status, duration, and authenticated user ID when available.
- Logs never include plaintext passwords, cookie values, authentication headers, or raw sensitive payloads.
- Validation errors identify the invalid input; authorization errors do not leak another client's data.
- Import reports give operations enough row-level context to correct source exports.

## Continuous Integration

GitHub Actions is part of the repository from the first working feature, not a last-minute addition. The workflow runs on every push and pull request. It builds the same API image defined by Docker Compose, starts the required PostgreSQL service, applies migrations/seeds as needed, and executes `pytest`.

The CI gate verifies that a change works outside the developer's current machine and that each feature's automated tests continue to pass alongside the existing authorization, workflow, assignment, import, and analytics coverage.

## Deployment Boundary

Docker Compose is the required local/reviewer delivery mechanism. It is not presented as production orchestration.

If the system later needs deployment, the same API image can run on a container platform behind HTTPS and a reverse proxy, with a managed PostgreSQL database, secrets injected by the deployment environment, backups, monitoring, and a migration release step. This remains outside the take-home scope unless the deployment stretch item is explicitly selected.

