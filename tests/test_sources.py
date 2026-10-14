"""Tests for the topology source abstraction: factory, demo, shared helpers, MCP transport."""

import json
import types

import pytest

from config import Config
from services.cloudflare_api import CloudflareAPIError
from services.sources import create_source, resolve_source_kind, TopologySource, SOURCE_NAMES
from services.sources import mcp as mcp_module
from services.sources.demo import DemoSource
from services.sources import shared


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

class FakeResponse:
    """Minimal stand-in for requests.Response as consumed by _rpc."""

    def __init__(self, payload=None, headers=None, status=200, raw=None):
        self.text = raw if raw is not None else json.dumps(payload)
        self.headers = headers or {}
        self.status_code = status


def execute_reply(payload):
    """Responder factory: answers tools/call with `payload` as the program result.

    The value is embedded the way the Code-Mode server embeds a returned
    array/object: wrapped in a `result` envelope inside the text block.
    """
    def responder(message, n):
        text = json.dumps({"result": payload})
        result = {"content": [{"type": "text", "text": text}]}
        return FakeResponse({"jsonrpc": "2.0", "id": message["id"], "result": result})
    return responder


def make_post(responder):
    """Build a fake session.post that routes by JSON-RPC method and records calls."""
    calls = []

    def post(url, json=None, headers=None, timeout=None):
        calls.append(json)
        return responder(json, len(calls))

    post.calls = calls
    return post


def with_handshake(responder):
    """Wrap a responder so the initialize handshake is answered automatically."""
    def routed(message, n):
        method = message["method"]
        if method == "initialize":
            return FakeResponse(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {
                        "protocolVersion": mcp_module.MCP_PROTOCOL_VERSION,
                        "serverInfo": {"name": "cloudflare-api", "version": "test"},
                    },
                },
                headers={"MCP-Session-Id": "sess-77"},
            )
        if method == "notifications/initialized":
            return FakeResponse(status=202)
        return responder(message, n)
    return routed


def build_source(config, responder, **kwargs):
    source = mcp_module.ZeroTrustMCPSource(config, **kwargs)
    source.session = types.SimpleNamespace(post=make_post(with_handshake(responder)))
    return source


# ---------------------------------------------------------------------------
# Factory / protocol
# ---------------------------------------------------------------------------

class TestSourceFactory:

    def test_resolve_kind_explicit_wins(self, monkeypatch):
        monkeypatch.setenv("TOPOLOGY_SOURCE", "rest")
        assert resolve_source_kind("mcp") == "mcp"

    def test_resolve_kind_demo_flag(self):
        assert resolve_source_kind(None, demo=True) == "demo"

    def test_resolve_kind_env(self, monkeypatch):
        monkeypatch.setenv("TOPOLOGY_SOURCE", "MCP")
        assert resolve_source_kind() == "mcp"

    def test_resolve_kind_default(self, monkeypatch):
        monkeypatch.delenv("TOPOLOGY_SOURCE", raising=False)
        assert resolve_source_kind() == "rest"

    def test_create_mcp_source(self):
        config = Config(api_token="t", account_id="acct")
        source = create_source("mcp", config)
        assert isinstance(source, mcp_module.ZeroTrustMCPSource)
        assert isinstance(source, TopologySource)

    def test_create_rest_source_aliases(self):
        config = Config(api_token="t", account_id="acct")
        for name in ("rest", "api", "direct"):
            source = create_source(name, config)
            assert type(source).__name__ == "RestZeroTrustSource"

    def test_create_demo_source(self):
        assert isinstance(create_source("demo", None), DemoSource)

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError, match="Unknown data source"):
            create_source("nope", None)
        assert "mcp" in SOURCE_NAMES


# ---------------------------------------------------------------------------
# Demo source
# ---------------------------------------------------------------------------

class TestDemoSource:

    def test_returns_synthetic_topology(self):
        topology = DemoSource().fetch_topology()
        assert topology.total_resources > 0
        assert topology.account_id == "demo-account"

    def test_honours_include_devices_flag(self):
        assert DemoSource().fetch_topology(include_devices=False).devices == []


# ---------------------------------------------------------------------------
# Shared parsers
# ---------------------------------------------------------------------------

class TestSharedParsers:

    def test_parse_tunnel_matches_client(self):
        from services.cloudflare_api import CloudflareAPIClient

        raw = {
            "id": "tun-1",
            "name": "prod",
            "status": "healthy",
            "remote_config": True,
            "connections": [{"uuid": "c-1", "colo_name": "SFO", "is_pending_reconnect": False}],
        }
        shared_tunnel = shared.parse_tunnel(dict(raw))
        client = CloudflareAPIClient.__new__(CloudflareAPIClient)
        client_tunnel = client._parse_tunnel(dict(raw))
        assert shared_tunnel == client_tunnel
        assert shared_tunnel.connections[0].id == "c-1"

    def test_parse_tunnel_config(self):
        cfg = shared.parse_tunnel_config({"ingress": [{"hostname": "a.example.com"}]})
        assert cfg.ingress_rules[0]["hostname"] == "a.example.com"
        assert shared.parse_tunnel_config(None).ingress == []

    def test_parse_device_user_fields(self):
        device = shared.parse_device({"id": "d1", "user": {"email": "a@b.c", "name": "Ada"}})
        assert device.user_email == "a@b.c"
        assert shared.parse_device({"id": "d2"}).user_email is None

    def test_try_fetch_swallows_403(self):
        def boom():
            raise CloudflareAPIError("nope", status_code=403)
        assert shared.try_fetch("widgets", boom) == []

    def test_try_fetch_reraises_other_status(self):
        def boom():
            raise CloudflareAPIError("boom", status_code=500)
        with pytest.raises(CloudflareAPIError):
            shared.try_fetch("widgets", boom)

    def test_run_parallel_noop_on_empty(self):
        assert shared.run_parallel(lambda x: x, []) == []

    def test_format_endpoint(self):
        assert shared.format_endpoint("acct", "/accounts/{account_id}/x") == "/accounts/acct/x"


# ---------------------------------------------------------------------------
# MCP module-level helpers
# ---------------------------------------------------------------------------

class TestMCPParsers:

    def test_render_embeds_values_as_literals(self):
        code = mcp_module._render(
            mcp_module._JS_PAGINATED, path="/accounts/1/cfd_tunnel",
            per_page=100, max_pages=50,
        )
        assert "codemode.request" in code
        assert "per_page=" in code
        assert '"/accounts/1/cfd_tunnel"' in code

    def test_render_quotes_hostile_value(self):
        code = mcp_module._render(mcp_module._JS_PAGINATED, path='/a"alert(1)', per_page=1, max_pages=1)
        # The injected text must sit inside one escaped JS string literal.
        literal_line = [ln for ln in code.splitlines() if "const path" in ln][0]
        assert '\\"' in literal_line

    def test_unwrap_items_variants(self):
        assert mcp_module._unwrap_items([{"id": 1}, "junk"]) == [{"id": 1}]
        assert mcp_module._unwrap_items({"result": [{"id": 2}]}) == [{"id": 2}]
        assert mcp_module._unwrap_items(None) == []

    def test_parse_stream_sse(self):
        inner = json.dumps({"jsonrpc": "2.0", "id": 4, "result": {"ok": 1}})
        body = "event: message\ndata: " + inner + "\n\n"
        assert mcp_module._parse_stream(body, 4)["result"]["ok"] == 1

    def test_parse_stream_rejects_other_id(self):
        body = json.dumps({"jsonrpc": "2.0", "id": 5, "result": {}})
        assert mcp_module._parse_stream(body, 4) is None

    def test_status_from_text(self):
        assert mcp_module._status_from_text("failed (403) here") == 403
        assert mcp_module._status_from_text("no code") is None


# ---------------------------------------------------------------------------
# MCP source behaviour
# ---------------------------------------------------------------------------

class TestZeroTrustMCPSource:

    def test_handshake_then_execute(self):
        source = build_source(
            Config(api_token="t", account_id="acct-9"),
            execute_reply([{"id": "t1", "name": "prod", "status": "healthy"}]),
        )
        items = source.list_tunnels()

        methods = [c["method"] for c in source.session.post.calls]
        assert methods == ["initialize", "notifications/initialized", "tools/call"]
        call = source.session.post.calls[-1]
        assert call["params"]["name"] == mcp_module.MCP_EXECUTE_TOOL
        assert "codemode.request" in call["params"]["arguments"]["code"]
        assert "acct-9" in call["params"]["arguments"]["code"]
        assert items[0]["name"] == "prod"
        assert source._session_id == "sess-77"

    def test_handshake_runs_once(self):
        source = build_source(Config(api_token="t", account_id="a"), execute_reply([]))
        source.list_tunnels()
        source.list_tunnels()
        methods = [c["method"] for c in source.session.post.calls]
        assert methods.count("initialize") == 1

    def test_structured_content_preferred(self):
        def responder(message, n):
            result = {"structuredContent": {"result": [{"id": "a1", "domain": "x.example.com"}]}}
            return FakeResponse({"jsonrpc": "2.0", "id": message["id"], "result": result})
        source = build_source(Config(api_token="t", account_id="a"), responder)
        assert source.list_applications()[0]["domain"] == "x.example.com"

    def test_sse_framed_tool_result(self):
        def responder(message, n):
            inner = json.dumps({
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"content": [{"type": "text",
                                        "text": json.dumps({"result": [{"id": "g1"}]})}]},
            })
            return FakeResponse(raw="event: message\ndata: " + inner + "\n\n")
        source = build_source(Config(api_token="t", account_id="a"), responder)
        assert source.list_groups()[0]["id"] == "g1"

    def test_permission_error_tolerated(self):
        def responder(message, n):
            result = {"isError": True, "content": [{"type": "text",
                                                    "text": "Not authorized (403)"}]}
            return FakeResponse({"jsonrpc": "2.0", "id": message["id"], "result": result})
        source = build_source(Config(api_token="t", account_id="a"), responder)
        assert source._try_fetch("devices", source.list_devices) == []

    def test_jsonrpc_error_surfaced(self):
        def responder(message, n):
            body = {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {"code": -32601, "message": "Method not found"},
            }
            return FakeResponse(body)
        source = build_source(Config(api_token="t", account_id="a"), responder)
        with pytest.raises(CloudflareAPIError, match="Method not found"):
            source.list_tunnels()

    def test_retry_on_rate_limit_then_success(self):
        state = {"n": 0}

        def responder(message, n):
            state["n"] += 1
            if state["n"] == 1:
                return FakeResponse(status=429, raw="rate limited")
            return execute_reply([{"id": "t1"}])(message, n)

        source = build_source(
            Config(api_token="t", account_id="a"), responder, backoff_factor=0.0,
        )
        assert source.list_tunnels() == [{"id": "t1"}]
        assert state["n"] == 2

    def test_account_discovery(self):
        source = build_source(
            Config(api_token="t", account_id=""),
            execute_reply([{"id": "found-1", "name": "Acme"}]),
        )
        assert source._ensure_account_id() == "found-1"
        assert source.config.account_id == "found-1"

    def test_account_discovery_none_found(self):
        source = build_source(
            Config(api_token="t", account_id="a"), execute_reply([]),
        )
        with pytest.raises(CloudflareAPIError, match="No accounts found"):
            source._discover_account_id()

    def test_list_tools(self):
        def responder(message, n):
            if message["method"] == "tools/list":
                tools = [{"name": "execute"}, {"name": "search"}]
                return FakeResponse({
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {"tools": tools},
                })
            return execute_reply([])(message, n)
        source = build_source(Config(api_token="t", account_id="a"), responder)
        assert [t["name"] for t in source.list_tools()] == ["execute", "search"]

    def test_fetch_topology_end_to_end(self):
        fixtures = {
            # Order matters: first substring hit in the generated program wins.
            "configurations": {"ingress": [{"hostname": "g.example.com",
                                           "service": "http://localhost:8080"}]},
            "cfd_tunnel": [{"id": "t1", "name": "prod", "status": "healthy",
                            "remote_config": True, "connections": []}],
            "/access/apps/": [{"id": "p0", "name": "app-allow", "decision": "allow"}],
            "/access/apps": [{"id": "a1", "name": "grafana", "domain": "g.example.com",
                              "type": "self_hosted"}],
            "identity_providers": [{"id": "i1", "name": "Okta", "type": "okta"}],
            "physical-devices": [{"id": "d1", "name": "laptop",
                                  "user": {"email": "a@b.c"}}],
        }

        reusable_policy = {
            "id": "p1",
            "name": "allow-all",
            "decision": "allow",
            "include": [{"everyone": {}}],
        }

        def responder(message, n):
            code = message["params"]["arguments"]["code"]
            if "/access/policies" in code:
                return execute_reply([reusable_policy])(message, n)
            for needle, payload in fixtures.items():
                if needle in code:
                    return execute_reply(payload)(message, n)
            return execute_reply([])(message, n)

        source = build_source(Config(api_token="t", account_id="acct-x"), responder)
        topology = source.fetch_topology()

        assert topology.account_id == "acct-x"
        assert topology.tunnels[0].config.ingress[0]["hostname"] == "g.example.com"
        assert topology.applications[0].policies[0].decision == "allow"
        assert topology.policies[0].include[0].rule_type == "everyone"
        assert topology.identity_providers[0].idp_type == "okta"
        assert topology.devices[0].user_email == "a@b.c"
        assert topology.total_resources > 0
