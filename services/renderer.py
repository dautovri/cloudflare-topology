"""
HTML renderer for Cloudflare topology visualization using Pyvis.
"""

import logging
import json
from typing import Optional
from pathlib import Path

from pyvis.network import Network

from config import Config, NodeColors, VALID_NODE_TYPES
from services.network_graph import NetworkGraphBuilder, NodeMetadata, EdgeMetadata

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
            bgcolor="#1a1a2e",
            font_color="#ffffff",
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
        
        # Generate HTML
        net.write_html(output_path, notebook=False, open_browser=False)
        
        # Inject custom CSS and JavaScript
        self._inject_customizations(output_path, graph, node_counts)
        
        logger.info(f"Rendered topology with {len(graph.nodes)} nodes and {len(graph.edges)} edges")
        return output_path
    
    def _get_physics_options(self) -> str:
        """Get Pyvis physics configuration."""
        options = {
            "physics": {
                "enabled": self.config.physics_enabled,
                "stabilization": {
                    "enabled": self.config.physics_stabilization,
                    "iterations": 100,
                    "updateInterval": 25,
                },
                "barnesHut": {
                    "gravitationalConstant": -8000,
                    "centralGravity": 0.3,
                    "springLength": 150,
                    "springConstant": 0.04,
                    "damping": 0.09,
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
                "navigationButtons": True,
                "keyboard": {
                    "enabled": True,
                    "bindToWindow": True,
                },
            },
            "nodes": {
                "font": {
                    "size": 14,
                    "color": "#ffffff",
                },
                "borderWidth": 2,
                "borderWidthSelected": 4,
            },
            "edges": {
                "font": {
                    "size": 11,
                    "color": "#888888",
                    "strokeWidth": 0,
                    "background": "#1a1a2e",
                },
                "smooth": {
                    "enabled": True,
                    "type": "continuous",
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
        
        # Legend HTML (only show types that exist)
        legend_html = self._get_legend_html(node_counts)
        
        # Search box HTML (only show filter buttons for types that exist)
        search_html = self._get_search_html(node_counts)
        
        # Header HTML with branding and stats
        header_html = self._get_header_html(node_counts, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        # Inject CSS before </head>
        html_content = html_content.replace(
            "</head>",
            f"<style>{custom_css}</style></head>"
        )
        
        # Inject HTML elements before the network div
        html_content = html_content.replace(
            '<div id="mynetwork"',
            f'{header_html}{search_html}{legend_html}<div id="mynetwork"'
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
        return """
        * {
            box-sizing: border-box;
        }
        
        body {
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #1a1a2e;
            color: #ffffff;
        }
        
        #mynetwork {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
        }
        
        /* Search Box */
        .search-container {
            position: fixed;
            top: 20px;
            left: 20px;
            z-index: 1000;
            background: rgba(26, 26, 46, 0.95);
            padding: 15px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
            min-width: 300px;
            max-width: 400px;
            cursor: move;
        }
        
        .search-container h3 {
            margin: 0 0 10px 0;
            font-size: 14px;
            color: #888;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .search-input {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #333;
            border-radius: 8px;
            background: #16213e;
            color: #fff;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }
        
        .search-input:focus {
            border-color: #3b82f6;
        }
        
        .search-input::placeholder {
            color: #666;
        }
        
        .filter-buttons {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 10px;
        }
        
        .filter-btn {
            padding: 5px 10px;
            border: 1px solid #333;
            border-radius: 6px;
            background: #16213e;
            color: #888;
            font-size: 11px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .filter-btn:hover {
            border-color: #555;
            color: #fff;
        }
        
        .filter-btn.active {
            background: #3b82f6;
            border-color: #3b82f6;
            color: #fff;
        }
        
        .search-results {
            margin-top: 10px;
            max-height: 200px;
            overflow-y: auto;
            font-size: 12px;
        }
        
        .search-result-item {
            padding: 8px 10px;
            border-radius: 6px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: background 0.2s;
        }
        
        .search-result-item:hover {
            background: #16213e;
        }
        
        .result-type {
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            text-transform: uppercase;
        }
        
        .clear-btn {
            background: none;
            border: none;
            color: #666;
            cursor: pointer;
            font-size: 18px;
            padding: 0;
            line-height: 1;
        }
        
        .clear-btn:hover {
            color: #fff;
        }
        
        /* Legend */
        .legend-container {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 1000;
            background: rgba(26, 26, 46, 0.95);
            padding: 15px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
            max-width: 200px;
        }
        
        .legend-container h4 {
            margin: 0 0 10px 0;
            font-size: 12px;
            color: #888;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .legend-toggle {
            background: none;
            border: none;
            color: #888;
            cursor: pointer;
            font-size: 12px;
        }
        
        .legend-toggle:hover {
            color: #fff;
        }
        
        .legend-items {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        
        .legend-item {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 12px;
        }
        
        .legend-color {
            width: 16px;
            height: 16px;
            border-radius: 4px;
            flex-shrink: 0;
        }
        
        .legend-hidden {
            display: none;
        }
        
        /* Stats */
        .stats-container {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 1000;
            background: rgba(26, 26, 46, 0.95);
            padding: 12px 15px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
            font-size: 12px;
        }
        
        .stats-item {
            display: flex;
            justify-content: space-between;
            gap: 20px;
            margin-bottom: 4px;
        }
        
        .stats-item:last-child {
            margin-bottom: 0;
        }
        
        .stats-label {
            color: #888;
        }
        
        .stats-value {
            font-weight: 600;
        }
        
        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 6px;
        }
        
        ::-webkit-scrollbar-track {
            background: #16213e;
            border-radius: 3px;
        }
        
        ::-webkit-scrollbar-thumb {
            background: #333;
            border-radius: 3px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: #444;
        }
        
        /* Header */
        .header-container {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 1001;
            background: linear-gradient(180deg, rgba(26, 26, 46, 0.98) 0%, rgba(26, 26, 46, 0.9) 80%, rgba(26, 26, 46, 0) 100%);
            padding: 15px 20px 30px 20px;
            pointer-events: none;
        }
        
        .header-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
            pointer-events: auto;
        }
        
        .header-brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .header-logo {
            width: 32px;
            height: 32px;
        }
        
        .header-title {
            font-size: 18px;
            font-weight: 600;
            color: #fff;
            margin: 0;
        }
        
        .header-subtitle {
            font-size: 11px;
            color: #666;
            margin: 0;
        }
        
        .header-stats {
            display: flex;
            gap: 20px;
            align-items: center;
        }
        
        .stat-item {
            text-align: center;
        }
        
        .stat-value {
            font-size: 20px;
            font-weight: 700;
            color: #fff;
        }
        
        .stat-label {
            font-size: 10px;
            color: #666;
            text-transform: uppercase;
        }
        
        .header-timestamp {
            font-size: 10px;
            color: #555;
        }
        
        /* Adjust search container position */
        .search-container {
            top: 80px !important;
        }
        
        /* Mobile responsive */
        @media (max-width: 768px) {
            .search-container {
                left: 10px;
                right: 10px;
                min-width: auto;
                max-width: none;
                top: 70px !important;
            }
            
            .legend-container {
                bottom: 10px;
                right: 10px;
                left: 10px;
                max-width: none;
            }
            
            .header-stats {
                display: none;
            }
            
            .header-container {
                padding: 10px 15px 20px 15px;
            }
        }
        """
    
    def _get_header_html(self, node_counts: dict, timestamp: str) -> str:
        """Get header HTML with branding and stats."""
        total_resources = sum(node_counts.values())
        
        # Cloudflare orange logo SVG
        logo_svg = '''<svg class="header-logo" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M22.8 17.6L21.3 22.5C21.2 22.8 21.4 23.1 21.7 23.2C21.8 23.2 21.9 23.2 22 23.2H27.5C27.8 23.2 28 23 28 22.7C28 22.6 28 22.5 27.9 22.4L25.6 17.6C25.5 17.4 25.2 17.3 25 17.4C24.9 17.4 24.8 17.5 24.8 17.6L23.7 20.4L22.5 17.6C22.4 17.4 22.1 17.3 21.9 17.4C22 17.4 21.9 17.5 22.8 17.6Z" fill="#F6821F"/>
            <path d="M24.7 14.1C24.5 14.1 24.4 14 24.3 13.8C23.7 11.3 21.4 9.5 18.7 9.5C16.5 9.5 14.6 10.7 13.7 12.5C13.6 12.7 13.4 12.8 13.2 12.7C12.9 12.6 12.6 12.5 12.3 12.5C10.5 12.5 9 14 9 15.8C9 15.9 9 16 9 16.1C9 16.3 8.9 16.4 8.7 16.4C6.6 16.7 5 18.5 5 20.7C5 23.1 6.9 25 9.3 25H24.7C26.5 25 28 23.5 28 21.7C28 19.9 26.5 18.4 24.7 18.4C24.5 18.4 24.4 18.3 24.3 18.1C24 16.8 24 15.4 24.3 14.2C24.4 14.1 24.5 14.1 24.7 14.1Z" fill="#F6821F"/>
        </svg>'''
        
        # Build stats items
        stats_html = ""
        stat_types = [
            ('tunnel', 'Tunnels'),
            ('application', 'Apps'),
            ('identity_provider', 'IdPs'),
            ('virtual_network', 'VNets'),
        ]
        
        for node_type, label in stat_types:
            count = node_counts.get(node_type, 0)
            if count > 0:
                stats_html += f'''
                <div class="stat-item">
                    <div class="stat-value">{count}</div>
                    <div class="stat-label">{label}</div>
                </div>'''
        
        return f"""
        <div class="header-container">
            <div class="header-content">
                <div class="header-brand">
                    {logo_svg}
                    <div>
                        <h1 class="header-title">Cloudflare Zero Trust Topology</h1>
                        <p class="header-subtitle">Network visualization • {total_resources} resources</p>
                    </div>
                </div>
                <div class="header-stats">
                    {stats_html}
                    <div class="header-timestamp">Updated: {timestamp}</div>
                </div>
            </div>
        </div>
        """
    
    def _get_search_html(self, node_counts: dict) -> str:
        """Get search box HTML with dynamic filter buttons."""
        # Only show filter buttons for types that have data
        filter_buttons = ['<button class="filter-btn active" data-type="all" role="button" aria-pressed="true" onclick="toggleFilter(\'all\')">All</button>']
        
        type_labels = {
            'tunnel': 'Tunnels',
            'application': 'Apps', 
            'policy': 'Policies',
            'group': 'Groups',
            'identity_provider': 'IdPs',
            'virtual_network': 'VNets',
            'route': 'Routes',
            'device': 'Devices',
        }
        
        for node_type, label in type_labels.items():
            count = node_counts.get(node_type, 0)
            if count > 0:
                filter_buttons.append(
                    f'<button class="filter-btn" data-type="{node_type}" role="button" aria-pressed="false" onclick="toggleFilter(\'{node_type}\')">{label} ({count})</button>'
                )
        
        buttons_html = '\n                '.join(filter_buttons)
        
        return f"""
        <div class="search-container" id="searchContainer">
            <h3>
                <span aria-hidden="true">🔍</span> Search & Filter
                <button class="clear-btn" onclick="clearSearch()" aria-label="Clear search">×</button>
            </h3>
            <input 
                type="text" 
                class="search-input" 
                id="searchInput" 
                aria-label="Search nodes by name, domain, or type"
                placeholder="Search by name, domain, type..."
                onkeyup="performSearch(this.value)"
            >
            <div class="filter-buttons" id="filterButtons">
                {buttons_html}
            </div>
            <div class="search-results" id="searchResults"></div>
        </div>
        """
    
    def _get_legend_html(self, node_counts: dict) -> str:
        """Get legend HTML showing only types that exist."""
        legend_items = [
            ('tunnel', NodeColors.TUNNEL, "Tunnel"),
            ('application', NodeColors.APPLICATION, "Application"),
            ('policy', NodeColors.POLICY, "Policy"),
            ('group', NodeColors.GROUP, "Group"),
            ('identity_provider', NodeColors.IDENTITY_PROVIDER, "Identity Provider"),
            ('virtual_network', NodeColors.VIRTUAL_NETWORK, "Virtual Network"),
            ('route', NodeColors.ROUTE, "Route"),
            ('device', NodeColors.DEVICE, "Device"),
        ]
        
        items_html = ""
        for node_type, color, label in legend_items:
            count = node_counts.get(node_type, 0)
            if count > 0:
                items_html += f"""
                <div class="legend-item">
                    <div class="legend-color" style="background: {color};" role="img" aria-label="{label} color swatch"></div>
                    <span>{label}</span>
                    <span style="color: #555; margin-left: auto;">{count}</span>
                </div>
            """
        
        if not items_html:
            items_html = '<div class="legend-item" style="color: #666;">No resources found</div>'
        
        return f"""
        <div class="legend-container" id="legendContainer">
            <h4>
                <span>Legend</span>
                <button class="legend-toggle" onclick="toggleLegend()" aria-label="Toggle legend visibility">Hide</button>
            </h4>
            <div class="legend-items" id="legendItems">
                {items_html}
            </div>
        </div>
        """
    
    def _get_custom_js(self, node_data: list) -> str:
        """Get custom JavaScript for interactivity."""
        node_data_json = json.dumps(node_data)
        
        return f"""
        // Node data for search
        const nodeData = {node_data_json};
        let activeFilter = 'all';
        let selectedNodes = new Set();
        
        // Wait for network to be ready
        document.addEventListener('DOMContentLoaded', function() {{
            initializeSearch();
            initializeDragFunctionality();
            updateStats();
        }});
        
        function initializeSearch() {{
            const searchInput = document.getElementById('searchInput');
            if (searchInput) {{
                searchInput.focus();
            }}
        }}
        
        function performSearch(query) {{
            const resultsContainer = document.getElementById('searchResults');
            if (!resultsContainer) return;
            
            query = query.toLowerCase().trim();
            
            if (!query) {{
                resultsContainer.innerHTML = '';
                resetHighlighting();
                return;
            }}
            
            // Filter nodes
            let results = nodeData.filter(node => {{
                // Apply type filter
                if (activeFilter !== 'all' && node.type !== activeFilter) {{
                    return false;
                }}
                
                // Search in label
                if (node.label.toLowerCase().includes(query)) return true;
                
                // Search in type
                if (node.type.toLowerCase().includes(query)) return true;
                
                // Search in properties
                for (const [key, value] of Object.entries(node.properties || {{}})) {{
                    if (typeof value === 'string' && value.toLowerCase().includes(query)) return true;
                    if (Array.isArray(value) && value.some(v => String(v).toLowerCase().includes(query))) return true;
                }}
                
                return false;
            }});
            
            // Limit results
            results = results.slice(0, 20);
            
            // Render results
            if (results.length === 0) {{
                resultsContainer.innerHTML = '<div style="color: #666; padding: 10px;">No results found</div>';
            }} else {{
                resultsContainer.innerHTML = results.map(node => `
                    <div class="search-result-item" onclick="selectNode('${{node.id}}')">
                        <span class="result-type" style="background: ${{getTypeColor(node.type)}}">
                            ${{node.type}}
                        </span>
                        <span>${{highlightMatch(node.label, query)}}</span>
                    </div>
                `).join('');
            }}
            
            // Highlight matching nodes in graph
            highlightNodes(results.map(n => n.id));
        }}
        
        function getTypeColor(type) {{
            const colors = {{
                tunnel: '{NodeColors.TUNNEL}',
                application: '{NodeColors.APPLICATION}',
                policy: '{NodeColors.POLICY}',
                group: '{NodeColors.GROUP}',
                device: '{NodeColors.DEVICE}',
                virtual_network: '{NodeColors.VIRTUAL_NETWORK}',
                identity_provider: '{NodeColors.IDENTITY_PROVIDER}',
                route: '{NodeColors.ROUTE}',
            }};
            return colors[type] || '#6b7280';
        }}
        
        function highlightMatch(text, query) {{
            if (!query) return text;
            const regex = new RegExp(`(${{query}})`, 'gi');
            return text.replace(regex, '<strong style="color: #3b82f6;">$1</strong>');
        }}
        
        function toggleFilter(type) {{
            activeFilter = type;
            
            // Update button states
            document.querySelectorAll('.filter-btn').forEach(btn => {{
                const isActive = btn.dataset.type === type;
                btn.classList.toggle('active', isActive);
                btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            }});
            
            // Re-run search
            const searchInput = document.getElementById('searchInput');
            if (searchInput) {{
                performSearch(searchInput.value);
            }}
        }}
        
        function selectNode(nodeId) {{
            if (typeof network !== 'undefined') {{
                network.selectNodes([nodeId]);
                network.focus(nodeId, {{
                    scale: 1.5,
                    animation: {{
                        duration: 500,
                        easingFunction: 'easeInOutQuad'
                    }}
                }});
            }}
        }}
        
        function highlightNodes(nodeIds) {{
            if (typeof network !== 'undefined') {{
                // Get all node IDs
                const allNodes = network.body.data.nodes.getIds();
                const allEdges = network.body.data.edges.getIds();
                
                if (nodeIds.length === 0) {{
                    resetHighlighting();
                    return;
                }}
                
                // Dim non-matching nodes
                const nodeUpdates = allNodes.map(id => {{
                    const isMatch = nodeIds.includes(id);
                    return {{
                        id: id,
                        opacity: isMatch ? 1 : 0.2,
                    }};
                }});
                
                // Dim all edges
                const edgeUpdates = allEdges.map(id => ({{
                    id: id,
                    color: {{ opacity: 0.2 }},
                }}));
                
                network.body.data.nodes.update(nodeUpdates);
                network.body.data.edges.update(edgeUpdates);
            }}
        }}
        
        function resetHighlighting() {{
            if (typeof network !== 'undefined') {{
                const allNodes = network.body.data.nodes.getIds();
                const allEdges = network.body.data.edges.getIds();
                
                const nodeUpdates = allNodes.map(id => ({{
                    id: id,
                    opacity: 1,
                }}));
                
                const edgeUpdates = allEdges.map(id => ({{
                    id: id,
                    color: {{ opacity: 1 }},
                }}));
                
                network.body.data.nodes.update(nodeUpdates);
                network.body.data.edges.update(edgeUpdates);
            }}
        }}
        
        function clearSearch() {{
            const searchInput = document.getElementById('searchInput');
            const resultsContainer = document.getElementById('searchResults');
            
            if (searchInput) searchInput.value = '';
            if (resultsContainer) resultsContainer.innerHTML = '';
            
            resetHighlighting();
            
            if (typeof network !== 'undefined') {{
                network.unselectAll();
            }}
        }}
        
        function toggleLegend() {{
            const legendItems = document.getElementById('legendItems');
            const toggleBtn = document.querySelector('.legend-toggle');
            
            if (legendItems.classList.contains('legend-hidden')) {{
                legendItems.classList.remove('legend-hidden');
                toggleBtn.textContent = 'Hide';
            }} else {{
                legendItems.classList.add('legend-hidden');
                toggleBtn.textContent = 'Show';
            }}
        }}
        
        function initializeDragFunctionality() {{
            const container = document.getElementById('searchContainer');
            if (!container) return;
            
            let isDragging = false;
            let offsetX, offsetY;
            
            container.addEventListener('mousedown', function(e) {{
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON') return;
                
                isDragging = true;
                offsetX = e.clientX - container.offsetLeft;
                offsetY = e.clientY - container.offsetTop;
                container.style.cursor = 'grabbing';
            }});
            
            document.addEventListener('mousemove', function(e) {{
                if (!isDragging) return;
                
                container.style.left = (e.clientX - offsetX) + 'px';
                container.style.top = (e.clientY - offsetY) + 'px';
                container.style.right = 'auto';
            }});
            
            document.addEventListener('mouseup', function() {{
                isDragging = false;
                container.style.cursor = 'move';
            }});
        }}
        
        function updateStats() {{
            // Count nodes by type
            const counts = {{}};
            nodeData.forEach(node => {{
                counts[node.type] = (counts[node.type] || 0) + 1;
            }});
            
            // Create stats container if it doesn't exist
            let statsContainer = document.querySelector('.stats-container');
            if (!statsContainer) {{
                statsContainer = document.createElement('div');
                statsContainer.className = 'stats-container';
                document.body.appendChild(statsContainer);
            }}
            
            statsContainer.innerHTML = `
                <div class="stats-item">
                    <span class="stats-label">Total Nodes</span>
                    <span class="stats-value">${{nodeData.length}}</span>
                </div>
                <div class="stats-item">
                    <span class="stats-label">Tunnels</span>
                    <span class="stats-value">${{counts.tunnel || 0}}</span>
                </div>
                <div class="stats-item">
                    <span class="stats-label">Applications</span>
                    <span class="stats-value">${{counts.application || 0}}</span>
                </div>
                <div class="stats-item">
                    <span class="stats-label">Policies</span>
                    <span class="stats-value">${{counts.policy || 0}}</span>
                </div>
            `;
        }}
        
        // Neighbourhood highlight on click
        if (typeof network !== 'undefined') {{
            network.on('click', function(params) {{
                if (params.nodes.length > 0) {{
                    const nodeId = params.nodes[0];
                    const connectedNodes = network.getConnectedNodes(nodeId);
                    const connectedEdges = network.getConnectedEdges(nodeId);
                    
                    // Highlight selected node and connected nodes
                    const highlightIds = [nodeId, ...connectedNodes];
                    highlightNodes(highlightIds);
                }} else {{
                    resetHighlighting();
                }}
            }});
            
            network.on('doubleClick', function(params) {{
                if (params.nodes.length > 0) {{
                    network.focus(params.nodes[0], {{
                        scale: 1.5,
                        animation: true
                    }});
                }}
            }});
        }}
        """
