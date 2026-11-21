"""Polls Todoist's sync endpoint and keeps the account tree up to date."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import TodoistAuthError, TodoistClient, TodoistError
from .const import DOMAIN, FULL_SYNC_INTERVAL, SCAN_INTERVAL
from .tree import AccountState, ProjectView, build_projects

_LOGGER = logging.getLogger(__name__)


class TodoistCoordinator(DataUpdateCoordinator[dict[str, ProjectView]]):
    """One coordinator per Todoist account; data = project id -> view."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: TodoistClient
    ) -> None:
        """Start from a full sync."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.state = AccountState()
        self._sync_token = "*"
        self._last_full_sync = None

    async def _async_update_data(self) -> dict[str, ProjectView]:
        now = dt_util.utcnow()
        if self._last_full_sync is None or now - self._last_full_sync >= FULL_SYNC_INTERVAL:
            self._sync_token = "*"
        try:
            payload = await self.client.sync(self._sync_token)
        except TodoistAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TodoistError as err:
            raise UpdateFailed(str(err)) from err
        self.state.apply(payload)
        if payload.get("full_sync"):
            self._last_full_sync = now
        self._sync_token = payload.get("sync_token") or "*"
        return build_projects(self.state)
