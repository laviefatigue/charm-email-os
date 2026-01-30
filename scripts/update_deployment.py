"""Update push-to-emailbison deployment pull steps via REST API."""
import os
import json
import httpx

# Configuration
PREFECT_API_URL = "https://prefect.laviefatigue.com/api"
DEPLOYMENT_ID = "c1fa28f1-e601-4939-a22b-e677965fa890"  # From previous deployment

# CF Access headers
cf_headers = {
    "CF-Access-Client-Id": "c8133edc73827dea8ce2f9f773876a97.access",
    "CF-Access-Client-Secret": "245a089859489c4b0ba8f9f070065589258dbb15c8ba7fa8cbc53205620b503c",
    "Content-Type": "application/json",
}

# New pull steps
new_pull_steps = [
    {"prefect.deployments.steps.set_working_directory": {"directory": "/opt/charm-email-os"}},
    {"prefect.deployments.steps.run_shell_script": {"script": "git pull origin master", "stream_output": True}},
]

# Update deployment
with httpx.Client(timeout=30.0) as client:
    # First, get current deployment
    resp = client.get(f"{PREFECT_API_URL}/deployments/{DEPLOYMENT_ID}", headers=cf_headers)
    print(f"GET deployment status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"Error: {resp.text}")
        exit(1)

    current = resp.json()
    print(f"Current deployment: {current.get('name')}")
    print(f"Current pull_steps: {current.get('pull_steps')}")

    # Update with new pull steps
    update_data = {
        "pull_steps": new_pull_steps,
    }

    resp = client.patch(
        f"{PREFECT_API_URL}/deployments/{DEPLOYMENT_ID}",
        headers=cf_headers,
        json=update_data,
    )
    print(f"PATCH deployment status: {resp.status_code}")

    if resp.status_code in (200, 204):
        print("Successfully updated deployment pull_steps!")
        # Verify
        resp = client.get(f"{PREFECT_API_URL}/deployments/{DEPLOYMENT_ID}", headers=cf_headers)
        updated = resp.json()
        print(f"New pull_steps: {updated.get('pull_steps')}")
    else:
        print(f"Error: {resp.text}")
