"""
Cloudflare API client for fetching Zero Trust resources.
"""

import time
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

import requests

from config import Config, APIEndpoints, REQUEST_TIMEOUT, MAX_REQUESTS_PER_SECOND
from models.cloudflare_data import (
    CloudflareTopology,
    Tunnel,
    TunnelConnection,
    TunnelConfig,
    AccessApplication,
    AccessPolicy,
    PolicyRule,
    AccessGroup,
    Device,
    VirtualNetwork,
    Route,
    IdentityProvider,
    GatewayRule,
)

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
        self._last_request_time = 0.0
    
    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        min_interval = 1.0 / MAX_REQUESTS_PER_SECOND
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
            
            result = response.json()
            
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
        kwargs.setdefault("account_id", self.config.account_id)
        return template.format(**kwargs)
    
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
            
            return TunnelConfig(
                ingress=config_data.get("ingress", []),
                warp_routing=config_data.get("warp-routing"),
                origin_request=config_data.get("originRequest"),
            )
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
            
            connections = []
            for item in items:
                conn = TunnelConnection(
                    id=item.get("id", ""),
                    colo_name=item.get("colo_name", ""),
                    is_pending_reconnect=item.get("is_pending_reconnect", False),
                    client_id=item.get("client_id"),
                    client_version=item.get("client_version"),
                    opened_at=item.get("opened_at"),
                    origin_ip=item.get("origin_ip"),
                )
                connections.append(conn)
            
            return connections
        except CloudflareAPIError as e:
            logger.warning(f"Could not fetch connections for tunnel {tunnel_id}: {e}")
            return []
    
    def _parse_tunnel(self, data: Dict[str, Any]) -> Tunnel:
        """Parse tunnel data from API response."""
        connections = []
        for conn_data in data.get("connections", []):
            conn = TunnelConnection(
                id=conn_data.get("id", conn_data.get("uuid", "")),
                colo_name=conn_data.get("colo_name", ""),
                is_pending_reconnect=conn_data.get("is_pending_reconnect", False),
                client_id=conn_data.get("client_id"),
                client_version=conn_data.get("client_version"),
                opened_at=conn_data.get("opened_at"),
                origin_ip=conn_data.get("origin_ip"),
            )
            connections.append(conn)
        
        return Tunnel(
            id=data.get("id", ""),
            name=data.get("name", ""),
            status=data.get("status", "unknown"),
            created_at=data.get("created_at"),
            deleted_at=data.get("deleted_at"),
            connections=connections,
            account_tag=data.get("account_tag"),
            tun_type=data.get("tun_type"),
            remote_config=data.get("remote_config", False),
        )
    
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
        return AccessPolicy(
            id=data.get("id", ""),
            name=data.get("name", ""),
            decision=data.get("decision", "allow"),
            precedence=data.get("precedence", 0),
            include=[PolicyRule.from_dict(r) for r in data.get("include", [])],
            exclude=[PolicyRule.from_dict(r) for r in data.get("exclude", [])],
            require=[PolicyRule.from_dict(r) for r in data.get("require", [])],
            isolation_required=data.get("isolation_required", False),
            purpose_justification_required=data.get("purpose_justification_required", False),
            session_duration=data.get("session_duration"),
            approval_required=data.get("approval_required", False),
            approval_groups=data.get("approval_groups", []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            app_count=data.get("app_count", 0),
        )
    
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
        return AccessGroup(
            id=data.get("id", ""),
            name=data.get("name", ""),
            include=[PolicyRule.from_dict(r) for r in data.get("include", [])],
            exclude=[PolicyRule.from_dict(r) for r in data.get("exclude", [])],
            require=[PolicyRule.from_dict(r) for r in data.get("require", [])],
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
    
    # -------------------------------------------------------------------------
    # Identity Provider Methods
    # -------------------------------------------------------------------------
    
    def list_identity_providers(self) -> List[IdentityProvider]:
        """Fetch all identity providers."""
        endpoint = self._get_endpoint(APIEndpoints.LIST_IDENTITY_PROVIDERS)
        items = self._paginate(endpoint)
        
        providers = []
        for item in items:
            provider = IdentityProvider(
                id=item.get("id", ""),
                name=item.get("name", ""),
                idp_type=item.get("type", ""),
                config=item.get("config", {}),
                scim_config=item.get("scim_config"),
            )
            providers.append(provider)
        
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
            cursor = result_info.get("cursor")
            
            if not cursor:
                break
        
        return all_results
    
    def list_devices(self) -> List[Device]:
        """Fetch all WARP devices."""
        try:
            endpoint = self._get_endpoint(APIEndpoints.LIST_DEVICES)
            items = self._paginate_cursor(endpoint)
            
            devices = []
            for item in items:
                device = Device(
                    id=item.get("id", ""),
                    name=item.get("name"),
                    device_type=item.get("device_type"),
                    manufacturer=item.get("manufacturer"),
                    model=item.get("model"),
                    os_version=item.get("os_version"),
                    serial_number=item.get("serial_number"),
                    created_at=item.get("created_at"),
                    updated_at=item.get("updated_at"),
                    last_seen=item.get("last_seen"),
                    user_id=item.get("user", {}).get("id") if item.get("user") else None,
                    user_email=item.get("user", {}).get("email") if item.get("user") else None,
                    user_name=item.get("user", {}).get("name") if item.get("user") else None,
                    active_registrations=item.get("active_registrations", 0),
                    revoked_at=item.get("revoked_at"),
                )
                devices.append(device)
            
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
            
            vnets = []
            for item in items:
                vnet = VirtualNetwork(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    comment=item.get("comment"),
                    is_default=item.get("is_default", False),
                    is_default_network=item.get("is_default_network", False),
                    created_at=item.get("created_at"),
                    deleted_at=item.get("deleted_at"),
                )
                vnets.append(vnet)
            
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
            
            routes = []
            for item in items:
                route = Route(
                    id=item.get("id", ""),
                    network=item.get("network", ""),
                    tunnel_id=item.get("tunnel_id"),
                    tunnel_name=item.get("tunnel_name"),
                    virtual_network_id=item.get("virtual_network_id"),
                    comment=item.get("comment"),
                    created_at=item.get("created_at"),
                    deleted_at=item.get("deleted_at"),
                )
                routes.append(route)
            
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
            
            rules = []
            for item in items:
                rule = GatewayRule(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    action=item.get("action", ""),
                    enabled=item.get("enabled", True),
                    precedence=item.get("precedence", 0),
                    filters=item.get("filters", []),
                    traffic=item.get("traffic", ""),
                    rule_settings=item.get("rule_settings", {}),
                    created_at=item.get("created_at"),
                    updated_at=item.get("updated_at"),
                )
                rules.append(rule)
            
            logger.info(f"Fetched {len(rules)} gateway rules")
            return rules
        except CloudflareAPIError as e:
            logger.warning(f"Could not fetch gateway rules: {e}")
            return []
    
    # -------------------------------------------------------------------------
    # Full Topology Fetch
    # -------------------------------------------------------------------------
    
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
            fetched_at=datetime.utcnow().isoformat(),
        )
        
        # Fetch tunnels
        topology.tunnels = self.list_tunnels()
        
        # Fetch tunnel configs if requested
        if include_tunnel_configs:
            for tunnel in topology.tunnels:
                if tunnel.remote_config:
                    config = self.get_tunnel_config(tunnel.id)
                    if config:
                        tunnel.config = config
        
        # Fetch applications
        topology.applications = self.list_applications()
        
        # Fetch app policies if requested
        if include_app_policies:
            for app in topology.applications:
                app.policies = self.get_application_policies(app.id)
        
        # Fetch reusable policies
        topology.policies = self.list_policies()
        
        # Fetch groups
        topology.groups = self.list_groups()
        
        # Fetch identity providers
        topology.identity_providers = self.list_identity_providers()
        
        # Fetch networks
        topology.virtual_networks = self.list_virtual_networks()
        topology.routes = self.list_routes()
        
        # Fetch devices if requested
        if include_devices:
            topology.devices = self.list_devices()
        
        # Fetch gateway rules if requested
        if include_gateway_rules:
            topology.gateway_rules = self.list_gateway_rules()
        
        logger.info(f"Topology fetch complete. Total resources: {topology.total_resources}")
        return topology
