"""
Network graph builder for Cloudflare topology visualization.
"""

import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field

from config import NodeColors, NodeShapes
from models.cloudflare_data import (
    CloudflareTopology,
    Tunnel,
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


@dataclass
class NodeMetadata:
    """Metadata for a graph node, used for search and tooltips."""
    node_id: str
    node_type: str  # tunnel, application, policy, group, device, etc.
    label: str
    color: str
    shape: str
    size: int
    title: str  # HTML tooltip content
    
    # Searchable properties
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EdgeMetadata:
    """Metadata for a graph edge."""
    source: str
    target: str
    label: Optional[str] = None
    color: Optional[str] = None
    dashes: bool = False
    width: int = 1
    title: Optional[str] = None


class NetworkGraphBuilder:
    """Builds a network graph from Cloudflare topology data."""
    
    def __init__(self):
        self.nodes: Dict[str, NodeMetadata] = {}
        self.edges: List[EdgeMetadata] = []
        self._edge_set: Set[Tuple[str, str]] = set()  # For deduplication
    
    def _add_node(self, metadata: NodeMetadata) -> None:
        """Add a node to the graph."""
        if metadata.node_id not in self.nodes:
            self.nodes[metadata.node_id] = metadata
    
    def _add_edge(
        self,
        source: str,
        target: str,
        label: Optional[str] = None,
        color: Optional[str] = None,
        dashes: bool = False,
        width: int = 1,
        title: Optional[str] = None,
    ) -> None:
        """Add an edge to the graph, avoiding duplicates."""
        edge_key = (source, target)
        if edge_key not in self._edge_set:
            self._edge_set.add(edge_key)
            self.edges.append(EdgeMetadata(
                source=source,
                target=target,
                label=label,
                color=color,
                dashes=dashes,
                width=width,
                title=title,
            ))
    
    def _format_tooltip(self, title: str, items: Dict[str, Any]) -> str:
        """Format tooltip HTML content."""
        lines = [f"<b>{title}</b>"]
        for key, value in items.items():
            if value is not None and value != "" and value != []:
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value[:5])
                    if len(items.get(key, [])) > 5:
                        value += "..."
                elif isinstance(value, bool):
                    value = "Yes" if value else "No"
                lines.append(f"<br><b>{key}:</b> {value}")
        return "".join(lines)
    
    def _get_status_color(self, status: str) -> str:
        """Get color based on status."""
        status_colors = {
            "healthy": "#22c55e",
            "degraded": "#eab308",
            "inactive": "#6b7280",
            "down": "#ef4444",
        }
        return status_colors.get(status.lower(), "#6b7280")
    
    def _get_decision_color(self, decision: str) -> str:
        """Get color based on policy decision."""
        decision_colors = {
            "allow": NodeColors.ALLOW,
            "deny": NodeColors.DENY,
            "bypass": NodeColors.BYPASS,
            "non_identity": "#3b82f6",
        }
        return decision_colors.get(decision.lower(), NodeColors.POLICY)
    
    # -------------------------------------------------------------------------
    # Node Building Methods
    # -------------------------------------------------------------------------
    
    def _build_tunnel_nodes(self, tunnels: List[Tunnel]) -> None:
        """Build nodes for tunnels."""
        for tunnel in tunnels:
            # Build tooltip content
            tooltip_items = {
                "Status": tunnel.status.title(),
                "Type": tunnel.tun_type or "cfd_tunnel",
                "Connectors": tunnel.connector_count,
                "Remote Config": tunnel.remote_config,
                "Created": tunnel.created_at[:10] if tunnel.created_at else None,
            }
            
            # Add connector info
            if tunnel.connections:
                colos = [c.colo_name for c in tunnel.connections if c.colo_name]
                if colos:
                    tooltip_items["Connected Colos"] = colos
            
            # Add hostnames from config
            if tunnel.hostnames:
                tooltip_items["Hostnames"] = tunnel.hostnames[:5]
            
            node = NodeMetadata(
                node_id=f"tunnel:{tunnel.id}",
                node_type="tunnel",
                label=tunnel.name,
                color=self._get_status_color(tunnel.status),
                shape=NodeShapes.TUNNEL,
                size=30,
                title=self._format_tooltip(f"Tunnel: {tunnel.name}", tooltip_items),
                properties={
                    "name": tunnel.name,
                    "status": tunnel.status,
                    "type": tunnel.tun_type,
                    "hostnames": tunnel.hostnames,
                },
            )
            self._add_node(node)
    
    def _build_application_nodes(self, applications: List[AccessApplication]) -> None:
        """Build nodes for Access applications."""
        for app in applications:
            tooltip_items = {
                "Domain": app.domain,
                "Type": app.app_type,
                "Session Duration": app.session_duration,
                "App Launcher": app.app_launcher_visible,
                "Auto Redirect": app.auto_redirect_to_identity,
            }
            
            if app.self_hosted_domains:
                tooltip_items["Additional Domains"] = app.self_hosted_domains
            
            if app.policies:
                tooltip_items["Policies"] = len(app.policies)
            
            node = NodeMetadata(
                node_id=f"app:{app.id}",
                node_type="application",
                label=app.name,
                color=NodeColors.APPLICATION,
                shape=NodeShapes.APPLICATION,
                size=25,
                title=self._format_tooltip(f"Application: {app.name}", tooltip_items),
                properties={
                    "name": app.name,
                    "domain": app.domain,
                    "type": app.app_type,
                    "domains": app.all_domains,
                },
            )
            self._add_node(node)
    
    def _build_policy_nodes(self, policies: List[AccessPolicy], is_app_policy: bool = False) -> None:
        """Build nodes for Access policies."""
        for policy in policies:
            # Format include rules for tooltip
            include_summary = self._summarize_rules(policy.include)
            exclude_summary = self._summarize_rules(policy.exclude)
            require_summary = self._summarize_rules(policy.require)
            
            tooltip_items = {
                "Decision": policy.decision.upper(),
                "Precedence": policy.precedence,
                "Include": include_summary or "None",
                "Require": require_summary or "None",
                "Exclude": exclude_summary or "None",
                "Approval Required": policy.approval_required,
                "Isolation Required": policy.isolation_required,
            }
            
            if not is_app_policy and policy.app_count:
                tooltip_items["Used by Apps"] = policy.app_count
            
            node = NodeMetadata(
                node_id=f"policy:{policy.id}",
                node_type="policy",
                label=policy.name,
                color=self._get_decision_color(policy.decision),
                shape=NodeShapes.POLICY,
                size=20,
                title=self._format_tooltip(f"Policy: {policy.name}", tooltip_items),
                properties={
                    "name": policy.name,
                    "decision": policy.decision,
                    "include": include_summary,
                    "exclude": exclude_summary,
                    "require": require_summary,
                },
            )
            self._add_node(node)
    
    def _build_group_nodes(self, groups: List[AccessGroup]) -> None:
        """Build nodes for Access groups."""
        for group in groups:
            include_summary = self._summarize_rules(group.include)
            
            tooltip_items = {
                "Include": include_summary or "None",
                "Require": self._summarize_rules(group.require) or "None",
                "Exclude": self._summarize_rules(group.exclude) or "None",
            }
            
            node = NodeMetadata(
                node_id=f"group:{group.id}",
                node_type="group",
                label=group.name,
                color=NodeColors.GROUP,
                shape=NodeShapes.GROUP,
                size=20,
                title=self._format_tooltip(f"Group: {group.name}", tooltip_items),
                properties={
                    "name": group.name,
                    "members": include_summary,
                },
            )
            self._add_node(node)
    
    def _build_identity_provider_nodes(self, providers: List[IdentityProvider]) -> None:
        """Build nodes for identity providers."""
        for idp in providers:
            tooltip_items = {
                "Type": idp.idp_type,
                "SCIM Enabled": idp.scim_config is not None,
            }
            
            node = NodeMetadata(
                node_id=f"idp:{idp.id}",
                node_type="identity_provider",
                label=idp.name,
                color=NodeColors.IDENTITY_PROVIDER,
                shape=NodeShapes.IDENTITY_PROVIDER,
                size=25,
                title=self._format_tooltip(f"Identity Provider: {idp.name}", tooltip_items),
                properties={
                    "name": idp.name,
                    "type": idp.idp_type,
                },
            )
            self._add_node(node)
    
    def _build_device_nodes(self, devices: List[Device]) -> None:
        """Build nodes for WARP devices."""
        for device in devices:
            tooltip_items = {
                "Type": device.device_type,
                "Model": f"{device.manufacturer} {device.model}" if device.manufacturer else device.model,
                "OS": device.os_version,
                "User": device.user_email or device.user_name,
                "Last Seen": device.last_seen[:10] if device.last_seen else None,
                "Active Registrations": device.active_registrations,
            }
            
            display_name = device.name or device.model or f"Device {device.id[:8]}"
            
            node = NodeMetadata(
                node_id=f"device:{device.id}",
                node_type="device",
                label=display_name,
                color=NodeColors.DEVICE,
                shape=NodeShapes.DEVICE,
                size=15,
                title=self._format_tooltip(f"Device: {display_name}", tooltip_items),
                properties={
                    "name": display_name,
                    "type": device.device_type,
                    "user": device.user_email,
                },
            )
            self._add_node(node)
    
    def _build_virtual_network_nodes(self, vnets: List[VirtualNetwork]) -> None:
        """Build nodes for virtual networks."""
        for vnet in vnets:
            tooltip_items = {
                "Default": vnet.is_default or vnet.is_default_network,
                "Comment": vnet.comment,
            }
            
            node = NodeMetadata(
                node_id=f"vnet:{vnet.id}",
                node_type="virtual_network",
                label=vnet.name,
                color=NodeColors.VIRTUAL_NETWORK,
                shape=NodeShapes.VIRTUAL_NETWORK,
                size=22,
                title=self._format_tooltip(f"Virtual Network: {vnet.name}", tooltip_items),
                properties={
                    "name": vnet.name,
                    "default": vnet.is_default,
                },
            )
            self._add_node(node)
    
    def _build_route_nodes(self, routes: List[Route]) -> None:
        """Build nodes for private network routes."""
        for route in routes:
            tooltip_items = {
                "Network": route.network,
                "Tunnel": route.tunnel_name,
                "Comment": route.comment,
            }
            
            node = NodeMetadata(
                node_id=f"route:{route.id}",
                node_type="route",
                label=route.network,
                color=NodeColors.ROUTE,
                shape=NodeShapes.ROUTE,
                size=18,
                title=self._format_tooltip(f"Route: {route.network}", tooltip_items),
                properties={
                    "network": route.network,
                    "tunnel": route.tunnel_name,
                },
            )
            self._add_node(node)
    
    # -------------------------------------------------------------------------
    # Edge Building Methods
    # -------------------------------------------------------------------------
    
    def _build_tunnel_to_app_edges(
        self,
        tunnels: List[Tunnel],
        applications: List[AccessApplication],
    ) -> None:
        """Build edges from tunnels to applications based on hostnames."""
        # Create a map of domains to apps
        domain_to_app: Dict[str, AccessApplication] = {}
        for app in applications:
            for domain in app.all_domains:
                if domain:
                    domain_to_app[domain.lower()] = app
        
        # Connect tunnels to apps via hostnames
        for tunnel in tunnels:
            for hostname in tunnel.hostnames:
                hostname_lower = hostname.lower()
                if hostname_lower in domain_to_app:
                    app = domain_to_app[hostname_lower]
                    self._add_edge(
                        source=f"tunnel:{tunnel.id}",
                        target=f"app:{app.id}",
                        label="serves",
                        color="#6b7280",
                        width=2,
                    )
    
    def _build_app_to_policy_edges(self, applications: List[AccessApplication]) -> None:
        """Build edges from applications to their policies."""
        for app in applications:
            for policy in app.policies:
                edge_color = self._get_decision_color(policy.decision)
                self._add_edge(
                    source=f"app:{app.id}",
                    target=f"policy:{policy.id}",
                    label=policy.decision,
                    color=edge_color,
                    width=2,
                )
    
    def _build_policy_to_group_edges(
        self,
        policies: List[AccessPolicy],
        groups: List[AccessGroup],
    ) -> None:
        """Build edges from policies to groups they reference."""
        group_ids = {g.id for g in groups}
        
        for policy in policies:
            for rule in policy.include + policy.require:
                if rule.rule_type == "group":
                    group_value = rule.value
                    if isinstance(group_value, dict):
                        group_id = group_value.get("id", "")
                    else:
                        group_id = str(group_value)
                    
                    if group_id in group_ids:
                        self._add_edge(
                            source=f"policy:{policy.id}",
                            target=f"group:{group_id}",
                            label="includes",
                            color=NodeColors.GROUP,
                            dashes=True,
                        )
    
    def _build_app_to_idp_edges(
        self,
        applications: List[AccessApplication],
        providers: List[IdentityProvider],
    ) -> None:
        """Build edges from applications to identity providers."""
        idp_ids = {idp.id for idp in providers}
        
        for app in applications:
            for idp_id in app.allowed_idps:
                if idp_id in idp_ids:
                    self._add_edge(
                        source=f"app:{app.id}",
                        target=f"idp:{idp_id}",
                        label="authenticates",
                        color=NodeColors.IDENTITY_PROVIDER,
                        dashes=True,
                    )
    
    def _build_route_to_tunnel_edges(
        self,
        routes: List[Route],
        tunnels: List[Tunnel],
    ) -> None:
        """Build edges from routes to tunnels."""
        tunnel_ids = {t.id for t in tunnels}
        
        for route in routes:
            if route.tunnel_id and route.tunnel_id in tunnel_ids:
                self._add_edge(
                    source=f"route:{route.id}",
                    target=f"tunnel:{route.tunnel_id}",
                    label="via",
                    color=NodeColors.ROUTE,
                    width=2,
                )
    
    def _build_route_to_vnet_edges(
        self,
        routes: List[Route],
        vnets: List[VirtualNetwork],
    ) -> None:
        """Build edges from routes to virtual networks."""
        vnet_ids = {v.id for v in vnets}
        
        for route in routes:
            if route.virtual_network_id and route.virtual_network_id in vnet_ids:
                self._add_edge(
                    source=f"route:{route.id}",
                    target=f"vnet:{route.virtual_network_id}",
                    label="in",
                    color=NodeColors.VIRTUAL_NETWORK,
                    dashes=True,
                )
    
    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------
    
    def _summarize_rules(self, rules: List[PolicyRule]) -> str:
        """Create a summary string for policy rules."""
        if not rules:
            return ""
        
        summaries = []
        for rule in rules[:3]:  # Limit to first 3
            if rule.rule_type == "email":
                email = rule.value.get("email", "") if isinstance(rule.value, dict) else str(rule.value)
                summaries.append(f"email:{email}")
            elif rule.rule_type == "email_domain":
                domain = rule.value.get("domain", "") if isinstance(rule.value, dict) else str(rule.value)
                summaries.append(f"domain:{domain}")
            elif rule.rule_type == "group":
                group_id = rule.value.get("id", "") if isinstance(rule.value, dict) else str(rule.value)
                summaries.append(f"group:{group_id[:8]}...")
            elif rule.rule_type == "everyone":
                summaries.append("everyone")
            elif rule.rule_type == "ip":
                ip = rule.value.get("ip", "") if isinstance(rule.value, dict) else str(rule.value)
                summaries.append(f"ip:{ip}")
            elif rule.rule_type == "country":
                country = rule.value.get("country_code", "") if isinstance(rule.value, dict) else str(rule.value)
                summaries.append(f"country:{country}")
            else:
                summaries.append(rule.rule_type)
        
        result = ", ".join(summaries)
        if len(rules) > 3:
            result += f" (+{len(rules) - 3} more)"
        
        return result
    
    # -------------------------------------------------------------------------
    # Main Build Method
    # -------------------------------------------------------------------------
    
    def build(self, topology: CloudflareTopology) -> "NetworkGraphBuilder":
        """
        Build the complete network graph from topology data.
        
        Args:
            topology: CloudflareTopology containing all resources
        
        Returns:
            self for method chaining
        """
        logger.info("Building network graph...")
        
        # Build nodes
        self._build_tunnel_nodes(topology.tunnels)
        self._build_application_nodes(topology.applications)
        
        # Build policy nodes (both app-specific and reusable)
        for app in topology.applications:
            self._build_policy_nodes(app.policies, is_app_policy=True)
        self._build_policy_nodes(topology.policies, is_app_policy=False)
        
        self._build_group_nodes(topology.groups)
        self._build_identity_provider_nodes(topology.identity_providers)
        self._build_virtual_network_nodes(topology.virtual_networks)
        self._build_route_nodes(topology.routes)
        self._build_device_nodes(topology.devices)
        
        # Build edges
        self._build_tunnel_to_app_edges(topology.tunnels, topology.applications)
        self._build_app_to_policy_edges(topology.applications)
        
        # Collect all policies for edge building
        all_policies = list(topology.policies)
        for app in topology.applications:
            all_policies.extend(app.policies)
        
        self._build_policy_to_group_edges(all_policies, topology.groups)
        self._build_app_to_idp_edges(topology.applications, topology.identity_providers)
        self._build_route_to_tunnel_edges(topology.routes, topology.tunnels)
        self._build_route_to_vnet_edges(topology.routes, topology.virtual_networks)
        
        logger.info(f"Graph built: {len(self.nodes)} nodes, {len(self.edges)} edges")
        return self
    
    def get_node_list(self) -> List[NodeMetadata]:
        """Get all nodes as a list."""
        return list(self.nodes.values())
    
    def get_edge_list(self) -> List[EdgeMetadata]:
        """Get all edges as a list."""
        return self.edges
