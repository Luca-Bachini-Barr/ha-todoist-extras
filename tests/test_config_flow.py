"""Config flow and reauth."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.todoist_extras.api import TodoistAuthError, TodoistError
from custom_components.todoist_extras.const import DOMAIN

from .conftest import TOKEN


async def test_user_flow(hass: HomeAssistant, client: AsyncMock) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: f" {TOKEN} "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "John"
    assert result["data"] == {CONF_API_TOKEN: TOKEN}
    assert result["result"].unique_id == "61550591"
    client.sync.assert_any_await(resource_types=["user"])


@pytest.mark.parametrize(
    ("error", "key"),
    [(TodoistAuthError("401"), "invalid_auth"), (TodoistError("down"), "cannot_connect")],
)
async def test_user_flow_errors(
    hass: HomeAssistant, client: AsyncMock, error, key
) -> None:
    client.sync.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: TOKEN}
    )
    assert result["errors"] == {"base": key}
    client.sync.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured(
    hass: HomeAssistant, client: AsyncMock, entry
) -> None:
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, client: AsyncMock, entry) -> None:
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    client.sync.side_effect = TodoistAuthError("401")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: "bad"}
    )
    assert result["errors"] == {"base": "invalid_auth"}
    client.sync.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: "newtoken"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_TOKEN] == "newtoken"


async def test_reauth_wrong_account(
    hass: HomeAssistant, client: AsyncMock, entry
) -> None:
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    client.sync.return_value = {"user": {"id": "someone-else"}}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: "other"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"


@pytest.mark.parametrize("reply", [{}, {"user": {}}, {"user": None}])
async def test_user_flow_reply_without_user_id(
    hass: HomeAssistant, client: AsyncMock, reply
) -> None:
    client.sync.return_value = reply
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: TOKEN}
    )
    assert result["errors"] == {"base": "cannot_connect"}
