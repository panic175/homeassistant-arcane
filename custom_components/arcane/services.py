"""Services for the Arcane integration."""

from enum import StrEnum

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    service,
)
import probatio

from .const import DOMAIN
from .coordinator import ArcaneConfigEntry

# Plain string so the integration also works on Home Assistant versions
# that do not ship homeassistant.const.CommonServiceArgument yet.
CONF_DEVICE_ID = "device_id"


class ArcaneService(StrEnum):
    """Store keys for Arcane services."""

    PRUNE_IMAGES = "prune_images"
    PRUNE_VOLUMES = "prune_volumes"
    PRUNE_NETWORKS = "prune_networks"
    RECREATE_CONTAINER = "recreate_container"


class ArcaneServiceArgument(StrEnum):
    """Store keys for Arcane service arguments."""

    DANGLING = "dangling"
    CONTAINER_DEVICE_ID = "container_device_id"


SERVICE_PRUNE_IMAGES_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_DEVICE_ID): cv.string,
        probatio.Optional(ArcaneServiceArgument.DANGLING): cv.boolean,
    },
)

SERVICE_PRUNE_VOLUMES_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_DEVICE_ID): cv.string,
    },
)

SERVICE_PRUNE_NETWORKS_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_DEVICE_ID): cv.string,
    },
)

SERVICE_RECREATE_CONTAINER_SCHEMA = probatio.Schema(
    {
        probatio.Required(ArcaneServiceArgument.CONTAINER_DEVICE_ID): cv.string,
    },
)


@callback
def _async_get_device_and_entry(
    call: ServiceCall, device_id: str
) -> tuple[dr.AnyDeviceEntry, ArcaneConfigEntry]:
    """Resolve and validate the device and Arcane config entry for a device ID."""
    device, config_entry = service.async_get_device_and_config_entry(
        call.hass, DOMAIN, device_id
    )
    return device, config_entry


@callback
def _async_get_environment_id(
    device: dr.AnyDeviceEntry,
    config_entry: ArcaneConfigEntry,
) -> str:
    """Get the environment ID from an environment device entry."""
    coordinator = config_entry.runtime_data

    for environment_id in coordinator.data:
        if (
            DOMAIN,
            f"{config_entry.entry_id}_{environment_id}",
        ) in device.identifiers:
            return environment_id

    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="invalid_target",
    )


@callback
def _async_get_container_and_environment_ids(
    device: dr.AnyDeviceEntry,
    config_entry: ArcaneConfigEntry,
) -> tuple[str, str]:
    """Get the environment ID and container ID from a container device entry."""
    coordinator = config_entry.runtime_data

    for environment_id, environment_data in coordinator.data.items():
        for name, container in environment_data.containers.items():
            if (
                DOMAIN,
                f"{config_entry.entry_id}_{environment_id}_{name}",
            ) in device.identifiers:
                return environment_id, container["id"]

    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="invalid_target",
    )


async def prune_images(call: ServiceCall) -> None:
    """Prune unused images in Arcane."""
    device, config_entry = _async_get_device_and_entry(call, call.data[CONF_DEVICE_ID])
    coordinator = config_entry.runtime_data
    environment_id = _async_get_environment_id(device, config_entry)

    await coordinator.async_call_arcane(
        coordinator.client.async_prune_images(
            environment_id,
            dangling=call.data.get(ArcaneServiceArgument.DANGLING, False),
        ),
    )


async def prune_volumes(call: ServiceCall) -> None:
    """Prune unused volumes in Arcane."""
    device, config_entry = _async_get_device_and_entry(call, call.data[CONF_DEVICE_ID])
    coordinator = config_entry.runtime_data
    environment_id = _async_get_environment_id(device, config_entry)

    await coordinator.async_call_arcane(
        coordinator.client.async_prune_volumes(environment_id),
    )


async def prune_networks(call: ServiceCall) -> None:
    """Prune unused networks in Arcane."""
    device, config_entry = _async_get_device_and_entry(call, call.data[CONF_DEVICE_ID])
    coordinator = config_entry.runtime_data
    environment_id = _async_get_environment_id(device, config_entry)

    await coordinator.async_call_arcane(
        coordinator.client.async_prune_networks(environment_id),
    )


async def recreate_container(call: ServiceCall) -> None:
    """Pull the latest image and recreate a container in Arcane."""
    device, config_entry = _async_get_device_and_entry(
        call, call.data[ArcaneServiceArgument.CONTAINER_DEVICE_ID]
    )
    coordinator = config_entry.runtime_data
    environment_id, container_id = _async_get_container_and_environment_ids(
        device, config_entry
    )

    await coordinator.async_call_arcane(
        coordinator.client.async_update_container(environment_id, container_id),
    )

    await coordinator.async_request_refresh()


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services."""

    service.async_register_admin_service(
        hass,
        DOMAIN,
        ArcaneService.PRUNE_IMAGES,
        prune_images,
        SERVICE_PRUNE_IMAGES_SCHEMA,
    )

    service.async_register_admin_service(
        hass,
        DOMAIN,
        ArcaneService.PRUNE_VOLUMES,
        prune_volumes,
        SERVICE_PRUNE_VOLUMES_SCHEMA,
    )

    service.async_register_admin_service(
        hass,
        DOMAIN,
        ArcaneService.PRUNE_NETWORKS,
        prune_networks,
        SERVICE_PRUNE_NETWORKS_SCHEMA,
    )

    service.async_register_admin_service(
        hass,
        DOMAIN,
        ArcaneService.RECREATE_CONTAINER,
        recreate_container,
        SERVICE_RECREATE_CONTAINER_SCHEMA,
    )
