"""
REST data source: talks directly to ``api.cloudflare.com``.

This is the default transport and the historical behaviour of the tool. It is
a thin, explicit alias for :class:`services.cloudflare_api.CloudflareAPIClient`
so the REST client stays the single implementation while satisfying the
:class:`services.sources.TopologySource` protocol by name.
"""

from services.cloudflare_api import CloudflareAPIClient


class RestZeroTrustSource(CloudflareAPIClient):
    """Topology source backed by the Cloudflare REST API.

    Behaviour is identical to :class:`CloudflareAPIClient` (same constructor,
    same ``fetch_topology`` signature, same retry/rate-limit handling); the
    subclass exists to give the REST transport a name that matches the other
    sources (``ZeroTrustMCPSource``, ``DemoSource``).

    Kept as a subclass rather than a wrapper so existing code and tests that
    use ``CloudflareAPIClient`` keep working unchanged.
    """
