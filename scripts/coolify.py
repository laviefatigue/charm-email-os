#!/usr/bin/env python3
"""
Coolify CLI — Direct API wrapper for managing production infrastructure.

Usage:
    py scripts/coolify.py list-apps
    py scripts/coolify.py status [APP_NAME]
    py scripts/coolify.py env-list APP_NAME
    py scripts/coolify.py env-set APP_NAME KEY VALUE
    py scripts/coolify.py env-delete APP_NAME KEY
    py scripts/coolify.py deploy APP_NAME
    py scripts/coolify.py restart APP_NAME
    py scripts/coolify.py stop APP_NAME
    py scripts/coolify.py start APP_NAME
    py scripts/coolify.py logs APP_NAME [--lines=100]

APP_NAME can be the full name or a shorthand (e.g., "sync" matches "emailbison-sync").
"""
import sys
import json
import urllib.request
import urllib.error
import urllib.parse

BASE_URL = "https://coolify.wizardgrimoire.cloud"
TOKEN = "4|UIVvsz1UT4KJ0quJwmGcgWTTVYMA3Q4L2zodb2jqca9cf96c"

# Known app UUIDs for quick lookup
APP_UUIDS = {
    "charm-api": "nckgggwww8sggg0kc4wo00o8",
    "charm-frontend": "qw88skgwgwgk8g44c0g4wgks",
    "executive-dashboard": "gkkgsscwck0o80gwkcsogcow",
    "emailbison-sync": "l4g44o00s4cccg804osswgcc",
    "hypertide-worker": "e0go4ocg8cggw08kowocok4g",
    "domain-worker": "u4oo8o0wocsgss8o4cs4g4oc",
    "price-checker": "rcckg8k84os8c400kwk4ck04",
    "incubation-watcher": "pssgc0c8w4sooos8gs0scsos",
}

# Shortcuts
ALIASES = {
    "api": "charm-api",
    "frontend": "charm-frontend",
    "dashboard": "executive-dashboard",
    "sync": "emailbison-sync",
    "eb-sync": "emailbison-sync",
    "hypertide": "hypertide-worker",
    "domain": "domain-worker",
    "price": "price-checker",
    "watcher": "incubation-watcher",
    "incubation": "incubation-watcher",
}


def api(method, path, body=None):
    """Make a Coolify API request."""
    url = f"{BASE_URL}/api/v1{path}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "CF-Access-Client-Id": "2d248ecd21fc2106dac566160e1d73b3.access",
        "CF-Access-Client-Secret": "4b0adcffdb27e3f1563cb2350137cb8e078df601ff6400a9ab9971fd1de07160",
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            if not raw.strip():
                return {}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                print(f"Non-JSON response ({resp.status}): {raw[:500].encode('ascii', 'replace').decode()}")
                return {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        print(f"ERROR {e.code}: {e.reason}")
        if body_text:
            try:
                print(json.dumps(json.loads(body_text), indent=2))
            except Exception:
                print(body_text[:500])
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"CONNECTION ERROR: {e.reason}")
        sys.exit(1)


def resolve_app(name):
    """Resolve app name/alias to UUID."""
    name = name.lower().strip()
    if name in ALIASES:
        name = ALIASES[name]
    if name in APP_UUIDS:
        return name, APP_UUIDS[name]
    # Fuzzy match
    for app_name, uuid in APP_UUIDS.items():
        if name in app_name:
            return app_name, uuid
    print(f"Unknown app: {name}")
    print(f"Available: {', '.join(APP_UUIDS.keys())}")
    sys.exit(1)


def cmd_list_apps():
    """List all applications."""
    apps = api("GET", "/applications")
    if isinstance(apps, list):
        data = apps
    elif isinstance(apps, dict):
        data = apps.get("data", apps.get("applications", [apps]))
    else:
        data = []

    print(f"{'Name':<30} {'UUID':<30} {'Status':<15}")
    print("-" * 75)
    for app in data:
        name = app.get("name", app.get("description", "?"))
        uuid = app.get("uuid", "?")
        status = app.get("status", "?")
        print(f"{name:<30} {uuid:<30} {status:<15}")


def cmd_status(app_name=None):
    """Get application status."""
    if app_name:
        name, uuid = resolve_app(app_name)
        app = api("GET", f"/applications/{uuid}")
        print(json.dumps(app, indent=2, default=str))
    else:
        cmd_list_apps()


def cmd_env_list(app_name):
    """List environment variables for an app."""
    name, uuid = resolve_app(app_name)
    envs = api("GET", f"/applications/{uuid}/envs")
    if isinstance(envs, list):
        data = envs
    elif isinstance(envs, dict):
        data = envs.get("data", envs.get("envs", []))
    else:
        data = []

    print(f"Environment variables for {name}:")
    print(f"{'Key':<40} {'Value':<50} {'ID'}")
    print("-" * 100)
    for env in sorted(data, key=lambda e: e.get("key", "")):
        key = env.get("key", "?")
        value = env.get("value", "?")
        env_id = env.get("id", "?")
        # Truncate long values
        if len(str(value)) > 47:
            value = str(value)[:47] + "..."
        print(f"{key:<40} {value:<50} {env_id}")


def cmd_env_set(app_name, key, value):
    """Create or update an environment variable.

    Self-heals duplicate-key drift. Coolify allows multiple env entries
    with the same key (each has its own UUID). PATCH on the collection
    only updates the first match, leaving stale duplicates with old
    values — which bit us 2026-05-05 when KILL_RULE_DRY_RUN had two
    entries (false + true) and the rule's behavior on container restart
    became non-deterministic.

    On every env-set call we:
      1. Pull all entries.
      2. If 2+ entries share the key, delete extras (keep first).
      3. PATCH (or POST) the survivor.
    """
    name, uuid = resolve_app(app_name)

    envs = api("GET", f"/applications/{uuid}/envs")
    if isinstance(envs, dict):
        envs = envs.get("data", envs.get("envs", []))

    matches = [e for e in (envs if isinstance(envs, list) else []) if e.get("key") == key]

    # Self-heal: delete duplicates (keep the first)
    if len(matches) > 1:
        for dup in matches[1:]:
            dup_id = dup.get("uuid") or dup.get("id")
            if dup_id:
                try:
                    api("DELETE", f"/applications/{uuid}/envs/{dup_id}")
                    print(f"  cleaned up duplicate {key} entry (uuid={dup_id})")
                except Exception as e:
                    print(f"  WARNING: failed to delete duplicate {key} (uuid={dup_id}): {e}")

    if matches:
        # Update existing — Coolify PATCH works on the collection endpoint with key+value
        api("PATCH", f"/applications/{uuid}/envs", {
            "key": key,
            "value": value,
        })
        print(f"UPDATED {key}={value} on {name}")
    else:
        # Create new
        api("POST", f"/applications/{uuid}/envs", {
            "key": key,
            "value": value,
        })
        print(f"CREATED {key}={value} on {name}")


def cmd_env_delete(app_name, key):
    """Delete an environment variable."""
    name, uuid = resolve_app(app_name)

    envs = api("GET", f"/applications/{uuid}/envs")
    if isinstance(envs, dict):
        envs = envs.get("data", envs.get("envs", []))

    for env in (envs if isinstance(envs, list) else []):
        if env.get("key") == key:
            env_id = env.get("uuid") or env.get("id")
            api("DELETE", f"/applications/{uuid}/envs/{env_id}")
            print(f"DELETED {key} from {name}")
            return

    print(f"Variable {key} not found on {name}")
    sys.exit(1)


def cmd_deploy(app_name):
    """Trigger deployment for an app.

    Uses force=true so Coolify pulls the latest commit fresh from git.
    With force=false, Coolify reuses its cached git state, which silently
    deploys an outdated image even when newer commits are pushed — this
    bit us 2026-05-04 (kill-rule rewrite deployed cached commit baf90cf7
    instead of 5118d59).
    """
    name, uuid = resolve_app(app_name)
    # Coolify uses GET /deploy?uuid=... (not POST /applications/{uuid}/deploy)
    result = api("GET", f"/deploy?uuid={uuid}&force=true")
    print(f"Deployment triggered for {name} (force=true: fresh git pull)")
    if isinstance(result, dict):
        deployments = result.get("deployments", [])
        if deployments:
            dep_uuid = deployments[0].get("deployment_uuid", "")
            if dep_uuid:
                print(f"Deployment UUID: {dep_uuid}")


def cmd_restart(app_name):
    """Restart an application."""
    name, uuid = resolve_app(app_name)
    result = api("POST", f"/applications/{uuid}/restart")
    print(f"Restart triggered for {name}")


def cmd_stop(app_name):
    """Stop an application."""
    name, uuid = resolve_app(app_name)
    result = api("POST", f"/applications/{uuid}/stop")
    print(f"Stop triggered for {name}")


def cmd_start(app_name):
    """Start an application."""
    name, uuid = resolve_app(app_name)
    result = api("POST", f"/applications/{uuid}/start")
    print(f"Start triggered for {name}")


def cmd_logs(app_name, lines=100):
    """Get application logs."""
    name, uuid = resolve_app(app_name)
    result = api("GET", f"/applications/{uuid}/logs?limit={lines}")
    if isinstance(result, list):
        for line in result:
            if isinstance(line, dict):
                print(line.get("output", line.get("message", str(line))))
            else:
                print(line)
    elif isinstance(result, dict):
        logs = result.get("logs", result.get("data", []))
        if isinstance(logs, list):
            for line in logs:
                if isinstance(line, dict):
                    print(line.get("output", line.get("message", str(line))))
                else:
                    print(line)
        elif isinstance(logs, str):
            print(logs)
        else:
            print(json.dumps(result, indent=2))
    else:
        print(result)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    if cmd in ("list-apps", "list", "ls"):
        cmd_list_apps()
    elif cmd == "status":
        cmd_status(args[0] if args else None)
    elif cmd in ("env-list", "envs"):
        if not args:
            print("Usage: coolify.py env-list APP_NAME")
            sys.exit(1)
        cmd_env_list(args[0])
    elif cmd in ("env-set", "env-add"):
        if len(args) < 3:
            print("Usage: coolify.py env-set APP_NAME KEY VALUE")
            sys.exit(1)
        cmd_env_set(args[0], args[1], args[2])
    elif cmd in ("env-delete", "env-rm"):
        if len(args) < 2:
            print("Usage: coolify.py env-delete APP_NAME KEY")
            sys.exit(1)
        cmd_env_delete(args[0], args[1])
    elif cmd == "deploy":
        if not args:
            print("Usage: coolify.py deploy APP_NAME")
            sys.exit(1)
        cmd_deploy(args[0])
    elif cmd == "restart":
        if not args:
            print("Usage: coolify.py restart APP_NAME")
            sys.exit(1)
        cmd_restart(args[0])
    elif cmd == "stop":
        if not args:
            print("Usage: coolify.py stop APP_NAME")
            sys.exit(1)
        cmd_stop(args[0])
    elif cmd == "start":
        if not args:
            print("Usage: coolify.py start APP_NAME")
            sys.exit(1)
        cmd_start(args[0])
    elif cmd == "logs":
        if not args:
            print("Usage: coolify.py logs APP_NAME [--lines=N]")
            sys.exit(1)
        lines = 100
        for a in args[1:]:
            if a.startswith("--lines="):
                lines = int(a.split("=")[1])
        cmd_logs(args[0], lines)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
