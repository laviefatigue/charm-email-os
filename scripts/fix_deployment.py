"""Fix deployment entrypoint to use Linux path separators."""
import httpx

# Configuration
PREFECT_API_URL = "https://prefect.laviefatigue.com/api"
DEPLOYMENT_ID = "c1fa28f1-e601-4939-a22b-e677965fa890"

# CF Access headers
cf_headers = {
    "CF-Access-Client-Id": "c8133edc73827dea8ce2f9f773876a97.access",
    "CF-Access-Client-Secret": "245a089859489c4b0ba8f9f070065589258dbb15c8ba7fa8cbc53205620b503c",
    "Content-Type": "application/json",
}

# Fix entrypoint to use forward slashes (Linux)
update_data = {
    "entrypoint": "prefect_flows/push_to_emailbison.py:push_suggestion_to_emailbison",
}

with httpx.Client(timeout=30.0) as client:
    resp = client.patch(
        f"{PREFECT_API_URL}/deployments/{DEPLOYMENT_ID}",
        headers=cf_headers,
        json=update_data,
    )
    print(f"PATCH status: {resp.status_code}")

    if resp.status_code in (200, 204):
        print("Successfully updated entrypoint!")
        # Verify
        resp = client.get(f"{PREFECT_API_URL}/deployments/{DEPLOYMENT_ID}", headers=cf_headers)
        updated = resp.json()
        print(f"New entrypoint: {updated.get('entrypoint')}")
    else:
        print(f"Error: {resp.text}")
