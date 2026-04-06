"""
Google BigQuery MCP Server — Remote Connection
Provides SQL analytics on historical productivity data.
"""

import google.auth
import google.auth.transport.requests
from google.adk.tools.mcp_tool import MCPToolset
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams

BIGQUERY_MCP_URL = "https://mcp.googleapis.com/v1alpha/bigquery"


def get_bigquery_toolset() -> MCPToolset:
    """
    Connect to Google BigQuery MCP Server using OAuth.

    Available tools include:
    - execute_sql: Run SQL queries against BigQuery datasets
    - get_table_info: Get schema info for a BigQuery table
    - list_tables: List tables in a dataset

    We use this for historical productivity analytics stored in BigQuery
    (monthly trends, quarterly comparisons, etc.)
    """
    credentials, project_id = google.auth.default(
        scopes=["https://www.googleapis.com/auth/bigquery"]
    )
    credentials.refresh(google.auth.transport.requests.Request())

    toolset = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=BIGQUERY_MCP_URL,
            headers={
                "Authorization": f"Bearer {credentials.token}",
                "x-goog-user-project": project_id,
            },
        )
    )
    print(f"BigQuery MCP Toolset configured for project: {project_id}")
    return toolset
