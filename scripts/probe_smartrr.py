import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("SMARTRR_API_TOKEN")
BASE_URL = os.getenv("SMARTRR_API_BASE", "https://api.smartrr.com").rstrip("/")
SHOP = os.getenv("SMARTRR_SHOP", "equestrian-labs.myshopify.com")

if not TOKEN:
    raise ValueError("Missing SMARTRR_API_TOKEN")

header_options = [
    {
        "label": "Authorization Bearer",
        "headers": {
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    },
    {
        "label": "X-Smartrr-Access-Token",
        "headers": {
            "X-Smartrr-Access-Token": TOKEN,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    },
    {
        "label": "x-smartrr-access-token",
        "headers": {
            "x-smartrr-access-token": TOKEN,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    },
    {
        "label": "X-API-Key",
        "headers": {
            "X-API-Key": TOKEN,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    },
]

candidate_endpoints = [
    "/subscriptions",
    "/api/subscriptions",
    "/v1/subscriptions",
    "/api/v1/subscriptions",
    "/merchant/subscriptions",
    "/api/merchant/subscriptions",
    "/shopify/subscriptions",
    "/shopify/merchant/api/subscriptions",
    "/customers",
    "/api/customers",
    "/v1/customers",
    "/api/v1/customers",
    "/orders",
    "/api/orders",
    "/v1/orders",
    "/api/v1/orders",
]

params_options = [
    {},
    {"shop": SHOP},
    {"shopify_domain": SHOP},
    {"shop_domain": SHOP},
    {"shopify_shop_domain": SHOP},
]

print("Testing Smartrr API")
print(f"Base URL: {BASE_URL}")
print(f"Shop: {SHOP}")
print("-" * 100)

for auth in header_options:
    print("")
    print(f"AUTH MODE: {auth['label']}")
    print("-" * 100)

    for endpoint in candidate_endpoints:
        for params in params_options:
            url = f"{BASE_URL}{endpoint}"

            try:
                response = requests.get(
                    url,
                    headers=auth["headers"],
                    params=params,
                    timeout=30,
                )

                content_type = response.headers.get("content-type", "")
                preview = response.text[:80].replace("\n", " ").replace("\r", " ")

                print(
                    f"{endpoint:<38} params={str(params):<48} "
                    f"status={response.status_code:<4} type={content_type[:30]}"
                )

                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception:
                        print(f"  ⚠️  200 but not JSON. Preview: {preview}")
                        continue

                    print("")
                    print("✅ WORKING JSON ENDPOINT FOUND")
                    print(f"Endpoint: {endpoint}")
                    print(f"Params: {params}")
                    print(f"Auth mode: {auth['label']}")

                    if isinstance(data, dict):
                        print(f"Response keys: {list(data.keys())[:20]}")
                    elif isinstance(data, list):
                        print(f"Rows: {len(data)}")

                    raise SystemExit(0)

            except requests.RequestException as error:
                print(f"{endpoint:<38} ERROR: {error}")

print("")
print("❌ No working JSON endpoint found.")
print("Copy this full log and send it here.")
print("Important: do not paste your API token.")
