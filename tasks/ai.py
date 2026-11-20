import re
from datetime import date, timedelta


def parse_task_text(text, today):
    """Parse plain text into validated task field values."""
    if not isinstance(text, str) or not text.strip():
        return {"title": "", "description": "", "due_date": None, "recurrence": None}

    normalized = text.strip()
    lower = normalized.lower()
    due_date = None
    recurrence = None

    if "tomorrow" in lower:
        due_date = (today + timedelta(days=1)).isoformat()
    else:
        month_match = re.search(r"\bon the\s+(\d{1,2})(?:st|nd|rd|th)?\b", lower)
        if month_match:
            day = int(month_match.group(1))
            try:
                due_date = date(today.year, today.month, day).isoformat()
            except ValueError:
                due_date = None

    if "every month" in lower or "monthly" in lower:
        recurrence = "monthly"
    elif "every week" in lower or "weekly" in lower:
        recurrence = "weekly"
    elif "every day" in lower or "daily" in lower:
        recurrence = "daily"

    title = re.sub(
        r"\b(remind me to|remember to|tomorrow|every month|monthly|on the "
        r"\d{1,2}(?:st|nd|rd|th)?|of every month|every week|weekly|every day|daily)\b",
        "",
        normalized,
        flags=re.I,
    )
    title = re.sub(r"\s+", " ", title).strip(" ,.-")

    return {
        "title": title[:100] or normalized[:100],
        "description": normalized,
        "due_date": due_date,
        "recurrence": recurrence,
    }


def break_down_task(task):
    """Split a task title by and/comma, or return a safe template."""
    text = task.title.strip()
    parts = re.split(r"\s+(?:and|&)\s+|,", text, flags=re.I)
    parts = [part.strip(" .") for part in parts if part.strip(" .")]
    if len(parts) > 1:
        return [
            {
                "title": part[:100],
                "description": f"Subtask for: {task.title}",
                "completed": False,
                "priority": task.priority,
                "due_date": None,
                "recurrence": "",
            }
            for part in parts
        ]
    return [
        {
            "title": f"{text[:85]} - plan",
            "description": f"Plan and prepare: {text}",
            "completed": False,
            "priority": task.priority,
            "due_date": None,
            "recurrence": "",
        },
        {
            "title": f"{text[:85]} - execute",
            "description": f"Complete: {text}",
            "completed": False,
            "priority": task.priority,
            "due_date": None,
            "recurrence": "",
        },
    ]
