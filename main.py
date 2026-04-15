#!/usr/bin/env python3
"""
Cloudflare Network Topology Mapper

Generates an interactive network topology visualization of your
Cloudflare Zero Trust infrastructure.

Usage:
    python main.py [--debug] [--output FILE]

Environment Variables:
    CLOUDFLARE_API_TOKEN: Your Cloudflare API token
    CLOUDFLARE_ACCOUNT_ID: Your Cloudflare account ID
"""

import argparse
import logging
import sys
import webbrowser
from pathlib import Path

from config import Config
from services.cloudflare_api import CloudflareAPIClient, CloudflareAPIError
from services.network_graph import NetworkGraphBuilder
from services.renderer import TopologyRenderer


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
    CLOUDFLARE_API_TOKEN    Cloudflare API token (required)
    CLOUDFLARE_ACCOUNT_ID   Cloudflare account ID (required)
    DEBUG                   Enable debug mode (optional)
        """
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="network_topology.html",
        help="Output HTML file path (default: network_topology.html)",
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
    
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    # Setup logging
    setup_logging(args.debug)
    logger = logging.getLogger(__name__)
    
    logger.info("🌐 Cloudflare Network Topology Mapper")
    logger.info("=" * 50)
    
    try:
        # Load configuration from environment
        config = Config.from_env()
        config.debug = args.debug
        config.output_file = args.output
        
        logger.info(f"Account ID: {config.account_id}")
        
        # Initialize API client
        api_client = CloudflareAPIClient(config)
        
        # Fetch topology data
        logger.info("📡 Fetching topology data from Cloudflare API...")
        topology = api_client.fetch_topology(
            include_tunnel_configs=not args.no_tunnel_configs,
            include_app_policies=True,
            include_devices=not args.no_devices,
            include_gateway_rules=args.include_gateway,
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
        if args.include_gateway:
            logger.info(f"   Gateway Rules:     {len(topology.gateway_rules)}")
        logger.info("")
        
        # Build network graph
        logger.info("🔧 Building network graph...")
        graph_builder = NetworkGraphBuilder()
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
        }
        
        # Render to HTML
        logger.info("🎨 Rendering visualization...")
        renderer = TopologyRenderer(config)
        output_path = renderer.render(graph_builder, args.output, node_counts)
        
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
        logger.error("")
        logger.error("Make sure to set environment variables:")
        logger.error("  export CLOUDFLARE_API_TOKEN='your-token'")
        logger.error("  export CLOUDFLARE_ACCOUNT_ID='your-account-id'")
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
