"""
Flask server for serving the topology visualization in Docker.
"""

import hmac
import os
import logging
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, send_from_directory, jsonify, request, render_template_string
from werkzeug.serving import WSGIRequestHandler

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Shared secret for /regenerate endpoint (set via REGEN_AUTH_TOKEN env var)
REGEN_AUTH_TOKEN = os.environ.get("REGEN_AUTH_TOKEN", "")

# ---------------------------------------------------------------------------
# Scheduled regeneration state
# ---------------------------------------------------------------------------
# _regen_lock ensures only one regeneration runs at a time (scheduler or on-demand).
# _state_lock protects the state dict read by /health.
_regen_lock = threading.Lock()
_state_lock = threading.Lock()
_state = {
    "regen_in_progress": False,
    "last_generated_at": None,       # ISO 8601 UTC or None
    "next_scheduled_regen_at": None,  # ISO 8601 UTC or None
}
_scheduler_timer = None  # type: threading.Timer | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_regen_interval() -> int:
    """Parse and validate REGEN_INTERVAL_SECONDS. Returns 0 to disable scheduler."""
    raw = os.environ.get("REGEN_INTERVAL_SECONDS", "900")
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "REGEN_INTERVAL_SECONDS=%r is not an integer; disabling scheduler "
            "(valid: 0 to disable, or integer >= 60, recommended >= 300)",
            raw,
        )
        return 0
    if value < 0:
        logger.warning(
            "REGEN_INTERVAL_SECONDS=%d is negative; disabling scheduler",
            value,
        )
        return 0
    if 0 < value < 60:
        logger.warning(
            "REGEN_INTERVAL_SECONDS=%d is below minimum 60s; clamping to 60",
            value,
        )
        return 60
    if 0 < value < 300:
        logger.info(
            "REGEN_INTERVAL_SECONDS=%d is below recommended 300s; proceeding",
            value,
        )
    return value


REGEN_INTERVAL_SECONDS = _parse_regen_interval()


def _detect_multi_worker():
    """Return (is_multi, reason) if a multi-worker WSGI server is likely in use."""
    for var in ("WEB_CONCURRENCY", "UWSGI_WORKERS", "GUNICORN_WORKERS"):
        val = os.environ.get(var)
        if val:
            try:
                if int(val) > 1:
                    return True, f"{var}={val}"
            except ValueError:
                pass
    args = os.environ.get("GUNICORN_CMD_ARGS", "")
    if args:
        m = re.search(r"(?:-w|--workers)\s+(\d+)", args)
        if m and int(m.group(1)) > 1:
            return True, f"GUNICORN_CMD_ARGS contains -w {m.group(1)}"
    return False, None


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "img-src 'self' data:"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


class _QuietHandler(WSGIRequestHandler):
    """Suppress the Server header that Werkzeug adds by default."""

    def send_header(self, keyword, value):
        if keyword.lower() != "server":
            super().send_header(keyword, value)

# Path to the generated HTML file
APP_DIR = Path(__file__).parent.parent
OUTPUT_FILE = "network_topology.html"


@app.route("/lib/<path:filename>")
def serve_lib(filename):
    """Serve pyvis helper files (e.g. lib/bindings/utils.js)."""
    return send_from_directory(str(APP_DIR / "lib"), filename)

ERROR_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} — Cloudflare Topology</title>
<style>
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
         background:#1a1a2e; color:#fff; }
  .card { text-align:center; max-width:420px; padding:40px 24px; }
  .code { font-size:72px; font-weight:700; color:#f6821f; margin:0 0 8px; }
  h1 { font-size:20px; font-weight:600; margin:0 0 12px; }
  p  { font-size:14px; color:#888; line-height:1.5; margin:0; }
</style>
</head>
<body>
  <div class="card">
    <div class="code">{{ code }}</div>
    <h1>{{ title }}</h1>
    <p>{{ message }}</p>
  </div>
</body>
</html>"""


def generate_topology() -> bool:
    """Generate the topology visualization."""
    logger.info("Generating topology visualization...")
    
    try:
        result = subprocess.run(
            [sys.executable, str(APP_DIR / "main.py"), "--no-browser"],
            cwd=str(APP_DIR),
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )
        
        if result.returncode != 0:
            logger.error(f"Topology generation failed: {result.stderr}")
            return False
        
        logger.info("Topology generated successfully")
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("Topology generation timed out")
        return False
    except Exception as e:
        logger.error(f"Error generating topology: {e}")
        return False


def _generate_topology_guarded() -> bool:
    """Run generate_topology and update /health state. Caller must hold _regen_lock."""
    with _state_lock:
        _state["regen_in_progress"] = True
    try:
        ok = generate_topology()
        if ok:
            with _state_lock:
                _state["last_generated_at"] = _now_iso()
        return ok
    finally:
        with _state_lock:
            _state["regen_in_progress"] = False


def _scheduler_tick():
    """Scheduler callback: attempt regen, then reschedule."""
    logger.info("Scheduler: tick starting")
    acquired = _regen_lock.acquire(blocking=False)
    if not acquired:
        logger.info("Scheduler: skipping tick — regeneration already in progress")
    else:
        try:
            _generate_topology_guarded()
        finally:
            _regen_lock.release()
    _schedule_next()


def _schedule_next():
    """Arm the next Timer. No-op if scheduler disabled."""
    global _scheduler_timer
    if REGEN_INTERVAL_SECONDS <= 0:
        return
    next_ts = datetime.now(timezone.utc).timestamp() + REGEN_INTERVAL_SECONDS
    with _state_lock:
        _state["next_scheduled_regen_at"] = (
            datetime.fromtimestamp(next_ts, tz=timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    timer = threading.Timer(REGEN_INTERVAL_SECONDS, _scheduler_tick)
    timer.name = "topology-scheduler"
    timer.daemon = True
    timer.start()
    _scheduler_timer = timer


def _start_scheduler():
    """Start the background scheduler if configured and safe."""
    if REGEN_INTERVAL_SECONDS <= 0:
        logger.info("Scheduler: disabled (REGEN_INTERVAL_SECONDS=0)")
        return
    is_multi, reason = _detect_multi_worker()
    if is_multi:
        logger.error(
            "Scheduler: disabled — multi-worker deployment detected (%s). "
            "Scheduled regeneration requires a single process "
            "(e.g. gunicorn -w 1). Each worker would run its own scheduler "
            "and race for the output file.",
            reason,
        )
        return
    minutes = REGEN_INTERVAL_SECONDS // 60
    logger.info(
        "Scheduler: enabled, interval %ds (~every %dm)",
        REGEN_INTERVAL_SECONDS,
        minutes,
    )
    _schedule_next()


@app.route("/")
def serve_topology():
    """Serve the network topology HTML file."""
    output_path = APP_DIR / OUTPUT_FILE
    
    if not output_path.exists():
        return render_template_string(
            ERROR_PAGE,
            code=503,
            title="Topology Not Ready",
            message="The network topology hasn't been generated yet. Check the logs or trigger a regeneration.",
        ), 503
    
    return send_from_directory(str(APP_DIR), OUTPUT_FILE)


@app.errorhandler(404)
def not_found(e):
    """Custom 404 page matching the Cloudflare dark theme."""
    return render_template_string(
        ERROR_PAGE,
        code=404,
        title="Page Not Found",
        message="The page you're looking for doesn't exist. Try the topology view at /.",
    ), 404


@app.route("/health")
def health_check():
    """Health check endpoint."""
    output_path = APP_DIR / OUTPUT_FILE
    with _state_lock:
        snap = dict(_state)

    # If we haven't recorded last_generated_at in memory (e.g. file pre-existed
    # before server started), fall back to the file mtime.
    last_generated = snap["last_generated_at"]
    if last_generated is None and output_path.exists():
        try:
            mtime = output_path.stat().st_mtime
            last_generated = (
                datetime.fromtimestamp(mtime, tz=timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
        except OSError:
            pass

    return jsonify({
        "status": "healthy",
        "topology_exists": output_path.exists(),
        "last_generated_at": last_generated,
        "regen_in_progress": snap["regen_in_progress"],
        "next_scheduled_regen_at": snap["next_scheduled_regen_at"],
    })


@app.route("/regenerate", methods=["POST"])
def regenerate():
    """Queue a topology regeneration. Fire-and-forget. Requires Bearer token auth.

    Returns:
        202 Accepted — regeneration queued in the background
        409 Conflict — a regeneration is already running (includes Retry-After: 10)
    """
    if not REGEN_AUTH_TOKEN:
        return jsonify({"status": "error", "message": "Regeneration endpoint not configured"}), 403

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"status": "error", "message": "Missing or invalid Authorization header"}), 401

    provided_token = auth_header[len("Bearer "):]
    if not hmac.compare_digest(provided_token, REGEN_AUTH_TOKEN):
        return jsonify({"status": "error", "message": "Invalid token"}), 403

    # Non-blocking: if regen already running, return 409 immediately.
    acquired = _regen_lock.acquire(blocking=False)
    if not acquired:
        resp = jsonify({
            "status": "already_running",
            "hint": "GET /health returns regen_in_progress and next_scheduled_regen_at",
        })
        resp.status_code = 409
        resp.headers["Retry-After"] = "10"
        return resp

    def _run():
        try:
            _generate_topology_guarded()
        finally:
            _regen_lock.release()

    thread = threading.Thread(target=_run, name="topology-regen-on-demand", daemon=True)
    thread.start()

    return jsonify({
        "status": "accepted",
        "message": "Topology regeneration queued",
    }), 202


if __name__ == "__main__":
    # Log configuration summary
    if REGEN_AUTH_TOKEN:
        logger.info("Auth: REGEN_AUTH_TOKEN set — /regenerate enabled")
    else:
        logger.info("Auth: REGEN_AUTH_TOKEN not set — /regenerate disabled")

    # Initialise last_generated_at from existing file mtime (if any), so /health
    # reports correctly before the first regen completes.
    output_path = APP_DIR / OUTPUT_FILE
    if output_path.exists():
        try:
            mtime = output_path.stat().st_mtime
            with _state_lock:
                _state["last_generated_at"] = (
                    datetime.fromtimestamp(mtime, tz=timezone.utc)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z")
                )
        except OSError:
            pass

    # Cold start: if no topology file exists yet, generate synchronously so the
    # first / request succeeds. Otherwise, rely on the scheduler.
    if not output_path.exists():
        with _regen_lock:
            _generate_topology_guarded()

    # Start background scheduler
    _start_scheduler()

    # Get port from environment or default
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")

    logger.info(f"Starting server on {host}:{port}")
    app.run(host=host, port=port, debug=False, request_handler=_QuietHandler)
