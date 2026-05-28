from pathlib import Path
from datetime import datetime, timezone
import os
import json

import pandas as pd

from smartrr_client import SmartrrClient


DATA_DIR = Path("data")
REPORTS_DIR = Path("reports")

DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

REPORT_YEAR = os.getenv("REPORT_YEAR", "2026")


def normalize_api_response(payload):
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ["data", "results", "subscriptions", "items"]:
            if key in payload and isinstance(payload[key], list):
                return payload[key]

        return [payload]

    return []


def safe_value(row, keys, default=""):
    for key in keys:
        if isinstance(row, dict) and key in row and row[key] not in [None, ""]:
            return row[key]
    return default


def to_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def build_raw_rows(subscriptions):
    rows = []

    for sub in subscriptions:
        customer = sub.get("customer") or {}
        line_items = sub.get("line_items") or sub.get("items") or []

        if not line_items:
            line_items = [{}]

        for item in line_items:
            price = to_float(
                safe_value(
                    item,
                    ["price", "amount", "unit_price", "selling_plan_price"],
                    safe_value(sub, ["price", "amount"], 0),
                )
            )

            quantity = to_float(safe_value(item, ["quantity", "qty"], 1))

            rows.append({
                "subscription_id": safe_value(sub, ["id", "subscription_id"]),
                "status": safe_value(sub, ["status", "subscription_status"]),
                "customer_id": safe_value(customer, ["id", "customer_id"]) or safe_value(sub, ["customer_id"]),
                "customer_name": safe_value(customer, ["name", "full_name"]) or safe_value(sub, ["customer_name"]),
                "first_name": safe_value(customer, ["first_name"]) or safe_value(sub, ["first_name"]),
                "last_name": safe_value(customer, ["last_name"]) or safe_value(sub, ["last_name"]),
                "email": safe_value(customer, ["email"]) or safe_value(sub, ["email", "customer_email"]),
                "phone": safe_value(customer, ["phone"]) or safe_value(sub, ["phone", "customer_phone"]),
                "product_title": safe_value(item, ["title", "product_title", "name"]),
                "sku": safe_value(item, ["sku", "variant_sku"]),
                "quantity": quantity,
                "price": price,
                "gross_sales": price * quantity,
                "discounts": 0,
                "net_sales": price * quantity,
                "gross_profit": price * quantity,
                "gross_margin": 1 if price else 0,
                "created_at": safe_value(sub, ["created_at", "createdAt"]),
                "next_billing_date": safe_value(sub, ["next_billing_date", "nextBillingDate"]),
                "cancelled_at": safe_value(sub, ["cancelled_at", "cancelledAt"]),
                "sales_rep": "Unassigned",
                "tags": "Smartrr",
                "is_concierge_tagged": "YES",
            })

    return rows


def build_customers(raw_df):
    if raw_df.empty:
        return pd.DataFrame()

    df = raw_df.copy()
    df["orders"] = 1

    grouped = df.groupby(
        ["customer_id", "customer_name", "first_name", "last_name", "email", "phone"],
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

    grouped["gross_margin"] = grouped["gross_profit"] / grouped["gross_sales"].replace(0, 1)
    grouped["sales_rep"] = "Unassigned"
    grouped["tags"] = "Smartrr"
    grouped["is_concierge_tagged"] = "YES"
    grouped["top_month"] = ""
    grouped = grouped.rename(columns={
        "created_at": "first_order_date",
        "next_billing_date": "last_order_date",
    })

    grouped = grouped.sort_values("gross_sales", ascending=False)
    grouped.insert(0, "rank", range(1, len(grouped) + 1))

    return grouped


def build_months(raw_df):
    if raw_df.empty:
        return pd.DataFrame()

    df = raw_df.copy()
    df["created_at_dt"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["month"] = df["created_at_dt"].dt.strftime("%Y-%m")
    df["orders"] = 1

    grouped = df.groupby(
        ["month", "customer_id", "customer_name", "first_name", "last_name", "email", "phone"],
        dropna=False,
    ).agg({
        "orders": "sum",
        "gross_sales": "sum",
        "discounts": "sum",
        "net_sales": "sum",
        "gross_profit": "sum",
    }).reset_index()

    grouped["gross_margin"] = grouped["gross_profit"] / grouped["gross_sales"].replace(0, 1)
    grouped["sales_rep"] = "Unassigned"
    grouped["tags"] = "Smartrr"

    return grouped.sort_values(["month", "gross_sales"], ascending=[False, False])


def build_summary(customers_df):
    if customers_df.empty:
        return pd.DataFrame([
            {"metric": "Gross Sales", "value": 0},
            {"metric": "Net Sales", "value": 0},
            {"metric": "Gross Profit", "value": 0},
            {"metric": "Gross Margin", "value": 0},
            {"metric": "Discounts", "value": 0},
            {"metric": "Total Customers", "value": 0},
            {"metric": "Orders", "value": 0},
            {"metric": "Concierge Tagged Only", "value": "YES"},
            {"metric": "Top Month", "value": ""},
            {"metric": "Top Month Net Sales", "value": 0},
        ])

    gross_sales = customers_df["gross_sales"].sum()
    gross_profit = customers_df["gross_profit"].sum()

    return pd.DataFrame([
        {"metric": "Gross Sales", "value": gross_sales},
        {"metric": "Net Sales", "value": customers_df["net_sales"].sum()},
        {"metric": "Gross Profit", "value": gross_profit},
        {"metric": "Gross Margin", "value": gross_profit / gross_sales if gross_sales else 0},
        {"metric": "Discounts", "value": customers_df["discounts"].sum()},
        {"metric": "Total Customers", "value": len(customers_df)},
        {"metric": "Orders", "value": customers_df["orders"].sum()},
        {"metric": "Concierge Tagged Only", "value": "YES"},
        {"metric": "Top Month", "value": ""},
        {"metric": "Top Month Net Sales", "value": 0},
    ])


def write_json(summary_df, customers_df, months_df, raw_df):
    now = datetime.now(timezone.utc).isoformat()

    report = {
        "meta": {
            "updated_at": now,
            "source": "Smartrr API",
            "only_concierge_tagged_orders": True,
            "raw_json_limit": 2000,
            "raw_total_rows_in_sheet": len(raw_df),
        },
        "ranges": [
            {
                "range_id": REPORT_YEAR,
                "range_label": f"{REPORT_YEAR} Full Year",
                "range_start": f"{REPORT_YEAR}-01-01",
                "range_end": f"{REPORT_YEAR}-12-31",
                "range_status": "open",
            }
        ],
        "summary": [
            {"range_id": REPORT_YEAR, **row}
            for row in summary_df.to_dict(orient="records")
        ],
        "customers": [
            {"range_id": REPORT_YEAR, **row}
            for row in customers_df.to_dict(orient="records")
        ],
        "months": [
            {"range_id": REPORT_YEAR, **row}
            for row in months_df.to_dict(orient="records")
        ],
        "raw": [
            {"range_id": REPORT_YEAR, **row}
            for row in raw_df.head(2000).to_dict(orient="records")
        ],
    }

    output_path = DATA_DIR / "report.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, default=str)

    return output_path


def write_excel(summary_df, customers_df, months_df, raw_df):
    output_path = REPORTS_DIR / "smartrr_report.xlsx"

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Dashboard", index=False)
        customers_df.to_excel(writer, sheet_name="Customers", index=False)
        months_df.to_excel(writer, sheet_name="Monthly Detail", index=False)
        raw_df.to_excel(writer, sheet_name="Raw Preview", index=False)

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


def main():
    client = SmartrrClient()

    print("Fetching subscriptions from Smartrr...")
    payload = client.get_subscriptions()
    subscriptions = normalize_api_response(payload)

    print(f"Subscriptions received: {len(subscriptions)}")

    raw_rows = build_raw_rows(subscriptions)
    raw_df = pd.DataFrame(raw_rows)

    customers_df = build_customers(raw_df)
    months_df = build_months(raw_df)
    summary_df = build_summary(customers_df)

    json_path = write_json(summary_df, customers_df, months_df, raw_df)
    excel_path = write_excel(summary_df, customers_df, months_df, raw_df)

    print(f"JSON created: {json_path}")
    print(f"Excel created: {excel_path}")


if __name__ == "__main__":
    main()
