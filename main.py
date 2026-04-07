"""
ProdigyAI FastAPI server.

Dashboard data is served from PostgreSQL. Chat uses ADK agents. Google
Workspace data is synced through a community MCP server wrapped by an internal
adapter and cached locally for the UI.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import date, timedelta

import dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from prodigy_ai.agent import root_agent
from prodigy_ai.db import (
    cache_gmail_threads,
    cache_google_calendar_events,
    cache_google_tasks,
    get_events_range as db_get_events_range,
    get_events_today as db_get_events_today,
    get_gmail_summary as db_get_gmail_summary,
    get_google_calendar_range as db_get_google_calendar_range,
    get_google_calendar_today as db_get_google_calendar_today,
    get_google_tasks as db_get_google_tasks,
    get_notes as db_get_notes,
    get_tasks as db_get_tasks,
    get_workload as db_get_workload,
    mark_google_task_complete as db_mark_google_task_complete,
    record_google_sync,
    simulate_day_off as db_simulate_day_off,
    update_task as db_update_task,
)
from prodigy_ai.tools.google_workspace_tools import (
    create_calendar_event,
    create_gmail_draft,
    create_google_task,
    list_calendar_events,
    get_gmail_thread_summary,
    get_workspace_status,
    list_calendar_events_today,
    list_google_tasks,
    list_priority_gmail_threads,
    complete_google_task,
)

dotenv.load_dotenv()

APP_NAME = "prodigy_ai"
USER_ID = "default_user"
session_service = InMemorySessionService()
runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)
_sessions = set()


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class TaskUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None


class GoogleEventCreateRequest(BaseModel):
    title: str
    event_date: str
    start_time: str = "10:00"
    end_time: str = "11:00"
    location: str = ""
    attendees: str = ""
    description: str = ""
    timezone: str = ""


class GoogleTaskCreateRequest(BaseModel):
    title: str
    notes: str = ""
    due_date: str = ""
    priority: str = "medium"
    thread_id: str = ""


class GmailTaskRequest(BaseModel):
    thread_id: str
    title: str | None = None
    notes: str = ""
    due_date: str = ""
    priority: str = "medium"


class GmailDraftRequest(BaseModel):
    thread_id: str
    to: str = ""
    subject: str = ""
    body: str = ""


async def get_or_create_session(sid: str | None = None) -> str:
    if sid and sid in _sessions:
        return sid
    new_id = sid or str(uuid.uuid4())
    await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=new_id)
    _sessions.add(new_id)
    return new_id


def _status_payload():
    status = get_workspace_status()
    return {
        "connected": status.get("connected", False),
        "state": status.get("status", "disconnected"),
        "message": status.get("message", ""),
    }


def _sync_google_workspace():
    status = get_workspace_status()
    if not status.get("connected"):
        record_google_sync("workspace", status=status.get("status", "disconnected"), error=status.get("message"))
        return {
            "status": _status_payload(),
            "calendar_events": 0,
            "tasks": 0,
            "threads": 0,
        }

    today = date.today()
    end = today + timedelta(days=6)
    calendar = {"events": []}
    tasks = {"tasks": []}
    gmail = {"threads": []}
    errors = []

    try:
        calendar = list_calendar_events(start_date=today.isoformat(), end_date=end.isoformat())
        cache_google_calendar_events(calendar.get("events", []))
    except Exception as exc:
        errors.append(f"calendar: {exc}")

    try:
        tasks = list_google_tasks()
        cache_google_tasks(tasks.get("tasks", []))
    except Exception as exc:
        errors.append(f"tasks: {exc}")

    try:
        gmail = list_priority_gmail_threads()
        cache_gmail_threads(gmail.get("threads", []))
    except Exception as exc:
        errors.append(f"gmail: {exc}")

    record_google_sync("workspace", status="connected" if not errors else "partial", error="; ".join(errors) or None)

    return {
        "status": _status_payload(),
        "calendar_events": len(calendar.get("events", [])),
        "tasks": len(tasks.get("tasks", [])),
        "threads": len(gmail.get("threads", [])),
        "warnings": errors,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    default_id = await get_or_create_session("default")
    print(f"ProdigyAI default session: {default_id}")
    yield


app = FastAPI(title="ProdigyAI", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_dashboard():
    return FileResponse("static/index.html")


@app.get("/api/tasks")
async def api_get_tasks(status: str = "all"):
    try:
        return JSONResponse(content=db_get_tasks(status))
    except Exception as exc:
        print(f"DB error (tasks): {exc}")
        return JSONResponse(content=[])


@app.put("/api/tasks/{task_id}")
async def api_update_task(task_id: int, update: TaskUpdate):
    try:
        result = db_update_task(task_id, status=update.status, priority=update.priority)
        return {"success": True, "result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/events/today")
async def api_get_events_today():
    try:
        return JSONResponse(content=db_get_events_today())
    except Exception as exc:
        print(f"DB error (events): {exc}")
        return JSONResponse(content=[])


@app.get("/api/events/range")
async def api_get_events_range(start: str, end: str):
    try:
        return JSONResponse(content=db_get_events_range(start, end))
    except Exception as exc:
        print(f"DB error (events range): {exc}")
        return JSONResponse(content=[])


@app.get("/api/notes")
async def api_get_notes():
    try:
        return JSONResponse(content=db_get_notes())
    except Exception as exc:
        print(f"DB error (notes): {exc}")
        return JSONResponse(content=[])


@app.get("/api/insights/workload")
async def api_get_workload():
    try:
        return JSONResponse(content=db_get_workload())
    except Exception as exc:
        print(f"DB error (workload): {exc}")
        return JSONResponse(content=[])


@app.get("/api/simulate/{date}")
async def api_simulate(date: str):
    try:
        return JSONResponse(content=db_simulate_day_off(date))
    except Exception as exc:
        print(f"Simulation error: {exc}")
        return JSONResponse(content={"error": str(exc)})


@app.get("/api/google/status")
async def api_google_status():
    return JSONResponse(content=_status_payload())


@app.post("/api/google/sync")
async def api_google_sync():
    try:
        return JSONResponse(content=_sync_google_workspace())
    except Exception as exc:
        record_google_sync("workspace", status="error", error=str(exc))
        return JSONResponse(content={"status": _status_payload(), "error": str(exc)}, status_code=500)


@app.get("/api/google/calendar/today")
async def api_google_calendar_today():
    try:
        today = date.today().isoformat()
        calendar = list_calendar_events(start_date=today, end_date=today)
        if calendar.get("events"):
            cache_google_calendar_events(calendar.get("events", []))
        return JSONResponse(content={"status": _status_payload(), "events": db_get_google_calendar_today()})
    except Exception as exc:
        return JSONResponse(content={"status": _status_payload(), "events": [], "error": str(exc)}, status_code=500)


@app.get("/api/google/calendar/range")
async def api_google_calendar_range(start: str, end: str):
    try:
        calendar = list_calendar_events(start_date=start, end_date=end)
        if calendar.get("events"):
            cache_google_calendar_events(calendar.get("events", []))
        return JSONResponse(content={"status": _status_payload(), "events": db_get_google_calendar_range(start, end)})
    except Exception as exc:
        return JSONResponse(content={"status": _status_payload(), "events": [], "error": str(exc)}, status_code=500)


@app.post("/api/google/calendar/events")
async def api_google_create_calendar_event(request: GoogleEventCreateRequest):
    try:
        result = create_calendar_event(
            title=request.title,
            event_date=request.event_date,
            start_time=request.start_time,
            end_time=request.end_time,
            location=request.location,
            attendees=request.attendees,
            description=request.description,
            timezone=request.timezone,
        )
        event = result.get("event")
        if event:
            cache_google_calendar_events([event])
        refreshed = list_calendar_events(start_date=request.event_date, end_date=request.event_date)
        refreshed_events = refreshed.get("events", [])
        if refreshed_events:
            cache_google_calendar_events(refreshed_events)
            matching = next((item for item in refreshed_events if item.get("title") == request.title), refreshed_events[0])
            result["event"] = matching
        result["events_for_day"] = refreshed_events
        return JSONResponse(content=result)
    except Exception as exc:
        return JSONResponse(content={"status": _status_payload(), "error": str(exc)}, status_code=500)


@app.get("/api/google/tasks")
async def api_google_tasks():
    try:
        return JSONResponse(content={"status": _status_payload(), "tasks": db_get_google_tasks()})
    except Exception as exc:
        return JSONResponse(content={"status": _status_payload(), "tasks": [], "error": str(exc)}, status_code=500)


@app.post("/api/google/tasks")
async def api_google_create_task(request: GoogleTaskCreateRequest):
    try:
        result = create_google_task(
            title=request.title,
            notes=request.notes,
            due_date=request.due_date,
            priority=request.priority,
            thread_id=request.thread_id,
        )
        task = result.get("task")
        if task:
            cache_google_tasks([task])
        return JSONResponse(content=result)
    except Exception as exc:
        return JSONResponse(content={"status": _status_payload(), "error": str(exc)}, status_code=500)


@app.post("/api/google/tasks/{task_id}/complete")
async def api_google_complete_task(task_id: str):
    try:
        result = complete_google_task(task_id)
        if result.get("success"):
            db_mark_google_task_complete(task_id)
        return JSONResponse(content=result)
    except Exception as exc:
        return JSONResponse(content={"status": _status_payload(), "error": str(exc)}, status_code=500)


@app.get("/api/google/gmail/summary")
async def api_google_gmail_summary():
    try:
        return JSONResponse(content=db_get_gmail_summary() | {"status": _status_payload()})
    except Exception as exc:
        return JSONResponse(content={"status": _status_payload(), "threads": [], "unread_count": 0, "error": str(exc)}, status_code=500)


@app.post("/api/google/task-from-email")
async def api_google_task_from_email(request: GmailTaskRequest):
    try:
        thread_result = get_gmail_thread_summary(request.thread_id)
        thread = thread_result.get("thread") or {}
        title = request.title or f"Follow up: {thread.get('subject', 'Email thread')}"
        notes = request.notes or thread.get("summary") or thread.get("snippet") or ""
        result = create_google_task(
            title=title,
            notes=notes,
            due_date=request.due_date,
            priority=request.priority,
            thread_id=request.thread_id,
        )
        task = result.get("task")
        if task:
            cache_google_tasks([task])
        return JSONResponse(content={"thread": thread, **result})
    except Exception as exc:
        return JSONResponse(content={"status": _status_payload(), "error": str(exc)}, status_code=500)


@app.post("/api/google/draft-from-email")
async def api_google_draft_from_email(request: GmailDraftRequest):
    try:
        thread_result = get_gmail_thread_summary(request.thread_id)
        thread = thread_result.get("thread") or {}
        subject = request.subject or f"Re: {thread.get('subject', 'Follow-up')}"
        body = request.body or f"Hi,\n\nThanks for the note about {thread.get('subject', 'this thread')}.\n\n"
        result = create_gmail_draft(
            thread_id=request.thread_id,
            to=request.to or thread.get("sender", ""),
            subject=subject,
            body=body,
        )
        return JSONResponse(content={"thread": thread, **result})
    except Exception as exc:
        return JSONResponse(content={"status": _status_payload(), "error": str(exc)}, status_code=500)


@app.post("/api/chat")
async def chat(request: ChatRequest):
    import asyncio

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            sid = await get_or_create_session(request.session_id or str(uuid.uuid4()))
            result, agents_used, tools_called = await run_agent_with_trace(request.message, sid)
            return {
                "response": result or "I processed your request but couldn't generate a text response. Please try rephrasing.",
                "agents": agents_used,
                "tools": tools_called,
                "session_id": sid,
            }
        except Exception as exc:
            error_str = str(exc).lower()
            if ("429" in error_str or "resource_exhausted" in error_str) and attempt < max_retries:
                wait = (attempt + 1) * 3
                print(f"Rate limited (attempt {attempt + 1}), retrying in {wait}s...")
                await asyncio.sleep(wait)
                continue
            print(f"Chat error: {exc}")
            return {
                "response": "I encountered a temporary issue. Please try again in a moment.",
                "agents": [],
                "tools": [],
            }


async def run_agent_with_trace(query: str, session_id: str = "default") -> tuple[str, list[str], list[str]]:
    content = types.Content(role="user", parts=[types.Part.from_text(text=query)])

    final_response = ""
    agents_used = set()
    tools_called = []
    last_text = ""

    async for event in runner.run_async(user_id=USER_ID, session_id=session_id, new_message=content):
        try:
            if hasattr(event, "author") and event.author:
                agents_used.add(event.author)

            if hasattr(event, "content") and event.content:
                parts = getattr(event.content, "parts", None)
                if parts:
                    try:
                        for part in parts:
                            fc = getattr(part, "function_call", None)
                            if fc:
                                name = getattr(fc, "name", None)
                                if name:
                                    tools_called.append(name)
                            if hasattr(part, "text") and part.text:
                                last_text = part.text
                    except TypeError:
                        pass

            if event.is_final_response():
                if hasattr(event, "content") and event.content:
                    parts = getattr(event.content, "parts", None)
                    if parts:
                        try:
                            for part in parts:
                                if hasattr(part, "text") and part.text:
                                    final_response += part.text
                        except TypeError:
                            pass
        except Exception as exc:
            print(f"Event processing error: {exc}")

    if not final_response and last_text:
        final_response = last_text

    return final_response, list(agents_used), tools_called


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
