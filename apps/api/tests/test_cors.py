import httpx


async def test_preflight_allows_browser_calls(client: httpx.AsyncClient) -> None:
    response = await client.options(
        "/organizations",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,x-org-id",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    for header in ("authorization", "content-type", "x-org-id"):
        assert header in allowed_headers


async def test_unknown_origin_is_not_allowed(client: httpx.AsyncClient) -> None:
    response = await client.options(
        "/organizations",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers
