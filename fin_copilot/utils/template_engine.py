"""Jinja2 template engine for skill script slot filling."""

from __future__ import annotations

import re
from typing import Any

from jinja2 import BaseLoader, Environment, Undefined


class _SilentUndefined(Undefined):
    """Renders undefined variables as the original placeholder ``{var_name}``."""

    def __str__(self) -> str:
        return "{" + str(self._undefined_name) + "}"


# Shared Jinja2 environment
_env = Environment(loader=BaseLoader(), undefined=_SilentUndefined)


def try_fill_template(
    script: str,
    data: dict[str, Any],
) -> tuple[str, bool]:
    """Try to fill a skill script template with data.

    Skill templates use ``{slot_name}`` placeholders.  This function converts
    them to Jinja2 ``{{ slot_name }}`` syntax, renders with *data*, and reports
    whether all slots were filled.

    Returns:
        (filled_text, is_complete) where *is_complete* is True when no
        unfilled ``{slot_name}`` placeholders remain.
    """
    # Convert {slot_name} to {{ slot_name }} for Jinja2
    jinja_script = re.sub(r"\{(\w+)\}", r"{{ \1 }}", script)

    try:
        template = _env.from_string(jinja_script)
        result = template.render(**data)
        # Check for remaining unfilled placeholders
        has_unfilled = bool(re.search(r"\{[a-z_]+\}", result))
        return result, not has_unfilled
    except Exception:
        return script, False
