"""
Hypertide Automation Pipeline Scripts.

A modular daisy chain of scripts for automating domain purchases,
inbox provisioning, and Email Bison integration.

Scripts:
    check_domains       - Query DB for approved domains
    purchase_domains    - Browser automation to buy domains from Hypertide
    generate_inboxes    - Create inbox specs from purchased domains
    provision_inboxes   - Browser automation to set up inboxes in Hypertide
    upload_to_emailbison - API call to add inboxes to workspace

Exit Codes:
    0 - Success
    1 - Partial failure / No items found
    2 - Total failure / Error
    3 - Awaiting human approval (checkpoint mode)
"""

__all__ = [
    "check_domains",
    "purchase_domains",
    "generate_inboxes",
    "provision_inboxes",
    "upload_to_emailbison",
]
