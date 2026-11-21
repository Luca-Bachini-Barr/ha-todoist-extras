"""Actions: add a comment (optionally with a file, e.g. audio) and add a subtask."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import TodoistError
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_CONTENT,
    ATTR_DESCRIPTION,
    ATTR_DUE_STRING,
    ATTR_FILE,
    ATTR_PROJECT,
    ATTR_TASK,
    DOMAIN,
    MAX_UPLOAD_BYTES,
    SERVICE_ADD_COMMENT,
    SERVICE_ADD_SUBTASK,
)
from .tree import find_project, find_task

if TYPE_CHECKING:
    from .coordinator import TodoistCoordinator

_LOGGER = logging.getLogger(__name__)

ADD_COMMENT_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
            vol.Exclusive(ATTR_TASK, "target"): cv.string,
            vol.Exclusive(ATTR_PROJECT, "target"): cv.string,
            vol.Optional(ATTR_CONTENT, default=""): cv.string,
            vol.Optional(ATTR_FILE): cv.string,
        }
    ),
    cv.has_at_least_one_key(ATTR_TASK, ATTR_PROJECT),
)

# What a comment's attachment carries (the upload result has more keys).
ATTACHMENT_FIELDS = ("file_name", "file_type", "file_url", "resource_type")

ADD_SUBTASK_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_TASK): cv.string,
        vol.Required(ATTR_CONTENT): cv.string,
        vol.Optional(ATTR_DESCRIPTION): cv.string,
        vol.Optional(ATTR_DUE_STRING): cv.string,
    }
)


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> TodoistCoordinator:
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    wanted = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if wanted:
        entries = [e for e in entries if e.entry_id == wanted]
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    if len(entries) > 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="pick_entry"
        )
    return entries[0].runtime_data


def _task_id(coordinator: TodoistCoordinator, ref: str) -> str:
    task_id = find_task(coordinator.state, ref)
    if task_id is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="task_not_found",
            translation_placeholders={"task": ref},
        )
    return task_id


def _read_file(hass: HomeAssistant, path: str) -> tuple[str, bytes, str | None]:
    """Runs in the executor: check the path is allowed and read it."""
    file = Path(path)
    if not hass.config.is_allowed_path(str(file)):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="path_not_allowed",
            translation_placeholders={"file": path},
        )
    if not file.is_file():
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="file_not_found",
            translation_placeholders={"file": path},
        )
    try:
        with file.open("rb") as handle:
            # Read one byte past the cap so a file that grew is still caught.
            data = handle.read(MAX_UPLOAD_BYTES + 1)
    except OSError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="file_unreadable",
            translation_placeholders={"file": path, "error": str(err)},
        ) from err
    if len(data) > MAX_UPLOAD_BYTES:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="file_too_big",
            translation_placeholders={"file": path},
        )
    return file.name, data, mimetypes.guess_type(file.name)[0]


async def _forget_upload(coordinator: TodoistCoordinator, file_url: str) -> None:
    """Best effort: delete an upload whose comment failed."""
    try:
        await coordinator.client.delete_upload(file_url)
    except TodoistError as err:
        _LOGGER.warning("Could not remove unattached upload %s: %s", file_url, err)


async def _add_comment(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    coordinator = _coordinator(hass, call)
    if not call.data[ATTR_CONTENT].strip() and not call.data.get(ATTR_FILE):
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="empty_comment"
        )
    target: dict[str, str] = {}
    if ATTR_TASK in call.data:
        target["task_id"] = _task_id(coordinator, call.data[ATTR_TASK])
    else:
        ref = call.data[ATTR_PROJECT]
        project_id = find_project(coordinator.state, ref)
        if project_id is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="project_not_found",
                translation_placeholders={"project": ref},
            )
        target["project_id"] = project_id
    content: str = call.data[ATTR_CONTENT].strip()
    attachment: dict[str, Any] | None = None
    try:
        if path := call.data.get(ATTR_FILE):
            name, data, mime = await hass.async_add_executor_job(
                _read_file, hass, path
            )
            uploaded = await coordinator.client.upload(name, data, mime)
            attachment = {k: uploaded.get(k) for k in ATTACHMENT_FIELDS}
            content = content or name
        try:
            comment = await coordinator.client.add_comment(
                content, attachment=attachment, **target
            )
        except TodoistError:
            if attachment and attachment.get("file_url"):
                await _forget_upload(coordinator, attachment["file_url"])
            raise
    except TodoistError as err:
        raise HomeAssistantError(f"Todoist: {err}") from err
    await coordinator.async_request_refresh()
    return {"comment_id": str(comment.get("id")), "attachment": attachment}


async def _add_subtask(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    coordinator = _coordinator(hass, call)
    parent_id = _task_id(coordinator, call.data[ATTR_TASK])
    try:
        task = await coordinator.client.add_task(
            call.data[ATTR_CONTENT],
            parent_id=parent_id,
            description=call.data.get(ATTR_DESCRIPTION),
            due_string=call.data.get(ATTR_DUE_STRING),
        )
    except TodoistError as err:
        raise HomeAssistantError(f"Todoist: {err}") from err
    await coordinator.async_request_refresh()
    return {"task_id": str(task.get("id"))}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""

    async def add_comment(call: ServiceCall) -> ServiceResponse:
        return await _add_comment(hass, call)

    async def add_subtask(call: ServiceCall) -> ServiceResponse:
        return await _add_subtask(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_COMMENT,
        add_comment,
        schema=ADD_COMMENT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_SUBTASK,
        add_subtask,
        schema=ADD_SUBTASK_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
