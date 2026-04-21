"""Tool handler: get_stop_collection_history.

Returns stop-collection request records for the customer.
"""

from tools.mock_data import DEFAULT_CUSTOMER_ID, STOP_COLLECTION_HISTORY


async def get_stop_collection_history(state: dict) -> dict:
    customer_id: str = (
        state.get("customer", {}).get("customer_id") or DEFAULT_CUSTOMER_ID
    )
    records = STOP_COLLECTION_HISTORY.get(
        customer_id, STOP_COLLECTION_HISTORY[DEFAULT_CUSTOMER_ID]
    )
    has_active = any(r.get("status") == "已受理" for r in records)
    return {
        "customer_id": customer_id,
        "stop_collection_history": records,
        "total_count": len(records),
        "has_active_stop": has_active,
    }
