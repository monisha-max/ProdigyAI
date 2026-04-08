# ProdigyAI

**A multi-agent AI system that acts as your Chief of Staff, orchestrating tasks, schedules, emails, notes, and knowledge across your entire Google Workspace through a single conversation.**

Built with Google ADK, MCP Toolbox for Databases, Google Workspace MCP, and Gemini 2.5 Flash.

Live Demo: https://prodigy-ai-577370621769.us-central1.run.app

---

## What It Does

ProdigyAI coordinates six specialized AI agents across three MCP connections and eight Google services to handle complex productivity workflows. One sentence like "Prepare for my investor pitch next Thursday" triggers parallel execution across Calendar, Tasks, Gmail, Maps, and Notes simultaneously.

The system is proactive, not reactive. It analyzes your day before you ask, detects conflicts and overdue items, and generates strategic recommendations with one-click execution.

### Key Features

- **6 AI Agents** with a Coordinator (Chief of Staff) routing to TaskOps, CalendarOps, KnowledgeBase, GmailOps, and Insights
- **ParallelAgent** runs three agents simultaneously for complex multi-step workflows
- **3 MCP Connections**: MCP Toolbox (19 SQL tools), Google Workspace MCP (Calendar, Gmail, Tasks, Drive, Docs), Google Maps Platform
- **Proactive AI Briefing** generated on app load with priorities, schedule insights, and recommendations
- **Time Machine** visual what-if simulator with split-screen before/after comparison and one-click rescue plan execution
- **Voice Input/Output** using browser-native Web Speech API
- **Live Agent Network Visualizer** showing real-time orchestration with animated data flow
- **Google Maps Integration** for venue search, directions, and travel time with real Places API data

---

## Architecture

```
User (Voice/Text) --> FastAPI Server --> ADK Coordinator Agent
                                              |
                      +-----------------------+-----------------------+
                      |              |              |              |
                  TaskOps      CalendarOps    KnowledgeBase    Insights
                      |              |              |              |
                  MCP Toolbox   Workspace MCP   Workspace MCP   MCP Toolbox
                  (Cloud SQL)   + Maps API      (Drive, Docs)   + Python Tools
                      |              |              |              |
                  PostgreSQL    Calendar        Drive           Analytics
                  19 SQL tools  Gmail, Tasks    Docs, Keep      Reports
```

### Tool Sources

| Source | Type | What It Provides |
|---|---|---|
| MCP Toolbox for Databases | Local MCP Server | 19 parameterized SQL tools across 4 toolsets for tasks, events, notes, projects |
| Google Workspace MCP | Remote MCP Server | Google Calendar, Gmail, Tasks, Drive, Docs via OAuth 2.1 |
| Google Maps Platform | REST API | Places API (New) for venue search, Directions API for travel time |
| Custom Python Tools | ADK FunctionTool | Scheduling algorithms, report generation, email drafts |

### Google Services Used

Vertex AI, Cloud SQL, Cloud Run, Google Calendar, Gmail, Google Tasks, Google Drive, Google Docs, Google Meet, Google Chat, Google Keep, Google Maps Platform

---

## Project Structure

```
prodigy-ai/
  prodigy_ai/
    agent.py                   -- 6 agents + ParallelAgent workflow
    db.py                      -- Direct PostgreSQL for dashboard (instant loads)
    tools/
      mcp_tools.py             -- MCP Toolbox connection (19 SQL tools)
      google_workspace_tools.py -- Google Workspace MCP adapter
      maps_tools.py            -- Google Maps REST API
      custom_tools.py          -- Python scheduling/report tools
  static/
    index.html                 -- Dashboard with all views
    css/style.css              -- Dark theme design system
    js/app.js                  -- Interactivity, voice, visualizations
  setup/
    schema.sql                 -- PostgreSQL schema
    setup_cloudsql.sh           -- Cloud SQL provisioning
    deploy_cloudrun.sh          -- Cloud Run deployment
  main.py                      -- FastAPI server with agent tracing
  tools.yaml                   -- MCP Toolbox tool definitions (local)
  tools-cloudrun.yaml          -- MCP Toolbox tool definitions (Cloud Run)
  Dockerfile                   -- Container with MCP Toolbox sidecar
  start.sh                     -- Container startup script
```

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- PostgreSQL
- Google Cloud CLI (gcloud)
- uv / uvx (for Google Workspace MCP server)

### 1. Clone and Install

```bash
git clone https://github.com/monisha-max/ProdigyAI.git
cd ProdigyAI
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Google Cloud Authentication

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com sqladmin.googleapis.com places.googleapis.com
```

### 3. Database Setup

```bash
createdb prodigyai
psql -d prodigyai < setup/schema.sql
```

### 4. Environment Configuration

Copy `.env.example` to `.env` and fill in your values:

```
GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
TOOLBOX_URL=http://127.0.0.1:5050
MAPS_API_KEY=your-maps-api-key
GOOGLE_WORKSPACE_MCP_ENABLED=true
GOOGLE_WORKSPACE_MCP_URL=http://127.0.0.1:8000/mcp
GOOGLE_WORKSPACE_USER_EMAIL=your-email@gmail.com
```

### 5. Google Maps API

Enable these APIs in Google Cloud Console and create one API key:

- Places API (New)
- Directions API

```bash
gcloud services enable places.googleapis.com directions-backend.googleapis.com
gcloud services api-keys create --display-name="ProdigyAI Maps"
```

### 6. Google Workspace MCP Server (Optional)

For Calendar, Gmail, Tasks, Drive, and Docs integration:

a. Enable APIs in Google Cloud Console:
   - Gmail API
   - Google Calendar API
   - Google Tasks API
   - Google Drive API
   - Google Docs API

b. Create OAuth 2.0 credentials:
   - Go to APIs and Services, then Credentials
   - Create OAuth client ID (Desktop app)
   - Download the client secret JSON
   - Copy it to `~/.google_workspace_mcp/credentials/client_secret.json`

c. Configure OAuth consent screen:
   - Set to External, Testing mode
   - Add your email as a test user
   - Add scopes for Calendar, Gmail, Tasks, Drive, Docs

d. Start the server:

```bash
export GOOGLE_OAUTH_CLIENT_ID=your-client-id
export GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
uvx workspace-mcp --tools gmail calendar tasks drive docs --transport streamable-http --single-user
```

e. Complete the OAuth flow by visiting the URL shown in the terminal.

### 7. MCP Toolbox

Download and start:

```bash
# macOS ARM64
curl -O https://storage.googleapis.com/genai-toolbox/v0.23.0/darwin/arm64/toolbox
chmod +x toolbox
./toolbox --tools-file=tools.yaml --port 5050
```

For other platforms, see the MCP Toolbox releases page.

### 8. Start ProdigyAI

```bash
python main.py
```

Open http://localhost:8080

---

## Cloud Run Deployment

### Deploy MCP Toolbox + ProdigyAI

```bash
gcloud run deploy prodigy-ai \
    --source . \
    --region=us-central1 \
    --allow-unauthenticated \
    --port=8080 \
    --memory=1Gi \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=your-project,..." \
    --add-cloudsql-instances=your-connection-name
```

### Deploy Google Workspace MCP Server

The Workspace MCP server deploys as a separate Cloud Run service with pre-authenticated OAuth credentials:

```bash
cd workspace-mcp-deploy
gcloud run deploy workspace-mcp \
    --source . \
    --region=us-central1 \
    --allow-unauthenticated \
    --port=8000
```

Then set `GOOGLE_WORKSPACE_MCP_URL` on the ProdigyAI service to point to the Workspace MCP service URL.

---

## Demo Workflows

| Workflow | What Happens | Agents and Tools |
|---|---|---|
| "Give me my daily briefing" | Proactive analysis of overdue items, priorities, schedule, and recommendations | Coordinator calls daily_briefing (SQL) |
| "Prepare for the investor pitch next Thursday" | ParallelAgent runs 3 agents simultaneously: schedule event, create 4 tasks, save research notes | CalendarOps + TaskOps + KnowledgeBase (7 tool calls) |
| "What if I take Thursday off?" | Time Machine shows visual before/after simulation with rescue plan | Coordinator calls simulate_day_off + smart_reschedule (SQL + Python) |
| "Find a restaurant near downtown SF" | Real venue search with ratings and addresses | Coordinator calls search_places (Google Maps API) |
| "Generate my weekly report" | Formatted productivity report with metrics table | Coordinator calls weekly_report + generate_report_summary (SQL + Python) |

---

## Technology Stack

| Component | Technology |
|---|---|
| Agent Framework | Google ADK v1.28.0 (LlmAgent, ParallelAgent) |
| LLM | Gemini 2.5 Flash via Vertex AI |
| MCP Server (Database) | MCP Toolbox for Databases v0.23.0 |
| MCP Server (Workspace) | Google Workspace MCP (workspace-mcp) |
| Database | Cloud SQL PostgreSQL 15 |
| Maps | Google Maps Places API (New) + Directions API |
| Web Server | FastAPI + Uvicorn |
| Frontend | Vanilla HTML/JS/CSS, Chart.js, Marked.js, Web Speech API |
| Deployment | Cloud Run + Docker |

---

## Team

Built for Gen AI Academy APAC Edition

Monisha Kollipara, Harsha Dayini Akula, Deekshitha Karvan, Pranav Yeturu
