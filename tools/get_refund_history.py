"""Tool handler: get_refund_history.

Returns refund application records for the customer.
"""

from tools.demo_data_access import customer_id_from_state, list_customer_payloads


async def get_refund_history(state: dict) -> dict:
    customer_id = customer_id_from_state(state)
    return list_customer_payloads("refund_history", customer_id, "refund_history")
