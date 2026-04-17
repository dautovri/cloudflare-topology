"""
Configuration and constants for Cloudflare Network Topology Mapper.
"""

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _read_wrangler_token() -> Optional[str]:
    """Read OAuth token from wrangler's config file (~/.wrangler/config/default.toml)."""
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomllib
        except ModuleNotFoundError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ModuleNotFoundError:
                return None

    candidates = [
        Path.home() / ".wrangler" / "config" / "default.toml",
        Path.home() / ".config" / ".wrangler" / "config" / "default.toml",
    ]
    for path in candidates:
        if path.is_file():
            try:
                data = tomllib.loads(path.read_text())
                token = data.get("oauth_token", "")
                if token:
                    logger.info(f"Using OAuth token from wrangler config ({path})")
                    return token
            except Exception:
                continue
    return None


@dataclass
class NodeColors:
    """Color scheme for different node types."""
    TUNNEL: str = "#3b82f6"       # Blue
    APPLICATION: str = "#22c55e"  # Green
    POLICY: str = "#eab308"       # Yellow
    GROUP: str = "#f97316"        # Orange
    DEVICE: str = "#ef4444"       # Red
    VIRTUAL_NETWORK: str = "#a855f7"  # Purple
    IDENTITY_PROVIDER: str = "#06b6d4"  # Cyan
    ROUTE: str = "#84cc16"        # Lime
    
    # Policy decision colors
    ALLOW: str = "#22c55e"  # Green
    DENY: str = "#ef4444"   # Red
    BYPASS: str = "#6b7280"  # Gray


@dataclass
class NodeShapes:
    """Shape scheme for different node types."""
    TUNNEL: str = "hexagon"
    APPLICATION: str = "dot"
    POLICY: str = "triangle"
    GROUP: str = "dot"
    DEVICE: str = "diamond"
    VIRTUAL_NETWORK: str = "square"
    IDENTITY_PROVIDER: str = "star"
    ROUTE: str = "dot"


@dataclass
class Config:
    """Application configuration."""
    
    # Cloudflare API settings
    api_token: str
    account_id: str = ""
    api_base_url: str = "https://api.cloudflare.com/client/v4"
    
    # Output settings
    output_file: str = "network_topology.html"
    
    # Debug mode
    debug: bool = False
    
    # Graph physics settings
    physics_enabled: bool = True
    physics_stabilization: bool = True
    
    # Node size settings
    node_size_tunnel: int = 30
    node_size_application: int = 25
    node_size_policy: int = 20
    node_size_group: int = 20
    node_size_device: int = 15
    node_size_default: int = 20
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables or wrangler OAuth token.

        Auth priority:
          1. CLOUDFLARE_API_TOKEN env var (explicit token)
          2. Wrangler OAuth token from ~/.wrangler/config/default.toml
        Account ID:
          - CLOUDFLARE_ACCOUNT_ID env var if set, otherwise auto-discovered later.
        """
        api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")

        if not api_token:
            api_token = _read_wrangler_token() or ""

        if not api_token:
            raise ValueError(
                "No Cloudflare credentials found. Either:\n"
                "  1. Run 'wrangler login' (easiest — browser OAuth, zero config)\n"
                "  2. Set CLOUDFLARE_API_TOKEN environment variable"
            )

        return cls(
            api_token=api_token,
            account_id=account_id,
            debug=os.environ.get("DEBUG", "").lower() in ("true", "1", "yes"),
            output_file=os.environ.get("OUTPUT_FILE", "network_topology.html"),
        )


# Cloudflare API endpoints (relative to base URL)
class APIEndpoints:
    """Cloudflare API endpoint templates."""
    
    # Tunnels
    LIST_TUNNELS = "/accounts/{account_id}/cfd_tunnel"
    GET_TUNNEL = "/accounts/{account_id}/cfd_tunnel/{tunnel_id}"
    GET_TUNNEL_CONNECTIONS = "/accounts/{account_id}/cfd_tunnel/{tunnel_id}/connections"
    GET_TUNNEL_CONFIG = "/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations"
    
    # Access Applications
    LIST_APPLICATIONS = "/accounts/{account_id}/access/apps"
    GET_APPLICATION = "/accounts/{account_id}/access/apps/{app_id}"
    LIST_APP_POLICIES = "/accounts/{account_id}/access/apps/{app_id}/policies"
    
    # Access Policies (reusable)
    LIST_POLICIES = "/accounts/{account_id}/access/policies"
    GET_POLICY = "/accounts/{account_id}/access/policies/{policy_id}"
    
    # Access Groups
    LIST_GROUPS = "/accounts/{account_id}/access/groups"
    GET_GROUP = "/accounts/{account_id}/access/groups/{group_id}"
    
    # Identity Providers
    LIST_IDENTITY_PROVIDERS = "/accounts/{account_id}/access/identity_providers"
    
    # Devices
    LIST_DEVICES = "/accounts/{account_id}/devices/physical-devices"
    LIST_DEVICE_POLICIES = "/accounts/{account_id}/devices/policies"
    
    # Networks
    LIST_VIRTUAL_NETWORKS = "/accounts/{account_id}/teamnet/virtual_networks"
    LIST_ROUTES = "/accounts/{account_id}/teamnet/routes"
    
    # Gateway
    LIST_GATEWAY_RULES = "/accounts/{account_id}/gateway/rules"
    LIST_GATEWAY_LOCATIONS = "/accounts/{account_id}/gateway/locations"
    
    # Users
    LIST_USERS = "/accounts/{account_id}/access/users"


# Valid node types for filtering
VALID_NODE_TYPES = [
    "tunnel",
    "application", 
    "policy",
    "group",
    "device",
    "virtual_network",
    "identity_provider",
    "route",
]

# Maximum file size for output (10MB)
MAX_OUTPUT_SIZE = 10 * 1024 * 1024

# Request timeout in seconds
REQUEST_TIMEOUT = 30

# Rate limiting: max requests per second
MAX_REQUESTS_PER_SECOND = 4
