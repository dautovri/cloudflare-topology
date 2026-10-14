"""
Topology data sources.

A source answers one question: "give me a fully populated CloudflareTopology".
Three transports ship with the project:

======================  ==========================================================
``rest`` (default)      ``RestZeroTrustSource`` -- direct ``api.cloudflare.com``
``mcp``                 ``ZeroTrustMCPSource`` -- Cloudflare's remote MCP server
                        at ``https://mcp.cloudflare.com/mcp`` (code mode)
``demo``                ``DemoSource`` -- synthetic data, no network at all
======================  ==========================================================

The MCP transport is still fully deterministic: we generate the sandbox
JavaScript ourselves and only ever run a fixed set of ``codemode.request``
calls -- no LLM sits in the fetch path.

Concrete source modules are imported lazily by :func:`create_source` so that
``services.sources.shared`` can be imported from ``services.cloudflare_api``
without an import cycle.
"""

import os
from typing import TYPE_CHECKING, Optional

from models.cloudflare_data import CloudflareTopology

if TYPE_CHECKING:
    from config import Config

__all__ = [
    "TopologySource",
    "SOURCE_NAMES",
    "resolve_source_kind",
    "create_source",
]

SOURCE_NAMES = ("rest", "mcp", "demo")

try:
    from typing import Protocol, runtime_checkable

    @runtime_checkable
    class TopologySource(Protocol):
        """Anything that can produce a fully populated CloudflareTopology."""

        def fetch_topology(
            self,
            include_tunnel_configs: bool = True,
            include_app_policies: bool = True,
            include_devices: bool = True,
            include_gateway_rules: bool = False,
        ) -> CloudflareTopology:
            ...

except ImportError:  # pragma: no cover -- typing.Protocol missing on very old runtime
    TopologySource = object  # type: ignore[assignment, misc]


def resolve_source_kind(kind: Optional[str] = None, demo: bool = False) -> str:
    """Resolve which source to use from an explicit value, --demo, or env/defaults."""
    if kind:
        return kind.strip().lower()
    if demo:
        return "demo"
    return (os.environ.get("TOPOLOGY_SOURCE") or "rest").strip().lower()


def create_source(kind: str, config: Optional["Config"] = None) -> "TopologySource":
    """Build a topology source by name (``rest``, ``mcp``, or ``demo``).

    Args:
        kind: Transport name: ``rest``/``api``/``direct``, ``mcp``, or ``demo``.
        config: Application configuration (unused by ``demo``).

    Returns:
        An object satisfying :class:`TopologySource`.
    """
    name = (kind or "rest").strip().lower()

    if name == "demo":
        from services.sources.demo import DemoSource

        return DemoSource()

    if name in ("rest", "api", "direct"):
        if config is None:
            raise ValueError(f"Config is required for source {name!r}")
        from services.sources.rest import RestZeroTrustSource

        return RestZeroTrustSource(config)

    if name == "mcp":
        if config is None:
            raise ValueError(f"Config is required for source {name!r}")
        from services.sources.mcp import ZeroTrustMCPSource

        return ZeroTrustMCPSource(config)

    raise ValueError(
        f"Unknown data source {kind!r}. Pick one of: {', '.join(SOURCE_NAMES)}"
    )
