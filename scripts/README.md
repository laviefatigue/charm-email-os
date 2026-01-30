# scripts/

One-off maintenance, debugging, and deployment scripts. These are **not** part of the production application — they are utility scripts used during development and troubleshooting.

## Scripts

| Script | Purpose |
|--------|---------|
| `check_flow_logs.py` | Check Prefect flow execution logs |
| `check_worker_env.py` | Verify worker environment variables |
| `fix_deployment.py` | Fix Coolify deployment issues |
| `fix_pull_steps.py` | Fix git pull steps in CI |
| `fix_with_git_clone.py` | Alternative deployment via git clone |
| `fix_with_pip_first.py` | Fix pip dependency ordering |
| `redeploy_flow.py` | Trigger Prefect flow redeployment |
| `redeploy_prefect.py` | Redeploy Prefect worker |
| `run_test_flow.py` | Run test Prefect flow locally |
| `simple_diagnostic.py` | Basic system diagnostic checks |
| `test_domain_search.py` | Test domain search/registrar integration |
| `test_local_browser.py` | Test local Playwright browser setup |
| `update_deployment.py` | Update Coolify deployment configuration |

## Usage

These scripts are typically run manually from the project root:

```bash
python scripts/fix_deployment.py
```

Most require the `.env` file to be present for database/API credentials.
