from pathlib import Path
from datetime import datetime, timezone
import os
import json
import math
import re

import pandas as pd

from smartrr_client import SmartrrClient


DATA_DIR = Path("data")
REPORTS_DIR = Path("reports")

DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

REPORT_YEAR = os.getenv("REPORT_YEAR", "2026")


def clean_json(value):
    if value is None:
        return None

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}

    if isinstance(value, list):
        return [clean_json(v) for v in value]

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    return value


def normalize_api_response(payload):
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in [
            "data",
            "items",
            "results",
            "records",
            "purchaseStates",
            "purchase_states",
            "subscriptions",
        ]:
            if key in payload and isinstance(payload[key], list):
                return payload[key]

        return [payload]

    return []


def dig(obj, path, default=""):
    cur = obj

    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except Exception:
                return default
        else:
            return default

        if cur in [None, ""]:
            return default

    return cur


def deep_find(obj, keys, depth=0):
    if depth > 8 or obj is None:
        return ""

    wanted = {re.sub(r"[^a-z0-9]", "", k.lower()) for k in keys}

    if isinstance(obj, dict):
        for k, v in obj.items():
            nk = re.sub(r"[^a-z0-9]", "", str(k).lower())

            if nk in wanted and v not in [None, ""]:
                return v

            if isinstance(v, (dict, list)):
                found = deep_find(v, keys, depth + 1)
                if found not in [None, ""]:
                    return found

    if isinstance(obj, list):
        for item in obj:
            found = deep_find(item, keys, depth + 1)
            if found not in [None, ""]:
                return found

    return ""


def to_float(value):
    try:
        if value in [None, "", "None", "null"]:
            return 0.0
        return float(str(value).replace(",", "").replace("USD", "").strip())
    except Exception:
        return 0.0


def money_to_usd(value):
    n = to_float(value)

    if abs(n) >= 1000:
        return round(n / 100, 2)

    return round(n, 2)


def parse_date(value):
    if value in [None, "", "None", "null"]:
        return ""

    s = str(value).strip()

    for fmt in [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
    ]:
        try:
            return datetime.strptime(s[:26], fmt).date().isoformat()
        except Exception:
            pass

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return ""


def get_month(value):
    parsed = parse_date(value)

    if not parsed:
        return "Unknown"

    return parsed[:7]


def get_status(sub):
    status = (
        sub.get("_smartrr_status_hint")
        or sub.get("purchaseStateStatus")
        or sub.get("purchase_state_status")
        or sub.get("status")
        or sub.get("subscriptionStatus")
        or ""
    )

    return str(status).strip().upper() or "UNKNOWN"


def get_line_items(sub):
    for key in ["stLineItems", "lineItems", "orderLineItems", "items"]:
        value = sub.get(key)

        if isinstance(value, list) and value:
            return value

    return [{}]


def get_product_title(line, sub):
    candidates = [
        dig(line, "purchasableAndPurchasableVariantName"),
        dig(line, "purchasable_and_purchasable_variant_name"),
        dig(line, "productTitle"),
        dig(line, "product_title"),
        dig(line, "variantTitle"),
        dig(line, "variant_title"),
        dig(line, "title"),
        dig(line, "name"),
        dig(line, "vnt.product.title"),
        dig(line, "vnt.product.name"),
        dig(line, "vnt.title"),
        dig(line, "vnt.name"),
        dig(sub, "planTitle"),
        dig(sub, "plan_title"),
        dig(sub, "productTitle"),
        dig(sub, "product_title"),
        dig(sub, "title"),
        deep_find(line, [
            "productTitle",
            "product_title",
            "variantTitle",
            "variant_title",
            "title",
            "name",
        ]),
    ]

    for value in candidates:
        text = str(value or "").strip()

        if text and text not in ["Default Title", "ø", "None"]:
            return text

    return "Unknown Product"


def get_sku(line):
    candidates = [
        line.get("currentSku") if isinstance(line, dict) else "",
        line.get("sku") if isinstance(line, dict) else "",
        dig(line, "vnt.sku"),
        dig(line, "variant.sku"),
        deep_find(line, ["sku", "currentSku"]),
    ]

    for value in candidates:
        text = str(value or "").strip()

        if text:
            return text

    return ""


def get_quantity(line):
    qty = (
        line.get("quantity")
        or line.get("qty")
        or deep_find(line, ["quantity", "qty"])
        or 1
    )

    n = to_float(qty)

    return int(n) if n > 0 else 1


def get_revenue(line, qty):
    candidates = [
        line.get("priceAfterDiscounts") if isinstance(line, dict) else "",
        line.get("price_after_discounts") if isinstance(line, dict) else "",
        line.get("basePrice") if isinstance(line, dict) else "",
        line.get("price") if isinstance(line, dict) else "",
        line.get("linePrice") if isinstance(line, dict) else "",
        line.get("totalPrice") if isinstance(line, dict) else "",
        dig(line, "vnt.price"),
        dig(line, "variant.price"),
    ]

    for value in candidates:
        if value not in [None, ""]:
            return round(money_to_usd(value) * qty, 2)

    return 0.0


def build_raw_rows(subscriptions):
    rows = []

    for sub in subscriptions:
        if not isinstance(sub, dict):
            continue

        status = get_status(sub)
        created_at = parse_date(
            sub.get("createdDate")
            or sub.get("createdAt")
            or sub.get("created_at")
            or sub.get("externalSubscriptionCreatedDate")
        )

        month = get_month(created_at)

        customer_name = (
            dig(sub, "customer.name")
            or dig(sub, "customer.fullName")
            or dig(sub, "customer.full_name")
            or sub.get("customerName")
            or sub.get("customer_name")
            or deep_find(sub, ["customerName", "customer_name", "name", "fullName"])
        )

        email = (
            dig(sub, "customer.email")
            or sub.get("email")
            or sub.get("customerEmail")
            or sub.get("customer_email")
            or deep_find(sub, ["email", "customerEmail", "customer_email"])
        )

        phone = (
            dig(sub, "customer.phone")
            or sub.get("phone")
            or sub.get("customerPhone")
            or sub.get("customer_phone")
            or deep_find(sub, ["phone", "customerPhone", "customer_phone"])
        )

        line_items = get_line_items(sub)

        for line in line_items:
            if not isinstance(line, dict):
                line = {}

            qty = get_quantity(line)
            gross_sales = get_revenue(line, qty)

            row = {
                "subscription_id": (
                    sub.get("id")
                    or sub.get("purchaseStateId")
                    or sub.get("subscriptionId")
                    or sub.get("shopifyId")
                    or ""
                ),
                "shopify_id": sub.get("shopifyId") or "",
                "status": status,
                "month": month,
                "created_at": created_at,
                "updated_at": parse_date(sub.get("updatedDate") or sub.get("updatedAt")),
                "cancelled_at": parse_date(sub.get("cancelledAt") or sub.get("deletedAt")),
                "next_billing_date": parse_date(
                    sub.get("nextBillingDate")
                    or sub.get("next_billing_date")
                    or sub.get("nextOrderDate")
                ),
                "customer_id": (
                    dig(sub, "customer.id")
                    or sub.get("customerId")
                    or sub.get("customer_id")
                    or ""
                ),
                "customer_name": customer_name or "",
                "email": email or "",
                "phone": phone or "",
                "product_title": get_product_title(line, sub),
                "sku": get_sku(line),
                "quantity": qty,
                "gross_sales": gross_sales,
                "discounts": 0,
                "net_sales": gross_sales,
                "gross_profit": gross_sales,
                "gross_margin": 1 if gross_sales else 0,
                "source": "Smartrr API",
            }

            rows.append(row)

    return rows


def build_customers(raw_df):
    if raw_df.empty:
        return pd.DataFrame()

    df = raw_df.copy()
    df["orders"] = 1

    grouped = df.groupby(
        ["customer_id", "customer_name", "email", "phone"],
        dropna=False,
    ).agg({
        "orders": "sum",
        "gross_sales": "sum",
        "discounts": "sum",
        "net_sales": "sum",
        "gross_profit": "sum",
        "created_at": "min",
        "next_billing_date": "max",
    }).reset_index()

    grouped = grouped.rename(columns={
        "created_at": "first_order_date",
        "next_billing_date": "last_order_date",
    })

    grouped["gross_margin"] = grouped["gross_profit"] / grouped["gross_sales"].replace(0, 1)
    grouped["tags"] = "Smartrr"
    grouped = grouped.sort_values("gross_sales", ascending=False)
    grouped.insert(0, "rank", range(1, len(grouped) + 1))

    return grouped


def build_purchase_states(raw_df):
    if raw_df.empty:
        return pd.DataFrame()

    cols = [
        "subscription_id",
        "shopify_id",
        "status",
        "month",
        "created_at",
        "updated_at",
        "cancelled_at",
        "next_billing_date",
        "customer_name",
        "email",
        "phone",
    ]

    return raw_df[cols].drop_duplicates().sort_values(["status", "created_at"])


def build_product_volume(raw_df):
    if raw_df.empty:
        return pd.DataFrame()

    grouped = raw_df.groupby(
        ["month", "status", "product_title", "sku"],
        dropna=False,
    ).agg({
        "quantity": "sum",
        "gross_sales": "sum",
        "subscription_id": "nunique",
    }).reset_index()

    grouped = grouped.rename(columns={
        "quantity": "total_quantity",
        "subscription_id": "purchase_states",
    })

    return grouped.sort_values(["month", "total_quantity"], ascending=[False, False])


def classify_box_type(product_title, sku=""):
    text = f"{product_title} {sku}".lower()

    if "signature" in text:
        return "Signature"
    if "premier" in text:
        return "Premier"
    if "spring" in text:
        return "Spring Box"
    if "69" in text:
        return "$69 Box"
    if "9" in text:
        return "$9 Box"
    if "box" in text:
        return "Box"

    return "Other / Needs Review"


def build_duplicate_audit(raw_df):
    """
    Potential duplicate audit for March 2026.

    This flags customers/products with more than one detected Smartrr line
    in the same month. It does NOT prove financial loss by itself.
    Final loss requires Shopify paid orders or warehouse fulfillment data.
    """
    columns = [
        "month",
        "customer_name",
        "email",
        "product_title",
        "sku",
        "box_type",
        "subscription_id_count",
        "detected_quantity",
        "suspected_duplicate_quantity",
        "unit_price",
        "estimated_possible_loss",
        "audit_status",
        "audit_reason",
    ]

    if raw_df.empty:
        return pd.DataFrame(columns=columns)

    df = raw_df.copy()
    df["month"] = df["month"].fillna("Unknown").astype(str)

    df = df[df["month"] == "2026-03"].copy()

    if df.empty:
        return pd.DataFrame(columns=columns)

    group_cols = [
        "month",
        "customer_name",
        "email",
        "product_title",
        "sku",
    ]

    grouped = df.groupby(group_cols, dropna=False).agg({
        "subscription_id": "nunique",
        "quantity": "sum",
        "gross_sales": "sum",
    }).reset_index()

    grouped = grouped.rename(columns={
        "subscription_id": "subscription_id_count",
        "quantity": "detected_quantity",
    })

    grouped["box_type"] = grouped.apply(
        lambda r: classify_box_type(r.get("product_title", ""), r.get("sku", "")),
        axis=1,
    )

    grouped["suspected_duplicate_quantity"] = grouped["detected_quantity"].apply(
        lambda x: max(int(x or 0) - 1, 0)
    )

    grouped["unit_price"] = grouped.apply(
        lambda r: round(float(r["gross_sales"] or 0) / float(r["detected_quantity"] or 1), 2),
        axis=1,
    )

    grouped["estimated_possible_loss"] = grouped.apply(
        lambda r: round(float(r["suspected_duplicate_quantity"] or 0) * float(r["unit_price"] or 0), 2),
        axis=1,
    )

    grouped["audit_status"] = grouped["suspected_duplicate_quantity"].apply(
        lambda x: "POSSIBLE DUPLICATE — NEEDS SHOPIFY/WAREHOUSE VALIDATION" if x > 0 else "NO DUPLICATE DETECTED"
    )

    grouped["audit_reason"] = grouped["suspected_duplicate_quantity"].apply(
        lambda x: (
            "Detected more than one Smartrr line for the same customer/product/month. "
            "Validate against Shopify paid quantity and warehouse shipped quantity."
            if x > 0
            else "Only one detected line for this customer/product/month."
        )
    )

    grouped = grouped.sort_values(
        ["suspected_duplicate_quantity", "estimated_possible_loss"],
        ascending=[False, False],
    )

    return grouped[columns]


def build_months(raw_df):
    if raw_df.empty:
        return pd.DataFrame()

    df = raw_df.copy()
    df["orders"] = 1

    grouped = df.groupby(
        ["month", "status"],
        dropna=False,
    ).agg({
        "orders": "sum",
        "quantity": "sum",
        "gross_sales": "sum",
        "discounts": "sum",
        "net_sales": "sum",
        "gross_profit": "sum",
    }).reset_index()

    grouped["gross_margin"] = grouped["gross_profit"] / grouped["gross_sales"].replace(0, 1)

    return grouped.sort_values(["month", "status"], ascending=[False, True])


def build_summary(raw_df, customers_df, duplicate_audit_df):
    if raw_df.empty:
        return pd.DataFrame([
            {"metric": "Total Purchase States", "value": 0},
            {"metric": "Active", "value": 0},
            {"metric": "Paused", "value": 0},
            {"metric": "Cancelled", "value": 0},
            {"metric": "Customers", "value": 0},
            {"metric": "Gross Sales", "value": 0},
            {"metric": "Possible Duplicate Loss March 2026", "value": 0},
        ])

    status_counts = raw_df.drop_duplicates("subscription_id")["status"].value_counts().to_dict()

    possible_loss = 0
    possible_duplicates = 0

    if not duplicate_audit_df.empty:
        possible_loss = duplicate_audit_df["estimated_possible_loss"].sum()
        possible_duplicates = duplicate_audit_df["suspected_duplicate_quantity"].sum()

    return pd.DataFrame([
        {"metric": "Total Purchase States", "value": raw_df["subscription_id"].nunique()},
        {"metric": "Active", "value": status_counts.get("ACTIVE", 0)},
        {"metric": "Paused", "value": status_counts.get("PAUSED", 0)},
        {"metric": "Cancelled", "value": status_counts.get("CANCELLED", 0)},
        {"metric": "Customers", "value": len(customers_df)},
        {"metric": "Gross Sales", "value": raw_df["gross_sales"].sum()},
        {"metric": "Net Sales", "value": raw_df["net_sales"].sum()},
        {"metric": "Gross Profit", "value": raw_df["gross_profit"].sum()},
        {"metric": "Possible Duplicate Qty March 2026", "value": possible_duplicates},
        {"metric": "Possible Duplicate Loss March 2026", "value": possible_loss},
        {"metric": "Rows", "value": len(raw_df)},
    ])


def build_ranges():
    rows = [
        {
            "range_id": "all",
            "range_label": "All 2026",
            "range_start": f"{REPORT_YEAR}-01-01",
            "range_end": f"{REPORT_YEAR}-12-31",
            "range_status": "open",
        }
    ]

    for month in range(1, 13):
        ym = f"{REPORT_YEAR}-{month:02d}"
        rows.append({
            "range_id": ym,
            "range_label": ym,
            "range_start": f"{ym}-01",
            "range_end": f"{ym}-31",
            "range_status": "month",
        })

    return pd.DataFrame(rows)


def write_excel(summary_df, customers_df, purchase_states_df, product_volume_df, months_df, duplicate_audit_df, raw_df, ranges_df):
    output_path = REPORTS_DIR / "smartrr_report.xlsx"

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Dashboard", index=False)
        customers_df.to_excel(writer, sheet_name="Customers", index=False)
        purchase_states_df.to_excel(writer, sheet_name="Purchase States", index=False)
        product_volume_df.to_excel(writer, sheet_name="Product Volume", index=False)
        months_df.to_excel(writer, sheet_name="Monthly Detail", index=False)
        duplicate_audit_df.to_excel(writer, sheet_name="Duplicate Audit", index=False)
        raw_df.to_excel(writer, sheet_name="Raw Preview", index=False)
        ranges_df.to_excel(writer, sheet_name="Ranges", index=False)

        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            ws.freeze_panes = "A2"

            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True, color="FFFFFF")
                cell.fill = cell.fill.copy(fill_type="solid", fgColor="0C1B2E")

            for column in ws.columns:
                max_length = 0
                column_letter = column[0].column_letter

                for cell in column:
                    value = "" if cell.value is None else str(cell.value)
                    max_length = max(max_length, len(value))

                ws.column_dimensions[column_letter].width = min(max_length + 3, 45)

    return output_path


def write_json(summary_df, customers_df, purchase_states_df, product_volume_df, months_df, duplicate_audit_df, raw_df, ranges_df):
    now = datetime.now(timezone.utc).isoformat()

    report = {
        "meta": {
            "updated_at": now,
            "source": "Smartrr API",
            "report_year": REPORT_YEAR,
            "raw_json_limit": 5000,
            "raw_total_rows": len(raw_df),
            "note": "Duplicate Audit shows possible duplicates only. Final loss requires Shopify paid orders and warehouse fulfillment validation.",
        },
        "ranges": ranges_df.to_dict(orient="records"),
        "summary": summary_df.to_dict(orient="records"),
        "customers": customers_df.to_dict(orient="records"),
        "purchase_states": purchase_states_df.to_dict(orient="records"),
        "product_volume": product_volume_df.to_dict(orient="records"),
        "months": months_df.to_dict(orient="records"),
        "duplicate_audit": duplicate_audit_df.to_dict(orient="records"),
        "raw": raw_df.head(5000).to_dict(orient="records"),
    }

    output_path = DATA_DIR / "report.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(clean_json(report), file, indent=2, ensure_ascii=False, allow_nan=False)

    return output_path


def main():
    client = SmartrrClient()

    print("Fetching purchase states from Smartrr...")
    payload = client.get_subscriptions()
    subscriptions = normalize_api_response(payload)

    print(f"Purchase states received: {len(subscriptions)}")

    raw_rows = build_raw_rows(subscriptions)
    raw_df = pd.DataFrame(raw_rows)

    if raw_df.empty:
        raw_df = pd.DataFrame(columns=[
            "subscription_id",
            "shopify_id",
            "status",
            "month",
            "created_at",
            "updated_at",
            "cancelled_at",
            "next_billing_date",
            "customer_id",
            "customer_name",
            "email",
            "phone",
            "product_title",
            "sku",
            "quantity",
            "gross_sales",
            "discounts",
            "net_sales",
            "gross_profit",
            "gross_margin",
            "source",
        ])

    customers_df = build_customers(raw_df)
    purchase_states_df = build_purchase_states(raw_df)
    product_volume_df = build_product_volume(raw_df)
    months_df = build_months(raw_df)
    duplicate_audit_df = build_duplicate_audit(raw_df)
    summary_df = build_summary(raw_df, customers_df, duplicate_audit_df)
    ranges_df = build_ranges()

    json_path = write_json(
        summary_df,
        customers_df,
        purchase_states_df,
        product_volume_df,
        months_df,
        duplicate_audit_df,
        raw_df,
        ranges_df,
    )

    excel_path = write_excel(
        summary_df,
        customers_df,
        purchase_states_df,
        product_volume_df,
        months_df,
        duplicate_audit_df,
        raw_df,
        ranges_df,
    )

    print(f"JSON created: {json_path}")
    print(f"Excel created: {excel_path}")


if __name__ == "__main__":
    main()
