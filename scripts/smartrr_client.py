import os
import requests
from dotenv import load_dotenv

load_dotenv()


class SmartrrClient:
    def __init__(self):
        self.token = os.getenv("SMARTRR_API_TOKEN")
        self.base_url = os.getenv("SMARTRR_API_BASE", "https://api.smartrr.com").rstrip("/")
        self.subscriptions_endpoint = os.getenv(
            "SMARTRR_SUBSCRIPTIONS_ENDPOINT",
            "/vendor/purchase-state",
        )

        if not self.token:
            raise ValueError("Missing SMARTRR_API_TOKEN")

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def get(self, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"

        final_params = {
            "pageSize": 100,
            "pageNumber": 0,
        }

        if params:
            final_params.update(params)

        response = requests.get(
            url,
            headers=self.headers,
            params=final_params,
            timeout=60,
        )

        content_type = response.headers.get("content-type", "")
        preview = response.text[:300].replace("\n", " ").replace("\r", " ")

        if response.status_code == 401:
            raise RuntimeError("Unauthorized. Revisa SMARTRR_API_TOKEN.")

        if response.status_code == 403:
            raise RuntimeError("Forbidden. El token no tiene permisos.")

        if response.status_code == 404:
            raise RuntimeError(f"Endpoint not found: {endpoint}")

        response.raise_for_status()

        try:
            return response.json()
        except Exception as error:
            raise RuntimeError(
                f"Smartrr returned non-JSON response. "
                f"Endpoint={endpoint}. "
                f"Status={response.status_code}. "
                f"Content-Type={content_type}. "
                f"Preview={preview}"
            ) from error

    def get_subscriptions(self):
        return self.get(self.subscriptions_endpoint)
