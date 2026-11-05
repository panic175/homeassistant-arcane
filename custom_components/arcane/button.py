"""Button platform for the Arcane integration."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import ArcaneClient
from .coordinator import ArcaneConfigEntry, ArcaneEnvironmentData
from .entity import (
    ArcaneContainerEntity,
    ArcaneEnvironmentEntity,
    ArcaneProjectEntity,
)
from .util import async_add_entities_by_subentry

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ArcaneEnvironmentButtonDescription(ButtonEntityDescription):
    """Class to describe an Arcane environment button entity."""

    press_action: Callable[[ArcaneClient, str], Coroutine[Any, Any, Any]]


@dataclass(frozen=True, kw_only=True)
class ArcaneContainerButtonDescription(ButtonEntityDescription):
    """Class to describe an Arcane container button entity."""

    press_action: Callable[[ArcaneClient, str, str], Coroutine[Any, Any, Any]]


@dataclass(frozen=True, kw_only=True)
class ArcaneProjectButtonDescription(ButtonEntityDescription):
    """Class to describe an Arcane project button entity."""

    press_action: Callable[[ArcaneClient, str, str], Coroutine[Any, Any, Any]]


ENVIRONMENT_BUTTONS: tuple[ArcaneEnvironmentButtonDescription, ...] = (
    ArcaneEnvironmentButtonDescription(
        key="images_prune",
        translation_key="images_prune",
        press_action=lambda client, environment_id: client.async_prune_images(
            environment_id
        ),
    ),
    ArcaneEnvironmentButtonDescription(
        key="volumes_prune",
        translation_key="volumes_prune",
        press_action=lambda client, environment_id: client.async_prune_volumes(
            environment_id
        ),
    ),
    ArcaneEnvironmentButtonDescription(
        key="networks_prune",
        translation_key="networks_prune",
        press_action=lambda client, environment_id: client.async_prune_networks(
            environment_id
        ),
    ),
)

CONTAINER_BUTTONS: tuple[ArcaneContainerButtonDescription, ...] = (
    ArcaneContainerButtonDescription(
        key="restart_container",
        translation_key="restart_container",
        press_action=lambda client, environment_id, container_id: (
            client.async_container_action(environment_id, container_id, "restart")
        ),
    ),
    ArcaneContainerButtonDescription(
        key="pause_container",
        translation_key="pause_container",
        press_action=lambda client, environment_id, container_id: (
            client.async_container_action(environment_id, container_id, "pause")
        ),
    ),
    ArcaneContainerButtonDescription(
        key="resume_container",
        translation_key="resume_container",
        press_action=lambda client, environment_id, container_id: (
            client.async_container_action(environment_id, container_id, "unpause")
        ),
    ),
    ArcaneContainerButtonDescription(
        key="recreate_container",
        translation_key="recreate_container",
        press_action=lambda client, environment_id, container_id: (
            client.async_redeploy_container(environment_id, container_id)
        ),
    ),
)

PROJECT_BUTTONS: tuple[ArcaneProjectButtonDescription, ...] = (
    ArcaneProjectButtonDescription(
        key="update_project",
        translation_key="update_project",
        press_action=lambda client, environment_id, project_id: (
            client.async_project_action(environment_id, project_id, "update-services")
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArcaneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Arcane buttons based on a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        ArcaneEnvironmentButton(
            coordinator,
            entity_description,
            environment_id,
            environment_data.environment,
        )
        for environment_id, environment_data in coordinator.data.items()
        for entity_description in ENVIRONMENT_BUTTONS
    )

    def _async_add_new_projects(
        projects: list[tuple[str, ArcaneEnvironmentData, dict[str, Any]]],
    ) -> None:
        """Add new project buttons."""
        async_add_entities_by_subentry(
            async_add_entities,
            coordinator.subentry_id_for_environment,
            (
                (
                    ArcaneProjectButton(
                        coordinator, entity_description, environment_id, project
                    ),
                    environment_id,
                )
                for environment_id, _environment_data, project in projects
                for entity_description in PROJECT_BUTTONS
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
        containers: list[tuple[str, ArcaneEnvironmentData, dict[str, Any]]],
    ) -> None:
        """Add new container buttons."""
        async_add_entities_by_subentry(
            async_add_entities,
            coordinator.subentry_id_for_environment,
            (
                (
                    ArcaneContainerButton(
                        coordinator, entity_description, environment_id, container
                    ),
                    environment_id,
                )
                for environment_id, _environment_data, container in containers
                for entity_description in CONTAINER_BUTTONS
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


class ArcaneEnvironmentButton(ArcaneEnvironmentEntity, ButtonEntity):
    """Button for an Arcane environment (prune actions)."""

    entity_description: ArcaneEnvironmentButtonDescription

    @override
    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_call_arcane(
            self.entity_description.press_action(
                self.coordinator.client, self.environment_id
            )
        )
        await self.coordinator.async_request_refresh()


class ArcaneContainerButton(ArcaneContainerEntity, ButtonEntity):
    """Button for an Arcane container."""

    entity_description: ArcaneContainerButtonDescription

    @override
    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_call_arcane(
            self.entity_description.press_action(
                self.coordinator.client, self.environment_id, self.container_data["id"]
            )
        )
        await self.coordinator.async_request_refresh()


class ArcaneProjectButton(ArcaneProjectEntity, ButtonEntity):
    """Button for an Arcane project."""

    entity_description: ArcaneProjectButtonDescription

    @override
    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_call_arcane(
            self.entity_description.press_action(
                self.coordinator.client, self.environment_id, self.project_id
            )
        )
        await self.coordinator.async_request_refresh()
