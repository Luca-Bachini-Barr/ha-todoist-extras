"""The HTTP client against a mocked api.todoist.com."""

from __future__ import annotations

import json

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.todoist_extras.api import (
    TodoistAuthError,
    TodoistClient,
    TodoistError,
)

BASE = "https://api.todoist.com/api/v1"


async def test_sync_sends_token_and_resources(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/sync", json={"sync_token": "t", "full_sync": True})
    client = TodoistClient(async_get_clientsession(hass), "secret")
    assert (await client.sync())["sync_token"] == "t"
    _, _, data, headers = aioclient_mock.mock_calls[0]
    assert headers["Authorization"] == "Bearer secret"
    assert data["sync_token"] == "*"
    assert "notes" in json.loads(data["resource_types"])


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, TodoistAuthError), (403, TodoistAuthError), (500, TodoistError)],
)
async def test_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status, error
) -> None:
    aioclient_mock.post(f"{BASE}/sync", status=status, text="nope")
    client = TodoistClient(async_get_clientsession(hass), "secret")
    with pytest.raises(error):
        await client.sync()


async def test_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/sync", exc=TimeoutError())
    client = TodoistClient(async_get_clientsession(hass), "secret")
    with pytest.raises(TodoistError):
        await client.sync()


async def test_comment_task_and_upload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/uploads", json={"file_url": "u"})
    aioclient_mock.post(f"{BASE}/comments", json={"id": "c"})
    aioclient_mock.post(f"{BASE}/tasks", json={"id": "t"})
    client = TodoistClient(async_get_clientsession(hass), "secret")
    attachment = await client.upload("a.mp3", b"x", "audio/mpeg")
    assert attachment == {"file_url": "u"}
    assert await client.add_comment("hi", task_id="1", attachment=attachment) == {
        "id": "c"
    }
    assert aioclient_mock.mock_calls[1][2] == {
        "content": "hi",
        "task_id": "1",
        "attachment": {"file_url": "u"},
    }
    await client.add_comment("hi", project_id="p")
    assert aioclient_mock.mock_calls[2][2] == {"content": "hi", "project_id": "p"}
    assert await client.add_task("sub", parent_id="1", due_string=None) == {"id": "t"}
    assert aioclient_mock.mock_calls[3][2] == {"content": "sub", "parent_id": "1"}
