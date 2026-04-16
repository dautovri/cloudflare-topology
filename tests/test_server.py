"""Tests for the Flask server: /health, /regenerate, scheduler, and config parsing."""

import importlib
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def server_module(monkeypatch, tmp_path):
    """Reload server module with a clean state. Auth token set by default."""
    monkeypatch.setenv("REGEN_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("REGEN_INTERVAL_SECONDS", "0")  # disable scheduler by default
    # Ensure server package is importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    if "server.server" in sys.modules:
        del sys.modules["server.server"]
    mod = importlib.import_module("server.server")
    # Point APP_DIR / OUTPUT at a tmp location so tests don't touch real files
    monkeypatch.setattr(mod, "APP_DIR", tmp_path)
    yield mod
    # Cancel any scheduler timer left running
    if mod._scheduler_timer is not None:
        mod._scheduler_timer.cancel()


@pytest.fixture
def client(server_module):
    server_module.app.config["TESTING"] = True
    return server_module.app.test_client()


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_returns_all_fields(client, server_module):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "healthy"
    assert "topology_exists" in body
    assert "last_generated_at" in body
    assert "regen_in_progress" in body
    assert "next_scheduled_regen_at" in body


def test_health_regen_in_progress_reflects_state(client, server_module):
    with server_module._state_lock:
        server_module._state["regen_in_progress"] = True
    resp = client.get("/health")
    assert resp.get_json()["regen_in_progress"] is True


def test_health_topology_exists_false_when_missing(client, server_module):
    resp = client.get("/health")
    assert resp.get_json()["topology_exists"] is False


def test_health_falls_back_to_file_mtime(client, server_module, tmp_path):
    out = tmp_path / server_module.OUTPUT_FILE
    out.write_text("<html></html>")
    resp = client.get("/health")
    body = resp.get_json()
    assert body["topology_exists"] is True
    assert body["last_generated_at"] is not None


# ---------------------------------------------------------------------------
# /regenerate — auth
# ---------------------------------------------------------------------------

def test_regenerate_missing_auth_header(client):
    resp = client.post("/regenerate")
    assert resp.status_code == 401


def test_regenerate_invalid_token(client):
    resp = client.post("/regenerate", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 403


def test_regenerate_disabled_when_no_token(monkeypatch, tmp_path):
    monkeypatch.delenv("REGEN_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("REGEN_INTERVAL_SECONDS", "0")
    if "server.server" in sys.modules:
        del sys.modules["server.server"]
    mod = importlib.import_module("server.server")
    try:
        client = mod.app.test_client()
        resp = client.post("/regenerate", headers={"Authorization": "Bearer anything"})
        assert resp.status_code == 403
    finally:
        if mod._scheduler_timer is not None:
            mod._scheduler_timer.cancel()


# ---------------------------------------------------------------------------
# /regenerate — 202 / 409
# ---------------------------------------------------------------------------

def test_regenerate_returns_202_when_idle(client, server_module):
    # Mock out the actual subprocess so we don't hit Cloudflare
    with patch.object(server_module, "generate_topology", return_value=True):
        resp = client.post("/regenerate", headers={"Authorization": "Bearer test-token"})
        assert resp.status_code == 202
        body = resp.get_json()
        assert body["status"] == "accepted"
    # Wait for background thread to release lock
    time.sleep(0.05)


def test_regenerate_returns_409_when_already_running(client, server_module):
    # Hold the lock to simulate an in-progress regen
    acquired = server_module._regen_lock.acquire(blocking=False)
    assert acquired
    try:
        resp = client.post("/regenerate", headers={"Authorization": "Bearer test-token"})
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["status"] == "already_running"
        assert "hint" in body
        assert resp.headers.get("Retry-After") == "10"
    finally:
        server_module._regen_lock.release()


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def test_schedule_next_no_op_when_disabled(server_module, monkeypatch):
    monkeypatch.setattr(server_module, "REGEN_INTERVAL_SECONDS", 0)
    server_module._scheduler_timer = None
    server_module._schedule_next()
    assert server_module._scheduler_timer is None


def test_schedule_next_arms_timer_when_enabled(server_module, monkeypatch):
    monkeypatch.setattr(server_module, "REGEN_INTERVAL_SECONDS", 3600)
    server_module._scheduler_timer = None
    try:
        server_module._schedule_next()
        assert server_module._scheduler_timer is not None
        assert server_module._scheduler_timer.name == "topology-scheduler"
        assert server_module._scheduler_timer.daemon is True
        with server_module._state_lock:
            assert server_module._state["next_scheduled_regen_at"] is not None
    finally:
        if server_module._scheduler_timer is not None:
            server_module._scheduler_timer.cancel()


def test_scheduler_tick_skips_when_lock_held(server_module):
    calls = []

    def fake_generate():
        calls.append(1)
        return True

    with patch.object(server_module, "generate_topology", side_effect=fake_generate):
        server_module._regen_lock.acquire()
        try:
            # Tick should skip because lock is held. It also schedules next,
            # but interval is 0 so that no-ops.
            server_module._scheduler_tick()
        finally:
            server_module._regen_lock.release()
    assert calls == []


# ---------------------------------------------------------------------------
# REGEN_INTERVAL_SECONDS parsing
# ---------------------------------------------------------------------------

def test_parse_interval_default(monkeypatch):
    monkeypatch.delenv("REGEN_INTERVAL_SECONDS", raising=False)
    if "server.server" in sys.modules:
        del sys.modules["server.server"]
    mod = importlib.import_module("server.server")
    assert mod._parse_regen_interval() == 900


def test_parse_interval_non_integer_disables(monkeypatch, server_module):
    monkeypatch.setenv("REGEN_INTERVAL_SECONDS", "not-a-number")
    assert server_module._parse_regen_interval() == 0


def test_parse_interval_negative_disables(monkeypatch, server_module):
    monkeypatch.setenv("REGEN_INTERVAL_SECONDS", "-10")
    assert server_module._parse_regen_interval() == 0


def test_parse_interval_below_minimum_clamps(monkeypatch, server_module):
    monkeypatch.setenv("REGEN_INTERVAL_SECONDS", "30")
    assert server_module._parse_regen_interval() == 60


def test_parse_interval_zero_disables(monkeypatch, server_module):
    monkeypatch.setenv("REGEN_INTERVAL_SECONDS", "0")
    assert server_module._parse_regen_interval() == 0


# ---------------------------------------------------------------------------
# Multi-worker detection
# ---------------------------------------------------------------------------

def test_detect_multi_worker_web_concurrency(monkeypatch, server_module):
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    is_multi, reason = server_module._detect_multi_worker()
    assert is_multi is True
    assert "WEB_CONCURRENCY=4" in reason


def test_detect_multi_worker_gunicorn_cmd_args(monkeypatch, server_module):
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.delenv("UWSGI_WORKERS", raising=False)
    monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
    monkeypatch.setenv("GUNICORN_CMD_ARGS", "--workers 3 --timeout 60")
    is_multi, reason = server_module._detect_multi_worker()
    assert is_multi is True


def test_detect_multi_worker_single_worker_ok(monkeypatch, server_module):
    for var in ("WEB_CONCURRENCY", "UWSGI_WORKERS", "GUNICORN_WORKERS", "GUNICORN_CMD_ARGS"):
        monkeypatch.delenv(var, raising=False)
    is_multi, reason = server_module._detect_multi_worker()
    assert is_multi is False
    assert reason is None
