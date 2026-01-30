"""Create a minimal diagnostic deployment."""
import httpx
import time

PREFECT_API_URL = "https://prefect.laviefatigue.com/api"

cf_headers = {
    "CF-Access-Client-Id": "c8133edc73827dea8ce2f9f773876a97.access",
    "CF-Access-Client-Secret": "245a089859489c4b0ba8f9f070065589258dbb15c8ba7fa8cbc53205620b503c",
    "Content-Type": "application/json",
}

with httpx.Client(timeout=30.0) as client:
    # Create/get diagnostic flow
    resp = client.post(f"{PREFECT_API_URL}/flows/", headers=cf_headers, json={"name": "diagnostic"})
    if resp.status_code == 201:
        flow_id = resp.json().get("id")
    else:
        resp = client.post(f"{PREFECT_API_URL}/flows/filter", headers=cf_headers, json={"flows": {"name": {"any_": ["diagnostic"]}}})
        flows = resp.json()
        flow_id = flows[0].get("id") if flows else None
    print(f"Flow ID: {flow_id}")

    # Create deployment with ONLY a simple echo command - no files needed
    # This tests if basic shell commands work
    deployment_data = {
        "name": "diagnostic-v2",
        "flow_id": flow_id,
        "work_pool_name": "default",
        # Use a fake entrypoint - the flow will fail but we can see if pull steps run
        "entrypoint": "nonexistent.py:test",
        "pull_steps": [
            {"prefect.deployments.steps.run_shell_script": {
                "script": "echo 'DIAGNOSTIC: Shell works!' && whoami && pwd && ls -la /opt/ 2>&1 | head -20",
                "stream_output": True
            }},
        ],
        "tags": ["diagnostic"],
    }

    resp = client.post(f"{PREFECT_API_URL}/deployments/", headers=cf_headers, json=deployment_data)
    print(f"Create deployment status: {resp.status_code}")

    if resp.status_code in (200, 201):
        deployment = resp.json()
        deployment_id = deployment.get('id')
        print(f"Deployment ID: {deployment_id}")

        # Trigger it
        resp = client.post(f"{PREFECT_API_URL}/deployments/{deployment_id}/create_flow_run", headers=cf_headers, json={})
        if resp.status_code in (200, 201):
            flow_run = resp.json()
            flow_run_id = flow_run.get('id')
            print(f"Flow run ID: {flow_run_id}")

            # Wait and check
            print("Waiting 15 seconds...")
            time.sleep(15)

            resp = client.get(f"{PREFECT_API_URL}/flow_runs/{flow_run_id}", headers=cf_headers)
            run_data = resp.json()
            print(f"State: {run_data.get('state_name')}")
            print(f"Message: {run_data.get('state', {}).get('message', 'N/A')}")
    else:
        print(f"Error: {resp.text}")
