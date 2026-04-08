"""
ProdigyAI multi-agent system.

This version keeps the existing SQL-backed toolsets and layers Google
Workspace MCP capabilities behind local FunctionTools so chat can work with
Calendar, Gmail, and Google Tasks without hard-coupling to a third-party
server implementation.
"""

import os
from datetime import date, timedelta

from google.adk.agents import LlmAgent, ParallelAgent
from google.adk.tools import FunctionTool

from .tools.custom_tools import (
    calculate_free_slots,
    generate_report_summary,
    send_email_draft,
    smart_reschedule,
)
from .tools.google_workspace_tools import (
    get_workspace_calendar_tools,
    get_workspace_docs_tools,
    get_workspace_drive_tools,
    get_workspace_gmail_tools,
    get_workspace_task_tools,
)
from .tools.maps_tools import get_directions, search_places
from .tools.mcp_tools import (
    get_calendar_tools,
    get_insights_tools,
    get_notes_tools,
    get_task_tools,
)

TODAY = date.today().isoformat()
TODAY_NAME = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][
    date.today().weekday()
]
_upcoming = {
    ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][
        (date.today().weekday() + i) % 7
    ]: (date.today() + timedelta(days=i)).isoformat()
    for i in range(7)
}
DATE_CONTEXT = f"""
## CURRENT DATE
Today is {TODAY_NAME}, {TODAY}.
Upcoming: {', '.join(f'{k} = {v}' for k, v in _upcoming.items())}
ALWAYS calculate exact dates from relative terms. NEVER ask the user to clarify dates.
"""


def _safe_tool_load(loader, label):
    try:
        tools = loader()
        print(f"{label}: connected ({len(tools)} tools)")
        return tools
    except Exception as exc:
        print(f"{label}: unavailable ({exc})")
        return []


task_tools = _safe_tool_load(get_task_tools, "Task tools")
calendar_tools = _safe_tool_load(get_calendar_tools, "Calendar tools")
notes_tools = _safe_tool_load(get_notes_tools, "Notes tools")
insights_tools = _safe_tool_load(get_insights_tools, "Insights tools")

workspace_calendar_tools = get_workspace_calendar_tools()
workspace_task_tools = get_workspace_task_tools()
workspace_gmail_tools = get_workspace_gmail_tools()
workspace_drive_tools = get_workspace_drive_tools()
workspace_docs_tools = get_workspace_docs_tools()

search_places_tool = FunctionTool(func=search_places)
get_directions_tool = FunctionTool(func=get_directions)
has_maps = bool(os.getenv("MAPS_API_KEY") and os.getenv("MAPS_API_KEY") != "your-maps-api-key")
print(f"Google Maps: {'Connected' if has_maps else 'No API key'}")

free_slots_tool = FunctionTool(func=calculate_free_slots)
reschedule_tool = FunctionTool(func=smart_reschedule)
email_tool = FunctionTool(func=send_email_draft)
report_tool = FunctionTool(func=generate_report_summary)

ALL_TOOLS = [
    *task_tools,
    *calendar_tools,
    *notes_tools,
    *insights_tools,
    *workspace_calendar_tools,
    *workspace_task_tools,
    *workspace_gmail_tools,
    *workspace_drive_tools,
    *workspace_docs_tools,
    search_places_tool,
    get_directions_tool,
    free_slots_tool,
    reschedule_tool,
    email_tool,
    report_tool,
]

task_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="task_ops",
    description="Task management specialist for local planning tasks and Google Tasks follow-ups.",
    instruction=DATE_CONTEXT
    + """You are TaskOps, the task management specialist.
You have tools for: create_task, list_tasks, update_task, update_task_priority, delete_task, tasks_by_priority, overdue_tasks, list_google_tasks, create_google_task, complete_google_task.

Use Google Tasks tools for personal follow-up and action-item requests.
Use the SQL task tools for internal dashboard and project-planning requests.
When creating multiple tasks, create them one by one with appropriate priorities and staggered due dates.
Format dates as YYYY-MM-DD. Be concise.""",
    tools=[*task_tools, *workspace_task_tools],
)

calendar_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="calendar_ops",
    description="Scheduling specialist with Google Calendar, location intelligence, and conflict handling.",
    instruction=DATE_CONTEXT
    + """You are CalendarOps, the scheduling specialist.
You have tools for: create_event, list_events, upcoming_events, check_conflicts, list_calendar_events_today, safe_list_google_calendar_events, create_calendar_event, search_places, get_directions, calculate_free_slots, smart_reschedule.

Workflow for creating events:
1. Check conflicts first with check_conflicts when using the internal planner
2. Prefer create_calendar_event for user-facing scheduling on Google Calendar
3. If there are conflicts, find free slots with calculate_free_slots
4. Use sensible defaults: 1 hour duration, 10:00 start, location TBD
For user questions about "my meetings", "my calendar", "today", "tomorrow", or date ranges, prefer Google calendar tools first:
- use safe_list_google_calendar_events for ranges and relative dates
- use list_calendar_events_today only for strictly-today asks
NEVER ask the user for details; use defaults.""",
    tools=[*calendar_tools, *workspace_calendar_tools, search_places_tool, get_directions_tool, free_slots_tool, reschedule_tool],
)

knowledge_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="knowledge_base",
    description="Knowledge specialist. Searches Google Drive and Google Docs, generates research summaries, and saves notes.",
    instruction=DATE_CONTEXT
    + """You are KnowledgeBase, the knowledge specialist.
You have tools for: create_note, create_note_linked, search_notes, list_notes, safe_search_drive_files, safe_list_drive_files, safe_get_drive_file_metadata, safe_search_google_docs, safe_list_google_docs, safe_get_google_doc_content.

For research requests: first search Drive and Docs for existing related files (safe_search_drive_files + safe_search_google_docs), then use your training knowledge to generate actionable summaries, then save them as notes.
For "find files" or "search Drive" requests: use safe_search_drive_files with the user's query.
For "recent files" or "show my Drive" requests: use safe_list_drive_files.
For "search docs" or "find documents" requests: use safe_search_google_docs.
For "read/summarize this doc" requests: use safe_get_google_doc_content with the document ID.
Always suggest relevant tags when saving notes. Be specific, not generic.""",
    tools=[*notes_tools, *workspace_drive_tools, *workspace_docs_tools],
)

insights_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="insights",
    description="Strategic intelligence analyst for briefings, reports, workload analysis, and what-if simulations.",
    instruction=DATE_CONTEXT
    + """You are the Insights Agent, the strategic analyst.
You have tools for: daily_briefing, weekly_report, workload_analysis, simulate_day_off, smart_reschedule, generate_report_summary.

For daily briefing: call daily_briefing, then prioritize and recommend rather than just listing.
For what-if: call simulate_day_off, then smart_reschedule, then present impact plus rescue plan.
For reports: call weekly_report, then generate_report_summary with the data.

Think like a Chief of Staff. Be opinionated. Lead with the most important insight.""",
    tools=[*insights_tools, reschedule_tool, report_tool],
)

gmail_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="gmail_ops",
    description="Inbox specialist for Gmail triage, summaries, draft replies, and task extraction.",
    instruction=DATE_CONTEXT
    + """You are GmailOps, the inbox specialist.
You have tools for: list_priority_gmail_threads, get_gmail_thread_summary, create_gmail_draft, create_google_task.

Workflow:
1. For inbox triage, begin with list_priority_gmail_threads
2. For a specific email, use get_gmail_thread_summary
3. Draft replies instead of sending
4. When the user asks for follow-up, create a Google Task with a concise action title

Never send email. Draft only.""",
    tools=[*workspace_gmail_tools, *workspace_task_tools],
)

prep_calendar_worker = LlmAgent(
    model="gemini-2.5-flash",
    name="prep_calendar",
    description="Schedules the event for the preparation workflow.",
    instruction=DATE_CONTEXT
    + """You are part of a parallel preparation workflow.
Your job: check for conflicts on the target date, then create the event with sensible defaults.
Prefer create_calendar_event for real calendar scheduling. Do not ask questions.""",
    tools=[*calendar_tools, *workspace_calendar_tools],
)

prep_tasks_worker = LlmAgent(
    model="gemini-2.5-flash",
    name="prep_tasks",
    description="Creates preparation tasks for the workflow.",
    instruction=DATE_CONTEXT
    + """You are part of a parallel preparation workflow.
Your job: create 4 preparation tasks with staggered due dates leading up to the event.
Tasks: "Prepare presentation", "Research background", "Draft talking points", "Rehearse and finalize".
Prefer Google Tasks for personal follow-up.""",
    tools=[*task_tools, *workspace_task_tools],
)

prep_research_worker = LlmAgent(
    model="gemini-2.5-flash",
    name="prep_research",
    description="Creates research notes for the workflow, optionally linking relevant Drive files.",
    instruction=DATE_CONTEXT
    + """You are part of a parallel preparation workflow.
Your job: search Drive and Google Docs for related files (safe_search_drive_files + safe_search_google_docs), then generate a research summary using your knowledge and save it as a note.
Use create_note with relevant tags. If files are found, mention their names in the note content. Be specific and actionable.""",
    tools=[*notes_tools, *workspace_drive_tools, *workspace_docs_tools],
)

prepare_workflow = ParallelAgent(
    name="prepare_workflow",
    description="Parallel workflow for preparing for meetings and events.",
    sub_agents=[prep_calendar_worker, prep_tasks_worker, prep_research_worker],
)

root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="coordinator",
    description="ProdigyAI Coordinator, an AI Chief of Staff with direct access to local and Google Workspace tools.",
    instruction=DATE_CONTEXT
    + """You are ProdigyAI, an AI Chief of Staff. You manage tasks, schedules, notes, inbox workflows, Drive files, and strategic intelligence.

## CRITICAL RULE
NEVER ask the user for more details. ALWAYS use sensible defaults and act immediately. If information is missing, fill in reasonable defaults and proceed.

## YOUR TOOLS

### Task Management
- create_task / list_tasks / update_task / update_task_priority / delete_task / tasks_by_priority / overdue_tasks
- list_google_tasks / create_google_task / complete_google_task

### Calendar & Scheduling
- create_event / list_events / upcoming_events / check_conflicts
- list_calendar_events_today / safe_list_google_calendar_events / create_calendar_event
- search_places / get_directions / calculate_free_slots / smart_reschedule

### Gmail & Inbox
- list_priority_gmail_threads / get_gmail_thread_summary / create_gmail_draft

### Notes & Knowledge
- create_note / create_note_linked / search_notes / list_notes

### Google Drive
- safe_search_drive_files / safe_list_drive_files / safe_get_drive_file_metadata

### Google Docs
- safe_search_google_docs / safe_list_google_docs / safe_get_google_doc_content

### Analytics & Intelligence
- daily_briefing / weekly_report / workload_analysis / simulate_day_off / generate_report_summary / send_email_draft

## DIRECT TOOL USE
Use tools directly for simple asks like:
- "show my schedule"
- "show my Google tasks"
- "summarize my inbox"
- "draft a reply"
- "create a task"
- "create an event"

For "my calendar / my meetings" queries, prefer Google calendar tools over local SQL calendar tools.
"Tomorrow" and date-range queries should use safe_list_google_calendar_events.

## DELEGATION
Delegate when the request spans multiple products or multiple tool calls:
- "Prepare for [meeting]" -> prepare_workflow
- "Summarize my inbox and create follow-up tasks" -> gmail_ops then task_ops
- "Schedule a meeting with prep tasks" -> calendar_ops then task_ops

## RESPONSE STYLE
- Warm, proactive, concise
- Use markdown
- Lead with the most important outcome
- Mention what was created or drafted
- Draft email only; never claim an email was sent
""",
    tools=ALL_TOOLS,
    sub_agents=[task_agent, calendar_agent, knowledge_agent, insights_agent, gmail_agent, prepare_workflow],
)
