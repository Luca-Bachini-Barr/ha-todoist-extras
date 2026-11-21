"""Constants for Todoist Extras."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "todoist_extras"
PLATFORMS: list[Platform] = [Platform.SENSOR]

API_BASE = "https://api.todoist.com/api/v1"
APP_TASK_URL = "https://app.todoist.com/app/task/{id}"
APP_PROJECT_URL = "https://app.todoist.com/app/project/{id}"

SCAN_INTERVAL = timedelta(minutes=1)
# Every so often start again from a full sync, so a missed change can't stick.
FULL_SYNC_INTERVAL = timedelta(minutes=30)

RESOURCE_TYPES = ["user", "projects", "sections", "items", "notes", "project_notes"]

ATTR_TASK = "task"
ATTR_PROJECT = "project"
ATTR_CONTENT = "content"
ATTR_FILE = "file"
ATTR_DESCRIPTION = "description"
ATTR_DUE_STRING = "due_string"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"

SERVICE_ADD_COMMENT = "add_comment"
SERVICE_ADD_SUBTASK = "add_subtask"

# Todoist's own upload limit is per plan; refuse anything larger up front.
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
