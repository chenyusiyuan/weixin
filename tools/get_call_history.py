"""Tool handler: get_call_history.

Returns recent inbound/outbound service call records for the customer.
"""

from tools.demo_data_access import customer_id_from_state, list_customer_payloads


async def get_call_history(state: dict) -> dict:
    customer_id = customer_id_from_state(state)
    return list_customer_payloads("call_history", customer_id, "call_history")
