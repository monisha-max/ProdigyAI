-- ProdigyAI Database Schema
-- Seed data aligned to demo around April 3, 2026 (Friday)

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    deadline DATE,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'on_hold')),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Tasks table
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

-- Events table
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

-- Notes table
CREATE TABLE IF NOT EXISTS notes (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    tags VARCHAR(255),
    related_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    related_event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);
CREATE INDEX IF NOT EXISTS idx_notes_tags ON notes(tags);

-- ═══ SEED DATA ═══
-- Aligned to April 3, 2026 (Friday) as "today"

INSERT INTO projects (name, description, deadline, status) VALUES
('Product Launch', 'Q2 flagship product launch campaign', '2026-04-15', 'active'),
('Website Redesign', 'Modernize company website with new brand identity', '2026-04-25', 'active'),
('Team Offsite', 'Annual team building retreat planning', '2026-04-11', 'active')
ON CONFLICT (name) DO NOTHING;

INSERT INTO tasks (title, description, priority, due_date, status, project) VALUES
-- Overdue (due before today April 3)
('Code review: auth module', 'Review authentication refactor PR #247', 'high', '2026-04-02', 'todo', 'Website Redesign'),
-- Due today (April 3 = Friday)
('Review PR strategy', 'Approve media outreach plan from comms team', 'high', '2026-04-03', 'todo', 'Product Launch'),
('Finalize launch deck', 'Complete the investor-facing presentation with Q1 metrics', 'high', '2026-04-03', 'in_progress', 'Product Launch'),
-- Due next week
('Book venue for offsite', 'Research and book venue for 30 people', 'urgent', '2026-04-06', 'todo', 'Team Offsite'),
('Set up monitoring alerts', 'Configure Datadog alerts for launch traffic spike', 'high', '2026-04-07', 'todo', 'Product Launch'),
('Update landing page copy', 'Refresh hero section and CTAs for new product', 'medium', '2026-04-08', 'todo', 'Website Redesign'),
('Write blog post', 'Draft announcement blog post for launch day', 'medium', '2026-04-09', 'todo', 'Product Launch'),
('Send team survey', 'Collect activity preferences from all attendees', 'low', '2026-04-10', 'todo', 'Team Offsite')
ON CONFLICT DO NOTHING;

INSERT INTO events (title, event_date, start_time, end_time, attendees, location, related_project) VALUES
-- Today (April 3 = Friday)
('Launch Standup', '2026-04-03', '09:00', '09:30', 'Sarah, Mike, Priya', 'Zoom', 'Product Launch'),
('Design Review', '2026-04-03', '14:00', '15:00', 'Alex, Jordan', 'Conference Room B', 'Website Redesign'),
('Friday Wrap-up', '2026-04-03', '16:30', '17:00', 'Full Team', 'Zoom', NULL),
-- Monday April 6
('Sprint Planning', '2026-04-06', '10:00', '11:00', 'Engineering Team', 'Main Hall', 'Website Redesign'),
('1:1 with Manager', '2026-04-06', '15:00', '15:30', 'Chris', 'Office', NULL),
-- Tuesday April 7
('Product Demo', '2026-04-07', '14:00', '15:30', 'Stakeholders', 'Board Room', 'Product Launch'),
-- Wednesday April 8
('Offsite Planning Sync', '2026-04-08', '11:00', '11:45', 'Full Team', 'Zoom', 'Team Offsite'),
-- Thursday April 9
('Launch Dress Rehearsal', '2026-04-09', '10:00', '12:00', 'All Hands', 'Main Hall', 'Product Launch')
ON CONFLICT DO NOTHING;

INSERT INTO notes (title, content, tags, related_task_id, related_event_id) VALUES
('Launch Day Checklist', 'Pre-launch: verify CDN cache, test checkout flow, confirm support coverage. Post-launch: monitor error rates for 2h, social media response tracking, send thank-you to beta users.', 'launch,checklist', 2, NULL),
('Venue Options Research', 'Top 3: Lakehouse Retreat ($5k, 40 cap), Mountain Lodge ($4.2k, 35 cap), Urban Loft ($3.8k, 30 cap). Lakehouse has best reviews and team prefers it.', 'offsite,venue,research', 4, NULL),
('Design Review Notes - April 3', 'Team agreed on glassmorphism style for new components. Alex to provide updated mockups by Tuesday. Jordan flagged accessibility concerns with low contrast — needs WCAG AA compliance check.', 'design,review,accessibility', NULL, 2)
ON CONFLICT DO NOTHING;
