"""Check worker environment by running shell commands."""
import httpx
import time

PREFECT_API_URL = "https://prefect.laviefatigue.com/api"

cf_headers = {
    "CF-Access-Client-Id": "c8133edc73827dea8ce2f9f773876a97.access",
    "CF-Access-Client-Secret": "245a089859489c4b0ba8f9f070065589258dbb15c8ba7fa8cbc53205620b503c",
    "Content-Type": "application/json",
}

with httpx.Client(timeout=30.0) as client:
    # Create a diagnostic flow
    resp = client.post(
        f"{PREFECT_API_URL}/flows/",
        headers=cf_headers,
        json={"name": "diagnostic-flow"},
    )
    if resp.status_code == 201:
        flow_id = resp.json().get("id")
    else:
        # Get existing
        resp = client.post(
            f"{PREFECT_API_URL}/flows/filter",
            headers=cf_headers,
            json={"flows": {"name": {"any_": ["diagnostic-flow"]}}},
        )
        flows = resp.json()
        flow_id = flows[0].get("id") if flows else None

    print(f"Flow ID: {flow_id}")

    # Create deployment with diagnostic pull steps
    deployment_data = {
        "name": "diagnostic",
        "flow_id": flow_id,
        "work_pool_name": "default",
        "entrypoint": "diagnostic.py:run",  # This won't exist but let's see the error
        "pull_steps": [
            {"prefect.deployments.steps.run_shell_script": {
                "script": "echo 'Current dir:' && pwd && echo 'Contents:' && ls -la /opt/ 2>&1 || echo 'No /opt/ dir' && echo 'Charm dir:' && ls -la /opt/charm-email-os 2>&1 || echo 'No charm dir' && echo 'Git status:' && cd /opt/charm-email-os && git status 2>&1 || echo 'Git failed'",
                "stream_output": True
            }},
        ],
        "tags": ["diagnostic"],
    }

    resp = client.post(
        f"{PREFECT_API_URL}/deployments/",
        headers=cf_headers,
        json=deployment_data,
    )
    print(f"Create deployment status: {resp.status_code}")

    if resp.status_code in (200, 201):
        deployment = resp.json()
        deployment_id = deployment.get('id')
        print(f"Deployment ID: {deployment_id}")

        # Trigger it
        resp = client.post(
            f"{PREFECT_API_URL}/deployments/{deployment_id}/create_flow_run",
            headers=cf_headers,
            json={},
        )
        if resp.status_code in (200, 201):
            flow_run = resp.json()
            print(f"Flow run ID: {flow_run.get('id')}")
            print("Waiting 20 seconds for flow run...")
            time.sleep(20)

            # Check status
            resp = client.get(
                f"{PREFECT_API_URL}/flow_runs/{flow_run.get('id')}",
                headers=cf_headers,
            )
            run_data = resp.json()
            print(f"State: {run_data.get('state_name')}")
            print(f"Message: {run_data.get('state', {}).get('message', 'N/A')}")
    else:
        print(f"Error: {resp.text}")
