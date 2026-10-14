"""
Cloudflare API client for fetching Zero Trust resources.
"""

import time
import logging
import threading
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from config import Config, APIEndpoints, REQUEST_TIMEOUT, MAX_REQUESTS_PER_SECOND
from models.cloudflare_data import (
    CloudflareTopology,
    Tunnel,
    TunnelConnection,
    TunnelConfig,
    AccessApplication,
    AccessPolicy,
    AccessGroup,
    Device,
    VirtualNetwork,
    Route,
    IdentityProvider,
    GatewayRule,
)
from services.sources import shared

logger = logging.getLogger(__name__)


class CloudflareAPIError(Exception):
    """Exception raised for Cloudflare API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, errors: Optional[List[Dict]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.errors = errors or []


class CloudflareAPIClient:
    """Client for interacting with Cloudflare Zero Trust API."""

    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {config.api_token}",
            "Content-Type": "application/json",
        })
        retry_strategy = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD", "OPTIONS"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self._last_request_time = 0.0
        self._rate_limit_lock = threading.Lock()

        if not self.config.account_id:
            self.config.account_id = self._discover_account_id()

    def _discover_account_id(self) -> str:
        """Auto-discover account ID from the API token."""
        logger.info("No account ID provided, discovering from token...")
        result = self._make_request("GET", "/accounts", params={"per_page": 1})
        accounts = result.get("result", [])
        if not accounts:
            raise CloudflareAPIError("No accounts found for this API token")
        account_id = str(accounts[0]["id"])
        if len(accounts) == 1 or result.get("result_info", {}).get("total_count", 1) == 1:
            logger.info(f"Discovered account: {accounts[0].get('name', account_id)} ({account_id})")
        else:
            total = result.get("result_info", {}).get("total_count", "multiple")
            logger.warning(
                f"Token has access to {total} accounts, using first: "
                f"{accounts[0].get('name', account_id)} ({account_id}). "
                f"Set CLOUDFLARE_ACCOUNT_ID to override."
            )
        return account_id

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests (thread-safe)."""
        min_interval = 1.0 / MAX_REQUESTS_PER_SECOND
        with self._rate_limit_lock:
            elapsed = time.time() - self._last_request_time
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self._last_request_time = time.time()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an API request with error handling."""
        self._rate_limit()

        url = f"{self.config.api_base_url}{endpoint}"

        if self.config.debug:
            logger.debug(f"API Request: {method} {url}")

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=REQUEST_TIMEOUT,
            )

            try:
                result = response.json()
            except ValueError:
                raise CloudflareAPIError(
                    f"API request failed with status {response.status_code}: {response.text[:200]}",
                    status_code=response.status_code,
                )

            if not isinstance(result, dict):
                raise CloudflareAPIError(
                    "API request returned unexpected non-dict JSON",
                    status_code=response.status_code,
                )

            if not result.get("success", False):
                errors = result.get("errors", [])
                error_messages = [e.get("message", "Unknown error") for e in errors]
                raise CloudflareAPIError(
                    f"API request failed: {', '.join(error_messages)}",
                    status_code=response.status_code,
                    errors=errors,
                )

            return result

        except requests.exceptions.Timeout:
            raise CloudflareAPIError(f"Request timeout for {endpoint}")
        except requests.exceptions.RequestException as e:
            raise CloudflareAPIError(f"Request failed: {str(e)}")

    def _paginate(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Paginate through all results."""
        all_results = []
        page = 1
        per_page = 100

        params = params or {}

        while True:
            params.update({"page": page, "per_page": per_page})
            result = self._make_request("GET", endpoint, params=params)

            items = result.get("result", [])
            if not items:
                break

            all_results.extend(items)

            # Check if there are more pages
            result_info = result.get("result_info", {})
            total_pages = result_info.get("total_pages", 1)

            if page >= total_pages:
                break

            page += 1

        return all_results

    def _get_endpoint(self, template: str, **kwargs) -> str:
        """Format an endpoint template with parameters."""
        return shared.format_endpoint(self.config.account_id, template, **kwargs)

    # -------------------------------------------------------------------------
    # Tunnel Methods
    # -------------------------------------------------------------------------

    def list_tunnels(self) -> List[Tunnel]:
        """Fetch all Cloudflare Tunnels."""
        endpoint = self._get_endpoint(APIEndpoints.LIST_TUNNELS)
        items = self._paginate(endpoint)

        tunnels = []
        for item in items:
            tunnel = self._parse_tunnel(item)
            tunnels.append(tunnel)

        logger.info(f"Fetched {len(tunnels)} tunnels")
        return tunnels

    def get_tunnel_config(self, tunnel_id: str) -> Optional[TunnelConfig]:
        """Fetch tunnel configuration."""
        try:
            endpoint = self._get_endpoint(
                APIEndpoints.GET_TUNNEL_CONFIG,
                tunnel_id=tunnel_id
            )
            result = self._make_request("GET", endpoint)
            config_data = result.get("result", {}).get("config", {})

            return shared.parse_tunnel_config(config_data)
        except CloudflareAPIError as e:
            logger.warning(f"Could not fetch config for tunnel {tunnel_id}: {e}")
            return None

    def get_tunnel_connections(self, tunnel_id: str) -> List[TunnelConnection]:
        """Fetch tunnel connector connections."""
        try:
            endpoint = self._get_endpoint(
                APIEndpoints.GET_TUNNEL_CONNECTIONS,
                tunnel_id=tunnel_id
            )
            result = self._make_request("GET", endpoint)
            items = result.get("result", [])

            return shared.parse_tunnel_connections(items)
        except CloudflareAPIError as e:
            logger.warning(f"Could not fetch connections for tunnel {tunnel_id}: {e}")
            return []

    def _parse_tunnel(self, data: Dict[str, Any]) -> Tunnel:
        """Parse tunnel data from API response."""
        return shared.parse_tunnel(data)

    # -------------------------------------------------------------------------
    # Access Application Methods
    # -------------------------------------------------------------------------

    def list_applications(self) -> List[AccessApplication]:
        """Fetch all Access applications."""
        endpoint = self._get_endpoint(APIEndpoints.LIST_APPLICATIONS)
        items = self._paginate(endpoint)

        applications = []
        for item in items:
            app = self._parse_application(item)
            applications.append(app)

        logger.info(f"Fetched {len(applications)} applications")
        return applications

    def get_application_policies(self, app_id: str) -> List[AccessPolicy]:
        """Fetch policies for a specific application."""
        try:
            endpoint = self._get_endpoint(
                APIEndpoints.LIST_APP_POLICIES,
                app_id=app_id
            )
            items = self._paginate(endpoint)

            policies = []
            for item in items:
                policy = self._parse_policy(item)
                policy.app_id = app_id
                policies.append(policy)

            return policies
        except CloudflareAPIError as e:
            logger.warning(f"Could not fetch policies for app {app_id}: {e}")
            return []

    def _parse_application(self, data: Dict[str, Any]) -> AccessApplication:
        """Parse application data from API response."""
        return shared.parse_application(data)

    # -------------------------------------------------------------------------
    # Access Policy Methods
    # -------------------------------------------------------------------------

    def list_policies(self) -> List[AccessPolicy]:
        """Fetch all reusable Access policies."""
        endpoint = self._get_endpoint(APIEndpoints.LIST_POLICIES)
        items = self._paginate(endpoint)

        policies = []
        for item in items:
            policy = self._parse_policy(item)
            policies.append(policy)

        logger.info(f"Fetched {len(policies)} reusable policies")
        return policies

    def _parse_policy(self, data: Dict[str, Any]) -> AccessPolicy:
        """Parse policy data from API response."""
        return shared.parse_policy(data)

    # -------------------------------------------------------------------------
    # Access Group Methods
    # -------------------------------------------------------------------------

    def list_groups(self) -> List[AccessGroup]:
        """Fetch all Access groups."""
        endpoint = self._get_endpoint(APIEndpoints.LIST_GROUPS)
        items = self._paginate(endpoint)

        groups = []
        for item in items:
            group = self._parse_group(item)
            groups.append(group)

        logger.info(f"Fetched {len(groups)} groups")
        return groups

    def _parse_group(self, data: Dict[str, Any]) -> AccessGroup:
        """Parse group data from API response."""
        return shared.parse_group(data)

    # -------------------------------------------------------------------------
    # Identity Provider Methods
    # -------------------------------------------------------------------------

    def list_identity_providers(self) -> List[IdentityProvider]:
        """Fetch all identity providers."""
        endpoint = self._get_endpoint(APIEndpoints.LIST_IDENTITY_PROVIDERS)
        items = self._paginate(endpoint)

        providers = [shared.parse_identity_provider(item) for item in items]

        logger.info(f"Fetched {len(providers)} identity providers")
        return providers

    # -------------------------------------------------------------------------
    # Device Methods
    # -------------------------------------------------------------------------

    def _paginate_cursor(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        per_page: int = 100,
    ) -> List[Dict[str, Any]]:
        """Paginate through all results using cursor-based pagination."""
        all_results = []
        cursor: Optional[str] = None

        params = params or {}
        params["per_page"] = per_page

        while True:
            if cursor:
                params["cursor"] = cursor

            result = self._make_request("GET", endpoint, params=params)

            items = result.get("result", [])
            if not items:
                break

            all_results.extend(items)

            # Check for next cursor
            result_info = result.get("result_info", {})
            cursors = result_info.get("cursors", {})
            cursor = cursors.get("after") if isinstance(cursors, dict) else None
            if not cursor:
                cursor = result_info.get("cursor")

            if not cursor:
                break

        return all_results

    def list_devices(self) -> List[Device]:
        """Fetch all WARP devices."""
        try:
            endpoint = self._get_endpoint(APIEndpoints.LIST_DEVICES)
            items = self._paginate_cursor(endpoint)

            devices = [shared.parse_device(item) for item in items]

            logger.info(f"Fetched {len(devices)} devices")
            return devices
        except CloudflareAPIError as e:
            logger.warning(f"Could not fetch devices: {e}")
            return []

    # -------------------------------------------------------------------------
    # Network Methods
    # -------------------------------------------------------------------------

    def list_virtual_networks(self) -> List[VirtualNetwork]:
        """Fetch all virtual networks."""
        try:
            endpoint = self._get_endpoint(APIEndpoints.LIST_VIRTUAL_NETWORKS)
            items = self._paginate(endpoint)

            vnets = [shared.parse_virtual_network(item) for item in items]

            logger.info(f"Fetched {len(vnets)} virtual networks")
            return vnets
        except CloudflareAPIError as e:
            logger.warning(f"Could not fetch virtual networks: {e}")
            return []

    def list_routes(self) -> List[Route]:
        """Fetch all private network routes."""
        try:
            endpoint = self._get_endpoint(APIEndpoints.LIST_ROUTES)
            items = self._paginate(endpoint)

            routes = [shared.parse_route(item) for item in items]

            logger.info(f"Fetched {len(routes)} routes")
            return routes
        except CloudflareAPIError as e:
            logger.warning(f"Could not fetch routes: {e}")
            return []

    # -------------------------------------------------------------------------
    # Gateway Methods
    # -------------------------------------------------------------------------

    def list_gateway_rules(self) -> List[GatewayRule]:
        """Fetch all Gateway firewall rules."""
        try:
            endpoint = self._get_endpoint(APIEndpoints.LIST_GATEWAY_RULES)
            result = self._make_request("GET", endpoint)
            items = result.get("result", [])

            rules = [shared.parse_gateway_rule(item) for item in items]

            logger.info(f"Fetched {len(rules)} gateway rules")
            return rules
        except CloudflareAPIError as e:
            logger.warning(f"Could not fetch gateway rules: {e}")
            return []

    # -------------------------------------------------------------------------
    # Full Topology Fetch
    # -------------------------------------------------------------------------

    def _try_fetch(self, name: str, fetcher):
        """Call fetcher and return its result, returning [] on 403 permission errors."""
        return shared.try_fetch(name, fetcher)

    def fetch_topology(
        self,
        include_tunnel_configs: bool = True,
        include_app_policies: bool = True,
        include_devices: bool = True,
        include_gateway_rules: bool = False,
    ) -> CloudflareTopology:
        """
        Fetch complete Zero Trust topology.

        Args:
            include_tunnel_configs: Fetch detailed tunnel configurations
            include_app_policies: Fetch policies for each application
            include_devices: Fetch WARP devices
            include_gateway_rules: Fetch Gateway firewall rules

        Returns:
            CloudflareTopology with all fetched data
        """
        logger.info("Starting topology fetch...")

        topology = CloudflareTopology(
            account_id=self.config.account_id,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

        # Fetch tunnels
        topology.tunnels = self._try_fetch("tunnels", self.list_tunnels)

        # Fetch tunnel configs concurrently if requested
        if include_tunnel_configs and topology.tunnels:
            tunnels_with_config = [t for t in topology.tunnels if t.remote_config]

            def _fetch_tunnel_config(t: Tunnel) -> None:
                cfg = self.get_tunnel_config(t.id)
                if cfg:
                    t.config = cfg

            shared.run_parallel(_fetch_tunnel_config, tunnels_with_config, max_workers=4)

        # Fetch applications
        topology.applications = self._try_fetch("applications", self.list_applications)

        # Fetch app policies concurrently if requested
        if include_app_policies and topology.applications:
            def _fetch_app_policies(app: AccessApplication) -> None:
                app.policies = self.get_application_policies(app.id)

            shared.run_parallel(_fetch_app_policies, topology.applications, max_workers=4)

        # Fetch reusable policies
        topology.policies = self._try_fetch("policies", self.list_policies)

        # Fetch groups
        topology.groups = self._try_fetch("groups", self.list_groups)

        # Fetch identity providers
        topology.identity_providers = self._try_fetch("identity_providers", self.list_identity_providers)

        # Fetch networks
        topology.virtual_networks = self._try_fetch("virtual_networks", self.list_virtual_networks)
        topology.routes = self._try_fetch("routes", self.list_routes)

        # Fetch devices if requested
        if include_devices:
            topology.devices = self._try_fetch("devices", self.list_devices)

        # Fetch gateway rules if requested
        if include_gateway_rules:
            topology.gateway_rules = self._try_fetch("gateway_rules", self.list_gateway_rules)

        logger.info(f"Topology fetch complete. Total resources: {topology.total_resources}")
        return topology
