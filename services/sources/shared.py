"""
Shared parsing and orchestration helpers for topology sources.

A *source* turns Cloudflare Zero Trust data into ``CloudflareTopology``
models. Two transports exist:

- ``services.cloudflare_api.CloudflareAPIClient`` — direct REST calls
  (wrapped as ``RestZeroTrustSource``)
- ``services.sources.mcp.ZeroTrustMCPSource`` — the Cloudflare remote MCP
  server (``https://mcp.cloudflare.com/mcp``) via its code-mode
  ``search``/``execute`` tools

Both transports receive the same JSON documents from the Cloudflare API
(the MCP server proxies ``api.cloudflare.com`` on your behalf), so all
parsing lives here and is shared between them. That keeps the produced
models byte-identical regardless of transport.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Iterable, List, Optional

from models.cloudflare_data import (
    AccessApplication,
    AccessGroup,
    AccessPolicy,
    CloudflareTopology,
    Device,
    GatewayRule,
    IdentityProvider,
    PolicyRule,
    Route,
    Tunnel,
    TunnelConfig,
    TunnelConnection,
    VirtualNetwork,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Endpoint templates
# ---------------------------------------------------------------------------

def format_endpoint(account_id: str, template: str, **kwargs: Any) -> str:
    """Format an endpoint template, defaulting account_id from config."""
    kwargs.setdefault("account_id", account_id)
    return template.format(**kwargs)


# ---------------------------------------------------------------------------
# Parsers (input: raw Cloudflare API JSON, output: dataclass models)
# ---------------------------------------------------------------------------

def parse_tunnel_connections(connections_data: Iterable[Dict[str, Any]]) -> List[TunnelConnection]:
    """Parse connector connection objects from tunnel API payloads."""
    connections = []
    for conn_data in connections_data:
        if not isinstance(conn_data, dict):
            continue
        connections.append(TunnelConnection(
            id=str(conn_data.get("id", conn_data.get("uuid", "")) or ""),
            colo_name=str(conn_data.get("colo_name", "") or ""),
            is_pending_reconnect=conn_data.get("is_pending_reconnect", False),
            client_id=conn_data.get("client_id"),
            client_version=conn_data.get("client_version"),
            opened_at=conn_data.get("opened_at"),
            origin_ip=conn_data.get("origin_ip"),
        ))
    return connections


def parse_tunnel(data: Dict[str, Any]) -> Tunnel:
    """Parse tunnel data from an API response."""
    return Tunnel(
        id=data.get("id", ""),
        name=data.get("name", ""),
        status=data.get("status", "unknown"),
        created_at=data.get("created_at"),
        deleted_at=data.get("deleted_at"),
        connections=parse_tunnel_connections(data.get("connections", [])),
        account_tag=data.get("account_tag"),
        tun_type=data.get("tun_type"),
        remote_config=data.get("remote_config", False),
    )


def parse_tunnel_config(config_data: Optional[Dict[str, Any]]) -> TunnelConfig:
    """Parse a tunnel configuration object (the ``config`` member) into TunnelConfig."""
    config_data = config_data or {}
    raw_ingress = config_data.get("ingress", []) or []
    ingress = [rule for rule in raw_ingress if isinstance(rule, dict)]
    return TunnelConfig(
        ingress=ingress,
        warp_routing=config_data.get("warp-routing"),
        origin_request=config_data.get("originRequest"),
    )


def parse_application(data: Dict[str, Any]) -> AccessApplication:
    """Parse application data from an API response."""
    return AccessApplication(
        id=data.get("id", ""),
        name=data.get("name", ""),
        domain=data.get("domain", ""),
        app_type=data.get("type", "self_hosted"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        session_duration=data.get("session_duration"),
        allowed_idps=data.get("allowed_idps", []),
        auto_redirect_to_identity=data.get("auto_redirect_to_identity", False),
        enable_binding_cookie=data.get("enable_binding_cookie", False),
        http_only_cookie_attribute=data.get("http_only_cookie_attribute", True),
        same_site_cookie_attribute=data.get("same_site_cookie_attribute"),
        logo_url=data.get("logo_url"),
        skip_interstitial=data.get("skip_interstitial", False),
        app_launcher_visible=data.get("app_launcher_visible", True),
        custom_deny_message=data.get("custom_deny_message"),
        custom_deny_url=data.get("custom_deny_url"),
        self_hosted_domains=data.get("self_hosted_domains", []),
    )


def parse_policy(data: Dict[str, Any]) -> AccessPolicy:
    """Parse policy data from an API response."""
    return AccessPolicy(
        id=data.get("id", ""),
        name=data.get("name", ""),
        decision=data.get("decision", "allow"),
        precedence=data.get("precedence", 0),
        include=[PolicyRule.from_dict(r) for r in data.get("include", []) if isinstance(r, dict)],
        exclude=[PolicyRule.from_dict(r) for r in data.get("exclude", []) if isinstance(r, dict)],
        require=[PolicyRule.from_dict(r) for r in data.get("require", []) if isinstance(r, dict)],
        isolation_required=data.get("isolation_required", False),
        purpose_justification_required=data.get("purpose_justification_required", False),
        session_duration=data.get("session_duration"),
        approval_required=data.get("approval_required", False),
        approval_groups=data.get("approval_groups", []),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        app_count=data.get("app_count", 0),
    )


def parse_group(data: Dict[str, Any]) -> AccessGroup:
    """Parse group data from an API response."""
    return AccessGroup(
        id=data.get("id", ""),
        name=data.get("name", ""),
        include=[PolicyRule.from_dict(r) for r in data.get("include", []) if isinstance(r, dict)],
        exclude=[PolicyRule.from_dict(r) for r in data.get("exclude", []) if isinstance(r, dict)],
        require=[PolicyRule.from_dict(r) for r in data.get("require", []) if isinstance(r, dict)],
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def parse_identity_provider(data: Dict[str, Any]) -> IdentityProvider:
    """Parse identity provider data from an API response."""
    return IdentityProvider(
        id=data.get("id", ""),
        name=data.get("name", ""),
        idp_type=data.get("type", ""),
        config=data.get("config", {}),
        scim_config=data.get("scim_config"),
    )


def parse_device(data: Dict[str, Any]) -> Device:
    """Parse WARP device data from an API response."""
    user = data.get("user") if data.get("user") else None
    return Device(
        id=data.get("id", ""),
        name=data.get("name"),
        device_type=data.get("device_type"),
        manufacturer=data.get("manufacturer"),
        model=data.get("model"),
        os_version=data.get("os_version"),
        serial_number=data.get("serial_number"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        last_seen=data.get("last_seen"),
        user_id=user.get("id") if user else None,
        user_email=user.get("email") if user else None,
        user_name=user.get("name") if user else None,
        active_registrations=data.get("active_registrations", 0),
        revoked_at=data.get("revoked_at"),
    )


def parse_virtual_network(data: Dict[str, Any]) -> VirtualNetwork:
    """Parse virtual network data from an API response."""
    return VirtualNetwork(
        id=data.get("id", ""),
        name=data.get("name", ""),
        comment=data.get("comment"),
        is_default=data.get("is_default", False),
        is_default_network=data.get("is_default_network", False),
        created_at=data.get("created_at"),
        deleted_at=data.get("deleted_at"),
    )


def parse_route(data: Dict[str, Any]) -> Route:
    """Parse private network route data from an API response."""
    return Route(
        id=data.get("id", ""),
        network=data.get("network", ""),
        tunnel_id=data.get("tunnel_id"),
        tunnel_name=data.get("tunnel_name"),
        virtual_network_id=data.get("virtual_network_id"),
        comment=data.get("comment"),
        created_at=data.get("created_at"),
        deleted_at=data.get("deleted_at"),
    )


def parse_gateway_rule(data: Dict[str, Any]) -> GatewayRule:
    """Parse Gateway firewall rule data from an API response."""
    return GatewayRule(
        id=data.get("id", ""),
        name=data.get("name", ""),
        action=data.get("action", ""),
        enabled=data.get("enabled", True),
        precedence=data.get("precedence", 0),
        filters=data.get("filters", []),
        traffic=data.get("traffic", ""),
        rule_settings=data.get("rule_settings", {}),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# Orchestration helpers (shared by every source's fetch_topology)
# ---------------------------------------------------------------------------

def run_parallel(func: Callable[[Any], Any], items: Iterable[Any], max_workers: int = 4) -> List[Any]:
    """Map func over items on a small thread pool. Returns the list of results."""
    materialized = list(items)
    if not materialized:
        return []
    workers = min(max_workers, len(materialized))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(func, materialized))


def try_fetch(name: str, fetcher: Callable[[], List[Any]]) -> List[Any]:
    """Call fetcher and return its result, returning [] on 403 permission errors."""
    # Imported lazily to avoid a cycle: cloudflare_api imports this module.
    from services.cloudflare_api import CloudflareAPIError

    try:
        return fetcher()
    except CloudflareAPIError as e:
        if e.status_code == 403:
            logger.warning(f"No permission to fetch {name} (HTTP 403) — skipping. "
                           f"Grant additional token permissions to include this resource.")
            return []
        raise


def build_topology(
    account_id: Optional[str],
    fetched_at: str,
    *,
    tunnels: Optional[List[Tunnel]] = None,
    applications: Optional[List[AccessApplication]] = None,
    policies: Optional[List[AccessPolicy]] = None,
    groups: Optional[List[AccessGroup]] = None,
    devices: Optional[List[Device]] = None,
    virtual_networks: Optional[List[VirtualNetwork]] = None,
    routes: Optional[List[Route]] = None,
    identity_providers: Optional[List[IdentityProvider]] = None,
    gateway_rules: Optional[List[GatewayRule]] = None,
) -> CloudflareTopology:
    """Assemble a CloudflareTopology from per-resource lists (None -> [])."""
    return CloudflareTopology(
        account_id=account_id,
        fetched_at=fetched_at,
        tunnels=tunnels or [],
        applications=applications or [],
        policies=policies or [],
        groups=groups or [],
        devices=devices or [],
        virtual_networks=virtual_networks or [],
        routes=routes or [],
        identity_providers=identity_providers or [],
        gateway_rules=gateway_rules or [],
    )
