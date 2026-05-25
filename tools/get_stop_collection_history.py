"""Tool handler: get_stop_collection_history.

Returns stop-collection request records for the customer.
"""

from tools.demo_data_access import customer_id_from_state, list_customer_payloads


async def get_stop_collection_history(state: dict) -> dict:
    customer_id = customer_id_from_state(state)
    result = list_customer_payloads(
        "stop_collection_history",
        customer_id,
        "stop_collection_history",
    )
    records = result["stop_collection_history"]
    has_active = any(r.get("status") == "已受理" for r in records)
    result["has_active_stop"] = has_active
    return result
