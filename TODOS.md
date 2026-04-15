# TODOS

## Security & Reliability
- [x] Auth on /regenerate endpoint — Fixed by /qa on main, 2026-04-15 (ISSUE-004)
- [x] Security headers (CSP, X-Frame-Options, X-Content-Type-Options) — Fixed by /qa on main, 2026-04-15 (ISSUE-005)
- [ ] Add caching/TTL for topology data (15 min TTL, regenerate in background)
- [ ] Atomic file writes for OUTPUT_FILE (write to temp, rename on success)
- [ ] Add CI/CD pipeline (.github/workflows/test.yml with pytest + mypy)
- [x] Server version disclosure: Server header fully stripped via custom WSGIRequestHandler — Fixed by /qa on main, 2026-04-15 (ISSUE-008, was ISSUE-006)

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
- [x] Remove dead isinstance branch in main.py node_counts — Fixed by /qa on main, 2026-04-15 (ISSUE-007)

## Design (from /design-review, 2026-04-15)
- [x] 503 error page was raw JSON — Fixed, styled dark theme error page (FINDING-001)
- [x] 404 page was Werkzeug default — Fixed, custom branded 404 (FINDING-002)
- [x] Search input missing aria-label — Fixed (FINDING-003)
- [x] Emoji read by screen readers — Fixed with aria-hidden (FINDING-004)
- [x] Clear/legend buttons missing aria-label — Fixed (FINDING-005)
- [x] Filter buttons missing aria-pressed — Fixed (FINDING-006)
- [x] Viewport 100vh should be 100dvh — Fixed (FINDING-007)
- [ ] Extract CSS colors into custom properties (FINDING-008, medium)
- [ ] Spacing design tokens instead of magic numbers (FINDING-009, medium)
- [ ] Add tablet responsive breakpoint (FINDING-010, medium)
- [ ] Use rem/em instead of px for font sizes (FINDING-011, medium)
- [ ] Extract CSS/JS from Python string literals to separate files (FINDING-012, medium)
- [ ] Color-blind safe legend (text labels alongside swatches) (FINDING-013, low)
- [ ] Differentiate APPLICATION vs ROUTE green hues for deuteranopia (FINDING-014, low)
