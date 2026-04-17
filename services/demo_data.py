"""
Synthetic demo topology data.

Used for the public Cloudflare Pages deployment so we never publish real
account data. Also useful for screenshots, docs, and local previews without
hitting the Cloudflare API.
"""

from datetime import datetime, timezone

from models.cloudflare_data import (
    AccessApplication,
    AccessGroup,
    AccessPolicy,
    CloudflareTopology,
    IdentityProvider,
    PolicyRule,
    Route,
    Tunnel,
    TunnelConfig,
    TunnelConnection,
    VirtualNetwork,
)


def build_demo_topology() -> CloudflareTopology:
    """Return a realistic-looking but entirely fake Zero Trust topology."""

    now = datetime.now(timezone.utc).isoformat()

    # Identity providers
    idps = [
        IdentityProvider(
            id="idp-okta-demo",
            name="Okta (demo)",
            idp_type="okta",
            config={"okta_account": "acme.okta.com"},
        ),
        IdentityProvider(
            id="idp-google-demo",
            name="Google Workspace (demo)",
            idp_type="google-apps",
            config={"apps_domain": "acme.example"},
        ),
    ]

    # Access groups
    groups = [
        AccessGroup(
            id="grp-engineers",
            name="Engineering",
            include=[PolicyRule("email_domain", {"domain": "acme.example"})],
        ),
        AccessGroup(
            id="grp-contractors",
            name="Contractors",
            include=[PolicyRule("email", {"email": "contractor@partner.example"})],
        ),
    ]

    # Policies
    policies = [
        AccessPolicy(
            id="pol-allow-eng",
            name="Allow Engineering",
            decision="allow",
            precedence=1,
            include=[PolicyRule("group", {"id": "grp-engineers"})],
        ),
        AccessPolicy(
            id="pol-require-mfa",
            name="Require MFA",
            decision="allow",
            precedence=2,
            require=[PolicyRule("auth_method", {"auth_method": "mfa"})],
        ),
        AccessPolicy(
            id="pol-deny-default",
            name="Deny by default",
            decision="deny",
            precedence=99,
            include=[PolicyRule("everyone", {})],
        ),
    ]

    # Applications
    applications = [
        AccessApplication(
            id="app-grafana",
            name="Grafana",
            domain="grafana.acme.example",
            app_type="self_hosted",
            allowed_idps=["idp-okta-demo"],
            policies=policies[:2],
        ),
        AccessApplication(
            id="app-jenkins",
            name="Jenkins",
            domain="jenkins.acme.example",
            app_type="self_hosted",
            allowed_idps=["idp-okta-demo"],
            policies=[policies[0]],
        ),
        AccessApplication(
            id="app-internal-wiki",
            name="Internal Wiki",
            domain="wiki.acme.example",
            app_type="self_hosted",
            allowed_idps=["idp-google-demo"],
            policies=[policies[0], policies[2]],
        ),
    ]

    # Virtual networks
    vnets = [
        VirtualNetwork(
            id="vnet-default",
            name="default",
            comment="Demo default vnet",
            is_default=True,
            is_default_network=True,
        ),
    ]

    # Tunnels
    tunnels = [
        Tunnel(
            id=f"tun-{i}",
            name=name,
            status=status,
            created_at=now,
            tun_type="cfd_tunnel",
            connections=[
                TunnelConnection(
                    id=f"conn-{i}-1",
                    colo_name="FRA",
                    is_pending_reconnect=False,
                    client_version="2025.1.1",
                ),
                TunnelConnection(
                    id=f"conn-{i}-2",
                    colo_name="AMS",
                    is_pending_reconnect=False,
                    client_version="2025.1.1",
                ),
            ],
            config=TunnelConfig(
                ingress=[
                    {"hostname": hostname, "service": f"http://localhost:{port}"}
                    for hostname, port in ingress
                ]
            ),
        )
        for i, (name, status, ingress) in enumerate(
            [
                ("prod-edge", "healthy", [("grafana.acme.example", 3000)]),
                ("prod-backoffice", "healthy", [("jenkins.acme.example", 8080)]),
                ("prod-wiki", "healthy", [("wiki.acme.example", 80)]),
                ("staging-edge", "degraded", [("staging.acme.example", 3000)]),
                ("dev-laptop", "inactive", []),
                ("legacy-vpn", "down", []),
            ]
        )
    ]

    # Routes
    routes = [
        Route(
            id="rt-1",
            network="10.10.0.0/16",
            tunnel_id="tun-0",
            tunnel_name="prod-edge",
            virtual_network_id="vnet-default",
            comment="Prod VPC",
        ),
        Route(
            id="rt-2",
            network="10.20.0.0/16",
            tunnel_id="tun-1",
            tunnel_name="prod-backoffice",
            virtual_network_id="vnet-default",
            comment="Backoffice VPC",
        ),
    ]

    return CloudflareTopology(
        tunnels=tunnels,
        applications=applications,
        policies=policies,
        groups=groups,
        devices=[],
        virtual_networks=vnets,
        routes=routes,
        identity_providers=idps,
        gateway_rules=[],
        account_id="demo-account",
        fetched_at=now,
    )
