"""Todoist Extras: subtasks, comments and attachments that the core Todoist
integration leaves out, plus actions to add comments (with files) and subtasks.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import TodoistClient
from .const import DOMAIN, PLATFORMS
from .coordinator import TodoistCoordinator
from .services import async_setup_services

type TodoistConfigEntry = ConfigEntry[TodoistCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions once."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TodoistConfigEntry) -> bool:
    """Do a full sync, then set up the project sensors."""
    client = TodoistClient(async_get_clientsession(hass), entry.data[CONF_API_TOKEN])
    coordinator = TodoistCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TodoistConfigEntry) -> bool:
    """Unload the sensors."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
