import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("SMARTRR_API_TOKEN")
BASE_URL = os.getenv("SMARTRR_API_BASE", "https://api.smartrr.com").rstrip("/")
ENDPOINT = os.getenv("SMARTRR_SUBSCRIPTIONS_ENDPOINT", "/vendor/purchase-state")

if not TOKEN:
    raise ValueError("Missing SMARTRR_API_TOKEN")

headers_list = [
    {
        "label": "x-smartrr-access-token",
        "headers": {
            "x-smartrr-access-token": TOKEN,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    },
    {
        "label": "Bearer",
        "headers": {
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    },
]

statuses = ["ACTIVE", "PAUSED", "CANCELLED"]

print("Testing Smartrr API")
print(f"Base URL: {BASE_URL}")
print(f"Endpoint: {ENDPOINT}")
print("-" * 100)

for auth in headers_list:
    print("")
    print(f"AUTH MODE: {auth['label']}")
    print("-" * 100)

    for status in statuses:
        params = {
            "pageSize": 5,
            "pageNumber": 0,
            "filterEquals[purchaseStateStatus]": status,
            "include": "items,lineItems,orderLineItems,stLineItems,product,variant,purchasableVariant,orders",
        }

        response = requests.get(
            f"{BASE_URL}{ENDPOINT}",
            headers=auth["headers"],
            params=params,
            timeout=30,
        )

        content_type = response.headers.get("content-type", "")
        preview = response.text[:200].replace("\n", " ").replace("\r", " ")

        print(f"status_filter={status:<10} http={response.status_code:<4} type={content_type}")

        if response.status_code == 200:
            try:
                data = response.json()
            except Exception:
                print(f"  Non-JSON preview: {preview}")
                continue

            if isinstance(data, dict):
                print(f"  Response keys: {list(data.keys())[:30]}")
                print(f"  Preview JSON: {str(data)[:300]}")
            elif isinstance(data, list):
                print(f"  Rows: {len(data)}")

print("")
print("Probe finished.")
