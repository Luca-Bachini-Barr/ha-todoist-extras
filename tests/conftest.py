"""Fixtures: a sync payload shaped like a real Todoist account and a mocked client."""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_API_TOKEN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.todoist_extras.const import DOMAIN

PYTEST_PLUGINS = "pytest_homeassistant_custom_component"

INBOX = "6j43pgfhpHGRpFhp"
XMAS = "6j43w3XHP3WV99F3"
LUCA = "6j43w7wJjH5R3HR3"
LUCA_SUB = "6j448f2q9HxwFJ33"
JANNA = "6j4485673jjFJ6R3"
FAITH = "6j44986R8hrcC84V"
TEST1 = "6j43v3VP5jVR6pQG"


def _project(pid: str, name: str, order: int, inbox: bool = False) -> dict[str, Any]:
    return {
        "id": pid,
        "name": name,
        "color": "charcoal",
        "child_order": order,
        "is_archived": False,
        "is_deleted": False,
        "inbox_project": inbox,
        "parent_id": None,
    }


def _item(
    iid: str,
    content: str,
    project: str,
    order: int,
    parent: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    base = {
        "id": iid,
        "content": content,
        "description": "",
        "project_id": project,
        "section_id": None,
        "parent_id": parent,
        "child_order": order,
        "checked": False,
        "is_deleted": False,
        "labels": [],
        "priority": 1,
        "due": None,
        "deadline": None,
        "duration": None,
    }
    base.update(extra)
    return base


FULL_SYNC: dict[str, Any] = {
    "full_sync": True,
    "sync_token": "token-1",
    "user": {"id": "61550591", "full_name": "John", "email": "john@example.com"},
    "projects": [_project(INBOX, "Inbox", 0, True), _project(XMAS, "Christmas Presents", 2)],
    "sections": [],
    "items": [
        _item(TEST1, "test task number 1", INBOX, 1, due={"date": "2026-11-21", "string": "21 Nov", "is_recurring": False}),
        _item(LUCA, "Luca", XMAS, 1, description="overwrite existing description ?"),
        _item(LUCA_SUB, "Luca - subtask", XMAS, 1, parent=LUCA),
        _item(
            JANNA,
            "Janna",
            XMAS,
            2,
            description="money, some hand warmers",
            priority=4,
            labels=["family"],
            due={"date": "2026-11-28T14:00:00", "string": "28 Nov 14:00", "is_recurring": False},
            duration={"amount": 30, "unit": "minute"},
            deadline={"date": "2026-12-20"},
        ),
        _item(FAITH, "Faith", XMAS, 3),
    ],
    "notes": [
        {
            "id": "n2",
            "item_id": LUCA,
            "content": "voice note",
            "posted_at": "2026-11-21T13:00:00Z",
            "is_deleted": False,
            "file_attachment": {
                "file_name": "note.m4a",
                "file_type": "audio/mp4",
                "file_url": "https://files.todoist.com/note.m4a",
                "resource_type": "file",
            },
        },
        {
            "id": "n1",
            "item_id": LUCA,
            "content": "Size 14",
            "posted_at": "2026-11-21T12:00:00Z",
            "is_deleted": False,
            "file_attachment": None,
        },
        {
            "id": "n3",
            "item_id": LUCA_SUB,
            "content": "from Argos",
            "posted_at": "2026-11-21T12:30:00Z",
            "is_deleted": False,
        },
    ],
    "project_notes": [
        {
            "id": "p1",
            "project_id": XMAS,
            "content": "Budget £50 each",
            "posted_at": "2026-11-21T11:00:00Z",
            "is_deleted": False,
        }
    ],
}

TOKEN = "0123456789abcdef"


def full_sync() -> dict[str, Any]:
    """A fresh copy of the full-sync payload."""
    return copy.deepcopy(FULL_SYNC)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom integrations in every test."""
    yield


@pytest.fixture
def client() -> AsyncMock:
    """The Todoist client as the integration and the flow use it."""
    mock = AsyncMock()
    mock.sync.return_value = full_sync()
    mock.upload.return_value = {
        "file_name": "note.mp3",
        "file_type": "audio/mpeg",
        "file_url": "https://files.todoist.com/x/note.mp3",
        "resource_type": "file",
        "upload_state": "completed",
    }
    mock.add_comment.return_value = {"id": "c-new"}
    mock.add_task.return_value = {"id": "t-new"}
    with (
        patch("custom_components.todoist_extras.TodoistClient", return_value=mock),
        patch(
            "custom_components.todoist_extras.config_flow.TodoistClient",
            return_value=mock,
        ),
    ):
        yield mock


@pytest.fixture
def entry() -> MockConfigEntry:
    """A Todoist Extras entry for the fixture account."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="John",
        unique_id="61550591",
        data={CONF_API_TOKEN: TOKEN},
    )
