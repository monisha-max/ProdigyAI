"""
MCP Toolbox for Databases — Cloud SQL Connection
Provides 17 SQL tools across 4 toolsets for structured data operations.
"""

import os
from toolbox_core import ToolboxSyncClient

TOOLBOX_URL = os.getenv("TOOLBOX_URL", "http://127.0.0.1:5000")

_client = None


def _get_client() -> ToolboxSyncClient:
    global _client
    if _client is None:
        _client = ToolboxSyncClient(TOOLBOX_URL)
        print(f"MCP Toolbox connected at {TOOLBOX_URL}")
    return _client


def get_task_tools():
    """Load task management tools: create, list, update, delete, priority, overdue."""
    return _get_client().load_toolset("task_tools")


def get_calendar_tools():
    """Load calendar tools: create event, list events, upcoming, conflicts."""
    return _get_client().load_toolset("calendar_tools")


def get_notes_tools():
    """Load notes tools: create, create linked, search, list."""
    return _get_client().load_toolset("notes_tools")


def get_insights_tools():
    """Load insights tools: daily briefing, weekly report, workload, simulate."""
    return _get_client().load_toolset("insights_tools")
