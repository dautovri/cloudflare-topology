"""Tests for data models."""

import pytest
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


class TestTunnel:
    """Tests for Tunnel model."""

    def test_tunnel_minimal(self):
        """Test creating a Tunnel with minimal fields."""
        tunnel = Tunnel(
            id="tunnel-123",
            name="test-tunnel",
            status="healthy",
        )

        assert tunnel.id == "tunnel-123"
        assert tunnel.name == "test-tunnel"
        assert tunnel.status == "healthy"
        assert tunnel.created_at is None
        assert tunnel.connections == []

    def test_tunnel_full(self):
        """Test creating a Tunnel with all fields."""
        conn = TunnelConnection(
            id="conn-1",
            colo_name="DFW",
            is_pending_reconnect=False,
            origin_ip="192.168.1.1",
            opened_at="2024-01-15T10:05:00Z",
        )
        tunnel = Tunnel(
            id="tunnel-456",
            name="production-tunnel",
            status="healthy",
            created_at="2024-01-15T10:00:00Z",
            deleted_at=None,
            connections=[conn],
        )

        assert tunnel.id == "tunnel-456"
        assert tunnel.name == "production-tunnel"
        assert tunnel.created_at == "2024-01-15T10:00:00Z"
        assert len(tunnel.connections) == 1
        assert tunnel.connections[0].colo_name == "DFW"
        assert tunnel.connections[0].origin_ip == "192.168.1.1"
        assert tunnel.is_healthy is True
        assert tunnel.connector_count == 1


class TestAccessApplication:
    """Tests for AccessApplication model."""

    def test_access_application(self):
        """Test creating an AccessApplication."""
        app = AccessApplication(
            id="app-123",
            name="Internal Dashboard",
            domain="dashboard.example.com",
            app_type="self_hosted",
            session_duration="24h",
            allowed_idps=["idp-1", "idp-2"],
            auto_redirect_to_identity=True,
            created_at="2024-01-10T08:00:00Z",
        )

        assert app.id == "app-123"
        assert app.name == "Internal Dashboard"
        assert app.domain == "dashboard.example.com"
        assert app.app_type == "self_hosted"
        assert app.session_duration == "24h"
        assert len(app.allowed_idps) == 2
        assert app.auto_redirect_to_identity is True


class TestAccessPolicy:
    """Tests for AccessPolicy model."""

    def test_access_policy(self):
        """Test creating an AccessPolicy with rules."""
        include_rules = [
            PolicyRule.from_dict({"group": {"id": "group-1"}}),
            PolicyRule.from_dict({"email": {"email": "admin@example.com"}}),
        ]
        exclude_rules = [
            PolicyRule.from_dict({"ip": {"ip": "192.168.1.0/24"}}),
        ]
        policy = AccessPolicy(
            id="policy-123",
            name="Allow Engineering",
            decision="allow",
            precedence=1,
            include=include_rules,
            exclude=exclude_rules,
        )

        assert policy.id == "policy-123"
        assert policy.name == "Allow Engineering"
        assert policy.decision == "allow"
        assert policy.precedence == 1
        assert len(policy.include) == 2
        assert len(policy.exclude) == 1


class TestAccessGroup:
    """Tests for AccessGroup model."""

    def test_access_group(self):
        """Test creating an AccessGroup."""
        include_rules = [
            PolicyRule.from_dict({"email_domain": {"domain": "engineering.example.com"}}),
        ]
        group = AccessGroup(
            id="group-123",
            name="Engineering Team",
            include=include_rules,
            created_at="2024-01-05T12:00:00Z",
        )

        assert group.id == "group-123"
        assert group.name == "Engineering Team"
        assert len(group.include) == 1


class TestDevice:
    """Tests for Device model."""

    def test_device(self):
        """Test creating a Device."""
        device = Device(
            id="device-123",
            name="MacBook Pro",
            user_email="user@example.com",
            user_id="user-1",
            last_seen="2024-01-20T15:30:00Z",
            os_version="14.2",
        )

        assert device.id == "device-123"
        assert device.name == "MacBook Pro"
        assert device.user_email == "user@example.com"
        assert device.user_id == "user-1"
        assert device.os_version == "14.2"


class TestVirtualNetwork:
    """Tests for VirtualNetwork model."""

    def test_virtual_network(self):
        """Test creating a VirtualNetwork."""
        vnet = VirtualNetwork(
            id="vnet-123",
            name="Production Network",
            comment="Production environment",
            is_default_network=True,
            created_at="2024-01-01T00:00:00Z",
        )

        assert vnet.id == "vnet-123"
        assert vnet.name == "Production Network"
        assert vnet.is_default_network is True


class TestRoute:
    """Tests for Route model."""

    def test_route(self):
        """Test creating a Route."""
        route = Route(
            id="route-123",
            network="10.0.0.0/8",
            tunnel_id="tunnel-456",
            tunnel_name="prod-tunnel",
            virtual_network_id="vnet-789",
            comment="Internal network route",
            created_at="2024-01-10T09:00:00Z",
        )

        assert route.id == "route-123"
        assert route.network == "10.0.0.0/8"
        assert route.tunnel_id == "tunnel-456"
        assert route.virtual_network_id == "vnet-789"


class TestCloudflareTopology:
    """Tests for CloudflareTopology model."""

    def test_empty_topology(self):
        """Test creating an empty topology."""
        topology = CloudflareTopology()

        assert topology.tunnels == []
        assert topology.applications == []
        assert topology.policies == []
        assert topology.groups == []
        assert topology.devices == []
        assert topology.virtual_networks == []
        assert topology.routes == []
        assert topology.identity_providers == []
        assert topology.gateway_rules == []

    def test_topology_with_data(self):
        """Test topology with actual data."""
        tunnel = Tunnel(
            id="tunnel-1",
            name="test-tunnel",
            status="healthy",
        )
        app = AccessApplication(
            id="app-1",
            name="Test App",
            domain="app.example.com",
            app_type="self_hosted",
        )

        topology = CloudflareTopology(
            tunnels=[tunnel],
            applications=[app],
        )

        assert len(topology.tunnels) == 1
        assert len(topology.applications) == 1
        assert topology.tunnels[0].name == "test-tunnel"
        assert topology.applications[0].domain == "app.example.com"
        assert topology.total_resources == 2
