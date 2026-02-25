#!/usr/bin/env python
import httpx
import sys

api_key = "33|hvosGDc0tkZihZhxJmXvpIZZ6qOjlINb3sSc0aPVa39c82f7"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "application/json"
}

all_emails = []
page = 1

while True:
    url = f"https://spellcast.hirecharm.com/api/sender-emails?per_page=100&page={page}"
    print(f"Fetching page {page}...", file=sys.stderr)

    try:
        resp = httpx.get(url, headers=headers, timeout=30)
        data = resp.json()
    except Exception as e:
        print(f"Error on page {page}: {e}", file=sys.stderr)
        break

    if "data" not in data:
        print(f"No data in response: {data}", file=sys.stderr)
        break

    if len(data["data"]) == 0:
        break

    for account in data["data"]:
        all_emails.append(account["email"])

    meta = data.get("meta", {})
    last_page = meta.get("last_page", 1)

    print(f"  Got {len(data['data'])} emails, page {page}/{last_page}", file=sys.stderr)

    if page >= last_page:
        break
    page += 1

print(f"\nTotal EmailBison accounts: {len(all_emails)}", file=sys.stderr)
print(f"Unique emails: {len(set(all_emails))}", file=sys.stderr)

# Output sorted unique emails to stdout
for email in sorted(set(all_emails)):
    print(email)
