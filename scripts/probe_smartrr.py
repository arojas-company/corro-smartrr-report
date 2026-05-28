import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("SMARTRR_API_TOKEN")
BASE_URL = os.getenv("SMARTRR_API_BASE", "https://api.smartrr.com").rstrip("/")

if not TOKEN:
    raise ValueError("Missing SMARTRR_API_TOKEN")

headers_list = [
    {
        "label": "Bearer",
        "headers": {
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
        },
    },
    {
        "label": "X-Smartrr-Access-Token",
        "headers": {
            "X-Smartrr-Access-Token": TOKEN,
            "Accept": "application/json",
        },
    },
]

endpoints = [
    "/vendor/purchase-state",
    "/vendor/customer-relationship",
]

params = {
    "pageSize": 5,
    "pageNumber": 0,
}

print("Testing Smartrr API")
print(f"Base URL: {BASE_URL}")
print("-" * 90)

for auth in headers_list:
    print(f"\nAUTH MODE: {auth['label']}")
    print("-" * 90)

    for endpoint in endpoints:
        url = f"{BASE_URL}{endpoint}"

        response = requests.get(
            url,
            headers=auth["headers"],
            params=params,
            timeout=30,
        )

        content_type = response.headers.get("content-type", "")
        preview = response.text[:200].replace("\n", " ").replace("\r", " ")

        print(f"{endpoint:<35} status={response.status_code} type={content_type}")

        if response.status_code == 200:
            try:
                data = response.json()
            except Exception:
                print(f"  Non-JSON preview: {preview}")
                continue

            print("\n✅ WORKING JSON ENDPOINT FOUND")
            print(f"Endpoint: {endpoint}")
            print(f"Auth mode: {auth['label']}")

            if isinstance(data, dict):
                print(f"Response keys: {list(data.keys())[:30]}")
            elif isinstance(data, list):
                print(f"Rows: {len(data)}")

            raise SystemExit(0)

print("\n❌ No working JSON endpoint found.")
raise SystemExit(1)
