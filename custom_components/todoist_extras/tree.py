"""Keep a local copy of the Todoist account and turn it into per-project trees.

Pure code (no Home Assistant imports) so it is easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import APP_PROJECT_URL, APP_TASK_URL

# Sync resource -> key of our local store.
_COLLECTIONS = {
    "projects": "projects",
    "sections": "sections",
    "items": "items",
    "notes": "notes",
    "project_notes": "project_notes",
}


@dataclass
class AccountState:
    """Everything the sync endpoint told us, keyed by id."""

    projects: dict[str, dict[str, Any]] = field(default_factory=dict)
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    items: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: dict[str, dict[str, Any]] = field(default_factory=dict)
    project_notes: dict[str, dict[str, Any]] = field(default_factory=dict)
    user: dict[str, Any] = field(default_factory=dict)

    def apply(self, payload: dict[str, Any]) -> None:
        """Merge one sync response (full or incremental) into the store."""
        if payload.get("full_sync"):
            for key in _COLLECTIONS.values():
                getattr(self, key).clear()
        if payload.get("user"):
            self.user = payload["user"]
        for resource, key in _COLLECTIONS.items():
            store: dict[str, dict[str, Any]] = getattr(self, key)
            for obj in payload.get(resource) or []:
                obj_id = str(obj["id"])
                if _gone(resource, obj):
                    store.pop(obj_id, None)
                else:
                    store[obj_id] = obj


def _gone(resource: str, obj: dict[str, Any]) -> bool:
    if obj.get("is_deleted"):
        return True
    if resource == "items" and obj.get("checked"):
        return True
    return resource == "projects" and bool(obj.get("is_archived"))


def _attachment(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None
    return {
        "file_name": raw.get("file_name"),
        "file_type": raw.get("file_type"),
        "file_url": raw.get("file_url"),
        "resource_type": raw.get("resource_type"),
        "is_audio": str(raw.get("file_type") or "").startswith("audio/")
        or raw.get("resource_type") == "audio",
    }


def _comment(note: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(note["id"]),
        "content": note.get("content") or "",
        "posted_at": note.get("posted_at"),
        "attachment": _attachment(note.get("file_attachment")),
    }


def _by_posted(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_comment(n) for n in sorted(notes, key=lambda n: n.get("posted_at") or "")]


def _order(item: dict[str, Any]) -> tuple[int, str]:
    return (item.get("child_order") or 0, str(item["id"]))


def _duration(raw: dict[str, Any] | None) -> str | None:
    if not raw:
        return None
    return f"{raw.get('amount')} {raw.get('unit')}"


@dataclass
class ProjectView:
    """One project as the sensor shows it."""

    id: str
    name: str
    url: str
    color: str | None
    tasks: list[dict[str, Any]]
    comments: list[dict[str, Any]]
    open_tasks: int
    open_subtasks: int
    comment_count: int


def build_projects(state: AccountState) -> dict[str, ProjectView]:
    """Nest open tasks -> subtasks -> comments for every active project."""
    notes_by_item: dict[str, list[dict[str, Any]]] = {}
    for note in state.notes.values():
        notes_by_item.setdefault(str(note.get("item_id")), []).append(note)
    notes_by_project: dict[str, list[dict[str, Any]]] = {}
    for note in state.project_notes.values():
        notes_by_project.setdefault(str(note.get("project_id")), []).append(note)
    children: dict[str | None, list[dict[str, Any]]] = {}
    for item in state.items.values():
        parent = item.get("parent_id")
        # A subtask whose parent is gone (completed/deleted) moves up a level.
        if parent is not None and str(parent) not in state.items:
            parent = None
        key = str(parent) if parent is not None else f"project:{item['project_id']}"
        children.setdefault(key, []).append(item)

    def task(item: dict[str, Any], counts: dict[str, int]) -> dict[str, Any]:
        item_id = str(item["id"])
        comments = _by_posted(notes_by_item.get(item_id, []))
        counts["comments"] += len(comments)
        due = item.get("due") or {}
        section = state.sections.get(str(item.get("section_id")))
        subtasks = []
        for child in sorted(children.get(item_id, []), key=_order):
            counts["subtasks"] += 1
            subtasks.append(task(child, counts))
        deadline = item.get("deadline") or {}
        return {
            "id": item_id,
            "content": item.get("content") or "",
            "description": item.get("description") or "",
            "due": due.get("date"),
            "due_string": due.get("string"),
            "is_recurring": bool(due.get("is_recurring")),
            "deadline": deadline.get("date"),
            "duration": _duration(item.get("duration")),
            # Todoist stores 4 for its "P1" (urgent); show it the way the app does.
            "priority": 5 - int(item.get("priority") or 1),
            "labels": list(item.get("labels") or []),
            "section": section.get("name") if section else None,
            "url": APP_TASK_URL.format(id=item_id),
            "comments": comments,
            "subtasks": subtasks,
        }

    views: dict[str, ProjectView] = {}
    for project in state.projects.values():
        project_id = str(project["id"])
        counts = {"subtasks": 0, "comments": 0}
        top = sorted(children.get(f"project:{project_id}", []), key=_order)
        tasks = [task(item, counts) for item in top]
        comments = _by_posted(notes_by_project.get(project_id, []))
        views[project_id] = ProjectView(
            id=project_id,
            name=project.get("name") or project_id,
            url=APP_PROJECT_URL.format(id=project_id),
            color=project.get("color"),
            tasks=tasks,
            comments=comments,
            open_tasks=len(tasks),
            open_subtasks=counts["subtasks"],
            comment_count=counts["comments"] + len(comments),
        )
    return views


def find_task(state: AccountState, ref: str) -> str | None:
    """Resolve a task id, or an exact (case-insensitive) unique task name."""
    ref = ref.strip()
    if ref in state.items:
        return ref
    matches = [
        item_id
        for item_id, item in state.items.items()
        if (item.get("content") or "").strip().casefold() == ref.casefold()
    ]
    return matches[0] if len(matches) == 1 else None


def find_project(state: AccountState, ref: str) -> str | None:
    """Resolve a project id or an exact (case-insensitive) project name."""
    ref = ref.strip()
    if ref in state.projects:
        return ref
    matches = [
        pid
        for pid, project in state.projects.items()
        if (project.get("name") or "").strip().casefold() == ref.casefold()
    ]
    return matches[0] if len(matches) == 1 else None
