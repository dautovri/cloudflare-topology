// Cloudflare Zero Trust Network Topology Controller

const nodeData = __NODE_DATA__;
let activeFilter = 'all';
let selectedNodeId = null;
let physicsEnabled = true;

// Build fast lookup map for node metadata
const nodeMap = new Map();
nodeData.forEach(node => nodeMap.set(node.id, node));

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    initializeSearch();
    initializeDragFunctionality();
    initializeKeyboardShortcuts();
});

// --------------------------------------------------------------------------
// Search & Filter
// --------------------------------------------------------------------------
function initializeSearch() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            performSearch(this.value);
        });
    }
}

function performSearch(query) {
    const resultsContainer = document.getElementById('searchResults');
    if (!resultsContainer) return;
    
    query = (query || '').toLowerCase().trim();
    
    if (!query && activeFilter === 'all') {
        resultsContainer.innerHTML = '';
        if (!selectedNodeId) {
            resetHighlighting();
        }
        return;
    }
    
    const results = nodeData.filter(node => {
        // Filter by category
        if (activeFilter !== 'all' && node.type !== activeFilter) {
            return false;
        }
        
        if (!query) return true;
        
        // Match label
        if (node.label && node.label.toLowerCase().includes(query)) return true;
        
        // Match type
        if (node.type && node.type.toLowerCase().includes(query)) return true;
        
        // Match properties
        for (const [key, value] of Object.entries(node.properties || {})) {
            if (typeof value === 'string' && value.toLowerCase().includes(query)) return true;
            if (Array.isArray(value) && value.some(v => String(v).toLowerCase().includes(query))) return true;
        }
        
        return false;
    });
    
    const displayResults = results.slice(0, 25);
    
    if (displayResults.length === 0) {
        resultsContainer.innerHTML = '<div style="color: var(--text-tertiary); padding: 10px; text-align: center;">No matching resources found</div>';
    } else {
        resultsContainer.innerHTML = displayResults.map(node => {
            const color = getTypeColor(node.type);
            const highlighted = highlightMatch(node.label, query);
            const subtitle = getNodeSubtitle(node);
            
            return `
                <div class="search-result-item" onclick="selectAndFocusNode('${node.id}')" role="button" tabindex="0">
                    <span class="result-type" style="background: ${color}">
                        ${formatTypeLabel(node.type)}
                    </span>
                    <div style="flex: 1; min-width: 0;">
                        <div class="result-label">${highlighted}</div>
                        ${subtitle ? `<div style="font-size: 0.6875rem; color: var(--text-tertiary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${subtitle}</div>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }
    
    highlightNodes(results.map(n => n.id));
}

function getNodeSubtitle(node) {
    const props = node.properties || {};
    if (props.domain) return props.domain;
    if (props.network) return props.network;
    if (props.status) return `Status: ${props.status}`;
    if (props.decision) return `Decision: ${props.decision}`;
    if (props.model) return props.model;
    return '';
}

function formatTypeLabel(type) {
    const labels = {
        tunnel: 'Tunnel',
        application: 'App',
        policy: 'Policy',
        group: 'Group',
        device: 'Device',
        virtual_network: 'VNet',
        identity_provider: 'IdP',
        route: 'Route',
    };
    return labels[type] || type;
}

function getTypeColor(type) {
    const colors = __NODE_COLORS__;
    return colors[type] || '#64748b';
}

function highlightMatch(text, query) {
    if (!query || !text) return text || '';
    const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
    return text.replace(regex, '<strong style="color: var(--cf-orange); font-weight: 700;">$1</strong>');
}

function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function toggleFilter(type) {
    activeFilter = type;
    
    document.querySelectorAll('.filter-btn').forEach(btn => {
        const isActive = btn.dataset.type === type;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
    
    const searchInput = document.getElementById('searchInput');
    performSearch(searchInput ? searchInput.value : '');
}

function clearSearch() {
    const searchInput = document.getElementById('searchInput');
    const resultsContainer = document.getElementById('searchResults');
    
    if (searchInput) searchInput.value = '';
    if (resultsContainer) resultsContainer.innerHTML = '';
    
    if (!selectedNodeId) {
        resetHighlighting();
        if (typeof network !== 'undefined') {
            network.unselectAll();
        }
    }
}

// --------------------------------------------------------------------------
// Node Selection & Inspector Drawer
// --------------------------------------------------------------------------
function selectAndFocusNode(nodeId) {
    selectedNodeId = nodeId;
    if (typeof network !== 'undefined') {
        network.selectNodes([nodeId]);
        network.focus(nodeId, {
            scale: 1.4,
            animation: {
                duration: 500,
                easingFunction: 'easeInOutQuad'
            }
        });
    }
    openInspector(nodeId);
    highlightNodeAndNeighbors(nodeId);
}

function openInspector(nodeId) {
    const drawer = document.getElementById('inspectorDrawer');
    const node = nodeMap.get(nodeId);
    if (!drawer || !node) return;
    
    selectedNodeId = nodeId;
    
    const typeEl = document.getElementById('inspectorType');
    const statusEl = document.getElementById('inspectorStatus');
    const titleEl = document.getElementById('inspectorTitle');
    const overviewEl = document.getElementById('inspectorOverview');
    const propsEl = document.getElementById('inspectorProperties');
    
    if (typeEl) {
        typeEl.textContent = formatTypeLabel(node.type);
        typeEl.style.background = getTypeColor(node.type);
    }
    
    const props = node.properties || {};
    const status = props.status || props.decision || (props.enabled !== undefined ? (props.enabled ? 'Enabled' : 'Disabled') : 'Active');
    
    if (statusEl) {
        statusEl.textContent = status;
        statusEl.style.color = (status === 'healthy' || status === 'allow' || status === 'Enabled' || status === 'Active') 
            ? 'var(--accent-green)' 
            : (status === 'down' || status === 'deny' ? 'var(--accent-red)' : 'var(--text-secondary)');
    }
    
    if (titleEl) {
        titleEl.textContent = node.label || node.id;
    }
    
    // Overview details
    if (overviewEl) {
        let detailsHtml = `
            <div class="inspector-property-row">
                <span class="inspector-prop-key">Resource ID</span>
                <span class="inspector-prop-val" title="${node.id}">${node.id}</span>
            </div>
            <div class="inspector-property-row">
                <span class="inspector-prop-key">Type</span>
                <span class="inspector-prop-val">${node.type}</span>
            </div>
        `;
        
        if (props.domain) {
            detailsHtml += `
                <div class="inspector-property-row">
                    <span class="inspector-prop-key">Domain</span>
                    <span class="inspector-prop-val" title="${props.domain}">${props.domain}</span>
                </div>
            `;
        }
        
        if (props.network) {
            detailsHtml += `
                <div class="inspector-property-row">
                    <span class="inspector-prop-key">Network CIDR</span>
                    <span class="inspector-prop-val">${props.network}</span>
                </div>
            `;
        }
        
        if (props.ingress_rules && Array.isArray(props.ingress_rules)) {
            const rulesSummary = props.ingress_rules.filter(r => r.hostname).map(r => r.hostname).join(', ') || 'Default';
            detailsHtml += `
                <div class="inspector-property-row">
                    <span class="inspector-prop-key">Ingress Hosts</span>
                    <span class="inspector-prop-val" title="${rulesSummary}">${rulesSummary}</span>
                </div>
            `;
        }
        
        overviewEl.innerHTML = detailsHtml;
    }
    
    // Key/Value Properties Table
    if (propsEl) {
        const entries = Object.entries(props).filter(([k]) => k !== 'status');
        if (entries.length === 0) {
            propsEl.innerHTML = '<span style="color: var(--text-tertiary);">No additional properties</span>';
        } else {
            propsEl.innerHTML = entries.map(([key, val]) => {
                let displayVal = typeof val === 'object' ? JSON.stringify(val) : String(val);
                return `
                    <div class="inspector-property-row">
                        <span class="inspector-prop-key">${formatPropKey(key)}</span>
                        <span class="inspector-prop-val" title="${displayVal}">${displayVal}</span>
                    </div>
                `;
            }).join('');
        }
    }
    
    drawer.classList.add('open');
}

function closeInspector() {
    const drawer = document.getElementById('inspectorDrawer');
    if (drawer) {
        drawer.classList.remove('open');
    }
    selectedNodeId = null;
    resetHighlighting();
    if (typeof network !== 'undefined') {
        network.unselectAll();
    }
}

function formatPropKey(key) {
    return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function focusCurrentNode() {
    if (selectedNodeId && typeof network !== 'undefined') {
        network.focus(selectedNodeId, {
            scale: 1.6,
            animation: {
                duration: 600,
                easingFunction: 'easeInOutQuad'
            }
        });
    }
}

function highlightCurrentNeighbors() {
    if (selectedNodeId) {
        highlightNodeAndNeighbors(selectedNodeId);
    }
}

function copyCurrentNodeId() {
    if (!selectedNodeId) return;
    navigator.clipboard.writeText(selectedNodeId).then(() => {
        showToast(`Copied ID to clipboard: ${selectedNodeId}`);
    }).catch(() => {
        showToast(`Resource ID: ${selectedNodeId}`);
    });
}

function showToast(message) {
    const toast = document.getElementById('toastNotification');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => {
        toast.classList.remove('show');
    }, 2800);
}

// --------------------------------------------------------------------------
// Graph Highlighting & Interaction
// --------------------------------------------------------------------------
function highlightNodeAndNeighbors(nodeId) {
    if (typeof network === 'undefined') return;
    
    const connectedNodes = network.getConnectedNodes(nodeId);
    const connectedEdges = network.getConnectedEdges(nodeId);
    const allNodeIds = [nodeId, ...connectedNodes];
    
    highlightNodes(allNodeIds, connectedEdges);
}

function highlightNodes(nodeIds, edgeIds = null) {
    if (typeof network === 'undefined') return;
    
    const allNodes = network.body.data.nodes.getIds();
    const allEdges = network.body.data.edges.getIds();
    
    if (nodeIds.length === 0) {
        resetHighlighting();
        return;
    }
    
    const nodeUpdates = allNodes.map(id => ({
        id: id,
        opacity: nodeIds.includes(id) ? 1.0 : 0.15,
    }));
    
    const edgeUpdates = allEdges.map(id => {
        const isMatch = edgeIds ? edgeIds.includes(id) : false;
        return {
            id: id,
            color: { opacity: isMatch ? 0.9 : 0.1 },
        };
    });
    
    network.body.data.nodes.update(nodeUpdates);
    network.body.data.edges.update(edgeUpdates);
}

function resetHighlighting() {
    if (typeof network === 'undefined') return;
    
    const allNodes = network.body.data.nodes.getIds();
    const allEdges = network.body.data.edges.getIds();
    
    const nodeUpdates = allNodes.map(id => ({
        id: id,
        opacity: 1.0,
    }));
    
    const edgeUpdates = allEdges.map(id => ({
        id: id,
        color: { opacity: 0.8 },
    }));
    
    network.body.data.nodes.update(nodeUpdates);
    network.body.data.edges.update(edgeUpdates);
}

// --------------------------------------------------------------------------
// Canvas Toolbar Actions
// --------------------------------------------------------------------------
function zoomIn() {
    if (typeof network !== 'undefined') {
        const scale = network.getScale();
        network.moveTo({ scale: scale * 1.35, animation: { duration: 300 } });
    }
}

function zoomOut() {
    if (typeof network !== 'undefined') {
        const scale = network.getScale();
        network.moveTo({ scale: scale / 1.35, animation: { duration: 300 } });
    }
}

function fitGraphView() {
    if (typeof network !== 'undefined') {
        network.fit({
            animation: {
                duration: 600,
                easingFunction: 'easeInOutQuad'
            }
        });
    }
}

function togglePhysics() {
    if (typeof network === 'undefined') return;
    
    physicsEnabled = !physicsEnabled;
    network.setOptions({ physics: { enabled: physicsEnabled } });
    
    const textEl = document.getElementById('physicsStatusText');
    const headerBtn = document.getElementById('physicsHeaderBtn');
    const toolbarBtn = document.getElementById('toolbarPhysicsBtn');
    
    if (textEl) {
        textEl.textContent = physicsEnabled ? 'Pause' : 'Resume';
    }
    if (headerBtn) {
        headerBtn.classList.toggle('active', !physicsEnabled);
    }
    if (toolbarBtn) {
        toolbarBtn.classList.toggle('active', !physicsEnabled);
    }
    
    showToast(physicsEnabled ? 'Layout physics resumed' : 'Layout physics paused (nodes frozen)');
}

function exportGraphPng() {
    if (typeof network === 'undefined') return;
    
    const canvas = document.querySelector('#mynetwork canvas');
    if (!canvas) {
        showToast('Canvas not available for export');
        return;
    }
    
    try {
        const imageUri = canvas.toDataURL('image/png');
        const link = document.createElement('a');
        link.download = `cloudflare-topology-${new Date().toISOString().slice(0, 10)}.png`;
        link.href = imageUri;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        showToast('Exported topology snapshot as PNG');
    } catch (err) {
        showToast('Export failed (canvas tainted by external images)');
    }
}

function toggleLegend() {
    const legendItems = document.getElementById('legendItems');
    const toggleBtn = document.querySelector('.legend-toggle');
    if (!legendItems) return;
    
    const isHidden = legendItems.classList.contains('legend-hidden');
    if (isHidden) {
        legendItems.classList.remove('legend-hidden');
        if (toggleBtn) toggleBtn.textContent = 'Hide';
    } else {
        legendItems.classList.add('legend-hidden');
        if (toggleBtn) toggleBtn.textContent = 'Show';
    }
}

function openShortcutsModal() {
    const modal = document.getElementById('shortcutsModal');
    if (modal) modal.classList.add('open');
}

function closeShortcutsModal(e) {
    if (e && e.target && e.target !== e.currentTarget && !e.target.classList.contains('inspector-close-btn')) {
        return;
    }
    const modal = document.getElementById('shortcutsModal');
    if (modal) modal.classList.remove('open');
}

// --------------------------------------------------------------------------
// Keyboard Shortcuts & Drag Functionality
// --------------------------------------------------------------------------
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        const isInput = e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA';
        
        // Escape: Close modals, drawer, or clear search
        if (e.key === 'Escape') {
            const modal = document.getElementById('shortcutsModal');
            if (modal && modal.classList.contains('open')) {
                closeShortcutsModal();
                return;
            }
            const drawer = document.getElementById('inspectorDrawer');
            if (drawer && drawer.classList.contains('open')) {
                closeInspector();
                return;
            }
            clearSearch();
            return;
        }
        
        // Global search shortcut: / or Cmd+K / Ctrl+K
        if ((e.key === '/' && !isInput) || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) {
            e.preventDefault();
            const searchInput = document.getElementById('searchInput');
            if (searchInput) {
                searchInput.focus();
                searchInput.select();
            }
            return;
        }
        
        // Non-input shortcuts
        if (!isInput) {
            if (e.key === 'f' || e.key === 'F') {
                e.preventDefault();
                fitGraphView();
            } else if (e.code === 'Space') {
                e.preventDefault();
                togglePhysics();
            } else if (e.key === 'e' || e.key === 'E') {
                e.preventDefault();
                exportGraphPng();
            } else if (e.key === 'l' || e.key === 'L') {
                e.preventDefault();
                toggleLegend();
            } else if (e.key === '?') {
                e.preventDefault();
                openShortcutsModal();
            }
        }
    });
}

function initializeDragFunctionality() {
    const container = document.getElementById('searchContainer');
    if (!container) return;
    
    let isDragging = false;
    let offsetX, offsetY;
    
    container.addEventListener('mousedown', function(e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON' || e.target.closest('.search-result-item') || e.target.closest('.filter-btn')) {
            return;
        }
        
        isDragging = true;
        offsetX = e.clientX - container.offsetLeft;
        offsetY = e.clientY - container.offsetTop;
        container.style.cursor = 'grabbing';
    });
    
    document.addEventListener('mousemove', function(e) {
        if (!isDragging) return;
        
        container.style.left = (e.clientX - offsetX) + 'px';
        container.style.top = (e.clientY - offsetY) + 'px';
        container.style.right = 'auto';
    });
    
    document.addEventListener('mouseup', function() {
        isDragging = false;
        container.style.cursor = 'move';
    });
}

// --------------------------------------------------------------------------
// Vis.js Network Event Bindings
// --------------------------------------------------------------------------
if (typeof network !== 'undefined') {
    network.on('click', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            openInspector(nodeId);
            highlightNodeAndNeighbors(nodeId);
        } else {
            closeInspector();
        }
    });
    
    network.on('doubleClick', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            network.focus(nodeId, {
                scale: 1.6,
                animation: {
                    duration: 500,
                    easingFunction: 'easeInOutQuad'
                }
            });
        }
    });
}
