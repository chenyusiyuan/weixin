"""Tool handler: get_sms_history.

Returns SMS records sent to the customer.
"""

from tools.mock_data import DEFAULT_CUSTOMER_ID, SMS_HISTORY


async def get_sms_history(state: dict) -> dict:
    customer_id: str = (
        state.get("customer", {}).get("customer_id") or DEFAULT_CUSTOMER_ID
    )
    records = SMS_HISTORY.get(customer_id, SMS_HISTORY[DEFAULT_CUSTOMER_ID])
    return {
        "customer_id": customer_id,
        "sms_history": records,
        "total_count": len(records),
    }
