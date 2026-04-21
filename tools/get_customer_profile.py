"""
Tool handler: get_customer_profile
Returns masked customer identity and account status.
"""

from tools.mock_data import CUSTOMERS, DEFAULT_CUSTOMER_ID


async def get_customer_profile(state: dict) -> dict:
    """
    Retrieve customer profile from state context.

    Args:
        state: Pipeline state dict; may contain 'customer' with 'customer_id'.

    Returns:
        Customer profile dict with masked PII fields.
    """
    customer_id: str = (
        state.get("customer", {}).get("customer_id") or DEFAULT_CUSTOMER_ID
    )
    profile = CUSTOMERS.get(customer_id, CUSTOMERS[DEFAULT_CUSTOMER_ID])
    return dict(profile)
