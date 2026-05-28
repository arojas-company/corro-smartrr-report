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

    def _headers_token(self):
        return {
            "x-smartrr-access-token": self.token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _headers_bearer(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(self, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"

        response = requests.get(
            url,
            headers=self._headers_token(),
            params=params or {},
            timeout=60,
        )

        if response.status_code in [401, 403]:
            response = requests.get(
                url,
                headers=self._headers_bearer(),
                params=params or {},
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

    def _extract_items(self, payload):
        if isinstance(payload, list):
            return payload

        if not isinstance(payload, dict):
            return []

        for key in [
            "data",
            "items",
            "results",
            "records",
            "purchaseStates",
            "purchase_states",
            "purchaseState",
            "purchase_state",
            "subscriptions",
            "subscription_contracts",
            "contracts",
        ]:
            value = payload.get(key)

            if isinstance(value, list):
                return value

            if isinstance(value, dict):
                nested = self._extract_items(value)
                if nested:
                    return nested

        return []

    def get_purchase_states(self):
        all_states = []
        seen_ids = set()
        page_size = 250

        for status in ["ACTIVE", "PAUSED", "CANCELLED"]:
            page_number = 0

            while page_number < 200:
                params = {
                    "pageSize": page_size,
                    "pageNumber": page_number,
                    "filterEquals[purchaseStateStatus]": status,
                    "include": "items,lineItems,orderLineItems,stLineItems,product,variant,purchasableVariant,orders",
                }

                payload = self._request(self.subscriptions_endpoint, params=params)
                items = self._extract_items(payload)

                print(f"Smartrr {status} page {page_number}: {len(items)} rows")

                if not items:
                    break

                for item in items:
                    if isinstance(item, dict):
                        item["_smartrr_status_hint"] = status.lower()
                        item_id = (
                            item.get("id")
                            or item.get("purchaseStateId")
                            or item.get("subscriptionId")
                            or str(item)[:200]
                        )

                        dedupe_key = f"{status}:{item_id}"

                        if dedupe_key not in seen_ids:
                            seen_ids.add(dedupe_key)
                            all_states.append(item)

                if len(items) < page_size:
                    break

                page_number += 1

        print(f"Smartrr purchase states total: {len(all_states)}")
        return all_states

    def get_subscriptions(self):
        return self.get_purchase_states()
