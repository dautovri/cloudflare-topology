<!-- /autoplan restore point: /Users/rd/.gstack/projects/dautovri-cloudflare-topology/main-autoplan-restore-20260414-211220.md -->
# Plan: Harden Server, Add Retry Logic, Fix Test Suite

## Problem Statement

cloudflare-topology is a Cloudflare Zero Trust network topology mapper. It fetches data
from the Cloudflare API, builds a graph, and renders an interactive HTML visualization.
It can run as a CLI tool or as a Docker-deployed Flask web server.

Three issues need fixing before this is production-ready:

### 1. Security: Unauthenticated /regenerate endpoint

`server/server.py` exposes a POST `/regenerate` endpoint with zero authentication.
Anyone who can reach the server can trigger topology regeneration, which:
- Hammers the Cloudflare API with the stored token
- Could be used for DoS via repeated regeneration requests
- Exposes the server to abuse in any network environment

**Fix:** Add a simple bearer token authentication to the `/regenerate` endpoint using
an environment variable (`REGENERATE_TOKEN`). Return 401 if missing or wrong.

### 2. Reliability: No retry logic for API calls

`services/cloudflare_api.py` has basic rate limiting but no retry logic. If a single
API call times out or returns a transient 5xx error, the entire topology fetch fails.
For accounts with many tunnels/apps, this is common.

**Fix:** Add exponential backoff retry (3 attempts) for transient failures (timeouts,
429, 500, 502, 503, 504). Use the existing `requests` library, no new dependencies.

### 3. Tests: Broken fixtures and missing coverage

`tests/test_network_graph.py` has fixtures that don't match model constructors:
- `PolicyRule(type=...)` should be `PolicyRule(rule_type=...)`  
- `AccessApplication(type=...)` should be `AccessApplication(app_type=...)`
- `NetworkGraphBuilder` constructor doesn't match actual implementation

Also missing: tests for the retry logic (once added), error paths in API client,
and server endpoint tests.

**Fix:** Fix existing test fixtures to match actual model APIs. Add tests for retry
logic, error paths, and server endpoints.

## Affected Files

- `server/server.py` — add auth to /regenerate
- `services/cloudflare_api.py` — add retry logic
- `tests/test_network_graph.py` — fix broken fixtures
- `tests/test_cloudflare_api.py` — new file for API client tests
- `tests/test_server.py` — new file for server endpoint tests

## Out of Scope

- Caching/TTL for topology data (future improvement)
- JSON export mode (future improvement)
- CI/CD pipeline setup
- Frontend visualization changes
- Multi-account support
- Structured logging with request IDs

## What Already Exists

| Sub-problem | Existing file | What's there |
|---|---|---|
| HTTP server | server/server.py | Flask routes, /regenerate endpoint |
| API requests | services/cloudflare_api.py | `_make_request()`, rate limiting |
| Rate limiting | services/cloudflare_api.py | `_rate_limit()` with sleep |
| Test structure | tests/test_network_graph.py | Fixtures, basic assertions |
| Data models | models/cloudflare_data.py | Dataclasses for all CF resources |

## Error & Rescue Registry

| Error Scenario | Current Behavior | After Plan | Rescue Path |
|---|---|---|---|
| Attacker hits /regenerate | Unlimited regeneration | Token-protected | 401 response |
| API timeout on tunnel fetch | Whole job fails | 3x retry | Exponential backoff |
| Bad test fixtures | Tests crash | Tests pass | CI catches regressions |
| Rate limit (429) | Job fails | Retry after backoff | Respects Retry-After header |

## Failure Modes Registry

| Mode | Likelihood | Impact | Mitigation |
|---|---|---|---|
| REGENERATE_TOKEN env var not set | Medium | /regenerate returns 500 | Require at startup or disable endpoint |
| Retry masks auth failures | Low | Silent 401 loops | Only retry on specific codes (429, 5xx) |
| Tests pass locally, fail in CI | Low | False confidence | Add CI (deferred, flagged) |

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|---------------|-----------|-----------|----------|
| 1 | CEO | Fix all three issues (A) vs partial | Mechanical | P1+P2 | Complete fix covers security+reliability+tests | Option B (security only), Option C (retry only) |
| 2 | CEO | Add rate-limit guard on /regenerate | Mechanical | P2 | In blast radius, <1 file, prevents abuse | — |
| 3 | CEO | Defer CI/CD to TODOS.md | Mechanical | P3 | Outside blast radius | Include CI in this plan |
| 4 | CEO | Accept auth-on-/regenerate premise | Mechanical | P6 | Open endpoint is wrong regardless of usage | Remove endpoint entirely (taste) |
| 5 | CEO | Accept retry-logic premise | Mechanical | P6 | Standard HTTP client practice | Caching instead (taste) |
| 6 | CEO | Add retry logging | Mechanical | P1 | Completeness: retries should be visible | — |
| 7 | ENG | Fix `isinstance` dead branch in main.py:155 | Mechanical | P5 | Dead code from model refactor, explicit > clever | — |
| 8 | ENG | Set backoff base to 0.5s (not 1.0s) | Mechanical | P3 | Pragmatic: keeps worst-case per request at 3.5s | 1.0s base |
| 9 | ENG | Add warning log for empty first page in _paginate | Mechanical | P1 | Completeness: silent empty responses should be logged | — |
| 10 | ENG | All test gaps covered (new test files) | Mechanical | P1 | Every new codepath needs a test | Defer tests |
| 11 | DX | Improve error messages in _make_request | Mechanical | P1+P2 | In blast radius, costs 10 lines, actionable errors | Leave bare messages |
| 12 | DX | Defer CLI flag consistency | Mechanical | P3 | Outside blast radius | Fix --include-gateway now |
| 13 | DX | Defer .env support | Mechanical | P3 | Outside blast radius | Add python-dotenv now |
| 14 | DX | Defer programmatic API | Mechanical | P3 | Outside blast radius, new architecture | Add __init__.py now |
| 15 | DX | Defer troubleshooting docs | Mechanical | P3 | Outside blast radius | Add README section now |

## Cross-Phase Themes

**Error message quality** — flagged in CEO (Finding 3: retry masks issues), Eng (Finding 3.2: silent empty responses), DX (Finding 3: bare messages, no cause/fix/link). High-confidence signal across all three review phases. In-scope fix: improve error messages in `_make_request()` since we're already modifying that method for retry logic.

## Final Gate: Auto-Approved

- **Taste Decision 1:** Auth `/regenerate` (not remove). Rationale: preserves container-restart-free regeneration capability.
- **Taste Decision 2:** Retry logic (not caching/TTL). Rationale: simpler implementation, directly solves the failure mode.
- **Auto-decided:** 13 mechanical decisions (see audit trail above).
- **User challenges:** 0 (user unavailable, autonomous mode).
- **Review scores:** CEO clean, Eng clean, DX 5/10 (in-scope items addressed, rest deferred to TODOS.md).
- **Status:** APPROVED — ready for implementation.
