import os
import requests
from dotenv import load_dotenv

load_dotenv()


class SmartrrClient:
    def __init__(self):
        self.token = os.getenv("SMARTRR_API_TOKEN")
        self.base_url = os.getenv("SMARTRR_API_BASE", "https://api.smartrr.com").rstrip("/")
        self.shop = os.getenv("SMARTRR_SHOP", "equestrian-labs.myshopify.com")
        self.subscriptions_endpoint = os.getenv("SMARTRR_SUBSCRIPTIONS_ENDPOINT", "/subscriptions")

        if not self.token:
            raise ValueError("Missing SMARTRR_API_TOKEN")

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def get(self, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"

        final_params = {
            "shop": self.shop,
        }

        if params:
            final_params.update(params)

        response = requests.get(
            url,
            headers=self.headers,
            params=final_params,
            timeout=60,
        )

        if response.status_code == 401:
            raise RuntimeError("Unauthorized. Revisa SMARTRR_API_TOKEN.")

        if response.status_code == 403:
            raise RuntimeError("Forbidden. El token no tiene permisos.")

        if response.status_code == 404:
            raise RuntimeError(f"Endpoint not found: {endpoint}")

        response.raise_for_status()
        return response.json()

    def get_subscriptions(self):
        return self.get(self.subscriptions_endpoint)
