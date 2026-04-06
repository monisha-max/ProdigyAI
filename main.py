"""
ProdigyAI — FastAPI Server
Dashboard data: direct PostgreSQL queries (fast, reliable)
Chat: ADK multi-agent system (Gemini + MCP Toolbox + Maps + Python tools)
"""

import os
import json
import uuid
import traceback as tb
from contextlib import asynccontextmanager

import dotenv
dotenv.load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Direct DB access for dashboard (fast, reliable)
from prodigy_ai.db import (
    get_tasks as db_get_tasks,
    update_task as db_update_task,
    get_events_today as db_get_events_today,
    get_events_range as db_get_events_range,
    get_notes as db_get_notes,
    get_workload as db_get_workload,
    simulate_day_off as db_simulate_day_off,
)

# Agent for chat (LLM-powered)
from prodigy_ai.agent import root_agent

# ─── Session Management ───
APP_NAME = "prodigy_ai"
USER_ID = "default_user"
session_service = InMemorySessionService()
runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)

# Track sessions: one persistent session per browser tab (via session_id param)
# plus the ability to create fresh sessions for each chat if needed
_sessions = set()


async def get_or_create_session(sid: str = None) -> str:
    """Get existing session or create new one."""
    if sid and sid in _sessions:
        return sid
    new_id = sid or str(uuid.uuid4())
    await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=new_id,
    )
    _sessions.add(new_id)
    return new_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create a default session on startup
    default_id = await get_or_create_session("default")
    print(f"ProdigyAI default session: {default_id}")
    yield


app = FastAPI(title="ProdigyAI", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ─── Models ───
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None  # Optional: reuse session for conversation continuity

class TaskUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None


# ═══════════════════════════════════════
# DASHBOARD API — Direct DB (instant)
# ═══════════════════════════════════════

@app.get("/")
async def serve_dashboard():
    return FileResponse("static/index.html")


@app.get("/api/tasks")
async def api_get_tasks(status: str = "all"):
    try:
        return JSONResponse(content=db_get_tasks(status))
    except Exception as e:
        print(f"DB error (tasks): {e}")
        return JSONResponse(content=[])


@app.put("/api/tasks/{task_id}")
async def api_update_task(task_id: int, update: TaskUpdate):
    try:
        result = db_update_task(task_id, status=update.status, priority=update.priority)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/events/today")
async def api_get_events_today():
    try:
        return JSONResponse(content=db_get_events_today())
    except Exception as e:
        print(f"DB error (events): {e}")
        return JSONResponse(content=[])


@app.get("/api/events/range")
async def api_get_events_range(start: str, end: str):
    try:
        return JSONResponse(content=db_get_events_range(start, end))
    except Exception as e:
        print(f"DB error (events range): {e}")
        return JSONResponse(content=[])


@app.get("/api/notes")
async def api_get_notes():
    try:
        return JSONResponse(content=db_get_notes())
    except Exception as e:
        print(f"DB error (notes): {e}")
        return JSONResponse(content=[])


@app.get("/api/insights/workload")
async def api_get_workload():
    try:
        return JSONResponse(content=db_get_workload())
    except Exception as e:
        print(f"DB error (workload): {e}")
        return JSONResponse(content=[])


@app.get("/api/simulate/{date}")
async def api_simulate(date: str):
    """Time Machine: get structured before/after simulation data for a date."""
    try:
        return JSONResponse(content=db_simulate_day_off(date))
    except Exception as e:
        print(f"Simulation error: {e}")
        return JSONResponse(content={"error": str(e)})


# ═══════════════════════════════════════
# CHAT API — ADK Agents (LLM-powered)
# ═══════════════════════════════════════

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
        except Exception as e:
            error_str = str(e).lower()
            if ("429" in error_str or "resource_exhausted" in error_str) and attempt < max_retries:
                wait = (attempt + 1) * 3
                print(f"Rate limited (attempt {attempt+1}), retrying in {wait}s...")
                await asyncio.sleep(wait)
                continue
            print(f"Chat error: {e}")
            return {
                "response": "I encountered a temporary issue. Please try again in a moment.",
                "agents": [],
                "tools": [],
            }


async def run_agent_with_trace(query: str, session_id: str = "default") -> tuple[str, list[str], list[str]]:
    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=query)]
    )

    final_response = ""
    agents_used = set()
    tools_called = []

    last_text = ""  # Track last text seen from any event, not just final

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=content,
    ):
        try:
            if hasattr(event, 'author') and event.author:
                agents_used.add(event.author)

            if hasattr(event, 'content') and event.content:
                parts = getattr(event.content, 'parts', None)
                if parts:
                    try:
                        for part in parts:
                            fc = getattr(part, 'function_call', None)
                            if fc:
                                name = getattr(fc, 'name', None)
                                if name:
                                    tools_called.append(name)
                            # Capture text from ALL events, not just final
                            if hasattr(part, 'text') and part.text:
                                last_text = part.text
                    except TypeError:
                        pass

            if event.is_final_response():
                if hasattr(event, 'content') and event.content:
                    parts = getattr(event.content, 'parts', None)
                    if parts:
                        try:
                            for part in parts:
                                if hasattr(part, 'text') and part.text:
                                    final_response += part.text
                        except TypeError:
                            pass
        except Exception as e:
            print(f"Event processing error: {e}")

    # If final response is empty but we captured text from intermediate events, use that
    if not final_response and last_text:
        final_response = last_text

    return final_response, list(agents_used), tools_called


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
