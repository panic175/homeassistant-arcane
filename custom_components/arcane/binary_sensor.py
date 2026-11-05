"""Binary sensor platform for the Arcane integration."""

from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ArcaneConfigEntry, ArcaneEnvironmentData
from .entity import ArcaneContainerEntity, ArcaneEnvironmentEntity
from .util import async_add_entities_by_subentry

PARALLEL_UPDATES = 0

CONTAINER_BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="status",
        translation_key="status",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
)

ENVIRONMENT_BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="connected",
        translation_key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArcaneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Arcane binary sensors based on a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        ArcaneEnvironmentBinarySensor(
            coordinator,
            entity_description,
            environment_id,
            environment_data.environment,
        )
        for environment_id, environment_data in coordinator.data.items()
        for entity_description in ENVIRONMENT_BINARY_SENSORS
    )

    def _async_add_new_containers(
        containers: list[tuple[str, ArcaneEnvironmentData, dict]],
    ) -> None:
        """Add new container binary sensors."""
        async_add_entities_by_subentry(
            async_add_entities,
            coordinator.subentry_id_for_environment,
            (
                (
                    ArcaneContainerBinarySensor(
                        coordinator, entity_description, environment_id, container
                    ),
                    environment_id,
                )
                for environment_id, _environment_data, container in containers
                for entity_description in CONTAINER_BINARY_SENSORS
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


class ArcaneContainerBinarySensor(ArcaneContainerEntity, BinarySensorEntity):
    """Binary sensor for an Arcane container."""

    entity_description: BinarySensorEntityDescription

    @property
    @override
    def is_on(self) -> bool | None:
        """Return true if the container is running."""
        return self.container_data.get("state") == "running"


class ArcaneEnvironmentBinarySensor(ArcaneEnvironmentEntity, BinarySensorEntity):
    """Binary sensor for an Arcane environment."""

    entity_description: BinarySensorEntityDescription

    @property
    @override
    def is_on(self) -> bool | None:
        """Return true if the environment is connected."""
        return self.environment_data.environment.get("connected") is True
