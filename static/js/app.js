const API = '';

let workloadChart = null;
let weekOffset = 0;
let isStreaming = false;
let chatSessionId = null;
let briefingSessionId = null;
let recognition = null;
let isListening = false;

let cachedTasks = [];
let cachedEvents = [];
let cachedGoogleTasks = [];
let cachedGoogleEvents = [];
let cachedGmailThreads = [];
let notifications = [];
let googleWorkspaceStatus = { connected: false, state: 'disconnected', message: 'Not synced yet.' };
const BROWSER_TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Local';

const NODE_MAP = {
    coordinator: 'node-coordinator',
    task_ops: 'node-taskops',
    calendar_ops: 'node-calendarops',
    knowledge_base: 'node-knowledge',
    insights: 'node-insights',
    gmail_ops: 'node-gmailops',
};
const MINI_MAP = {
    coordinator: 'mini-coordinator',
    task_ops: 'mini-taskops',
    calendar_ops: 'mini-calendarops',
    knowledge_base: 'mini-knowledge',
    insights: 'mini-insights',
    gmail_ops: 'mini-gmailops',
};
const LINE_MAP = {
    task_ops: 'line-taskops',
    calendar_ops: 'line-calendarops',
    knowledge_base: 'line-knowledge',
    insights: 'line-insights',
};
const STATUS_MAP = {
    coordinator: 'status-coordinator',
    task_ops: 'status-taskops',
    calendar_ops: 'status-calendarops',
    knowledge_base: 'status-knowledge',
    insights: 'status-insights',
    gmail_ops: 'status-gmailops',
};
const NAMES = {
    coordinator: 'Coordinator',
    task_ops: 'TaskOps',
    calendar_ops: 'CalendarOps',
    knowledge_base: 'Knowledge',
    insights: 'Insights',
    gmail_ops: 'GmailOps',
};

document.addEventListener('DOMContentLoaded', () => {
    initSplash();
    setDate();
    createParticles();
    autoResize();
    initScheduleForm();
    initTaskForm();
});

function initSplash() {
    const statuses = [
        'Connecting to Cloud SQL via MCP Toolbox...',
        'Connecting to Google Workspace MCP...',
        'Checking Google Maps integration...',
        'Loading TaskOps Agent...',
        'Loading CalendarOps Agent...',
        'Loading GmailOps Agent...',
        'Loading KnowledgeBase Agent...',
        'Loading Insights Agent...',
        'Coordinator online. Analyzing your day...',
    ];
    let i = 0;
    const el = document.getElementById('splashStatus');
    const interval = setInterval(() => {
        i += 1;
        if (i < statuses.length) el.textContent = statuses[i];
        else clearInterval(interval);
    }, 280);
    setTimeout(() => {
        document.getElementById('splash').classList.add('hidden');
        document.getElementById('app').style.opacity = '1';
        setTimeout(() => {
            if (window.innerWidth > 768) toggleChat();
            refreshAll();
        }, 300);
    }, 3000);
}

function createParticles() {
    const c = document.getElementById('splashParticles');
    for (let i = 0; i < 40; i += 1) {
        const p = document.createElement('div');
        p.className = 'splash-particle';
        p.style.left = `${Math.random() * 100}%`;
        p.style.top = `${Math.random() * 100}%`;
        p.style.animationDelay = `${Math.random() * 6}s`;
        p.style.animationDuration = `${4 + Math.random() * 4}s`;
        c.appendChild(p);
    }
}

function setDate() {
    const d = new Date();
    document.getElementById('currentDate').textContent = d.toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
    });
    const greet = d.getHours() < 12 ? 'Good Morning' : d.getHours() < 17 ? 'Good Afternoon' : 'Good Evening';
    const el = document.getElementById('commandGreeting');
    if (el) el.textContent = `${greet} - Here's your optimized day`;
}

async function fetchData(url, options = undefined) {
    try {
        const response = await fetch(API + url, options);
        return await response.json();
    } catch {
        return {};
    }
}

function mergeTasks(localTasks, googleTasks) {
    const local = (Array.isArray(localTasks) ? localTasks : []).map(task => ({ ...task, source: task.source || 'local' }));
    const google = (Array.isArray(googleTasks) ? googleTasks : []).map(task => ({
        ...task,
        source: 'google',
        project: task.project || 'Google Tasks',
        description: task.description || task.notes || '',
    }));
    return [...local, ...google];
}

function mergeEvents(localEvents, googleEvents) {
    const local = (Array.isArray(localEvents) ? localEvents : []).map(event => ({ ...event, source: event.source || 'local' }));
    const google = (Array.isArray(googleEvents) ? googleEvents : []).map(event => ({ ...event, source: 'google' }));
    return [...local, ...google].sort((a, b) => (a.start_time || '').localeCompare(b.start_time || ''));
}

async function syncGoogleWorkspace(silent = false) {
    try {
        const data = await fetchData('/api/google/sync', { method: 'POST' });
        googleWorkspaceStatus = data.status || googleWorkspaceStatus;
        renderWorkspaceStatus(googleWorkspaceStatus);
        if (!silent) addActivityLog('gmail_ops', `Workspace sync complete: ${data.calendar_events || 0} events, ${data.tasks || 0} tasks, ${data.threads || 0} threads`);
        return data;
    } catch {
        googleWorkspaceStatus = { connected: false, state: 'error', message: 'Unable to reach the Google Workspace sync endpoint.' };
        renderWorkspaceStatus(googleWorkspaceStatus);
        return null;
    }
}

async function refreshAll() {
    await syncGoogleWorkspace(true);
    const [localTasks, localEvents, googleTasksPayload, googleCalendarPayload, gmailSummary] = await Promise.all([
        fetchData('/api/tasks?status=all'),
        fetchData('/api/events/today'),
        fetchData('/api/google/tasks'),
        fetchData('/api/google/calendar/today'),
        fetchData('/api/google/gmail/summary'),
    ]);

    cachedGoogleTasks = googleTasksPayload.tasks || [];
    cachedGoogleEvents = googleCalendarPayload.events || [];
    cachedGmailThreads = gmailSummary.threads || [];
    googleWorkspaceStatus = googleCalendarPayload.status || googleTasksPayload.status || gmailSummary.status || googleWorkspaceStatus;

    cachedTasks = mergeTasks(localTasks, cachedGoogleTasks);
    cachedEvents = mergeEvents(localEvents, cachedGoogleEvents);

    renderWorkspaceStatus(googleWorkspaceStatus);
    renderGoogleCalendarPanel(cachedGoogleEvents);
    renderGmailPanel(gmailSummary);
    updateStats(cachedTasks, cachedEvents);
    renderKanban(cachedTasks);
    renderBattlePlan(cachedTasks, cachedEvents);
    generateSmartAlerts(cachedTasks, cachedEvents, gmailSummary);
    loadWeekRadar();
    generateCommandBriefing();

    const activeView = document.querySelector('.view.active')?.id || '';
    if (activeView === 'view-tasks') loadTasksView(getCurrentTaskFilter());
    if (activeView === 'view-calendar') loadCalendarView();
    if (activeView === 'view-notes') loadNotesView();
}

function renderWorkspaceStatus(status) {
    const pill = document.getElementById('googleWorkspaceStatus');
    const meta = document.getElementById('googleWorkspaceMeta');
    const copy = document.getElementById('googleWorkspaceCopy');
    if (!pill || !meta || !copy) return;
    pill.textContent = status.connected ? 'Connected' : 'Disconnected';
    pill.className = `status-pill ${status.connected ? 'status-good' : 'status-warn'}`;
    meta.textContent = status.connected ? 'Workspace MCP connected and cache ready.' : 'Workspace MCP unavailable or not yet configured.';
    copy.textContent = status.message || 'Google Workspace integration is waiting for its first sync.';
}

function renderGoogleCalendarPanel(events) {
    const list = document.getElementById('googleCalendarList');
    if (!list) return;
    if (!events.length) {
        list.innerHTML = '<div class="workspace-empty">No Google Calendar events for today yet.</div>';
        return;
    }
    list.innerHTML = events.map(event => `
        <div class="workspace-item">
            <div class="workspace-item-icon calendar"><span class="material-icons-round">event</span></div>
            <div class="workspace-item-body">
                <div class="workspace-item-title">
                    <span>${esc(event.title)}</span>
                    <span class="source-badge google">Google</span>
                </div>
                <div class="workspace-item-copy">${esc(event.summary || event.location || 'Calendar event')}</div>
                <div class="workspace-item-meta">
                    <span>${fmtTime(event.start_time) || 'All day'}${event.end_time ? ` - ${fmtTime(event.end_time)}` : ''}</span>
                    ${event.location ? `<span>${esc(event.location)}</span>` : ''}
                    ${event.attendees ? `<span>${esc(event.attendees)}</span>` : ''}
                </div>
            </div>
        </div>
    `).join('');
}

function getDateKey(value = new Date()) {
    const date = value instanceof Date ? value : new Date(value);
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().split('T')[0];
}

function renderGmailPanel(summary) {
    const count = document.getElementById('gmailUnreadCount');
    const list = document.getElementById('gmailThreadList');
    const threads = summary.threads || [];
    if (count) count.textContent = `${summary.unread_count || 0} unread`;
    if (!list) return;
    if (!threads.length) {
        list.innerHTML = '<div class="workspace-empty">No priority Gmail threads cached yet.</div>';
        return;
    }
    list.innerHTML = threads.map(thread => `
        <div class="workspace-item">
            <div class="workspace-item-icon gmail"><span class="material-icons-round">mail</span></div>
            <div class="workspace-item-body">
                <div class="workspace-item-title">
                    <span>${esc(thread.subject)}</span>
                    <span class="source-badge google">Gmail</span>
                </div>
                <div class="workspace-item-copy">${esc(thread.summary || thread.snippet || 'Inbox thread')}</div>
                <div class="workspace-item-meta">
                    ${thread.sender ? `<span>${esc(thread.sender)}</span>` : ''}
                    ${thread.received_at ? `<span>${new Date(thread.received_at).toLocaleString()}</span>` : ''}
                </div>
                <div class="workspace-inline-actions">
                    <button class="workspace-action-btn" onclick="createTaskFromEmail('${encodeURIComponent(thread.id)}', '${encodeURIComponent(thread.subject)}')">Create follow-up task</button>
                    <button class="workspace-action-btn" onclick="draftReplyFromEmail('${encodeURIComponent(thread.id)}', '${encodeURIComponent(thread.subject)}')">Draft reply</button>
                </div>
            </div>
        </div>
    `).join('');
}

function quickCreateGoogleEvent() {
    openScheduleModal();
}

function initScheduleForm() {
    const dateInput = document.getElementById('scheduleDate');
    const startInput = document.getElementById('scheduleStartTime');
    const endInput = document.getElementById('scheduleEndTime');
    const timezoneInput = document.getElementById('scheduleTimezone');
    if (timezoneInput) timezoneInput.value = BROWSER_TIMEZONE;
    if (dateInput) dateInput.value = getLocalDateInputValue();
    if (startInput && !startInput.value) startInput.value = getRoundedTimeValue();
    if (endInput && !endInput.value) endInput.value = getRoundedTimeValue(60);
    [dateInput, startInput, endInput].forEach(input => input?.addEventListener('input', updateSchedulePreview));
    updateSchedulePreview();
}

function openScheduleModal(prefill = {}) {
    const modal = document.getElementById('scheduleModal');
    if (!modal) return;
    document.getElementById('scheduleTitle').value = prefill.title || '';
    document.getElementById('scheduleDate').value = prefill.event_date || getLocalDateInputValue();
    document.getElementById('scheduleStartTime').value = prefill.start_time || getRoundedTimeValue();
    document.getElementById('scheduleEndTime').value = prefill.end_time || getRoundedTimeValue(60);
    document.getElementById('scheduleLocation').value = prefill.location || '';
    document.getElementById('scheduleAttendees').value = prefill.attendees || '';
    document.getElementById('scheduleDescription').value = prefill.description || '';
    document.getElementById('scheduleTimezone').value = BROWSER_TIMEZONE;
    document.getElementById('scheduleTimezoneCopy').textContent = `Times will be created in ${BROWSER_TIMEZONE}.`;
    updateSchedulePreview();
    modal.style.display = 'flex';
    document.body.classList.add('modal-open');
    setTimeout(() => document.getElementById('scheduleTitle').focus(), 50);
}

function closeScheduleModal() {
    const modal = document.getElementById('scheduleModal');
    if (!modal) return;
    modal.style.display = 'none';
    document.body.classList.remove('modal-open');
}

function updateSchedulePreview() {
    const preview = document.getElementById('schedulePreview');
    if (!preview) return;
    const title = document.getElementById('scheduleTitle')?.value?.trim() || 'Untitled meeting';
    const date = document.getElementById('scheduleDate')?.value || getLocalDateInputValue();
    const start = document.getElementById('scheduleStartTime')?.value || '10:00';
    const end = document.getElementById('scheduleEndTime')?.value || '11:00';
    preview.textContent = `${title} will be created for ${fmtDateLong(date)} from ${fmtTime(start)} to ${fmtTime(end)} in ${BROWSER_TIMEZONE}.`;
}

async function submitScheduleMeeting(event) {
    event.preventDefault();
    const payload = {
        title: document.getElementById('scheduleTitle').value.trim(),
        event_date: document.getElementById('scheduleDate').value,
        start_time: document.getElementById('scheduleStartTime').value,
        end_time: document.getElementById('scheduleEndTime').value,
        location: document.getElementById('scheduleLocation').value.trim(),
        attendees: document.getElementById('scheduleAttendees').value.trim(),
        description: document.getElementById('scheduleDescription').value.trim(),
        timezone: BROWSER_TIMEZONE,
    };
    if (!payload.title || !payload.event_date || !payload.start_time || !payload.end_time) return;
    if (payload.end_time <= payload.start_time) {
        alert('End time must be after start time.');
        return;
    }
    const response = await fetchData('/api/google/calendar/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (response.event) {
        closeScheduleModal();
        addActivityLog('calendar_ops', `Created Google Calendar event: ${response.event.title}`);
        fireConfetti();
        setWeekForDate(response.event.event_date || payload.event_date);
        await refreshAll();
        switchView('calendar');
    } else if (response.error) {
        alert(response.error);
    }
}

async function quickAddGoogleTask() {
    openTaskModal();
}

function initTaskForm() {
    const dueInput = document.getElementById('taskDueDate');
    const titleInput = document.getElementById('taskTitle');
    const notesInput = document.getElementById('taskNotes');
    [dueInput, titleInput, notesInput].forEach(input => input?.addEventListener('input', updateTaskPreview));
    updateTaskPreview();
}

function openTaskModal(prefill = {}) {
    const modal = document.getElementById('taskModal');
    if (!modal) return;
    document.getElementById('taskTitle').value = prefill.title || '';
    document.getElementById('taskDueDate').value = prefill.due_date || '';
    document.getElementById('taskNotes').value = prefill.notes || '';
    document.getElementById('taskPriority').value = prefill.priority || 'medium';
    updateTaskPreview();
    modal.style.display = 'flex';
    document.body.classList.add('modal-open');
    setTimeout(() => document.getElementById('taskTitle').focus(), 50);
}

function closeTaskModal() {
    const modal = document.getElementById('taskModal');
    if (!modal) return;
    modal.style.display = 'none';
    document.body.classList.remove('modal-open');
}

function updateTaskPreview() {
    const preview = document.getElementById('taskPreview');
    if (!preview) return;
    const title = document.getElementById('taskTitle')?.value?.trim() || 'Untitled task';
    const due = document.getElementById('taskDueDate')?.value || '';
    preview.textContent = due
        ? `${title} will be created in Google Tasks and due on ${fmtDateLong(due)}.`
        : `${title} will be created in Google Tasks with no due date yet.`;
}

async function submitGoogleTaskForm(event) {
    event.preventDefault();
    const payload = {
        title: document.getElementById('taskTitle').value.trim(),
        due_date: document.getElementById('taskDueDate').value,
        notes: document.getElementById('taskNotes').value.trim(),
        priority: document.getElementById('taskPriority').value || 'medium',
    };
    if (!payload.title) return;
    const response = await fetchData('/api/google/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (response.task) {
        closeTaskModal();
        addActivityLog('task_ops', `Created Google Task: ${response.task.title}`);
        fireConfetti();
        await refreshAll();
        switchView('tasks');
    } else if (response.error) {
        alert(response.error);
    }
}

async function createTaskFromEmail(encodedThreadId, encodedSubject) {
    const threadId = decodeURIComponent(encodedThreadId);
    const subject = decodeURIComponent(encodedSubject);
    const title = prompt('Task title', `Follow up: ${subject}`) || `Follow up: ${subject}`;
    const dueDate = prompt('Due date (YYYY-MM-DD, optional)', '') || '';
    const response = await fetchData('/api/google/task-from-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: threadId, title, due_date: dueDate }),
    });
    if (response.task) {
        addActivityLog('gmail_ops', `Created task from Gmail thread: ${subject}`);
        fireConfetti();
        await refreshAll();
    }
}

async function draftReplyFromEmail(encodedThreadId, encodedSubject) {
    const threadId = decodeURIComponent(encodedThreadId);
    const subject = decodeURIComponent(encodedSubject);
    const body = prompt('Draft body', `Hi,\n\nThanks for the note about ${subject}.\n\n`) || '';
    const response = await fetchData('/api/google/draft-from-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: threadId, body }),
    });
    if (response.draft) {
        addActivityLog('gmail_ops', `Drafted Gmail reply for: ${subject}`);
        fireConfetti();
        await refreshAll();
    }
}

async function generateCommandBriefing() {
    const body = document.getElementById('commandBody');
    const time = document.getElementById('commandTime');
    const actions = document.getElementById('commandActions');
    const badge = document.getElementById('commandBadge');

    body.innerHTML = `<div class="command-loading"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div><span>Insights Agent analyzing tasks, events, workload, and inbox context...</span></div>`;
    actions.style.display = 'none';

    try {
        const res = await fetch(API + '/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: `You are generating a proactive morning command briefing. Analyze my day and give me:

1. STATUS: one-line assessment
2. TOP 3 PRIORITIES: ranked by urgency
3. SCHEDULE INSIGHT: where to fit the work today
4. RISK ALERT: overdue items, conflicts, overloaded days, or inbox follow-ups
5. MY RECOMMENDATION: one specific action

Be concise, strategic, and opinionated. Use markdown.`,
            }),
        });
        const data = await res.json();
        briefingSessionId = data.session_id;
        body.innerHTML = marked.parse(data.response || 'No briefing available.');
        time.textContent = `Generated at ${new Date().toLocaleTimeString()} by Insights Agent`;
        actions.style.display = 'flex';
        const overdue = cachedTasks.filter(task => task.status !== 'done' && task.due_date && task.due_date < new Date().toISOString().split('T')[0]).length;
        if (overdue > 0) {
            badge.className = 'command-badge alert';
            badge.innerHTML = `<span class="material-icons-round">warning</span><span>${overdue} Overdue</span>`;
        } else {
            badge.className = 'command-badge';
            badge.innerHTML = `<span class="material-icons-round">check_circle</span><span>On Track</span>`;
        }
        addActivityLog('insights', 'Morning briefing generated');
    } catch {
        body.innerHTML = `<p style="color:var(--text-muted)">Connect to ProdigyAI server for your AI-generated command briefing.</p>`;
        time.textContent = 'Offline';
    }
}

async function executeCommandPlan() {
    addMessage('Execute the optimizations you suggested in the briefing. Move tasks if needed, adjust priorities, and confirm what changed.', 'user');
    const typingId = showTyping();
    activateAgent('coordinator', 'Executing accepted plan...');
    showAgentStream(['Coordinator analyzing accepted plan...', 'TaskOps applying task changes...', 'CalendarOps adjusting schedule...', 'GmailOps checking follow-ups...', 'Confirming changes...']);
    try {
        const res = await fetch(API + '/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: 'Execute the optimizations from the briefing. Move tasks if needed, adjust priorities, and call out any Gmail follow-ups.',
                session_id: briefingSessionId,
            }),
        });
        removeTyping(typingId);
        completeAgentStream();
        const data = await res.json();
        addMessage(data.response, 'bot');
        fireConfetti();
        setTimeout(refreshAll, 500);
    } catch {
        removeTyping(typingId);
        completeAgentStream();
        addMessage('Failed to execute plan.', 'bot');
    }
}

function modifyCommandPlan() {
    toggleChat();
    document.getElementById('chatInput').value = 'I want to modify the plan: ';
    document.getElementById('chatInput').focus();
}

function dismissCommand() {
    document.getElementById('commandActions').style.display = 'none';
}

function generateSmartAlerts(tasks, events, gmailSummary = {}) {
    notifications = [];
    const overdue = tasks.filter(task => task.status !== 'done' && task.due_date && task.due_date < new Date().toISOString().split('T')[0]);
    overdue.forEach(task => {
        notifications.push({ icon: 'danger', iconName: 'warning', text: `<strong>${esc(task.title)}</strong> is overdue (due ${fmtDate(task.due_date)})`, time: 'Now' });
    });
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];
    tasks.filter(task => task.due_date === tomorrowStr && task.status !== 'done').forEach(task => {
        notifications.push({ icon: 'warn', iconName: 'schedule', text: `<strong>${esc(task.title)}</strong> is due tomorrow`, time: 'Soon' });
    });
    events.forEach(event => {
        notifications.push({ icon: 'info', iconName: 'event', text: `<strong>${esc(event.title)}</strong> at ${fmtTime(event.start_time)} ${event.source === 'google' ? 'from Google Calendar' : ''}`, time: 'Today' });
    });
    const unread = gmailSummary.unread_count || 0;
    if (unread > 0) {
        notifications.push({ icon: 'info', iconName: 'mail', text: `Your inbox has <strong>${unread} unread</strong> priority thread${unread !== 1 ? 's' : ''}`, time: 'Inbox' });
    }
    const dot = document.getElementById('notifDot');
    dot.classList.toggle('active', notifications.length > 0);
    document.getElementById('notifCount').textContent = notifications.length;
    renderNotifications();
}

function renderNotifications() {
    const list = document.getElementById('notifList');
    if (!notifications.length) {
        list.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">All clear!</div>';
        return;
    }
    list.innerHTML = notifications.map(item => `
        <div class="notif-item">
            <div class="notif-item-icon ${item.icon}"><span class="material-icons-round">${item.iconName}</span></div>
            <div class="notif-item-text">${item.text}</div>
            <div class="notif-item-time">${item.time}</div>
        </div>
    `).join('');
}

function toggleNotifications() {
    document.getElementById('notifPanel').classList.toggle('open');
}

document.addEventListener('click', event => {
    const panel = document.getElementById('notifPanel');
    const btn = document.getElementById('notifBtn');
    if (panel && btn && !panel.contains(event.target) && !btn.contains(event.target)) panel.classList.remove('open');
});

function renderBattlePlan(tasks, events) {
    const container = document.getElementById('battleTimeline');
    const items = [];
    events.forEach(event => items.push({
        type: 'event',
        time: event.start_time || '09:00',
        title: event.title,
        detail: `${event.location ? `@ ${event.location}` : ''} ${event.source === 'google' ? '(Google Calendar)' : ''}`.trim(),
        sortKey: event.start_time || '09:00',
    }));
    tasks.filter(task => task.status !== 'done' && task.due_date)
        .sort((a, b) => ({ urgent: 0, high: 1, medium: 2, low: 3 }[a.priority] || 3) - ({ urgent: 0, high: 1, medium: 2, low: 3 }[b.priority] || 3))
        .slice(0, 4)
        .forEach((task, index) => items.push({ type: 'task', title: task.title, detail: `${task.priority} priority · ${task.source === 'google' ? 'Google Task' : 'Local task'}`, priority: task.priority, sortKey: `99${index}` }));
    if (!items.length) {
        container.innerHTML = '<div class="timeline-empty">No events or tasks for today</div>';
        return;
    }
    items.sort((a, b) => a.sortKey.localeCompare(b.sortKey));
    container.innerHTML = items.map(item => item.type === 'event'
        ? `<div class="battle-block event-block"><div class="battle-time">${fmtTime(item.time)}</div><div class="battle-info"><h4>${esc(item.title)}</h4><p>${esc(item.detail)}</p></div><span class="battle-tag event">Event</span></div>`
        : `<div class="battle-block task-block"><div class="battle-time"><span class="priority-badge priority-${item.priority}" style="font-size:0.6rem">${item.priority}</span></div><div class="battle-info"><h4>${esc(item.title)}</h4><p>${esc(item.detail)}</p></div><span class="battle-tag task">Task</span></div>`).join('');
}

async function loadWeekRadar() {
    let data = [];
    try {
        data = await fetchData('/api/insights/workload');
    } catch {
        data = placeholderWorkload();
    }
    if (!Array.isArray(data)) data = placeholderWorkload();
    renderRadarDays(data);
    renderWorkloadChart(data);
}

function renderRadarDays(data) {
    const c = document.getElementById('radarDays');
    const today = new Date().toISOString().split('T')[0];
    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    c.innerHTML = data.map(day => {
        const dt = new Date(`${day.date}T00:00:00`);
        const load = (day.tasks_due || 0) + (day.events_scheduled || 0);
        const cls = load >= 5 ? 'load-heavy' : load >= 3 ? 'load-medium' : 'load-light';
        return `<div class="radar-day ${day.date === today ? 'today' : ''}" title="${load} items"><div class="radar-day-name">${dayNames[dt.getDay()]}</div><div class="radar-day-num">${dt.getDate()}</div><div class="radar-day-load ${cls}">${load}</div></div>`;
    }).join('');
}

function updateStats(tasks, events) {
    const pending = tasks.filter(task => task.status !== 'done').length;
    const overdue = tasks.filter(task => task.status !== 'done' && task.due_date && task.due_date < new Date().toISOString().split('T')[0]).length;
    const completed = tasks.filter(task => task.status === 'done').length;
    animateNum('statPending', pending);
    animateNum('statOverdue', overdue);
    animateNum('statEventsToday', events.length);
    animateNum('statCompleted', completed);
    document.getElementById('taskBadge').textContent = pending;
    document.getElementById('statOverdueCard').classList.toggle('has-overdue', overdue > 0);
}

function animateNum(id, target) {
    const el = document.getElementById(id);
    const start = parseInt(el.textContent, 10) || 0;
    const t0 = performance.now();
    const animate = t => {
        const p = Math.min((t - t0) / 800, 1);
        el.textContent = Math.round(start + (target - start) * (1 - Math.pow(1 - p, 4)));
        if (p < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
}

function renderKanban(tasks) {
    const todo = tasks.filter(task => task.status === 'todo');
    const progress = tasks.filter(task => task.status === 'in_progress');
    const done = tasks.filter(task => task.status === 'done');
    document.getElementById('todoCount').textContent = todo.length;
    document.getElementById('progressCount').textContent = progress.length;
    document.getElementById('doneCount').textContent = done.length;
    document.getElementById('kanbanTodo').innerHTML = todo.map(kanbanCard).join('');
    document.getElementById('kanbanProgress').innerHTML = progress.map(kanbanCard).join('');
    document.getElementById('kanbanDone').innerHTML = done.map(kanbanCard).join('');
}

function kanbanCard(task) {
    const overdue = task.due_date && task.due_date < new Date().toISOString().split('T')[0] && task.status !== 'done';
    return `<div class="kanban-card" onclick="handleTaskAction('${encodeURIComponent(String(task.id))}','${task.status}','${task.source || 'local'}')">
        <div class="kanban-card-title">${esc(task.title)}</div>
        <div class="kanban-card-meta">
            <span class="priority-badge priority-${task.priority || 'medium'}">${task.priority || 'medium'}</span>
            <span class="kanban-card-date" style="${overdue ? 'color:var(--danger)' : ''}">${task.due_date ? fmtDate(task.due_date) : '-'}</span>
        </div>
        ${task.project ? `<div class="kanban-card-project">${esc(task.project)}</div>` : ''}
        <div class="kanban-card-source"><span class="source-badge ${(task.source || 'local') === 'google' ? 'google' : 'local'}">${(task.source || 'local') === 'google' ? 'Google' : 'Local'}</span></div>
    </div>`;
}

async function handleTaskAction(encodedId, status, source) {
    const id = decodeURIComponent(encodedId);
    if (source === 'google') {
        if (status === 'done') return;
        await completeGoogleTask(id);
    } else {
        await cycleTask(parseInt(id, 10), status);
    }
}

async function cycleTask(id, status) {
    const next = { todo: 'in_progress', in_progress: 'done', done: 'todo' };
    try {
        await fetch(API + `/api/tasks/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: next[status] }),
        });
        if (next[status] === 'done') fireConfetti();
        await refreshAll();
    } catch {}
}

async function completeGoogleTask(taskId) {
    try {
        const data = await fetchData(`/api/google/tasks/${encodeURIComponent(taskId)}/complete`, { method: 'POST' });
        if (data.success) {
            addActivityLog('task_ops', `Completed Google Task ${taskId}`);
            fireConfetti();
            await refreshAll();
        }
    } catch {}
}

function getCurrentTaskFilter() {
    const btn = document.querySelector('.filter-btn.active');
    if (!btn) return 'all';
    return { All: 'all', 'To Do': 'todo', 'In Progress': 'in_progress', Done: 'done' }[btn.textContent.trim()] || 'all';
}

async function showTimeMachine(targetDate) {
    const tm = document.getElementById('timeMachine');
    tm.style.display = 'block';
    document.getElementById('view-command').scrollTop = 0;
    tm.scrollIntoView({ behavior: 'smooth', block: 'start' });
    document.getElementById('tmSubtitle').textContent = `Simulating day off: ${targetDate}`;
    document.getElementById('tmWeekBefore').innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem">Loading...</div>';
    document.getElementById('tmWeekAfter').innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem">Calculating...</div>';
    document.getElementById('tmMoves').innerHTML = '';
    try {
        const data = await fetchData(`/api/simulate/${targetDate}`);
        renderTimeMachine(data);
    } catch {
        document.getElementById('tmSubtitle').textContent = 'Simulation failed';
    }
}

function renderTimeMachine(data) {
    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const maxLoad = Math.max(...data.workload_before.map(day => day.tasks + day.events), ...data.workload_after.map(day => day.tasks + day.events), 1);
    document.getElementById('tmSubtitle').textContent = `What if you take ${new Date(`${data.target_date}T00:00:00`).toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })} off?`;
    document.getElementById('tmImpactText').textContent = `${data.total_affected} item${data.total_affected !== 1 ? 's' : ''} affected`;
    const renderDay = (day, isTarget, isAfter, beforeTotal) => {
        const dt = new Date(`${day.date}T00:00:00`);
        const total = day.tasks + day.events;
        const grew = isAfter && total > (beforeTotal || 0);
        const pct = total > 0 ? Math.max((total / maxLoad) * 100, 8) : 0;
        return `<div class="tm-day-row ${isTarget ? 'target-day' : ''} ${grew ? 'highlighted' : ''}">
            <span class="tm-day-name">${dayNames[dt.getDay()]}</span>
            <span class="tm-day-date">${day.date.slice(5)}</span>
            <div class="tm-day-bar">${isTarget && isAfter && total === 0 ? '<div class="tm-day-off">DAY OFF</div>' : `<div class="tm-day-fill ${total >= 5 ? 'tm-fill-heavy' : 'tm-fill-normal'}" style="width:${pct}%">${total}</div>`}</div>
            <span class="tm-day-count">${total}</span>
        </div>`;
    };
    document.getElementById('tmWeekBefore').innerHTML = data.workload_before.map(day => renderDay(day, day.date === data.target_date, false, 0)).join('');
    document.getElementById('tmWeekAfter').innerHTML = data.workload_after.map(day => {
        const before = data.workload_before.find(item => item.date === day.date);
        return renderDay(day, day.date === data.target_date, true, before ? before.tasks + before.events : 0);
    }).join('');
    document.getElementById('tmMoves').innerHTML = data.moves.map(move => `<div class="tm-move-item"><span class="tm-move-type ${move.type === 'event' ? 'event' : 'task'}">${move.type}</span><span class="tm-move-title">${esc(move.title)}</span><span class="tm-move-arrow">${move.from_date.slice(5)} <span class="material-icons-round">east</span> ${move.to_date.slice(5)}</span></div>`).join('');
}

function closeTimeMachine() {
    document.getElementById('timeMachine').style.display = 'none';
}

function executeTimeMachinePlan() {
    document.getElementById('chatInput').value = 'Execute the rescue plan from the what-if simulation. Move the affected tasks and events to their suggested new dates.';
    sendMessage();
    closeTimeMachine();
}

function placeholderWorkload() {
    const data = [];
    for (let i = 0; i < 7; i += 1) {
        const dt = new Date();
        dt.setDate(dt.getDate() + i);
        data.push({ date: dt.toISOString().split('T')[0], tasks_due: Math.floor(Math.random() * 4), events_scheduled: Math.floor(Math.random() * 3) });
    }
    return data;
}

function renderWorkloadChart(data) {
    const ctx = document.getElementById('workloadChart').getContext('2d');
    if (workloadChart) workloadChart.destroy();
    const labels = data.map(day => new Date(`${day.date}T00:00:00`).toLocaleDateString('en-US', { weekday: 'short', day: 'numeric' }));
    workloadChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Tasks', data: data.map(day => day.tasks_due), backgroundColor: 'rgba(108,92,231,0.5)', borderColor: 'rgba(108,92,231,1)', borderWidth: 1, borderRadius: 6 },
                { label: 'Events', data: data.map(day => day.events_scheduled), backgroundColor: 'rgba(116,185,255,0.5)', borderColor: 'rgba(116,185,255,1)', borderWidth: 1, borderRadius: 6 },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: '#9898B8', font: { size: 10 } } } },
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { color: '#5E5E80', font: { size: 9 } } },
                y: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { color: '#5E5E80', stepSize: 1 }, beginAtZero: true },
            },
        },
    });
}

function switchView(view) {
    document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.getElementById(`view-${view}`).classList.add('active');
    document.querySelector(`[data-view="${view}"]`).classList.add('active');
    document.getElementById('viewTitle').textContent = { command: 'Command Center', tasks: 'Tasks', calendar: 'Calendar', notes: 'Notes', agents: 'Agent Network' }[view] || view;
    if (view === 'tasks') loadTasksView(getCurrentTaskFilter());
    if (view === 'calendar') loadCalendarView();
    if (view === 'notes') loadNotesView();
}

function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
}

function toggleChat() {
    document.body.classList.toggle('chat-open');
    if (document.body.classList.contains('chat-open')) document.getElementById('chatInput').focus();
}

async function loadTasksView(filter = 'all') {
    const localTasks = await fetchData(`/api/tasks?status=${filter === 'all' ? 'all' : filter}`);
    const googleTasksPayload = await fetchData('/api/google/tasks');
    let tasks = mergeTasks(localTasks, googleTasksPayload.tasks || []);
    if (filter !== 'all') tasks = tasks.filter(task => task.status === filter);
    renderTaskList(tasks);
}

function filterTasks(status, btn) {
    document.querySelectorAll('.filter-btn').forEach(item => item.classList.remove('active'));
    btn.classList.add('active');
    loadTasksView(status);
}

function renderTaskList(tasks) {
    const container = document.getElementById('taskListView');
    if (!Array.isArray(tasks)) tasks = [];
    if (!tasks.length) {
        container.innerHTML = '<div class="timeline-empty">No tasks found</div>';
        return;
    }
    container.innerHTML = tasks.map(task => {
        const overdue = task.due_date && task.due_date < new Date().toISOString().split('T')[0] && task.status !== 'done';
        return `<div class="task-item">
            <div class="task-check ${task.status === 'done' ? 'checked' : ''}" onclick="event.stopPropagation(); handleTaskAction('${encodeURIComponent(String(task.id))}','${task.status}','${task.source || 'local'}')"></div>
            <div class="task-info">
                <div class="task-title ${task.status === 'done' ? 'completed' : ''}">${esc(task.title)}</div>
                <div class="task-meta">
                    <span class="priority-badge priority-${task.priority || 'medium'}">${task.priority || 'medium'}</span>
                    <span class="source-badge ${(task.source || 'local') === 'google' ? 'google' : 'local'}">${(task.source || 'local') === 'google' ? 'Google' : 'Local'}</span>
                    <span style="${overdue ? 'color:var(--danger)' : ''}"><span class="material-icons-round">event</span>${task.due_date ? fmtDate(task.due_date) : '-'}</span>
                    ${task.project ? `<span><span class="material-icons-round">folder</span>${esc(task.project)}</span>` : ''}
                </div>
            </div>
        </div>`;
    }).join('');
}

async function loadCalendarView() {
    const start = getWeekStart(weekOffset);
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    const startKey = getDateKey(start);
    const endKey = getDateKey(end);
    document.getElementById('calendarWeekLabel').textContent = `${start.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} - ${end.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`;
    const timezoneLabel = document.getElementById('calendarTimeZoneLabel');
    if (timezoneLabel) timezoneLabel.textContent = `Times shown in ${BROWSER_TIMEZONE}`;
    const [localEvents, googlePayload] = await Promise.all([
        fetchData(`/api/events/range?start=${startKey}&end=${endKey}`),
        fetchData(`/api/google/calendar/range?start=${startKey}&end=${endKey}`),
    ]);
    const events = mergeEvents(localEvents, googlePayload.events || []);
    const days = [];
    for (let i = 0; i < 7; i += 1) {
        const day = new Date(start);
        day.setDate(day.getDate() + i);
        days.push(day);
    }
    const today = getDateKey();
    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    document.getElementById('calendarGrid').innerHTML = days.map(day => {
        const ds = getDateKey(day);
        const dayEvents = events.filter(event => event.event_date === ds);
        return `<div class="calendar-day ${ds === today ? 'today' : ''}"><div class="calendar-day-header">${dayNames[day.getDay()]}</div><div class="calendar-day-number">${day.getDate()}</div>${dayEvents.length ? dayEvents.map(event => `<div class="calendar-event ${event.source === 'google' ? 'google' : ''}"><div class="calendar-event-time">${fmtTime(event.start_time) || 'All day'}</div><div class="calendar-event-title">${esc(event.title)}</div>${event.location ? `<div class="calendar-event-meta">${esc(event.location)}</div>` : ''}${event.attendees ? `<div class="calendar-event-meta">${esc(event.attendees)}</div>` : ''}</div>`).join('') : '<div class="calendar-empty-slot">No events</div>'}</div>`;
    }).join('');
}

function changeWeek(delta) {
    weekOffset += delta;
    loadCalendarView();
}

function setWeekForDate(dateString) {
    if (!dateString) return;
    const target = new Date(`${dateString}T00:00:00`);
    const currentWeekStart = getWeekStart(0);
    const targetWeekStart = new Date(target);
    const day = targetWeekStart.getDay();
    const diff = targetWeekStart.getDate() - day + (day === 0 ? -6 : 1);
    targetWeekStart.setDate(diff);
    targetWeekStart.setHours(0, 0, 0, 0);
    weekOffset = Math.round((targetWeekStart.getTime() - currentWeekStart.getTime()) / (7 * 24 * 60 * 60 * 1000));
}

function getWeekStart(offset) {
    const now = new Date();
    const day = now.getDay();
    const diff = now.getDate() - day + (day === 0 ? -6 : 1);
    const monday = new Date(now);
    monday.setDate(diff + offset * 7);
    monday.setHours(0, 0, 0, 0);
    return monday;
}

async function loadNotesView() {
    renderNotes(await fetchData('/api/notes'));
}

function renderNotes(notes) {
    const container = document.getElementById('notesGrid');
    if (!Array.isArray(notes)) notes = [];
    if (!notes.length) {
        container.innerHTML = '<div class="timeline-empty">No notes yet. Ask ProdigyAI to create one!</div>';
        return;
    }
    container.innerHTML = notes.map(note => `<div class="note-card"><div class="note-title">${esc(note.title)}</div><div class="note-content">${esc(note.content)}</div><div class="note-tags">${(note.tags || '').split(',').filter(Boolean).map(tag => `<span class="note-tag">${esc(tag.trim())}</span>`).join('')}</div><div class="note-date">${note.created_at ? new Date(note.created_at).toLocaleDateString() : ''}</div></div>`).join('');
}

function activateAgent(name, statusText = 'Processing...') {
    const nodeId = NODE_MAP[name];
    if (nodeId) {
        const node = document.getElementById(nodeId);
        if (node) {
            node.classList.add('active', 'working');
            node.classList.remove('done');
        }
    }
    if (LINE_MAP[name]) document.getElementById(LINE_MAP[name])?.classList.add('active');
    if (STATUS_MAP[name]) document.getElementById(STATUS_MAP[name]).textContent = statusText;
    if (MINI_MAP[name]) document.getElementById(MINI_MAP[name])?.classList.add('active');
    addActivityLog(name, statusText);
}

function deactivateAgent(name, doneText = 'Done') {
    const nodeId = NODE_MAP[name];
    if (nodeId) {
        const node = document.getElementById(nodeId);
        if (node) {
            node.classList.remove('active', 'working');
            node.classList.add('done');
            setTimeout(() => node.classList.remove('done'), 4000);
        }
    }
    if (LINE_MAP[name]) document.getElementById(LINE_MAP[name])?.classList.remove('active');
    if (STATUS_MAP[name]) document.getElementById(STATUS_MAP[name]).textContent = doneText;
    if (MINI_MAP[name]) setTimeout(() => document.getElementById(MINI_MAP[name])?.classList.remove('active'), 1500);
}

function resetAllAgents() {
    Object.keys(NODE_MAP).forEach(name => {
        document.getElementById(NODE_MAP[name])?.classList.remove('active', 'working', 'done');
        if (LINE_MAP[name]) document.getElementById(LINE_MAP[name])?.classList.remove('active');
        if (STATUS_MAP[name]) document.getElementById(STATUS_MAP[name]).textContent = name === 'coordinator' ? 'Idle' : 'Standby';
        if (MINI_MAP[name]) document.getElementById(MINI_MAP[name])?.classList.remove('active');
    });
}

async function runDemoReplay() {
    const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
    resetAllAgents();
    activateAgent('coordinator', 'Planning a cross-tool workflow...');
    await wait(700);
    activateAgent('gmail_ops', 'Reviewing inbox priorities...');
    await wait(700);
    deactivateAgent('gmail_ops', 'Inbox triaged');
    activateAgent('calendar_ops', 'Creating a Google Calendar event...');
    await wait(700);
    deactivateAgent('calendar_ops', 'Event created');
    activateAgent('task_ops', 'Adding follow-up tasks...');
    await wait(700);
    deactivateAgent('task_ops', 'Tasks created');
    activateAgent('insights', 'Summarizing the outcome...');
    await wait(700);
    deactivateAgent('insights', 'Summary ready');
    deactivateAgent('coordinator', 'Workflow complete');
}

function addActivityLog(agent, text) {
    const feed = document.getElementById('activityFeed');
    if (!feed) return;
    const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const cls = agent.replace('_', '');
    const item = document.createElement('div');
    item.className = 'activity-item';
    item.innerHTML = `<span class="activity-time">${time}</span><span class="activity-agent ${cls}">${NAMES[agent] || agent}</span><span class="activity-text">${text}</span>`;
    feed.appendChild(item);
    feed.scrollTop = feed.scrollHeight;
    while (feed.children.length > 30) feed.removeChild(feed.firstChild);
}

function showAgentStream(steps) {
    const stream = document.getElementById('agentStream');
    const el = document.getElementById('streamSteps');
    stream.style.display = 'block';
    el.innerHTML = '';
    steps.forEach((step, index) => {
        setTimeout(() => {
            const row = document.createElement('div');
            row.className = 'stream-step';
            row.innerHTML = `<div class="stream-step-icon running"><span class="material-icons-round" style="font-size:10px">sync</span></div><span class="stream-step-text active">${step}</span>`;
            el.appendChild(row);
        }, index * 350);
    });
}

function completeAgentStream() {
    document.querySelectorAll('#streamSteps .stream-step').forEach(step => {
        const icon = step.querySelector('.stream-step-icon');
        icon.className = 'stream-step-icon done';
        icon.innerHTML = '<span class="material-icons-round" style="font-size:10px">check</span>';
        step.querySelector('.stream-step-text').className = 'stream-step-text';
    });
    setTimeout(() => { document.getElementById('agentStream').style.display = 'none'; }, 2000);
}

function guessSteps(message) {
    const lower = message.toLowerCase();
    const steps = ['Coordinator analyzing intent...'];
    if (lower.includes('inbox') || lower.includes('gmail') || lower.includes('reply')) steps.push('GmailOps: Reviewing Gmail threads...', 'TaskOps: Capturing follow-up actions...');
    else if (lower.includes('prepare') || lower.includes('meeting') || lower.includes('schedule')) steps.push('CalendarOps: Checking schedule...', 'TaskOps: Planning follow-up work...');
    else if (lower.includes('briefing') || lower.includes('focus')) steps.push('Insights: Building strategic briefing...', 'CalendarOps: Reviewing schedule...');
    else if (lower.includes('what if') || lower.includes('day off') || lower.includes('simulate')) steps.push('Insights: Running what-if simulation...');
    else steps.push('Routing to best agent...');
    steps.push('Coordinator synthesizing response...');
    return steps;
}

function toggleVoice() {
    if (isListening) stopVoice();
    else startVoice();
}

function startVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        addMessage('Voice input is not supported in this browser. Try Chrome.', 'bot');
        return;
    }
    recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = true;
    recognition.continuous = false;
    const voiceBtn = document.getElementById('voiceBtn');
    const voiceIcon = document.getElementById('voiceIcon');
    const voiceStatus = document.getElementById('voiceStatus');
    const input = document.getElementById('chatInput');
    recognition.onstart = () => {
        isListening = true;
        voiceBtn.classList.add('listening');
        voiceIcon.textContent = 'mic_off';
        voiceStatus.style.display = 'flex';
        input.placeholder = 'Listening...';
    };
    recognition.onresult = event => {
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; i += 1) transcript += event.results[i][0].transcript;
        input.value = transcript;
        input.style.height = 'auto';
        input.style.height = `${Math.min(input.scrollHeight, 90)}px`;
        if (event.results[event.results.length - 1].isFinal) {
            setTimeout(() => {
                stopVoice();
                if (input.value.trim()) sendMessage();
            }, 300);
        }
    };
    recognition.onerror = () => stopVoice();
    recognition.onend = () => stopVoice();
    recognition.start();
}

function stopVoice() {
    isListening = false;
    if (recognition) {
        try { recognition.stop(); } catch {}
    }
    document.getElementById('voiceBtn').classList.remove('listening');
    document.getElementById('voiceIcon').textContent = 'mic';
    document.getElementById('voiceStatus').style.display = 'none';
    document.getElementById('chatInput').placeholder = 'Ask ProdigyAI anything...';
}

function speakResponse(text) {
    if (!window.speechSynthesis) return;
    const clean = text.replace(/[#*_`\[\]]/g, '').replace(/\n+/g, '. ');
    const short = clean.split('. ').slice(0, 3).join('. ');
    if (short.length < 10) return;
    const utterance = new SpeechSynthesisUtterance(short.substring(0, 300));
    utterance.rate = 1.05;
    utterance.volume = 0.8;
    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
}

function autoResize() {
    const textarea = document.getElementById('chatInput');
    textarea.addEventListener('input', () => {
        textarea.style.height = 'auto';
        textarea.style.height = `${Math.min(textarea.scrollHeight, 90)}px`;
    });
}

function handleKey(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function sendQuick(text) {
    document.getElementById('chatInput').value = text;
    sendMessage();
}

async function sendMessage() {
    const input = document.getElementById('chatInput');
    const text = input.value.trim();
    if (!text || isStreaming) return;
    const wasVoice = isListening || document.getElementById('voiceBtn').classList.contains('listening');
    addMessage(text, 'user');
    input.value = '';
    input.style.height = 'auto';
    showAgentStream(guessSteps(text));
    document.getElementById('chatStatus').textContent = 'Thinking...';
    document.getElementById('chatStatus').style.color = 'var(--warning)';
    resetAllAgents();
    activateAgent('coordinator', 'Analyzing request...');
    addActivityLog('coordinator', `User: "${text.substring(0, 80)}${text.length > 80 ? '...' : ''}"`);
    const typingId = showTyping();
    isStreaming = true;
    document.getElementById('sendBtn').disabled = true;
    try {
        const res = await fetch(API + '/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, session_id: chatSessionId }),
        });
        removeTyping(typingId);
        completeAgentStream();
        if (res.ok) {
            const data = await res.json();
            if (data.session_id) chatSessionId = data.session_id;
            await animateRealOrchestration(data.agents || [], data.tools || []);
            addMessage(data.response, 'bot');
            if (wasVoice) speakResponse(data.response);
            deactivateAgent('coordinator', 'Response delivered');
            setTimeout(refreshAll, 500);

            const lower = text.toLowerCase();
            if (lower.includes('what if') || lower.includes('day off') || lower.includes('take off') || lower.includes('simulate')) {
                const match = text.match(/(\d{4}-\d{2}-\d{2})/);
                const simDate = match ? match[1] : new Date().toISOString().split('T')[0];
                switchView('command');
                setTimeout(() => showTimeMachine(simDate), 500);
            }
        } else {
            deactivateAgent('coordinator', 'Error');
            addMessage('Error occurred. Please try again.', 'bot');
        }
    } catch {
        removeTyping(typingId);
        completeAgentStream();
        deactivateAgent('coordinator', 'Connection failed');
        addMessage('Cannot reach server.', 'bot');
    }
    document.getElementById('chatStatus').textContent = 'Ready';
    document.getElementById('chatStatus').style.color = '';
    isStreaming = false;
    document.getElementById('sendBtn').disabled = false;
}

async function animateRealOrchestration(agents, tools) {
    const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
    const toolAgentMap = {
        create_task: 'task_ops',
        list_tasks: 'task_ops',
        update_task: 'task_ops',
        update_task_priority: 'task_ops',
        create_google_task: 'task_ops',
        complete_google_task: 'task_ops',
        list_google_tasks: 'task_ops',
        create_event: 'calendar_ops',
        create_calendar_event: 'calendar_ops',
        list_calendar_events_today: 'calendar_ops',
        check_conflicts: 'calendar_ops',
        search_places: 'calendar_ops',
        get_directions: 'calendar_ops',
        create_note: 'knowledge_base',
        create_note_linked: 'knowledge_base',
        daily_briefing: 'insights',
        weekly_report: 'insights',
        workload_analysis: 'insights',
        simulate_day_off: 'insights',
        generate_report_summary: 'insights',
        list_priority_gmail_threads: 'gmail_ops',
        get_gmail_thread_summary: 'gmail_ops',
        create_gmail_draft: 'gmail_ops',
    };
    deactivateAgent('coordinator', 'Delegating...');
    const grouped = {};
    tools.filter(tool => tool !== 'transfer_to_agent').forEach(tool => {
        const agent = toolAgentMap[tool] || 'coordinator';
        if (!grouped[agent]) grouped[agent] = [];
        grouped[agent].push(tool);
    });
    for (const [agent, agentTools] of Object.entries(grouped)) {
        activateAgent(agent, 'Working...');
        for (const tool of agentTools) {
            activateAgent(agent, `${tool}...`);
            await wait(220);
        }
        deactivateAgent(agent, `${agentTools.length} tool${agentTools.length > 1 ? 's' : ''} called`);
    }
    for (const agent of agents) {
        if (agent !== 'coordinator' && !grouped[agent]) {
            activateAgent(agent, 'Delegated response...');
            await wait(220);
            deactivateAgent(agent, 'Done');
        }
    }
    activateAgent('coordinator', 'Synthesizing response...');
    await wait(300);
}

function addMessage(text, type) {
    const c = document.getElementById('chatMessages');
    const msg = document.createElement('div');
    msg.className = `message ${type}-message`;
    const avatar = type === 'bot' ? 'psychology' : 'person';
    const rendered = type === 'bot' ? marked.parse(text) : `<p>${esc(text)}</p>`;
    msg.innerHTML = `<div class="message-avatar"><span class="material-icons-round">${avatar}</span></div><div class="message-content">${rendered}</div>`;
    c.appendChild(msg);
    c.scrollTop = c.scrollHeight;
}

function showTyping() {
    const c = document.getElementById('chatMessages');
    const id = `t-${Date.now()}`;
    const msg = document.createElement('div');
    msg.className = 'message bot-message';
    msg.id = id;
    msg.innerHTML = `<div class="message-avatar"><span class="material-icons-round">psychology</span></div><div class="message-content"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div>`;
    c.appendChild(msg);
    c.scrollTop = c.scrollHeight;
    return id;
}

function removeTyping(id) {
    document.getElementById(id)?.remove();
}

function fireConfetti() {
    const cv = document.getElementById('confettiCanvas');
    const ctx = cv.getContext('2d');
    cv.width = window.innerWidth;
    cv.height = window.innerHeight;
    const particles = [];
    const colors = ['#6C5CE7', '#A29BFE', '#00B894', '#FDCB6E', '#FD79A8', '#74B9FF'];
    for (let i = 0; i < 80; i += 1) particles.push({ x: cv.width / 2, y: cv.height / 2, vx: (Math.random() - 0.5) * 15, vy: (Math.random() - 0.5) * 15 - 5, size: Math.random() * 6 + 3, color: colors[Math.floor(Math.random() * colors.length)], rotation: Math.random() * 360, rotationSpeed: (Math.random() - 0.5) * 10, life: 1 });
    let frame = 0;
    const animate = () => {
        ctx.clearRect(0, 0, cv.width, cv.height);
        let alive = false;
        particles.forEach(p => {
            if (p.life <= 0) return;
            alive = true;
            p.x += p.vx;
            p.y += p.vy;
            p.vy += 0.3;
            p.rotation += p.rotationSpeed;
            p.life -= 0.015;
            ctx.save();
            ctx.translate(p.x, p.y);
            ctx.rotate((p.rotation * Math.PI) / 180);
            ctx.globalAlpha = p.life;
            ctx.fillStyle = p.color;
            ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
            ctx.restore();
        });
        if (alive && frame < 200) {
            frame += 1;
            requestAnimationFrame(animate);
        } else {
            ctx.clearRect(0, 0, cv.width, cv.height);
        }
    };
    animate();
}

function fmtDate(value) {
    if (!value) return '';
    return new Date(`${value}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function fmtDateLong(value) {
    if (!value) return '';
    return new Date(`${value}T00:00:00`).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

function fmtTime(value) {
    if (!value) return '';
    const [h, m] = String(value).slice(0, 5).split(':');
    if (!h || !m) return value;
    const hr = parseInt(h, 10);
    return `${hr % 12 || 12}:${m} ${hr >= 12 ? 'PM' : 'AM'}`;
}

function esc(value) {
    if (!value) return '';
    const div = document.createElement('div');
    div.textContent = value;
    return div.innerHTML;
}

function getLocalDateInputValue() {
    const now = new Date();
    const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    return local.toISOString().split('T')[0];
}

function getRoundedTimeValue(offsetMinutes = 30) {
    const now = new Date();
    const rounded = new Date(now.getTime() + offsetMinutes * 60000);
    rounded.setMinutes(Math.ceil(rounded.getMinutes() / 15) * 15, 0, 0);
    return `${String(rounded.getHours()).padStart(2, '0')}:${String(rounded.getMinutes()).padStart(2, '0')}`;
}
