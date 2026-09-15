"""Render evaluation traces as compact Markdown summaries."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DATA_DIR = PROJECT_ROOT / "evaluation" / "data"
MAX_TOOL_RESULT_CHARS = 2_000
MAX_THINKING_SENTENCES = 4
MAX_THINKING_CHARS = 1_500


def _load_json(path: Path) -> Any:
    with path.open() as file:
        return json.load(file)


def _load_cases(split: str) -> list[dict[str, str]]:
    return _load_json(EVAL_DATA_DIR / f"evals_{split}.json")


def _case_prompt(split: str, case_number: int) -> str:
    cases = _load_cases(split)
    if not 1 <= case_number <= len(cases):
        raise ValueError(f"Case {case_number} is outside the 1-{len(cases)} range")
    return str(cases[case_number - 1]["prompt"])


def find_trace(run_dir: Path, prompt: str) -> tuple[Path, dict[str, Any]]:
    """Find the JSON trace whose prompt matches the selected evaluation case."""
    for trace_path in sorted(run_dir.glob("*.json")):
        trace = _load_json(trace_path)
        if trace.get("case", {}).get("prompt") == prompt:
            return trace_path, trace
    raise ValueError("The selected case was not found in this run")


def _compact_thinking(chunks: list[str]) -> tuple[str, bool]:
    """Keep the conclusion of an iteration instead of repeated prior reasoning."""
    thinking = re.sub(r"\s+", " ", "".join(chunks)).strip()
    if not thinking:
        return "", False

    sentences = re.split(r"(?<=[.!?])\s+", thinking)
    was_shortened = len(sentences) > MAX_THINKING_SENTENCES
    if was_shortened:
        thinking = " ".join(sentences[-MAX_THINKING_SENTENCES:])

    if len(thinking) > MAX_THINKING_CHARS:
        thinking = thinking[-MAX_THINKING_CHARS:].lstrip()
        was_shortened = True

    return thinking, was_shortened


def _tool_result(value: Any) -> str:
    result = str(value)
    if len(result) <= MAX_TOOL_RESULT_CHARS:
        return result
    omitted = len(result) - MAX_TOOL_RESULT_CHARS
    return f"{result[:MAX_TOOL_RESULT_CHARS]}\n\n[Truncated {omitted} characters]"


def render_trace(trace: dict[str, Any], case_number: int, trace_name: str) -> str:
    """Convert a trace dictionary into readable Markdown."""
    result = trace["result"]
    case = trace["case"]
    status = "PASSED" if result["passed"] else "FAILED"
    tool_names = [
        event["data"]["name"]
        for event in trace["events"]
        if event["type"] == "TOOL_CALL_PARSED"
    ]
    tool_counts = ", ".join(
        f"{name}: {count}" for name, count in Counter(tool_names).items()
    )

    lines = [
        f"# Case {case_number} trace summary",
        "",
        f"- **Status:** {status} ({result['failure_type']})",
        f"- **Duration:** {trace.get('duration_seconds', 0):.2f} seconds",
        f"- **Trace:** `{trace_name}`",
        f"- **Tool calls:** {tool_counts or 'none'}",
    ]
    if result.get("error"):
        lines.append(f"- **Error:** {result['error']}")

    lines.extend(
        [
            "",
            "## Question",
            "",
            case["prompt"],
            "",
            "## Expected SQL",
            "",
            "```sql",
            case["gold_query"],
            "```",
            "",
            "## Submitted SQL",
            "",
            "```sql",
            result.get("submitted_query") or "-- No query submitted",
            "```",
            "",
            "## Timeline",
        ]
    )

    current_iteration: int | None = None
    thinking_chunks: list[str] = []

    def flush_thinking() -> None:
        thinking, was_shortened = _compact_thinking(thinking_chunks)
        if thinking:
            lines.extend(["", "**Thinking — conclusion for this iteration**", ""])
            if was_shortened:
                lines.extend(
                    [
                        "_Earlier restatement omitted; the complete reasoning remains in the "
                        "source JSON._",
                        "",
                    ]
                )
            lines.append(thinking)
        thinking_chunks.clear()

    for event in trace["events"]:
        event_type = event["type"]
        data = event["data"]
        if event_type == "ITERATION_START":
            flush_thinking()
            current_iteration = int(data["iteration"])
            lines.extend(["", f"### Iteration {current_iteration}"])
        elif event_type == "THINKING_CHUNK":
            thinking_chunks.append(str(data["chunk"]))
        elif event_type == "TOOL_CALL_PARSED":
            flush_thinking()
            lines.extend(
                [
                    "",
                    f"#### Tool call: `{data['name']}`",
                    "",
                    "```json",
                    json.dumps(data.get("arguments", {}), indent=2),
                    "```",
                ]
            )
        elif event_type == "TOOL_EXECUTION_END":
            lines.extend(
                [
                    "",
                    f"**Result from `{data['name']}`**",
                    "",
                    "```text",
                    _tool_result(data.get("result", "")),
                    "```",
                ]
            )
    flush_thinking()
    return "\n".join(lines) + "\n"


def inspect_case(run_dir: Path, case_number: int) -> Path:
    """Write the selected case summary inside its run directory."""
    split_dir = run_dir.name
    if split_dir not in {"evals_easy", "evals_hard"}:
        raise ValueError("Run directory must end in evals_easy or evals_hard")

    split = split_dir.removeprefix("evals_")
    prompt = _case_prompt(split, case_number)
    trace_path, trace = find_trace(run_dir, prompt)
    output_path = run_dir / f"case_{case_number}_summary.md"
    output_path.write_text(render_trace(trace, case_number, trace_path.name))
    return output_path


def summarize_all(run_dir: Path) -> Path:
    """Write summaries for every trace in a run and link them from an index."""
    split_dir = run_dir.name
    if split_dir not in {"evals_easy", "evals_hard"}:
        raise ValueError("Run directory must end in evals_easy or evals_hard")

    split = split_dir.removeprefix("evals_")
    case_numbers = {
        case["prompt"]: case_number
        for case_number, case in enumerate(_load_cases(split), start=1)
    }
    summaries: list[tuple[int, dict[str, Any], str]] = []
    for trace_path in sorted(run_dir.glob("*.json")):
        trace = _load_json(trace_path)
        prompt = trace.get("case", {}).get("prompt")
        if prompt not in case_numbers:
            raise ValueError(f"Could not match {trace_path.name} to an evaluation case")
        summaries.append((case_numbers[prompt], trace, trace_path.name))

    if not summaries:
        raise ValueError("No JSON traces were found in this run")

    output_dir = run_dir / "summaries"
    output_dir.mkdir(exist_ok=True)
    index_lines = [
        "# Evaluation trace summaries",
        "",
        "| Case | Status | Duration | Report |",
        "| ---: | --- | ---: | --- |",
    ]
    for case_number, trace, trace_name in sorted(summaries):
        report_name = f"case_{case_number}.md"
        (output_dir / report_name).write_text(
            render_trace(trace, case_number, trace_name)
        )
        result = trace["result"]
        status = "Passed" if result["passed"] else f"Failed ({result['failure_type']})"
        duration = trace.get("duration_seconds", 0)
        index_lines.append(
            f"| {case_number} | {status} | {duration:.2f}s | [Open]({report_name}) |"
        )

    (output_dir / "index.md").write_text("\n".join(index_lines) + "\n")
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Path to an evals_easy or evals_hard run")
    parser.add_argument("--case", type=int, help="One-based evaluation case")
    args = parser.parse_args()

    try:
        output_path = (
            inspect_case(args.run_dir, args.case)
            if args.case is not None
            else summarize_all(args.run_dir)
        )
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    print(output_path)


if __name__ == "__main__":
    main()
