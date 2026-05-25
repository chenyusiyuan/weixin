"""Tool handler: get_sms_history.

Returns SMS records sent to the customer.
"""

from tools.demo_data_access import customer_id_from_state, list_customer_payloads


async def get_sms_history(state: dict) -> dict:
    customer_id = customer_id_from_state(state)
    return list_customer_payloads("sms_history", customer_id, "sms_history")
