"""
Tool handler: get_quota_service_info
Returns credit quota breakdown and assessment result.
"""

from tools.mock_data import QUOTAS, DEFAULT_CUSTOMER_ID


async def get_quota_service_info(state: dict) -> dict:
    """
    Retrieve quota service information for a customer.

    Args:
        state: Pipeline state dict; may contain 'customer' with 'customer_id'.

    Returns:
        Quota details including total, available, used amounts and assessment.
    """
    customer_id: str = (
        state.get("customer", {}).get("customer_id") or DEFAULT_CUSTOMER_ID
    )
    quota = QUOTAS.get(customer_id, QUOTAS[DEFAULT_CUSTOMER_ID])
    return dict(quota)
