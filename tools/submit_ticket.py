"""
Tool handler: submit_ticket
Creates a new service ticket for a customer.
"""

import asyncio
import datetime
from tools.mock_data import TICKETS, DEFAULT_CUSTOMER_ID
import tools.mock_data as _mock_data

_counter_lock = asyncio.Lock()


async def submit_ticket(state: dict) -> dict:
    """
    Submit a new ticket on behalf of a customer.

    Reads optional slot fields from state:
        - state['slots']['ticket_type']   (str): ticket category, e.g. "逾期协商"
        - state['slots']['ticket_summary'] (str): free-text summary

    Args:
        state: Pipeline state dict.

    Returns:
        New ticket confirmation with ticket_id, status, and handling message.
    """
    customer_id: str = (
        state.get("customer", {}).get("customer_id") or DEFAULT_CUSTOMER_ID
    )
    slots: dict = state.get("slots", {})
    ticket_type: str = slots.get("ticket_type", "咨询")
    ticket_summary: str = slots.get("ticket_summary", "客户发起工单")

    # Generate sequential ticket ID (thread-safe under concurrent async)
    async with _counter_lock:
        _mock_data._ticket_counter += 1
        counter_val = _mock_data._ticket_counter
    today = datetime.date.today().strftime("%Y%m%d")
    ticket_id = f"TK{today}{counter_val:03d}"

    new_ticket: dict = {
        "ticket_id": ticket_id,
        "type": ticket_type,
        "status": "pending",
        "created_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": ticket_summary,
    }

    # Persist to mock store
    TICKETS.setdefault(customer_id, []).append(new_ticket)

    return {
        "ticket_id": ticket_id,
        "status": "submitted",
        "message": "工单已提交，预计24小时内处理",
    }
