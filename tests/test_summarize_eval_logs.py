import json
from pathlib import Path

import evaluation.summarize_eval_logs as summarize_eval_logs
from evaluation.summarize_eval_logs import render_trace, summarize_all


def sample_trace(prompt: str = "Find the answer") -> dict:
    return {
        "duration_seconds": 1.25,
        "case": {"prompt": prompt, "gold_query": "SELECT 1"},
        "events": [
            {"type": "ITERATION_START", "data": {"iteration": 1}},
            {"type": "THINKING_CHUNK", "data": {"chunk": "Check"}},
            {"type": "THINKING_CHUNK", "data": {"chunk": " the schema."}},
            {
                "type": "TOOL_CALL_PARSED",
                "data": {"name": "list_tables", "arguments": {"schema_name": "main"}},
            },
            {
                "type": "TOOL_EXECUTION_END",
                "data": {"name": "list_tables", "result": "items"},
            },
        ],
        "result": {
            "passed": True,
            "failure_type": "NONE",
            "submitted_query": "SELECT 1",
            "error": None,
        },
    }


def test_render_trace_combines_thinking_and_includes_tools() -> None:
    trace = sample_trace()

    report = render_trace(trace, case_number=3, trace_name="trace.json")

    assert "# Case 3 trace summary" in report
    assert "Check the schema." in report
    assert "Earlier restatement omitted" not in report
    assert "Tool call: `list_tables`" in report
    assert '"schema_name": "main"' in report
    assert "Result from `list_tables`" in report
    assert "items" in report


def test_summarize_all_writes_index_and_case_reports(
    tmp_path: Path, monkeypatch,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "evals_hard.json").write_text(
        json.dumps([{"prompt": "First"}, {"prompt": "Second"}])
    )
    run_dir = tmp_path / "evals_hard"
    run_dir.mkdir()
    (run_dir / "second.json").write_text(json.dumps(sample_trace("Second")))
    (run_dir / "first.json").write_text(json.dumps(sample_trace("First")))
    monkeypatch.setattr(summarize_eval_logs, "EVAL_DATA_DIR", data_dir)

    output_dir = summarize_all(run_dir)

    assert output_dir == run_dir / "summaries"
    assert (output_dir / "case_1.md").exists()
    assert (output_dir / "case_2.md").exists()
    index = (output_dir / "index.md").read_text()
    assert "| 1 | Passed | 1.25s | [Open](case_1.md) |" in index
    assert index.index("case_1.md") < index.index("case_2.md")


def test_render_trace_keeps_only_the_end_of_long_thinking() -> None:
    trace = sample_trace()
    trace["events"][1:3] = [
        {
            "type": "THINKING_CHUNK",
            "data": {
                "chunk": "Old point one. Old point two. New check one. New check two. "
                "Run the final query."
            },
        }
    ]

    report = render_trace(trace, case_number=1, trace_name="trace.json")

    assert "Old point one" not in report
    assert "Old point two" in report
    assert "Run the final query." in report
    assert "Earlier restatement omitted" in report
