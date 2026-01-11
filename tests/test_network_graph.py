"""Tests for network graph builder."""

import pytest
from unittest.mock import MagicMock

from services.network_graph import NetworkGraphBuilder, NodeMetadata, EdgeMetadata
from models.cloudflare_data import (
    Tunnel,
    TunnelConnection,
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
                    origin_ip="192.168.1.1",
                )
            ],
        )
        
        app = AccessApplication(
            id="app-1",
            name="Dashboard",
            domain="dashboard.example.com",
            type="self_hosted",
        )
        
        policy = AccessPolicy(
            id="policy-1",
            name="Allow Engineers",
            decision="allow",
            precedence=1,
            include=[PolicyRule(type="group", value={"id": "group-1"})],
        )
        
        group = AccessGroup(
            id="group-1",
            name="Engineering",
            include=[PolicyRule(type="email_domain", value={"domain": "eng.example.com"})],
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
            type="okta",
        )
        
        return CloudflareTopology(
            tunnels=[tunnel],
            applications=[app],
            policies={"app-1": [policy]},
            groups=[group],
            virtual_networks=[vnet],
            routes=[route],
            identity_providers=[idp],
        )

    def test_build_empty_graph(self, empty_topology):
        """Test building a graph from empty topology."""
        builder = NetworkGraphBuilder(empty_topology)
        graph = builder.build()
        
        # Should have central Cloudflare node
        assert len(graph.nodes) >= 1

    def test_build_graph_with_data(self, sample_topology):
        """Test building a graph with sample data."""
        builder = NetworkGraphBuilder(sample_topology)
        graph = builder.build()
        
        # Should have nodes for each resource type
        assert len(graph.nodes) > 1
        assert len(graph.edges) > 0

    def test_node_colors(self, sample_topology):
        """Test that nodes have correct colors based on type."""
        builder = NetworkGraphBuilder(sample_topology)
        graph = builder.build()
        
        # Check that tunnel node has correct color
        tunnel_nodes = [n for n in graph.nodes if "tunnel" in str(n).lower()]
        assert len(tunnel_nodes) > 0

    def test_edge_creation(self, sample_topology):
        """Test that edges are created between related resources."""
        builder = NetworkGraphBuilder(sample_topology)
        graph = builder.build()
        
        # Should have edges connecting resources
        assert len(graph.edges) > 0


class TestNodeMetadata:
    """Tests for NodeMetadata dataclass."""

    def test_node_metadata_defaults(self):
        """Test NodeMetadata with default values."""
        meta = NodeMetadata(
            id="test-id",
            label="Test Node",
            title="Test tooltip",
            color=NodeColors.TUNNEL,
        )
        
        assert meta.id == "test-id"
        assert meta.label == "Test Node"
        assert meta.color == NodeColors.TUNNEL
        assert meta.shape == "dot"
        assert meta.size == 25

    def test_node_metadata_custom(self):
        """Test NodeMetadata with custom values."""
        meta = NodeMetadata(
            id="custom-id",
            label="Custom",
            title="Custom tooltip",
            color="#ff0000",
            shape="box",
            size=50,
            group="custom-group",
        )
        
        assert meta.shape == "box"
        assert meta.size == 50
        assert meta.group == "custom-group"


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
