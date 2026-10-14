# TODOS

## Security & Reliability
- [x] Auth on /regenerate endpoint — Fixed by /qa on main, 2026-04-15 (ISSUE-004)
- [x] Security headers (CSP, X-Frame-Options, X-Content-Type-Options) — Fixed by /qa on main, 2026-04-15 (ISSUE-005)
- [x] CSP blocks vis-network/bootstrap CDN resources — Fixed by /qa on main, 2026-04-16 (QA2-ISSUE-001)
- [x] Add caching/TTL for topology data (15 min TTL, regenerate in background) — Shipped as scheduled regen in v0.2
- [x] Atomic file writes for OUTPUT_FILE (write to temp, rename on success) — Shipped in v0.2 (renderer uses tempfile + os.replace)
- [x] Add CI/CD pipeline (.github/workflows/ci.yml with pytest + flake8 + mypy)
- [x] Server version disclosure: Server header fully stripped via custom WSGIRequestHandler — Fixed by /qa on main, 2026-04-15 (ISSUE-008, was ISSUE-006)
- [x] HTML/XSS escaping in graph tooltips (`services/network_graph.py`) and search/inspector DOM (`services/assets/topology.js`) — Shipped in v0.3

## Features
- [x] Cloudflare MCP transport (`--source mcp` / `ZeroTrustMCPSource` over `https://mcp.cloudflare.com/mcp` Code Mode + `TopologySource` abstraction)
- [x] JSON export mode (`--export-json FILE`, `CloudflareTopology.to_dict()`, `NetworkGraphBuilder.to_dict()`, plus UI `J` JSON download)
- [x] Gateway rule graph nodes & domain-matching edges (`--include-gateway`)
- [x] Multi-account support (`--account-id` repeatable/comma-separated + `CloudflareTopology.merge()`)
- [x] Config file support (`--config topology.json` / `.toml` via `Config.from_file()`)

## DX Improvements
- [x] Add .env.example and python-dotenv support
- [x] Standardize CLI flags (`--no-gateway` alongside `--include-gateway`, `--no-physics`)
- [x] Add troubleshooting section to README
- [x] Add performance guidance in docs (large accounts, timeout tips)
- [x] Programmatic API: export classes from __init__.py for library use
- [x] Config extensibility: CLI & config file overrides for physics, node sizes, accounts
- [x] Structured logging with request IDs (`X-Request-Id` middleware in `server/server.py`)

## Code Quality
- [x] Remove dead isinstance branch in main.py node_counts — Fixed by /qa on main, 2026-04-15 (ISSUE-007)
- [x] lib/bindings/utils.js 404 via Flask — Fixed, added /lib/ route, /qa 2026-04-16 (QA2-ISSUE-002)
- [x] Unused Bootstrap in pyvis output — Fixed, stripped in renderer, /qa 2026-04-16 (QA2-ISSUE-003)
- [x] Zero flake8 & mypy issues across entire codebase; `.dockerignore` and slimmed Alpine `Dockerfile`; `!/lib/` un-ignored in `.gitignore` — Shipped in v0.3

## UX (from /qa, 2026-04-16)
- [x] Filter buttons do nothing without search text — Fixed in performSearch, /qa 2026-04-16 (QA2-ISSUE-004)
- [x] Duplicate stats panel overlapping header — Fixed, removed updateStats, /qa 2026-04-16 (QA2-ISSUE-005)
- [x] IdP node shows UUID instead of name — Formatted with IdP type prefix + shortened UUID (`_build_identity_provider_nodes`)
- [x] Connected Resources navigation in Inspector Drawer, Hierarchical Flow layout (`H`), Connected Only & Health quick filters, and clickable Legend items — Shipped in v0.3

## Design (from /design-review, 2026-04-15)
- [x] 503 error page was raw JSON — Fixed, styled dark theme error page (FINDING-001)
- [x] 404 page was Werkzeug default — Fixed, custom branded 404 (FINDING-002)
- [x] Search input missing aria-label — Fixed (FINDING-003)
- [x] Emoji read by screen readers — Fixed with aria-hidden (FINDING-004)
- [x] Clear/legend buttons missing aria-label — Fixed (FINDING-005)
- [x] Filter buttons missing aria-pressed — Fixed (FINDING-006)
- [x] Viewport 100vh should be 100dvh — Fixed (FINDING-007)
- [x] Extract CSS colors into custom properties (FINDING-008, medium)
- [x] Spacing design tokens instead of magic numbers (FINDING-009, medium)
- [x] Add tablet responsive breakpoint (FINDING-010, medium)
- [x] Use rem/em instead of px for font sizes (FINDING-011, medium)
- [x] Extract CSS/JS from Python string literals to separate files (FINDING-012, medium)
- [x] Color-blind safe legend (text labels alongside swatches) (FINDING-013, low)
- [x] Differentiate APPLICATION vs ROUTE green hues for deuteranopia (FINDING-014, low)
