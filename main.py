#!/usr/bin/env python3
"""
Cloudflare Network Topology Mapper

Generates an interactive network topology visualization of your
Cloudflare Zero Trust infrastructure.

Usage:
    python main.py [--debug] [--output FILE]

Environment Variables:
    CLOUDFLARE_API_TOKEN: Your Cloudflare API token (required)
    CLOUDFLARE_ACCOUNT_ID: Your Cloudflare account ID (auto-discovered if omitted)
"""

import argparse
import json
import logging
import os
import sys
import tempfile
import webbrowser
from dataclasses import replace
from pathlib import Path
from typing import Dict, Any

from config import Config, __version__
from models.cloudflare_data import CloudflareTopology
from services.cloudflare_api import CloudflareAPIError
from services.network_graph import NetworkGraphBuilder
from services.renderer import TopologyRenderer
from services.sources import create_source, resolve_source_kind


def setup_logging(debug: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if debug else logging.INFO
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate Cloudflare Zero Trust network topology visualization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate topology with default settings
    python main.py

    # Enable debug logging
    python main.py --debug

    # Custom output file
    python main.py --output my_topology.html

    # Skip devices (faster)
    python main.py --no-devices

Environment Variables:
    CLOUDFLARE_API_TOKEN    Cloudflare API token (or use wrangler login)
    CLOUDFLARE_ACCOUNT_ID   Cloudflare account ID (auto-discovered if omitted)
    DEBUG                   Enable debug mode (optional)
        """
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        metavar="FILE",
        help="Load configuration from a JSON or TOML file",
    )

    parser.add_argument(
        "--account-id",
        dest="account_ids",
        action="append",
        default=None,
        metavar="ID",
        help="Cloudflare account ID (repeatable or comma-separated for multi-account aggregation)",
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output HTML file path (default: network_topology.html)",
    )

    parser.add_argument(
        "--export-json",
        type=str,
        default=None,
        metavar="FILE",
        help="Also export topology and graph data as structured JSON to FILE",
    )

    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open browser after generating",
    )

    parser.add_argument(
        "--no-devices",
        action="store_true",
        help="Skip fetching WARP devices (faster)",
    )

    parser.add_argument(
        "--no-tunnel-configs",
        action="store_true",
        help="Skip fetching detailed tunnel configurations",
    )

    parser.add_argument(
        "--include-gateway",
        action="store_true",
        help="Include Gateway firewall rules",
    )

    parser.add_argument(
        "--no-gateway",
        action="store_true",
        help="Skip fetching Gateway firewall rules (default)",
    )

    parser.add_argument(
        "--no-physics",
        action="store_true",
        help="Disable graph layout physics on initial load",
    )

    parser.add_argument(
        "--source",
        choices=["rest", "mcp", "demo"],
        default=None,
        help=(
            "Data source: 'rest' (default) calls api.cloudflare.com directly; "
            "'mcp' fetches through Cloudflare's remote MCP server "
            "(https://mcp.cloudflare.com/mcp); 'demo' uses synthetic data. "
            "Overrides TOPOLOGY_SOURCE."
        ),
    )

    parser.add_argument(
        "--mcp-url",
        type=str,
        default=None,
        help=(
            "Streamable HTTP endpoint for --source mcp "
            "(default: https://mcp.cloudflare.com/mcp, or CLOUDFLARE_MCP_URL)."
        ),
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use synthetic demo data (no Cloudflare API calls). Safe for public deploys.",
    )

    parser.add_argument(
        "--setup",
        action="store_true",
        help="Interactive first-run setup: writes a .env file with your Cloudflare token.",
    )

    return parser.parse_args()


def run_setup() -> int:
    """Interactive setup that writes a .env file for the user."""
    from pathlib import Path

    print("\n🌐 Cloudflare Topology — setup")
    print("=" * 50)
    print("This will create a .env file so `python main.py` just works.\n")

    env_path = Path(".env")
    if env_path.exists():
        resp = input(f".env already exists at {env_path.absolute()}. Overwrite? [y/N] ").strip().lower()
        if resp != "y":
            print("Aborted. Your existing .env was not touched.")
            return 0

    print("\nCreate a token (opens in browser): https://dash.cloudflare.com/profile/api-tokens")
    print("  Permissions needed: 'Account → Zero Trust: Read' + 'Account → Access: Apps and Policies: Read'\n")

    try:
        import webbrowser
        if input("Open the API tokens page in your browser now? [Y/n] ").strip().lower() not in ("n", "no"):
            webbrowser.open("https://dash.cloudflare.com/profile/api-tokens")
    except Exception:
        pass

    token = input("\nPaste your CLOUDFLARE_API_TOKEN: ").strip()
    if not token:
        print("❌ No token provided. Aborted.")
        return 1

    account = input("CLOUDFLARE_ACCOUNT_ID (leave blank to auto-discover): ").strip()

    lines = [
        "# Cloudflare Topology — generated by `python main.py --setup`",
        f"CLOUDFLARE_API_TOKEN={token}",
    ]
    if account:
        lines.append(f"CLOUDFLARE_ACCOUNT_ID={account}")
    env_path.write_text("\n".join(lines) + "\n")
    try:
        env_path.chmod(0o600)
    except OSError:
        pass

    print(f"\n✅ Wrote {env_path.absolute()} (chmod 600)")
    print("Next:  python main.py")
    return 0


def _fetch_for_accounts(
    source_kind: str,
    config: Config,
    *,
    include_tunnel_configs: bool,
    include_devices: bool,
    include_gateway_rules: bool,
    logger: logging.Logger,
) -> CloudflareTopology:
    """Fetch topology for one or more Cloudflare accounts and merge when multiple."""
    account_ids = config.resolved_account_ids
    if len(account_ids) <= 1:
        if account_ids:
            config.account_id = account_ids[0]
        source = create_source(source_kind, config)
        if config.account_id and source_kind != "demo":
            logger.info(f"Account ID: {config.account_id}")
        return source.fetch_topology(
            include_tunnel_configs=include_tunnel_configs,
            include_app_policies=True,
            include_devices=include_devices,
            include_gateway_rules=include_gateway_rules,
        )

    combined: CloudflareTopology | None = None
    for acc_id in account_ids:
        logger.info(f"Account ID: {acc_id}")
        acc_cfg = replace(config, account_id=acc_id, account_ids=[acc_id])
        source = create_source(source_kind, acc_cfg)
        part = source.fetch_topology(
            include_tunnel_configs=include_tunnel_configs,
            include_app_policies=True,
            include_devices=include_devices,
            include_gateway_rules=include_gateway_rules,
        )
        combined = part if combined is None else combined.merge(part)

    assert combined is not None
    return combined


def export_topology_json(
    target_path: str,
    source_kind: str,
    topology: CloudflareTopology,
    graph_builder: NetworkGraphBuilder,
) -> Path:
    """Atomically write topology + graph JSON export to target_path."""
    json_target = Path(target_path)
    json_dir = json_target.parent if str(json_target.parent) else Path(".")
    json_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_json = tempfile.mkstemp(
        prefix=f".{json_target.stem}.",
        suffix=".json",
        dir=str(json_dir),
    )
    os.close(fd)
    try:
        export_payload: Dict[str, Any] = {
            "version": __version__,
            "source": source_kind,
            "topology": topology.to_dict(),
            "graph": graph_builder.to_dict(),
        }
        Path(tmp_json).write_text(
            json.dumps(export_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_json, str(json_target))
        return json_target.absolute()
    except Exception:
        try:
            os.unlink(tmp_json)
        except OSError:
            pass
        raise


def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.setup:
        return run_setup()

    # Setup logging
    setup_logging(args.debug)
    logger = logging.getLogger(__name__)

    logger.info("🌐 Cloudflare Network Topology Mapper")
    logger.info("=" * 50)

    # Resolve which data source to use (CLI flag wins over --demo and TOPOLOGY_SOURCE)
    source_kind = resolve_source_kind(args.source, demo=args.demo)

    try:
        if args.config:
            config = Config.from_file(args.config, require_auth=(source_kind != "demo"))
        elif source_kind == "demo":
            config = Config(api_token="demo", account_id="demo-account")
        else:
            config = Config.from_env()

        if args.debug:
            config.debug = True
        if args.output:
            config.output_file = args.output
        if args.mcp_url:
            config.mcp_url = args.mcp_url
        if args.no_physics:
            config.physics_enabled = False
        if args.account_ids:
            cli_accounts = [
                part.strip()
                for raw in args.account_ids
                for part in raw.split(",")
                if part.strip()
            ]
            if cli_accounts:
                config.account_ids = cli_accounts
                config.account_id = cli_accounts[0]

        if source_kind == "demo":
            logger.info("🎭 Demo mode — using synthetic data (no Cloudflare API calls)")
        elif source_kind == "mcp":
            logger.info(f"📡 Fetching topology via Cloudflare MCP server: {config.mcp_url}")
        else:
            logger.info("📡 Fetching topology data from Cloudflare API...")

        include_gateway = bool(args.include_gateway and not args.no_gateway)

        # Fetch topology data (supports single or multi-account aggregation)
        topology = _fetch_for_accounts(
            source_kind,
            config,
            include_tunnel_configs=not args.no_tunnel_configs,
            include_devices=not args.no_devices,
            include_gateway_rules=include_gateway,
            logger=logger,
        )

        # Print summary
        logger.info("")
        logger.info("📊 Resources Found:")
        logger.info(f"   Tunnels:           {len(topology.tunnels)}")
        logger.info(f"   Applications:      {len(topology.applications)}")
        logger.info(f"   Policies:          {len(topology.policies)}")
        logger.info(f"   Groups:            {len(topology.groups)}")
        logger.info(f"   Identity Providers: {len(topology.identity_providers)}")
        logger.info(f"   Virtual Networks:  {len(topology.virtual_networks)}")
        logger.info(f"   Routes:            {len(topology.routes)}")
        logger.info(f"   Devices:           {len(topology.devices)}")
        if include_gateway:
            logger.info(f"   Gateway Rules:     {len(topology.gateway_rules)}")
        logger.info("")

        # Build network graph
        logger.info("🔧 Building network graph...")
        graph_builder = NetworkGraphBuilder(config)
        graph_builder.build(topology)

        # Calculate node counts for UI
        node_counts = {
            'tunnel': len(topology.tunnels),
            'application': len(topology.applications),
            'policy': len(topology.policies),
            'group': len(topology.groups),
            'identity_provider': len(topology.identity_providers),
            'virtual_network': len(topology.virtual_networks),
            'route': len(topology.routes),
            'device': len(topology.devices),
            'gateway_rule': len(topology.gateway_rules),
        }

        if args.export_json:
            exported_abs = export_topology_json(
                args.export_json, source_kind, topology, graph_builder,
            )
            logger.info(f"📄 Exported JSON to {exported_abs}")

        # Render to HTML
        logger.info("🎨 Rendering visualization...")
        renderer = TopologyRenderer(config)
        output_path = renderer.render(graph_builder, config.output_file, node_counts)

        # Success message
        output_abs = Path(output_path).absolute()
        logger.info("")
        logger.info("✅ Topology generated successfully!")
        logger.info(f"   Output: {output_abs}")
        logger.info(f"   Nodes:  {len(graph_builder.nodes)}")
        logger.info(f"   Edges:  {len(graph_builder.edges)}")

        # Open in browser
        if not args.no_browser:
            logger.info("")
            logger.info("🌍 Opening in browser...")
            webbrowser.open(f"file://{output_abs}")

        return 0

    except ValueError as e:
        logger.error(f"❌ Configuration error: {e}")
        return 1

    except CloudflareAPIError as e:
        logger.error(f"❌ Cloudflare API error: {e}")
        if e.errors:
            for error in e.errors:
                logger.error(f"   - {error.get('message', 'Unknown error')}")
        return 2

    except Exception as e:
        logger.exception(f"❌ Unexpected error: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
