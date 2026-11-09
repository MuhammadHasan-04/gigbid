"""In-process fake marketplace port backed by GigSim's FastAPI app (no network)."""
import os

import httpx

os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGSIM_RPM", "100000")
os.environ.setdefault("GIGSIM_STATE_FILE", "/tmp/gigsim_test_state.json")


def gigsim_adapter():
    from gigsim import server
    from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
    client_transport = httpx.MockTransport(lambda req: _asgi(server.app, req))
    return GigSimAdapter(base_url="http://gigsim", transport=client_transport)


def _asgi(app, request: httpx.Request) -> httpx.Response:
    from starlette.testclient import TestClient
    tc = _clients.setdefault(id(app), TestClient(app))
    r = tc.request(request.method, str(request.url).replace("http://gigsim", ""), headers=dict(request.headers),
                   content=request.content)
    return httpx.Response(r.status_code, headers=r.headers, content=r.content)


_clients = {}
