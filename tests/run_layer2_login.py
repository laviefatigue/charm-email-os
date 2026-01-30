"""
Layer 2: Run Claude Code with MCP server to test Hypertide login.
Uses subprocess to avoid shell escaping issues with special characters in passwords.
"""
import subprocess
import sys
import os

PROMPT = """You have access to a purchase-executor MCP server with browser automation tools.
Use ONLY the mcp__purchase-executor__ tools. Do NOT use chrome-devtools or any other MCP server.

Execute these steps in order:

1. Call mcp__purchase-executor__navigate with url="https://app2.hypertide.io/signin"
2. Call mcp__purchase-executor__fill with selector='input[type="email"]' and value="chris@hirecharm.com"
3. Call mcp__purchase-executor__fill with selector='input[type="password"]' and value="l$97t73M"
4. Call mcp__purchase-executor__click with selector="text=Sign In"
5. Call mcp__purchase-executor__screenshot
6. Call mcp__purchase-executor__get_page_text

Report whether login succeeded (dashboard with "Place New Order" visible) or failed (still on signin page).
STOP after reporting. Do NOT click anything else.
"""

def main():
    claude_cmd = r"C:\Users\ellio\AppData\Roaming\npm\claude.cmd"

    cmd = [
        claude_cmd,
        "-p", PROMPT,
        "--mcp-config", "purchase_mcp_config_local.json",
        "--dangerously-skip-permissions",
        "--max-turns", "20",
    ]

    print("Running Claude Code with MCP server...")
    print("=" * 60)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[:500])
    print("=" * 60)
    print(f"Exit code: {result.returncode}")


if __name__ == "__main__":
    main()
