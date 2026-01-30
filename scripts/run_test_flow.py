"""Run the test flow."""
import httpx

# Configuration
PREFECT_API_URL = "https://prefect.laviefatigue.com/api"
DEPLOYMENT_ID = "9a7fb8d5-b77d-412b-9552-1de06663ad50"

# CF Access headers
cf_headers = {
    "CF-Access-Client-Id": "c8133edc73827dea8ce2f9f773876a97.access",
    "CF-Access-Client-Secret": "245a089859489c4b0ba8f9f070065589258dbb15c8ba7fa8cbc53205620b503c",
    "Content-Type": "application/json",
}

with httpx.Client(timeout=30.0) as client:
    # Create a flow run
    resp = client.post(
        f"{PREFECT_API_URL}/deployments/{DEPLOYMENT_ID}/create_flow_run",
        headers=cf_headers,
        json={"parameters": {"message": "Test from API"}},
    )
    print(f"Create flow run status: {resp.status_code}")
    if resp.status_code in (200, 201):
        flow_run = resp.json()
        print(f"Flow run ID: {flow_run.get('id')}")
        print(f"Flow run name: {flow_run.get('name')}")
    else:
        print(f"Error: {resp.text}")
