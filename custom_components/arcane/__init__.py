"""The Arcane integration."""

import logging

from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
import homeassistant.helpers.device_registry as dr

from .api import ArcaneClient
from .const import API_MAX_RETRIES, DOMAIN
from .coordinator import ArcaneConfigEntry, ArcaneCoordinator, ArcaneVersionCoordinator
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]

_LOGGER = logging.getLogger(__name__)


async def _async_update_listener(hass: HomeAssistant, entry: ArcaneConfigEntry) -> None:
    """Reload the entry when it, or one of its environment subentries, changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ArcaneConfigEntry) -> None:
    """Set up Arcane from a config entry."""
    session = async_create_clientsession(
        hass=hass, verify_ssl=entry.data[CONF_VERIFY_SSL]
    )
    client = ArcaneClient(
        api_url=entry.data[CONF_URL],
        api_key=entry.data[CONF_API_TOKEN],
        session=session,
        max_retries=API_MAX_RETRIES,
    )

    coordinator = ArcaneCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    version_coordinator = ArcaneVersionCoordinator(hass, entry, client)
    await version_coordinator.async_refresh()
    coordinator.version = version_coordinator

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Register the environment and project devices up front so that container
    # entities can deterministically resolve them as their via device when
    # their platforms are set up below, regardless of platform/entity add order.
    coordinator.async_register_environment_and_project_devices(
        coordinator.data,
        set(coordinator.data),
        {
            (environment_id, project_id)
            for environment_id, environment_data in coordinator.data.items()
            for project_id in environment_data.projects
        },
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Arcane integration."""
    async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ArcaneConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ArcaneConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Remove a config entry device."""
    coordinator = entry.runtime_data
    valid_identifiers: set[tuple[str, str]] = {(DOMAIN, entry.entry_id)}

    valid_identifiers.update(
        (DOMAIN, f"{entry.entry_id}_{environment_id}")
        for environment_id in coordinator.data
    )
    valid_identifiers.update(
        (
            DOMAIN,
            f"{entry.entry_id}_{environment_id}_project_{project_id}",
        )
        for environment_id, environment_data in coordinator.data.items()
        for project_id in environment_data.projects
    )
    valid_identifiers.update(
        (DOMAIN, f"{entry.entry_id}_{environment_id}_{name}")
        for environment_id, environment_data in coordinator.data.items()
        for name in environment_data.containers
    )

    return not device.identifiers.intersection(valid_identifiers)
