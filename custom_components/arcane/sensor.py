"""Sensor platform for the Arcane integration."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .coordinator import (
    ArcaneConfigEntry,
    ArcaneEnvironmentData,
)
from .entity import (
    ArcaneContainerEntity,
    ArcaneEnvironmentEntity,
    ArcaneProjectEntity,
)
from .util import async_add_entities_by_subentry

PARALLEL_UPDATES = 0


def _resource_sample(container: dict[str, Any]) -> dict[str, Any]:
    return container.get("resourceSample") or {}


def _cpu_usage(container: dict[str, Any]) -> float | None:
    return _resource_sample(container).get("cpuPercent")


def _memory_usage(container: dict[str, Any]) -> int | None:
    return _resource_sample(container).get("memoryUsageBytes")


def _memory_limit(container: dict[str, Any]) -> int | None:
    sample = _resource_sample(container)
    return sample.get("memoryLimitBytes") or (container.get("hostConfig") or {}).get(
        "memory"
    )


def _memory_usage_percentage(container: dict[str, Any]) -> float | None:
    sample = _resource_sample(container)
    usage = sample.get("memoryUsageBytes")
    limit = sample.get("memoryLimitBytes")
    if not usage or not limit:
        return None
    return round(usage / limit * 100, 1)


@dataclass(frozen=True, kw_only=True)
class ArcaneContainerSensorEntityDescription(SensorEntityDescription):
    """Class to hold Arcane container sensor descriptions."""

    value_fn: Callable[[dict[str, Any]], StateType | datetime]


@dataclass(frozen=True, kw_only=True)
class ArcaneEnvironmentSensorEntityDescription(SensorEntityDescription):
    """Class to hold Arcane environment sensor descriptions."""

    value_fn: Callable[[ArcaneEnvironmentData], StateType]


@dataclass(frozen=True, kw_only=True)
class ArcaneProjectSensorEntityDescription(SensorEntityDescription):
    """Class to hold Arcane project sensor descriptions."""

    value_fn: Callable[[dict[str, Any]], StateType]


CONTAINER_SENSORS: tuple[ArcaneContainerSensorEntityDescription, ...] = (
    ArcaneContainerSensorEntityDescription(
        key="image",
        translation_key="image",
        value_fn=lambda container: container.get("image"),
    ),
    ArcaneContainerSensorEntityDescription(
        key="container_state",
        translation_key="container_state",
        value_fn=lambda container: container.get("state"),
        device_class=SensorDeviceClass.ENUM,
        options=[
            "created",
            "running",
            "paused",
            "restarting",
            "removing",
            "exited",
            "dead",
        ],
    ),
    ArcaneContainerSensorEntityDescription(
        key="container_status",
        translation_key="container_status",
        value_fn=lambda container: container.get("status"),
    ),
    ArcaneContainerSensorEntityDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        value_fn=_cpu_usage,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ArcaneContainerSensorEntityDescription(
        key="memory_usage",
        translation_key="memory_usage",
        value_fn=_memory_usage,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ArcaneContainerSensorEntityDescription(
        key="memory_usage_percentage",
        translation_key="memory_usage_percentage",
        value_fn=_memory_usage_percentage,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ArcaneContainerSensorEntityDescription(
        key="memory_limit",
        translation_key="memory_limit",
        value_fn=_memory_limit,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
    ),
    ArcaneContainerSensorEntityDescription(
        key="container_started_at",
        translation_key="container_started_at",
        value_fn=lambda container: (
            parsed
            if (started_at := (container.get("state") or {}).get("startedAt"))
            and (parsed := dt_util.parse_datetime(started_at)) is not None
            and parsed.year > 1
            else None
        ),
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

ENVIRONMENT_SENSORS: tuple[ArcaneEnvironmentSensorEntityDescription, ...] = (
    ArcaneEnvironmentSensorEntityDescription(
        key="docker_version",
        translation_key="docker_version",
        value_fn=lambda data: data.docker_info.get("ServerVersion"),
    ),
    ArcaneEnvironmentSensorEntityDescription(
        key="kernel_version",
        translation_key="kernel_version",
        value_fn=lambda data: data.docker_info.get("KernelVersion"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ArcaneEnvironmentSensorEntityDescription(
        key="operating_system",
        translation_key="operating_system",
        value_fn=lambda data: data.docker_info.get("OperatingSystem"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ArcaneEnvironmentSensorEntityDescription(
        key="memory_total",
        translation_key="memory_total",
        value_fn=lambda data: data.docker_info.get("MemTotal"),
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
    ),
    ArcaneEnvironmentSensorEntityDescription(
        key="cpu_total",
        translation_key="cpu_total",
        value_fn=lambda data: data.docker_info.get("NCPU"),
    ),
    ArcaneEnvironmentSensorEntityDescription(
        key="containers_running",
        translation_key="containers_running",
        value_fn=lambda data: data.docker_info.get("ContainersRunning"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ArcaneEnvironmentSensorEntityDescription(
        key="containers_stopped",
        translation_key="containers_stopped",
        value_fn=lambda data: data.docker_info.get("ContainersStopped"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ArcaneEnvironmentSensorEntityDescription(
        key="containers_paused",
        translation_key="containers_paused",
        value_fn=lambda data: data.docker_info.get("ContainersPaused"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ArcaneEnvironmentSensorEntityDescription(
        key="containers_count",
        translation_key="containers_count",
        value_fn=lambda data: data.docker_info.get("Containers"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ArcaneEnvironmentSensorEntityDescription(
        key="images_count",
        translation_key="images_count",
        value_fn=lambda data: data.docker_info.get("Images"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ArcaneEnvironmentSensorEntityDescription(
        key="image_disk_usage_total_size",
        translation_key="image_disk_usage_total_size",
        value_fn=lambda data: (data.usage.get("images") or {}).get("totalImageSize"),
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ArcaneEnvironmentSensorEntityDescription(
        key="volumes_count",
        translation_key="volumes_count",
        value_fn=lambda data: (data.usage.get("volumes") or {}).get("total"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

PROJECT_SENSORS: tuple[ArcaneProjectSensorEntityDescription, ...] = (
    ArcaneProjectSensorEntityDescription(
        key="project_status",
        translation_key="project_status",
        value_fn=lambda project: project.get("status"),
    ),
    ArcaneProjectSensorEntityDescription(
        key="project_service_count",
        translation_key="project_service_count",
        value_fn=lambda project: project.get("serviceCount"),
    ),
    ArcaneProjectSensorEntityDescription(
        key="project_running_count",
        translation_key="project_running_count",
        value_fn=lambda project: project.get("runningCount"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArcaneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Arcane sensors based on a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        ArcaneEnvironmentSensor(
            coordinator,
            entity_description,
            environment_id,
            environment_data.environment,
        )
        for environment_id, environment_data in coordinator.data.items()
        for entity_description in ENVIRONMENT_SENSORS
    )

    def _async_add_new_projects(
        projects: list[tuple[str, ArcaneEnvironmentData, dict[str, Any]]],
    ) -> None:
        """Add new project sensors."""
        async_add_entities_by_subentry(
            async_add_entities,
            coordinator.subentry_id_for_environment,
            (
                (
                    ArcaneProjectSensor(
                        coordinator, entity_description, environment_id, project
                    ),
                    environment_id,
                )
                for environment_id, _environment_data, project in projects
                for entity_description in PROJECT_SENSORS
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
        """Add new container sensors."""
        async_add_entities_by_subentry(
            async_add_entities,
            coordinator.subentry_id_for_environment,
            (
                (
                    ArcaneContainerSensor(
                        coordinator, entity_description, environment_id, container
                    ),
                    environment_id,
                )
                for environment_id, _environment_data, container in containers
                for entity_description in CONTAINER_SENSORS
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


class ArcaneContainerSensor(ArcaneContainerEntity, SensorEntity):
    """Sensor for an Arcane container."""

    entity_description: ArcaneContainerSensorEntityDescription

    @property
    @override
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.container_data)


class ArcaneEnvironmentSensor(ArcaneEnvironmentEntity, SensorEntity):
    """Sensor for an Arcane environment."""

    entity_description: ArcaneEnvironmentSensorEntityDescription

    @property
    @override
    def native_value(self) -> StateType:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.environment_data)


class ArcaneProjectSensor(ArcaneProjectEntity, SensorEntity):
    """Sensor for an Arcane project."""

    entity_description: ArcaneProjectSensorEntityDescription

    @property
    @override
    def native_value(self) -> StateType:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.project_data)
