"""Redeploy Prefect flow with CF Access headers."""
import os
import subprocess

# Set CF Access headers
os.environ["PREFECT_API_URL"] = "https://prefect.laviefatigue.com/api"

# Monkey-patch httpx to include CF Access headers
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

# Now run Prefect deploy
from prefect.deployments import deploy

# Use sync deployment
import asyncio
from prefect import flow

# Load the flow
import sys
sys.path.insert(0, r"D:\Work\charm-email-os")

from prefect_flows.push_to_emailbison import push_suggestion_to_emailbison

# Deploy
async def do_deploy():
    from prefect.runner.storage import GitRepository
    from prefect.deployments import Deployment

    deployment = await Deployment.build_from_flow(
        flow=push_suggestion_to_emailbison,
        name="push-to-emailbison",
        work_pool_name="default-agent-pool",
        tags=["charm", "emailbison", "push", "manual"],
    )
    deployment_id = await deployment.apply()
    print(f"Deployment created: {deployment_id}")
    return deployment_id

if __name__ == "__main__":
    result = asyncio.run(do_deploy())
    print(f"Done: {result}")
