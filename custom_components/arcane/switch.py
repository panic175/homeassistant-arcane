"""Switch platform for the Arcane integration."""

from typing import override

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ArcaneConfigEntry, ArcaneEnvironmentData
from .entity import ArcaneContainerEntity, ArcaneProjectEntity
from .util import async_add_entities_by_subentry

PARALLEL_UPDATES = 1

CONTAINER_SWITCHES: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key="container",
        translation_key="container",
    ),
)

PROJECT_SWITCHES: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key="project",
        translation_key="project",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArcaneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Arcane switches based on a config entry."""
    coordinator = entry.runtime_data

    def _async_add_new_projects(
        projects: list[tuple[str, ArcaneEnvironmentData, dict]],
    ) -> None:
        """Add new project switches."""
        async_add_entities_by_subentry(
            async_add_entities,
            coordinator.subentry_id_for_environment,
            (
                (
                    ArcaneProjectSwitch(
                        coordinator, entity_description, environment_id, project
                    ),
                    environment_id,
                )
                for environment_id, _environment_data, project in projects
                for entity_description in PROJECT_SWITCHES
            ),
        )

    coordinator.new_projects_callbacks.append(_async_add_new_projects)
    _async_add_new_projects(
        [
            (environment_id, environment_data, project)
            for environment_id, environment_data in coordinator.data.items()
            for project in environment_data.projects.values()
        ]
    )

    def _async_add_new_containers(
        containers: list[tuple[str, ArcaneEnvironmentData, dict]],
    ) -> None:
        """Add new container switches."""
        async_add_entities_by_subentry(
            async_add_entities,
            coordinator.subentry_id_for_environment,
            (
                (
                    ArcaneContainerSwitch(
                        coordinator, entity_description, environment_id, container
                    ),
                    environment_id,
                )
                for environment_id, _environment_data, container in containers
                for entity_description in CONTAINER_SWITCHES
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


class ArcaneContainerSwitch(ArcaneContainerEntity, SwitchEntity):
    """Switch that starts or stops an Arcane container."""

    entity_description: SwitchEntityDescription

    @property
    @override
    def is_on(self) -> bool | None:
        """Return true if the container is running."""
        return self.container_data.get("state") == "running"

    @override
    async def async_turn_on(self, **kwargs) -> None:
        """Start the container."""
        await self.coordinator.async_call_arcane(
            self.coordinator.client.async_container_action(
                self.environment_id, self.container_data["id"], "start"
            )
        )
        await self.coordinator.async_request_refresh()

    @override
    async def async_turn_off(self, **kwargs) -> None:
        """Stop the container."""
        await self.coordinator.async_call_arcane(
            self.coordinator.client.async_container_action(
                self.environment_id, self.container_data["id"], "stop"
            )
        )
        await self.coordinator.async_request_refresh()


class ArcaneProjectSwitch(ArcaneProjectEntity, SwitchEntity):
    """Switch that deploys or stops an Arcane project."""

    entity_description: SwitchEntityDescription

    @property
    @override
    def is_on(self) -> bool | None:
        """Return true if the project is running."""
        status = self.project_data.get("status")
        if status is None:
            return None
        return status in ("running", "partially running")

    @override
    async def async_turn_on(self, **kwargs) -> None:
        """Deploy the project."""
        await self.coordinator.async_call_arcane(
            self.coordinator.client.async_project_action(
                self.environment_id, self.project_id, "up"
            )
        )
        await self.coordinator.async_request_refresh()

    @override
    async def async_turn_off(self, **kwargs) -> None:
        """Bring the project down."""
        await self.coordinator.async_call_arcane(
            self.coordinator.client.async_project_action(
                self.environment_id, self.project_id, "down"
            )
        )
        await self.coordinator.async_request_refresh()
