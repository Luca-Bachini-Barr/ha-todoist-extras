"""Setup, sensors, polling and the actions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.todoist_extras.api import TodoistAuthError, TodoistError
from custom_components.todoist_extras.const import DOMAIN, SCAN_INTERVAL

from .conftest import FAITH, LUCA, XMAS, full_sync

XMAS_SENSOR = "sensor.todoist_christmas_presents"
INBOX_SENSOR = "sensor.todoist_inbox"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_sensors(hass: HomeAssistant, client: AsyncMock, entry) -> None:
    await _setup(hass, entry)
    state = hass.states.get(XMAS_SENSOR)
    assert state.state == "3"
    assert state.attributes["open_subtasks"] == 1
    assert state.attributes["comment_count"] == 4
    assert state.attributes["project_comments"][0]["content"] == "Budget £50 each"
    tasks = state.attributes["tasks"]
    assert tasks[0]["subtasks"][0]["content"] == "Luca - subtask"
    assert tasks[0]["comments"][1]["attachment"]["is_audio"] is True
    assert hass.states.get(INBOX_SENSOR).state == "1"
    client.sync.assert_awaited_once_with("*")


async def test_incremental_poll_and_new_project(
    hass: HomeAssistant,
    client: AsyncMock,
    entry,
    freezer: FrozenDateTimeFactory,
) -> None:
    await _setup(hass, entry)
    client.sync.return_value = {
        "full_sync": False,
        "sync_token": "token-2",
        "projects": [
            {"id": "work", "name": "Work", "is_archived": False, "is_deleted": False}
        ],
        "items": [
            {"id": FAITH, "checked": True, "project_id": XMAS},
            {
                "id": "w1",
                "content": "Report",
                "project_id": "work",
                "parent_id": None,
                "child_order": 1,
            },
        ],
    }
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    client.sync.assert_awaited_with("token-1")
    assert hass.states.get(XMAS_SENSOR).state == "2"
    assert hass.states.get("sensor.todoist_work").state == "1"


async def test_project_archived_becomes_unavailable(
    hass: HomeAssistant, client: AsyncMock, entry, freezer: FrozenDateTimeFactory
) -> None:
    await _setup(hass, entry)
    client.sync.return_value = {
        "full_sync": False,
        "sync_token": "token-2",
        "projects": [{"id": XMAS, "is_archived": True}],
    }
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(XMAS_SENSOR).state == "unavailable"


async def test_full_sync_again_after_interval(
    hass: HomeAssistant, client: AsyncMock, entry, freezer: FrozenDateTimeFactory
) -> None:
    await _setup(hass, entry)
    client.sync.return_value = {"full_sync": False, "sync_token": "token-2"}
    for _ in range(30):
        freezer.tick(SCAN_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert client.sync.await_args.args == ("*",)


async def test_setup_errors(hass: HomeAssistant, client: AsyncMock, entry) -> None:
    client.sync.side_effect = TodoistError("down")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_auth_error_starts_reauth(
    hass: HomeAssistant, client: AsyncMock, entry
) -> None:
    client.sync.side_effect = TodoistAuthError("401")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert flows and flows[0]["context"]["source"] == "reauth"


async def test_poll_error_keeps_last_data_unavailable(
    hass: HomeAssistant, client: AsyncMock, entry, freezer: FrozenDateTimeFactory
) -> None:
    await _setup(hass, entry)
    client.sync.side_effect = TodoistError("down")
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(XMAS_SENSOR).state == "unavailable"


async def test_unload(hass: HomeAssistant, client: AsyncMock, entry) -> None:
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_add_comment_text_by_task_name(
    hass: HomeAssistant, client: AsyncMock, entry
) -> None:
    await _setup(hass, entry)
    result = await hass.services.async_call(
        DOMAIN,
        "add_comment",
        {"task": "luca", "content": "Size 14"},
        blocking=True,
        return_response=True,
    )
    client.add_comment.assert_awaited_once_with(
        "Size 14", attachment=None, task_id=LUCA
    )
    assert result == {"comment_id": "c-new", "attachment": None}


async def test_add_comment_on_project(
    hass: HomeAssistant, client: AsyncMock, entry
) -> None:
    await _setup(hass, entry)
    await hass.services.async_call(
        DOMAIN,
        "add_comment",
        {"project": "Christmas Presents", "content": "Budget"},
        blocking=True,
    )
    client.add_comment.assert_awaited_once_with(
        "Budget", attachment=None, project_id=XMAS
    )


async def test_add_comment_with_file(
    hass: HomeAssistant, client: AsyncMock, entry, tmp_path: Path
) -> None:
    await _setup(hass, entry)
    audio = tmp_path / "note.mp3"
    audio.write_bytes(b"ID3fake")
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    result = await hass.services.async_call(
        DOMAIN,
        "add_comment",
        {"task": LUCA, "file": str(audio)},
        blocking=True,
        return_response=True,
    )
    client.upload.assert_awaited_once_with("note.mp3", b"ID3fake", "audio/mpeg")
    client.add_comment.assert_awaited_once_with(
        "note.mp3",
        attachment={
            "file_name": "note.mp3",
            "file_type": "audio/mpeg",
            "file_url": "https://files.todoist.com/x/note.mp3",
            "resource_type": "file",
        },
        task_id=LUCA,
    )
    assert result["attachment"]["file_url"].endswith("note.mp3")


@pytest.mark.parametrize(
    ("data", "key"),
    [
        ({"task": "nobody", "content": "x"}, "task_not_found"),
        ({"project": "Work", "content": "x"}, "project_not_found"),
        ({"task": "Luca", "content": "  "}, "empty_comment"),
        ({"task": "Luca", "file": "/etc/passwd"}, "path_not_allowed"),
    ],
)
async def test_add_comment_validation(
    hass: HomeAssistant, client: AsyncMock, entry, data, key
) -> None:
    await _setup(hass, entry)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "add_comment", data, blocking=True)
    assert err.value.translation_key == key
    client.add_comment.assert_not_awaited()


async def test_add_comment_missing_file(
    hass: HomeAssistant, client: AsyncMock, entry, tmp_path: Path
) -> None:
    await _setup(hass, entry)
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_comment",
            {"task": "Luca", "file": str(tmp_path / "missing.mp3")},
            blocking=True,
        )
    assert err.value.translation_key == "file_not_found"


async def test_add_comment_api_error(
    hass: HomeAssistant, client: AsyncMock, entry
) -> None:
    await _setup(hass, entry)
    client.add_comment.side_effect = TodoistError("boom")
    with pytest.raises(HomeAssistantError, match="boom"):
        await hass.services.async_call(
            DOMAIN, "add_comment", {"task": "Luca", "content": "x"}, blocking=True
        )


async def test_add_subtask(hass: HomeAssistant, client: AsyncMock, entry) -> None:
    await _setup(hass, entry)
    result = await hass.services.async_call(
        DOMAIN,
        "add_subtask",
        {"task": "Luca", "content": "Wrap it", "due_string": "tomorrow"},
        blocking=True,
        return_response=True,
    )
    client.add_task.assert_awaited_once_with(
        "Wrap it", parent_id=LUCA, description=None, due_string="tomorrow"
    )
    assert result == {"task_id": "t-new"}


async def test_add_subtask_api_error(
    hass: HomeAssistant, client: AsyncMock, entry
) -> None:
    await _setup(hass, entry)
    client.add_task.side_effect = TodoistError("boom")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "add_subtask", {"task": "Luca", "content": "x"}, blocking=True
        )


async def test_actions_need_a_loaded_entry(
    hass: HomeAssistant, client: AsyncMock, entry
) -> None:
    await _setup(hass, entry)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_comment",
            {"config_entry_id": "nope", "task": "Luca", "content": "x"},
            blocking=True,
        )
    assert err.value.translation_key == "not_loaded"


async def test_actions_need_entry_choice_with_two_accounts(
    hass: HomeAssistant, client: AsyncMock, entry
) -> None:
    await _setup(hass, entry)
    second = MockConfigEntry(
        domain=DOMAIN, unique_id="other", data={"api_token": "t2"}
    )
    client.sync.return_value = full_sync()
    await _setup(hass, second)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "add_comment", {"task": "Luca", "content": "x"}, blocking=True
        )
    assert err.value.translation_key == "pick_entry"
