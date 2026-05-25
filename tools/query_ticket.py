"""
Tool handler: query_ticket
Returns existing tickets for a customer.
"""

from tools.demo_data_access import customer_id_from_state, list_customer_payloads


async def query_ticket(state: dict) -> dict:
    """
    Query tickets for a customer.

    Args:
        state: Pipeline state dict; may contain 'customer' with 'customer_id'.

    Returns:
        Dict with ticket list and total count.
    """
    customer_id = customer_id_from_state(state)
    result = list_customer_payloads("tickets", customer_id, "tickets")
    result.pop("customer_id", None)
    return result
