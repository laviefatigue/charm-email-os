#!/usr/bin/env python3
"""
Atomically commit a set of rendered files to HireCharm/client-<slug>.

REFERENCE IMPLEMENTATION. Currently hard-coded paths; consumes the JSON map
emitted by synthesize_client_repo.py.

Reads the file map from stdin (or from a JSON file via --input). Each key is
the repo-relative path, each value is the full file content as a string.

Uses GitHub's git-data API (blobs + tree + commit + ref-update) to land all
changes as a single commit. This is idempotent at the commit level — re-running
with the same content creates a no-op commit (could be improved to skip if
nothing changed).

Repo creation from template (when the target repo doesn't exist yet) is in a
separate flow; this script assumes the repo exists.

Authentication via Charm Onboarder GitHub App. PEM + App ID at:
  d:/Work/Charm/.secrets/charm-onboarder.env
  d:/Work/Charm/.secrets/charm-onboarder.pem

TODO before bulk rollout:
  - Add --create-if-missing flag that does /repos/{template}/generate first
  - Add --skip-if-content-matches that diffs blobs before committing
  - Slug normalization helper (lowercase, strip non-alphanumeric, hyphen-separate)
  - Move charm-onboarder cred path to env vars

See ../../docs/dayai/HANDOFF_client_repo_pipeline.md for context.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import jwt  # PyJWT


# --- HARDCODED (see TODO in module docstring) ---

REPO_OWNER = 'HireCharm'
PEM_PATH = Path('d:/Work/Charm/.secrets/charm-onboarder.pem')
APP_ID = '3480661'
INSTALL_ID = '126503394'


def _mint_installation_token() -> str:
    """Mint a Charm Onboarder installation access token via JWT."""
    pem = PEM_PATH.read_text()
    now = int(time.time())
    app_jwt = jwt.encode(
        {'iat': now - 10, 'exp': now + 540, 'iss': APP_ID},
        pem,
        algorithm='RS256',
    )
    req = urllib.request.Request(
        f'https://api.github.com/app/installations/{INSTALL_ID}/access_tokens',
        method='POST',
        headers={
            'Authorization': f'Bearer {app_jwt}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'charm-onboarder',
        },
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
    return resp['token']


def _gh(token: str, path: str, method: str = 'GET', body: dict | None = None) -> dict:
    """Thin wrapper around GitHub API with the installation token."""
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'charm-onboarder',
        'Content-Type': 'application/json',
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f'https://api.github.com{path}', headers=headers, method=method, data=data)
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def commit_files_atomic(repo: str, files: dict[str, str], message: str) -> str:
    """Land all files in a single commit on main. Returns the new commit SHA."""
    token = _mint_installation_token()
    ref = _gh(token, f'/repos/{repo}/git/refs/heads/main')
    parent_sha = ref['object']['sha']
    base_tree_sha = _gh(token, f'/repos/{repo}/git/commits/{parent_sha}')['tree']['sha']

    tree_entries = []
    for path, content in files.items():
        blob = _gh(
            token,
            f'/repos/{repo}/git/blobs',
            method='POST',
            body={
                'content': base64.b64encode(content.encode('utf-8')).decode('ascii'),
                'encoding': 'base64',
            },
        )
        tree_entries.append({'path': path, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
        print(f'  blob {blob["sha"][:10]}  {path}  ({len(content)} chars)', file=sys.stderr)

    new_tree = _gh(
        token,
        f'/repos/{repo}/git/trees',
        method='POST',
        body={'base_tree': base_tree_sha, 'tree': tree_entries},
    )
    commit = _gh(
        token,
        f'/repos/{repo}/git/commits',
        method='POST',
        body={'message': message, 'tree': new_tree['sha'], 'parents': [parent_sha]},
    )
    _gh(
        token,
        f'/repos/{repo}/git/refs/heads/main',
        method='PATCH',
        body={'sha': commit['sha'], 'force': False},
    )
    return commit['sha']


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slug', required=True, help='Client slug (becomes HireCharm/client-<slug>)')
    parser.add_argument('--input', type=Path, default=None, help='JSON file mapping repo-relative path -> content. Defaults to stdin.')
    parser.add_argument('--message', default=None, help='Commit message. Auto-generated if omitted.')
    args = parser.parse_args()

    if args.input is not None:
        files = json.loads(args.input.read_text(encoding='utf-8'))
    else:
        files = json.loads(sys.stdin.read())

    if not isinstance(files, dict) or not files:
        print('No files provided (expected JSON object mapping path -> content)', file=sys.stderr)
        return 2

    repo = f'{REPO_OWNER}/client-{args.slug}'
    msg = args.message or f'chore: refresh enriched files from Day.AI + charm-email-os ({len(files)} files)'

    print(f'Committing {len(files)} file(s) to {repo}', file=sys.stderr)
    sha = commit_files_atomic(repo, files, msg)
    print(f'commit {sha[:10]}')
    print(f'https://github.com/{repo}/commit/{sha[:10]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
