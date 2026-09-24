"""
HTML renderer for Cloudflare topology visualization using Pyvis.
"""

import logging
import json
import os
import shutil
import tempfile
from typing import Optional
from pathlib import Path

from pyvis.network import Network

from config import Config, NodeColors
from services.network_graph import NetworkGraphBuilder

logger = logging.getLogger(__name__)


class TopologyRenderer:
    """Renders network graph as interactive HTML visualization."""
    
    def __init__(self, config: Config):
        self.config = config
    
    def render(
        self,
        graph: NetworkGraphBuilder,
        output_path: Optional[str] = None,
        node_counts: Optional[dict] = None,
    ) -> str:
        """
        Render the network graph to an interactive HTML file.
        
        Args:
            graph: NetworkGraphBuilder with nodes and edges
            output_path: Output file path (uses config default if not provided)
            node_counts: Dictionary of node type counts for dynamic legend/filters
        
        Returns:
            Path to the generated HTML file
        """
        output_path = output_path or self.config.output_file
        node_counts = node_counts or {}
        
        logger.info(f"Rendering topology to {output_path}...")
        
        # Create Pyvis network
        net = Network(
            height="100dvh",
            width="100%",
            bgcolor="#0a0e17",
            font_color="#f8fafc",
            directed=True,
            select_menu=False,
            filter_menu=False,
        )
        
        # Configure physics
        net.set_options(self._get_physics_options())
        
        # Add nodes
        for node in graph.get_node_list():
            net.add_node(
                node.node_id,
                label=node.label,
                color=node.color,
                shape=node.shape,
                size=node.size,
                title=node.title,
                group=node.node_type,
            )
        
        # Add edges
        for edge in graph.get_edge_list():
            net.add_edge(
                edge.source,
                edge.target,
                label=edge.label,
                color=edge.color or "#6b7280",
                dashes=edge.dashes,
                width=edge.width,
                title=edge.title,
                arrows="to",
            )
        
        # Generate HTML atomically: write to a temp file in the same directory,
        # inject customisations, then os.replace to the final path. Prevents
        # partial/empty files if the process is killed mid-write.
        final_path = Path(output_path)
        target_dir = final_path.parent if str(final_path.parent) else Path(".")
        target_dir.mkdir(parents=True, exist_ok=True)

        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=f".{final_path.stem}.",
            suffix=".html",
            dir=str(target_dir),
        )
        os.close(tmp_fd)  # pyvis opens by path

        try:
            net.write_html(tmp_path, notebook=False, open_browser=False)
            self._inject_customizations(tmp_path, graph, node_counts)
            os.replace(tmp_path, output_path)

            # Ensure vendored pyvis assets (lib/) exist in the target directory
            # if output_path is placed in a subdirectory (e.g., _deploy/ or build/)
            cwd_lib = Path.cwd() / "lib"
            target_lib = target_dir / "lib"
            if target_dir.resolve() != Path.cwd().resolve() and cwd_lib.is_dir():
                try:
                    if target_lib.exists():
                        shutil.rmtree(target_lib)
                    shutil.copytree(cwd_lib, target_lib)
                except Exception as e:
                    logger.debug(f"Could not copy lib/ to {target_lib}: {e}")
        except Exception:
            # Best-effort cleanup of temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        logger.info(f"Rendered topology with {len(graph.nodes)} nodes and {len(graph.edges)} edges")
        return output_path
    
    def _get_physics_options(self) -> str:
        """Get Pyvis physics configuration."""
        options = {
            "physics": {
                "enabled": self.config.physics_enabled,
                "stabilization": {
                    "enabled": self.config.physics_stabilization,
                    "iterations": 120,
                    "updateInterval": 25,
                    "fit": True,
                },
                "barnesHut": {
                    "gravitationalConstant": -8500,
                    "centralGravity": 0.25,
                    "springLength": 160,
                    "springConstant": 0.04,
                    "damping": 0.12,
                    "avoidOverlap": 0.35,
                },
            },
            "interaction": {
                "hover": True,
                "hoverConnectedEdges": True,
                "selectConnectedEdges": True,
                "multiselect": True,
                "dragNodes": True,
                "dragView": True,
                "zoomView": True,
                "navigationButtons": False,
                "keyboard": {
                    "enabled": False,
                },
                "tooltipDelay": 150,
            },
            "nodes": {
                "font": {
                    "size": 13,
                    "color": "#f8fafc",
                    "face": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
                    "strokeWidth": 3,
                    "strokeColor": "#0a0e17",
                },
                "borderWidth": 2,
                "borderWidthSelected": 4,
                "shadow": {
                    "enabled": True,
                    "color": "rgba(0, 0, 0, 0.5)",
                    "size": 8,
                    "x": 0,
                    "y": 3,
                },
            },
            "edges": {
                "font": {
                    "size": 11,
                    "color": "#94a3b8",
                    "face": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
                    "strokeWidth": 2,
                    "strokeColor": "#0a0e17",
                    "align": "middle",
                },
                "smooth": {
                    "enabled": True,
                    "type": "continuous",
                },
                "color": {
                    "color": "#334155",
                    "highlight": "#f6821f",
                    "hover": "#60a5fa",
                    "opacity": 0.8,
                },
            },
        }
        return json.dumps(options)
    
    def _inject_customizations(self, output_path: str, graph: NetworkGraphBuilder, node_counts: dict) -> None:
        """Inject custom CSS and JavaScript into the generated HTML."""
        from datetime import datetime
        
        with open(output_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # Remove empty h1 tags that pyvis adds
        html_content = html_content.replace('<center>\n<h1></h1>\n</center>', '')
        html_content = html_content.replace('<center>\n          <h1></h1>\n        </center>', '')

        # A11y + SEO + mobile: add lang, viewport, title, description, theme color.
        # Pyvis emits a bare <html> and empty <title>, which breaks mobile rendering
        # and leaves a blank browser tab.
        html_content = html_content.replace('<html>', '<html lang="en">', 1)
        meta_head = (
            '<title>Cloudflare Zero Trust Topology</title>'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            '<meta name="description" content="Interactive network topology for Cloudflare Zero Trust: tunnels, access apps, policies, identity providers, and private networks.">'
            '<meta name="color-scheme" content="dark">'
            '<meta name="theme-color" content="#1a1a2e">'
        )
        html_content = html_content.replace(
            '<meta charset="utf-8">',
            f'<meta charset="utf-8">{meta_head}',
            1,
        )
        
        # Remove Bootstrap (unused — custom CSS handles all styling)
        import re
        html_content = re.sub(
            r'<link[^>]*cdn\.jsdelivr\.net/npm/bootstrap[^>]*/>\s*', '', html_content
        )
        html_content = re.sub(
            r'<script[^>]*cdn\.jsdelivr\.net/npm/bootstrap[^>]*></script>\s*', '', html_content
        )
        
        # Prepare node metadata for search
        node_data = []
        for node in graph.get_node_list():
            node_data.append({
                "id": node.node_id,
                "label": node.label,
                "type": node.node_type,
                "properties": node.properties,
            })
        
        # Custom CSS
        custom_css = self._get_custom_css()
        
        # Custom JavaScript
        custom_js = self._get_custom_js(node_data)
        
        # Header HTML with branding and stats
        header_html = self._get_header_html(node_counts, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        # Search box HTML (only show filter buttons for types that exist)
        search_html = self._get_search_html(node_counts)

        # Legend HTML (only show types that exist)
        legend_html = self._get_legend_html(node_counts)

        # Inspector drawer HTML
        inspector_html = self._get_inspector_html()

        # Canvas toolbar dock HTML
        toolbar_html = self._get_toolbar_html()

        # Shortcuts modal & toast HTML
        shortcuts_html = self._get_shortcuts_html()
        
        # Inject CSS before </head>
        html_content = html_content.replace(
            "</head>",
            f"<style>{custom_css}</style></head>"
        )
        
        # Inject HTML elements before the network div
        html_content = html_content.replace(
            '<div id="mynetwork"',
            f'{header_html}{search_html}{legend_html}{inspector_html}{toolbar_html}{shortcuts_html}<div id="mynetwork"'
        )
        
        # Inject JavaScript before </body>
        html_content = html_content.replace(
            "</body>",
            f"<script>{custom_js}</script></body>"
        )
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
    
    def _get_custom_css(self) -> str:
        """Get custom CSS for the visualization."""
        css_file = Path(__file__).resolve().parent / "assets" / "style.css"
        if css_file.is_file():
            return css_file.read_text(encoding="utf-8")
        return ""
    
    def _get_header_html(self, node_counts: dict, timestamp: str) -> str:
        """Get header HTML with branding and summary line."""
        total_resources = sum(node_counts.values())

        # Cloudflare orange logo SVG
        logo_svg = '''<svg class="header-logo" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M22.8 17.6L21.3 22.5C21.2 22.8 21.4 23.1 21.7 23.2C21.8 23.2 21.9 23.2 22 23.2H27.5C27.8 23.2 28 23 28 22.7C28 22.6 28 22.5 27.9 22.4L25.6 17.6C25.5 17.4 25.2 17.3 25 17.4C24.9 17.4 24.8 17.5 24.8 17.6L23.7 20.4L22.5 17.6C22.4 17.4 22.1 17.3 21.9 17.4C22 17.4 21.9 17.5 22.8 17.6Z" fill="#F6821F"/>
            <path d="M24.7 14.1C24.5 14.1 24.4 14 24.3 13.8C23.7 11.3 21.4 9.5 18.7 9.5C16.5 9.5 14.6 10.7 13.7 12.5C13.6 12.7 13.4 12.8 13.2 12.7C12.9 12.6 12.6 12.5 12.3 12.5C10.5 12.5 9 14 9 15.8C9 15.9 9 16 9 16.1C9 16.3 8.9 16.4 8.7 16.4C6.6 16.7 5 18.5 5 20.7C5 23.1 6.9 25 9.3 25H24.7C26.5 25 28 23.5 28 21.7C28 19.9 26.5 18.4 24.7 18.4C24.5 18.4 24.4 18.3 24.3 18.1C24 16.8 24 15.4 24.3 14.2C24.4 14.1 24.5 14.1 24.7 14.1Z" fill="#F6821F"/>
        </svg>'''

        return f"""
        <header class="header-container">
            <div class="header-content">
                <div class="header-brand">
                    {logo_svg}
                    <div class="header-titles">
                        <div class="header-title-row">
                            <h1 class="header-title">Cloudflare Zero Trust Topology</h1>
                            <span class="header-badge">v0.2</span>
                        </div>
                        <p class="header-subtitle">
                            <span class="live-pulse" aria-hidden="true"></span>
                            <span>{total_resources} resources</span>
                            <span aria-hidden="true">&bull;</span>
                            <span>Updated {timestamp}</span>
                        </p>
                    </div>
                </div>
                <div class="header-actions">
                    <button class="header-btn" onclick="fitGraphView()" title="Fit all nodes to view (F)" aria-label="Fit graph to view">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
                        <span>Fit View</span>
                        <span class="kbd-hint">F</span>
                    </button>
                    <button class="header-btn" id="physicsHeaderBtn" onclick="togglePhysics()" title="Pause/Resume layout physics (Space)" aria-label="Toggle layout physics">
                        <svg id="physicsIconPause" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                        <span id="physicsStatusText">Pause</span>
                        <span class="kbd-hint">Space</span>
                    </button>
                    <button class="header-btn" onclick="openShortcutsModal()" title="Keyboard shortcuts (?)" aria-label="Show keyboard shortcuts">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                        <span class="kbd-hint">?</span>
                    </button>
                </div>
            </div>
        </header>
        """
    
    def _get_search_html(self, node_counts: dict) -> str:
        """Get search box HTML with dynamic filter buttons."""
        filter_buttons = [
            '<button class="filter-btn active" data-type="all" role="button" aria-pressed="true" onclick="toggleFilter(\'all\')">'
            '<span class="filter-dot" style="background: var(--cf-orange);"></span>All</button>'
        ]
        
        type_labels = [
            ('tunnel', 'Tunnels', NodeColors.TUNNEL),
            ('application', 'Apps', NodeColors.APPLICATION),
            ('policy', 'Policies', NodeColors.POLICY),
            ('group', 'Groups', NodeColors.GROUP),
            ('identity_provider', 'IdPs', NodeColors.IDENTITY_PROVIDER),
            ('virtual_network', 'VNets', NodeColors.VIRTUAL_NETWORK),
            ('route', 'Routes', NodeColors.ROUTE),
            ('device', 'Devices', NodeColors.DEVICE),
        ]
        
        for node_type, label, color in type_labels:
            count = node_counts.get(node_type, 0)
            if count > 0:
                filter_buttons.append(
                    f'<button class="filter-btn" data-type="{node_type}" role="button" aria-pressed="false" onclick="toggleFilter(\'{node_type}\')">'
                    f'<span class="filter-dot" style="background: {color};"></span>{label} ({count})</button>'
                )
        
        buttons_html = '\n                '.join(filter_buttons)
        
        return f"""
        <aside class="search-container" id="searchContainer" aria-label="Search and filter nodes">
            <div class="search-container-header">
                <span class="search-container-title">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    Search &amp; Filter
                </span>
                <span style="font-size: 0.6875rem; color: var(--text-tertiary);">Drag to move</span>
            </div>
            <div class="search-input-wrapper">
                <svg class="search-input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                <input 
                    type="text" 
                    class="search-input" 
                    id="searchInput" 
                    aria-label="Search nodes by name, domain, or type"
                    placeholder="Search name, domain, IP... (/)"
                    onkeyup="performSearch(this.value)"
                >
                <button class="clear-btn" onclick="clearSearch()" aria-label="Clear search and close" type="button">&times;</button>
            </div>
            <div class="filter-buttons" id="filterButtons">
                {buttons_html}
            </div>
            <div class="search-results" id="searchResults"></div>
        </aside>
        """
    
    def _get_legend_html(self, node_counts: dict) -> str:
        """Get legend HTML showing only types that exist with shape indicators."""
        shape_svgs = {
            'tunnel': lambda c: f'<svg class="legend-shape-badge" viewBox="0 0 24 24" fill="{c}"><polygon points="12,2 22,7.5 22,18.5 12,24 2,18.5 2,7.5"/></svg>',
            'application': lambda c: f'<svg class="legend-shape-badge" viewBox="0 0 24 24" fill="{c}"><circle cx="12" cy="12" r="9"/></svg>',
            'policy': lambda c: f'<svg class="legend-shape-badge" viewBox="0 0 24 24" fill="{c}"><polygon points="12,3 22,21 2,21"/></svg>',
            'group': lambda c: f'<svg class="legend-shape-badge" viewBox="0 0 24 24" fill="{c}"><circle cx="12" cy="12" r="7"/></svg>',
            'identity_provider': lambda c: f'<svg class="legend-shape-badge" viewBox="0 0 24 24" fill="{c}"><polygon points="12,2 15,9 22,9.5 17,14.5 18.5,21.5 12,18 5.5,21.5 7,14.5 2,9.5 9,9"/></svg>',
            'virtual_network': lambda c: f'<svg class="legend-shape-badge" viewBox="0 0 24 24" fill="{c}"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>',
            'route': lambda c: f'<svg class="legend-shape-badge" viewBox="0 0 24 24" fill="{c}"><circle cx="12" cy="12" r="8"/></svg>',
            'device': lambda c: f'<svg class="legend-shape-badge" viewBox="0 0 24 24" fill="{c}"><polygon points="12,2 22,12 12,22 2,12"/></svg>',
        }
        
        legend_items = [
            ('tunnel', NodeColors.TUNNEL, "Tunnel"),
            ('application', NodeColors.APPLICATION, "Application"),
            ('policy', NodeColors.POLICY, "Policy"),
            ('group', NodeColors.GROUP, "Group"),
            ('identity_provider', NodeColors.IDENTITY_PROVIDER, "IdP"),
            ('virtual_network', NodeColors.VIRTUAL_NETWORK, "Virtual Network"),
            ('route', NodeColors.ROUTE, "Route"),
            ('device', NodeColors.DEVICE, "Device"),
        ]
        
        items_html = ""
        for node_type, color, label in legend_items:
            count = node_counts.get(node_type, 0)
            if count > 0:
                shape_icon = shape_svgs.get(node_type, shape_svgs['application'])(color)
                items_html += f"""
                <div class="legend-item">
                    {shape_icon}
                    <span>{label}</span>
                    <span class="legend-item-count">{count}</span>
                </div>
                """
        
        if not items_html:
            items_html = '<div class="legend-item" style="color: var(--text-tertiary);">No resources found</div>'
        
        return f"""
        <div class="legend-container" id="legendContainer">
            <div class="legend-header">
                <span class="legend-title">Legend</span>
                <button class="legend-toggle" onclick="toggleLegend()" aria-label="Toggle legend visibility">Hide</button>
            </div>
            <div class="legend-items" id="legendItems">
                {items_html}
            </div>
        </div>
        """

    def _get_inspector_html(self) -> str:
        """Get slide-out node details inspector HTML."""
        return """
        <aside class="inspector-drawer" id="inspectorDrawer" aria-label="Node Details">
            <div class="inspector-header">
                <div style="flex: 1; min-width: 0;">
                    <div class="inspector-badge-row">
                        <span class="inspector-type-badge" id="inspectorType">Resource</span>
                        <span class="inspector-status-badge" id="inspectorStatus">Active</span>
                    </div>
                    <h2 class="inspector-title" id="inspectorTitle">Select a Node</h2>
                </div>
                <button class="inspector-close-btn" onclick="closeInspector()" aria-label="Close inspector panel">&times;</button>
            </div>
            <div class="inspector-body" id="inspectorBody">
                <div class="inspector-section">
                    <span class="inspector-section-title">Overview</span>
                    <div class="inspector-card" id="inspectorOverview">
                        <p style="color: var(--text-secondary); font-size: 0.8125rem;">Click on any node in the topology to inspect configuration, ingress rules, routes, and policies.</p>
                    </div>
                </div>
                <div class="inspector-section" id="inspectorPropertiesSection">
                    <span class="inspector-section-title">Properties</span>
                    <div class="inspector-card" id="inspectorProperties"></div>
                </div>
            </div>
            <div class="inspector-actions">
                <button class="inspector-btn inspector-btn-primary" onclick="focusCurrentNode()" id="btnFocusNode">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M3 12h3m12 0h3M12 3v3m0 12v3"/></svg>
                    Focus
                </button>
                <button class="inspector-btn inspector-btn-secondary" onclick="highlightCurrentNeighbors()" id="btnHighlightNeighbors">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>
                    Neighbors
                </button>
                <button class="inspector-btn inspector-btn-secondary" onclick="copyCurrentNodeId()" id="btnCopyId" title="Copy Resource ID">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                    Copy ID
                </button>
            </div>
        </aside>
        """

    def _get_toolbar_html(self) -> str:
        """Get floating canvas toolbar dock HTML."""
        return """
        <nav class="canvas-toolbar" aria-label="Canvas controls">
            <button class="toolbar-btn" onclick="zoomIn()" title="Zoom In (+)" aria-label="Zoom in">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
            </button>
            <button class="toolbar-btn" onclick="zoomOut()" title="Zoom Out (-)" aria-label="Zoom out">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
            </button>
            <button class="toolbar-btn" onclick="fitGraphView()" title="Fit to View (F)" aria-label="Fit graph">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
            </button>
            <div class="toolbar-divider"></div>
            <button class="toolbar-btn" id="toolbarPhysicsBtn" onclick="togglePhysics()" title="Toggle Physics (Space)" aria-label="Pause or resume physics">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
            </button>
            <button class="toolbar-btn" onclick="exportGraphPng()" title="Export PNG Snapshot (E)" aria-label="Export canvas snapshot as PNG">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
            </button>
            <div class="toolbar-divider"></div>
            <button class="toolbar-btn" onclick="toggleLegend()" title="Toggle Legend (L)" aria-label="Toggle legend">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
            </button>
            <button class="toolbar-btn" onclick="openShortcutsModal()" title="Keyboard Shortcuts (?)" aria-label="Keyboard shortcuts">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M6 8h.01M10 8h.01M14 8h.01M18 8h.01M6 12h.01M10 12h.01M14 12h.01M18 12h.01M7 16h10"/></svg>
            </button>
        </nav>
        """

    def _get_shortcuts_html(self) -> str:
        """Get keyboard shortcuts modal and toast notification HTML."""
        return """
        <div class="modal-backdrop" id="shortcutsModal" onclick="closeShortcutsModal(event)" role="dialog" aria-modal="true" aria-labelledby="shortcutsTitle">
            <div class="shortcuts-modal" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3 class="modal-title" id="shortcutsTitle">Keyboard Shortcuts</h3>
                    <button class="inspector-close-btn" onclick="closeShortcutsModal()" aria-label="Close modal">&times;</button>
                </div>
                <div class="shortcuts-grid">
                    <div class="shortcut-row"><span>Focus Search</span><span><kbd>/</kbd> or <kbd>⌘K</kbd></span></div>
                    <div class="shortcut-row"><span>Fit View to Canvas</span><span><kbd>F</kbd></span></div>
                    <div class="shortcut-row"><span>Pause / Resume Physics</span><span><kbd>Space</kbd></span></div>
                    <div class="shortcut-row"><span>Export PNG Snapshot</span><span><kbd>E</kbd></span></div>
                    <div class="shortcut-row"><span>Toggle Legend</span><span><kbd>L</kbd></span></div>
                    <div class="shortcut-row"><span>Close Panel / Clear</span><span><kbd>Esc</kbd></span></div>
                    <div class="shortcut-row"><span>Show Shortcuts Help</span><span><kbd>?</kbd></span></div>
                </div>
            </div>
        </div>
        <div class="toast-notification" id="toastNotification" role="status" aria-live="polite"></div>
        """
    
    def _get_custom_js(self, node_data: list) -> str:
        """Get custom JavaScript for interactivity."""
        node_data_json = json.dumps(node_data)
        colors_json = json.dumps({
            "tunnel": NodeColors.TUNNEL,
            "application": NodeColors.APPLICATION,
            "policy": NodeColors.POLICY,
            "group": NodeColors.GROUP,
            "device": NodeColors.DEVICE,
            "virtual_network": NodeColors.VIRTUAL_NETWORK,
            "identity_provider": NodeColors.IDENTITY_PROVIDER,
            "route": NodeColors.ROUTE,
        })
        js_file = Path(__file__).resolve().parent / "assets" / "topology.js"
        if js_file.is_file():
            content = js_file.read_text(encoding="utf-8")
            return content.replace("__NODE_DATA__", node_data_json).replace("__NODE_COLORS__", colors_json)
        return f"const nodeData = {node_data_json};"
