"""Fix the 7 validator warnings by adding slot_source tools to tools.optional.

Scans each skill: for every tool referenced in slot_sources but not listed in
tools.required/optional, add it to tools.optional.

Safe and idempotent.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills" / "definitions"

KNOWN_TOOLS = {
    "get_customer_profile",
    "get_bill_and_repayment_plan",
    "get_loan_service_info",
    "get_membership_service_info",
    "get_quota_service_info",
    "query_ticket",
    "submit_ticket",
}

yaml_rt = YAML(typ="rt")
yaml_rt.preserve_quotes = True
yaml_rt.width = 4096
yaml_rt.indent(mapping=2, sequence=4, offset=2)


def tools_from_sources(slot_sources: CommentedMap | dict) -> set[str]:
    tools: set[str] = set()
    for src in (slot_sources or {}).values():
        if isinstance(src, str) and src.startswith("tool:"):
            ref = src[len("tool:"):]
            tool = ref.split(".", 1)[0]
            if tool in KNOWN_TOOLS:
                tools.add(tool)
    return tools


def fix_file(path: Path) -> bool:
    with open(path, encoding="utf-8") as f:
        docs = list(yaml_rt.load_all(f))
    docs = [d for d in docs if d is not None]
    if not docs:
        return False
    # New layout: single merged doc (front-matter + body together).
    # Legacy layout: two docs separated by `---`.
    if len(docs) == 1:
        front = None
        body = docs[0]
    else:
        front, body = docs[0], docs[1]

    slot_sources = body.get("slot_sources") or {}
    needed = tools_from_sources(slot_sources)

    tools_block = body.get("tools")
    if tools_block is None:
        tools_block = CommentedMap()
        body["tools"] = tools_block
    required_list = tools_block.get("required") or []
    optional_list = tools_block.get("optional") or []
    required = set(required_list)
    optional = set(optional_list)
    missing = needed - required - optional
    if not missing:
        return False

    new_optional = list(optional_list) + sorted(missing)
    tools_block["optional"] = CommentedSeq(new_optional)

    buf = StringIO()
    buf.write("---\n")
    if front is not None:
        yaml_rt.dump(front, buf)
        buf.write("\n")
    yaml_rt.dump(body, buf)
    path.write_text(buf.getvalue(), encoding="utf-8")
    return True


def main() -> None:
    changed = 0
    for path in sorted(SKILLS_DIR.glob("*.yaml")):
        if fix_file(path):
            changed += 1
            print(f"[FIX] {path.name}")
    print(f"{changed} file(s) updated")


if __name__ == "__main__":
    main()
