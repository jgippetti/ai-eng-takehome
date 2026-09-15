from __future__ import annotations

import json
from collections.abc import Iterator

from rich.console import Console
from rich.markup import escape

from framework.agent import AgentEvent, EventType
from framework.llm import TokenUsage


class StreamPrinter:
    """Helper class to print agent events in a formatted way using rich."""

    def __init__(
        self,
        *,
        show_thinking: bool = True,
        show_tool_calls: bool = True,
        show_tool_results: bool = True,
        show_token_usage: bool = True,
        console: Console | None = None,
    ) -> None:
        """
        Initialize the stream printer.

        Args:
            show_thinking: Whether to display thinking content.
            show_tool_calls: Whether to display tool calls.
            show_tool_results: Whether to display tool results.
            show_token_usage: Whether to display token usage at the end.
            console: Rich Console instance (defaults to new Console with stdout).
        """
        self.show_thinking = show_thinking
        self.show_tool_calls = show_tool_calls
        self.show_tool_results = show_tool_results
        self.show_token_usage = show_token_usage
        self.console = console if console is not None else Console()

    def print_event(self, event: AgentEvent) -> None:
        """Print a single event."""
        match event.type:
            case EventType.ITERATION_START:
                iteration = event.data.get("iteration", "?")
                self.console.print()
                self.console.print(
                    f"--- Iteration {iteration} ---",
                    style="dim",
                )

            case EventType.THINKING_START:
                if self.show_thinking:
                    self.console.print()
                    self.console.print(escape("[Thinking] "), style="cyan", end="")

            case EventType.THINKING_CHUNK:
                if self.show_thinking:
                    chunk = event.data.get("chunk", "")
                    self.console.print(
                        escape(chunk),
                        style="dim",
                        end="",
                    )

            case EventType.THINKING_END:
                if self.show_thinking:
                    self.console.print(escape(" [/Thinking]"), style="cyan")
                    self.console.print()

            case EventType.RESPONSE_CHUNK:
                chunk = event.data.get("chunk", "")
                self.console.print(escape(chunk), end="", highlight=False)

            case EventType.TOOL_CALL_PARSED:
                if self.show_tool_calls:
                    name = event.data.get("name", "unknown")
                    args = event.data.get("arguments", {})
                    args_str = json.dumps(args, indent=2)
                    self.console.print()
                    self.console.print(escape(f"[Tool Call] {name}"), style="yellow")
                    self.console.print(escape(args_str), style="dim")

            case EventType.TOOL_EXECUTION_END:
                if self.show_tool_results:
                    name = event.data.get("name", "unknown")
                    result = event.data.get("result", "")
                    # Truncate long results for display
                    display_result = (
                        result[:1000] + "\n...(truncated for display)"
                        if len(result) > 1000
                        else result
                    )
                    self.console.print(escape(f"[Tool Result] {name}:"), style="green")
                    self.console.print(escape(display_result))

            case EventType.AGENT_COMPLETE:
                self.console.print()
                self.console.print(escape("[Complete]"), style="magenta")
                self._print_usage(event.data.get("usage"))

            case EventType.AGENT_ERROR:
                error = event.data.get("error", "Unknown error")
                self.console.print()
                self.console.print(escape(f"[Error] {error}"), style="bold red")
                self._print_usage(event.data.get("usage"))

    def _print_usage(self, usage: TokenUsage | None) -> None:
        """Print token usage if enabled and available."""
        if not self.show_token_usage or usage is None:
            return
        self.console.print(
            f"[dim]Tokens: {usage.prompt_tokens:,} input, "
            f"{usage.completion_tokens:,} output "
            f"({usage.total_tokens:,} total)[/dim]"
        )

    def print_stream(self, events: Iterator[AgentEvent]) -> str:
        """
        Print all events from a stream and return the final response.

        Args:
            events: Iterator of AgentEvent objects.

        Returns:
            The final response from the agent.
        """
        final_response = ""
        for event in events:
            self.print_event(event)
            if event.type == EventType.AGENT_COMPLETE:
                final_response = event.data.get("response", "")
        return final_response
