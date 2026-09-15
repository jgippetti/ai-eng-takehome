from tools.record_rules import RECORD_RULES, record_rules


def test_record_rules_formats_task_and_guide_rules() -> None:
    result = record_rules(
        phase="hypothesis",
        guide_status="applicable",
        guide_reason="The baseball guide defines batting eligibility.",
        rules=[
            {
                "source": "guide",
                "rule": "Exclude seasons with fewer than 100 at-bats.",
                "status": "guide_candidate",
                "source_excerpt": "seasons with fewer than 100 at-bats should be excluded",
            },
            {
                "source": "task",
                "rule": "Include only players with at least 500 career at-bats.",
                "status": "task_required",
                "source_excerpt": "at least 500 career at-bats",
            },
        ]
    )

    assert result == (
        "Rule hypothesis:\n"
        "Guide status: applicable\n"
        "Guide decision: The baseball guide defines batting eligibility.\n"
        "Required task rules:\n"
        "- Include only players with at least 500 career at-bats.\n"
        '  Source excerpt: "at least 500 career at-bats"\n'
        "Candidate guide rules (confirm scope and schema support):\n"
        "- [candidate] Exclude seasons with fewer than 100 at-bats.\n"
        '  Source excerpt: "seasons with fewer than 100 at-bats should be excluded"'
    )


def test_record_rules_tool_definition_is_strict() -> None:
    assert RECORD_RULES.name == "record_rules"
    assert RECORD_RULES.parameters["additionalProperties"] is False
    assert RECORD_RULES.parameters["properties"]["rules"]["items"][
        "additionalProperties"
    ] is False
    assert RECORD_RULES.parameters["properties"]["rules"]["items"]["required"] == [
        "source",
        "rule",
        "status",
        "source_excerpt",
    ]
    mapping_description = RECORD_RULES.parameters["properties"]["rules"]["items"][
        "properties"
    ]["data_mapping"]["description"]
    assert "plausible alternative" in mapping_description


def test_record_rules_rejects_guide_rules_when_no_guide_is_relevant() -> None:
    result = record_rules(
        phase="hypothesis",
        guide_status="no_relevant_guide",
        guide_reason="Search results were unrelated.",
        rules=[
            {
                "source": "guide",
                "rule": "Unrelated rule",
                "status": "guide_candidate",
                "source_excerpt": "unrelated",
            }
        ],
    )

    assert result.startswith("Error:")


def test_record_rules_rejects_invalid_guide_status() -> None:
    result = record_rules(
        phase="hypothesis",
        guide_status="unknown",
        guide_reason="Unclear",
        rules=[
            {
                "source": "task",
                "rule": "Return all rows.",
                "status": "task_required",
                "source_excerpt": "all rows",
            }
        ],
    )

    assert result == "Error: invalid guide status 'unknown'."


def test_record_rules_requires_source_excerpt() -> None:
    result = record_rules(
        phase="hypothesis",
        guide_status="no_relevant_guide",
        guide_reason="Search results were unrelated.",
        rules=[
            {
                "source": "task",
                "rule": "Return all rows.",
                "status": "task_required",
            }
        ],
    )

    assert result == "Error: every rule requires a source_excerpt."


def test_record_rules_marks_absent_guide_rules_explicitly() -> None:
    result = record_rules(
        phase="hypothesis",
        guide_status="no_relevant_guide",
        guide_reason="Search results were unrelated.",
        rules=[
            {
                "source": "task",
                "rule": "Return all rows.",
                "status": "task_required",
                "source_excerpt": "all rows",
            }
        ],
    )

    assert "Required task rules:\n- Return all rows." in result
    assert "Candidate guide rules (confirm scope and schema support):\n- None" in result


def test_record_rules_formats_revised_rule_decisions_and_mappings() -> None:
    result = record_rules(
        phase="revised",
        guide_status="applicable",
        guide_reason="The guide contains a potentially relevant eligibility rule.",
        rules=[
            {
                "source": "task",
                "rule": "Return the top ten players.",
                "status": "task_required",
                "source_excerpt": "top ten players",
                "data_mapping": "ORDER BY score DESC LIMIT 10",
            },
            {
                "source": "guide",
                "rule": "Do not exclude short games.",
                "status": "guide_rejected",
                "source_excerpt": "short games should be analyzed separately",
                "data_mapping": "Out of scope: analyzed separately does not mean excluded.",
            },
        ],
    )

    assert result.startswith("Revised rule contract:")
    assert "Data mapping: ORDER BY score DESC LIMIT 10" in result
    assert "- [rejected] Do not exclude short games." in result


def test_revised_rules_require_a_mapping_or_decision_reason() -> None:
    result = record_rules(
        phase="revised",
        guide_status="no_relevant_guide",
        guide_reason="Search results were unrelated.",
        rules=[
            {
                "source": "task",
                "rule": "Return all rows.",
                "status": "task_required",
                "source_excerpt": "all rows",
            }
        ],
    )

    assert result == "Error: every revised rule requires a data_mapping or decision reason."
