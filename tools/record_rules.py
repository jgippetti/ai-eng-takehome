"""Tool for keeping important task and guide rules visible to the agent."""

from typing import Any

from framework.agent import Tool


def record_rules(
    phase: str,
    guide_status: str,
    guide_reason: str,
    rules: list[dict[str, Any]],
) -> str:
    """Format task and guide rules for reuse in later agent iterations."""
    if phase not in {"hypothesis", "revised"}:
        return f"Error: invalid phase '{phase}'."
    if guide_status not in {"applicable", "no_relevant_guide"}:
        return f"Error: invalid guide status '{guide_status}'."
    if not guide_reason.strip():
        return "Error: guide_reason must explain the guide decision."

    has_guide_rules = any(rule.get("source") == "guide" for rule in rules)
    if guide_status == "applicable" and not has_guide_rules:
        return "Error: applicable guide status requires at least one guide-sourced rule."
    if guide_status == "no_relevant_guide" and has_guide_rules:
        return "Error: no_relevant_guide status cannot include guide-sourced rules."

    for rule in rules:
        source_excerpt = rule.get("source_excerpt", "").strip()
        if not source_excerpt:
            return "Error: every rule requires a source_excerpt."
        status = rule.get("status")
        expected_statuses = (
            {"task_required"}
            if rule.get("source") == "task"
            else {"guide_candidate"}
            if phase == "hypothesis"
            else {"guide_confirmed", "guide_rejected", "guide_unsupported"}
        )
        if status not in expected_statuses:
            expected = ", ".join(sorted(expected_statuses))
            return f"Error: {phase} {rule.get('source')} rule status must be {expected}."
        if phase == "revised" and not rule.get("data_mapping", "").strip():
            return "Error: every revised rule requires a data_mapping or decision reason."

    task_rules = [rule for rule in rules if rule.get("source") == "task"]
    guide_rules = [rule for rule in rules if rule.get("source") == "guide"]

    lines = [
        "Rule hypothesis:" if phase == "hypothesis" else "Revised rule contract:",
        f"Guide status: {guide_status}",
        f"Guide decision: {guide_reason}",
        "Required task rules:",
    ]
    for rule in task_rules:
        lines.append(
            f"- {rule['rule']}\n"
            f'  Source excerpt: "{rule["source_excerpt"].strip()}"'
        )
        if phase == "revised":
            lines.append(f"  Data mapping: {rule['data_mapping'].strip()}")
    lines.append(
        "Candidate guide rules (confirm scope and schema support):"
        if phase == "hypothesis"
        else "Guide rule decisions:"
    )
    if not guide_rules:
        lines.append("- None")
    for rule in guide_rules:
        lines.append(
            f"- [{rule['status'].removeprefix('guide_')}] {rule['rule']}\n"
            f'  Source excerpt: "{rule["source_excerpt"].strip()}"'
        )
        if phase == "revised":
            lines.append(f"  Data mapping: {rule['data_mapping'].strip()}")
    return "\n".join(lines)


RECORD_RULES = Tool(
    name="record_rules",
    description=(
        "Record a traceable rule hypothesis before data exploration, then a revised contract "
        "after inspecting the data. Task rules remain mandatory. Guide rules begin as "
        "candidates and are later confirmed, rejected as out of scope, or marked unsupported. "
        "Every rule must include an exact source excerpt. Revised rules map consequential "
        "requirements to concrete data and explain column choices or guide-rule decisions."
    ),
    parameters={
        "type": "object",
        "properties": {
            "phase": {
                "type": "string",
                "enum": ["hypothesis", "revised"],
                "description": (
                    "Use hypothesis before database exploration and revised after inspecting "
                    "candidate tables and values."
                ),
            },
            "guide_status": {
                "type": "string",
                "enum": ["applicable", "no_relevant_guide"],
                "description": (
                    "Use applicable after reading a relevant guide. Use no_relevant_guide "
                    "only when guide search found no plausible match."
                ),
            },
            "guide_reason": {
                "type": "string",
                "description": (
                    "Briefly identify the applicable guide or explain why the search "
                    "results were not relevant."
                ),
            },
            "rules": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {
                            "type": "string",
                            "enum": ["task", "guide"],
                            "description": "Where the rule came from.",
                        },
                        "rule": {
                            "type": "string",
                            "description": (
                                "For task sources, a required constraint. For guide sources, "
                                "a provisional interpretation to confirm after schema discovery."
                            ),
                        },
                        "status": {
                            "type": "string",
                            "enum": [
                                "task_required",
                                "guide_candidate",
                                "guide_confirmed",
                                "guide_rejected",
                                "guide_unsupported",
                            ],
                            "description": (
                                "Task rules are always task_required. Guide rules start as "
                                "guide_candidate; revised guide rules must be confirmed, "
                                "rejected as out of scope, or marked unsupported by the data."
                            ),
                        },
                        "source_excerpt": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 240,
                            "description": (
                                "A short exact excerpt copied from the question when source "
                                "is task, or from the complete guide when source is guide."
                            ),
                        },
                        "data_mapping": {
                            "type": "string",
                            "description": (
                                "Required in the revised phase: name the chosen table, column, "
                                "or expression and why the observed type, values, grain, or "
                                "guide supports it. When a plausible alternative existed, state "
                                "which one was rejected and why. For rejected or unsupported "
                                "guide rules, provide the decision reason. Omit in hypothesis."
                            ),
                        },
                    },
                    "required": ["source", "rule", "status", "source_excerpt"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["phase", "guide_status", "guide_reason", "rules"],
        "additionalProperties": False,
    },
    function=record_rules,
)
