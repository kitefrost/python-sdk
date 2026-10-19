"""GN review 2026-10-17: exercise requests against a contract-aware server."""

import json

import httpx
import pytest

from kitefrost_core import KiteFrostCore


def test_byok_project_lifecycle_and_scan():
    stored = {}

    def server(request):
        if request.url.path == "/v1/byok/scan" and request.method == "POST":
            return httpx.Response(200, json={"safe": True})
        if request.url.raw_path != b"/v1/projects/project%2Fone/byok":
            return httpx.Response(404, json={"detail": "Unknown endpoint"})
        if request.method == "PUT":
            stored.update(json.loads(request.content))
        elif request.method == "DELETE":
            stored.clear()
            return httpx.Response(204)
        elif request.method != "GET":
            return httpx.Response(405)
        return httpx.Response(200, json={"has_key": bool(stored)})

    with KiteFrostCore(
        api_key="test",
        http_client=httpx.Client(
            base_url="https://api.kitefrost.ai",
            transport=httpx.MockTransport(server),
        ),
    ) as core:
        assert core.byok.list("project/one") == {"has_key": False}
        assert core.byok.set("project/one", {"provider": "openai", "api_key": "test"}) == {
            "has_key": True
        }
        assert core.byok.list("project/one") == {"has_key": True}
        assert core.byok.delete("project/one") is None
        assert core.byok.list("project/one") == {"has_key": False}
        assert core.byok.scan({"response_text": "A story."}) == {"safe": True}


@pytest.mark.parametrize(
    "method,args,signature",
    [
        ("list", (), "byok.list(project_id)"),
        ("set", ({"provider": "openai", "api_key": "test"},), "byok.set(project_id, body)"),
        ("list", ({"project_id": "project"},), "byok.list(project_id)"),
    ],
)
def test_old_byok_signature_explains_required_project_before_transport(method, args, signature):
    requests = []

    def server(request):
        requests.append(request)
        return httpx.Response(200, json={})

    with KiteFrostCore(
        api_key="test",
        http_client=httpx.Client(
            base_url="https://api.kitefrost.ai",
            transport=httpx.MockTransport(server),
        ),
    ) as core:
        with pytest.raises(TypeError) as error:
            getattr(core.byok, method)(*args)
        assert signature in str(error.value)
        assert requests == []


@pytest.mark.parametrize(
    "media_type", ["text/markdown", "text/plain", "application/x-ink", "application/x-yarn"]
)
def test_export_returns_text(media_type):
    with KiteFrostCore(
        api_key="test",
        http_client=httpx.Client(
            base_url="https://api.kitefrost.ai",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    text="# Chapter\nA story.\n",
                    headers={"Content-Type": media_type + "; charset=utf-8"},
                )
            ),
        ),
    ) as core:
        assert core.transport.post("/export", {"format": "markdown"}) == "# Chapter\nA story.\n"


@pytest.mark.parametrize("media_type", ["application/json", "application/vnd.kitefrost+json"])
def test_json_exports_remain_structured(media_type):
    with KiteFrostCore(
        api_key="test",
        http_client=httpx.Client(
            base_url="https://api.kitefrost.ai",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={"nodes": []},
                    headers={"Content-Type": media_type},
                )
            ),
        ),
    ) as core:
        assert core.transport.post("/export") == {"nodes": []}
