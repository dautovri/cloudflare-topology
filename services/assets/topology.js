// Cloudflare Zero Trust Network Topology Controller

const nodeData = __NODE_DATA__;
let activeFilter = 'all';
let connectedOnly = false;
let statusFilter = null; // null | 'healthy' | 'unhealthy'
let hierarchicalEnabled = false;
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

    if (!query && activeFilter === 'all' && !connectedOnly && !statusFilter) {
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

        // Filter by connected nodes only
        if (connectedOnly && typeof network !== 'undefined') {
            const deg = (network.getConnectedNodes(node.id) || []).length;
            if (deg === 0) return false;
        }

        // Filter by health / status
        if (statusFilter) {
            const st = String((node.properties && (node.properties.status || node.properties.decision)) || '').toLowerCase();
            if (statusFilter === 'healthy') {
                if (st && st !== 'healthy' && st !== 'allow') return false;
                if (!st && node.type === 'tunnel') return false;
            } else if (statusFilter === 'unhealthy') {
                if (!['inactive', 'down', 'degraded', 'deny', 'block'].includes(st)) return false;
            }
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
            const color = escapeHtml(getTypeColor(node.type));
            const highlighted = highlightMatch(node.label, query);
            const subtitle = escapeHtml(getNodeSubtitle(node));
            const safeIdAttr = escapeHtml(String(node.id || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'"));

            return `
                <div class="search-result-item" onclick="selectAndFocusNode('${safeIdAttr}')" role="button" tabindex="0">
                    <span class="result-type" style="background: ${color}">
                        ${escapeHtml(formatTypeLabel(node.type))}
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
        gateway_rule: 'Gateway',
    };
    return labels[type] || type;
}

function getTypeColor(type) {
    const colors = __NODE_COLORS__;
    return colors[type] || '#64748b';
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function highlightMatch(text, query) {
    const safeText = escapeHtml(text || '');
    if (!query || !text) return safeText;
    const safeQuery = escapeHtml(query);
    const regex = new RegExp(`(${escapeRegex(safeQuery)})`, 'gi');
    return safeText.replace(regex, '<strong style="color: var(--cf-orange); font-weight: 700;">$1</strong>');
}

function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function toggleFilter(type) {
    if (activeFilter === type && type !== 'all') {
        activeFilter = 'all';
    } else {
        activeFilter = type;
    }

    document.querySelectorAll('.filter-btn').forEach(btn => {
        const isActive = btn.dataset.type === activeFilter;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });

    const searchInput = document.getElementById('searchInput');
    performSearch(searchInput ? searchInput.value : '');
}

function toggleConnectedOnly() {
    connectedOnly = !connectedOnly;
    const btn = document.getElementById('connectedOnlyBtn');
    if (btn) {
        btn.classList.toggle('active', connectedOnly);
        btn.setAttribute('aria-pressed', connectedOnly ? 'true' : 'false');
    }
    const searchInput = document.getElementById('searchInput');
    performSearch(searchInput ? searchInput.value : '');
}

function toggleStatusFilter(mode) {
    statusFilter = statusFilter === mode ? null : mode;
    const healthyBtn = document.getElementById('healthyOnlyBtn');
    const unhealthyBtn = document.getElementById('unhealthyOnlyBtn');
    if (healthyBtn) {
        const isH = statusFilter === 'healthy';
        healthyBtn.classList.toggle('active', isH);
        healthyBtn.setAttribute('aria-pressed', isH ? 'true' : 'false');
    }
    if (unhealthyBtn) {
        const isU = statusFilter === 'unhealthy';
        unhealthyBtn.classList.toggle('active', isU);
        unhealthyBtn.setAttribute('aria-pressed', isU ? 'true' : 'false');
    }
    const searchInput = document.getElementById('searchInput');
    performSearch(searchInput ? searchInput.value : '');
}

function clearSearch() {
    const searchInput = document.getElementById('searchInput');
    const resultsContainer = document.getElementById('searchResults');

    if (searchInput) searchInput.value = '';
    if (resultsContainer) resultsContainer.innerHTML = '';

    connectedOnly = false;
    statusFilter = null;
    ['connectedOnlyBtn', 'healthyOnlyBtn', 'unhealthyOnlyBtn'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.classList.remove('active');
            el.setAttribute('aria-pressed', 'false');
        }
    });

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
        const safeId = escapeHtml(node.id);
        const safeType = escapeHtml(node.type);
        let detailsHtml = `
            <div class="inspector-property-row">
                <span class="inspector-prop-key">Resource ID</span>
                <span class="inspector-prop-val" title="${safeId}">${safeId}</span>
            </div>
            <div class="inspector-property-row">
                <span class="inspector-prop-key">Type</span>
                <span class="inspector-prop-val">${safeType}</span>
            </div>
        `;

        if (props.domain) {
            const safeDomain = escapeHtml(props.domain);
            detailsHtml += `
                <div class="inspector-property-row">
                    <span class="inspector-prop-key">Domain</span>
                    <span class="inspector-prop-val" title="${safeDomain}">${safeDomain}</span>
                </div>
            `;
        }

        if (props.network) {
            const safeNetwork = escapeHtml(props.network);
            detailsHtml += `
                <div class="inspector-property-row">
                    <span class="inspector-prop-key">Network CIDR</span>
                    <span class="inspector-prop-val">${safeNetwork}</span>
                </div>
            `;
        }

        if (props.ingress_rules && Array.isArray(props.ingress_rules)) {
            const rulesSummary = escapeHtml(
                props.ingress_rules.filter(r => r.hostname).map(r => r.hostname).join(', ') || 'Default'
            );
            detailsHtml += `
                <div class="inspector-property-row">
                    <span class="inspector-prop-key">Ingress Hosts</span>
                    <span class="inspector-prop-val" title="${rulesSummary}">${rulesSummary}</span>
                </div>
            `;
        }

        overviewEl.innerHTML = detailsHtml;
    }

    // Connected Resources Section
    const connSectionEl = document.getElementById('inspectorConnectionsSection');
    const connTitleEl = document.getElementById('inspectorConnectionsTitle');
    const connListEl = document.getElementById('inspectorConnections');
    if (connSectionEl && connListEl && typeof network !== 'undefined') {
        const neighborIds = network.getConnectedNodes(nodeId) || [];
        if (neighborIds.length === 0) {
            connSectionEl.style.display = 'none';
            connListEl.innerHTML = '';
        } else {
            connSectionEl.style.display = 'flex';
            if (connTitleEl) {
                connTitleEl.textContent = `Connected Resources (${neighborIds.length})`;
            }
            connListEl.innerHTML = neighborIds.map(nId => {
                const neighbor = nodeMap.get(nId) || { id: nId, label: nId, type: 'resource' };
                const nColor = escapeHtml(getTypeColor(neighbor.type));
                const nType = escapeHtml(formatTypeLabel(neighbor.type));
                const nLabel = escapeHtml(neighbor.label || neighbor.id);
                const safeNIdAttr = escapeHtml(String(neighbor.id || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'"));
                return `
                    <button type="button" class="inspector-conn-item" onclick="selectAndFocusNode('${safeNIdAttr}')">
                        <span class="result-type" style="background: ${nColor}">${nType}</span>
                        <span class="inspector-conn-label" title="${nLabel}">${nLabel}</span>
                        <span class="inspector-conn-arrow">&rarr;</span>
                    </button>
                `;
            }).join('');
        }
    }

    // Key/Value Properties Table
    if (propsEl) {
        const entries = Object.entries(props).filter(([k, v]) => (
            k !== 'status' &&
            k !== 'ingress_rules' &&
            v !== null &&
            v !== undefined &&
            v !== '' &&
            !(Array.isArray(v) && v.length === 0)
        ));
        if (entries.length === 0) {
            propsEl.innerHTML = '<span style="color: var(--text-tertiary);">No additional properties</span>';
        } else {
            propsEl.innerHTML = entries.map(([key, val]) => {
                const safeKey = escapeHtml(formatPropKey(key));
                if (Array.isArray(val)) {
                    const tagsHtml = val.slice(0, 12).map(item => {
                        const text = typeof item === 'object' ? JSON.stringify(item) : String(item);
                        const safeItem = escapeHtml(text);
                        return `<span class="inspector-tag" title="${safeItem}">${safeItem}</span>`;
                    }).join('');
                    const moreCount = val.length > 12 ? `<span class="inspector-tag">+${val.length - 12} more</span>` : '';
                    return `
                        <div class="inspector-property-row inspector-property-row-stacked">
                            <span class="inspector-prop-key">${safeKey}</span>
                            <div class="inspector-tag-list">${tagsHtml}${moreCount}</div>
                        </div>
                    `;
                }
                const rawVal = typeof val === 'object' ? JSON.stringify(val) : String(val);
                const safeVal = escapeHtml(rawVal);
                return `
                    <div class="inspector-property-row">
                        <span class="inspector-prop-key">${safeKey}</span>
                        <span class="inspector-prop-val" title="${safeVal}">${safeVal}</span>
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

function exportGraphJson() {
    try {
        const edges = typeof network !== 'undefined' && network.body && network.body.data
            ? network.body.data.edges.get()
            : [];
        const payload = {
            exported_at: new Date().toISOString(),
            node_count: nodeData.length,
            edge_count: edges.length,
            nodes: nodeData,
            edges: edges,
        };
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.download = `cloudflare-topology-${new Date().toISOString().slice(0, 10)}.json`;
        link.href = url;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        showToast('Downloaded topology data as JSON');
    } catch (err) {
        showToast('Failed to export JSON');
    }
}

function toggleHierarchicalLayout() {
    if (typeof network === 'undefined') return;

    hierarchicalEnabled = !hierarchicalEnabled;
    if (hierarchicalEnabled) {
        network.setOptions({
            layout: {
                hierarchical: {
                    enabled: true,
                    direction: 'LR',
                    sortMethod: 'directed',
                    levelSeparation: 220,
                    nodeSpacing: 110,
                    treeSpacing: 160,
                },
            },
            physics: { enabled: false },
        });
        physicsEnabled = false;
    } else {
        network.setOptions({
            layout: { hierarchical: { enabled: false } },
            physics: { enabled: true },
        });
        physicsEnabled = true;
    }

    const layoutHeaderBtn = document.getElementById('layoutHeaderBtn');
    const toolbarLayoutBtn = document.getElementById('toolbarLayoutBtn');
    const layoutText = document.getElementById('layoutStatusText');
    if (layoutHeaderBtn) layoutHeaderBtn.classList.toggle('active', hierarchicalEnabled);
    if (toolbarLayoutBtn) toolbarLayoutBtn.classList.toggle('active', hierarchicalEnabled);
    if (layoutText) layoutText.textContent = hierarchicalEnabled ? 'Force View' : 'Hierarchy';

    fitGraphView();
    showToast(hierarchicalEnabled ? 'Switched to Hierarchical Flow layout' : 'Switched to Force-Directed layout');
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
            } else if (e.key === 'h' || e.key === 'H') {
                e.preventDefault();
                toggleHierarchicalLayout();
            } else if (e.code === 'Space') {
                e.preventDefault();
                togglePhysics();
            } else if (e.key === 'e' || e.key === 'E') {
                e.preventDefault();
                exportGraphPng();
            } else if (e.key === 'j' || e.key === 'J') {
                e.preventDefault();
                exportGraphJson();
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
