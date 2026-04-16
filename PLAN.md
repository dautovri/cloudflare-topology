<!-- /autoplan restore point: /Users/rd/.gstack/projects/dautovri-cloudflare-topology/main-autoplan-restore-20260416-215708.md -->
# Plan: Scheduled topology regeneration + fire-and-forget /regenerate

## Problem Statement

[server/server.py](server/server.py) runs [`generate_topology()`](server/server.py#L86-L111) once at startup (line 176), then relies on manual `POST /regenerate` calls to refresh `network_topology.html`. Today `/regenerate` is synchronous: it calls `subprocess.run(..., timeout=300)` inline on the request thread ([server/server.py](server/server.py#L166)), so the HTTP connection stays open up to 5 minutes. Reverse proxies and browsers time out well before that.

Two real problems fall out:

1. **Stale-by-default.** Topology only refreshes if a human (or cron outside the app) calls `/regenerate`. If nobody does, the served HTML drifts from the live Cloudflare state.
2. **Blocking trigger.** When someone does call `/regenerate`, they either wait up to 5 minutes or get cut off by a proxy. Neither is a good contract.

[TODOS.md](TODOS.md) line 7 has already captured the right fix: "Add caching/TTL for topology data (15 min TTL, regenerate in background)." This plan ships that.

## Premise (confirmed by user — reframed again from async job queue direction)

- Background-scheduled regeneration is Tier 1. On-demand status polling is Tier 2, deferred.
- `/regenerate` becomes an admin override, fire-and-forget (202 + background thread). No status endpoint, no job IDs, no LRU, no `?wait=true`.
- The artifact is one file (`network_topology.html`). Global "is a regen running" flag, not per-job state.

Both CEO voices (Claude subagent + Codex) independently flagged the async job queue direction as overbuilt. User accepted the reframe to Tier 1 only.

## Proposed Design

### 1. Background scheduler

A `threading.Timer` fires every `REGEN_INTERVAL_SECONDS` (default 900 = 15 min). On fire:

1. Tries to acquire `_regen_lock` (a `threading.Lock`) non-blocking. If already held, skip this tick (a manual regen is in progress).
2. Otherwise runs `generate_topology()`, releases lock in `finally`.
3. Schedules the next tick regardless of outcome.

Startup flow:
- Run `generate_topology()` synchronously on boot (unchanged — [server/server.py](server/server.py#L176)).
- Then start the scheduler (unless `REGEN_INTERVAL_SECONDS=0`).

Shutdown: daemon thread; process exit kills it cleanly.

### 2. Fire-and-forget /regenerate

```
POST /regenerate → 202 { "status": "queued" }          (lock acquired, background thread started)
POST /regenerate → 409 { "status": "already_running" } (lock held by scheduler or prior call)
```

- Auth unchanged (bearer token via `REGEN_AUTH_TOKEN`, [server/server.py](server/server.py#L152-L164)).
- No status endpoint. Freshness visible via `/health` (see §3) and via `network_topology.html` mtime.
- Errors during the background run are logged; caller already got 202 and moved on.

### 3. /health exposes freshness

Extend [`/health`](server/server.py#L141-L150) to include:
- `last_generated_at` (ISO-8601) — mtime of `network_topology.html`
- `topology_exists` (existing)
- `regen_in_progress` (bool — is the lock held?)
- `next_scheduled_regen_at` (ISO-8601) — computed from the timer

No auth on /health. This is the observability the async-job-queue plan tried to add via a status endpoint — here it's just fields on the existing health check.

### 4. Configuration

Env vars:
- `REGEN_INTERVAL_SECONDS` — default 900. Set to `0` to disable scheduler (manual /regenerate + startup only).
- `REGEN_AUTH_TOKEN` — unchanged.

Document both in README.

## Affected Files

- [server/server.py](server/server.py) — add scheduler, lock + `_regen_in_progress` bool flag, drift-accurate `_next_scheduled_at`, background worker wrapped in `try/finally`; simplify `/regenerate` to 202/409; extend `/health`; validate `REGEN_INTERVAL_SECONDS` (reject non-int, negative → disable with warning); detect gunicorn multi-worker at startup and log ERROR + refuse to schedule if detected
- [main.py](main.py) — atomic write of `network_topology.html` (write to tempfile in same dir, `os.replace()` on success) so SIGKILL from subprocess timeout cannot leave a truncated file
- [tests/test_server.py](tests/test_server.py) — **new file** — 16 tests per test plan artifact (202 on idle, 409 when locked, all auth paths, /health fields + ISO-8601 + bool type, scheduler tick skip/reschedule, REGEN_INTERVAL_SECONDS validation, startup generate_topology)
- [README.md](README.md) — document `REGEN_INTERVAL_SECONDS` (default 900, 0 disables), new 202/409 contract, `/health` fields, **single-process deployment only** (explicit gunicorn -w 1 warning), 5-min subprocess timeout behavior
- [TODOS.md](TODOS.md) — mark line 7 (caching/TTL) as shipped

## Out of Scope

- Status polling endpoint, job IDs, LRU, `?wait=true`. Tier 2 only if evidence warrants.
- Multi-process/multi-replica coordination (Redis, SQLite). Single-process only. Document in README.
- Cancellation.
- Replacing `subprocess.run` with in-process `main()` call. Works, no need.
- Retry logic in `services/cloudflare_api.py`. Partial work from prior plan is orphaned but harmless; leave as-is.
- Persistent job/run history. `network_topology.html` mtime is the record.
- Rate limiting.
- Frontend changes.

## What Already Exists

| Sub-problem | File | State |
|---|---|---|
| Bearer-token auth | [server/server.py](server/server.py#L152-L164) | ✅ shipped, reused |
| `generate_topology()` worker | [server/server.py](server/server.py#L86-L111) | ✅ shipped, wrap in lock |
| Startup regeneration | [server/server.py](server/server.py#L176) | ✅ shipped, unchanged |
| /health endpoint | [server/server.py](server/server.py#L141-L150) | ✅ shipped, extend with freshness |
| Test infra | [tests/test_network_graph.py](tests/test_network_graph.py) | ✅ 39/39 pass, pattern to copy |
| CI | [.github/workflows/ci.yml](.github/workflows/ci.yml) | ✅ runs pytest on push |
| TTL direction captured | [TODOS.md](TODOS.md) line 7 | ✅ this plan ships it |

## Error & Rescue Registry

| Error Scenario | Behavior | Rescue Path |
|---|---|---|
| Scheduler tick fires while manual regen running | Tick skipped (lock held), next tick runs in 15 min | None needed; self-healing |
| Manual /regenerate during scheduler run | 409 `already_running` | Caller retries after a few minutes |
| Background regen fails (auth, network, subprocess) | Logged with stack; lock released in `finally`; next tick retries | Operator checks logs; /health `last_generated_at` shows staleness |
| Server restart mid-regen | Background thread dies with process; lock gone; startup regen re-runs | Self-healing |
| Two replicas both running scheduler | Both regenerate, last-writer-wins on file | README: "single-process deployment only" |
| `REGEN_INTERVAL_SECONDS=0` | Scheduler disabled; manual /regenerate + startup work only | Documented |

## Failure Modes Registry

| Mode | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Lock never released (worker exception) | Low | `/regenerate` always 409 | `try/finally` around `lock.release()`; test 7 covers exception path |
| Scheduler drift (task takes > interval) | Medium | `/health` next_scheduled_regen_at inaccurate | Track `_next_scheduled_at = max(now, prev + interval)` instead of reschedule-from-end |
| TOCTOU race on `/health` reading lock state | Low | Observability noise only (no data corruption) | Explicit `_regen_in_progress: bool` flag (set before work, cleared in finally) — `/health` reads flag, not `lock.locked()` |
| Partial/truncated `network_topology.html` if subprocess killed mid-write | Medium | Serves broken HTML | `main.py` writes to `tempfile.NamedTemporaryFile` in same dir, then `os.replace()` — POSIX-atomic |
| Background thread silently crashes | Low | Topology goes stale | Exceptions logged at ERROR; `/health` `last_generated_at` reveals staleness |
| Multi-replica deployment | Medium (if undocumented) | Redundant regens, possible file corruption | Explicit README warning + runtime detection: if `GUNICORN_CMD_ARGS` or `UWSGI_WORKERS > 1` or `WEB_CONCURRENCY > 1`, log ERROR and set `REGEN_INTERVAL_SECONDS=0` |
| `REGEN_INTERVAL_SECONDS` misconfigured (negative, non-int, or <60) | Low | Crash on startup or Cloudflare rate-limit | Validate on startup: non-int → default 900 + WARN; negative → 0 (disabled) + WARN; no enforced floor in v1 but README recommends ≥60s |
| subprocess.run 300s timeout cascade during peak load | Low | Scheduled tick blocked up to 5 min | Acceptable; REGEN_INTERVAL_SECONDS ≥ 600 recommended; documented |

## Open Questions

- `threading.Timer` vs APScheduler: recommend `threading.Timer` — zero new deps, ~20 lines, explicit.
- Is `/health` cheap enough for scrape-every-10s? Yes — mtime stat + bool read is <1ms.

## DX Review Outputs (Phase 3.5)

### 409 response body — actionable

Instead of bare `{"status":"already_running"}`, return:

```json
{
  "status": "already_running",
  "hint": "GET /health returns regen_in_progress and next_scheduled_regen_at"
}
```

Also set HTTP header `Retry-After: 10` so generic clients back off automatically.

### /health response schema — documented in README

```json
{
  "status": "healthy",
  "topology_exists": true,
  "last_generated_at": "2026-04-16T14:15:00Z",
  "regen_in_progress": false,
  "next_scheduled_regen_at": "2026-04-16T14:30:00Z"
}
```

All five fields go in a typed schema table in README, so Prometheus/Datadog integrations can consume them without reading source.

### README additions (specific sections)

1. **Environment Variables table** — add rows for `REGEN_INTERVAL_SECONDS` (default 900, 0 disables, valid range 0 or ≥60, recommended ≥300) and `REGEN_AUTH_TOKEN` (shipped, currently undocumented — fix in this plan).
2. **Scheduled Regeneration** subsection under Docker Deployment — default behaviour, how to customise, how to disable.
3. **⚠️ Single-Process Deployment Only** callout — explicit gunicorn `-w 1` instruction; note that multi-worker deployments are auto-detected and scheduler disabled with ERROR log.
4. **API Contract** subsection — POST `/regenerate` returns 202 (queued) or 409 (already_running, with `Retry-After: 10`); GET `/health` schema table.
5. **Upgrade Guide: v0.1 → v0.2** — the `/regenerate` response code changes from 200 to 202. Existing [Makefile](Makefile#L79-L81) `curl -X POST` works (ignores body); scripts checking `== 200` must be updated to accept `202|200`.
6. **Monitoring & Debugging** subsection — `docker logs <container> | grep -i scheduler`, `curl /health | jq '.last_generated_at'`, "if last_generated_at is older than 2× REGEN_INTERVAL_SECONDS, restart the container".

### Startup logging (required)

On boot, log (INFO):
- `Scheduler: enabled, interval 900s (~every 15m)` or `Scheduler: disabled (REGEN_INTERVAL_SECONDS=0)`
- `Auth: REGEN_AUTH_TOKEN set` or `Auth: /regenerate disabled (no REGEN_AUTH_TOKEN)`
- Warnings for `REGEN_INTERVAL_SECONDS < 60` and multi-worker detection

Thread name: `threading.Thread(name="topology-scheduler", ...)` so stack dumps are legible.

### DX Scorecard

| Dimension | Initial | Target | Delta |
|---|---|---|---|
| 1. Getting started < 5 min | 4 | 8 | README env var table + Scheduled Regeneration section |
| 2. API/CLI naming guessable | 7 | 8 | Keep `REGEN_INTERVAL_SECONDS` (clear, units-suffixed) |
| 3. Error messages actionable | 5 | 9 | 409 body includes `hint`; `Retry-After` header |
| 4. Docs findable & complete | 3 | 9 | /health schema table; /regenerate contract section |
| 5. Upgrade path safe | 3 | 8 | Upgrade Guide section; document 200→202 contract break |
| 6. Dev environment friction-free | 7 | 8 | `python main.py` unchanged; Docker unchanged default |
| 7. Observability discoverable | 4 | 9 | /health fields typed & documented; startup logs structured |
| 8. Deployment safety | 4 | 9 | Gunicorn runtime detection + README callout |
| **Overall** | **~5/10** | **~8.5/10** | |

### TTHW (time-to-hello-world)

- Local dev: `python main.py` → ~2 min (unchanged)
- Docker auto-refresh: `docker run -e CLOUDFLARE_API_TOKEN=... -e CLOUDFLARE_ACCOUNT_ID=... -p 8080:8080 cloudflare-topology` → ~3 min to first fresh render, then auto-refreshes every 15 min with zero operator action. Target: <5 min. ✓

### Developer Journey Map (9-stage)

| Stage | Touchpoint | State | Fix |
|---|---|---|---|
| 1. Discover | GitHub README | ✓ clear CLI pitch | — |
| 2. Install | `pip install -r requirements.txt` | ✓ works | — |
| 3. First run (CLI) | `python main.py` | ✓ unchanged | — |
| 4. First run (Docker) | `docker run ...` | △ auto-refresh not advertised | README §Scheduled Regeneration |
| 5. Configure | env vars | ✗ `REGEN_*` undocumented | README env var table |
| 6. Integrate (cron POST) | `curl -X POST /regenerate` | △ 202 vs 200 contract change unannounced | README Upgrade Guide |
| 7. Observe | `/health` | ✗ new fields undocumented | README schema table |
| 8. Debug | logs + /health | △ no monitoring guidance | README §Monitoring & Debugging |
| 9. Upgrade | pull new version | ✗ silent breaking change | CHANGELOG + migration note |

---

## Prior Decision History (superseded)

- April 14 /autoplan: auth + retry + tests plan. Auth shipped, tests pass (39/39). Retry partial.
- April 16 /autoplan round 1: CEO dual voices flagged original plan as stale (auth shipped, tests pass). User reframed to async job queue + status polling.
- April 16 /autoplan round 2 (this run): CEO dual voices flagged job-queue plan as overbuilt. User reframed to Tier 1 only (scheduled regeneration + fire-and-forget). This plan.

Full prior audit trails in `/Users/rd/.gstack/projects/dautovri-cloudflare-topology/main-autoplan-restore-*.md`.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 2 (Apr 16, via /autoplan) | reframed twice | Round 2: 6/6 DISAGREE → user reframed to Tier 1 |
| Codex Review | `/codex review` | Independent 2nd opinion | 2 (Apr 16) | converged CEO both rounds; rate-limited for Eng+DX | Round 2 CEO: converged on "overbuilt; use TODOS.md:7"; Eng+DX `[subagent-only]` |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 (Apr 16, via /autoplan) | complete `[subagent-only]` | 9 findings: 2 CRITICAL (gunicorn multi-worker, tests missing), 3 MEDIUM (drift, atomic write, subprocess timeout), 3 LOW (TOCTOU, env validation), 1 minor |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | n/a | no UI scope |
| DX Review | `/plan-devex-review` | Developer experience gaps | 1 (Apr 16, via /autoplan) | complete `[subagent-only]` | 8 findings: 3 CRITICAL (env docs, 200→202 break, multi-worker), 2 HIGH (409 body, /health schema), 3 MEDIUM (debug UX, validation, atomic write docs) |

**VERDICT:** REFRAMED (round 2) + REVIEWED — Tier 1 plan (scheduled regen + fire-and-forget /regenerate) ships [TODOS.md](TODOS.md) line 7. Eng + DX findings integrated into Affected Files, Failure Modes Registry, and DX Review Outputs sections. Ready for implementation.
<!-- /autoplan restore point: /Users/rd/.gstack/projects/dautovri-cloudflare-topology/main-autoplan-restore-20260416-213118.md -->
# Plan: Async /regenerate (job queue + status polling)

## Problem Statement

cloudflare-topology runs as a Dockerized Flask web server with real users hitting `/regenerate`. The current implementation in [server/server.py](server/server.py#L86-L172) is architecturally fragile in three ways:

1. **Synchronous blocking.** `/regenerate` calls `subprocess.run([...main.py], timeout=300)`. The HTTP connection is held open for up to 5 minutes. Any reverse proxy, load balancer, or browser will time out long before that. On large Cloudflare accounts, the 300s wall-clock cap silently drops the work.
2. **No concurrency control.** Two simultaneous `/regenerate` calls each spawn their own `main.py` subprocess. They race on `network_topology.html` (last writer wins, possibly partial). There's no idempotency, no deduplication, no "already in progress" response.
3. **No observability.** Caller gets one of two responses 5 minutes later: `success` or `failed`. No progress, no job ID, no way to cancel, no way to check status without re-triggering.

Auth is shipped (bearer token via `REGEN_AUTH_TOKEN`, validated with `hmac.compare_digest`). Tests pass (39/39). CI is in place. The next bet is fixing the architecture, not adding more guards on top of a synchronous endpoint.

## Premise (confirmed by user)

- Server-mode is the real deployment shape. Users hit `/regenerate` from clients that don't tolerate 5-minute requests.
- Async with status polling is the right pattern (vs SSE streaming or removing the endpoint).
- In-memory job state is acceptable scope for v1 (single-server deployment, no horizontal scaling). Persistence and Redis are explicit future work.

## Proposed Design

### 1. Job lifecycle

```
POST /regenerate          → 202 { "job_id": "...", "status": "queued" }
GET  /regenerate/{job_id} → 200 { "job_id": "...", "status": "running"|"success"|"failed",
                                  "started_at": "...", "finished_at": "...",
                                  "error": null|"...", "elapsed_s": N }
```

- New job ID generated per accepted request (uuid4 hex).
- If a regeneration is already running, second `/regenerate` returns `409 Conflict { "status": "already_running", "job_id": "..." }` with the in-flight job ID. Idempotency without a lock storm.
- Jobs run in a background thread (one worker; serial execution avoids the race condition entirely).
- Job results retained in an in-memory dict; LRU-evicted at >50 entries.

### 2. Status endpoint

- `GET /regenerate/{job_id}` requires the same bearer token as `POST /regenerate`. Status is operational data, not anonymous.
- 404 if job_id unknown.

### 3. Backwards compatibility

- `POST /regenerate` no longer blocks. Existing clients that ignored the response body get a 202 instead of 200/500 — most clients treat both as success, but document the change.
- Add `?wait=true` query param: if set, the server polls its own job and returns the final result synchronously (caps at 60s, then returns 202 with job_id). Preserves the old contract for scripts that depended on it.

### 4. /health update

- Include `current_job` field when a regeneration is running, so a load balancer probe can see liveness vs busy.

## Affected Files

- [server/server.py](server/server.py) — extract `generate_topology()` into a worker, add `JobRunner` class, new routes
- [tests/test_server.py](tests/test_server.py) — **new file** — covers POST /regenerate (202), GET /regenerate/{id} (queued → running → success/failed), 409 conflict, 404 unknown job, auth on both endpoints, `?wait=true` happy path + timeout
- [README.md](README.md) — document the new request/response shape, deprecation note for the old synchronous behavior
- [tests/test_cloudflare_api.py](tests/test_cloudflare_api.py) — **new file** — covers `_make_request()` retry behavior (left over from prior plan, still missing)

## Out of Scope

- Persistent job storage (Redis, SQLite). In-memory only for v1.
- Horizontal scaling / multi-worker support. Single Flask process.
- WebSocket or SSE progress streaming. Polling only.
- Caching/TTL for topology data. Separate plan if/when needed.
- Cancellation API (`DELETE /regenerate/{job_id}`). Future.
- Rate limiting on /regenerate. The 409-on-already-running provides the practical guard.
- Frontend changes to `network_topology.html`.
- Replacing `subprocess.run` with in-process `main()` call. Subprocess isolation is fine.

## What Already Exists

| Sub-problem | File | State |
|---|---|---|
| Bearer-token auth | [server/server.py](server/server.py#L152-L164) | ✅ shipped, reuse for status endpoint |
| `generate_topology()` worker | [server/server.py](server/server.py#L86-L111) | ✅ shipped, will become job body |
| Test infra | [tests/test_network_graph.py](tests/test_network_graph.py) | ✅ 39/39 pass, pattern to copy |
| CI | [.github/workflows/ci.yml](.github/workflows/ci.yml) | ✅ runs pytest on push |
| Custom error pages | [server/server.py](server/server.py) | ✅ 404/503 already styled, reuse |

## Error & Rescue Registry

| Error Scenario | Behavior | Rescue Path |
|---|---|---|
| Two clients POST /regenerate simultaneously | First wins (queued/running), second gets 409 with the in-flight `job_id` | Caller polls the returned job_id |
| Job worker crashes mid-run | Job marked `failed` with exception message, future POSTs accepted | Caller sees status=failed, can retry |
| `subprocess.run` times out (300s cap) | Job marked `failed` with reason="timeout" | Caller sees timeout reason in status |
| Client polls unknown `job_id` | 404 with `{ "error": "unknown job" }` | Caller re-POSTs to get a fresh job |
| Server restarts while job is running | In-memory state lost; client poll returns 404 | Document: "if 404 after restart, retry POST" |
| `?wait=true` exceeds 60s | Returns 202 with job_id (degrades to async) | Caller falls through to polling |

## Failure Modes Registry

| Mode | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Job dict grows unbounded | Medium (long-lived servers) | Memory leak | LRU cap at 50 entries |
| Worker thread dies silently | Low | Stuck in "running" state forever | Wrap worker in try/except/finally; finally always sets terminal status |
| Race on global job state | Low | Inconsistent status reads | `threading.Lock` around dict mutations |
| User polls too fast | Medium (no backoff guidance) | Server CPU waste | Document "poll every 5-10s" in README |
| Reverse proxy buffers POST response | Low | Client never sees 202 | Ensure response is small + content-length set |

## Open Questions

- Should the in-flight `job_id` returned by 409 be poll-able by clients without auth? (Recommendation: no, same auth as POST.)
- Logging: include `job_id` in every log line for that job? (Recommendation: yes, `extra={"job_id": ...}`.)

---

## Prior Decision History (superseded)

The April 14 /autoplan run approved a plan to (1) auth /regenerate, (2) add retry logic, (3) fix tests. Items (1) and (3) shipped. Item (2) was identified by the April 16 dual-voice CEO review as treating symptoms — the real fragility is the synchronous blocking design. The retry partial work in `services/cloudflare_api.py` can stay (defensive depth doesn't hurt), but it's no longer the strategic bet. This plan replaces the strategic bet with async /regenerate.

Full prior audit trail and CEO dual-voices analysis preserved in restore point: `/Users/rd/.gstack/projects/dautovri-cloudflare-topology/main-autoplan-restore-20260416-213118.md`.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 (April 16, via /autoplan) | reframed | 6/6 dimensions DISAGREE-WITH-PLAN → user accepted reframe |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 (April 16) | converged with subagent | 8 findings, all aligned with subagent |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 0 | — | — (pending on reframed plan) |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | n/a | no UI scope |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — (pending on reframed plan) |

**VERDICT:** REFRAMED — original plan re-reviewed and found misframed. New plan above captures the strategic bet (async /regenerate). Run `/autoplan` again (or `/plan-eng-review` + `/plan-devex-review` individually) to complete the pipeline on the reframed plan.

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale |
|---|-------|----------|----------------|-----------|-----------|
| 1 | CEO | Escalate scope disagreement to user (not auto-decide) | User Challenge | N/A | Both models disagreed with user's prior direction (async job queue); user chose reframe to Tier 1 |
| 2 | CEO | Accept reframe direction A (Tier 1 only) | User decision | N/A | User input at gate |
| 3 | Eng | Use threading.Lock (not Event/RLock) | Mechanical | P5 | Standard mutual exclusion primitive |
| 4 | Eng | Add drift-accurate _next_scheduled_at tracking | Auto | P1 | Required for /health accuracy |
| 5 | Eng | Add explicit _regen_in_progress bool flag (vs lock.locked()) | Auto | P5 | Atomic GIL read, avoids TOCTOU on /health |
| 6 | Eng | Detect gunicorn/uwsgi multi-worker + refuse to schedule | Auto | P2 | CRITICAL finding; blast radius covers deployment safety |
| 7 | Eng | Atomic write via tempfile + os.replace() in main.py | Auto | P1 | Prevents truncation on subprocess SIGKILL |
| 8 | Eng | Validate REGEN_INTERVAL_SECONDS (non-int, negative) | Auto | P5 | Explicit over clever; ~5 lines |
| 9 | Eng | Add 16 tests in new tests/test_server.py | Auto | P1 | Test plan artifact on disk |
| 10 | Eng | Keep subprocess.run timeout=300 (no retry logic) | Auto | P3 | Orphaned partial retry in cloudflare_api.py stays; no new action |
| 11 | DX | Extend 409 body with hint + Retry-After header | Auto | P5 | Generic clients handle Retry-After; hint points to /health |
| 12 | DX | Document /health schema in README | Auto | P1 | Enables monitoring integrations |
| 13 | DX | Add Upgrade Guide v0.1→v0.2 to README | Auto | P1 | 200→202 contract break needs explicit call-out |
| 14 | DX | Document REGEN_AUTH_TOKEN (currently shipped but undocumented) | Auto | P2 | In blast radius of this plan touching /regenerate |
| 15 | DX | Thread name "topology-scheduler" | Auto | P5 | Legible stack dumps, trivial cost |
| 16 | DX | Startup logging at INFO level for scheduler + auth state | Auto | P5 | Operator debugging UX |
