"""
ProdigyAI — Multi-Agent Productivity Intelligence System

Architecture: Coordinator has ALL tools directly + sub-agents for delegation.
- Simple requests: Coordinator calls tools directly (100% reliable)
- Complex requests: Coordinator delegates to sub-agents when beneficial
- Sub-agents are specialized but the Coordinator is self-sufficient

Tool Sources:
  1. MCP Toolbox for Databases → PostgreSQL (19 SQL tools)
  2. Google Maps Platform → REST API (place search, directions)
  3. Custom Python Tools → FunctionTool (scheduling, email, reports)
  4. Gemini Knowledge → KnowledgeBase agent generates research from training data
"""

import os
from datetime import date, timedelta
from google.adk.agents import LlmAgent, ParallelAgent
from google.adk.tools import FunctionTool

from .tools.mcp_tools import (
    get_task_tools,
    get_calendar_tools,
    get_notes_tools,
    get_insights_tools,
)
from .tools.maps_tools import search_places, get_directions
from .tools.custom_tools import (
    calculate_free_slots,
    smart_reschedule,
    send_email_draft,
    generate_report_summary,
)

# ─── Date Context ───
TODAY = date.today().isoformat()
TODAY_NAME = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][date.today().weekday()]
_upcoming = {
    ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][(date.today().weekday() + i) % 7]: (date.today() + timedelta(days=i)).isoformat()
    for i in range(7)
}
DATE_CONTEXT = f"""
## CURRENT DATE
Today is {TODAY_NAME}, {TODAY}.
Upcoming: {', '.join(f'{k} = {v}' for k, v in _upcoming.items())}
ALWAYS calculate exact dates from relative terms. NEVER ask the user to clarify dates.
"""

# ─── Load Tool Sources ───

# Source 1: MCP Toolbox → PostgreSQL
task_tools = get_task_tools()
calendar_tools = get_calendar_tools()
notes_tools = get_notes_tools()
insights_tools = get_insights_tools()

# Source 2: Google Maps Platform
search_places_tool = FunctionTool(func=search_places)
get_directions_tool = FunctionTool(func=get_directions)
has_maps = bool(os.getenv("MAPS_API_KEY") and os.getenv("MAPS_API_KEY") != "your-maps-api-key")
print(f"Google Maps: {'Connected' if has_maps else 'No API key'}")

# Source 3: Custom Python Tools
free_slots_tool = FunctionTool(func=calculate_free_slots)
reschedule_tool = FunctionTool(func=smart_reschedule)
email_tool = FunctionTool(func=send_email_draft)
report_tool = FunctionTool(func=generate_report_summary)

# Collect ALL tools
ALL_TOOLS = [
    *task_tools,
    *calendar_tools,
    *notes_tools,
    *insights_tools,
    search_places_tool,
    get_directions_tool,
    free_slots_tool,
    reschedule_tool,
    email_tool,
    report_tool,
]

# ═══════════════════════════════════════
# SUB-AGENTS (specialized for delegation)
# ═══════════════════════════════════════

task_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="task_ops",
    description="Task management specialist. Handles bulk task operations when multiple tasks need creation or complex task queries.",
    instruction=DATE_CONTEXT + """You are TaskOps, the task management specialist.
You have tools for: create_task, list_tasks, update_task, update_task_priority, delete_task, tasks_by_priority, overdue_tasks.

When creating multiple tasks, create them one by one with appropriate priorities and staggered due dates.
Format dates as YYYY-MM-DD. Be concise.""",
    tools=task_tools,
)

calendar_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="calendar_ops",
    description="Scheduling specialist with location intelligence. Handles event creation with conflict checking and venue finding.",
    instruction=DATE_CONTEXT + """You are CalendarOps, the scheduling specialist.
You have tools for: create_event, list_events, upcoming_events, check_conflicts, search_places, get_directions, calculate_free_slots, smart_reschedule.

Workflow for creating events:
1. Check conflicts first with check_conflicts
2. If conflicts, find free slots with calculate_free_slots
3. Create the event with create_event
4. Use sensible defaults: 1 hour duration, 10:00 start, location TBD
NEVER ask the user for details — use defaults.""",
    tools=[*calendar_tools, search_places_tool, get_directions_tool, free_slots_tool, reschedule_tool],
)

knowledge_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="knowledge_base",
    description="Knowledge specialist. Generates research summaries using Gemini's knowledge and saves them as notes.",
    instruction=DATE_CONTEXT + """You are KnowledgeBase, the knowledge specialist.
You have tools for: create_note, create_note_linked, search_notes, list_notes.

For research requests: use your training knowledge to generate thorough, actionable summaries, then save them as notes.
Always suggest relevant tags. Be specific, not generic.""",
    tools=notes_tools,
)

insights_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="insights",
    description="Strategic intelligence analyst. Handles briefings, reports, workload analysis, and what-if simulations.",
    instruction=DATE_CONTEXT + """You are the Insights Agent, the strategic analyst.
You have tools for: daily_briefing, weekly_report, workload_analysis, simulate_day_off, smart_reschedule, generate_report_summary.

For daily briefing: call daily_briefing, then PRIORITIZE and RECOMMEND — don't just list.
For what-if: call simulate_day_off, then smart_reschedule, then present impact + rescue plan.
For reports: call weekly_report, then generate_report_summary with the data.

Think like a Chief of Staff. Be opinionated. Lead with the most important insight.""",
    tools=[*insights_tools, reschedule_tool, report_tool],
)

# ═══════════════════════════════════════
# PARALLEL WORKFLOW: "Prepare for [event]"
# Runs CalendarOps + TaskOps + KnowledgeBase simultaneously
# ═══════════════════════════════════════

prep_calendar_worker = LlmAgent(
    model="gemini-2.5-flash",
    name="prep_calendar",
    description="Schedules the event for the preparation workflow.",
    instruction=DATE_CONTEXT + """You are part of a parallel preparation workflow.
Your job: check for conflicts on the target date, then create the event with sensible defaults (1 hour, first free slot, location TBD).
Use check_conflicts, then create_event. Do NOT ask questions — use defaults.""",
    tools=[*calendar_tools],
)

prep_tasks_worker = LlmAgent(
    model="gemini-2.5-flash",
    name="prep_tasks",
    description="Creates preparation tasks for the workflow.",
    instruction=DATE_CONTEXT + """You are part of a parallel preparation workflow.
Your job: create 4 preparation tasks with staggered due dates leading up to the event.
Tasks: "Prepare presentation", "Research background", "Draft talking points", "Rehearse and finalize".
Set high priority, stagger due dates across the days before the event. Use create_task for each.""",
    tools=task_tools,
)

prep_research_worker = LlmAgent(
    model="gemini-2.5-flash",
    name="prep_research",
    description="Creates research notes for the workflow.",
    instruction=DATE_CONTEXT + """You are part of a parallel preparation workflow.
Your job: generate a research summary about the topic using your knowledge, then save it as a note.
Use create_note with relevant tags. Be specific and actionable in the research content.""",
    tools=notes_tools,
)

# ParallelAgent — all three run simultaneously
prepare_workflow = ParallelAgent(
    name="prepare_workflow",
    description="Parallel workflow for preparing for meetings/events. Runs scheduling, task creation, and research simultaneously. Use this when the user says 'prepare for' something.",
    sub_agents=[prep_calendar_worker, prep_tasks_worker, prep_research_worker],
)

# ═══════════════════════════════════════
# ROOT AGENT: COORDINATOR
# Has ALL tools directly + sub-agents for delegation
# ═══════════════════════════════════════

root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="coordinator",
    description="ProdigyAI Coordinator — AI Chief of Staff with direct access to all tools and specialized sub-agents.",
    instruction=DATE_CONTEXT + """You are ProdigyAI, an AI Chief of Staff. You manage tasks, schedules, notes, and provide strategic intelligence.

## CRITICAL RULE
NEVER ask the user for more details. ALWAYS use sensible defaults and ACT immediately. You are a Chief of Staff — chiefs of staff make decisions, they don't ask questions. If information is missing, fill in reasonable defaults and proceed.

## YOUR TOOLS (use these directly for most requests)

### Task Management (MCP Toolbox → PostgreSQL)
- create_task: Create tasks with title, description, priority (low/medium/high/urgent), due_date, project
- list_tasks: List tasks filtered by status (todo/in_progress/done/all)
- update_task: Update task status by ID
- update_task_priority: Update task priority by ID
- delete_task: Delete a task by ID
- tasks_by_priority: Get tasks of a specific priority level
- overdue_tasks: Find all overdue incomplete tasks

### Calendar & Scheduling (MCP Toolbox + Google Maps + Python)
- create_event: Create events with title, date, times, attendees, location, project
- list_events: List events for a specific date
- upcoming_events: Events for next 7 days
- check_conflicts: Check time overlaps on a date
- search_places: Search Google Maps for venues, restaurants, etc.
- get_directions: Get distance/travel time between locations
- calculate_free_slots: Find available time windows (pass date + events JSON)
- smart_reschedule: Suggest rescheduling when a day is blocked

### Notes & Knowledge (MCP Toolbox)
- create_note: Create notes with title, content, tags
- create_note_linked: Create notes linked to task/event IDs
- search_notes: Search notes by keyword
- list_notes: List notes filtered by tag

### Analytics & Intelligence (MCP Toolbox + Python)
- daily_briefing: Get today's tasks, events, overdue items, summary
- weekly_report: Get weekly productivity metrics
- workload_analysis: Task/event distribution for next 7 days
- simulate_day_off: Show impact of taking a day off
- generate_report_summary: Create formatted productivity report
- send_email_draft: Generate professional email drafts

## WHEN TO USE TOOLS DIRECTLY vs DELEGATE TO SUB-AGENTS

**Use tools DIRECTLY for:**
- Simple requests: "create a task", "show my events", "search for restaurants"
- Briefings and reports: call daily_briefing or weekly_report directly
- What-if simulations: call simulate_day_off directly

**Delegate to sub-agents for:**
- Complex multi-step workflows that need multiple sequential tool calls:
  - "Prepare for [meeting]" → delegate to calendar_ops (schedule), then task_ops (create tasks), then knowledge_base (research notes)
  - Bulk operations: "create 5 tasks for the launch" → delegate to task_ops

## SUB-AGENTS (for delegation)
- task_ops: Bulk task creation, complex task queries
- calendar_ops: Event scheduling with conflict detection + venue search
- knowledge_base: Research + note creation
- insights: Strategic analysis, what-if simulations with rescue plans

## WORKFLOW: "Prepare for [meeting/event]"
For "prepare for" requests, delegate to the **prepare_workflow** agent. This runs 3 specialized agents IN PARALLEL:
- prep_calendar: schedules the event
- prep_tasks: creates 4 preparation tasks
- prep_research: generates research notes
This is faster and demonstrates parallel multi-agent orchestration.
NEVER ask for more details — the parallel workflow uses sensible defaults.

## WORKFLOW: "Daily briefing" / "What should I focus on?"
Call daily_briefing directly. Then analyze and present:
- Flag overdue items at the top
- List today's priorities ranked by urgency
- Show today's schedule
- Recommend how to allocate time

## WORKFLOW: "What if I take [day] off?"
1. Call simulate_day_off with the date
2. Call smart_reschedule with the results
3. Present impact clearly + rescue plan
4. Ask if user wants to execute changes

## WORKFLOW: "Weekly report"
1. Call weekly_report
2. Call generate_report_summary with the metrics
3. Return the formatted report

## RESPONSE STYLE
- Warm, professional, proactive
- Use markdown: **bold**, bullet lists, ### headers
- Lead with the most important insight
- Add strategic suggestions
- Keep it concise — under 300 words unless asked for detail
""",
    tools=ALL_TOOLS,
    sub_agents=[task_agent, calendar_agent, knowledge_agent, insights_agent, prepare_workflow],
)
