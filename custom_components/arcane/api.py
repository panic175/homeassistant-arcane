"""Async client for the Arcane REST API.

Kept free of Home Assistant imports so it can be unit tested standalone.
Authentication uses the ``X-Api-Key`` header; API keys are created in
Arcane under Settings -> API Keys.
"""

import asyncio
import json
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_REQUEST_TIMEOUT = 10
# Container/project lifecycle actions can include image pulls and stop grace
# periods, so give them more headroom than a plain read.
DEFAULT_ACTION_TIMEOUT = 120
DEFAULT_STREAM_TIMEOUT = 600
PAGE_SIZE = 100

# Container lifecycle actions the client accepts
CONTAINER_LIFECYCLE_ACTIONS: tuple[str, ...] = (
    "start",
    "stop",
    "restart",
    "pause",
    "unpause",
)

# Project actions that answer with a newline-delimited JSON progress stream
PROJECT_STREAM_ACTIONS: tuple[str, ...] = ("up", "redeploy", "pull")


class ArcaneError(Exception):
    """Base error for Arcane API errors."""


class ArcaneAuthenticationError(ArcaneError):
    """Error to indicate the API key was rejected."""


class ArcaneConnectionError(ArcaneError):
    """Error to indicate the Arcane instance could not be reached."""


class ArcaneTimeoutError(ArcaneError):
    """Error to indicate a request timed out."""


class ArcaneActionError(ArcaneError):
    """Error to indicate an action reported a failure."""


class ArcaneClient:
    """Thin async client for the Arcane REST API."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        session: aiohttp.ClientSession,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        max_retries: int = 0,
    ) -> None:
        """Initialize the client."""
        self._api_url = api_url.rstrip("/")
        self._base_url = f"{self._api_url}/api"
        self._api_key = api_key
        self._session = session
        self._request_timeout = request_timeout
        self._max_retries = max_retries

    @property
    def api_url(self) -> str:
        """Return the base URL of the Arcane instance."""
        return self._api_url

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: Any | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Send a request and return the decoded JSON body."""
        url = f"{self._base_url}{path}"
        total_timeout = timeout or self._request_timeout
        last_error: ArcaneError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                async with self._session.request(
                    method,
                    url,
                    params=params,
                    json=payload,
                    headers={"X-Api-Key": self._api_key},
                    timeout=aiohttp.ClientTimeout(total=total_timeout),
                ) as response:
                    if response.status in (401, 403):
                        raise ArcaneAuthenticationError(
                            f"Authentication failed with status {response.status}"
                        )
                    if response.status >= 400:
                        body = await response.text()
                        raise ArcaneError(f"{response.status} for {path}: {body[:200]}")
                    if response.status == 204:
                        return None
                    return await response.json(content_type=None)
            except ArcaneError:
                raise
            except TimeoutError:
                last_error = ArcaneTimeoutError(f"Timeout requesting {path}")
            except aiohttp.ClientError as err:
                last_error = ArcaneConnectionError(
                    f"Connection error requesting {path}: {err}"
                )
            if attempt < self._max_retries:
                await asyncio.sleep(0.5 * (attempt + 1))
        if last_error is not None:
            raise last_error
        raise ArcaneConnectionError(f"Request to {path} failed")

    async def _request_stream(
        self,
        path: str,
        *,
        payload: Any | None = None,
        timeout: float = DEFAULT_STREAM_TIMEOUT,
    ) -> None:
        """POST and consume a newline-delimited JSON progress stream.

        Long-running Arcane operations answer with lines like
        ``{"activityId": ...}``, ``{"log": ...}``, ``{"done": true}`` or
        ``{"error": ...}``. Completion is the ``done`` line, not EOF.
        """
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                "POST",
                url,
                json=payload,
                headers={"X-Api-Key": self._api_key},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status in (401, 403):
                    raise ArcaneAuthenticationError(
                        f"Authentication failed with status {response.status}"
                    )
                if response.status >= 400:
                    body = await response.text()
                    raise ArcaneError(f"{response.status} for {path}: {body[:200]}")
                while line := await response.content.readline():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        message = json.loads(line)
                    except ValueError:
                        _LOGGER.debug("Ignoring non-JSON stream line: %s", line[:200])
                        continue
                    if error := message.get("error"):
                        raise ArcaneActionError(str(error))
                    if message.get("done"):
                        return
                    if log := message.get("log"):
                        _LOGGER.debug("Arcane %s: %s", path, str(log).rstrip())
                raise ArcaneActionError(
                    f"Progress stream for {path} ended without completion"
                )
        except TimeoutError as err:
            raise ArcaneTimeoutError(f"Timeout waiting for {path}") from err
        except aiohttp.ClientError as err:
            raise ArcaneConnectionError(f"Connection error for {path}: {err}") from err

    async def _get_all(
        self, path: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch every page of a paginated list endpoint."""
        items: list[dict[str, Any]] = []
        start = 0
        while True:
            page = await self._request(
                "GET",
                path,
                params={**(params or {}), "start": start, "limit": PAGE_SIZE},
            )
            entries = (page or {}).get("data") or []
            items.extend(entries)
            start += len(entries)
            pagination = (page or {}).get("pagination") or {}
            total = (
                pagination.get("grandTotalItems") or pagination.get("totalItems") or 0
            )
            if not entries or len(entries) < PAGE_SIZE or start >= total:
                return items

    async def async_get_environments(self) -> list[dict[str, Any]]:
        """Return all Arcane environments."""
        return await self._get_all("/environments")

    async def async_get_containers(self, environment_id: str) -> list[dict[str, Any]]:
        """Return all containers of an environment."""
        return await self._get_all(f"/environments/{environment_id}/containers")

    async def async_get_projects(self, environment_id: str) -> list[dict[str, Any]]:
        """Return all projects of an environment (archived excluded by default)."""
        return await self._get_all(f"/environments/{environment_id}/projects")

    async def async_get_events(
        self, environment_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return the newest events of an environment, newest first."""
        page = await self._request(
            "GET",
            f"/events/environment/{environment_id}",
            params={"sort": "timestamp", "order": "desc", "limit": limit},
        )
        return (page or {}).get("data") or []

    async def async_get_docker_info(self, environment_id: str) -> dict[str, Any]:
        """Return Docker engine info for an environment."""
        return await self._request(
            "GET", f"/environments/{environment_id}/system/docker/info"
        )

    async def async_get_image_counts(self, environment_id: str) -> dict[str, Any]:
        """Return image usage counts for an environment."""
        page = await self._request(
            "GET", f"/environments/{environment_id}/images/counts"
        )
        return (page or {}).get("data") or {}

    async def async_get_volume_counts(self, environment_id: str) -> dict[str, Any]:
        """Return volume usage counts for an environment."""
        page = await self._request(
            "GET", f"/environments/{environment_id}/volumes/counts"
        )
        return (page or {}).get("data") or {}

    async def async_get_version(self) -> dict[str, Any]:
        """Return version information of the Arcane manager."""
        return await self._request("GET", "/app-version")

    async def async_container_action(
        self, environment_id: str, container_id: str, action: str
    ) -> None:
        """Run a lifecycle action (start/stop/restart/pause/unpause) on a container."""
        if action not in CONTAINER_LIFECYCLE_ACTIONS:
            raise ArcaneActionError(f"Unsupported container action: {action}")
        await self._request(
            "POST",
            f"/environments/{environment_id}/containers/{container_id}/{action}",
            timeout=DEFAULT_ACTION_TIMEOUT,
        )

    async def async_update_container(
        self, environment_id: str, container_id: str
    ) -> None:
        """Pull the latest image and apply Arcane's update strategy."""
        await self._request(
            "POST",
            f"/environments/{environment_id}/containers/{container_id}/update",
            timeout=DEFAULT_STREAM_TIMEOUT,
        )

    async def async_redeploy_container(
        self, environment_id: str, container_id: str
    ) -> None:
        """Pull the latest image and recreate a container."""
        await self._request(
            "POST",
            f"/environments/{environment_id}/containers/{container_id}/redeploy",
            timeout=DEFAULT_STREAM_TIMEOUT,
        )

    async def async_project_action(
        self, environment_id: str, project_id: str, action: str
    ) -> None:
        """Run a project action (up/down/restart/redeploy/pull/update-services)."""
        path = f"/environments/{environment_id}/projects/{project_id}/{action}"
        if action in PROJECT_STREAM_ACTIONS:
            await self._request_stream(path)
            return
        payload: Any | None = None
        timeout = DEFAULT_ACTION_TIMEOUT
        if action == "update-services":
            payload = {"services": []}
            timeout = DEFAULT_STREAM_TIMEOUT
        elif action in ("down", "restart"):
            timeout = DEFAULT_STREAM_TIMEOUT
        await self._request("POST", path, payload=payload, timeout=timeout)

    async def async_prune_images(
        self, environment_id: str, dangling: bool = False
    ) -> None:
        """Remove unused images from an environment."""
        await self._request(
            "POST",
            f"/environments/{environment_id}/images/prune",
            params={"dangling": "true"} if dangling else None,
            timeout=DEFAULT_STREAM_TIMEOUT,
        )

    async def async_prune_volumes(self, environment_id: str) -> None:
        """Remove unused volumes from an environment."""
        await self._request(
            "POST",
            f"/environments/{environment_id}/volumes/prune",
            timeout=DEFAULT_STREAM_TIMEOUT,
        )

    async def async_prune_networks(self, environment_id: str) -> None:
        """Remove unused networks from an environment."""
        await self._request(
            "POST",
            f"/environments/{environment_id}/networks/prune",
            timeout=DEFAULT_STREAM_TIMEOUT,
        )
