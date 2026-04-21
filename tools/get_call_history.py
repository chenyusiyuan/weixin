"""Tool handler: get_call_history.

Returns recent inbound/outbound service call records for the customer.
"""

from tools.mock_data import CALL_HISTORY, DEFAULT_CUSTOMER_ID


async def get_call_history(state: dict) -> dict:
    customer_id: str = (
        state.get("customer", {}).get("customer_id") or DEFAULT_CUSTOMER_ID
    )
    records = CALL_HISTORY.get(customer_id, CALL_HISTORY[DEFAULT_CUSTOMER_ID])
    return {
        "customer_id": customer_id,
        "call_history": records,
        "total_count": len(records),
    }
