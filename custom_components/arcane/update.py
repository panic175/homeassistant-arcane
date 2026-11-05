"""Update platform for the Arcane integration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, override

from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ArcaneConfigEntry
from .entity import ArcaneContainerEntity, ArcaneServerEntity
from .util import async_add_entities_by_subentry

PARALLEL_UPDATES = 1


def _short_digest(digest: str) -> str:
    """Shorten a digest to its algorithm and the leading hex characters."""
    algorithm, separator, hex_digest = digest.partition(":")
    return f"{algorithm}{separator}{hex_digest[:12]}"


def _container_installed(container: dict[str, Any]) -> str | None:
    """Return the installed version of a container's image."""
    info = container.get("updateInfo") or {}
    if info.get("updateType") == "digest" and (digest := info.get("currentDigest")):
        return _short_digest(digest)
    return info.get("currentVersion")


def _container_latest(container: dict[str, Any]) -> str | None:
    """Return the latest version of a container's image.

    Arcane only reports a newer version when an update exists, so mirror the
    installed version to keep the entity in the "up to date" state.
    """
    info = container.get("updateInfo") or {}
    if not info.get("hasUpdate"):
        return _container_installed(container)
    if info.get("updateType") == "digest" and (digest := info.get("latestDigest")):
        return _short_digest(digest)
    return info.get("latestVersion") or _container_installed(container)


@dataclass(frozen=True, kw_only=True)
class ArcaneContainerUpdateEntityDescription(UpdateEntityDescription):
    """Class to describe an Arcane container update entity."""

    installed_version: Callable[[dict[str, Any]], str | None]
    latest_version: Callable[[dict[str, Any]], str | None]


CONTAINER_UPDATES: tuple[ArcaneContainerUpdateEntityDescription, ...] = (
    ArcaneContainerUpdateEntityDescription(
        key="container_image_update",
        translation_key="container_image_update",
        entity_category=EntityCategory.CONFIG,
        installed_version=_container_installed,
        latest_version=_container_latest,
    ),
)

SERVER_UPDATE = UpdateEntityDescription(
    key="server_update",
    translation_key="server_update",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArcaneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Arcane update entities based on a config entry."""
    coordinator = entry.runtime_data
    if TYPE_CHECKING:
        assert coordinator.version is not None
    async_add_entities(ArcaneServerUpdateEntity(coordinator.version, SERVER_UPDATE))

    def _async_add_new_containers(
        containers: list[tuple[str, Any, dict[str, Any]]],
    ) -> None:
        """Add new container update entities."""
        async_add_entities_by_subentry(
            async_add_entities,
            coordinator.subentry_id_for_environment,
            (
                (
                    ArcaneContainerUpdate(
                        coordinator, entity_description, environment_id, container
                    ),
                    environment_id,
                )
                for environment_id, _environment_data, container in containers
                for entity_description in CONTAINER_UPDATES
            ),
        )

    coordinator.new_containers_callbacks.append(_async_add_new_containers)
    _async_add_new_containers(
        [
            (environment_id, environment_data, container)
            for environment_id, environment_data in coordinator.data.items()
            for container in environment_data.containers.values()
        ]
    )


class ArcaneContainerUpdate(ArcaneContainerEntity, UpdateEntity):
    """Representation of an Arcane container image update."""

    _attr_supported_features = UpdateEntityFeature.INSTALL

    entity_description: ArcaneContainerUpdateEntityDescription

    @override
    @property
    def title(self) -> str | None:
        """Return title."""
        return self.device_name

    @override
    @property
    def installed_version(self) -> str | None:
        """Return installed version."""
        return self.entity_description.installed_version(self.container_data)

    @override
    @property
    def latest_version(self) -> str | None:
        """Return latest version."""
        return self.entity_description.latest_version(self.container_data)

    @override
    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Pull the latest image and apply Arcane's update strategy."""
        self._attr_in_progress = True
        self.async_write_ha_state()
        try:
            await self.coordinator.async_call_arcane(
                self.coordinator.client.async_update_container(
                    self.environment_id, self.container_data["id"]
                )
            )
        finally:
            self._attr_in_progress = False
        await self.coordinator.async_request_refresh()


class ArcaneServerUpdateEntity(ArcaneServerEntity, UpdateEntity):
    """Representation of an update of the Arcane manager itself.

    Report-only: installing would recreate the Arcane manager container from
    inside Home Assistant, which the deployment rules forbid (see README).
    """

    _attr_title = "Arcane"

    entity_description: UpdateEntityDescription

    @override
    @property
    def installed_version(self) -> str | None:
        """Return the running Arcane version."""
        return self.coordinator.data.get("currentVersion")

    @override
    @property
    def latest_version(self) -> str | None:
        """Return the latest available Arcane version."""
        data = self.coordinator.data
        return data.get("newestVersion") or data.get("currentVersion")

    @override
    @property
    def release_url(self) -> str | None:
        """Return the release notes of the latest version."""
        return self.coordinator.data.get("releaseUrl")
