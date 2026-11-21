"""The local account copy and the per-project trees."""

from __future__ import annotations

from custom_components.todoist_extras.tree import (
    AccountState,
    build_projects,
    find_project,
    find_task,
)

from .conftest import FAITH, INBOX, JANNA, LUCA, LUCA_SUB, XMAS, full_sync


def _state() -> AccountState:
    state = AccountState()
    state.apply(full_sync())
    return state


def test_tree_nests_subtasks_and_comments() -> None:
    views = build_projects(_state())
    xmas = views[XMAS]
    assert xmas.name == "Christmas Presents"
    assert [t["content"] for t in xmas.tasks] == ["Luca", "Janna", "Faith"]
    assert xmas.open_tasks == 3
    assert xmas.open_subtasks == 1
    assert xmas.comment_count == 4  # 2 on Luca, 1 on the subtask, 1 on the project

    luca = xmas.tasks[0]
    assert luca["description"] == "overwrite existing description ?"
    # Comments come oldest first.
    assert [c["content"] for c in luca["comments"]] == ["Size 14", "voice note"]
    assert luca["comments"][0]["attachment"] is None
    audio = luca["comments"][1]["attachment"]
    assert audio["is_audio"] is True
    assert audio["file_url"] == "https://files.todoist.com/note.m4a"
    assert luca["subtasks"][0]["id"] == LUCA_SUB
    assert luca["subtasks"][0]["comments"][0]["content"] == "from Argos"
    assert luca["url"] == f"https://app.todoist.com/app/task/{LUCA}"

    assert xmas.comments[0]["content"] == "Budget £50 each"


def test_task_fields() -> None:
    janna = build_projects(_state())[XMAS].tasks[1]
    assert janna["id"] == JANNA
    assert janna["due"] == "2026-11-28T14:00:00"
    assert janna["due_string"] == "28 Nov 14:00"
    assert janna["deadline"] == "2026-12-20"
    assert janna["duration"] == "30 minute"
    assert janna["priority"] == 1  # API 4 = the app's P1
    assert janna["labels"] == ["family"]
    assert janna["subtasks"] == []
    faith = build_projects(_state())[XMAS].tasks[2]
    assert faith["priority"] == 4
    assert faith["due"] is None


def test_incremental_sync_updates_and_removes() -> None:
    state = _state()
    state.apply(
        {
            "full_sync": False,
            "items": [
                {**full_sync()["items"][1], "content": "Luca (done soon)"},
                {"id": FAITH, "checked": True, "project_id": XMAS},
            ],
            "notes": [{"id": "n1", "is_deleted": True}],
            "projects": [],
        }
    )
    xmas = build_projects(state)[XMAS]
    assert [t["content"] for t in xmas.tasks] == ["Luca (done soon)", "Janna"]
    assert [c["content"] for c in xmas.tasks[0]["comments"]] == ["voice note"]
    # Untouched data is kept.
    assert INBOX in build_projects(state)


def test_completed_parent_moves_subtask_up() -> None:
    state = _state()
    state.apply({"full_sync": False, "items": [{"id": LUCA, "checked": True}]})
    xmas = build_projects(state)[XMAS]
    assert [t["content"] for t in xmas.tasks][0] == "Luca - subtask"


def test_archived_project_and_full_sync_reset() -> None:
    state = _state()
    state.apply({"full_sync": False, "projects": [{"id": XMAS, "is_archived": True}]})
    assert XMAS not in build_projects(state)
    state.apply({"full_sync": True, "projects": [], "items": []})
    assert build_projects(state) == {}
    assert not state.items and not state.notes and not state.project_notes
    assert not state.parents  # links of tasks no longer listed are dropped
    # A project that comes back brings none of the old tasks with it.
    state.apply({"full_sync": False, "projects": [{"id": XMAS, "name": "Christmas Presents"}]})
    assert build_projects(state)[XMAS].tasks == []


def test_sections_are_named() -> None:
    payload = full_sync()
    payload["sections"] = [{"id": "s1", "name": "Kids", "project_id": XMAS}]
    payload["items"][1]["section_id"] = "s1"
    state = AccountState()
    state.apply(payload)
    assert build_projects(state)[XMAS].tasks[0]["section"] == "Kids"


def test_find_task_and_project() -> None:
    state = _state()
    assert find_task(state, LUCA) == LUCA
    assert find_task(state, " janna ") == JANNA
    assert find_task(state, "nobody") is None
    assert find_project(state, "christmas presents") == XMAS
    assert find_project(state, INBOX) == INBOX
    assert find_project(state, "Work") is None


def test_find_task_ambiguous_name() -> None:
    payload = full_sync()
    payload["items"].append({**payload["items"][1], "id": "dup"})
    state = AccountState()
    state.apply(payload)
    assert find_task(state, "Luca") is None


def test_orphan_moves_to_nearest_open_ancestor() -> None:
    payload = full_sync()
    # Luca > Luca - subtask > grandchild
    payload["items"].append(
        {**payload["items"][2], "id": "gc", "content": "grandchild", "parent_id": LUCA_SUB}
    )
    state = AccountState()
    state.apply(payload)
    state.apply({"full_sync": False, "items": [{"id": LUCA_SUB, "parent_id": LUCA, "is_deleted": True}]})
    luca = build_projects(state)[XMAS].tasks[0]
    assert [s["content"] for s in luca["subtasks"]] == ["grandchild"]


def test_parent_loop_does_not_hang() -> None:
    state = _state()
    state.parents.update({"a": "b", "b": "a"})
    state.items["x"] = {**full_sync()["items"][4], "id": "x", "parent_id": "a"}
    assert any(t["id"] == "x" for t in build_projects(state)[XMAS].tasks)


def test_cycle_between_open_tasks_keeps_both() -> None:
    payload = full_sync()
    payload["items"][3]["parent_id"] = FAITH  # Janna under Faith
    payload["items"][4]["parent_id"] = JANNA  # Faith under Janna
    state = AccountState()
    state.apply(payload)
    xmas = build_projects(state)[XMAS]
    names = [t["content"] for t in xmas.tasks]
    assert "Luca" in names
    shown = names + [s["content"] for t in xmas.tasks for s in t["subtasks"]]
    assert "Janna" in shown and "Faith" in shown
