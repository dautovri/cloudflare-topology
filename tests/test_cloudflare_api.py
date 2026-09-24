"""Tests for CloudflareAPIClient."""

from unittest.mock import MagicMock, patch
import pytest
import requests

from config import Config
from services.cloudflare_api import CloudflareAPIClient, CloudflareAPIError
from models.cloudflare_data import CloudflareTopology, Tunnel, AccessApplication


@pytest.fixture
def mock_config():
    """Create a test Config object."""
    return Config(
        api_token="test-token-12345",
        account_id="acc-test-id",
        api_base_url="https://api.cloudflare.com/client/v4",
    )


class TestCloudflareAPIClientInit:
    """Tests for CloudflareAPIClient initialization."""

    def test_init_with_account_id(self, mock_config):
        """Test initializing client with account ID already set."""
        client = CloudflareAPIClient(mock_config)
        assert client.config.account_id == "acc-test-id"
        assert client.session.headers["Authorization"] == "Bearer test-token-12345"
        assert client.session.headers["Content-Type"] == "application/json"
        assert "https://" in client.session.adapters
        assert "http://" in client.session.adapters

    def test_auto_discover_account_id_single(self):
        """Test auto-discovering account ID when not provided."""
        config = Config(api_token="test-token", account_id="")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "result": [{"id": "discovered-acc-1", "name": "My Account"}],
            "result_info": {"total_count": 1},
        }

        with patch.object(requests.Session, "request", return_value=mock_response):
            client = CloudflareAPIClient(config)
            assert client.config.account_id == "discovered-acc-1"

    def test_auto_discover_account_id_multiple(self):
        """Test auto-discovering account ID with warning when multiple accounts exist."""
        config = Config(api_token="test-token", account_id="")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "result": [
                {"id": "first-acc", "name": "First Account"},
                {"id": "second-acc", "name": "Second Account"},
            ],
            "result_info": {"total_count": 2},
        }

        with patch.object(requests.Session, "request", return_value=mock_response):
            client = CloudflareAPIClient(config)
            assert client.config.account_id == "first-acc"

    def test_auto_discover_account_id_none_found(self):
        """Test error raised when no accounts are found."""
        config = Config(api_token="test-token", account_id="")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "result": [],
            "result_info": {"total_count": 0},
        }

        with patch.object(requests.Session, "request", return_value=mock_response):
            with pytest.raises(CloudflareAPIError, match="No accounts found"):
                CloudflareAPIClient(config)


class TestCloudflareAPIClientRequests:
    """Tests for _make_request and error handling."""

    def test_make_request_success(self, mock_config):
        """Test successful API request."""
        client = CloudflareAPIClient(mock_config)
        
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "result": [{"id": "item-1"}],
        }

        with patch.object(client.session, "request", return_value=mock_resp):
            res = client._make_request("GET", "/test-endpoint")
            assert res["success"] is True
            assert res["result"] == [{"id": "item-1"}]

    def test_make_request_api_error(self, mock_config):
        """Test API error response raises CloudflareAPIError."""
        client = CloudflareAPIClient(mock_config)
        
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "success": False,
            "errors": [{"code": 1000, "message": "Invalid token"}],
        }

        with patch.object(client.session, "request", return_value=mock_resp):
            with pytest.raises(CloudflareAPIError) as exc_info:
                client._make_request("GET", "/test-endpoint")
            assert "Invalid token" in str(exc_info.value)
            assert exc_info.value.status_code == 400
            assert len(exc_info.value.errors) == 1

    def test_make_request_non_json_response(self, mock_config):
        """Test handling of non-JSON response (e.g. 502 HTML)."""
        client = CloudflareAPIClient(mock_config)
        
        mock_resp = MagicMock()
        mock_resp.status_code = 502
        mock_resp.text = "Bad Gateway HTML error page"
        mock_resp.json.side_effect = ValueError("No JSON")

        with patch.object(client.session, "request", return_value=mock_resp):
            with pytest.raises(CloudflareAPIError) as exc_info:
                client._make_request("GET", "/test-endpoint")
            assert "502" in str(exc_info.value)
            assert exc_info.value.status_code == 502

    def test_make_request_timeout(self, mock_config):
        """Test handling of request timeout."""
        client = CloudflareAPIClient(mock_config)

        with patch.object(client.session, "request", side_effect=requests.exceptions.Timeout("Timed out")):
            with pytest.raises(CloudflareAPIError, match="Request timeout"):
                client._make_request("GET", "/test-endpoint")

    def test_make_request_connection_error(self, mock_config):
        """Test handling of general request exception."""
        client = CloudflareAPIClient(mock_config)

        with patch.object(client.session, "request", side_effect=requests.exceptions.ConnectionError("DNS failure")):
            with pytest.raises(CloudflareAPIError, match="Request failed"):
                client._make_request("GET", "/test-endpoint")


class TestCloudflareAPIClientPagination:
    """Tests for pagination helpers."""

    def test_paginate_multiple_pages(self, mock_config):
        """Test standard pagination across multiple pages."""
        client = CloudflareAPIClient(mock_config)

        responses = [
            {
                "success": True,
                "result": [{"id": "1"}, {"id": "2"}],
                "result_info": {"page": 1, "total_pages": 2},
            },
            {
                "success": True,
                "result": [{"id": "3"}],
                "result_info": {"page": 2, "total_pages": 2},
            },
        ]

        with patch.object(client, "_make_request", side_effect=responses):
            results = client._paginate("/endpoint")
            assert len(results) == 3
            assert [r["id"] for r in results] == ["1", "2", "3"]

    def test_paginate_cursor(self, mock_config):
        """Test cursor-based pagination."""
        client = CloudflareAPIClient(mock_config)

        responses = [
            {
                "success": True,
                "result": [{"id": "dev-1"}],
                "result_info": {"cursors": {"after": "cursor-token-2"}},
            },
            {
                "success": True,
                "result": [{"id": "dev-2"}],
                "result_info": {"cursors": {}},
            },
        ]

        with patch.object(client, "_make_request", side_effect=responses):
            results = client._paginate_cursor("/devices/physical-devices")
            assert len(results) == 2
            assert [r["id"] for r in results] == ["dev-1", "dev-2"]


class TestCloudflareAPIClientTryFetch:
    """Tests for _try_fetch resilience helper."""

    def test_try_fetch_success(self, mock_config):
        """Test _try_fetch returns normal results on success."""
        client = CloudflareAPIClient(mock_config)
        fetcher = MagicMock(return_value=[1, 2, 3])
        result = client._try_fetch("test_resource", fetcher)
        assert result == [1, 2, 3]

    def test_try_fetch_403_returns_empty(self, mock_config):
        """Test _try_fetch swallows 403 Forbidden and returns empty list."""
        client = CloudflareAPIClient(mock_config)
        fetcher = MagicMock(side_effect=CloudflareAPIError("Forbidden", status_code=403))
        result = client._try_fetch("test_resource", fetcher)
        assert result == []

    def test_try_fetch_non_403_raises(self, mock_config):
        """Test _try_fetch re-raises non-403 errors."""
        client = CloudflareAPIClient(mock_config)
        fetcher = MagicMock(side_effect=CloudflareAPIError("Server error", status_code=500))
        with pytest.raises(CloudflareAPIError) as exc_info:
            client._try_fetch("test_resource", fetcher)
        assert exc_info.value.status_code == 500


class TestCloudflareAPIClientResources:
    """Tests for individual resource fetching methods."""

    def test_list_tunnels(self, mock_config):
        """Test fetching and parsing tunnels."""
        client = CloudflareAPIClient(mock_config)
        
        mock_tunnels = [
            {
                "id": "tun-1",
                "name": "tunnel-one",
                "status": "healthy",
                "created_at": "2024-01-01T00:00:00Z",
                "remote_config": True,
                "connections": [
                    {
                        "id": "c-1",
                        "colo_name": "SFO",
                        "is_pending_reconnect": False,
                        "origin_ip": "1.2.3.4",
                        "opened_at": "2024-01-01T00:01:00Z",
                    }
                ],
            }
        ]

        with patch.object(client, "_paginate", return_value=mock_tunnels):
            tunnels = client.list_tunnels()
            assert len(tunnels) == 1
            assert tunnels[0].id == "tun-1"
            assert tunnels[0].name == "tunnel-one"
            assert tunnels[0].remote_config is True
            assert len(tunnels[0].connections) == 1
            assert tunnels[0].connections[0].colo_name == "SFO"

    def test_get_tunnel_config(self, mock_config):
        """Test fetching and parsing tunnel config ingress rules."""
        client = CloudflareAPIClient(mock_config)
        
        mock_data = {
            "success": True,
            "result": {
                "config": {
                    "ingress": [
                        {"hostname": "app.example.com", "service": "http://localhost:8080"},
                        {"service": "http_status:404"},
                    ]
                }
            }
        }

        with patch.object(client, "_make_request", return_value=mock_data):
            cfg = client.get_tunnel_config("tun-1")
            assert cfg is not None
            assert len(cfg.ingress_rules) == 2
            assert cfg.ingress_rules[0]["hostname"] == "app.example.com"

    def test_list_applications(self, mock_config):
        """Test fetching and parsing access applications."""
        client = CloudflareAPIClient(mock_config)
        
        mock_apps = [
            {
                "id": "app-1",
                "name": "Grafana",
                "domain": "grafana.example.com",
                "type": "self_hosted",
                "session_duration": "24h",
                "allowed_idps": ["idp-1"],
                "auto_redirect_to_identity": True,
            }
        ]

        with patch.object(client, "_paginate", return_value=mock_apps):
            apps = client.list_applications()
            assert len(apps) == 1
            assert apps[0].id == "app-1"
            assert apps[0].name == "Grafana"
            assert apps[0].domain == "grafana.example.com"
            assert apps[0].allowed_idps == ["idp-1"]

    def test_fetch_topology_orchestration(self, mock_config):
        """Test complete fetch_topology orchestration and concurrency."""
        client = CloudflareAPIClient(mock_config)

        tun = Tunnel(id="tun-1", name="Tunnel 1", status="healthy", remote_config=True)
        app = AccessApplication(id="app-1", name="App 1", domain="app1.com", app_type="self_hosted")

        with patch.object(client, "list_tunnels", return_value=[tun]), \
             patch.object(client, "get_tunnel_config", return_value=MagicMock()) as mock_cfg, \
             patch.object(client, "list_applications", return_value=[app]), \
             patch.object(client, "get_application_policies", return_value=[MagicMock()]) as mock_pol, \
             patch.object(client, "list_policies", return_value=[]), \
             patch.object(client, "list_groups", return_value=[]), \
             patch.object(client, "list_identity_providers", return_value=[]), \
             patch.object(client, "list_virtual_networks", return_value=[]), \
             patch.object(client, "list_routes", return_value=[]), \
             patch.object(client, "list_devices", return_value=[]):
            
            topology = client.fetch_topology(
                include_tunnel_configs=True,
                include_app_policies=True,
                include_devices=True,
                include_gateway_rules=False,
            )

            assert isinstance(topology, CloudflareTopology)
            assert len(topology.tunnels) == 1
            assert len(topology.applications) == 1
            mock_cfg.assert_called_once_with("tun-1")
            mock_pol.assert_called_once_with("app-1")
            assert tun.config is not None
            assert len(app.policies) == 1
