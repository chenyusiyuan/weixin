"""
Tool handler: get_bill_and_repayment_plan
Returns current bill details, overdue info, and repayment schedule.
"""

from tools.demo_data_access import customer_id_from_state, get_customer_payload


async def get_bill_and_repayment_plan(state: dict) -> dict:
    """
    Retrieve bill and repayment plan for a customer.

    Args:
        state: Pipeline state dict; may contain 'customer' with 'customer_id'.

    Returns:
        Bill details including overdue info, fee breakdown, and deduction records.
    """
    customer_id = customer_id_from_state(state)
    return get_customer_payload("bills", customer_id)
