# Cloudflare Zero Trust Network Topology Mapper

<p align="center">
  <img src="https://img.shields.io/badge/Cloudflare-Zero_Trust-F6821F?style=flat-square&logo=cloudflare" alt="Cloudflare Zero Trust">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/License-Apache_2.0-blue?style=flat-square" alt="License">
</p>

Generate interactive network topology visualizations for your Cloudflare Zero Trust infrastructure. See your tunnels, access applications, policies, identity providers, and private networks as a beautiful, interactive graph.

**Inspired by** [tailscale-network-topology-mapper](https://github.com/SimplyMinimal/tailscale-network-topology-mapper)

---

## 📸 Screenshot

<p align="center">
  <img src="docs/images/topology-screenshot.png" alt="Cloudflare Zero Trust Topology Visualization" width="100%">
</p>

---

## ✨ Features

| Resource | Visualization |
|----------|---------------|
| 🔵 **Tunnels** | Cloudflare Tunnels with connector status, ingress rules, origin IPs |
| 🟢 **Access Applications** | Self-hosted apps, SaaS apps with domains and session duration |
| 🟡 **Access Policies** | Allow/deny/bypass rules with include/exclude/require logic |
| 🟠 **Access Groups** | Reusable identity groups with member criteria |
| 🟣 **Virtual Networks** | Private network segmentation for tunnel routing |
| 🔴 **WARP Devices** | Enrolled devices with user info and last seen status |
| 🌐 **Identity Providers** | Okta, Azure AD, Google, GitHub, and other IdPs |
| 🛡️ **Gateway Rules** | DNS and HTTP firewall policies (optional) |

### Interactive Visualization
- **Search**: Find nodes by name, domain, or type
- **Filter**: Toggle visibility by resource type  
- **Zoom & Pan**: Navigate large topologies
- **Drag**: Rearrange nodes manually
- **Tooltips**: Hover for detailed configuration info
- **Dark Theme**: Easy on the eyes, matches Cloudflare dashboard

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.12+**
- **Cloudflare API Token** with Zero Trust read permissions

### 1. Clone & Install

```bash
git clone https://github.com/yourusername/cloudflare-topology.git
cd cloudflare-topology
pip install -r requirements.txt
```

### 2. Configure Credentials

```bash
export CLOUDFLARE_API_TOKEN="your-api-token"
export CLOUDFLARE_ACCOUNT_ID="your-account-id"
```

<details>
<summary>📍 Where to find your Account ID</summary>

Your Account ID is visible in:
- The URL when logged into Cloudflare: `dash.cloudflare.com/<ACCOUNT_ID>/...`
- Any zone's Overview page → right sidebar under "Account ID"
- Workers & Pages → right sidebar

</details>

### 3. Generate Topology

```bash
# Basic usage - opens in browser
python main.py

# Skip tunnel configs for faster generation
python main.py --no-tunnel-configs

# Include Gateway firewall rules
python main.py --include-gateway

# Debug mode with verbose output
python main.py --debug
```

---

## 🐳 Docker Deployment

Run as a web service with automatic regeneration:

```bash
# Build
make build

# Run (requires env vars)
export CLOUDFLARE_API_TOKEN="your-token"
export CLOUDFLARE_ACCOUNT_ID="your-account-id"
make run

# View at http://localhost:8080
```

Or with docker directly:

```bash
docker build -t cloudflare-topology .

docker run -d \
  --name cloudflare-topology \
  -p 8080:8080 \
  -e CLOUDFLARE_API_TOKEN="your-token" \
  -e CLOUDFLARE_ACCOUNT_ID="your-account-id" \
  cloudflare-topology
```

### Docker Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | View topology visualization |
| `/health` | GET | Health check |
| `/regenerate` | POST | Trigger topology refresh |

---

## 🔑 API Token Permissions

Create a token at [Cloudflare Dashboard → API Tokens](https://dash.cloudflare.com/profile/api-tokens):

### Required Permissions

| Permission | Scope | Used For |
|------------|-------|----------|
| **Zero Trust: Read** | Account | Tunnels, virtual networks, routes |
| **Access: Apps and Policies: Read** | Account | Applications, policies, groups |

### Optional Permissions

| Permission | Scope | Used For |
|------------|-------|----------|
| **Devices: Read** | Account | WARP device enrollment |
| **Gateway: Read** | Account | DNS/HTTP firewall rules |

<details>
<summary>🛡️ Recommended: Use a Custom Token</summary>

Create a token with **only** the permissions you need. Avoid using Global API Keys.

1. Go to [API Tokens](https://dash.cloudflare.com/profile/api-tokens)
2. Click "Create Token"
3. Use "Create Custom Token"
4. Add the permissions listed above
5. Set appropriate TTL and IP restrictions for security

</details>

---

## 🎨 Node Types & Colors

| Type | Color | Shape | Description |
|------|-------|-------|-------------|
| **Cloudflare** | Orange | Star | Central hub node |
| **Tunnel** | Blue `#3b82f6` | Hexagon | Cloudflare Tunnel connectors |
| **Application** | Green `#22c55e` | Circle | Access-protected applications |
| **Policy** | Yellow `#eab308` | Triangle | Access policy rules |
| **Group** | Orange `#f97316` | Circle | Access groups |
| **Identity Provider** | Cyan `#06b6d4` | Star | Okta, Azure AD, etc. |
| **Virtual Network** | Purple `#a855f7` | Square | Private network segments |
| **Route** | Lime `#84cc16` | Circle | Private network routes |
| **Device** | Red `#ef4444` | Diamond | WARP-enrolled devices |
| **Gateway Rule** | Pink `#ec4899` | Triangle | Firewall policies |

---

## ⚙️ CLI Options

```
python main.py [OPTIONS]

Options:
  --debug              Enable verbose debug logging
  --output, -o FILE    Output HTML file (default: network_topology.html)
  --no-browser         Don't auto-open browser after generation
  --no-devices         Skip fetching WARP devices (faster)
  --no-tunnel-configs  Skip fetching detailed tunnel configurations
  --include-gateway    Include Gateway firewall rules
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CLOUDFLARE_API_TOKEN` | ✅ | API token with Zero Trust read permissions |
| `CLOUDFLARE_ACCOUNT_ID` | ✅ | Your Cloudflare account ID |
| `DEBUG` | ❌ | Set to `true` for debug logging |

---

## 📁 Project Structure

```
cloudflare-topology/
├── main.py                 # CLI entry point
├── config.py               # Configuration, colors, API endpoints
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container image
├── Makefile                # Build/run commands
│
├── models/
│   └── cloudflare_data.py  # Data models for all resources
│
├── services/
│   ├── cloudflare_api.py   # Cloudflare API client with pagination
│   ├── network_graph.py    # Graph builder (nodes & edges)
│   └── renderer.py         # HTML/CSS/JS visualization
│
├── server/
│   └── server.py           # Flask server for Docker
│
└── tests/
    ├── test_config.py
    ├── test_models.py
    └── test_network_graph.py
```

---

## 🧪 Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run tests
make test
# or
python -m pytest tests/ -v

# Lint
make lint
```

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

---

## 📜 License

Apache 2.0 - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- [tailscale-network-topology-mapper](https://github.com/SimplyMinimal/tailscale-network-topology-mapper) - Original inspiration
- [Pyvis](https://pyvis.readthedocs.io/) - Python network visualization
- [vis.js](https://visjs.org/) - JavaScript graph library
- [Cloudflare](https://cloudflare.com) - Zero Trust platform

---

<p align="center">
  Made with ☁️ for the Cloudflare community
</p>
