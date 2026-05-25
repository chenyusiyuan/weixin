"""
Tool handler: get_customer_profile
Returns demo customer identity and account status.
"""

from tools.demo_data_access import customer_id_from_state, get_customer_payload


async def get_customer_profile(state: dict) -> dict:
    """
    Retrieve customer profile from state context.

    Args:
        state: Pipeline state dict; may contain 'customer' with 'customer_id'.

    Returns:
        Customer profile dict with full demo customer fields.
    """
    customer_id = customer_id_from_state(state)
    return get_customer_payload("customers", customer_id)
