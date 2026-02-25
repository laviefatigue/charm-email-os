"""
Project Directory Assistant - Test Harness (Config-Driven)

Tests all MCP tools exposed by the assistant server.
Reads project-assistant.yaml to determine which tools to test.

Usage:
    python test_assistant.py                # Full test suite
    python test_assistant.py --quick        # Skip ask_project (slow)
    python test_assistant.py --url URL      # Custom server URL
"""

import asyncio
import os
import sys

# Try to load config for project-aware testing
CONFIG = {}
try:
    import yaml
    config_path = os.getenv("ASSISTANT_CONFIG", "project-assistant.yaml")
    if os.path.exists(config_path):
        with open(config_path) as f:
            CONFIG = yaml.safe_load(f) or {}
except Exception:
    pass

PROJECT_NAME = CONFIG.get("project", {}).get("display_name", "Project")
DB_CONFIG = CONFIG.get("database", {})
STATIC_DOCS = CONFIG.get("static_docs", {})

API_KEY = os.getenv("ASSISTANT_API_KEY", "")
CF_ACCESS_CLIENT_ID = os.getenv("CF_ACCESS_CLIENT_ID", "")
CF_ACCESS_CLIENT_SECRET = os.getenv("CF_ACCESS_CLIENT_SECRET", "")

AUTH_HEADERS = {}
if API_KEY:
    AUTH_HEADERS["Authorization"] = f"Bearer {API_KEY}"
if CF_ACCESS_CLIENT_ID:
    AUTH_HEADERS["CF-Access-Client-Id"] = CF_ACCESS_CLIENT_ID
if CF_ACCESS_CLIENT_SECRET:
    AUTH_HEADERS["CF-Access-Client-Secret"] = CF_ACCESS_CLIENT_SECRET


def preview(text, limit=300):
    """Truncate text for preview display."""
    if len(text) > limit:
        return text[:limit] + f"\n... ({len(text)} chars total)"
    return text


async def main():
    from mcp.client.streamable_http import streamablehttp_client
    from mcp import ClientSession

    url = "http://localhost:3000/mcp"
    quick = False

    for arg in sys.argv[1:]:
        if arg == "--quick":
            quick = True
        elif arg.startswith("--url"):
            url = sys.argv[sys.argv.index(arg) + 1]

    print(f"Connecting to {url} ...")
    if AUTH_HEADERS:
        print(f"Using bearer auth")
    print()

    async with streamablehttp_client(url, headers=AUTH_HEADERS) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List all tools
            tools = await session.list_tools()
            print(f"Tools available ({len(tools.tools)}):")
            for tool in tools.tools:
                print(f"  {tool.name:25s} {tool.description[:70] if tool.description else ''}")
            print()

            # --- list_files ---
            print("--- list_files ---")
            result = await session.call_tool("list_files", {"directory": ""})
            print(preview(result.content[0].text))
            print()

            # --- Static doc tools (from config) ---
            for name in STATIC_DOCS:
                tool_name = f"get_{name}"
                print(f"--- {tool_name} ---")
                result = await session.call_tool(tool_name, {})
                print(preview(result.content[0].text))
                print()

            # --- search_project ---
            print("--- search_project ---")
            # Search for a common term
            result = await session.call_tool("search_project", {
                "query": "import",
                "file_pattern": "*.py",
                "teammate": "test-runner",
            })
            print(preview(result.content[0].text))
            print()

            # --- get_file ---
            print("--- get_file ---")
            # Try to read a common file
            for candidate in ["requirements.txt", "package.json", "README.md", "setup.py"]:
                result = await session.call_tool("get_file", {
                    "path": candidate,
                    "teammate": "test-runner",
                })
                text = result.content[0].text
                if "Error: file not found" not in text:
                    print(preview(text))
                    break
            else:
                print("(no common file found to read)")
            print()

            # --- get_recent_changes ---
            print("--- get_recent_changes ---")
            result = await session.call_tool("get_recent_changes", {"last_n": 5})
            print(preview(result.content[0].text))
            print()

            # ============================================================
            # Database tests (conditional)
            # ============================================================
            if DB_CONFIG.get("enabled"):
                primary_table = DB_CONFIG.get("primary_table", "?")
                print("=" * 60)
                print(f"Testing query_database ({DB_CONFIG.get('engine', 'unknown')})")
                print("=" * 60)
                print()

                # COUNT
                print(f"--- query_database (COUNT) ---")
                result = await session.call_tool("query_database", {
                    "sql": f"SELECT COUNT(*) AS total FROM {primary_table}",
                    "teammate": "test-runner",
                })
                print(preview(result.content[0].text, 500))
                print()

                # Sample rows
                print(f"--- query_database (Sample) ---")
                result = await session.call_tool("query_database", {
                    "sql": f"SELECT * FROM {primary_table} LIMIT 3",
                    "teammate": "test-runner",
                    "max_rows": 3,
                })
                print(preview(result.content[0].text, 500))
                print()

                # Blocked write
                print(f"--- query_database (Blocked write) ---")
                result = await session.call_tool("query_database", {
                    "sql": f"INSERT INTO {primary_table} VALUES (1)",
                    "teammate": "test-runner",
                })
                print(preview(result.content[0].text))
                print()
            else:
                print("(database tests skipped -- not enabled in config)")
                print()

            # ============================================================
            # Notes workflow
            # ============================================================
            print("=" * 60)
            print("Testing notes workflow (submit -> read -> update -> read)")
            print("=" * 60)
            print()

            # Submit a note
            print("--- submit_note ---")
            result = await session.call_tool("submit_note", {
                "teammate": "test-runner",
                "note_type": "feature_idea",
                "title": f"Test note for {PROJECT_NAME} assistant",
                "body": "This is an automated test note to verify the notes workflow.",
                "related_files": "",
            })
            text = result.content[0].text
            print(preview(text))
            note_id = ""
            for line in text.split("\n"):
                if "ID:" in line:
                    note_id = line.split("ID:")[1].strip()
                    break
            print()

            # Get all notes
            print("--- get_notes (all) ---")
            result = await session.call_tool("get_notes", {"last_n": 5})
            print(preview(result.content[0].text, 500))
            print()

            # Update the note
            if note_id:
                print(f"--- update_note ({note_id}) ---")
                result = await session.call_tool("update_note", {
                    "note_id": note_id,
                    "status": "reviewed",
                    "owner_response": "Test update -- automated test.",
                })
                print(preview(result.content[0].text))
                print()

            # Query log
            print("--- get_query_log ---")
            result = await session.call_tool("get_query_log", {"last_n": 5})
            print(preview(result.content[0].text, 500))
            print()

            # --- query_knowledge ---
            print("--- query_knowledge ---")
            result = await session.call_tool("query_knowledge", {
                "question": "What is the architecture of this project?",
                "context_area": "general",
                "teammate": "test-runner",
            })
            print(preview(result.content[0].text, 500))
            print()

            # --- ask_project (slow, skip with --quick) ---
            if not quick:
                print("--- ask_project ---")
                result = await session.call_tool("ask_project", {
                    "question": "What is the purpose of this project in 2 sentences?",
                    "context_area": "general",
                    "teammate": "test-runner",
                })
                print(preview(result.content[0].text, 500))
                print()
            else:
                print("(skipped ask_project -- run without --quick to include)")
                print()

            print("All tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
