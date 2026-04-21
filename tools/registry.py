"""
Tool registry mapping tool names to their async handler functions.

Each entry includes:
  - handler: the async callable
  - permission: "read" or "write" (Chain C only permits read tools)

Import TOOL_REGISTRY to dispatch tool calls by name.
Use WRITE_TOOLS to filter out write operations in Chain C.
"""

from typing import Any, Callable, Awaitable

from tools.get_customer_profile import get_customer_profile
from tools.get_bill_and_repayment_plan import get_bill_and_repayment_plan
from tools.get_loan_service_info import get_loan_service_info
from tools.get_membership_service_info import get_membership_service_info
from tools.get_quota_service_info import get_quota_service_info
from tools.get_call_history import get_call_history
from tools.get_sms_history import get_sms_history
from tools.get_stop_collection_history import get_stop_collection_history
from tools.get_refund_history import get_refund_history
from tools.query_ticket import query_ticket
from tools.submit_ticket import submit_ticket

# Full registry with permission metadata
TOOL_REGISTRY_META: dict[str, dict[str, Any]] = {
    "get_customer_profile":        {"handler": get_customer_profile,        "permission": "read"},
    "get_bill_and_repayment_plan": {"handler": get_bill_and_repayment_plan, "permission": "read"},
    "get_loan_service_info":       {"handler": get_loan_service_info,       "permission": "read"},
    "get_membership_service_info": {"handler": get_membership_service_info, "permission": "read"},
    "get_quota_service_info":      {"handler": get_quota_service_info,      "permission": "read"},
    "get_call_history":            {"handler": get_call_history,            "permission": "read"},
    "get_sms_history":             {"handler": get_sms_history,             "permission": "read"},
    "get_stop_collection_history": {"handler": get_stop_collection_history, "permission": "read"},
    "get_refund_history":          {"handler": get_refund_history,          "permission": "read"},
    "query_ticket":                {"handler": query_ticket,                "permission": "read"},
    "submit_ticket":               {"handler": submit_ticket,              "permission": "write"},
}

# Flat registry for backward compatibility (name → handler)
TOOL_REGISTRY: dict[str, Callable[..., Awaitable[dict]]] = {
    name: meta["handler"] for name, meta in TOOL_REGISTRY_META.items()
}

# Write-operation tools — must be blocked in Chain C
WRITE_TOOLS: frozenset[str] = frozenset(
    name for name, meta in TOOL_REGISTRY_META.items() if meta["permission"] == "write"
)
