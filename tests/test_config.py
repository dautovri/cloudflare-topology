"""Tests for configuration."""

import os
import pytest
from unittest.mock import patch
from config import Config, NodeColors, NodeShapes, APIEndpoints, _read_wrangler_token


class TestNodeColors:
    """Tests for NodeColors."""

    def test_color_values(self):
        """Test that all colors are valid hex values."""
        colors = [
            NodeColors.TUNNEL,
            NodeColors.APPLICATION,
            NodeColors.POLICY,
            NodeColors.GROUP,
            NodeColors.DEVICE,
            NodeColors.VIRTUAL_NETWORK,
            NodeColors.ROUTE,
            NodeColors.IDENTITY_PROVIDER,
            NodeColors.ALLOW,
            NodeColors.DENY,
            NodeColors.BYPASS,
        ]
        
        for color in colors:
            assert color.startswith("#")
            assert len(color) == 7
            # Validate hex characters
            int(color[1:], 16)


class TestNodeShapes:
    """Tests for NodeShapes."""

    def test_shape_values(self):
        """Test that shapes are valid vis.js shapes."""
        valid_shapes = {
            "dot", "square", "triangle", "triangleDown", "diamond",
            "star", "ellipse", "box", "database", "text", "image",
            "circularImage", "hexagon"
        }
        
        shapes = [
            NodeShapes.TUNNEL,
            NodeShapes.APPLICATION,
            NodeShapes.POLICY,
            NodeShapes.GROUP,
            NodeShapes.DEVICE,
            NodeShapes.VIRTUAL_NETWORK,
            NodeShapes.ROUTE,
            NodeShapes.IDENTITY_PROVIDER,
        ]
        
        for shape in shapes:
            assert shape in valid_shapes


class TestConfig:
    """Tests for Config."""

    def test_from_env_with_values(self, monkeypatch):
        """Test creating Config from environment variables."""
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token")
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-account")
        
        config = Config.from_env()
        
        assert config.api_token == "test-token"
        assert config.account_id == "test-account"
        assert config.api_base_url == "https://api.cloudflare.com/client/v4"

    def test_from_env_missing_token_and_no_wrangler(self, monkeypatch):
        """Test that missing API token with no wrangler config raises error."""
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
        monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
        
        with patch("config._read_wrangler_token", return_value=None):
            with pytest.raises(ValueError, match="No Cloudflare credentials found"):
                Config.from_env()

    def test_from_env_missing_account_id_is_ok(self, monkeypatch):
        """Test that missing account ID doesn't raise - it's auto-discovered later."""
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token")
        monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
        
        config = Config.from_env()
        assert config.api_token == "test-token"
        assert config.account_id == ""

    def test_from_env_falls_back_to_wrangler(self, monkeypatch):
        """Test that wrangler OAuth token is used when env var is missing."""
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
        monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)

        with patch("config._read_wrangler_token", return_value="wrangler-oauth-token"):
            config = Config.from_env()
            assert config.api_token == "wrangler-oauth-token"

    def test_env_token_takes_priority_over_wrangler(self, monkeypatch):
        """Test that CLOUDFLARE_API_TOKEN takes priority over wrangler."""
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "explicit-token")
        monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)

        with patch("config._read_wrangler_token", return_value="wrangler-oauth-token") as mock:
            config = Config.from_env()
            assert config.api_token == "explicit-token"
            mock.assert_not_called()


class TestAPIEndpoints:
    """Tests for APIEndpoints."""

    def test_tunnels_endpoint(self):
        """Test tunnels endpoint generation."""
        endpoint = APIEndpoints.LIST_TUNNELS.format(account_id="acc-123")
        assert endpoint == "/accounts/acc-123/cfd_tunnel"

    def test_tunnel_detail_endpoint(self):
        """Test tunnel detail endpoint generation."""
        endpoint = APIEndpoints.GET_TUNNEL.format(account_id="acc-123", tunnel_id="tun-456")
        assert endpoint == "/accounts/acc-123/cfd_tunnel/tun-456"

    def test_applications_endpoint(self):
        """Test applications endpoint generation."""
        endpoint = APIEndpoints.LIST_APPLICATIONS.format(account_id="acc-123")
        assert endpoint == "/accounts/acc-123/access/apps"

    def test_policies_endpoint(self):
        """Test policies endpoint generation."""
        endpoint = APIEndpoints.LIST_APP_POLICIES.format(account_id="acc-123", app_id="app-789")
        assert endpoint == "/accounts/acc-123/access/apps/app-789/policies"

    def test_groups_endpoint(self):
        """Test groups endpoint generation."""
        endpoint = APIEndpoints.LIST_GROUPS.format(account_id="acc-123")
        assert endpoint == "/accounts/acc-123/access/groups"

    def test_identity_providers_endpoint(self):
        """Test identity providers endpoint generation."""
        endpoint = APIEndpoints.LIST_IDENTITY_PROVIDERS.format(account_id="acc-123")
        assert endpoint == "/accounts/acc-123/access/identity_providers"

    def test_devices_endpoint(self):
        """Test devices endpoint generation."""
        endpoint = APIEndpoints.LIST_DEVICES.format(account_id="acc-123")
        assert endpoint == "/accounts/acc-123/devices/physical-devices"

    def test_virtual_networks_endpoint(self):
        """Test virtual networks endpoint generation."""
        endpoint = APIEndpoints.LIST_VIRTUAL_NETWORKS.format(account_id="acc-123")
        assert endpoint == "/accounts/acc-123/teamnet/virtual_networks"

    def test_routes_endpoint(self):
        """Test routes endpoint generation."""
        endpoint = APIEndpoints.LIST_ROUTES.format(account_id="acc-123")
        assert endpoint == "/accounts/acc-123/teamnet/routes"

    def test_gateway_rules_endpoint(self):
        """Test gateway rules endpoint generation."""
        endpoint = APIEndpoints.LIST_GATEWAY_RULES.format(account_id="acc-123")
        assert endpoint == "/accounts/acc-123/gateway/rules"


class TestReadWranglerToken:
    """Tests for _read_wrangler_token."""

    def test_reads_valid_toml(self, tmp_path, monkeypatch):
        """Test reading a valid wrangler config file."""
        config_dir = tmp_path / ".wrangler" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "default.toml").write_text(
            'oauth_token = "my-oauth-token"\nrefresh_token = "rt"\n'
        )
        monkeypatch.setattr("config.Path.home", lambda: tmp_path)
        assert _read_wrangler_token() == "my-oauth-token"

    def test_returns_none_when_no_file(self, tmp_path, monkeypatch):
        """Test returns None when wrangler config doesn't exist."""
        monkeypatch.setattr("config.Path.home", lambda: tmp_path)
        assert _read_wrangler_token() is None

    def test_returns_none_when_empty_token(self, tmp_path, monkeypatch):
        """Test returns None when oauth_token is empty."""
        config_dir = tmp_path / ".wrangler" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "default.toml").write_text('oauth_token = ""\n')
        monkeypatch.setattr("config.Path.home", lambda: tmp_path)
        assert _read_wrangler_token() is None

    def test_returns_none_on_malformed_toml(self, tmp_path, monkeypatch):
        """Test returns None on malformed TOML file."""
        config_dir = tmp_path / ".wrangler" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "default.toml").write_text("this is not valid toml {{{{")
        monkeypatch.setattr("config.Path.home", lambda: tmp_path)
        assert _read_wrangler_token() is None
