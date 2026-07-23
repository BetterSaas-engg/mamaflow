"""Web CORS wiring (spec 2026-07-18): API callable from the configured web-app
origin(s) only; no origins configured (today's default) = no CORS headers."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.config.settings import Settings, settings
from api.main import configure_cors


def test_web_origins_list_parses_and_strips():
    s = Settings(web_app_origins=" https://app.mamaflow.example , https://mamaflow-app.vercel.app ,")
    assert s.web_origins_list == [
        "https://app.mamaflow.example",
        "https://mamaflow-app.vercel.app",
    ]
    assert Settings(web_app_origins="").web_origins_list == []


def test_web_token_ttl_defaults_to_seven_days():
    assert Settings().web_token_expire_minutes == 7 * 24 * 60


@pytest.mark.asyncio
async def test_preflight_allowed_for_configured_origin(monkeypatch):
    monkeypatch.setattr(settings, "web_app_origins", "https://app.mamaflow.example")
    app = FastAPI()
    configure_cors(app)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.options("/ping", headers={
            "Origin": "https://app.mamaflow.example",
            "Access-Control-Request-Method": "GET",
        })
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "https://app.mamaflow.example"


@pytest.mark.asyncio
async def test_no_origins_configured_means_no_cors(monkeypatch):
    monkeypatch.setattr(settings, "web_app_origins", "")
    app = FastAPI()
    configure_cors(app)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/ping", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in resp.headers
