"""
Tool handler: submit_ticket
Creates a new service ticket for a customer.
"""

import datetime
from fin_copilot.demo.store import get_demo_store
from tools.demo_data_access import customer_id_from_state


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
    customer_id = customer_id_from_state(state)
    slots: dict = state.get("slots", {})
    ticket_type: str = slots.get("ticket_type", "咨询")
    ticket_summary: str = slots.get("ticket_summary", "客户发起工单")

    try:
        ticket_id = get_demo_store().next_ticket_id()
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        return {
            "status": "error",
            "message": f"demo_store_unavailable: {exc}",
        }

    new_ticket: dict = {
        "ticket_id": ticket_id,
        "type": ticket_type,
        "status": "pending",
        "created_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": ticket_summary,
    }

    try:
        get_demo_store().upsert_record("tickets", customer_id, new_ticket, ticket_id)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        return {
            "ticket_id": ticket_id,
            "status": "error",
            "message": f"demo_store_unavailable: {exc}",
        }

    return {
        "ticket_id": ticket_id,
        "status": "submitted",
        "message": "工单已提交，预计24小时内处理",
    }
