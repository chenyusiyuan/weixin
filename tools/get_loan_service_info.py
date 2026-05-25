"""
Tool handler: get_loan_service_info
Returns loan status, disbursement progress, and contract details.
"""

from tools.demo_data_access import customer_id_from_state, get_customer_payload


async def get_loan_service_info(state: dict) -> dict:
    """
    Retrieve loan service information for a customer.

    Args:
        state: Pipeline state dict; may contain 'customer' with 'customer_id'.

    Returns:
        Loan details including status, disbursement info, and product name.
    """
    customer_id = customer_id_from_state(state)
    return get_customer_payload("loans", customer_id)
