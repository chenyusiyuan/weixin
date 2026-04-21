"""
Tool handler: get_membership_service_info
Returns membership status, type, privileges, and cancellation eligibility.
"""

from tools.mock_data import MEMBERSHIPS, DEFAULT_CUSTOMER_ID


async def get_membership_service_info(state: dict) -> dict:
    """
    Retrieve membership service information for a customer.

    Args:
        state: Pipeline state dict; may contain 'customer' with 'customer_id'.

    Returns:
        Membership details including status, privileges, and refund eligibility.
    """
    customer_id: str = (
        state.get("customer", {}).get("customer_id") or DEFAULT_CUSTOMER_ID
    )
    membership = MEMBERSHIPS.get(customer_id, MEMBERSHIPS[DEFAULT_CUSTOMER_ID])
    return dict(membership)
