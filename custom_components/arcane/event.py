"""Event platform for the Arcane integration."""

from typing import override

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import EVENT_TYPES
from .coordinator import ArcaneConfigEntry, ArcaneCoordinator
from .entity import ArcaneEnvironmentEntity

PARALLEL_UPDATES = 0

EVENT_DESCRIPTION = EventEntityDescription(
    key="event",
    translation_key="event",
    entity_category=EntityCategory.DIAGNOSTIC,
    event_types=list(EVENT_TYPES),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArcaneConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Arcane event entities based on a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        ArcaneEnvironmentEventEntity(
            coordinator, EVENT_DESCRIPTION, environment_id, environment_data.environment
        )
        for environment_id, environment_data in coordinator.data.items()
    )


class ArcaneEnvironmentEventEntity(ArcaneEnvironmentEntity, EventEntity):
    """Event entity surfacing Arcane's event log for an environment."""

    entity_description: EventEntityDescription
    _last_fired_id: str | None = None

    def __init__(
        self,
        coordinator: ArcaneCoordinator,
        entity_description: EventEntityDescription,
        environment_id: str,
        environment: dict,
    ) -> None:
        """Initialize the Arcane event entity."""
        super().__init__(coordinator, entity_description, environment_id, environment)
        self._last_fired_id = None

    @override
    def _handle_coordinator_update(self) -> None:
        """Fire HA events for entries that appeared since the last refresh."""
        if self.available and (events := self.environment_data.events):
            if self._last_fired_id is None:
                # First refresh: remember the newest entry without replaying
                # the history that already happened before HA was running.
                self._last_fired_id = events[0].get("id")
            else:
                new_events = []
                for event in events:
                    if event.get("id") == self._last_fired_id:
                        break
                    new_events.append(event)
                else:
                    # The baseline left the fetched page (log turnover or an
                    # earlier fetch failure): re-baseline instead of replaying
                    # a whole page of history.
                    self._last_fired_id = events[0].get("id")
                    new_events = []

                if new_events:
                    self._last_fired_id = new_events[0].get("id")
                    for event in reversed(new_events):
                        event_type = event.get("type")
                        if event_type not in EVENT_TYPES:
                            continue
                        self._trigger_event(
                            event_type,
                            {
                                "title": event.get("title"),
                                "description": event.get("description"),
                                "severity": event.get("severity"),
                                "resource_type": event.get("resourceType"),
                                "resource_name": event.get("resourceName"),
                                "username": event.get("username"),
                            },
                        )
        super()._handle_coordinator_update()
