"""Base class for Arcane entities."""

from typing import override

from homeassistant.const import CONF_URL
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from yarl import URL

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import (
    ArcaneCoordinator,
    ArcaneEnvironmentData,
    ArcaneVersionCoordinator,
)
from .util import container_name


def _project_id_for_container(
    coordinator: ArcaneCoordinator, environment_id: str, container: dict
) -> str | None:
    """Return the Arcane project ID a container belongs to, if any."""
    if not coordinator.data or environment_id not in coordinator.data:
        return None
    compose_project = (container.get("labels") or {}).get("com.docker.compose.project")
    if not compose_project:
        return None
    return next(
        (
            project_id
            for project_id, project in coordinator.data[environment_id].projects.items()
            if project.get("name") == compose_project
        ),
        None,
    )


class ArcaneCoordinatorEntity(CoordinatorEntity[ArcaneCoordinator]):
    """Base class for Arcane entities."""

    _attr_has_entity_name = True


class ArcaneServerEntity(CoordinatorEntity[ArcaneVersionCoordinator]):
    """Base implementation for the Arcane manager itself."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ArcaneVersionCoordinator,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize an Arcane server entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        entry = coordinator.config_entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            configuration_url=URL(entry.data[CONF_URL]),
            manufacturer=DEFAULT_NAME,
            model="Manager",
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )
        self._attr_unique_id = f"{entry.entry_id}_{entity_description.key}"

    @property
    @override
    def available(self) -> bool:
        """Return if the version data has been fetched."""
        return super().available and self.coordinator.data is not None


class ArcaneEnvironmentEntity(ArcaneCoordinatorEntity):
    """Base implementation for an Arcane environment."""

    def __init__(
        self,
        coordinator: ArcaneCoordinator,
        entity_description: EntityDescription,
        environment_id: str,
        environment: dict,
    ) -> None:
        """Initialize an Arcane environment entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self.environment_id = environment_id
        entry_id = coordinator.config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{environment_id}")},
            configuration_url=URL(coordinator.config_entry.data[CONF_URL]),
            manufacturer=DEFAULT_NAME,
            model="Environment",
            name=environment.get("name") or f"Environment {environment_id}",
            entry_type=DeviceEntryType.SERVICE,
        )
        self._attr_unique_id = f"{entry_id}_{environment_id}_{entity_description.key}"

    @property
    @override
    def available(self) -> bool:
        """Return if the environment is present in coordinator data."""
        return super().available and self.environment_id in self.coordinator.data

    @property
    def environment_data(self) -> ArcaneEnvironmentData:
        """Return the coordinator data for this environment."""
        return self.coordinator.data[self.environment_id]


class ArcaneContainerEntity(ArcaneCoordinatorEntity):
    """Base implementation for an Arcane container."""

    def __init__(
        self,
        coordinator: ArcaneCoordinator,
        entity_description: EntityDescription,
        environment_id: str,
        container: dict,
    ) -> None:
        """Initialize an Arcane container entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self.environment_id = environment_id
        self.device_name = container_name(container)
        entry_id = coordinator.config_entry.entry_id

        # Nest the container under its project device when it belongs to a
        # Compose project, otherwise under the environment.
        project_id = _project_id_for_container(coordinator, environment_id, container)
        via_identifier = (
            f"{entry_id}_{environment_id}_project_{project_id}"
            if project_id
            else f"{entry_id}_{environment_id}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{environment_id}_{self.device_name}")},
            configuration_url=URL(coordinator.config_entry.data[CONF_URL]),
            manufacturer=DEFAULT_NAME,
            model="Container",
            name=self.device_name,
            via_device_id=dr.async_get_device_id_by_identifier(
                coordinator.hass,
                (DOMAIN, via_identifier),
                config_entry_id=entry_id,
            ),
        )
        self._attr_unique_id = (
            f"{entry_id}_{environment_id}_{self.device_name}_{entity_description.key}"
        )

    @property
    @override
    def available(self) -> bool:
        """Return if the container is present in coordinator data."""
        return (
            super().available
            and self.environment_id in self.coordinator.data
            and self.device_name
            in self.coordinator.data[self.environment_id].containers
        )

    @property
    def container_data(self) -> dict:
        """Return the coordinator data for this container."""
        return self.coordinator.data[self.environment_id].containers[self.device_name]


class ArcaneProjectEntity(ArcaneCoordinatorEntity):
    """Base implementation for an Arcane project."""

    def __init__(
        self,
        coordinator: ArcaneCoordinator,
        entity_description: EntityDescription,
        environment_id: str,
        project: dict,
    ) -> None:
        """Initialize an Arcane project entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self.environment_id = environment_id
        self.project_id = project["id"]
        self.device_name = project.get("name") or self.project_id
        entry_id = coordinator.config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, f"{entry_id}_{environment_id}_project_{self.project_id}")
            },
            configuration_url=URL(coordinator.config_entry.data[CONF_URL]),
            manufacturer=DEFAULT_NAME,
            model="Project",
            name=self.device_name,
            via_device_id=dr.async_get_device_id_by_identifier(
                coordinator.hass,
                (DOMAIN, f"{entry_id}_{environment_id}"),
                config_entry_id=entry_id,
            ),
        )
        self._attr_unique_id = (
            f"{entry_id}_{environment_id}_{self.project_id}_{entity_description.key}"
        )

    @property
    @override
    def available(self) -> bool:
        """Return if the project is present in coordinator data."""
        return (
            super().available
            and self.environment_id in self.coordinator.data
            and self.project_id in self.coordinator.data[self.environment_id].projects
        )

    @property
    def project_data(self) -> dict:
        """Return the coordinator data for this project."""
        return self.coordinator.data[self.environment_id].projects[self.project_id]
