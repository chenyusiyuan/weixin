"""
Tool handler: get_quota_service_info
Returns credit quota breakdown and assessment result.
"""

from tools.demo_data_access import customer_id_from_state, get_customer_payload


async def get_quota_service_info(state: dict) -> dict:
    """
    Retrieve quota service information for a customer.

    Args:
        state: Pipeline state dict; may contain 'customer' with 'customer_id'.

    Returns:
        Quota details including total, available, used amounts and assessment.
    """
    customer_id = customer_id_from_state(state)
    return get_customer_payload("quotas", customer_id)
