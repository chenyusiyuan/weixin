"""
Tool handler: get_bill_and_repayment_plan
Returns current bill details, overdue info, and repayment schedule.
"""

from tools.mock_data import BILLS, DEFAULT_CUSTOMER_ID


async def get_bill_and_repayment_plan(state: dict) -> dict:
    """
    Retrieve bill and repayment plan for a customer.

    Args:
        state: Pipeline state dict; may contain 'customer' with 'customer_id'.

    Returns:
        Bill details including overdue info, fee breakdown, and deduction records.
    """
    customer_id: str = (
        state.get("customer", {}).get("customer_id") or DEFAULT_CUSTOMER_ID
    )
    bill = BILLS.get(customer_id, BILLS[DEFAULT_CUSTOMER_ID])
    return dict(bill)
