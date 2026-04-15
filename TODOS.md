# TODOS

## Security & Reliability
- [x] Auth on /regenerate endpoint — Fixed by /qa on main, 2026-04-15 (ISSUE-004)
- [x] Security headers (CSP, X-Frame-Options, X-Content-Type-Options) — Fixed by /qa on main, 2026-04-15 (ISSUE-005)
- [ ] Add caching/TTL for topology data (15 min TTL, regenerate in background)
- [ ] Atomic file writes for OUTPUT_FILE (write to temp, rename on success)
- [ ] Add CI/CD pipeline (.github/workflows/test.yml with pytest + mypy)
- [ ] Server version disclosure: Werkzeug still leaks version in dev mode (ISSUE-006, deferred/low)

## Features
- [ ] JSON export mode (enable Terraform/Ansible/compliance integrations)
- [ ] Multi-account support (aggregate multiple CF accounts)
- [ ] Config file support (--config topology.json)

## DX Improvements
- [ ] Add .env.example and python-dotenv support
- [ ] Standardize CLI flags (--include-gateway → --no-gateway for consistency)
- [ ] Add troubleshooting section to README
- [ ] Add performance guidance in docs (large accounts, timeout tips)
- [ ] Programmatic API: export classes from __init__.py for library use
- [ ] Config extensibility: CLI overrides for physics, colors, node sizes
- [ ] Structured logging with request IDs

## Code Quality
- [ ] Remove dead isinstance branch in main.py:155
