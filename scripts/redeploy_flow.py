"""Redeploy push-to-emailbison Prefect flow with updated configuration."""
import os
import sys
import subprocess

# Set up environment
os.environ["PREFECT_API_URL"] = "https://prefect.laviefatigue.com/api"

# Monkey-patch httpx for CF Access before importing prefect
cf_client_id = "c8133edc73827dea8ce2f9f773876a97.access"
cf_client_secret = "245a089859489c4b0ba8f9f070065589258dbb15c8ba7fa8cbc53205620b503c"

import httpx

_original_async_init = httpx.AsyncClient.__init__
_original_sync_init = httpx.Client.__init__

def _patched_async_init(self, *args, **kwargs):
    headers = dict(kwargs.get('headers', {}) or {})
    headers['CF-Access-Client-Id'] = cf_client_id
    headers['CF-Access-Client-Secret'] = cf_client_secret
    kwargs['headers'] = headers
    _original_async_init(self, *args, **kwargs)

def _patched_sync_init(self, *args, **kwargs):
    headers = dict(kwargs.get('headers', {}) or {})
    headers['CF-Access-Client-Id'] = cf_client_id
    headers['CF-Access-Client-Secret'] = cf_client_secret
    kwargs['headers'] = headers
    _original_sync_init(self, *args, **kwargs)

httpx.AsyncClient.__init__ = _patched_async_init
httpx.Client.__init__ = _patched_sync_init

print("CF Access headers configured")

# Change to the project directory
os.chdir(r"D:\Work\charm-email-os")
sys.path.insert(0, r"D:\Work\charm-email-os")

# Import the flow
from prefect_flows.push_to_emailbison import push_suggestion_to_emailbison

# Use the Prefect 3.x flow.deploy() with source
import asyncio
from prefect.runner.storage import LocalStorage

async def do_deploy():
    # Deploy using flow.from_source() to specify pull steps
    deployment_id = await push_suggestion_to_emailbison.deploy(
        name="push-to-emailbison",
        work_pool_name="default",
        tags=["charm", "emailbison", "push", "manual"],
    )
    print(f"Deployment updated: {deployment_id}")
    return deployment_id

if __name__ == "__main__":
    result = asyncio.run(do_deploy())
    print(f"Done: {result}")
