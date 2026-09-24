"""Tests for TopologyRenderer."""

from pathlib import Path
import tempfile
import pytest

from config import Config
from services.network_graph import NetworkGraphBuilder
from services.renderer import TopologyRenderer
from services.demo_data import build_demo_topology


@pytest.fixture
def mock_config():
    """Create a Config for testing."""
    return Config(
        api_token="test-token",
        account_id="test-account",
    )


class TestTopologyRenderer:
    """Tests for TopologyRenderer."""

    def test_get_custom_css_loads_file(self, mock_config):
        """Test custom CSS is read from assets/style.css."""
        renderer = TopologyRenderer(mock_config)
        css = renderer._get_custom_css()
        assert ":root" in css
        assert "--bg-base" in css
        assert "search-container" in css

    def test_get_custom_js_loads_file_and_replaces_tokens(self, mock_config):
        """Test custom JS is read and tokens are substituted."""
        renderer = TopologyRenderer(mock_config)
        node_data = [{"id": "node-1", "label": "Test Node", "type": "tunnel", "properties": {}}]
        js = renderer._get_custom_js(node_data)
        
        assert "__NODE_DATA__" not in js
        assert "__NODE_COLORS__" not in js
        assert "node-1" in js
        assert "Test Node" in js
        assert "performSearch" in js

    def test_render_generates_html(self, mock_config):
        """Test rendering demo graph to HTML."""
        topology = build_demo_topology()
        graph = NetworkGraphBuilder()
        graph.build(topology)

        renderer = TopologyRenderer(mock_config)
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "topology.html"
            rendered_path = renderer.render(graph, output_path=str(output_file))

            assert Path(rendered_path).is_file()
            content = output_file.read_text(encoding="utf-8")
            assert "<html lang=\"en\">" in content
            assert "Cloudflare Zero Trust Topology" in content
            assert "mynetwork" in content
            assert "performSearch" in content
            assert ":root" in content
