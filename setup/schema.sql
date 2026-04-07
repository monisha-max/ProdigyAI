-- ProdigyAI Database Schema

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    deadline DATE,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'on_hold')),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    priority VARCHAR(20) DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    due_date DATE,
    status VARCHAR(20) DEFAULT 'todo' CHECK (status IN ('todo', 'in_progress', 'done')),
    project VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    event_date DATE NOT NULL,
    start_time TIME,
    end_time TIME,
    attendees TEXT,
    location TEXT,
    related_project VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notes (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    tags VARCHAR(255),
    related_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    related_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);
CREATE INDEX IF NOT EXISTS idx_notes_tags ON notes(tags);

CREATE TABLE IF NOT EXISTS google_accounts (
    account_email VARCHAR(255) PRIMARY KEY,
    display_name VARCHAR(255),
    provider VARCHAR(50) DEFAULT 'google',
    status VARCHAR(30) DEFAULT 'connected',
    last_synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

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
);

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
);

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
);

CREATE TABLE IF NOT EXISTS google_sync_state (
    sync_key VARCHAR(50) PRIMARY KEY,
    status VARCHAR(30) DEFAULT 'idle',
    last_synced_at TIMESTAMP,
    last_error TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- No demo seed data is inserted by default. The UI is intended to reflect live
-- Google Workspace data and any records you explicitly create.
