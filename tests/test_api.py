"""Tests for the Arcane API client.

The client is loaded directly from its file so these tests run without a
Home Assistant installation (api.py has no Home Assistant imports).
"""

import asyncio
from contextlib import asynccontextmanager
import importlib.util
from pathlib import Path
import socket

import aiohttp
from aiohttp import web
import pytest

_API_PATH = Path(__file__).parent.parent / "custom_components" / "arcane" / "api.py"
_SPEC = importlib.util.spec_from_file_location("arcane_api", _API_PATH)
assert _SPEC is not None and _SPEC.loader is not None
api = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(api)


@asynccontextmanager
async def _server(handler):
    """Run a minimal API server on a random port, yielding its base URL."""
    app = web.Application()
    app.router.add_route("*", "/api/{path:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    site = web.SockSite(runner, sock)
    await site.start()
    try:
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        await runner.cleanup()
        sock.close()


async def _with_client(handler, func, api_key="test-key", **client_kwargs):
    """Run ``func`` against a client talking to the given handler."""
    async with _server(handler) as base_url:
        session = aiohttp.ClientSession()
        try:
            client = api.ArcaneClient(base_url, api_key, session, **client_kwargs)
            return await func(client)
        finally:
            await session.close()


def test_get_all_paginates():
    """The client walks all pages of a paginated endpoint."""
    items = [{"id": str(index)} for index in range(150)]

    async def handler(request: web.Request) -> web.Response:
        start = int(request.query.get("start", "0"))
        limit = int(request.query.get("limit", "100"))
        return web.json_response(
            {
                "data": items[start : start + limit],
                "pagination": {"grandTotalItems": len(items)},
            }
        )

    async def run(client: api.ArcaneClient) -> list[dict]:
        return await client.async_get_environments()

    result = asyncio.run(_with_client(handler, run))
    assert len(result) == 150
    assert result[0]["id"] == "0"
    assert result[-1]["id"] == "149"


def test_stream_success():
    """A progress stream is consumed until the done line."""

    async def handler(request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse()
        resp.content_type = "application/x-ndjson"
        await resp.prepare(request)
        await resp.write(b'{"activityId":"abc"}\n')
        await resp.write(b'{"log":"pulling image\\n"}\n')
        await resp.write(b'{"done":true}\n')
        return resp

    async def run(client: api.ArcaneClient) -> None:
        await client.async_project_action("0", "42", "up")

    asyncio.run(_with_client(handler, run))


def test_stream_error_line_raises():
    """An error line in the stream fails the action."""

    async def handler(request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse()
        resp.content_type = "application/x-ndjson"
        await resp.prepare(request)
        await resp.write(b'{"log":"working"}\n')
        await resp.write(b'{"error":"compose file not found"}\n')
        return resp

    async def run(client: api.ArcaneClient) -> None:
        with pytest.raises(api.ArcaneActionError, match="compose file not found"):
            await client.async_project_action("0", "42", "up")

    asyncio.run(_with_client(handler, run))


def test_stream_eof_without_done_raises():
    """A stream that ends without a done line is treated as a failure."""

    async def handler(request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse()
        resp.content_type = "application/x-ndjson"
        await resp.prepare(request)
        await resp.write(b'{"log":"working"}\n')
        return resp

    async def run(client: api.ArcaneClient) -> None:
        with pytest.raises(api.ArcaneActionError, match="without completion"):
            await client.async_project_action("0", "42", "pull")

    asyncio.run(_with_client(handler, run))


def test_authentication_error():
    """A rejected API key raises ArcaneAuthenticationError."""

    async def handler(request: web.Request) -> web.Response:
        return web.Response(status=401, text="unauthorized")

    async def run(client: api.ArcaneClient) -> None:
        with pytest.raises(api.ArcaneAuthenticationError):
            await client.async_get_environments()

    # Retries must not delay or swallow the auth error
    asyncio.run(_with_client(handler, run, max_retries=3))


def test_server_error_raises_without_retry():
    """Server errors raise ArcaneError instead of being retried."""
    calls = 0

    async def handler(request: web.Request) -> web.Response:
        nonlocal calls
        calls += 1
        return web.Response(status=500, text="boom")

    async def run(client: api.ArcaneClient) -> None:
        with pytest.raises(api.ArcaneError, match="500"):
            await client.async_get_version()

    asyncio.run(_with_client(handler, run, max_retries=3))
    assert calls == 1


def test_unsupported_container_action_is_rejected():
    """The client refuses container actions outside its whitelist."""

    async def handler(request: web.Request) -> web.Response:  # pragma: no cover
        return web.Response(status=204)

    async def run(client: api.ArcaneClient) -> None:
        with pytest.raises(api.ArcaneActionError, match="Unsupported"):
            await client.async_container_action("0", "abc", "kill")

    asyncio.run(_with_client(handler, run))
