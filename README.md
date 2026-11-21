# Todoist Extras for Home Assistant

The built-in [Todoist integration](https://www.home-assistant.io/integrations/todoist/)
gives you a to-do list and a calendar per project, but it leaves out **subtasks**,
**comments** and **attachments**, and only notices new projects after a reload.
This integration fills those gaps. It is meant to run *next to* the core one.

## What you get

**One sensor per project** (`sensor.todoist_<project>`), created automatically,
including for projects you add later.

- State: number of open top-level tasks.
- Attributes:
  - `tasks`: open tasks in Todoist order, each with `id`, `content`, `description`,
    `due`, `due_string`, `is_recurring`, `deadline`, `duration`, `priority`
    (1 = P1/urgent … 4 = no priority, as the app shows it), `labels`, `section`,
    `url`, `comments` and `subtasks` (same shape, nested to any depth).
  - Each comment: `id`, `content`, `posted_at`, `attachment`
    (`file_name`, `file_type`, `file_url`, `resource_type`, `is_audio`) or `null`.
  - `project_comments`, `open_subtasks`, `comment_count`, `project_id`, `url`, `color`.

Attributes are not written to the recorder database.

**Actions**

| Action | What it does |
|---|---|
| `todoist_extras.add_comment` | Comment on a task (`task`) or a project (`project`) with `content`, and/or a `file` to attach, such as an audio recording. Returns the comment id and attachment. |
| `todoist_extras.add_subtask` | Add a subtask under `task`, with optional `description` and `due_string` ("tomorrow 5pm"). Returns the new task id. |

`task` takes the id of an **open** task, or its exact name (when only one open
task has that name). Completed tasks can't be targeted. `project` takes an id or name. A `file` must be in a folder listed
in `allowlist_external_dirs` (for example `/media`).

## Setup

1. Copy `custom_components/todoist_extras` into your `config/custom_components`
   folder (or add this repository to HACS as a custom integration) and restart.
2. **Settings → Devices & services → Add integration → Todoist Extras**.
3. Paste your API token from Todoist: **Settings → Integrations → Developer**.

The integration polls Todoist's sync endpoint every minute and only fetches what
changed (with a full refresh every 30 minutes).

## Example: show a project tree in a Markdown card

```jinja
{% for t in state_attr('sensor.todoist_christmas_presents', 'tasks') %}
**{{ t.content }}**{% if t.due_string %} · {{ t.due_string }}{% endif %}
{% for s in t.subtasks %}- {{ s.content }}
{% endfor %}{% for c in t.comments %}> {{ c.content }}{% if c.attachment %} [{{ c.attachment.file_name }}]({{ c.attachment.file_url }}){% endif %}
{% endfor %}
{% endfor %}
```

## License

MIT
