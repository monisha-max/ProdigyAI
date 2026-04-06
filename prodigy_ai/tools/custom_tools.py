"""
Custom Python Tools — ADK FunctionTools
These are pure Python tools that don't need MCP. They provide utility functions
that complement the MCP-based tools for scheduling logic, email drafts, and reports.
"""

from datetime import datetime, timedelta, time
from typing import Optional


def calculate_free_slots(
    date: str,
    events_json: str,
    min_duration_minutes: int = 30,
) -> dict:
    """Calculate available free time slots on a given date, based on existing events.
    Use this AFTER fetching events for a date to find open windows for scheduling.

    Args:
        date: The date to analyze in YYYY-MM-DD format.
        events_json: JSON string of events array with start_time and end_time fields (HH:MM format).
        min_duration_minutes: Minimum slot duration to consider (default 30 minutes).

    Returns:
        A dict with the date and a list of free slot objects with start, end, and duration_minutes.
    """
    import json

    work_start = time(8, 0)  # 8 AM
    work_end = time(18, 0)  # 6 PM

    try:
        events = json.loads(events_json) if isinstance(events_json, str) else events_json
    except (json.JSONDecodeError, TypeError):
        events = []

    # Parse and sort events by start time
    busy = []
    for e in events:
        if e.get("start_time") and e.get("end_time"):
            try:
                st = datetime.strptime(e["start_time"][:5], "%H:%M").time()
                et = datetime.strptime(e["end_time"][:5], "%H:%M").time()
                busy.append((st, et))
            except ValueError:
                continue
    busy.sort()

    # Find gaps
    free_slots = []
    current = work_start

    for start, end in busy:
        if start > current:
            gap_minutes = (
                datetime.combine(datetime.min, start) - datetime.combine(datetime.min, current)
            ).seconds // 60
            if gap_minutes >= min_duration_minutes:
                free_slots.append({
                    "start": current.strftime("%H:%M"),
                    "end": start.strftime("%H:%M"),
                    "duration_minutes": gap_minutes,
                })
        if end > current:
            current = end

    # After last event
    if current < work_end:
        gap_minutes = (
            datetime.combine(datetime.min, work_end) - datetime.combine(datetime.min, current)
        ).seconds // 60
        if gap_minutes >= min_duration_minutes:
            free_slots.append({
                "start": current.strftime("%H:%M"),
                "end": work_end.strftime("%H:%M"),
                "duration_minutes": gap_minutes,
            })

    return {
        "date": date,
        "work_hours": f"{work_start.strftime('%H:%M')} - {work_end.strftime('%H:%M')}",
        "free_slots": free_slots,
        "total_free_minutes": sum(s["duration_minutes"] for s in free_slots),
        "busiest_period": f"{busy[0][0].strftime('%H:%M')}-{busy[-1][1].strftime('%H:%M')}" if busy else "No events",
    }


def smart_reschedule(
    impacted_items_json: str,
    blocked_date: str,
) -> dict:
    """Suggest optimal rescheduling when a day is blocked (e.g., taking a day off).
    Takes the output from simulate_day_off (or any list of tasks/events) and generates
    a rescue plan with new suggested dates.

    Args:
        impacted_items_json: JSON string — either an array of items from simulate_day_off
            (each having type, id, title, detail, date_info fields) OR separate task/event arrays.
        blocked_date: The date being blocked in YYYY-MM-DD format.

    Returns:
        A dict with rescheduling suggestions for each impacted task and event.
    """
    import json

    items = []
    try:
        parsed = json.loads(impacted_items_json) if isinstance(impacted_items_json, str) else impacted_items_json
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            # Handle various formats
            items = parsed.get("items", parsed.get("results", [parsed]))
    except (json.JSONDecodeError, TypeError):
        items = []

    try:
        blocked = datetime.strptime(blocked_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        blocked = datetime.now().date()

    suggestions = []
    tasks_count = 0
    events_count = 0

    for item in items:
        item_type = item.get("type", "task")
        title = item.get("title", "Unknown item")
        detail = item.get("detail", item.get("priority", ""))
        item_id = item.get("id")

        if item_type == "task":
            tasks_count += 1
            is_high = detail.lower() in ("urgent", "high") if detail else False
            if is_high:
                new_date = blocked - timedelta(days=1)
                reason = "High priority — moved to day before to avoid risk"
            else:
                new_date = blocked + timedelta(days=1)
                reason = "Moved to next day — safe to shift"
            # Skip weekends
            while new_date.weekday() >= 5:
                new_date += timedelta(days=1) if new_date > blocked else timedelta(days=-1)
        else:
            events_count += 1
            new_date = blocked + timedelta(days=1)
            while new_date.weekday() >= 5:
                new_date += timedelta(days=1)
            reason = "Event moved to next available weekday"

        suggestions.append({
            "type": item_type,
            "id": item_id,
            "title": title,
            "original_date": blocked_date,
            "suggested_date": new_date.isoformat(),
            "reason": reason,
        })

    return {
        "blocked_date": blocked_date,
        "total_impacted": len(suggestions),
        "tasks_impacted": tasks_count,
        "events_impacted": events_count,
        "suggestions": suggestions,
        "summary": f"{'⚠️ ' if len(suggestions) > 3 else ''}{len(suggestions)} items affected. {tasks_count} tasks and {events_count} events need rescheduling." if suggestions else "No items affected — you're clear to take the day off!",
    }


def send_email_draft(
    to: str,
    subject: str,
    context: str,
    tone: str = "professional",
) -> dict:
    """Generate a professional email draft based on context. Does NOT actually send —
    returns the draft for user review.

    Args:
        to: Recipient name or email address.
        subject: Email subject line.
        context: What the email is about — meeting invite, follow-up, status update, etc.
        tone: Tone of the email: professional, casual, or urgent.

    Returns:
        A dict with the complete email draft ready for review.
    """
    tone_openers = {
        "professional": f"Dear {to},\n\nI hope this message finds you well.",
        "casual": f"Hey {to}!\n\nHope you're doing great.",
        "urgent": f"Hi {to},\n\nI'm reaching out regarding an urgent matter.",
    }

    opener = tone_openers.get(tone, tone_openers["professional"])

    draft = {
        "to": to,
        "subject": subject,
        "tone": tone,
        "body": f"{opener}\n\n{context}\n\nPlease let me know if you have any questions or need further details.\n\nBest regards",
        "status": "draft — review before sending",
        "note": "This is an AI-generated draft. Please review and personalize before sending.",
    }

    return draft


def generate_report_summary(
    title: str,
    period: str,
    tasks_completed: int,
    tasks_pending: int,
    tasks_overdue: int,
    events_attended: int,
    notes_created: int,
    top_projects: str,
    insights: str,
) -> dict:
    """Generate a structured productivity report summary with key metrics and insights.

    Args:
        title: Report title (e.g., "Weekly Productivity Report").
        period: Time period covered (e.g., "March 28 - April 3, 2026").
        tasks_completed: Number of tasks completed in the period.
        tasks_pending: Number of tasks still pending.
        tasks_overdue: Number of overdue tasks.
        events_attended: Number of events/meetings in the period.
        notes_created: Number of notes created.
        top_projects: Comma-separated list of most active projects.
        insights: AI-generated insights about productivity patterns.

    Returns:
        A dict with the structured report data and formatted markdown content.
    """
    completion_rate = (
        round(tasks_completed / max(tasks_completed + tasks_pending + tasks_overdue, 1) * 100)
    )

    health = "Excellent" if completion_rate >= 80 else "Good" if completion_rate >= 60 else "Needs Attention"

    report = {
        "title": title,
        "period": period,
        "generated_at": datetime.now().isoformat(),
        "metrics": {
            "tasks_completed": tasks_completed,
            "tasks_pending": tasks_pending,
            "tasks_overdue": tasks_overdue,
            "completion_rate": f"{completion_rate}%",
            "events_attended": events_attended,
            "notes_created": notes_created,
            "productivity_health": health,
        },
        "top_projects": [p.strip() for p in top_projects.split(",")],
        "insights": insights,
        "markdown": f"""# {title}
**Period:** {period}
**Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

---

## Productivity Score: {completion_rate}% ({health})

### Key Metrics
| Metric | Value |
|--------|-------|
| Tasks Completed | {tasks_completed} |
| Tasks Pending | {tasks_pending} |
| Tasks Overdue | {tasks_overdue} |
| Events Attended | {events_attended} |
| Notes Created | {notes_created} |

### Active Projects
{chr(10).join(f'- {p.strip()}' for p in top_projects.split(','))}

### AI Insights
{insights}
""",
    }

    return report
