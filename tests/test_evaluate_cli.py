import argparse
import json
from pathlib import Path

import pytest

from evaluation.evaluate import (
    EvalCase,
    EvalResult,
    EvalSplitResults,
    FailureType,
    build_run_config,
    create_tools,
    parse_case_numbers,
    positive_int,
    save_run_summary,
    select_eval_cases,
)
from framework.llm import OpenRouterConfig, TokenUsage


def test_parse_case_numbers() -> None:
    assert parse_case_numbers("5, 15,16,19") == [5, 15, 16, 19]


@pytest.mark.parametrize("value", ["", "0", "1,two", "5,5"])
def test_parse_case_numbers_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_case_numbers(value)


def test_positive_int() -> None:
    assert positive_int("20") == 20
    with pytest.raises(argparse.ArgumentTypeError):
        positive_int("0")


def test_select_eval_cases_uses_one_based_positions_in_requested_order() -> None:
    cases = [
        EvalCase(prompt=f"prompt {number}", gold_query=f"query {number}")
        for number in range(1, 5)
    ]

    selected = select_eval_cases(cases, [3, 1])

    assert [case.prompt for case in selected] == ["prompt 3", "prompt 1"]


def test_select_eval_cases_rejects_out_of_range_positions() -> None:
    cases = [EvalCase(prompt="prompt", gold_query="query")]

    with pytest.raises(ValueError, match=r"Case number\(s\) out of range: 2"):
        select_eval_cases(cases, [2])


def test_build_run_config_records_runtime_settings_without_api_key() -> None:
    args = argparse.Namespace(
        split="hard",
        cases=[13, 46],
        limit=None,
        concurrency=8,
        prompt="output-shape",
    )

    config = build_run_config(args, {"search_guides": object()})

    assert config["evaluation"]["cases"] == [13, 46]
    assert config["evaluation"]["prompt"] == "output-shape"
    assert config["model"]["temperature"] == OpenRouterConfig().temperature
    assert config["model"]["max_iterations"] == OpenRouterConfig().max_iterations
    assert "api_key" not in json.dumps(config)


def test_create_tools_includes_agent_exploration_and_submission_tools() -> None:
    tools = create_tools()

    assert "search_guides" in tools
    assert "read_guide" in tools
    assert "run_query" in tools
    assert "submit_answer" in tools


def test_create_tools_can_include_record_rules_for_prompt_experiments() -> None:
    assert "record_rules" not in create_tools()
    assert "record_rules" in create_tools(include_record_rules=True)


def test_save_run_summary_records_counts_and_tokens(tmp_path: Path) -> None:
    case = EvalCase(prompt="question", gold_query="SELECT 1")
    results = [
        EvalResult(
            case=case,
            submitted_query="SELECT 1",
            passed=True,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=2),
        ),
        EvalResult(
            case=case,
            submitted_query="SELECT 2",
            passed=False,
            failure_type=FailureType.MISMATCH,
            usage=TokenUsage(prompt_tokens=20, completion_tokens=3),
        ),
        EvalResult(
            case=case,
            submitted_query=None,
            passed=False,
            failure_type=FailureType.AGENT_ERROR,
        ),
    ]

    path = save_run_summary([EvalSplitResults(name="evals_hard", results=results)], tmp_path)
    summary = json.loads(path.read_text())

    assert summary["overall"]["passed"] == 1
    assert summary["overall"]["mismatch"] == 1
    assert summary["overall"]["other"] == 1
    assert summary["overall"]["pass_rate"] == pytest.approx(1 / 3)
    assert summary["overall"]["failure_types"] == {"MISMATCH": 1, "AGENT_ERROR": 1}
    assert summary["overall"]["token_usage"] == {
        "input": 30,
        "output": 5,
        "total": 35,
    }
