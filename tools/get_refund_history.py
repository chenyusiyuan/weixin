"""Tool handler: get_refund_history.

Returns refund application records for the customer.
"""

from tools.mock_data import DEFAULT_CUSTOMER_ID, REFUND_HISTORY


async def get_refund_history(state: dict) -> dict:
    customer_id: str = (
        state.get("customer", {}).get("customer_id") or DEFAULT_CUSTOMER_ID
    )
    records = REFUND_HISTORY.get(customer_id, REFUND_HISTORY[DEFAULT_CUSTOMER_ID])
    return {
        "customer_id": customer_id,
        "refund_history": records,
        "total_count": len(records),
    }
