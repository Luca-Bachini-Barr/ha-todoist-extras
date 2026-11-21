"""One sensor per Todoist project: open-task count plus the full task tree."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TodoistConfigEntry
from .const import DOMAIN
from .coordinator import TodoistCoordinator
from .tree import ProjectView

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TodoistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a sensor per project now, and for every project created later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new() -> None:
        new = [pid for pid in coordinator.data if pid not in known]
        known.update(new)
        if new:
            async_add_entities(TodoistProjectSensor(coordinator, pid) for pid in new)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class TodoistProjectSensor(CoordinatorEntity[TodoistCoordinator], SensorEntity):
    """Open tasks in one project; tasks, subtasks and comments as attributes."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:checkbox-marked-circle-outline"
    _attr_native_unit_of_measurement = "tasks"
    _attr_state_class = SensorStateClass.MEASUREMENT
    # The tree can be large and changes often; keep it out of the database.
    _unrecorded_attributes = frozenset({MATCH_ALL})

    def __init__(self, coordinator: TodoistCoordinator, project_id: str) -> None:
        """Bind the sensor to one project id."""
        super().__init__(coordinator)
        self._project_id = project_id
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{project_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Todoist",
            manufacturer="Doist",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://app.todoist.com",
        )

    @property
    def _project(self) -> ProjectView | None:
        return (self.coordinator.data or {}).get(self._project_id)

    @property
    def available(self) -> bool:
        """Unavailable once the project is archived or deleted."""
        return super().available and self._project is not None

    @property
    def name(self) -> str | None:
        """The project's current name (follows renames)."""
        project = self._project
        return project.name if project else self._project_id

    @property
    def native_value(self) -> int | None:
        """Open top-level tasks, like the core to-do list count."""
        project = self._project
        return project.open_tasks if project else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """The whole project tree."""
        project = self._project
        if project is None:
            return None
        return {
            "project_id": project.id,
            "url": project.url,
            "color": project.color,
            "open_subtasks": project.open_subtasks,
            "comment_count": project.comment_count,
            "project_comments": project.comments,
            "tasks": project.tasks,
        }
