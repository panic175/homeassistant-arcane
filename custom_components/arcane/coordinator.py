"""Data Update Coordinator for Arcane."""

from abc import abstractmethod
import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
import homeassistant.helpers.device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from yarl import URL

from .api import (
    ArcaneAuthenticationError,
    ArcaneClient,
    ArcaneConnectionError,
    ArcaneError,
    ArcaneTimeoutError,
)
from .const import (
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERSION_SCAN_INTERVAL,
    DOMAIN,
)
from .util import container_name

type ArcaneConfigEntry = ConfigEntry[ArcaneCoordinator]

_LOGGER = logging.getLogger(__name__)


@dataclass
class ArcaneEnvironmentData:
    """Data class for one Arcane environment."""

    environment: dict[str, Any]
    docker_info: dict[str, Any]
    usage: dict[str, dict[str, Any]]
    containers: dict[str, dict[str, Any]]
    projects: dict[str, dict[str, Any]]
    events: list[dict[str, Any]]


type ArcaneCoordinatorData = dict[str, ArcaneEnvironmentData]


class ArcaneBaseCoordinator[DataT](DataUpdateCoordinator[DataT]):
    """Base coordinator for Arcane."""

    config_entry: ArcaneConfigEntry
    _update_interval: timedelta

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ArcaneConfigEntry,
        client: ArcaneClient,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=self._update_interval,
        )
        self.client = client

    @override
    async def _async_setup(self) -> None:
        """Validate credentials before the first data fetch."""
        try:
            await self.client.async_get_environments()
        except ArcaneAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except (ArcaneConnectionError, ArcaneTimeoutError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err

    def subentry_id_for_environment(self, environment_id: str) -> str | None:
        """Return the subentry ID an environment belongs to, if any."""
        return next(
            (
                subentry_id
                for subentry_id, subentry in self.config_entry.subentries.items()
                if subentry.unique_id == environment_id
            ),
            None,
        )

    def configured_environment_ids(self) -> set[str]:
        """Return the environment IDs of all configured subentries."""
        return {
            subentry.unique_id
            for subentry in self.config_entry.subentries.values()
            if subentry.unique_id
        }

    @abstractmethod
    async def update_data(self) -> DataT:
        """Update coordinator data."""

    @override
    async def _async_update_data(self) -> DataT:
        """Fetch per coordinator specific data."""
        try:
            return await self.update_data()
        except ArcaneAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except ArcaneConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err
        except ArcaneTimeoutError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="timeout_connect",
            ) from err
        except ArcaneError as err:
            raise UpdateFailed(str(err)) from err

    async def async_call_arcane(self, coroutine: Any) -> None:
        """Await an Arcane call, mapping client errors to HomeAssistantError."""
        try:
            await coroutine
        except ArcaneAuthenticationError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except ArcaneConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err
        except ArcaneTimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="timeout_connect",
            ) from err
        except ArcaneError as err:
            raise HomeAssistantError(str(err)) from err


class ArcaneCoordinator(ArcaneBaseCoordinator[ArcaneCoordinatorData]):
    """Data Update Coordinator for Arcane."""

    config_entry: ArcaneConfigEntry
    version: "ArcaneVersionCoordinator | None" = None
    _update_interval = DEFAULT_SCAN_INTERVAL

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ArcaneConfigEntry,
        client: ArcaneClient,
    ) -> None:
        """Initialize."""
        super().__init__(hass, config_entry, client)
        self.known_containers: set[tuple[str, str]] = set()
        self.known_projects: set[tuple[str, str]] = set()
        self.new_containers_callbacks: list[
            Callable[[list[tuple[str, ArcaneEnvironmentData, dict[str, Any]]]], None]
        ] = []
        self.new_projects_callbacks: list[
            Callable[[list[tuple[str, ArcaneEnvironmentData, dict[str, Any]]]], None]
        ] = []

    @override
    async def update_data(self) -> ArcaneCoordinatorData:
        """Fetch data from the Arcane API."""
        _LOGGER.debug(
            "Fetching data from Arcane API: %s", self.config_entry.data[CONF_URL]
        )
        environments = await self.client.async_get_environments()
        environments_by_id = {env["id"]: env for env in environments}

        data: ArcaneCoordinatorData = {}
        for environment_id in sorted(self.configured_environment_ids()):
            environment = environments_by_id.get(environment_id)
            if environment is None:
                # Keep entities but mark them unavailable until it reappears
                _LOGGER.warning(
                    "Environment %s is not (or no longer) available", environment_id
                )
                continue
            (
                containers,
                projects,
                events,
                docker_info,
                image_counts,
                volume_counts,
            ) = await asyncio.gather(
                self.client.async_get_containers(environment_id),
                self.client.async_get_projects(environment_id),
                self._async_get_events(environment_id),
                self.client.async_get_docker_info(environment_id),
                self.client.async_get_image_counts(environment_id),
                self.client.async_get_volume_counts(environment_id),
            )
            data[environment_id] = ArcaneEnvironmentData(
                environment=environment,
                docker_info=docker_info,
                usage={"images": image_counts, "volumes": volume_counts},
                containers={
                    container_name(container): container for container in containers
                },
                projects={project["id"]: project for project in projects},
                events=events,
            )

        self._async_add_remove_resources(data)
        return data

    async def _async_get_events(self, environment_id: str) -> list[dict[str, Any]]:
        """Fetch recent events; never fail the update when the log is broken."""
        try:
            return await self.client.async_get_events(environment_id)
        except ArcaneError as err:
            _LOGGER.debug(
                "Could not fetch events for environment %s: %s", environment_id, err
            )
            return []

    def _async_add_remove_resources(self, data: ArcaneCoordinatorData) -> None:
        """Detect new containers and projects, then notify the platforms."""
        current_projects = {
            (environment_id, project_id)
            for environment_id, environment_data in data.items()
            for project_id in environment_data.projects
        }
        new_projects = current_projects - self.known_projects
        if new_projects:
            # Register devices before any callback constructs an entity that
            # resolves one of them as its via device.
            self.async_register_environment_and_project_devices(
                data, environment_ids=set(), project_keys=new_projects
            )

        current_containers = {
            (environment_id, name)
            for environment_id, environment_data in data.items()
            for name in environment_data.containers
        }
        # Prune departed containers so a recreated container with a new name
        # is detected as new.
        self.known_containers &= current_containers
        new_containers = current_containers - self.known_containers

        self.known_projects = current_projects
        if new_projects:
            _LOGGER.debug("New projects found: %s", new_projects)
            self.known_projects |= new_projects
            new_project_data = [
                (
                    environment_id,
                    data[environment_id],
                    data[environment_id].projects[project_id],
                )
                for environment_id, project_id in sorted(new_projects)
            ]
            for project_callback in self.new_projects_callbacks:
                project_callback(new_project_data)

        if new_containers:
            _LOGGER.debug("New containers found: %s", new_containers)
            self.known_containers |= new_containers
            new_container_data = [
                (
                    environment_id,
                    data[environment_id],
                    data[environment_id].containers[name],
                )
                for environment_id, name in sorted(new_containers)
            ]
            for container_callback in self.new_containers_callbacks:
                container_callback(new_container_data)

    def async_register_environment_and_project_devices(
        self,
        data: ArcaneCoordinatorData,
        environment_ids: set[str],
        project_keys: set[tuple[str, str]],
    ) -> None:
        """Register environment and project devices.

        Must run for an environment/project before any entity that resolves it
        as its via device is constructed, both during initial setup and when a
        later refresh discovers new projects.
        """
        device_registry = dr.async_get(self.hass)
        entry_id = self.config_entry.entry_id

        for environment_id in sorted(environment_ids):
            environment = data[environment_id].environment
            device_registry.async_get_or_create(
                config_entry_id=entry_id,
                config_subentry_id=self.subentry_id_for_environment(environment_id),
                identifiers={(DOMAIN, f"{entry_id}_{environment_id}")},
                configuration_url=URL(self.config_entry.data[CONF_URL]),
                manufacturer=DEFAULT_NAME,
                model="Environment",
                name=environment.get("name") or f"Environment {environment_id}",
                entry_type=DeviceEntryType.SERVICE,
            )

        for environment_id, project_id in sorted(project_keys):
            project = data[environment_id].projects[project_id]
            device_registry.async_get_or_create(
                config_entry_id=entry_id,
                config_subentry_id=self.subentry_id_for_environment(environment_id),
                identifiers={
                    (DOMAIN, f"{entry_id}_{environment_id}_project_{project_id}")
                },
                configuration_url=URL(self.config_entry.data[CONF_URL]),
                manufacturer=DEFAULT_NAME,
                model="Project",
                name=project.get("name") or project_id,
                via_device_id=dr.async_get_device_id_by_identifier(
                    self.hass,
                    (DOMAIN, f"{entry_id}_{environment_id}"),
                    config_entry_id=entry_id,
                ),
            )


class ArcaneVersionCoordinator(ArcaneBaseCoordinator[dict[str, Any]]):
    """Coordinator for the Arcane manager version (checked rarely)."""

    _update_interval = DEFAULT_VERSION_SCAN_INTERVAL

    @override
    async def update_data(self) -> dict[str, Any]:
        """Fetch Arcane version information."""
        return await self.client.async_get_version()
