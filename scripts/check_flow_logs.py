"""Check flow run logs from Prefect API."""
import httpx

PREFECT_API_URL = "https://prefect.laviefatigue.com/api"
FLOW_RUN_ID = "06c662f9-23c4-4876-8bc1-3f62c441ddf8"

cf_headers = {
    "CF-Access-Client-Id": "c8133edc73827dea8ce2f9f773876a97.access",
    "CF-Access-Client-Secret": "245a089859489c4b0ba8f9f070065589258dbb15c8ba7fa8cbc53205620b503c",
    "Content-Type": "application/json",
}

with httpx.Client(timeout=30.0) as client:
    # Get flow run details
    print("=== Flow Run Details ===")
    resp = client.get(f"{PREFECT_API_URL}/flow_runs/{FLOW_RUN_ID}", headers=cf_headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"Name: {data.get('name')}")
        print(f"State: {data.get('state_name')}")
        print(f"State type: {data.get('state_type')}")
        state = data.get('state', {})
        if isinstance(state, dict):
            print(f"Message: {state.get('message')}")
            if 'data' in state:
                print(f"State data: {state.get('data')}")
        print(f"Start time: {data.get('start_time')}")
        print(f"End time: {data.get('end_time')}")
        print(f"Infrastructure PID: {data.get('infrastructure_pid')}")

    # Try to get logs
    print("\n=== Flow Run Logs ===")
    resp = client.post(
        f"{PREFECT_API_URL}/logs/filter",
        headers=cf_headers,
        json={
            "logs": {
                "flow_run_id": {"any_": [FLOW_RUN_ID]}
            },
            "sort": "TIMESTAMP_ASC",
            "limit": 100
        }
    )
    if resp.status_code == 200:
        logs = resp.json()
        if logs:
            for log in logs:
                print(f"[{log.get('level_name', 'INFO')}] {log.get('message')}")
        else:
            print("No logs found for this flow run")
    else:
        print(f"Failed to get logs: {resp.status_code} - {resp.text}")

    # Check recent flow runs
    print("\n=== Recent Flow Runs (last 5) ===")
    resp = client.post(
        f"{PREFECT_API_URL}/flow_runs/filter",
        headers=cf_headers,
        json={
            "sort": "START_TIME_DESC",
            "limit": 5
        }
    )
    if resp.status_code == 200:
        runs = resp.json()
        for run in runs:
            state = run.get('state', {})
            msg = state.get('message', 'N/A') if isinstance(state, dict) else 'N/A'
            print(f"  {run.get('id')[:8]}... | {run.get('state_name'):15} | {run.get('start_time') or 'Not started'} | {msg[:50]}")
