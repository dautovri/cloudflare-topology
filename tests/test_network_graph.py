"""Tests for network graph builder."""

import pytest
from unittest.mock import MagicMock

from services.network_graph import NetworkGraphBuilder, NodeMetadata, EdgeMetadata
from models.cloudflare_data import (
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
    CloudflareTopology,
)
from config import NodeColors, NodeShapes


class TestNetworkGraphBuilder:
    """Tests for NetworkGraphBuilder."""

    @pytest.fixture
    def empty_topology(self):
        """Create an empty topology for testing."""
        return CloudflareTopology()

    @pytest.fixture
    def sample_topology(self):
        """Create a sample topology with various resources."""
        tunnel = Tunnel(
            id="tunnel-1",
            name="prod-tunnel",
            status="healthy",
            connections=[
                TunnelConnection(
                    id="conn-1",
                    colo_name="DFW",
                    is_pending_reconnect=False,
                    origin_ip="192.168.1.1",
                )
            ],
            config=TunnelConfig(
                ingress=[
                    {"hostname": "dashboard.example.com", "service": "http://localhost:8080"},
                    {"service": "http_status:404"},
                ],
            ),
        )

        policy = AccessPolicy(
            id="policy-1",
            name="Allow Engineers",
            decision="allow",
            precedence=1,
            include=[PolicyRule(rule_type="group", value={"id": "group-1"})],
        )

        app = AccessApplication(
            id="app-1",
            name="Dashboard",
            domain="dashboard.example.com",
            app_type="self_hosted",
            policies=[policy],
            allowed_idps=["idp-1"],
        )

        group = AccessGroup(
            id="group-1",
            name="Engineering",
            include=[PolicyRule(rule_type="email_domain", value={"domain": "eng.example.com"})],
        )

        vnet = VirtualNetwork(
            id="vnet-1",
            name="Production",
            is_default=True,
        )

        route = Route(
            id="route-1",
            network="10.0.0.0/8",
            tunnel_id="tunnel-1",
            virtual_network_id="vnet-1",
        )

        idp = IdentityProvider(
            id="idp-1",
            name="Okta",
            idp_type="okta",
        )

        return CloudflareTopology(
            tunnels=[tunnel],
            applications=[app],
            policies=[],
            groups=[group],
            virtual_networks=[vnet],
            routes=[route],
            identity_providers=[idp],
        )

    def test_build_empty_graph(self, empty_topology):
        """Test building a graph from empty topology."""
        builder = NetworkGraphBuilder()
        builder.build(empty_topology)

        assert len(builder.nodes) == 0
        assert len(builder.edges) == 0

    def test_build_graph_with_data(self, sample_topology):
        """Test building a graph with sample data."""
        builder = NetworkGraphBuilder()
        builder.build(sample_topology)

        # Should have nodes for each resource type
        # tunnel, app, policy, group, vnet, route, idp = 7
        assert len(builder.nodes) == 7
        assert len(builder.edges) > 0

    def test_node_colors(self, sample_topology):
        """Test that nodes have correct colors based on type."""
        builder = NetworkGraphBuilder()
        builder.build(sample_topology)

        # Check that tunnel node exists and has a status-based color
        tunnel_node = builder.nodes.get("tunnel:tunnel-1")
        assert tunnel_node is not None
        assert tunnel_node.node_type == "tunnel"

        # Check application node uses APPLICATION color
        app_node = builder.nodes.get("app:app-1")
        assert app_node is not None
        assert app_node.color == NodeColors.APPLICATION

    def test_edge_creation(self, sample_topology):
        """Test that edges are created between related resources."""
        builder = NetworkGraphBuilder()
        builder.build(sample_topology)

        # Expected edges:
        # tunnel→app (hostname match), app→policy, policy→group, app→idp,
        # route→tunnel, route→vnet
        edge_pairs = [(e.source, e.target) for e in builder.edges]

        assert ("tunnel:tunnel-1", "app:app-1") in edge_pairs
        assert ("app:app-1", "policy:policy-1") in edge_pairs
        assert ("route:route-1", "tunnel:tunnel-1") in edge_pairs
        assert ("route:route-1", "vnet:vnet-1") in edge_pairs
        assert ("app:app-1", "idp:idp-1") in edge_pairs


class TestNodeMetadata:
    """Tests for NodeMetadata dataclass."""

    def test_node_metadata_defaults(self):
        """Test NodeMetadata with required values."""
        meta = NodeMetadata(
            node_id="test-id",
            node_type="tunnel",
            label="Test Node",
            color=NodeColors.TUNNEL,
            shape=NodeShapes.TUNNEL,
            size=30,
            title="Test tooltip",
        )

        assert meta.node_id == "test-id"
        assert meta.node_type == "tunnel"
        assert meta.label == "Test Node"
        assert meta.color == NodeColors.TUNNEL
        assert meta.shape == NodeShapes.TUNNEL
        assert meta.size == 30
        assert meta.properties == {}

    def test_node_metadata_custom(self):
        """Test NodeMetadata with custom values."""
        meta = NodeMetadata(
            node_id="custom-id",
            node_type="application",
            label="Custom",
            color="#ff0000",
            shape="box",
            size=50,
            title="Custom tooltip",
            properties={"group": "custom-group"},
        )

        assert meta.shape == "box"
        assert meta.size == 50
        assert meta.properties["group"] == "custom-group"


class TestEdgeMetadata:
    """Tests for EdgeMetadata dataclass."""

    def test_edge_metadata_defaults(self):
        """Test EdgeMetadata with default values."""
        edge = EdgeMetadata(
            source="node-1",
            target="node-2",
        )

        assert edge.source == "node-1"
        assert edge.target == "node-2"
        assert edge.label is None
        assert edge.title is None
        assert edge.dashes is False

    def test_edge_metadata_custom(self):
        """Test EdgeMetadata with custom values."""
        edge = EdgeMetadata(
            source="node-1",
            target="node-2",
            label="connects",
            title="Connection info",
            color="#888888",
            width=2,
            dashes=True,
        )

        assert edge.label == "connects"
        assert edge.dashes is True
        assert edge.width == 2
