import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("SMARTRR_API_TOKEN")
BASE_URL = os.getenv("SMARTRR_API_BASE", "https://api.smartrr.com").rstrip("/")
SHOP = os.getenv("SMARTRR_SHOP", "equestrian-labs.myshopify.com")

if not TOKEN:
    raise ValueError("Missing SMARTRR_API_TOKEN")

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

candidate_endpoints = [
    "/subscriptions",
    "/api/subscriptions",
    "/v1/subscriptions",
    "/api/v1/subscriptions",
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
]

print("Testing Smartrr API")
print(f"Base URL: {BASE_URL}")
print(f"Shop: {SHOP}")
print("-" * 80)

for endpoint in candidate_endpoints:
    for params in params_options:
        url = f"{BASE_URL}{endpoint}"

        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=30,
            )

            print(f"{endpoint:<25} params={str(params):<45} status={response.status_code}")

            if response.status_code == 200:
                print("")
                print("✅ WORKING ENDPOINT FOUND")
                print(f"Endpoint: {endpoint}")
                print(f"Params: {params}")

                try:
                    data = response.json()
                    if isinstance(data, dict):
                        print(f"Response keys: {list(data.keys())[:20]}")
                    elif isinstance(data, list):
                        print(f"Rows: {len(data)}")
                except Exception:
                    print("Response is not JSON")

                raise SystemExit(0)

        except requests.RequestException as error:
            print(f"{endpoint:<25} ERROR: {error}")

print("")
print("❌ No working endpoint found.")
print("If all are 401, the token is wrong.")
print("If all are 403, the token has no permission.")
print("If all are 404, the endpoint path is different.")
