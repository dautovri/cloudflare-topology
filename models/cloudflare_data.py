"""
Data models for Cloudflare Zero Trust resources.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class TunnelConnection:
    """Represents a cloudflared connector connection."""
    id: str
    colo_name: str
    is_pending_reconnect: bool
    client_id: Optional[str] = None
    client_version: Optional[str] = None
    opened_at: Optional[str] = None
    origin_ip: Optional[str] = None


@dataclass
class TunnelConfig:
    """Tunnel ingress configuration."""
    ingress: List[Dict[str, Any]] = field(default_factory=list)
    warp_routing: Optional[Dict[str, Any]] = None
    origin_request: Optional[Dict[str, Any]] = None


@dataclass
class Tunnel:
    """Represents a Cloudflare Tunnel."""
    id: str
    name: str
    status: str  # healthy, degraded, inactive, down
    created_at: Optional[str] = None
    deleted_at: Optional[str] = None
    connections: List[TunnelConnection] = field(default_factory=list)
    config: Optional[TunnelConfig] = None
    account_tag: Optional[str] = None
    tun_type: Optional[str] = None  # cfd_tunnel, warp_connector
    remote_config: bool = False
    
    @property
    def is_healthy(self) -> bool:
        return self.status == "healthy"
    
    @property
    def connector_count(self) -> int:
        return len(self.connections)
    
    @property
    def hostnames(self) -> List[str]:
        """Extract hostnames from ingress config."""
        if not self.config or not self.config.ingress:
            return []
        return [
            rule.get("hostname", "")
            for rule in self.config.ingress
            if rule.get("hostname")
        ]


@dataclass
class PolicyRule:
    """A rule within an access policy (include/exclude/require)."""
    rule_type: str  # email, email_domain, group, everyone, ip, country, etc.
    value: Any
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyRule":
        """Parse a rule from API response."""
        # Rules come in format like {"email": {"email": "user@example.com"}}
        for rule_type, value in data.items():
            return cls(rule_type=rule_type, value=value)
        return cls(rule_type="unknown", value=data)


@dataclass
class AccessPolicy:
    """Represents an Access policy."""
    id: str
    name: str
    decision: str  # allow, deny, non_identity, bypass
    precedence: int = 0
    include: List[PolicyRule] = field(default_factory=list)
    exclude: List[PolicyRule] = field(default_factory=list)
    require: List[PolicyRule] = field(default_factory=list)
    isolation_required: bool = False
    purpose_justification_required: bool = False
    session_duration: Optional[str] = None
    approval_required: bool = False
    approval_groups: List[Dict[str, Any]] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    # For app-specific policies
    app_id: Optional[str] = None
    
    # For reusable policies
    app_count: int = 0


@dataclass
class AccessApplication:
    """Represents an Access application."""
    id: str
    name: str
    domain: str
    app_type: str  # self_hosted, saas, ssh, vnc, browser_isolation, etc.
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    # Application settings
    session_duration: Optional[str] = None
    allowed_idps: List[str] = field(default_factory=list)
    auto_redirect_to_identity: bool = False
    enable_binding_cookie: bool = False
    http_only_cookie_attribute: bool = True
    same_site_cookie_attribute: Optional[str] = None
    logo_url: Optional[str] = None
    skip_interstitial: bool = False
    app_launcher_visible: bool = True
    
    # Policies attached to this app
    policies: List[AccessPolicy] = field(default_factory=list)
    
    # For self-hosted apps
    custom_deny_message: Optional[str] = None
    custom_deny_url: Optional[str] = None
    
    # Additional domains
    self_hosted_domains: List[str] = field(default_factory=list)
    
    @property
    def all_domains(self) -> List[str]:
        """Get all domains including self-hosted domains."""
        domains = [self.domain] if self.domain else []
        domains.extend(self.self_hosted_domains)
        return list(set(domains))


@dataclass
class AccessGroup:
    """Represents an Access group."""
    id: str
    name: str
    include: List[PolicyRule] = field(default_factory=list)
    exclude: List[PolicyRule] = field(default_factory=list)
    require: List[PolicyRule] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    @property
    def member_count(self) -> int:
        """Estimate member count from include rules."""
        count = 0
        for rule in self.include:
            if rule.rule_type == "email":
                count += 1
            elif rule.rule_type == "email_list":
                # Can't determine exact count without fetching list
                count += 1
            elif rule.rule_type == "everyone":
                return -1  # Indicates "everyone"
        return count


@dataclass
class Device:
    """Represents a WARP device."""
    id: str
    name: Optional[str] = None
    device_type: Optional[str] = None  # windows, mac, linux, ios, android
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    os_version: Optional[str] = None
    serial_number: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_seen: Optional[str] = None
    
    # User association
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    
    # Registration info
    active_registrations: int = 0
    revoked_at: Optional[str] = None


@dataclass
class VirtualNetwork:
    """Represents a virtual network (vnet)."""
    id: str
    name: str
    comment: Optional[str] = None
    is_default: bool = False
    is_default_network: bool = False
    created_at: Optional[str] = None
    deleted_at: Optional[str] = None


@dataclass
class Route:
    """Represents a private network route."""
    id: str
    network: str  # CIDR notation
    tunnel_id: Optional[str] = None
    tunnel_name: Optional[str] = None
    virtual_network_id: Optional[str] = None
    comment: Optional[str] = None
    created_at: Optional[str] = None
    deleted_at: Optional[str] = None


@dataclass
class IdentityProvider:
    """Represents an identity provider (IdP)."""
    id: str
    name: str
    idp_type: str  # azureAD, okta, google, github, saml, etc.
    config: Dict[str, Any] = field(default_factory=dict)
    
    # SCIM configuration
    scim_config: Optional[Dict[str, Any]] = None


@dataclass
class GatewayRule:
    """Represents a Gateway firewall rule."""
    id: str
    name: str
    action: str  # allow, block, isolate, etc.
    enabled: bool = True
    precedence: int = 0
    filters: List[str] = field(default_factory=list)
    traffic: str = ""  # dns, http, l4
    rule_settings: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass 
class CloudflareTopology:
    """Container for all Cloudflare Zero Trust topology data."""
    tunnels: List[Tunnel] = field(default_factory=list)
    applications: List[AccessApplication] = field(default_factory=list)
    policies: List[AccessPolicy] = field(default_factory=list)
    groups: List[AccessGroup] = field(default_factory=list)
    devices: List[Device] = field(default_factory=list)
    virtual_networks: List[VirtualNetwork] = field(default_factory=list)
    routes: List[Route] = field(default_factory=list)
    identity_providers: List[IdentityProvider] = field(default_factory=list)
    gateway_rules: List[GatewayRule] = field(default_factory=list)
    
    # Metadata
    account_id: Optional[str] = None
    fetched_at: Optional[str] = None
    
    @property
    def total_resources(self) -> int:
        """Total number of resources."""
        return (
            len(self.tunnels) +
            len(self.applications) +
            len(self.policies) +
            len(self.groups) +
            len(self.devices) +
            len(self.virtual_networks) +
            len(self.routes) +
            len(self.identity_providers) +
            len(self.gateway_rules)
        )
    
    def get_tunnel_by_id(self, tunnel_id: str) -> Optional[Tunnel]:
        """Find tunnel by ID."""
        for tunnel in self.tunnels:
            if tunnel.id == tunnel_id:
                return tunnel
        return None
    
    def get_app_by_id(self, app_id: str) -> Optional[AccessApplication]:
        """Find application by ID."""
        for app in self.applications:
            if app.id == app_id:
                return app
        return None
    
    def get_group_by_id(self, group_id: str) -> Optional[AccessGroup]:
        """Find group by ID."""
        for group in self.groups:
            if group.id == group_id:
                return group
        return None
    
    def get_vnet_by_id(self, vnet_id: str) -> Optional[VirtualNetwork]:
        """Find virtual network by ID."""
        for vnet in self.virtual_networks:
            if vnet.id == vnet_id:
                return vnet
        return None
