"""
Tool handler: get_loan_service_info
Returns loan status, disbursement progress, and contract details.
"""

from tools.mock_data import LOANS, DEFAULT_CUSTOMER_ID


async def get_loan_service_info(state: dict) -> dict:
    """
    Retrieve loan service information for a customer.

    Args:
        state: Pipeline state dict; may contain 'customer' with 'customer_id'.

    Returns:
        Loan details including status, disbursement info, and product name.
    """
    customer_id: str = (
        state.get("customer", {}).get("customer_id") or DEFAULT_CUSTOMER_ID
    )
    loan = LOANS.get(customer_id, LOANS[DEFAULT_CUSTOMER_ID])
    return dict(loan)
