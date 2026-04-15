"""
Flask server for serving the topology visualization in Docker.
"""

import hmac
import os
import logging
import subprocess
import sys
from pathlib import Path

from flask import Flask, send_from_directory, jsonify, request
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


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
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


@app.route("/")
def serve_topology():
    """Serve the network topology HTML file."""
    output_path = APP_DIR / OUTPUT_FILE
    
    if not output_path.exists():
        return jsonify({
            "error": "Topology not generated yet",
            "message": "Please wait or check the logs for errors"
        }), 503
    
    return send_from_directory(str(APP_DIR), OUTPUT_FILE)


@app.route("/health")
def health_check():
    """Health check endpoint."""
    output_path = APP_DIR / OUTPUT_FILE
    
    return jsonify({
        "status": "healthy",
        "topology_exists": output_path.exists(),
    })


@app.route("/regenerate", methods=["POST"])
def regenerate():
    """Regenerate the topology visualization. Requires Bearer token auth."""
    if not REGEN_AUTH_TOKEN:
        return jsonify({"status": "error", "message": "Regeneration endpoint not configured"}), 403

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"status": "error", "message": "Missing or invalid Authorization header"}), 401

    provided_token = auth_header[len("Bearer "):]
    if not hmac.compare_digest(provided_token, REGEN_AUTH_TOKEN):
        return jsonify({"status": "error", "message": "Invalid token"}), 403

    success = generate_topology()
    
    if success:
        return jsonify({"status": "success", "message": "Topology regenerated"})
    else:
        return jsonify({"status": "error", "message": "Failed to regenerate topology"}), 500


if __name__ == "__main__":
    # Generate topology on startup
    generate_topology()
    
    # Get port from environment or default
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")
    
    logger.info(f"Starting server on {host}:{port}")
    app.run(host=host, port=port, debug=False, request_handler=_QuietHandler)
