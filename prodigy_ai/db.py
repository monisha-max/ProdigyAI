"""
Direct PostgreSQL access for dashboard API endpoints.
These bypass the LLM for fast, reliable data loading.
The LLM/agents are only used for the chat endpoint.
"""

import os
import pg8000
import dotenv

dotenv.load_dotenv()

_google_tables_ready = False

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


def _ensure_google_tables():
    global _google_tables_ready
    if _google_tables_ready:
        return
    conn = _conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS google_accounts (
                account_email VARCHAR(255) PRIMARY KEY,
                display_name VARCHAR(255),
                provider VARCHAR(50) DEFAULT 'google',
                status VARCHAR(30) DEFAULT 'connected',
                last_synced_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS google_calendar_cache (
                event_id VARCHAR(255) PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                event_date DATE,
                start_time TIME,
                end_time TIME,
                attendees TEXT,
                location TEXT,
                summary TEXT,
                source VARCHAR(30) DEFAULT 'google',
                last_synced_at TIMESTAMP DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS google_tasks_cache (
                task_id VARCHAR(255) PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                notes TEXT,
                due_date DATE,
                status VARCHAR(20) DEFAULT 'todo',
                priority VARCHAR(20) DEFAULT 'medium',
                thread_id VARCHAR(255),
                source VARCHAR(30) DEFAULT 'google',
                last_synced_at TIMESTAMP DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS gmail_threads_cache (
                thread_id VARCHAR(255) PRIMARY KEY,
                subject VARCHAR(255) NOT NULL,
                snippet TEXT,
                summary TEXT,
                sender VARCHAR(255),
                unread_count INTEGER DEFAULT 0,
                message_count INTEGER DEFAULT 1,
                received_at TIMESTAMP,
                source VARCHAR(30) DEFAULT 'google',
                last_synced_at TIMESTAMP DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS google_drive_cache (
                file_id VARCHAR(500) PRIMARY KEY,
                name VARCHAR(500) NOT NULL,
                mime_type VARCHAR(255),
                web_view_link TEXT,
                modified_time TIMESTAMP,
                owner VARCHAR(255),
                size VARCHAR(50),
                source VARCHAR(30) DEFAULT 'google',
                last_synced_at TIMESTAMP DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS google_docs_cache (
                doc_id VARCHAR(500) PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                web_view_link TEXT,
                modified_time TIMESTAMP,
                source VARCHAR(30) DEFAULT 'google',
                last_synced_at TIMESTAMP DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS google_sync_state (
                sync_key VARCHAR(50) PRIMARY KEY,
                status VARCHAR(30) DEFAULT 'idle',
                last_synced_at TIMESTAMP,
                last_error TEXT,
                updated_at TIMESTAMP DEFAULT NOW()
            )
            """
        )
        conn.commit()
        _google_tables_ready = True
    finally:
        conn.close()


def _upsert_many(sql, rows):
    if not rows:
        return
    conn = _conn()
    try:
        cursor = conn.cursor()
        for row in rows:
            cursor.execute(sql, row)
        conn.commit()
    finally:
        conn.close()


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


def cache_google_calendar_events(events):
    _ensure_google_tables()
    rows = [
        [
            event.get("id"),
            event.get("title"),
            event.get("event_date"),
            event.get("start_time"),
            event.get("end_time"),
            event.get("attendees"),
            event.get("location"),
            event.get("summary"),
            event.get("source", "google"),
        ]
        for event in events
        if event.get("id")
    ]
    _upsert_many(
        """
        INSERT INTO google_calendar_cache (
            event_id, title, event_date, start_time, end_time, attendees, location, summary, source, last_synced_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (event_id) DO UPDATE SET
            title = EXCLUDED.title,
            event_date = EXCLUDED.event_date,
            start_time = EXCLUDED.start_time,
            end_time = EXCLUDED.end_time,
            attendees = EXCLUDED.attendees,
            location = EXCLUDED.location,
            summary = EXCLUDED.summary,
            source = EXCLUDED.source,
            last_synced_at = NOW()
        """,
        rows,
    )


def cache_google_tasks(tasks):
    _ensure_google_tables()
    _execute("DELETE FROM google_tasks_cache")
    rows = [
        [
            task.get("id"),
            task.get("title"),
            task.get("notes"),
            task.get("due_date"),
            task.get("status", "todo"),
            task.get("priority", "medium"),
            task.get("thread_id"),
            task.get("source", "google"),
        ]
        for task in tasks
        if task.get("id")
    ]
    _upsert_many(
        """
        INSERT INTO google_tasks_cache (
            task_id, title, notes, due_date, status, priority, thread_id, source, last_synced_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (task_id) DO UPDATE SET
            title = EXCLUDED.title,
            notes = EXCLUDED.notes,
            due_date = EXCLUDED.due_date,
            status = EXCLUDED.status,
            priority = EXCLUDED.priority,
            thread_id = EXCLUDED.thread_id,
            source = EXCLUDED.source,
            last_synced_at = NOW()
        """,
        rows,
    )


def cache_gmail_threads(threads):
    _ensure_google_tables()
    rows = [
        [
            thread.get("id"),
            thread.get("subject"),
            thread.get("snippet"),
            thread.get("summary"),
            thread.get("sender"),
            thread.get("unread_count", 0),
            thread.get("message_count", 1),
            thread.get("received_at"),
            thread.get("source", "google"),
        ]
        for thread in threads
        if thread.get("id")
    ]
    _upsert_many(
        """
        INSERT INTO gmail_threads_cache (
            thread_id, subject, snippet, summary, sender, unread_count, message_count, received_at, source, last_synced_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (thread_id) DO UPDATE SET
            subject = EXCLUDED.subject,
            snippet = EXCLUDED.snippet,
            summary = EXCLUDED.summary,
            sender = EXCLUDED.sender,
            unread_count = EXCLUDED.unread_count,
            message_count = EXCLUDED.message_count,
            received_at = EXCLUDED.received_at,
            source = EXCLUDED.source,
            last_synced_at = NOW()
        """,
        rows,
    )


def record_google_sync(sync_key, status="idle", error=None):
    _ensure_google_tables()
    _execute(
        """
        INSERT INTO google_sync_state (sync_key, status, last_synced_at, last_error, updated_at)
        VALUES (%s, %s, CASE WHEN %s = 'connected' THEN NOW() ELSE NULL END, %s, NOW())
        ON CONFLICT (sync_key) DO UPDATE SET
            status = EXCLUDED.status,
            last_synced_at = CASE WHEN EXCLUDED.status = 'connected' THEN NOW() ELSE google_sync_state.last_synced_at END,
            last_error = EXCLUDED.last_error,
            updated_at = NOW()
        """,
        [sync_key, status, status, error],
    )


def get_google_calendar_today():
    _ensure_google_tables()
    rows = _query(
        """
        SELECT
            event_id AS id,
            title,
            event_date,
            start_time,
            end_time,
            attendees,
            location,
            summary,
            source,
            last_synced_at
        FROM google_calendar_cache
        WHERE event_date = CURRENT_DATE
        ORDER BY start_time ASC NULLS LAST, title ASC
        """
    )
    return _serialize(rows)


def get_google_calendar_range(start_date, end_date):
    _ensure_google_tables()
    rows = _query(
        """
        SELECT
            event_id AS id,
            title,
            event_date,
            start_time,
            end_time,
            attendees,
            location,
            summary,
            source,
            last_synced_at
        FROM google_calendar_cache
        WHERE event_date BETWEEN %s AND %s
        ORDER BY event_date ASC, start_time ASC NULLS LAST, title ASC
        """,
        [start_date, end_date],
    )
    return _serialize(rows)


def get_google_tasks():
    _ensure_google_tables()
    rows = _query(
        """
        SELECT
            task_id AS id,
            title,
            notes,
            due_date,
            status,
            priority,
            thread_id,
            source,
            last_synced_at
        FROM google_tasks_cache
        ORDER BY
            CASE status WHEN 'todo' THEN 1 WHEN 'in_progress' THEN 2 WHEN 'done' THEN 3 ELSE 4 END,
            due_date ASC NULLS LAST,
            title ASC
        """
    )
    return _serialize(rows)


def mark_google_task_complete(task_id):
    _ensure_google_tables()
    return _serialize(
        _execute(
            """
            UPDATE google_tasks_cache
            SET status = 'done', last_synced_at = NOW()
            WHERE task_id = %s
            RETURNING task_id AS id, title, notes, due_date, status, priority, thread_id, source
            """,
            [task_id],
        )
    )


def cache_google_drive_files(files):
    _ensure_google_tables()
    if not files:
        return
    rows = [
        [
            f.get("id"),
            f.get("name"),
            f.get("mime_type"),
            f.get("web_view_link"),
            f.get("modified_time"),
            f.get("owner"),
            f.get("size"),
            f.get("source", "google"),
        ]
        for f in files
        if f.get("id") and f.get("name")
    ]
    _upsert_many(
        """
        INSERT INTO google_drive_cache (
            file_id, name, mime_type, web_view_link, modified_time, owner, size, source, last_synced_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (file_id) DO UPDATE SET
            name = EXCLUDED.name,
            mime_type = EXCLUDED.mime_type,
            web_view_link = EXCLUDED.web_view_link,
            modified_time = EXCLUDED.modified_time,
            owner = EXCLUDED.owner,
            size = EXCLUDED.size,
            source = EXCLUDED.source,
            last_synced_at = NOW()
        """,
        rows,
    )


def get_google_drive_files(limit: int = 20):
    _ensure_google_tables()
    rows = _query(
        """
        SELECT
            file_id AS id,
            name,
            mime_type,
            web_view_link,
            modified_time,
            owner,
            size,
            source,
            last_synced_at
        FROM google_drive_cache
        ORDER BY modified_time DESC NULLS LAST, name ASC
        LIMIT %s
        """,
        [limit],
    )
    return _serialize(rows)


def search_google_drive_files_cache(query: str):
    _ensure_google_tables()
    rows = _query(
        """
        SELECT
            file_id AS id,
            name,
            mime_type,
            web_view_link,
            modified_time,
            owner,
            size,
            source,
            last_synced_at
        FROM google_drive_cache
        WHERE name ILIKE %s
        ORDER BY modified_time DESC NULLS LAST
        LIMIT 20
        """,
        [f"%{query}%"],
    )
    return _serialize(rows)


def cache_google_docs(docs):
    _ensure_google_tables()
    if not docs:
        return
    rows = [
        [
            d.get("id"),
            d.get("title") or d.get("name"),
            d.get("web_view_link"),
            d.get("modified_time"),
            d.get("source", "google"),
        ]
        for d in docs
        if d.get("id") and (d.get("title") or d.get("name"))
    ]
    _upsert_many(
        """
        INSERT INTO google_docs_cache (
            doc_id, title, web_view_link, modified_time, source, last_synced_at
        )
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (doc_id) DO UPDATE SET
            title = EXCLUDED.title,
            web_view_link = EXCLUDED.web_view_link,
            modified_time = EXCLUDED.modified_time,
            source = EXCLUDED.source,
            last_synced_at = NOW()
        """,
        rows,
    )


def get_google_docs(limit: int = 20):
    _ensure_google_tables()
    rows = _query(
        """
        SELECT
            doc_id AS id,
            title,
            web_view_link,
            modified_time,
            source,
            last_synced_at
        FROM google_docs_cache
        ORDER BY modified_time DESC NULLS LAST, title ASC
        LIMIT %s
        """,
        [limit],
    )
    return _serialize(rows)


def search_google_docs_cache(query: str):
    _ensure_google_tables()
    rows = _query(
        """
        SELECT
            doc_id AS id,
            title,
            web_view_link,
            modified_time,
            source,
            last_synced_at
        FROM google_docs_cache
        WHERE title ILIKE %s
        ORDER BY modified_time DESC NULLS LAST
        LIMIT 20
        """,
        [f"%{query}%"],
    )
    return _serialize(rows)


def get_gmail_summary():
    _ensure_google_tables()
    rows = _serialize(
        _query(
            """
            SELECT
                thread_id AS id,
                subject,
                snippet,
                summary,
                sender,
                unread_count,
                message_count,
                received_at,
                source,
                last_synced_at
            FROM gmail_threads_cache
            ORDER BY unread_count DESC, received_at DESC NULLS LAST
            LIMIT 5
            """
        )
    )
    unread_count = sum(int(row.get("unread_count") or 0) for row in rows)
    sync_state = _serialize(
        _query(
            """
            SELECT sync_key, status, last_synced_at, last_error
            FROM google_sync_state
            WHERE sync_key = 'workspace'
            """
        )
    )
    status = sync_state[0] if sync_state else {"status": "idle", "last_error": None, "last_synced_at": None}
    return {"threads": rows, "unread_count": unread_count, "status": status}
