"""
Demo data source: synthetic Zero Trust topology, no network access at all.

Wraps :func:`services.demo_data.build_demo_topology` so the demo path is a
first-class source (usable via ``--source demo`` / ``--demo`` /
``TOPOLOGY_SOURCE=demo``) instead of a special case in ``main.py``.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from models.cloudflare_data import CloudflareTopology, GatewayRule

logger = logging.getLogger(__name__)


class DemoSource:
    """Topology source that returns a realistic but entirely fake topology."""

    def __init__(self, account_id: Optional[str] = None):
        self.account_id = account_id or "demo-account"

    def fetch_topology(
        self,
        include_tunnel_configs: bool = True,
        include_app_policies: bool = True,
        include_devices: bool = True,
        include_gateway_rules: bool = False,
    ) -> CloudflareTopology:
        """Return the synthetic topology (same flags as the real sources)."""
        from services.demo_data import build_demo_topology

        topology = build_demo_topology()
        topology.account_id = self.account_id
        topology.fetched_at = datetime.now(timezone.utc).isoformat()
        if not include_devices:
            topology.devices = []
        if include_gateway_rules and not topology.gateway_rules:
            topology.gateway_rules = [
                GatewayRule(
                    id="gw-demo-1",
                    name="Inspect Grafana HTTP Traffic",
                    action="allow",
                    enabled=True,
                    precedence=10,
                    filters=["http"],
                    traffic='http.request.host in {"grafana.acme.example.com"}',
                ),
                GatewayRule(
                    id="gw-demo-2",
                    name="Block Malware Domains",
                    action="block",
                    enabled=True,
                    precedence=20,
                    filters=["dns"],
                    traffic="any(dns.security_category[*] in {80 117})",
                ),
            ]
        return topology
