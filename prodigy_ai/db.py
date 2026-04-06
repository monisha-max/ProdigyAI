"""
Direct PostgreSQL access for dashboard API endpoints.
These bypass the LLM for fast, reliable data loading.
The LLM/agents are only used for the chat endpoint.
"""

import os
import pg8000
import dotenv

dotenv.load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "prodigyai"),
    "user": os.getenv("DB_USER", "apple"),
    "password": os.getenv("DB_PASSWORD", "prodigyai123"),
}


def _conn():
    return pg8000.connect(**DB_CONFIG)


def _query(sql, params=None):
    """Execute a query and return list of dicts."""
    conn = _conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params or [])
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


def _execute(sql, params=None):
    """Execute a write query and return affected rows."""
    conn = _conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params or [])
        conn.commit()
        if cursor.description:
            cols = [desc[0] for desc in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
        return []
    finally:
        conn.close()


def _serialize(rows):
    """Convert date/time objects to strings for JSON serialization."""
    import datetime
    result = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if isinstance(v, (datetime.date, datetime.datetime)):
                clean[k] = v.isoformat()
            elif isinstance(v, datetime.time):
                clean[k] = v.strftime("%H:%M")
            elif isinstance(v, datetime.timedelta):
                total = int(v.total_seconds())
                clean[k] = f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
            else:
                clean[k] = v
        result.append(clean)
    return result


# ─── Task Queries ───

def get_tasks(status="all"):
    if status == "all":
        sql = """SELECT id, title, description, priority, due_date, status, project, created_at
                 FROM tasks ORDER BY
                 CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 WHEN 'low' THEN 4 END,
                 due_date ASC NULLS LAST"""
        return _serialize(_query(sql))
    else:
        sql = """SELECT id, title, description, priority, due_date, status, project, created_at
                 FROM tasks WHERE status = %s ORDER BY
                 CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 WHEN 'low' THEN 4 END,
                 due_date ASC NULLS LAST"""
        return _serialize(_query(sql, [status]))


def update_task(task_id, status=None, priority=None):
    updates = []
    params = []
    if status:
        updates.append("status = %s")
        params.append(status)
    if priority:
        updates.append("priority = %s")
        params.append(priority)
    if not updates:
        return []
    params.append(task_id)
    sql = f"UPDATE tasks SET {', '.join(updates)} WHERE id = %s RETURNING id, title, status, priority"
    return _serialize(_execute(sql, params))


# ─── Event Queries ───

def get_events_today():
    sql = """SELECT id, title, event_date, start_time, end_time, attendees, location, related_project
             FROM events WHERE event_date = CURRENT_DATE ORDER BY start_time ASC"""
    return _serialize(_query(sql))


def get_events_range(start_date, end_date):
    sql = """SELECT id, title, event_date, start_time, end_time, attendees, location, related_project
             FROM events WHERE event_date BETWEEN %s AND %s ORDER BY event_date, start_time"""
    return _serialize(_query(sql, [start_date, end_date]))


# ─── Notes Queries ───

def get_notes():
    sql = """SELECT id, title, content, tags, related_task_id, related_event_id, created_at
             FROM notes ORDER BY created_at DESC"""
    return _serialize(_query(sql))


# ─── Workload Query ───

def get_workload():
    sql = """SELECT
        d.day::date AS date,
        COALESCE(t.task_count, 0) AS tasks_due,
        COALESCE(e.event_count, 0) AS events_scheduled
    FROM generate_series(CURRENT_DATE, CURRENT_DATE + INTERVAL '6 days', '1 day') AS d(day)
    LEFT JOIN (
        SELECT due_date, COUNT(*) AS task_count FROM tasks WHERE status != 'done' GROUP BY due_date
    ) t ON t.due_date = d.day::date
    LEFT JOIN (
        SELECT event_date, COUNT(*) AS event_count FROM events GROUP BY event_date
    ) e ON e.event_date = d.day::date
    ORDER BY d.day"""
    return _serialize(_query(sql))


# ─── Simulation Queries ───

def simulate_day_off(target_date):
    """Get structured before/after data for the Time Machine visualization."""
    from datetime import datetime, timedelta

    target = datetime.strptime(target_date, "%Y-%m-%d").date()

    # Items on the target date
    affected_tasks = _serialize(_query(
        "SELECT id, title, priority, due_date, status FROM tasks WHERE due_date = %s AND status != 'done'",
        [target_date]
    ))
    affected_events = _serialize(_query(
        "SELECT id, title, event_date, start_time, end_time, attendees, location FROM events WHERE event_date = %s",
        [target_date]
    ))

    # Full week workload (Mon-Sun around target)
    week_start = target - timedelta(days=target.weekday())
    week_end = week_start + timedelta(days=6)
    workload_before = _serialize(_query("""
        SELECT d.day::date AS date,
            COALESCE(t.cnt, 0) AS tasks,
            COALESCE(e.cnt, 0) AS events
        FROM generate_series(%s::date, %s::date, '1 day') AS d(day)
        LEFT JOIN (SELECT due_date, COUNT(*) AS cnt FROM tasks WHERE status != 'done' GROUP BY due_date) t ON t.due_date = d.day::date
        LEFT JOIN (SELECT event_date, COUNT(*) AS cnt FROM events GROUP BY event_date) e ON e.event_date = d.day::date
        ORDER BY d.day
    """, [week_start.isoformat(), week_end.isoformat()]))

    # Compute "after" — remove items from target, add to neighbors
    workload_after = [dict(d) for d in workload_before]
    for d in workload_after:
        if d['date'] == target_date:
            d['tasks'] = 0
            d['events'] = 0

    next_wd = target + timedelta(days=1)
    while next_wd.weekday() >= 5:
        next_wd += timedelta(days=1)
    prev_wd = target - timedelta(days=1)
    while prev_wd.weekday() >= 5:
        prev_wd -= timedelta(days=1)

    moves = []
    for t in affected_tasks:
        is_high = t.get('priority') in ('urgent', 'high')
        dest = prev_wd.isoformat() if is_high else next_wd.isoformat()
        moves.append({'type': 'task', 'id': t['id'], 'title': t['title'], 'priority': t.get('priority', 'medium'), 'from_date': target_date, 'to_date': dest})
        for d in workload_after:
            if d['date'] == dest:
                d['tasks'] += 1

    for ev in affected_events:
        dest = next_wd.isoformat()
        moves.append({'type': 'event', 'id': ev['id'], 'title': ev['title'], 'priority': 'event', 'from_date': target_date, 'to_date': dest})
        for d in workload_after:
            if d['date'] == dest:
                d['events'] += 1

    return {
        'target_date': target_date,
        'affected_tasks': len(affected_tasks),
        'affected_events': len(affected_events),
        'total_affected': len(moves),
        'workload_before': workload_before,
        'workload_after': workload_after,
        'moves': moves,
    }
