# NOTES.md — engineering reasoning

## 1. Design

**Data model.** Five tables, all state in PostgreSQL: `users` (email unique,
Argon2 hash only, role, active flag), `episodes` (canonical `episode_id`
unique; robot/task/time/duration/operator/quality), `requests` (owning client,
task, count, deadline, status, submitted/delivered timestamps),
`assignments` (request ↔ episode, `episode_id` unique: one clip, one request),
`status_history` (append-only audit: request, from → to, actor, time).
Everything else (sessions, filters, pagination) is derived, never stored.

**Hardest decisions.**

1. *HTMX + server rendering vs a JS frontend.* One Python app owns rendering,
   auth, and rules, so there is no CORS/token/duplicated-type surface to
   defend. Cost: dual JSON/HTML responses per endpoint (content negotiation),
   which we contained with a single `wants_html()` helper (Accept or
   HX-Request) plus separate `/form` POST handlers that redirect.
2. *Import normalization policy.* The brief's export mixes harmless formatting
   (`USABLE`, `  Pick Cup `) with semantic traps (`excellent`, `arm-99`,
   `14/08/2026`). We canonicalize only the former and reject the latter with
   row-level reasons, because guessing corrupts delivery eligibility and
   analytics silently. Conflicts (same ID, different data) never overwrite.
3. *Constraint vs application validation.* Both: services return readable
   403/409/422s, while unique/FK/check constraints are the last line of
   defense against races (double-assign) and out-of-band writes. The
   double-assign test proves the constraint path, not just the pre-check.

## 2. Left out, simplified, next two days

Left out: password reset/MFA, full-text search, batch assignment, import job
history tables, the background/deployment stretch options. Stretch taken:
**real-time (SSE)** — in-process bounded-queue broadcast, operator-only
`/events` feed, live-refreshing request list. Chosen because the HTMX pages
already swap fragments, so it cost one bus module + one endpoint with no new
infrastructure; the honest limit is single-process (documented Redis pub/sub
step for multi-worker). Simplified: episode list pagination without total-page
prefetch; analytics without rollups; toasts via query param instead of a
session flash store; no CSRF tokens yet (SameSite=lax + POST-only mutations;
tokens are the known gap — see §4).

With two more days: (1) CSRF tokens on browser forms + `Secure` cookies behind
TLS; (2) durable import jobs with per-row lineage for the ops audit trail.

## 3. Something that went wrong

Pressing *Mark delivered* in the browser returned a 500 — yet the request had
actually transitioned (the redirect crashed, not the commit). Diagnosis: the
API log showed `AttributeError: 'RequestStatus' object has no attribute
'HTTP_303_SEE_OTHER'` in `transition_form`. The form field was named `status`,
shadowing the imported `status` module when building the redirect. Fixed by
renaming the field to `target_status` (template + handler), then hardened all
browser form actions to re-render the page with the reason inline instead of
leaking JSON errors. Regression test: form double-delivery returns 200 with
the message, never 500. Lesson: form handlers need their own tests precisely
because the JSON suite never touches them.

## 4. Security

Passwords: Argon2id via `pwdlib`; seeds hold disposable plaintext, the DB holds
hashes only; login failures are generic (no user enumeration). Sessions:
`itsdangerous`-signed `HttpOnly`, `SameSite=lax` cookies (`Secure` when
`SESSION_HTTPS_ONLY=true`); the user is reloaded from the DB per request so
deactivation/role change bites immediately. Validation: Pydantic + service
checks; clients get 404 (not 403) for others' requests to avoid leaking IDs.

Two worries that keep me up: (1) **missing CSRF tokens** — SameSite helps but
a forged cross-site POST from an authenticated browser is still possible;
tokens on all mutating forms are the next commit. (2) **CSV as an attack
surface** — uploads are parsed server-side; we cap error reporting, bound page
sizes, and never interpolate filenames, but a hostile multi-MB file still
occupies a worker (streaming/chunked import + size limits come with job
tracking).

## 5. Scale (measured, not guessed)

We loaded 50,171 episodes and drove the app with 10 concurrent users (200
requests). Single user: health 13ms, requests page 25ms, episodes page 30ms,
year-range analytics 67ms. Under load (28 req/s): p50 119–215ms, p95
307–563ms — sub-second throughout, acceptable for an internal tool. 20 parallel
logins completed in 3.0s. Two surprises: (1) a 40-session Argon2 burst
serialized badly on the single dev uvicorn worker (median session 14s) — auth
CPU, not Postgres, is the first 10× bottleneck, fixed by multi-worker uvicorn
+ login rate limiting before any DB work; (2) the idempotent import *rerun*
over 50k rows took ~88s of row-by-row SELECTs, while analytics over the same
data took 0.07s — so the import loop, not the queries, is the real 100× debt
(bulk `COPY`/batched upsert first, rollups only if `EXPLAIN ANALYZE` then
still complains). No queues, caches, or replicas before measurements demand
them — now we have the measurements.

## 6. Tradeoffs made along the way

- *Dual JSON/HTML endpoints* instead of separate API + pages: one URL serves
  both via `wants_html()`, keeping `/docs` and the browser consistent. Cost:
  every list/detail route carries a template branch; the alternative (split
  routers) would have doubled the route surface for the same rules.
- *Single-commit import* instead of chunked jobs: a 190-row brief file imports
  atomically with a clear report, at the price of a worker held for the whole
  file — the 50k probe proved this won't survive 100×, hence the job-queue
  item in §2.
- *Per-request user reload* instead of caching the session: every action pays
  one indexed lookup so deactivation/role changes bite instantly. Cheap at our
  scale, revisit only if auth lookups ever dominate profiles.
- *No `Secure`-by-default cookies / no CSRF yet*: kept local HTTP review
  frictionless; production must flip `SESSION_HTTPS_ONLY=true` and add tokens
  (§4). A conscious demo-vs-prod split, not an oversight.

## 7. AI tooling

An AI coding assistant (Muse Spark via OpenCode) scaffolded boilerplate
(models, routes, test skeletons) and drafted these docs; every rule, query,
and policy decision was reviewed, run (`pytest` + `ruff` in Compose), and
fixed by hand — including the three bugs above, two HTMX swap issues, and the
entrypoint permission failure CI caught on Linux. The live session will show
whether that understanding holds.
