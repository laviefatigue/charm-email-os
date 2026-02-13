import asyncio
import httpx
import json

API_URL = 'https://spellcast.hirecharm.com'
API_KEY = '33|hvosGDc0tkZihZhxJmXvpIZZ6qOjlINb3sSc0aPVa39c82f7'

async def test_tag():
    async with httpx.AsyncClient(headers={'Authorization': f'Bearer {API_KEY}'}) as client:
        # Get one pending kill queue item
        # First switch to workspace 13 (Spout - has most pending)
        r = await client.post(f'{API_URL}/api/workspaces/v1.1/switch-workspace', json={'team_id': 13})
        print(f'Switch to workspace 13: {r.status_code}')
        
        # List tags
        r = await client.get(f'{API_URL}/api/tags')
        print(f'Tags status: {r.status_code}')
        tags = r.json().get('data', [])
        print(f'Tags found: {[t.get("name") for t in tags]}')
        
        # Create test tag
        r = await client.post(f'{API_URL}/api/tags', json={'name': 'delete_queue_20260212_test'})
        print(f'Create tag status: {r.status_code}')
        if r.status_code == 200 or r.status_code == 201:
            tag_id = r.json().get('id') or r.json().get('data', {}).get('id')
            print(f'Tag ID: {tag_id}')
            
            # Get a sender account from this workspace
            r = await client.get(f'{API_URL}/api/sender-emails?page=1&per_page=1')
            print(f'Sender emails status: {r.status_code}')
            if r.status_code == 200:
                accounts = r.json().get('data', [])
                if accounts:
                    account_id = accounts[0].get('id')
                    account_email = accounts[0].get('email')
                    print(f'Test account: {account_email} (ID: {account_id})')
                    
                    # Try to tag it
                    r = await client.post(f'{API_URL}/api/tags/attach-to-sender-emails', 
                        json={'tag_ids': [tag_id], 'sender_email_ids': [account_id]})
                    print(f'Tag inbox status: {r.status_code}')
                    print(f'Response: {r.text[:500]}')

asyncio.run(test_tag())
