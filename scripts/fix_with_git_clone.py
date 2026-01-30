"""Fix deployment using proper Prefect git_clone step."""
import httpx

PREFECT_API_URL = "https://prefect.laviefatigue.com/api"
DEPLOYMENT_ID = "c1fa28f1-e601-4939-a22b-e677965fa890"

cf_headers = {
    "CF-Access-Client-Id": "c8133edc73827dea8ce2f9f773876a97.access",
    "CF-Access-Client-Secret": "245a089859489c4b0ba8f9f070065589258dbb15c8ba7fa8cbc53205620b503c",
    "Content-Type": "application/json",
}

# Use Prefect's built-in git_clone step
# This will clone into a temp directory and the flow will run from there
new_pull_steps = [
    {"prefect.deployments.steps.git_clone": {
        "repository": "https://github.com/laviefatigue/charm-email-os.git",
        "branch": "master",
    }},
]

with httpx.Client(timeout=30.0) as client:
    # Update deployment
    resp = client.patch(
        f"{PREFECT_API_URL}/deployments/{DEPLOYMENT_ID}",
        headers=cf_headers,
        json={"pull_steps": new_pull_steps},
    )
    print(f"PATCH status: {resp.status_code}")

    if resp.status_code in (200, 204):
        print("Successfully updated to use git_clone!")
        # Verify
        resp = client.get(f"{PREFECT_API_URL}/deployments/{DEPLOYMENT_ID}", headers=cf_headers)
        updated = resp.json()
        print(f"Pull steps: {updated.get('pull_steps')}")
    else:
        print(f"Error: {resp.text}")
