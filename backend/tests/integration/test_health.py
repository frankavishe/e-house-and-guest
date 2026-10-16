import httpx


async def test_health_reports_database_ok(client: httpx.AsyncClient) -> None:
    res = await client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "database": "ok"}


async def test_unknown_route_uses_error_shape(client: httpx.AsyncClient) -> None:
    res = await client.get("/api/v1/nope", headers={"Accept-Language": "en"})
    assert res.status_code == 404
    body = res.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Not found."


async def test_error_message_defaults_to_swahili(client: httpx.AsyncClient) -> None:
    res = await client.get("/api/v1/nope")
    assert res.json()["error"]["message"] == "Hakijapatikana."
