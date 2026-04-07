# ProdigyAI

ProdigyAI is a FastAPI-based AI chief-of-staff dashboard that combines:

- local tasks, events, notes, and insights from PostgreSQL
- Google Workspace data through a community MCP server
- Google Calendar scheduling
- Google Tasks management
- Gmail inbox triage and draft creation
- MCP Toolbox-backed database tools
- Vertex AI / Gemini chat orchestration

This README is a full startup guide for local development on Windows, including:

- which Google APIs to enable
- how to configure OAuth
- how to start the Google Workspace MCP server
- how to start MCP Toolbox
- how to run ProdigyAI
- how to test Calendar, Tasks, and Gmail

## Architecture

ProdigyAI has three moving parts:

1. `Google Workspace MCP server`
   - handles Google Calendar, Google Tasks, and Gmail access
   - talks to Google APIs using your OAuth credentials

2. `MCP Toolbox`
   - exposes SQL-backed tools for local tasks, events, notes, and insights

3. `ProdigyAI app`
   - UI and API server
   - reads local PostgreSQL data
   - reads Google Workspace data through the Workspace MCP server
   - uses Vertex AI / Gemini for chat

## Prerequisites

Install these first:

- Python 3.13 or similar
- Node.js and `npx`
- PostgreSQL
- `gcloud` CLI
- `uv` / `uvx`

Recommended Windows install commands:

```powershell
winget install Python.Python.3.13
winget install OpenJS.NodeJS
winget install PostgreSQL.PostgreSQL
winget install Google.CloudSDK
winget install --id=astral-sh.uv -e
```

If `uvx` is not found after install, restart PowerShell.

## Google Cloud Setup

Create or use a Google Cloud project for this app.

### 1. Enable APIs

In Google Cloud Console, enable these APIs under `APIs & Services`:

- `Gmail API`
- `Google Calendar API`
- `Google Tasks API`
- `Vertex AI API`

Optional:

- `Geocoding API`
- `Places API`
- `Directions API`

The optional APIs are only needed if you want Google Maps features in the app.

### 2. Configure OAuth Consent Screen

Go to `Google Auth Platform` or `APIs & Services -> OAuth consent screen`.

Use these settings for local development:

- App name: `ProdigyAI Local`
- Audience: `External`
- Publishing status: `Testing`
- Test user: add `pranavyeturu@gmail.com`

### 3. Add Google scopes

For this repo, the Workspace MCP flow needs access for:

- Gmail read:
  - `https://www.googleapis.com/auth/gmail.readonly`
- Gmail draft / compose:
  - `https://www.googleapis.com/auth/gmail.compose`
- Gmail label / modify support used by the community server:
  - `https://www.googleapis.com/auth/gmail.modify`
  - `https://www.googleapis.com/auth/gmail.labels`
  - `https://www.googleapis.com/auth/gmail.settings.basic`
  - `https://www.googleapis.com/auth/gmail.send`
- Calendar:
  - `https://www.googleapis.com/auth/calendar`
  - `https://www.googleapis.com/auth/calendar.readonly`
  - `https://www.googleapis.com/auth/calendar.events`
- Tasks:
  - `https://www.googleapis.com/auth/tasks`
  - `https://www.googleapis.com/auth/tasks.readonly`
- User identity:
  - `openid`
  - `https://www.googleapis.com/auth/userinfo.email`
  - `https://www.googleapis.com/auth/userinfo.profile`

### 4. Create OAuth Client

Go to `APIs & Services -> Credentials`.

Create:

- `OAuth client ID`
- Application type: `Desktop app`

Download the OAuth JSON file.

In this setup, it is expected to live outside the app repo, for example:

```text
C:\Users\Pranav Yeturu\Desktop\workspace-mcp-config\client_secret.json
```

## Vertex AI / Gemini Setup

ProdigyAI chat uses Vertex AI authentication, not the Workspace MCP OAuth flow.

Run:

```powershell
gcloud auth login
gcloud auth application-default login
gcloud config set project adk-mcp-491312
```

Verify ADC works:

```powershell
gcloud auth application-default print-access-token
```

If this fails or hangs, `/api/chat` will fail even if Calendar / Tasks / Gmail are working.

## Environment Configuration

Create or update `C:\Users\Pranav Yeturu\Desktop\ProdigyAI\.env`.

Example:

```env
GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_PROJECT=adk-mcp-491312
GOOGLE_CLOUD_LOCATION=us-central1

TOOLBOX_URL=http://127.0.0.1:5050

MAPS_API_KEY=your-maps-api-key

DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=prodigyai
DB_USER=apple
DB_PASSWORD=prodigyai123

GOOGLE_WORKSPACE_MCP_ENABLED=true
GOOGLE_WORKSPACE_MCP_URL=http://127.0.0.1:8000/mcp
GOOGLE_WORKSPACE_MCP_TIMEOUT=12

GOOGLE_WORKSPACE_USER_EMAIL=pranavyeturu@gmail.com
GOOGLE_WORKSPACE_TASK_LIST_ID=MDcyNjA4MjIxMTg1NDg1Mjg4Njk6MDow
```

Notes:

- `GOOGLE_WORKSPACE_USER_EMAIL` must match the Google account you authenticated with in the Workspace MCP browser flow.
- `GOOGLE_WORKSPACE_TASK_LIST_ID` points to the default Google task list used by the app.
- `GOOGLE_WORKSPACE_MCP_URL` assumes the Workspace MCP server is started with HTTP transport on port `8000`.

## Google Workspace MCP Server

ProdigyAI expects a local HTTP MCP server for Google Workspace.

This repo already includes:

- `C:\Users\Pranav Yeturu\Desktop\ProdigyAI\start_google_workspace_mcp.ps1`

That script is intended to start the community Workspace MCP server with Gmail, Calendar, and Tasks enabled.

### Expected credential env for the Workspace MCP server

The Workspace MCP server must know where your downloaded OAuth client JSON file lives.

Example:

```powershell
$env:GOOGLE_CLIENT_SECRET_PATH="C:\Users\Pranav Yeturu\Desktop\workspace-mcp-config\client_secret.json"
$env:OAUTHLIB_INSECURE_TRANSPORT="1"
uvx workspace-mcp --tools gmail calendar tasks --transport streamable-http
```

### Start the Workspace MCP server

From the repo root:

```powershell
cd C:\Users\Pranav Yeturu\Desktop\ProdigyAI
.\start_google_workspace_mcp.ps1
```

Important:

- keep this terminal open
- complete any Google browser auth flow that appears
- use the same account as `GOOGLE_WORKSPACE_USER_EMAIL`

## MCP Toolbox

Start MCP Toolbox in a second terminal:

```powershell
cd C:\Users\Pranav Yeturu\Desktop\ProdigyAI
npx.cmd @toolbox-sdk/server --tools-file tools.yaml --port 5050
```

Keep this terminal open too.

## Start ProdigyAI

In a third terminal:

```powershell
cd C:\Users\Pranav Yeturu\Desktop\ProdigyAI
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --host 0.0.0.0 --port 8081
```

Open the app:

```powershell
start http://127.0.0.1:8081
```

## Database Notes

ProdigyAI expects PostgreSQL and uses:

- local tables such as `tasks`, `events`, `notes`
- cache tables such as:
  - `google_calendar_cache`
  - `google_tasks_cache`
  - `gmail_threads_cache`

If the app logs permission errors for `tasks` or `events`, run:

```powershell
psql -h 127.0.0.1 -U postgres -d prodigyai -c "GRANT USAGE ON SCHEMA public TO apple; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO apple; GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO apple; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO apple; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO apple;"
```

## Startup Order

Always start services in this order:

1. Google Workspace MCP server
2. MCP Toolbox
3. ProdigyAI app

If you change `.env`, restart the ProdigyAI app.

If you change Workspace MCP credentials or auth, restart the Workspace MCP server too.

## How To Test

### Google Calendar

In the UI:

1. Open `Calendar`
2. Click `Schedule Meeting`
3. Create a meeting
4. Confirm it appears on the calendar page
5. Confirm it also appears in Google Calendar

You can also click `Sync` from the dashboard.

### Google Tasks

In the UI:

1. Open `Tasks`
2. Click `Add Google Task`
3. Create a task with title, optional due date, and notes
4. Confirm it appears in the Tasks page
5. Click `Sync`
6. Mark it complete
7. Confirm it also updates in Google Tasks

### Gmail

In the UI:

1. Open `Command Center`
2. Click `Sync`
3. Check `Inbox Briefing`
4. Click `Draft reply` on a thread
5. Confirm a draft appears in Gmail Drafts
6. Click `Create follow-up task`
7. Confirm the task appears in Google Tasks

### Chat

Try:

- `Show my Google tasks`
- `Summarize my inbox`
- `Schedule a meeting tomorrow at 3 PM`
- `Create follow-up tasks from my inbox`

If chat fails but Calendar / Tasks / Gmail UI works, the problem is usually Vertex AI auth, not Workspace MCP.

## Troubleshooting

### Google Calendar works but UI is empty

Check:

- Workspace MCP server is running
- ProdigyAI was restarted after `.env` changes
- click `Sync`
- open:
  - `http://127.0.0.1:8081/api/google/calendar/range?start=2026-04-06&end=2026-04-12`

If that endpoint returns events, backend sync is working and the issue is frontend rendering.

### Google Tasks create works but Tasks page is empty

Check:

- `GOOGLE_WORKSPACE_TASK_LIST_ID` is set in `.env`
- restart ProdigyAI after changing `.env`
- click `Sync`
- open:
  - `http://127.0.0.1:8081/api/google/tasks`

### Gmail panel is empty

Check:

- click `Sync`
- open:
  - `http://127.0.0.1:8081/api/google/gmail/summary`

If that endpoint has threads, the backend is working and the issue is frontend rendering or parser coverage.

### Chat fails with `oauth2.googleapis.com/token` timeout

This is usually Vertex AI auth or network connectivity.

Run:

```powershell
gcloud auth application-default login
gcloud auth application-default print-access-token
```

If that fails, `/api/chat` will fail too.

### Workspace MCP shows auth errors

Use the latest auth link printed by the Workspace MCP terminal.

Do not reuse old OAuth links.

### `uvx` not found

Install `uv`:

```powershell
winget install --id=astral-sh.uv -e
```

Then restart PowerShell.

## Useful Commands

Start Workspace MCP:

```powershell
cd C:\Users\Pranav Yeturu\Desktop\ProdigyAI
.\start_google_workspace_mcp.ps1
```

Start Toolbox:

```powershell
cd C:\Users\Pranav Yeturu\Desktop\ProdigyAI
npx.cmd @toolbox-sdk/server --tools-file tools.yaml --port 5050
```

Start app:

```powershell
cd C:\Users\Pranav Yeturu\Desktop\ProdigyAI
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --host 0.0.0.0 --port 8081
```

## Repo Notes

- Seed/demo data has been removed from the setup flow.
- Google Calendar and Google Tasks are now backed by local cache tables so the UI can render quickly after sync.
- The app is currently configured around the Google account `pranavyeturu@gmail.com`.
