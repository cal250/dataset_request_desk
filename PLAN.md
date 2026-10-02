# Dataset Request Desk: Build Plan

## Goal

Build a compact, production-minded internal platform for a robotics data collection company. Clients create and review dataset requests; operators fulfil them using imported robot episodes; admins manage accounts. The priority is correct server-enforced domain rules, a relational database, repeatable operations, targeted tests, and clear written reasoning.

This is intentionally a focused system. A clean, explainable implementation of the required scope is more valuable than a broad unfinished product.

## Scope and Success Criteria

The completed repository will provide:

- Python backend with a relational PostgreSQL database and versioned migrations.
- Authentication for every action except login, with role and ownership enforcement on the server.
- An HTMX web UI for the required client and operator workflows.
- CSV episode import that is safe to repeat, validates messy rows, and reports outcomes clearly.
- Database-side analytics for a requested date range.
- Health endpoint and structured per-request logging.
- Docker Compose startup from a clean clone.
- Automated tests runnable with one command.
- GitHub Actions CI that runs the tests on pushes and pull requests.
- `README.md` for setup and demo credentials, plus `NOTES.md` with engineering decisions.

The one optional stretch item is **real-time request updates with Server-Sent Events (SSE)**, and it will only be attempted after all required features, tests, and documentation are complete.

## Chosen Architecture

```text
Browser
  |
  | HTML forms and HTMX partial requests
  v
FastAPI application
  |- rendered Jinja templates and small JSON endpoints
  |- authentication and role/ownership checks
  |- domain services for requests, transitions, assignments, imports
  v
PostgreSQL
  |- users, episodes, requests, assignments, status_history
  |- Alembic migrations, constraints, indexes
```

### Stack

- **Backend:** Python, FastAPI, SQLAlchemy 2, Alembic, Pydantic.
- **Database:** PostgreSQL.
- **Frontend:** Jinja templates, HTMX, modest custom CSS.
- **Authentication:** Argon2 password hashes and signed, HTTP-only browser session cookies.
- **Testing:** pytest, with a dedicated test database.
- **Operations:** Docker Compose and GitHub Actions.

### Why HTMX instead of Next.js

The brief explicitly permits HTMX plus templates. It is the best fit for the time budget because one Python application owns server rendering, forms, authentication, authorization, and API behavior. This avoids a separate frontend build, CORS configuration, duplicated client/server types, and token-sharing complexity.

Next.js would be valid, but would add a frontend service and an API boundary that does not improve correctness for this small internal tool. We will choose the smaller surface area so we can understand and defend every component in the live session.

### Why PostgreSQL instead of SQLite

PostgreSQL supports concurrent transactions, indexes, database constraints, reliable analytics, query planning, and row locking. SQLite would be acceptable for a prototype, but does not model the intended multi-user operational environment as well. Docker Compose will run PostgreSQL locally, so reviewers need no local database installation.

## Domain Model

### Users

`users`

- `id` UUID or integer primary key
- `email` unique and normalized
- `password_hash` only; never a plaintext password
- `role`: `client`, `operator`, or `admin`
- `is_active`
- `name`
- `organisation` nullable; used for client accounts
- created/updated timestamps

### Episodes

`episodes`

- `id` internal primary key
- `episode_id` canonical external identifier, unique
- `robot_id`
- `task_name` canonical display/query value
- `recorded_at` timezone-aware timestamp
- `duration_seconds` positive integer within documented upper bound
- `operator_name`
- `quality`: `good`, `usable`, or `bad`
- created/updated timestamps

### Requests

`requests`

- `id` primary key
- `client_id` foreign key to users
- `task_name`
- `episodes_requested` positive integer
- `deadline`
- `notes`
- `status`: `submitted`, `in_progress`, `delivered`, `accepted`, `rejected`
- `submitted_at`, `delivered_at`, created/updated timestamps

### Assignments

`assignments`

- `id` primary key
- `request_id` foreign key
- `episode_id` foreign key
- `assigned_by` foreign key to user
- `assigned_at`

`episode_id` has a unique constraint. This is the last line of defense against assigning one episode to two requests when concurrent operator actions happen.

### Status History

`status_history`

- `id` primary key
- `request_id` foreign key
- `from_status`
- `to_status`
- `changed_by` foreign key to user
- `changed_at`

Status history is append-only. It provides an audit trail, supports median fulfilment-time analytics, and helps diagnose workflow issues.

## Authorization and Workflow Rules

All authorization happens in the FastAPI server. Hiding a button is only a usability aid and never a security mechanism.

| Role | Allowed actions |
| --- | --- |
| Client | Create requests; list/view only its own requests; accept or reject its own delivered requests |
| Operator | View all requests; move operator-owned workflow steps; assign valid episodes; import episodes |
| Admin | All operator actions plus user creation, deactivation, and role changes |

### Valid Status Transitions

| Current status | Valid next status | Who can act |
| --- | --- | --- |
| `submitted` | `in_progress` | operator/admin |
| `in_progress` | `delivered` | operator/admin, only after assignment threshold passes |
| `delivered` | `accepted` | owning client |
| `delivered` | `rejected` | owning client |
| `rejected` | `in_progress` | operator/admin |

All other transitions are rejected with a clear `409 Conflict` or `422 Unprocessable Entity`. The transition service will validate the acting user, the request owner where relevant, the current/target status pair, and the delivery assignment threshold. It will write the status history record in the same transaction as the request update.

### Assignment Rules

- An episode can be assigned to at most one request.
- Only episodes with `good` or `usable` quality can be assigned.
- A request may only be delivered after it has at least `episodes_requested` assignments.
- Operators/admins perform assignments; clients do not.

Application validation produces useful errors. Database unique/foreign-key/check constraints protect the same invariants if an alternate script or concurrent request bypasses normal application flow.

## Password and Session Flow

The seed JSON contains disposable demo credentials for reviewers. It is input to the seed command, not the data format stored in the database.

```text
users.json plaintext demo password
  -> seed command hashes it with Argon2
  -> database stores password_hash only

login form password
  -> look up user by email
  -> Argon2 verifies entered password against password_hash
  -> server sets signed, HTTP-only session cookie on success
```

The original password is not recoverable from the stored hash and is never logged. `HttpOnly` prevents browser JavaScript from reading the session cookie. In production the cookie is also `Secure` over HTTPS, forms receive CSRF protection, and environment-provided secrets replace committed demo credentials. The authenticated user is checked against current database state on each request so deactivation and role changes take effect promptly.

## CSV Import Policy

The seed export is deliberately messy. Import behavior must be deterministic, testable, idempotent, and explainable. We will not use machine learning for cleanup: these are structured data-quality decisions, and a model could silently guess incorrect business data.

### Principle

Normalize only formatting-only values. Reject values requiring semantic guessing. Include row number and a clear reason for every skipped row.

| Input issue | Handling | Reason and tradeoff |
| --- | --- | --- |
| Leading/trailing whitespace | Trim text fields | Fixes harmless export formatting; do not blindly trim fields where whitespace could be meaningful |
| Quality case variation | Trim, lowercase, validate enum | `USABLE` is safely canonicalized; unknown values are not guessed |
| Task-name case and spacing | Trim, collapse repeated spaces, canonicalize case | Prevents fragmented filters/analytics; could merge intentionally distinct casing, so document the assumption |
| Episode ID case | Trim and uppercase before uniqueness check | Detects `EP-00003`/`ep-00003` collision; assumes source IDs are logically case-insensitive |
| Robot IDs | Normalize known formatting then validate against allow-list/table | Stops `arm-99`; legitimate new robots require controlled configuration/domain update |
| Dates | Accept explicit, unambiguous formats then store UTC-aware time | Date strings that require guessing are rejected |
| Durations | Require a positive integer with documented upper bound, initially 3,600 seconds | Rejects `N/A`, negative and absurd values; future long recordings require policy change |
| Missing required field | Skip with row-level error | Maintains integrity, but source system must be corrected |
| Exact duplicate ID/data | Insert first valid occurrence; report later duplicate | Enables idempotency; does not auto-update old metadata |
| Same canonical ID, different data | Skip/report as conflict | Avoids silent overwrite; requires human decision |
| Unknown quality, e.g. `excellent` | Skip/report; do not map to `good` | Quality affects delivery eligibility and analytics, so guessing is unsafe |

Examples:

```text
"  PICK CUP " -> "pick cup"       safe formatting normalization
"USABLE"      -> "usable"         safe enum normalization
"excellent"   -> reject            semantic guess is unsafe
"arm-99"      -> reject            semantic guess is unsafe
"08/09/2026" -> reject if ambiguous
```

### Idempotency and Reporting

`episodes.episode_id` has a database unique constraint. An import run returns counts such as `inserted`, `already_exists`, `skipped_invalid`, and `skipped_conflict`, alongside a bounded row-level error list. Re-running the same file cannot create duplicate episodes.

For a production ingestion pipeline, we would retain the source file and durable import-job/error records for full lineage. The take-home will retain enough import result detail to demonstrate diagnosis and recovery without overbuilding a data platform.

## Endpoints and UI

The exact route names can evolve, but the behavioral boundary should remain small and obvious.

| Area | Required behavior |
| --- | --- |
| Health | `GET /health` returns service/database health |
| Authentication | Login, logout, authenticated current-user lookup |
| Requests | Client creates/lists/reads own requests; operator/admin lists all |
| Workflow | Authorized transition endpoint/action writes status history |
| Episodes | Operator/admin filter by task name and quality |
| Assignments | Operator/admin assigns eligible unassigned episodes |
| Import | Operator/admin uploads CSV or invokes documented import command |
| Analytics | Authorized date-range response with required aggregates |
| Admin | Admin creates/deactivates users and changes roles |

### Required Screens

- Login.
- Client request list with status and detail.
- Client request creation form.
- Delivered request accept/reject controls for its owner.
- Operator request list across all clients.
- Operator request detail/status transition controls.
- Operator episode list with task-name and quality filters, plus assignment control.
- Optional, compact admin user-management screen.

HTMX requests will update only the relevant list, status row, or form area. The server remains the only source of truth.

## Analytics and Database Design for Scale

All required analytics are computed in SQL, never by loading a full result set into Python:

- episodes recorded per day and robot;
- request counts grouped by status and median time from submitted to delivered;
- top five task names by count of good episodes.

Initial indexes to validate against actual query plans:

```sql
CREATE INDEX episodes_recorded_robot_idx ON episodes (recorded_at, robot_id);
CREATE INDEX episodes_quality_task_idx ON episodes (quality, task_name);
CREATE INDEX requests_client_status_idx ON requests (client_id, status);
CREATE INDEX assignments_request_idx ON assignments (request_id);
CREATE UNIQUE INDEX assignments_episode_unique_idx ON assignments (episode_id);
```

The application will paginate episode searches and request lists from the start. Date ranges will be required/bounded for analytics requests where appropriate.

### Scaling Decisions and Evidence

Use the simplest design that preserves correctness, then add complexity only after measuring latency, database load, throughput, and query plans.

| Decision | Why now | Cost | Evidence-based next step |
| --- | --- | --- | --- |
| Direct synchronous import | Small seed files, clear feedback | Large files occupy a web worker | Add durable import jobs, chunking, and workers when file size/latency shows need |
| SQL aggregation | Data stays close to database | Large scans can be expensive | Inspect `EXPLAIN ANALYZE`; add/refine indexes and rollups |
| One PostgreSQL primary | Simple operational model | Reads/writes share one database | Add connection pooling, read replicas when measured load requires it |
| Normalized task strings | Consistent analytics/filtering | Text values remain flexible | Introduce managed task catalog when governance/search needs prove it |
| Signed cookie session | Simple HTMX browser flow | Requires CSRF protection and current-user lookup | Central session/revocation store only if audit/revocation requirements demand it |
| No Redis/Celery initially | No proven asynchronous workload | Long tasks cannot run safely in HTTP | Add queue workers for heavy import/export work when measured |

At 10x users, stateless FastAPI instances behind a load balancer with PostgreSQL connection pooling should be sufficient. At 100x episodes, episode filtering and analytics are the likely bottleneck. We will inspect execution plans, revise indexes, consider date partitioning, and add materialized/pre-aggregated daily metrics for repeated dashboard queries. This is a measured response, not premature infrastructure.

## Logging and Operability

- `GET /health` checks application health and database connectivity.
- Structured JSON logging emits one line per request with method, path, status, duration, and authenticated user ID when present.
- Do not log passwords, session cookies, authorization headers, or raw sensitive form bodies.
- Consistent error responses distinguish validation errors, authentication failures, authorization failures, conflicts, and unexpected server errors.
- Docker Compose starts database, runs migrations, creates seed users, and starts the application from a clean clone.

## Automated Tests and CI

Tests run with one documented command, for example:

```bash
docker compose run --rm api pytest
```

High-value tests:

- Login success/failure and protected-route authentication.
- Client cannot view or modify another client's request.
- Client cannot assign episodes or perform operator-owned transitions.
- Operator cannot accept/reject on behalf of a client.
- Admin-only user management is enforced.
- Every valid and invalid status transition is tested.
- Delivery fails below the requested assignment threshold.
- `bad` episodes cannot be assigned.
- An episode cannot be assigned to two requests.
- Import normalization, invalid-row reporting, duplicate/conflict handling, and second-run idempotency.
- Health endpoint and analytics response behavior.

GitHub Actions will build/start the Compose environment and run the test command on pushes and pull requests. A coverage percentage badge is not a goal; precise protection of high-risk business rules is.

### Feature Completion Rule

No feature is considered complete when its page or endpoint merely appears to work manually. Each feature is built as a small vertical slice:

1. Define the rule and expected success/failure behavior.
2. Implement the smallest server-side, database, and UI change needed.
3. Add or update automated tests in the same commit, especially authorization and invalid-input cases.
4. Run the focused tests in Docker Compose, then run the full suite before pushing.
5. Let CI run the full suite again on every push and pull request.

Examples: a new status transition requires valid-transition, invalid-transition, role, ownership, history, and UI tests; a new importer normalization rule requires valid-input, invalid-input, reporting, and repeat-import tests. Cosmetic-only CSS changes may be manually checked, but all behavior and domain rules need automated coverage.

## Docker and Submission Flow

The repository, not Docker Hub, is the delivery artifact. A reviewer will use:

```bash
git clone <repository-url>
cd <repository-directory>
docker compose up --build
```

The repository includes Dockerfiles, `docker-compose.yml`, migrations, source, seed data, `.env.example`, `README.md`, and `NOTES.md`. Docker Hub is unnecessary for this take-home unless we explicitly choose the separate deployment stretch, which we are not doing.

The README must include application URL, test command, seed credentials, import command/instructions, and a short troubleshooting note.

## Git History Strategy

The repository history should be truthful, reviewable, and easy to bisect. Each commit represents one coherent, working change with its relevant tests and documentation. We do not manufacture timestamps, rewrite history to make it look older, or split one feature into artificial micro-commits.

### Commit Rules

- Initialize the repository before implementation and commit the supplied brief/reference documents separately from application code.
- Keep each commit narrow: one foundation change, one domain capability, one UI workflow, or one documentation/CI change.
- Include tests in the same commit as the behavior they verify.
- Run the relevant containerized tests before committing; run the full suite before pushing.
- Use imperative, descriptive messages: `Add client request creation` rather than `updates` or `fix stuff`.
- Do not mix unrelated formatting, refactoring, generated files, and feature work in one commit.
- Never commit `.env`, password hashes generated for a real environment, database volumes, virtual environments, caches, or build artifacts.
- Amend only the immediately previous local commit when correcting a small mistake before it has been shared; otherwise make a follow-up commit so the history remains honest.

### Planned Milestones

The following is a guide, not a reason to force a commit when a milestone is incomplete. Every listed commit should leave the project in a comprehensible state.

| Order | Example commit message | Contents |
| --- | --- | --- |
| 1 | `Initialize Dataset Request Desk project` | Git ignore rules, supplied brief references, plan/architecture/design docs, repository metadata |
| 2 | `Add Docker Compose application foundation` | API image, PostgreSQL service, environment example, basic startup/health path |
| 3 | `Add database schema and migrations` | SQLAlchemy models, initial Alembic migration, constraints, database test setup |
| 4 | `Add seeded users and session authentication` | Argon2 seed/login/logout/current-user behavior and tests |
| 5 | `Add request workflow and authorization` | Client request creation/listing, server ownership checks, transition/history service and tests |
| 6 | `Add episode import with validation reporting` | Canonicalization, idempotency/conflict policy, import CLI/endpoint, import tests |
| 7 | `Add assignment rules and operator workflow` | Episode filters, assignment service/UI, delivery threshold and concurrency-rule tests |
| 8 | `Add database analytics and query indexes` | Date-range analytics endpoint/view, SQL aggregation, indexes, query tests |
| 9 | `Add HTMX client and operator workspaces` | Polished templates/partials, responsive interaction states, manual UX verification |
| 10 | `Add CI and delivery documentation` | GitHub Actions, README, NOTES, Compose clean-start verification |
| 11 | `Add real-time request updates` | Optional SSE stretch only after required features are fully complete |

Small corrective commits are healthy when they represent real discoveries, for example `Handle conflicting duplicate episode IDs during import`. They give reviewers evidence of debugging and iteration when accompanied by the test that protects the correction.

## Build Sequence

### Phase 1: Foundation

- [ ] Initialize Git repository and make an initial commit.
- [ ] Create FastAPI project structure, dependency configuration, Dockerfiles, Compose, and environment example.
- [ ] Establish formatter, linter/type-check command, and concise comment/docstring conventions in the container.
- [ ] Add PostgreSQL connection, SQLAlchemy models, Alembic, first migration, and health endpoint.
- [ ] Add structured request logging.
- [ ] Create repeatable seed command that hashes users from `seed/users.json`.

### Phase 2: Authentication and Core Domain

- [ ] Implement Argon2 password verification, signed HTTP-only session cookie, login/logout, and current-user dependency.
- [ ] Implement role and ownership helpers.
- [ ] Implement request creation/list/detail with client scoping.
- [ ] Implement one transition service with status-history writes.
- [ ] Implement episode list/filtering and assignment service.

### Phase 3: Import and Analytics

- [ ] Implement deterministic CSV parser, validation, normalization, database insert/conflict handling, and import report.
- [ ] Implement database-side analytics with date-range validation and indexes.
- [ ] Test importing the supplied small CSV twice.
- [ ] Optionally generate a large clean CSV and inspect import/query behavior.

### Phase 4: HTMX Interface

- [ ] Build login and role-aware navigation.
- [ ] Build client create/list/detail/accept/reject workflow.
- [ ] Build operator request list, transition controls, episode filters, and assignment controls.
- [ ] Build compact admin user-management interface if time allows after required operator/client flow.

### Phase 5: Quality and Delivery

- [ ] Add and run high-value pytest suite.
- [ ] Add GitHub Actions CI.
- [ ] Review module boundaries, naming, non-obvious comments, error handling, and removal of duplicated business rules.
- [ ] Write README and NOTES with explicit assumptions, tradeoffs, limitations, security, and scale plan.
- [ ] Verify clean-clone Compose startup and complete manual client/operator walkthrough.
- [ ] Commit coherent milestones with meaningful messages.

### Phase 6: Optional Stretch

- [ ] Only after all required items pass: add a small SSE stream so operator list updates after new requests/status changes.

## What We Deliberately Leave Out

- File/object storage for video clips; episodes contain metadata only.
- Full organization/multi-tenant administration beyond client ownership.
- Batch assignment, bulk editing, and sophisticated search.
- Password reset, MFA, email verification, and external identity provider.
- Full import lineage storage and asynchronous job queue.
- Production deployment, managed secrets, monitoring dashboards, backups, and disaster recovery.
- The stretch item unless the core is complete.

With two more days, prioritize durable import jobs, production deployment/security hardening, pagination/search improvements, task/robot management, and metrics/monitoring.

## Live Technical Session Preparation

We must understand and be able to modify every line submitted. Before coding a change during the session:

1. Identify the affected business rule, endpoint/template, migration/model, test, and security implication.
2. Explain the smallest safe server-side change before editing.
3. Update or add a targeted test.
4. Consider migration and concurrency effects.
5. Demonstrate the behavior and run the relevant test.

Practice likely extensions:

- Add a new request status or transition.
- Add pagination or a new episode filter.
- Change episode eligibility rules.
- Add a role permission.
- Add an analytics grouping.
- Diagnose a failed/partial CSV import.
- Explain why a database constraint is needed in addition to application validation.

## NOTES.md Checklist

- Data model and where state lives.
- Hardest design decisions and rationale.
- Explicit assumptions, especially import normalization and duplicate policy.
- Simplifications and next two-day roadmap.
- A real issue encountered and how it was diagnosed.
- Password/session handling, validation, CSRF, and the two most relevant security concerns.
- Scale pressure points and measured scaling plan.
- AI tools used and what they helped with.

