# Task Manager REST API

A Django REST Framework API for creating and managing structured tasks, including subtasks, natural-language task creation, safe retries, filtering, search, ordering, and pagination.

## Features

- CRUD operations for tasks
- Consistent `error` response shape for validation and 404 errors
- Natural-language task creation with `parse_task_text(text, today)`
- Rule-based subtasks and task breakdown
- Cascade deletion of parent/subtask relationships
- Idempotent POST operations using `Idempotency-Key`
- Filtering, search, ordering, and pagination
- PostgreSQL through Docker

## Setup

From this directory:

```powershell
py -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt

docker compose up -d
python manage.py migrate
python manage.py runserver
```

The API runs at `http://127.0.0.1:8000/api/`. PostgreSQL is exposed on `localhost:5434`.

If an LLM wrapper is later added, set:

```powershell
$env:LLM_API_KEY="your-key"
python manage.py runserver
```

Never commit `.env` or API keys.

## Task fields

| Field | Type | Rules |
|---|---|---|
| `title` | string | Required and not blank |
| `description` | string | Required and not blank |
| `completed` | boolean | Must be `true` or `false` |
| `due_date` | string or null | `YYYY-MM-DD` |
| `priority` | string | `low`, `medium`, or `high` |
| `recurrence` | string | Optional |
| `parent` | integer or null | Read-only; set only through subtask endpoints |

## Endpoints

### List tasks

```http
GET /api/tasks/?completed=true&priority=high&search=rent&ordering=due_date&page=1
```

Example response:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "Pay rent",
      "description": "Pay rent",
      "completed": false,
      "due_date": "2026-12-01",
      "priority": "high",
      "recurrence": "monthly",
      "parent": null,
      "created_at": "2026-11-20T10:00:00Z",
      "updated_at": "2026-11-20T10:00:00Z"
    }
  ]
}
```

### Create task

```http
POST /api/tasks/
Content-Type: application/json
Idempotency-Key: create-rent-1
```

```json
{
  "title": "Pay rent",
  "description": "Pay rent on the first",
  "completed": false,
  "due_date": "2026-12-01",
  "priority": "high",
  "recurrence": "monthly"
}
```

### Retrieve, update, and delete

```http
GET /api/tasks/{id}/
PUT /api/tasks/{id}/
PATCH /api/tasks/{id}/
DELETE /api/tasks/{id}/
```

### Create from natural language

```http
POST /api/tasks/from-text/
Content-Type: application/json
Idempotency-Key: parser-rent-1
```

```json
{"text": "Remind me to pay rent on the 1st of every month"}
```

Example response:

```json
{
  "id": 1,
  "title": "pay rent",
  "description": "Remind me to pay rent on the 1st of every month",
  "completed": false,
  "due_date": null,
  "priority": "medium",
  "recurrence": "monthly",
  "parent": null
}
```

### Subtasks

```http
POST /api/tasks/{id}/subtasks/
GET /api/tasks/{id}/subtasks/
```

POST body:

```json
{
  "title": "Check rent payment",
  "description": "Verify payment and receipt",
  "completed": false,
  "priority": "medium"
}
```

### Breakdown

```http
POST /api/tasks/{id}/breakdown/
Idempotency-Key: breakdown-1
```

The response is a list of newly created subtasks. Parent tasks containing `and` or commas are split; otherwise plan and execute templates are generated.

## Validation error

Every 400/404 response uses this shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed",
    "details": [
      {"field": "title", "issue": "must not be empty"}
    ]
  }
}
```

422 idempotency conflicts and 502 parser/invalid parser output use the same shape.

## Idempotency

Send `Idempotency-Key` on task creation, text parsing, and breakdown. Reusing the key with the same JSON body returns the stored successful response. Reusing it with another body returns 422. Only successful responses are stored.

## Parser signature

```python
parse_task_text(text: str, today: datetime.date) -> dict
```

The function returns `title`, `description`, `due_date`, and optional `recurrence`. It can be replaced by an LLM wrapper while preserving the signature and the validation step.

## Testing

```powershell
python manage.py test tasks
```

The AI-generated checklist was initially missing impossible dates, subtask-of-subtask rules, repeated keys with changed bodies, parser exceptions/bad parser output, unknown IDs, and cascade deletion. The test suite now includes these cases.
