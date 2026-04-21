"""
Tool handler: query_ticket
Returns existing tickets for a customer.
"""

from tools.mock_data import TICKETS, DEFAULT_CUSTOMER_ID


async def query_ticket(state: dict) -> dict:
    """
    Query tickets for a customer.

    Args:
        state: Pipeline state dict; may contain 'customer' with 'customer_id'.

    Returns:
        Dict with ticket list and total count.
    """
    customer_id: str = (
        state.get("customer", {}).get("customer_id") or DEFAULT_CUSTOMER_ID
    )
    tickets: list[dict] = TICKETS.get(customer_id, [])
    return {
        "tickets": [dict(t) for t in tickets],
        "total_count": len(tickets),
    }
