"""Diagnostics for the Arcane integration."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant

from .coordinator import ArcaneConfigEntry, ArcaneCoordinator

TO_REDACT = [CONF_API_TOKEN, CONF_URL, "apiKey"]


def _serialize_coordinator(coordinator: ArcaneCoordinator) -> dict[str, Any]:
    """Serialize coordinator data into a JSON-safe structure."""
    environments: list[dict[str, Any]] = []
    for environment_id, environment_data in coordinator.data.items():
        environments.append(
            {
                "id": environment_id,
                "name": environment_data.environment.get("name"),
                "status": environment_data.environment.get("status"),
                "connected": environment_data.environment.get("connected"),
                "docker_info": environment_data.docker_info,
                "usage": environment_data.usage,
                "containers": [
                    {
                        "id": container.get("id"),
                        "names": container.get("names"),
                        "image": container.get("image"),
                        "state": container.get("state"),
                        "status": container.get("status"),
                    }
                    for container in environment_data.containers.values()
                ],
                "projects": [
                    {
                        "id": project.get("id"),
                        "name": project.get("name"),
                        "status": project.get("status"),
                        "serviceCount": project.get("serviceCount"),
                        "runningCount": project.get("runningCount"),
                    }
                    for project in environment_data.projects.values()
                ],
            }
        )

    return {"environments": environments}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ArcaneConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for an Arcane config entry."""
    coordinator = config_entry.runtime_data

    return {
        "config_entry": async_redact_data(config_entry.as_dict(), TO_REDACT),
        "coordinator": _serialize_coordinator(coordinator),
        "version": coordinator.version.data if coordinator.version else None,
    }
