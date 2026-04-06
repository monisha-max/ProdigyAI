# ProdigyAI — Architecture Document

## System Overview

ProdigyAI is a multi-agent productivity system with 5 genuinely distinct tool integrations
coordinated through Google ADK. It's not just CRUD — it's cross-service orchestration.

## 5 Tool Sources (All Different)

### 1. MCP Toolbox for Databases → Cloud SQL (PostgreSQL)
- **Type**: Local MCP Server (toolbox binary on port 5000)
- **Connection**: `ToolboxSyncClient("http://127.0.0.1:5000")`
- **What it does**: CRUD for tasks, events, notes, projects
- **17 SQL tools** across 4 toolsets
- **Why**: Core structured data — every agent reads/writes here

### 2. Google Maps Platform MCP Server (Remote)
- **Type**: Remote Google-hosted MCP Server
- **Connection**: `MCPToolset` with `StreamableHTTPConnectionParams`
- **Auth**: API Key via `X-Goog-Api-Key` header
- **URL**: `https://mcp.googleapis.com/v1alpha/maps`
- **What it does**: Place search, directions, geocoding, distance matrix
- **Why**: Location intelligence for events ("find a venue", "commute time to meeting")

### 3. Google Search via Grounding (ADK Built-in)
- **Type**: ADK native tool (`google_search`)
- **Connection**: Built into Gemini via Vertex AI
- **What it does**: Real-time web search for grounding agent responses
- **Why**: Research capability ("look up this investor", "latest news on topic X")

### 4. Custom Python Tools (ADK FunctionTool)
- **Type**: Python functions wrapped as ADK tools
- **What they do**:
  - `send_email_draft`: Generates email content for meeting invites, follow-ups
  - `generate_report_pdf`: Creates formatted PDF productivity reports
  - `smart_reschedule`: Algorithm that suggests optimal rescheduling when conflicts arise
  - `calculate_free_slots`: Finds available time windows in a day
- **Why**: Demonstrates custom tool creation beyond MCP, adds real utility

### 5. BigQuery MCP Server (Remote)
- **Type**: Remote Google-hosted MCP Server
- **Connection**: `MCPToolset` with `StreamableHTTPConnectionParams`
- **Auth**: OAuth Bearer token via `Authorization` header
- **URL**: `https://mcp.googleapis.com/v1alpha/bigquery`
- **What it does**: Query historical productivity data for trend analysis
- **Why**: Analytics that go beyond what's in Cloud SQL — monthly/quarterly trends

## Agent Architecture

```
                         ┌──────────────┐
                         │     User     │
                         └──────┬───────┘
                                │
                         ┌──────▼───────┐
                         │  Dashboard   │
                         │  (FastAPI)   │
                         └──────┬───────┘
                                │
                    ┌───────────▼───────────┐
                    │     Coordinator       │
                    │   (Chief of Staff)    │
                    │   gemini-2.5-flash    │
                    │   No tools — routes   │
                    └───┬───┬───┬───┬───────┘
                        │   │   │   │
          ┌─────────────┘   │   │   └─────────────┐
          │                 │   │                   │
    ┌─────▼─────┐   ┌──────▼───▼──┐   ┌──────────▼────────┐
    │  TaskOps   │   │ CalendarOps │   │   KnowledgeBase   │
    │            │   │             │   │                   │
    │ Tools:     │   │ Tools:      │   │ Tools:            │
    │ • MCP SQL  │   │ • MCP SQL   │   │ • MCP SQL (notes) │
    │   (tasks)  │   │   (events)  │   │ • Google Search   │
    │            │   │ • Maps MCP  │   │                   │
    │            │   │ • Python    │   │                   │
    │            │   │   (free     │   │                   │
    │            │   │   slots,    │   │                   │
    │            │   │   reschedule│   │                   │
    │            │   │   )         │   │                   │
    └────────────┘   └────────────┘   └───────────────────┘
                                                │
                                    ┌───────────▼──────────┐
                                    │      Insights        │
                                    │                      │
                                    │ Tools:               │
                                    │ • MCP SQL (analytics)│
                                    │ • BigQuery MCP       │
                                    │ • Python (PDF report)│
                                    └──────────────────────┘
```

## Multi-Step Workflow Demos

### Demo 1: "Prepare for the investor pitch next Thursday"
```
User message → Coordinator
  → CalendarOps:
      1. check_conflicts(Thursday) via Cloud SQL
      2. create_event("Investor Pitch") via Cloud SQL
      3. search_places("coffee shop near investor office") via Google Maps MCP
      4. calculate_free_slots(Thursday) via Python tool
  → TaskOps:
      1. create_task("Finalize pitch deck", urgent) via Cloud SQL
      2. create_task("Prepare financials", high) via Cloud SQL
      3. create_task("Research investor background", high) via Cloud SQL
  → KnowledgeBase:
      1. google_search("investor name + portfolio") via Google Search
      2. create_note("Investor Research Notes") via Cloud SQL
  → Insights:
      1. workload_analysis() via Cloud SQL
      2. Warns: "Thursday is heavy — 4 items. Move blog post to Friday?"
  → Coordinator: Synthesizes all results into one response
```

### Demo 2: "What if I take Friday off?"
```
User message → Coordinator
  → Insights:
      1. simulate_day_off(Friday) via Cloud SQL
      2. Returns: 3 tasks due, 2 events scheduled
  → Coordinator suggests rescheduling
  → User approves
  → TaskOps: update_task(move due dates) via Cloud SQL
  → CalendarOps: reschedule events via Cloud SQL
  → Coordinator: "Done! Moved 3 tasks to Thursday, rescheduled standup to Monday."
```

### Demo 3: "Generate my weekly productivity report"
```
User message → Coordinator
  → Insights:
      1. weekly_report() via Cloud SQL (current week stats)
      2. BigQuery query for monthly trend data via BigQuery MCP
      3. generate_report_pdf() via Python tool
  → Coordinator: Returns markdown summary + PDF download link
```

### Demo 4: "Schedule a team lunch somewhere nice near the office"
```
User message → Coordinator
  → CalendarOps:
      1. calculate_free_slots(today) via Python tool
      2. search_places("restaurants near office address") via Google Maps MCP
      3. get_directions(office, restaurant) via Google Maps MCP
      4. check_conflicts(suggested time) via Cloud SQL
      5. create_event("Team Lunch", location=restaurant) via Cloud SQL
  → Coordinator: "Booked team lunch at [restaurant], 15 min walk from office.
                   No conflicts. I've sent the details to the team."
```

## Technology Stack

| Component | Technology |
|---|---|
| Agent Framework | Google ADK (Agent Development Kit) |
| LLM | Gemini 2.5 Flash via Vertex AI |
| MCP Server (local) | MCP Toolbox for Databases v0.23.0 |
| MCP Server (Maps) | Google Maps Platform MCP (remote) |
| MCP Server (BigQuery) | Google BigQuery MCP (remote) |
| Search | Google Search grounding (ADK built-in) |
| Database | Cloud SQL PostgreSQL 15 |
| Analytics | BigQuery (public dataset or custom) |
| Web Framework | FastAPI + Uvicorn |
| Frontend | Vanilla HTML/JS/CSS + Chart.js |
| Deployment | Cloud Run + Docker |
| Language | Python 3.12 |

## File Structure

```
prodigy-ai/
├── prodigy_ai/                    # ADK Agent Application
│   ├── __init__.py
│   ├── agent.py                   # All 5 agents + routing
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── mcp_tools.py           # MCP Toolbox connection (Cloud SQL)
│   │   ├── maps_tools.py          # Google Maps MCP connection
│   │   ├── bigquery_tools.py      # BigQuery MCP connection
│   │   └── custom_tools.py        # Python FunctionTools (email, PDF, scheduling)
│   └── .env                       # Vertex AI config
├── static/                        # Dashboard UI
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── setup/
│   ├── schema.sql                 # Cloud SQL schema + seed data
│   ├── bigquery_schema.sql        # BigQuery historical data setup
│   ├── setup_cloudsql.sh          # Cloud SQL provisioning
│   └── deploy_cloudrun.sh         # Cloud Run deployment
├── main.py                        # FastAPI server
├── tools.yaml                     # MCP Toolbox config (17 SQL tools)
├── requirements.txt
├── Dockerfile
├── start.sh
└── .gitignore
```

## 4-Week Build Plan

### Week 1: Foundation
- Day 1-2: Cloud SQL setup, schema, seed data, tools.yaml, test toolbox locally
- Day 3-4: ADK agents (Coordinator + TaskOps + CalendarOps + KnowledgeBase + Insights)
- Day 5-6: FastAPI server, basic chat endpoint, verify agent routing
- Day 7: Test all 17 SQL tools end-to-end

### Week 2: Tool Integrations
- Day 8-9: Google Maps MCP integration + CalendarOps agent update
- Day 10-11: Custom Python tools (free slots, reschedule, email draft, PDF)
- Day 12-13: Google Search grounding + KnowledgeBase agent update
- Day 14: BigQuery MCP integration + Insights agent update

### Week 3: Dashboard & Visualization
- Day 15-16: Dashboard layout (sidebar, topbar, views, responsive)
- Day 17-18: Kanban board, calendar view, charts, stats cards
- Day 19-20: Chat panel with agent pipeline stream + agent network visualizer
- Day 21: Splash screen, animations, confetti, polish

### Week 4: Deploy & Submit
- Day 22-23: Dockerfile, Cloud Run deployment, end-to-end testing
- Day 24-25: Demo workflow testing (all 4 demos working perfectly)
- Day 26-27: Bug fixes, edge cases, performance tuning
- Day 28-29: Submission deck, screenshots, demo video recording
- Day 30: Final review and submit
