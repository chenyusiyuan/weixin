"""
Tool handler: get_membership_service_info
Returns membership status, type, privileges, and cancellation eligibility.
"""

from tools.demo_data_access import customer_id_from_state, get_customer_payload


async def get_membership_service_info(state: dict) -> dict:
    """
    Retrieve membership service information for a customer.

    Args:
        state: Pipeline state dict; may contain 'customer' with 'customer_id'.

    Returns:
        Membership details including status, privileges, and refund eligibility.
    """
    customer_id = customer_id_from_state(state)
    return get_customer_payload("memberships", customer_id)
