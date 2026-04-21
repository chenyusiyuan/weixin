"""trace_id generation utility."""

from __future__ import annotations

import time
import uuid


def generate_trace_id() -> str:
    """Generate a unique trace ID for request tracking."""
    return f"tr-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
