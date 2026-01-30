"""Fix deployment pull steps to handle missing directory."""
import httpx

PREFECT_API_URL = "https://prefect.laviefatigue.com/api"
DEPLOYMENT_ID = "c1fa28f1-e601-4939-a22b-e677965fa890"

cf_headers = {
    "CF-Access-Client-Id": "c8133edc73827dea8ce2f9f773876a97.access",
    "CF-Access-Client-Secret": "245a089859489c4b0ba8f9f070065589258dbb15c8ba7fa8cbc53205620b503c",
    "Content-Type": "application/json",
}

# Updated pull steps that handle missing directory
new_pull_steps = [
    # First, ensure the directory exists and has the repo
    {"prefect.deployments.steps.run_shell_script": {
        "script": """
set -e
echo "=== Checking environment ==="
echo "Current user: $(whoami)"
echo "Python: $(which python3 || which python)"
echo "Working dir: $(pwd)"

# Check if directory exists
if [ ! -d /opt/charm-email-os ]; then
    echo "Directory doesn't exist, cloning..."
    mkdir -p /opt
    cd /opt
    git clone https://github.com/laviefatigue/charm-email-os.git
else
    echo "Directory exists, pulling..."
    cd /opt/charm-email-os
    git pull origin master || echo "Git pull failed, continuing..."
fi

# Install dependencies
echo "Installing dependencies..."
cd /opt/charm-email-os
pip install httpx asyncpg prefect --quiet || pip3 install httpx asyncpg prefect --quiet

echo "=== Setup complete ==="
ls -la /opt/charm-email-os/prefect_flows/
""",
        "stream_output": True
    }},
    # Then set working directory
    {"prefect.deployments.steps.set_working_directory": {"directory": "/opt/charm-email-os"}},
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
        print("Successfully updated pull_steps!")
        # Verify
        resp = client.get(f"{PREFECT_API_URL}/deployments/{DEPLOYMENT_ID}", headers=cf_headers)
        updated = resp.json()
        print(f"New pull_steps count: {len(updated.get('pull_steps', []))}")
    else:
        print(f"Error: {resp.text}")
