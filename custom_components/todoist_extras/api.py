"""Small async client for the Todoist API v1 (sync, uploads, comments, tasks)."""

from __future__ import annotations

import json
from typing import Any

import aiohttp

from .const import API_BASE, RESOURCE_TYPES

TIMEOUT = aiohttp.ClientTimeout(total=60)


class TodoistError(Exception):
    """Todoist could not be reached or returned an error."""


class TodoistAuthError(TodoistError):
    """The API token was rejected."""


class TodoistClient:
    """Talks to api.todoist.com with a personal API token."""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        """Keep the session and token."""
        self._session = session
        self._token = token

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with self._session.request(
                method,
                f"{API_BASE}/{path}",
                headers=self._headers,
                timeout=TIMEOUT,
                **kwargs,
            ) as resp:
                # Todoist answers 401 for a bad token; 403 means "not allowed"
                # (or no token at all) and must not start a reauth.
                if resp.status == 401:
                    raise TodoistAuthError("Todoist rejected the token (401)")
                if resp.status >= 400:
                    body = (await resp.text())[:300]
                    raise TodoistError(f"Todoist {path} returned {resp.status}: {body}")
                if resp.status == 204:
                    return None
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise TodoistError(f"Cannot reach Todoist: {err}") from err
        except ValueError as err:  # a 2xx whose body is not JSON
            raise TodoistError(f"Todoist {path} sent an unreadable reply: {err}") from err

    async def sync(
        self, sync_token: str = "*", resource_types: list[str] | None = None
    ) -> dict[str, Any]:
        """Read everything ("*") or what changed since sync_token."""
        return await self._request(
            "POST",
            "sync",
            data={
                "sync_token": sync_token,
                "resource_types": json.dumps(resource_types or RESOURCE_TYPES),
            },
        )

    async def delete_upload(self, file_url: str) -> None:
        """Remove an uploaded file that never got attached to a comment."""
        await self._request("DELETE", "uploads", params={"file_url": file_url})

    async def upload(
        self, file_name: str, content: bytes, content_type: str | None
    ) -> dict[str, Any]:
        """Upload a file; the result is the attachment for a new comment."""
        form = aiohttp.FormData()
        form.add_field("file_name", file_name)
        form.add_field(
            "file",
            content,
            filename=file_name,
            content_type=content_type or "application/octet-stream",
        )
        return await self._request("POST", "uploads", data=form)

    async def add_comment(
        self,
        content: str,
        *,
        task_id: str | None = None,
        project_id: str | None = None,
        attachment: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Comment on a task or a project, optionally with an uploaded file."""
        body: dict[str, Any] = {"content": content}
        if task_id:
            body["task_id"] = task_id
        if project_id:
            body["project_id"] = project_id
        if attachment:
            body["attachment"] = attachment
        return await self._request("POST", "comments", json=body)

    async def add_task(self, content: str, **fields: Any) -> dict[str, Any]:
        """Create a task (with parent_id it becomes a subtask)."""
        body = {"content": content, **{k: v for k, v in fields.items() if v}}
        return await self._request("POST", "tasks", json=body)
