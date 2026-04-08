/* ═══════════════════════════════════════════
   ProdigyAI — AI-First Command Center
   ═══════════════════════════════════════════ */

const API = '';
let workloadChart = null;
let weekOffset = 0;
let isStreaming = false;
let cachedTasks = [];
let cachedEvents = [];
let notifications = [];
let chatSessionId = null; // Tracks conversation continuity within this tab
let briefingSessionId = null; // Tracks briefing session for execute plan

// ═══ INITIALIZATION ═══
document.addEventListener('DOMContentLoaded', () => {
    initSplash();
    setDate();
    createParticles();
    autoResize();
    // Network lines are CSS-drawn
});

// ═══ SPLASH SCREEN ═══
function initSplash() {
    const statuses = [
        'Connecting to Cloud SQL via MCP Toolbox...',
        'Google Maps MCP server connected...',
        'Google Search grounding active...',
        'BigQuery MCP analytics ready...',
        'Loading TaskOps Agent...',
        'Loading CalendarOps Agent...',
        'Loading KnowledgeBase Agent...',
        'Loading Insights Agent...',
        'Coordinator online. Analyzing your day...',
    ];
    let i = 0;
    const el = document.getElementById('splashStatus');
    const iv = setInterval(() => { i++; if (i < statuses.length) el.textContent = statuses[i]; else clearInterval(iv); }, 280);
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
    for (let i = 0; i < 40; i++) {
        const p = document.createElement('div');
        p.className = 'splash-particle';
        p.style.left = Math.random()*100+'%'; p.style.top = Math.random()*100+'%';
        p.style.animationDelay = Math.random()*6+'s'; p.style.animationDuration = (4+Math.random()*4)+'s';
        c.appendChild(p);
    }
}

function setDate() {
    const d = new Date();
    document.getElementById('currentDate').textContent = d.toLocaleDateString('en-US', { weekday:'long', year:'numeric', month:'long', day:'numeric' });
    const h = d.getHours();
    const greet = h < 12 ? 'Good Morning' : h < 17 ? 'Good Afternoon' : 'Good Evening';
    const el = document.getElementById('commandGreeting');
    if (el) el.textContent = `${greet} — Here's your optimized day`;
}

// ═══ MASTER REFRESH ═══
async function refreshAll() {
    const [tasks, events] = await Promise.all([fetchData('/api/tasks?status=all'), fetchData('/api/events/today')]);
    cachedTasks = tasks; cachedEvents = events;
    updateStats(tasks, events);
    renderKanban(tasks);
    loadWeekRadar();
    renderBattlePlan(tasks, events);
    generateSmartAlerts(tasks, events);
    generateCommandBriefing();
}

async function fetchData(url) {
    try { const r = await fetch(API+url); return await r.json(); } catch { return []; }
}

// ═══ PROACTIVE COMMAND BRIEFING ═══
async function generateCommandBriefing() {
    const body = document.getElementById('commandBody');
    const time = document.getElementById('commandTime');
    const actions = document.getElementById('commandActions');
    const badge = document.getElementById('commandBadge');

    body.innerHTML = `<div class="command-loading"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div><span>Insights Agent analyzing tasks, events, and workload...</span></div>`;
    actions.style.display = 'none';

    try {
        const res = await fetch(API+'/api/chat', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ message: `You are generating a proactive morning command briefing. Analyze my day and give me:

1. **STATUS**: One-line assessment (e.g., "Your day is packed but manageable" or "Warning: Thursday has conflicts")
2. **TOP 3 PRIORITIES**: Ranked by urgency and time-sensitivity. For each, give the task name and WHY it's the priority.
3. **SCHEDULE INSIGHT**: Look at my events and free slots. Tell me WHEN to do each priority task.
4. **RISK ALERT**: Any overdue items, conflicts, or overloaded days this week.
5. **MY RECOMMENDATION**: One specific, actionable suggestion to optimize the day.

Be opinionated. Don't just list — PRIORITIZE and RECOMMEND. Use markdown formatting. Be concise but strategic.` })
        });
        const data = await res.json();
        briefingSessionId = data.session_id; // Save for executeCommandPlan
        body.innerHTML = marked.parse(data.response);
        time.textContent = `Generated at ${new Date().toLocaleTimeString()} by Insights Agent`;
        actions.style.display = 'flex';

        // Set badge based on content
        const overdue = cachedTasks.filter(t => t.status !== 'done' && t.due_date && t.due_date < new Date().toISOString().split('T')[0]).length;
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
    addMessage('Execute the optimizations you suggested in the briefing. Move tasks if needed, adjust priorities, and confirm what you changed.', 'user');
    const typingId = showTyping();
    activateAgent('coordinator');
    showAgentStream(['Coordinator analyzing plan...', 'TaskOps executing task changes...', 'CalendarOps adjusting schedule...', 'Confirming changes...']);
    try {
        const res = await fetch(API+'/api/chat', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ message: 'Execute the optimizations from the briefing. Move any tasks that need rescheduling, update priorities where suggested, and confirm all changes made.', session_id: briefingSessionId })
        });
        removeTyping(typingId); completeAgentStream();
        const data = await res.json();
        addMessage(data.response, 'bot');
        fireConfetti();
        setTimeout(refreshAll, 500);
    } catch { removeTyping(typingId); completeAgentStream(); addMessage('Failed to execute plan.', 'bot'); }
}

function modifyCommandPlan() {
    toggleChat();
    document.getElementById('chatInput').value = 'I want to modify the plan: ';
    document.getElementById('chatInput').focus();
}

function dismissCommand() {
    document.getElementById('commandActions').style.display = 'none';
}

// ═══ SMART ALERTS (Proactive Notifications) ═══
function generateSmartAlerts(tasks, events) {
    notifications = [];
    const overdue = tasks.filter(t => t.status !== 'done' && t.due_date && t.due_date < new Date().toISOString().split('T')[0]);
    overdue.forEach(t => {
        notifications.push({ icon: 'danger', iconName: 'warning', text: `<strong>${esc(t.title)}</strong> is overdue (due ${fmtDate(t.due_date)})`, time: 'Now' });
    });

    // Upcoming deadlines (tomorrow)
    const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate()+1);
    const tStr = tomorrow.toISOString().split('T')[0];
    tasks.filter(t => t.due_date === tStr && t.status !== 'done').forEach(t => {
        notifications.push({ icon: 'warn', iconName: 'schedule', text: `<strong>${esc(t.title)}</strong> is due tomorrow`, time: 'Soon' });
    });

    // No agenda notes for events
    events.forEach(e => {
        notifications.push({ icon: 'info', iconName: 'note_add', text: `<strong>${esc(e.title)}</strong> at ${fmtTime(e.start_time)} — want me to create prep notes?`, time: 'Tip' });
    });

    // Productivity nudge
    const done = tasks.filter(t => t.status === 'done').length;
    if (done > 0) {
        notifications.push({ icon: 'success', iconName: 'emoji_events', text: `You've completed <strong>${done} tasks</strong> — keep the momentum!`, time: 'Win' });
    }

    const dot = document.getElementById('notifDot');
    dot.classList.toggle('active', notifications.length > 0);
    document.getElementById('notifCount').textContent = notifications.length;
    renderNotifications();
}

function renderNotifications() {
    const list = document.getElementById('notifList');
    if (!notifications.length) { list.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">All clear!</div>'; return; }
    list.innerHTML = notifications.map(n => `
        <div class="notif-item">
            <div class="notif-item-icon ${n.icon}"><span class="material-icons-round">${n.iconName}</span></div>
            <div class="notif-item-text">${n.text}</div>
            <div class="notif-item-time">${n.time}</div>
        </div>
    `).join('');
}

function toggleNotifications() {
    document.getElementById('notifPanel').classList.toggle('open');
}
// Close notification panel when clicking outside
document.addEventListener('click', (e) => {
    const panel = document.getElementById('notifPanel');
    const btn = document.getElementById('notifBtn');
    if (panel && !panel.contains(e.target) && !btn.contains(e.target)) {
        panel.classList.remove('open');
    }
});

// ═══ BATTLE PLAN (Today's Optimized Timeline) ═══
function renderBattlePlan(tasks, events) {
    const c = document.getElementById('battleTimeline');
    const items = [];

    // Add events as time blocks
    events.forEach(e => {
        items.push({ type: 'event', time: e.start_time || '09:00', end: e.end_time, title: e.title, detail: `${e.attendees||''} ${e.location ? '@ '+e.location : ''}`, sortKey: e.start_time || '09:00' });
    });

    // Add high-priority tasks as suggested work blocks
    const pendingTasks = tasks.filter(t => t.status !== 'done' && t.due_date).sort((a,b) => {
        const prio = {urgent:0,high:1,medium:2,low:3};
        return (prio[a.priority]||3) - (prio[b.priority]||3);
    });
    pendingTasks.slice(0, 4).forEach((t, i) => {
        items.push({ type: 'task', time: '', title: t.title, detail: `${t.priority} priority · due ${fmtDate(t.due_date)}`, priority: t.priority, sortKey: '99'+i });
    });

    if (!items.length) { c.innerHTML = '<div class="timeline-empty">No events or tasks for today</div>'; return; }

    // Sort: events by time first, then tasks
    items.sort((a,b) => a.sortKey.localeCompare(b.sortKey));

    c.innerHTML = items.map(item => {
        if (item.type === 'event') {
            return `<div class="battle-block event-block">
                <div class="battle-time">${fmtTime(item.time)}</div>
                <div class="battle-info"><h4>${esc(item.title)}</h4><p>${esc(item.detail)}</p></div>
                <span class="battle-tag event">Event</span>
            </div>`;
        } else {
            return `<div class="battle-block task-block">
                <div class="battle-time"><span class="priority-badge priority-${item.priority}" style="font-size:0.6rem">${item.priority}</span></div>
                <div class="battle-info"><h4>${esc(item.title)}</h4><p>${esc(item.detail)}</p></div>
                <span class="battle-tag task">Task</span>
            </div>`;
        }
    }).join('');
}

// ═══ WEEK RADAR ═══
async function loadWeekRadar() {
    let data = [];
    try {
        const res = await fetch(API+'/api/insights/workload');
        data = await res.json();
    } catch { data = placeholderWorkload(); }
    renderRadarDays(data);
    renderWorkloadChart(data);
}

function renderRadarDays(data) {
    const c = document.getElementById('radarDays');
    const today = new Date().toISOString().split('T')[0];
    const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    c.innerHTML = data.map(d => {
        const dt = new Date(d.date+'T00:00:00');
        const load = (d.tasks_due||0) + (d.events_scheduled||0);
        const cls = load >= 5 ? 'load-heavy' : load >= 3 ? 'load-medium' : 'load-light';
        const isToday = d.date === today;
        return `<div class="radar-day ${isToday?'today':''}" title="${load} items">
            <div class="radar-day-name">${dayNames[dt.getDay()]}</div>
            <div class="radar-day-num">${dt.getDate()}</div>
            <div class="radar-day-load ${cls}">${load}</div>
        </div>`;
    }).join('');
}

// ═══ STATS ═══
function updateStats(tasks, events) {
    const pending = tasks.filter(t => t.status !== 'done').length;
    const overdue = tasks.filter(t => t.status !== 'done' && t.due_date && t.due_date < new Date().toISOString().split('T')[0]).length;
    const completed = tasks.filter(t => t.status === 'done').length;
    animateNum('statPending', pending); animateNum('statOverdue', overdue);
    animateNum('statEventsToday', events.length); animateNum('statCompleted', completed);
    document.getElementById('taskBadge').textContent = pending;
    if (overdue > 0) document.getElementById('statOverdueCard').classList.add('has-overdue');
    else document.getElementById('statOverdueCard').classList.remove('has-overdue');
}

function animateNum(id, target) {
    const el = document.getElementById(id);
    const start = parseInt(el.textContent)||0;
    const t0 = performance.now();
    function f(t) { const p = Math.min((t-t0)/800,1); el.textContent = Math.round(start+(target-start)*(1-Math.pow(1-p,4))); if(p<1) requestAnimationFrame(f); }
    requestAnimationFrame(f);
}

// ═══ KANBAN ═══
function renderKanban(tasks) {
    const t=tasks.filter(t=>t.status==='todo'), p=tasks.filter(t=>t.status==='in_progress'), d=tasks.filter(t=>t.status==='done');
    document.getElementById('todoCount').textContent=t.length; document.getElementById('progressCount').textContent=p.length; document.getElementById('doneCount').textContent=d.length;
    document.getElementById('kanbanTodo').innerHTML=t.map(kanbanCard).join('');
    document.getElementById('kanbanProgress').innerHTML=p.map(kanbanCard).join('');
    document.getElementById('kanbanDone').innerHTML=d.map(kanbanCard).join('');
}

function kanbanCard(t) {
    const od = t.due_date && t.due_date < new Date().toISOString().split('T')[0] && t.status!=='done';
    return `<div class="kanban-card" onclick="cycleTask(${t.id},'${t.status}')">
        <div class="kanban-card-title">${esc(t.title)}</div>
        <div class="kanban-card-meta"><span class="priority-badge priority-${t.priority}">${t.priority}</span>
        <span class="kanban-card-date" style="${od?'color:var(--danger)':''}">${t.due_date?fmtDate(t.due_date):'—'}</span></div>
        ${t.project?`<div class="kanban-card-project">${esc(t.project)}</div>`:''}
    </div>`;
}

async function cycleTask(id, status) {
    const next = {todo:'in_progress', in_progress:'done', done:'todo'};
    try {
        await fetch(API+`/api/tasks/${id}`, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({status:next[status]}) });
        if (next[status]==='done') fireConfetti();
        // Refresh everything — dashboard + whichever view is active
        await refreshAll();
        loadTasksView(getCurrentTaskFilter());
    } catch {}
}

function getCurrentTaskFilter() {
    const btn = document.querySelector('.filter-btn.active');
    if (!btn) return 'all';
    const text = btn.textContent.trim();
    const map = {'All':'all','To Do':'todo','In Progress':'in_progress','Done':'done'};
    return map[text] || 'all';
}

// ═══ TIME MACHINE — What-If Visual Simulator ═══
async function showTimeMachine(targetDate) {
    const tm = document.getElementById('timeMachine');
    tm.style.display = 'block';
    // Scroll the view container to top so Time Machine is visible
    const view = document.getElementById('view-command');
    if (view) view.scrollTop = 0;
    tm.scrollIntoView({ behavior: 'smooth', block: 'start' });

    document.getElementById('tmSubtitle').textContent = `Simulating day off: ${targetDate}`;
    document.getElementById('tmWeekBefore').innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem">Loading...</div>';
    document.getElementById('tmWeekAfter').innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem">Calculating...</div>';
    document.getElementById('tmMoves').innerHTML = '';

    try {
        const res = await fetch(`${API}/api/simulate/${targetDate}`);
        const data = await res.json();
        renderTimeMachine(data);
    } catch (e) {
        document.getElementById('tmSubtitle').textContent = 'Simulation failed';
    }
}

function renderTimeMachine(data) {
    const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    const maxLoad = Math.max(
        ...data.workload_before.map(d => d.tasks + d.events),
        ...data.workload_after.map(d => d.tasks + d.events),
        1
    );

    // Update header
    const targetPretty = new Date(data.target_date + 'T00:00:00').toLocaleDateString('en-US', {weekday:'long', month:'short', day:'numeric'});
    document.getElementById('tmSubtitle').textContent = `What if you take ${targetPretty} off?`;
    document.getElementById('tmImpactText').textContent = `${data.total_affected} item${data.total_affected !== 1 ? 's' : ''} affected`;

    // Helper to render a day row
    function renderDayRow(d, isTarget, isAfter, beforeTotal) {
        const dt = new Date(d.date + 'T00:00:00');
        const total = d.tasks + d.events;
        const grew = isAfter && total > (beforeTotal || 0);
        const shrunk = isAfter && isTarget && total === 0;
        const pct = total > 0 ? Math.max((total / maxLoad) * 100, 8) : 0;

        let cls = 'tm-day-row';
        if (isTarget) cls += ' target-day';
        if (grew) cls += ' highlighted';
        if (total >= 5) cls += ' overloaded';

        let fillCls, fillContent, barInner;
        if (shrunk) {
            // Day off — show strikethrough "DAY OFF" badge
            barInner = `<div class="tm-day-off">DAY OFF</div>`;
        } else if (total === 0) {
            barInner = `<div class="tm-day-fill tm-fill-empty" style="width:3%"></div>`;
        } else {
            fillCls = grew ? 'tm-fill-added' : total >= 5 ? 'tm-fill-heavy' : 'tm-fill-normal';
            barInner = `<div class="tm-day-fill ${fillCls}" style="width:${pct}%">${total}</div>`;
        }

        const countStyle = grew ? 'color:var(--warning);font-weight:800' : shrunk ? 'color:var(--success)' : '';
        const countText = shrunk ? '0' : grew ? `${total} ↑` : `${total}`;

        return `<div class="${cls}">
            <span class="tm-day-name">${dayNames[dt.getDay()]}</span>
            <span class="tm-day-date">${d.date.slice(5)}</span>
            <div class="tm-day-bar">${barInner}</div>
            <span class="tm-day-count" style="${countStyle}">${countText}</span>
        </div>`;
    }

    // Render BEFORE
    document.getElementById('tmWeekBefore').innerHTML = data.workload_before.map(d =>
        renderDayRow(d, d.date === data.target_date, false, 0)
    ).join('');

    // Render AFTER (with animation delay for drama)
    setTimeout(() => {
        document.getElementById('tmWeekAfter').innerHTML = data.workload_after.map(d => {
            const beforeDay = data.workload_before.find(b => b.date === d.date);
            const beforeTotal = beforeDay ? beforeDay.tasks + beforeDay.events : 0;
            return renderDayRow(d, d.date === data.target_date, true, beforeTotal);
        }).join('');
    }, 600);

    // Render moves
    setTimeout(() => {
        document.getElementById('tmMoves').innerHTML = data.moves.map(m => {
            const fromDate = m.from_date.slice(5);
            const toDate = m.to_date.slice(5);
            const typeCls = m.type === 'event' ? 'event' : 'task';
            return `<div class="tm-move-item">
                <span class="tm-move-type ${typeCls}">${m.type}</span>
                <span class="tm-move-title">${esc(m.title)}</span>
                <span class="priority-badge priority-${m.priority}" style="font-size:0.55rem">${m.priority}</span>
                <span class="tm-move-arrow">${fromDate} <span class="material-icons-round">east</span> ${toDate}</span>
            </div>`;
        }).join('');
    }, 800);
}

function closeTimeMachine() {
    document.getElementById('timeMachine').style.display = 'none';
}

async function executeTimeMachinePlan() {
    // Send to chat to execute
    document.getElementById('chatInput').value = 'Execute the rescue plan from the what-if simulation. Move the affected tasks and events to their suggested new dates.';
    sendMessage();
    closeTimeMachine();
    fireConfetti();
}

// ═══ CHARTS ═══
function placeholderWorkload() {
    const d=[]; for(let i=0;i<7;i++){const dt=new Date();dt.setDate(dt.getDate()+i);d.push({date:dt.toISOString().split('T')[0],tasks_due:Math.floor(Math.random()*4),events_scheduled:Math.floor(Math.random()*3)});} return d;
}

function renderWorkloadChart(data) {
    const ctx = document.getElementById('workloadChart').getContext('2d');
    if (workloadChart) workloadChart.destroy();
    const labels = data.map(d => { const dt=new Date(d.date+'T00:00:00'); return dt.toLocaleDateString('en-US',{weekday:'short',day:'numeric'}); });
    workloadChart = new Chart(ctx, {
        type:'bar', data:{labels, datasets:[
            {label:'Tasks',data:data.map(d=>d.tasks_due),backgroundColor:'rgba(108,92,231,0.5)',borderColor:'rgba(108,92,231,1)',borderWidth:1,borderRadius:6},
            {label:'Events',data:data.map(d=>d.events_scheduled),backgroundColor:'rgba(116,185,255,0.5)',borderColor:'rgba(116,185,255,1)',borderWidth:1,borderRadius:6}
        ]}, options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#9898B8',font:{size:10}}}},
        scales:{x:{grid:{color:'rgba(255,255,255,0.03)'},ticks:{color:'#5E5E80',font:{size:9}}},y:{grid:{color:'rgba(255,255,255,0.03)'},ticks:{color:'#5E5E80',stepSize:1},beginAtZero:true}}}
    });
}

// ═══ VIEWS ═══
function switchView(v) {
    document.querySelectorAll('.view').forEach(el=>el.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
    document.getElementById(`view-${v}`).classList.add('active');
    document.querySelector(`[data-view="${v}"]`).classList.add('active');
    const titles = {command:'Command Center',tasks:'Tasks',calendar:'Calendar',notes:'Notes',agents:'Agent Network'};
    document.getElementById('viewTitle').textContent = titles[v]||v;
    if(v==='tasks') loadTasksView();
    if(v==='calendar') loadCalendarView();
    if(v==='notes') loadNotesView();
    // agent network lines are CSS-drawn, no action needed
}
function toggleSidebar() { document.getElementById('sidebar').classList.toggle('open'); }
function toggleChat() { document.body.classList.toggle('chat-open'); if(document.body.classList.contains('chat-open')) document.getElementById('chatInput').focus(); }

// Tasks View
async function loadTasksView(f='all') { try{const r=await fetch(API+`/api/tasks?status=${f}`);renderTaskList(await r.json());}catch{} }
function filterTasks(s,btn) { document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active')); btn.classList.add('active'); loadTasksView(s); }
function renderTaskList(tasks) {
    const c=document.getElementById('taskListView');
    if(!tasks.length){c.innerHTML='<div class="timeline-empty">No tasks found</div>';return;}
    c.innerHTML=tasks.map(t=>{
        const od=t.due_date&&t.due_date < new Date().toISOString().split('T')[0]&&t.status!=='done';
        return `<div class="task-item"><div class="task-check ${t.status==='done'?'checked':''}" onclick="cycleTask(${t.id},'${t.status}')"></div>
        <div class="task-info"><div class="task-title ${t.status==='done'?'completed':''}">${esc(t.title)}</div>
        <div class="task-meta"><span class="priority-badge priority-${t.priority}">${t.priority}</span>
        <span style="${od?'color:var(--danger)':''}"><span class="material-icons-round">event</span>${t.due_date?fmtDate(t.due_date):'—'}</span>
        ${t.project?`<span><span class="material-icons-round">folder</span>${esc(t.project)}</span>`:''}</div></div></div>`;
    }).join('');
}

// Calendar View
async function loadCalendarView() {
    const start=getWeekStart(weekOffset), end=new Date(start); end.setDate(end.getDate()+6);
    document.getElementById('calendarWeekLabel').textContent=`${start.toLocaleDateString('en-US',{month:'short',day:'numeric'})} — ${end.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})}`;
    const days=[]; for(let i=0;i<7;i++){const d=new Date(start);d.setDate(d.getDate()+i);days.push(d);}
    let events=[]; try{const r=await fetch(API+`/api/events/range?start=${start.toISOString().split('T')[0]}&end=${end.toISOString().split('T')[0]}`);events=await r.json();}catch{}
    const today=new Date().toISOString().split('T')[0], dn=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    document.getElementById('calendarGrid').innerHTML=days.map(d=>{
        const ds=d.toISOString().split('T')[0], de=events.filter(e=>e.event_date===ds);
        return `<div class="calendar-day ${ds===today?'today':''}"><div class="calendar-day-header">${dn[d.getDay()]}</div><div class="calendar-day-number">${d.getDate()}</div>
        ${de.map(e=>`<div class="calendar-event"><div class="calendar-event-time">${fmtTime(e.start_time)}</div><div class="calendar-event-title">${esc(e.title)}</div></div>`).join('')}</div>`;
    }).join('');
}
function changeWeek(d){weekOffset+=d;loadCalendarView();}
function getWeekStart(o){const n=new Date(),d=n.getDay(),diff=n.getDate()-d+(d===0?-6:1),m=new Date(n);m.setDate(diff+o*7);m.setHours(0,0,0,0);return m;}

// Notes View
async function loadNotesView() { try{const r=await fetch(API+'/api/notes');renderNotes(await r.json());}catch{} }
function renderNotes(notes) {
    const c=document.getElementById('notesGrid');
    if(!notes.length){c.innerHTML='<div class="timeline-empty">No notes yet. Ask ProdigyAI to create one!</div>';return;}
    c.innerHTML=notes.map(n=>`<div class="note-card"><div class="note-title">${esc(n.title)}</div>
    <div class="note-content">${esc(n.content)}</div>
    <div class="note-tags">${(n.tags||'').split(',').filter(t=>t.trim()).map(t=>`<span class="note-tag">${esc(t.trim())}</span>`).join('')}</div>
    <div class="note-date">${n.created_at?new Date(n.created_at).toLocaleDateString():''}</div></div>`).join('');
}

// ═══ AGENT NETWORK ═══
// Network lines are now CSS-drawn, no JS needed

// ═══ LIVE AGENT ORCHESTRATION ═══
const NODE_MAP = {coordinator:'node-coordinator',task_ops:'node-taskops',calendar_ops:'node-calendarops',knowledge_base:'node-knowledge',insights:'node-insights'};
const MINI_MAP = {coordinator:'mini-coordinator',task_ops:'mini-taskops',calendar_ops:'mini-calendarops',knowledge_base:'mini-knowledge',insights:'mini-insights'};
const LINE_MAP = {task_ops:'line-taskops',calendar_ops:'line-calendarops',knowledge_base:'line-knowledge',insights:'line-insights'};
const STATUS_MAP = {coordinator:'status-coordinator',task_ops:'status-taskops',calendar_ops:'status-calendarops',knowledge_base:'status-knowledge',insights:'status-insights'};
const NAMES = {coordinator:'Coordinator',task_ops:'TaskOps',calendar_ops:'CalendarOps',knowledge_base:'Knowledge',insights:'Insights'};

function activateAgent(name, statusText) {
    const status = statusText || 'Processing...';

    // Light up node
    const nodeId = NODE_MAP[name];
    if (nodeId) {
        const n = document.getElementById(nodeId);
        if (n) { n.classList.add('active', 'working'); n.classList.remove('done'); }
    }

    // Light up connection line
    const lineId = LINE_MAP[name];
    if (lineId) {
        const l = document.getElementById(lineId);
        if (l) l.classList.add('active');
    }

    // Update live status text
    const statusId = STATUS_MAP[name];
    if (statusId) {
        const s = document.getElementById(statusId);
        if (s) s.textContent = status;
    }

    // Light up mini agent in sidebar
    const miniId = MINI_MAP[name];
    if (miniId) {
        const m = document.getElementById(miniId);
        if (m) m.classList.add('active');
    }

    addActivityLog(name, status);
}

function deactivateAgent(name, doneText) {
    const nodeId = NODE_MAP[name];
    if (nodeId) {
        const n = document.getElementById(nodeId);
        if (n) { n.classList.remove('active', 'working'); n.classList.add('done'); setTimeout(() => n.classList.remove('done'), 5000); }
    }
    const lineId = LINE_MAP[name];
    if (lineId) {
        const l = document.getElementById(lineId);
        if (l) l.classList.remove('active');
    }
    const statusId = STATUS_MAP[name];
    if (statusId) {
        const s = document.getElementById(statusId);
        if (s) s.textContent = doneText || 'Done';
    }
    const miniId = MINI_MAP[name];
    if (miniId) {
        const m = document.getElementById(miniId);
        if (m) setTimeout(() => m.classList.remove('active'), 2000);
    }
}

function resetAllAgents() {
    Object.keys(NODE_MAP).forEach(name => {
        const n = document.getElementById(NODE_MAP[name]);
        if (n) n.classList.remove('active', 'working', 'done');
        const lineId = LINE_MAP[name];
        if (lineId) { const l = document.getElementById(lineId); if (l) l.classList.remove('active'); }
        const statusId = STATUS_MAP[name];
        if (statusId) { const s = document.getElementById(statusId); if (s) s.textContent = name === 'coordinator' ? 'Idle' : 'Standby'; }
    });
}

// ═══ DEMO REPLAY — Choreographed orchestration visualization ═══
async function runDemoReplay() {
    resetAllAgents();
    const log = (agent, text) => { activateAgent(agent, text); };
    const done = (agent, text) => { deactivateAgent(agent, text); };
    const wait = ms => new Promise(r => setTimeout(r, ms));

    // Simulate: "Prepare for investor pitch next Thursday"
    addActivityLog('coordinator', '→ User: "Prepare for investor pitch next Thursday"');
    log('coordinator', 'Analyzing request...');
    await wait(1000);

    log('coordinator', 'Multi-step detected → delegating');
    addActivityLog('coordinator', 'Breaking into: schedule + tasks + research');
    await wait(800);

    // Step 1: CalendarOps
    log('calendar_ops', 'Checking conflicts...');
    addActivityLog('calendar_ops', 'Tool: check_conflicts(2026-04-09)');
    await wait(1200);
    addActivityLog('calendar_ops', 'Tool: create_event("Investor Pitch", Apr 9, 10:00)');
    log('calendar_ops', 'Creating event...');
    await wait(1000);
    done('calendar_ops', 'Event created ✓');
    addActivityLog('calendar_ops', '✓ Event scheduled: Apr 9, 10:00-11:00');
    await wait(600);

    // Step 2: TaskOps
    log('task_ops', 'Creating prep tasks...');
    const tasks = ['Prepare slides', 'Research investor', 'Rehearse pitch', 'Finalize Q&A'];
    for (const t of tasks) {
        addActivityLog('task_ops', `Tool: create_task("${t}")`);
        await wait(500);
    }
    done('task_ops', `${tasks.length} tasks created ✓`);
    addActivityLog('task_ops', `✓ ${tasks.length} tasks created with staggered due dates`);
    await wait(600);

    // Step 3: KnowledgeBase
    log('knowledge_base', 'Researching investor...');
    addActivityLog('knowledge_base', 'Generating research via Gemini knowledge...');
    await wait(1500);
    addActivityLog('knowledge_base', 'Tool: create_note("Investor Research Notes")');
    await wait(800);
    done('knowledge_base', 'Research note saved ✓');
    addActivityLog('knowledge_base', '✓ Research notes created with tags');
    await wait(600);

    // Step 4: Insights
    log('insights', 'Checking workload...');
    addActivityLog('insights', 'Tool: workload_analysis()');
    await wait(1000);
    done('insights', 'Week looks manageable ✓');
    addActivityLog('insights', '✓ Workload OK — no conflicts detected');
    await wait(600);

    // Coordinator synthesizes
    log('coordinator', 'Synthesizing response...');
    await wait(800);
    done('coordinator', 'Response delivered ✓');
    addActivityLog('coordinator', '✓ 4 agents used · 8 tools called · Response delivered');
    await wait(2000);

    // Reset to idle
    resetAllAgents();
}

function addActivityLog(agent, text) {
    const feed=document.getElementById('activityFeed'); if(!feed)return;
    const time=new Date().toLocaleTimeString('en-US',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});
    const cls=agent.replace('_','');
    const item=document.createElement('div'); item.className='activity-item';
    item.innerHTML=`<span class="activity-time">${time}</span><span class="activity-agent ${cls}">${NAMES[agent]||agent}</span><span class="activity-text">${text}</span>`;
    feed.appendChild(item); feed.scrollTop=feed.scrollHeight;
    while(feed.children.length>30)feed.removeChild(feed.firstChild);
}

// ═══ AGENT STREAM (Chat Pipeline) ═══
function showAgentStream(steps) {
    const s=document.getElementById('agentStream'), el=document.getElementById('streamSteps');
    s.style.display='block'; el.innerHTML='';
    steps.forEach((step,i)=>{setTimeout(()=>{
        const d=document.createElement('div');d.className='stream-step';
        d.innerHTML=`<div class="stream-step-icon running"><span class="material-icons-round" style="font-size:10px">sync</span></div><span class="stream-step-text active">${step}</span>`;
        el.appendChild(d);
        if(step.includes('TaskOps'))activateAgent('task_ops');
        if(step.includes('CalendarOps'))activateAgent('calendar_ops');
        if(step.includes('Knowledge'))activateAgent('knowledge_base');
        if(step.includes('Insights'))activateAgent('insights');
        if(step.includes('Coordinator'))activateAgent('coordinator');
    },i*400);});
}
function completeAgentStream() {
    document.getElementById('streamSteps').querySelectorAll('.stream-step').forEach(s=>{
        const i=s.querySelector('.stream-step-icon');i.className='stream-step-icon done';
        i.innerHTML='<span class="material-icons-round" style="font-size:10px">check</span>';
        s.querySelector('.stream-step-text').className='stream-step-text';
    });
    setTimeout(()=>{document.getElementById('agentStream').style.display='none';},2000);
}

function guessSteps(msg) {
    const m=msg.toLowerCase(), s=['Coordinator analyzing intent...'];
    if(m.includes('briefing')||m.includes('focus')||m.includes('what should')){s.push('TaskOps: Fetching overdue & priority tasks...','CalendarOps: Loading schedule...','Insights: Generating strategic analysis...');}
    else if(m.includes('prepare')||m.includes('pitch')||m.includes('launch')){s.push('CalendarOps: Checking conflicts + searching venues (Maps)...','TaskOps: Creating preparation tasks...','KnowledgeBase: Researching via Google Search...','Insights: Analyzing workload impact...');}
    else if(m.includes('what if')||m.includes('day off')||m.includes('simulate')){s.push('Insights: Running what-if simulation...','Insights: Generating rescue plan (Python)...');}
    else if(m.includes('schedule')||m.includes('meeting')||m.includes('venue')||m.includes('lunch')){s.push('CalendarOps: Finding free slots (Python)...','CalendarOps: Searching places (Google Maps)...','CalendarOps: Creating event...');}
    else if(m.includes('research')||m.includes('look up')||m.includes('search')){s.push('KnowledgeBase: Searching web (Google Search)...','KnowledgeBase: Saving notes...');}
    else if(m.includes('report')||m.includes('analytics')){s.push('Insights: Querying Cloud SQL...','Insights: Querying BigQuery trends...','Insights: Generating report (Python)...');}
    else if(m.includes('task')||m.includes('todo')||m.includes('overdue')){s.push('TaskOps: Processing...');}
    else if(m.includes('note')){s.push('KnowledgeBase: Processing...');}
    else{s.push('Routing to best agent...');}
    s.push('Coordinator synthesizing response...');
    return s;
}

// ═══ VOICE INPUT/OUTPUT ═══
let recognition = null;
let isListening = false;

function toggleVoice() {
    if (isListening) {
        stopVoice();
    } else {
        startVoice();
    }
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

    recognition.onresult = (event) => {
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
            transcript += event.results[i][0].transcript;
        }
        input.value = transcript;
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 90) + 'px';

        // If this is a final result, auto-send
        if (event.results[event.results.length - 1].isFinal) {
            setTimeout(() => {
                stopVoice();
                if (input.value.trim()) sendMessage();
            }, 300);
        }
    };

    recognition.onerror = (event) => {
        console.log('Voice error:', event.error);
        stopVoice();
        if (event.error === 'not-allowed') {
            addMessage('Microphone access denied. Please allow microphone access in your browser settings.', 'bot');
        }
    };

    recognition.onend = () => {
        stopVoice();
    };

    recognition.start();
}

function stopVoice() {
    isListening = false;
    if (recognition) {
        try { recognition.stop(); } catch {}
    }
    const voiceBtn = document.getElementById('voiceBtn');
    const voiceIcon = document.getElementById('voiceIcon');
    const voiceStatus = document.getElementById('voiceStatus');
    const input = document.getElementById('chatInput');

    voiceBtn.classList.remove('listening');
    voiceIcon.textContent = 'mic';
    voiceStatus.style.display = 'none';
    input.placeholder = 'Ask ProdigyAI anything...';
}

// Voice output — reads back key parts of AI responses
function speakResponse(text) {
    if (!window.speechSynthesis) return;
    // Extract first sentence or 150 chars for speech
    const clean = text.replace(/[#*_`\[\]]/g, '').replace(/\n+/g, '. ');
    const short = clean.split('. ').slice(0, 3).join('. ');
    if (short.length < 10) return;

    const utterance = new SpeechSynthesisUtterance(short.substring(0, 300));
    utterance.rate = 1.05;
    utterance.pitch = 1.0;
    utterance.volume = 0.8;
    // Pick a good voice
    const voices = speechSynthesis.getVoices();
    const preferred = voices.find(v => v.name.includes('Samantha') || v.name.includes('Google') || v.name.includes('English'));
    if (preferred) utterance.voice = preferred;

    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
}

// ═══ CHAT ═══
function autoResize(){const t=document.getElementById('chatInput');t.addEventListener('input',()=>{t.style.height='auto';t.style.height=Math.min(t.scrollHeight,90)+'px';});}
function handleKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage();}}
function sendQuick(t){document.getElementById('chatInput').value=t;sendMessage();}

async function sendMessage() {
    const input=document.getElementById('chatInput'), text=input.value.trim();
    if(!text||isStreaming) return;
    const wasVoice = isListening || document.getElementById('voiceBtn').classList.contains('listening');
    addMessage(text,'user'); input.value=''; input.style.height='auto';
    showAgentStream(guessSteps(text));
    document.getElementById('chatStatus').textContent='Thinking...';
    document.getElementById('chatStatus').style.color='var(--warning)';

    // Start orchestration visualization
    resetAllAgents();
    activateAgent('coordinator', 'Analyzing request...');
    addActivityLog('coordinator', `→ User: "${text.substring(0, 60)}${text.length > 60 ? '...' : ''}"`);

    const tid=showTyping(); isStreaming=true; document.getElementById('sendBtn').disabled=true;
    try {
        const res=await fetch(API+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,session_id:chatSessionId})});
        removeTyping(tid); completeAgentStream();
        if(res.ok){
            const data=await res.json();
            if(data.session_id) chatSessionId = data.session_id;

            // Animate the real agent activity on the network
            await animateRealOrchestration(data.agents || [], data.tools || []);

            addMessage(data.response,'bot');
            // Voice output if input was voice
            if (wasVoice) speakResponse(data.response);
            deactivateAgent('coordinator', 'Response delivered ✓');
            setTimeout(refreshAll,500);

            // Auto-trigger Time Machine for what-if queries
            const msgLower = text.toLowerCase();
            if (msgLower.includes('what if') || msgLower.includes('day off') || msgLower.includes('take off') || msgLower.includes('simulate')) {
                // Extract date from the query
                const dateMatch = text.match(/(\d{4}-\d{2}-\d{2})/);
                let simDate;
                if (dateMatch) {
                    simDate = dateMatch[1];
                } else if (msgLower.includes('today')) {
                    simDate = new Date().toISOString().split('T')[0];
                } else if (msgLower.includes('tomorrow')) {
                    const d = new Date(); d.setDate(d.getDate()+1);
                    simDate = d.toISOString().split('T')[0];
                } else {
                    // Match any day name
                    const dayMap = {sunday:0, monday:1, tuesday:2, wednesday:3, thursday:4, friday:5, saturday:6};
                    let found = false;
                    for (const [name, targetDay] of Object.entries(dayMap)) {
                        if (msgLower.includes(name)) {
                            const d = new Date();
                            let diff = targetDay - d.getDay();
                            if (diff <= 0) diff += 7; // always go to NEXT occurrence
                            d.setDate(d.getDate() + diff);
                            simDate = d.toISOString().split('T')[0];
                            found = true;
                            break;
                        }
                    }
                    if (!found) simDate = new Date().toISOString().split('T')[0];
                }
                // Switch to command center and show Time Machine
                switchView('command');
                setTimeout(() => showTimeMachine(simDate), 500);
            }
        } else {
            deactivateAgent('coordinator', 'Error');
            addMessage('Error occurred. Please try again.','bot');
        }
    } catch {
        removeTyping(tid); completeAgentStream();
        deactivateAgent('coordinator', 'Connection failed');
        addMessage('Cannot reach server.','bot');
    }
    document.getElementById('chatStatus').textContent='Ready';
    document.getElementById('chatStatus').style.color='';
    isStreaming=false; document.getElementById('sendBtn').disabled=false;
}

// Animate the REAL agents and tools returned by the server
async function animateRealOrchestration(agents, tools) {
    const wait = ms => new Promise(r => setTimeout(r, ms));
    const toolNames = tools.filter(t => t !== 'transfer_to_agent');

    // Map tools to agents for visualization
    const toolAgentMap = {
        create_task: 'task_ops', list_tasks: 'task_ops', update_task: 'task_ops', delete_task: 'task_ops',
        tasks_by_priority: 'task_ops', overdue_tasks: 'task_ops', update_task_priority: 'task_ops',
        create_event: 'calendar_ops', list_events: 'calendar_ops', upcoming_events: 'calendar_ops',
        check_conflicts: 'calendar_ops', search_places: 'calendar_ops', get_directions: 'calendar_ops',
        calculate_free_slots: 'calendar_ops', smart_reschedule: 'insights',
        create_note: 'knowledge_base', create_note_linked: 'knowledge_base',
        search_notes: 'knowledge_base', list_notes: 'knowledge_base',
        daily_briefing: 'insights', weekly_report: 'insights', workload_analysis: 'insights',
        simulate_day_off: 'insights', generate_report_summary: 'insights', send_email_draft: 'insights',
    };

    // Group tools by agent
    const agentTools = {};
    for (const tool of toolNames) {
        const agent = toolAgentMap[tool] || 'coordinator';
        if (!agentTools[agent]) agentTools[agent] = [];
        agentTools[agent].push(tool);
    }

    // Animate each agent sequentially
    deactivateAgent('coordinator', 'Delegating...');
    for (const [agent, aTools] of Object.entries(agentTools)) {
        activateAgent(agent, `Calling ${aTools[0]}...`);
        for (const tool of aTools) {
            addActivityLog(agent, `Tool: ${tool}()`);
            activateAgent(agent, `${tool}...`);
            await wait(300);
        }
        deactivateAgent(agent, `${aTools.length} tool${aTools.length>1?'s':''} called ✓`);
        await wait(200);
    }
    activateAgent('coordinator', 'Synthesizing response...');
    await wait(300);
}

function addMessage(text,type) {
    const c=document.getElementById('chatMessages'), msg=document.createElement('div');
    msg.className=`message ${type}-message`;
    const av=type==='bot'?'psychology':'person', rendered=type==='bot'?marked.parse(text):`<p>${esc(text)}</p>`;
    msg.innerHTML=`<div class="message-avatar"><span class="material-icons-round">${av}</span></div><div class="message-content">${rendered}</div>`;
    c.appendChild(msg); c.scrollTop=c.scrollHeight;
}
function showTyping(){const c=document.getElementById('chatMessages'),id='t-'+Date.now(),m=document.createElement('div');m.className='message bot-message';m.id=id;
m.innerHTML=`<div class="message-avatar"><span class="material-icons-round">psychology</span></div><div class="message-content"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div>`;
c.appendChild(m);c.scrollTop=c.scrollHeight;return id;}
function removeTyping(id){const e=document.getElementById(id);if(e)e.remove();}

// ═══ CONFETTI ═══
function fireConfetti(){const cv=document.getElementById('confettiCanvas'),ctx=cv.getContext('2d');cv.width=window.innerWidth;cv.height=window.innerHeight;
const ps=[],cols=['#6C5CE7','#A29BFE','#00B894','#FDCB6E','#FD79A8','#74B9FF'];
for(let i=0;i<80;i++)ps.push({x:cv.width/2,y:cv.height/2,vx:(Math.random()-.5)*15,vy:(Math.random()-.5)*15-5,sz:Math.random()*6+3,c:cols[Math.floor(Math.random()*cols.length)],r:Math.random()*360,rs:(Math.random()-.5)*10,l:1});
let fr=0;function anim(){ctx.clearRect(0,0,cv.width,cv.height);let alive=false;ps.forEach(p=>{if(p.l<=0)return;alive=true;p.x+=p.vx;p.y+=p.vy;p.vy+=.3;p.r+=p.rs;p.l-=.015;
ctx.save();ctx.translate(p.x,p.y);ctx.rotate(p.r*Math.PI/180);ctx.globalAlpha=p.l;ctx.fillStyle=p.c;ctx.fillRect(-p.sz/2,-p.sz/2,p.sz,p.sz*.6);ctx.restore();});
if(alive&&fr<200){fr++;requestAnimationFrame(anim);}else ctx.clearRect(0,0,cv.width,cv.height);}anim();}

// ═══ UTILITIES ═══
function fmtDate(s){if(!s)return'';const d=new Date(s+'T00:00:00');return d.toLocaleDateString('en-US',{month:'short',day:'numeric'});}
function fmtTime(s){if(!s)return'';const[h,m]=s.split(':');const hr=parseInt(h);return`${hr%12||12}:${m} ${hr>=12?'PM':'AM'}`;}
function esc(s){if(!s)return'';const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
