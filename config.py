"""
Configuration and constants for Cloudflare Network Topology Mapper.
"""

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

__version__ = "0.3.0"

logger = logging.getLogger(__name__)


def _load_dotenv_if_present() -> None:
    """Load a .env file from the project root if present. No-op if missing.

    Runs once on import. Does not overwrite variables already set in the shell.
    """
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return
    # Project root (one level up from this file if inside a package, else cwd)
    here = Path(__file__).resolve().parent
    for candidate in (here / ".env", Path.cwd() / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            logger.debug(f"Loaded environment from {candidate}")
            return


_load_dotenv_if_present()


def _read_cloudflared_cert(home: Optional[Path] = None) -> Optional[str]:
    """Read API token (and default account ID) from ~/.cloudflared/cert.pem if present."""
    import base64
    import json
    import re

    base = home or Path.home()
    cert_path = base / ".cloudflared" / "cert.pem"
    if not cert_path.is_file():
        return None
    try:
        pem = cert_path.read_text(encoding="utf-8")
        match = re.search(
            r"-----BEGIN ARGO TUNNEL TOKEN-----\s*(.+?)\s*-----END ARGO TUNNEL TOKEN-----",
            pem,
            re.S,
        )
        if not match:
            return None
        payload = json.loads(base64.b64decode(match.group(1)).decode("utf-8"))
        token = payload.get("apiToken", "")
        account_id = payload.get("accountID", "")
        if token:
            if account_id and not os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
                os.environ["CLOUDFLARE_ACCOUNT_ID"] = str(account_id)
            logger.info(f"Using Cloudflare token from cloudflared origin cert ({cert_path})")
            return str(token)
    except Exception:
        return None
    return None


def _read_wrangler_token() -> Optional[str]:
    """Read OAuth token from wrangler's config file (or ~/.cloudflared/cert.pem fallback)."""
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

    home = Path.home()
    candidates = [
        home / ".wrangler" / "config" / "default.toml",
        home / ".config" / ".wrangler" / "config" / "default.toml",
        home / "Library" / "Preferences" / ".wrangler" / "config" / "default.toml",
    ]
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        candidates.append(Path(xdg_config) / ".wrangler" / "config" / "default.toml")

    expired_fallback: Optional[tuple[Path, str, str]] = None
    for path in candidates:
        if path.is_file():
            try:
                data = tomllib.loads(path.read_text())
                token = data.get("oauth_token", "")
                if token:
                    exp = data.get("expiration_time", "")
                    if exp:
                        try:
                            from datetime import datetime, timezone
                            exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
                            if exp_dt < datetime.now(timezone.utc):
                                expired_fallback = (path, str(token), str(exp))
                                continue
                        except ValueError:
                            pass
                    logger.info(f"Using OAuth token from wrangler config ({path})")
                    return str(token)
            except Exception:
                continue

    # If wrangler's token is missing or expired, check ~/.cloudflared/cert.pem
    cert_token = _read_cloudflared_cert(home)
    if cert_token:
        return cert_token

    if expired_fallback is not None:
        exp_path, exp_token, exp_str = expired_fallback
        logger.warning(
            f"Wrangler OAuth token at {exp_path} expired at {exp_str}; "
            f"run 'wrangler login' to refresh it."
        )
        return exp_token

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
    ROUTE: str = "#0d9488"        # Teal (deuteranopia-safe contrast vs Application)
    GATEWAY_RULE: str = "#ec4899"  # Pink

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
    GATEWAY_RULE: str = "triangle"


@dataclass
class Config:
    """Application configuration."""

    # Cloudflare API settings
    api_token: str
    account_id: str = ""
    account_ids: List[str] = field(default_factory=list)
    api_base_url: str = "https://api.cloudflare.com/client/v4"
    # Streamable HTTP endpoint of the Cloudflare remote MCP server
    # (used only by the `mcp` source; override with CLOUDFLARE_MCP_URL).
    mcp_url: str = "https://mcp.cloudflare.com/mcp"

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
    node_size_gateway_rule: int = 20
    node_size_default: int = 20

    @property
    def resolved_account_ids(self) -> List[str]:
        """Return deduplicated list of configured account IDs (empty if auto-discovered)."""
        raw: List[str] = []
        if self.account_ids:
            raw.extend(self.account_ids)
        if self.account_id:
            raw.extend(part.strip() for part in self.account_id.split(",") if part.strip())
        seen: List[str] = []
        for acc in raw:
            if acc and acc not in seen:
                seen.append(acc)
        return seen

    def apply_overrides(self, data: Dict[str, Any]) -> "Config":
        """Apply a dictionary of configuration overrides in-place and return self."""
        scalar_fields = (
            "api_token",
            "account_id",
            "api_base_url",
            "mcp_url",
            "output_file",
            "debug",
            "physics_enabled",
            "physics_stabilization",
            "node_size_tunnel",
            "node_size_application",
            "node_size_policy",
            "node_size_group",
            "node_size_device",
            "node_size_gateway_rule",
            "node_size_default",
        )
        for key in scalar_fields:
            if key in data and data[key] is not None:
                setattr(self, key, data[key])
        if "account_ids" in data and isinstance(data["account_ids"], list):
            self.account_ids = [str(a).strip() for a in data["account_ids"] if str(a).strip()]
            if self.account_ids and not self.account_id:
                self.account_id = self.account_ids[0]
        return self

    @classmethod
    def from_file(cls, path: Union[str, Path], require_auth: bool = True) -> "Config":
        """Load configuration from a JSON or TOML file, merged with environment variables."""
        file_path = Path(path)
        if not file_path.is_file():
            raise ValueError(f"Configuration file not found: {file_path}")
        raw_text = file_path.read_text(encoding="utf-8")
        if file_path.suffix.lower() == ".toml":
            import tomllib
            data = tomllib.loads(raw_text)
        else:
            data = json.loads(raw_text)
        if not isinstance(data, dict):
            raise ValueError(f"Configuration file {file_path} must contain a JSON/TOML object")

        if require_auth and not data.get("api_token"):
            cfg = cls.from_env()
        else:
            cfg = cls(api_token=str(data.get("api_token", "demo")))
        return cfg.apply_overrides(data)

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
            if not account_id:
                account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")

        if not api_token:
            raise ValueError(
                "No Cloudflare credentials found. Pick one:\n"
                "\n"
                "  1. wrangler login                  (easiest — browser OAuth)\n"
                "  2. python main.py --setup          (guided: creates .env for you)\n"
                "  3. cp .env.example .env            (then edit and fill in your token)\n"
                "  4. export CLOUDFLARE_API_TOKEN=... (one-off for this shell)\n"
                "  5. python main.py --demo           (skip auth, use synthetic data)\n"
                "\n"
                "Create a token with 'Zero Trust: Read' + 'Access: Apps and Policies: Read':\n"
                "  https://dash.cloudflare.com/profile/api-tokens"
            )

        return cls(
            api_token=api_token,
            account_id=account_id,
            debug=os.environ.get("DEBUG", "").lower() in ("true", "1", "yes"),
            output_file=os.environ.get("OUTPUT_FILE", "network_topology.html"),
            mcp_url=os.environ.get(
                "CLOUDFLARE_MCP_URL", "https://mcp.cloudflare.com/mcp",
            ),
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
    "gateway_rule",
]

# Maximum file size for output (10MB)
MAX_OUTPUT_SIZE = 10 * 1024 * 1024

# Request timeout in seconds
REQUEST_TIMEOUT = 30

# Rate limiting: max requests per second
MAX_REQUESTS_PER_SECOND = 4
