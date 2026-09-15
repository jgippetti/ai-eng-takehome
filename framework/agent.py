"""Agent framework for autonomous task execution with tool calling.

This module implements an agent that uses the OpenRouter API for LLM inference,
supporting streaming responses, tool calling, and reasoning token display.
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

from framework.llm import OpenRouterClient, OpenRouterConfig, TokenUsage

# Prefix that indicates the agent should stop (answer was submitted)
# This avoids global state - the tool result signals completion
ANSWER_SUBMITTED_PREFIX = "ANSWER_SUBMITTED:"
SQL_AGENT_PROMPT_PATH = Path(__file__).with_name("prompts") / "sql_agent.md"
PROMPT_PATHS = {
    "original": Path(__file__).with_name("prompts") / "original.md",
    "baseline": SQL_AGENT_PROMPT_PATH,
    "output-shape": Path(__file__).with_name("prompts") / "output_shape.md",
    "human-workflow": Path(__file__).with_name("prompts") / "human_workflow.md",
    "iterative-rules": Path(__file__).with_name("prompts") / "iterative_rules.md",
}
_GUIDED_WORKFLOW_PROMPTS = {"iterative-rules"}
_TOOLS_REQUIRING_RECORDED_RULES = {
    "list_schemas",
    "search_catalog",
    "list_tables",
    "describe_table",
    "run_query",
    "submit_answer",
}
_NON_REPEATABLE_TOOLS = {
    "search_guides",
    "read_guide",
    "list_schemas",
    "search_catalog",
    "list_tables",
    "describe_table",
    "run_query",
}
type ToolFunction = Callable[..., str]


def prompt_requires_record_rules(prompt_name: str) -> bool:
    """Return whether a prompt uses the optional rule-recording tool."""
    return prompt_name in _GUIDED_WORKFLOW_PROMPTS


class EventType(Enum):
    """Types of events emitted during agent execution."""

    # Generation events
    GENERATION_START = auto()
    THINKING_START = auto()
    THINKING_CHUNK = auto()
    THINKING_END = auto()
    RESPONSE_CHUNK = auto()
    GENERATION_END = auto()

    # Tool events
    TOOL_CALL_START = auto()
    TOOL_CALL_PARSED = auto()
    TOOL_EXECUTION_START = auto()
    TOOL_EXECUTION_END = auto()

    # Agent loop events
    ITERATION_START = auto()
    ITERATION_END = auto()
    AGENT_COMPLETE = auto()
    AGENT_ERROR = auto()


@dataclass
class AgentEvent:
    """An event emitted during agent execution."""

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        """Format event for display."""
        return f"[{self.type.name}] {self.data}"


@dataclass
class Tool:
    """Represents a tool that can be called by the agent.

    Tool functions must return a string that will be shown to the LLM.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    function: ToolFunction


@dataclass
class ToolCall:
    """Represents a (parsed) tool call request from the agent."""

    id: str  # Required for OpenAI-compatible API
    name: str
    arguments: dict[str, Any]
    error: str | None = None


@dataclass
class Message:
    """Represents a message in the conversation."""

    role: str  # "system", "user", "assistant", or "tool"
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None  # For assistant messages with tool calls
    tool_call_id: str | None = None  # For tool result messages


@dataclass
class ContextCompressionSettings:
    """Settings for context compression to reduce token usage."""

    enabled: bool = False
    keep_recent: int = 3  # Number of recent tool results to keep in full
    max_chars: int = 150  # Max chars for truncated older results


@dataclass
class Conversation:
    """Represents a conversation between the agent and the user."""

    messages: list[Message] = field(default_factory=list)

    def to_api_format(
        self,
        compression: ContextCompressionSettings | None = None,
    ) -> list[dict[str, Any]]:
        """Convert the conversation to OpenAI-compatible API format.

        Args:
            compression: Optional compression settings. If enabled, older tool
                results are truncated and duplicate consecutive tool calls are
                deduplicated.
        """
        messages_to_convert = self.messages

        if compression and compression.enabled:
            messages_to_convert = _compress_messages(
                self.messages,
                keep_recent=compression.keep_recent,
                max_chars=compression.max_chars,
            )

        result: list[dict[str, Any]] = []
        for message in messages_to_convert:
            msg: dict[str, Any] = {"role": message.role}

            if message.content is not None:
                msg["content"] = message.content

            if message.tool_calls is not None:
                msg["tool_calls"] = message.tool_calls

            if message.tool_call_id is not None:
                msg["tool_call_id"] = message.tool_call_id

            result.append(msg)
        return result


def _truncate_tool_result(content: str, max_chars: int) -> str:
    """Truncate a tool result to max_chars with a summary prefix."""
    if len(content) <= max_chars:
        return content

    # Extract first line as summary (often contains row/column counts)
    first_line = content.split("\n")[0]
    if len(first_line) <= max_chars - 20:
        return f"[Truncated] {first_line}"

    return f"[Truncated] {content[:max_chars - 15]}..."


def _compress_messages(
    messages: list[Message],
    keep_recent: int,
    max_chars: int,
) -> list[Message]:
    """Compress messages by truncating old tool results and deduplicating.

    Applies two optimizations:
    1. Truncates tool results older than keep_recent to max_chars
    2. Removes duplicate consecutive tool calls with identical results
    """
    # Find all tool message indices (for determining which are "recent")
    tool_indices: list[int] = [
        i for i, m in enumerate(messages) if m.role == "tool"
    ]

    # Indices of tool messages to keep in full (the most recent ones)
    recent_tool_indices = set(tool_indices[-keep_recent:]) if tool_indices else set()

    # Build compressed message list
    result: list[Message] = []
    seen_tool_calls: dict[str, str] = {}  # (name, args_json) -> full result

    for i, msg in enumerate(messages):
        if msg.role == "tool":
            # Check for deduplication: same tool call with same result
            # Find the corresponding assistant message's tool call
            tool_key: str | None = None
            for j in range(i - 1, -1, -1):
                assistant_tool_calls = messages[j].tool_calls
                if messages[j].role == "assistant" and assistant_tool_calls:
                    for tc in assistant_tool_calls:
                        if tc.get("id") == msg.tool_call_id:
                            name = tc.get("function", {}).get("name", "")
                            args = tc.get("function", {}).get("arguments", "")
                            tool_key = f"{name}:{args}"
                            break
                    break

            # Deduplicate: if we've seen this exact call before with same result
            if tool_key and msg.content:
                if tool_key in seen_tool_calls:
                    prev_content = seen_tool_calls[tool_key]
                    if prev_content == msg.content:
                        # Skip this duplicate - but we need to keep the message
                        # structure for the API, so mark it as deduplicated
                        result.append(
                            Message(
                                role=msg.role,
                                content="[Duplicate call - see earlier result]",
                                tool_call_id=msg.tool_call_id,
                            )
                        )
                        continue
                seen_tool_calls[tool_key] = msg.content

            # Truncate if not in recent set
            if i not in recent_tool_indices and msg.content:
                result.append(
                    Message(
                        role=msg.role,
                        content=_truncate_tool_result(msg.content, max_chars),
                        tool_call_id=msg.tool_call_id,
                    )
                )
            else:
                result.append(msg)
        else:
            result.append(msg)

    return result


class Agent:
    """Implements a tiny, generic agent framework.

    Built on top of the OpenRouter API client.

    Only supports a single model, streaming, and an extensible tool set.
    """

    def __init__(
        self,
        config: OpenRouterConfig,
        tools: dict[str, Tool],
        prompt_name: str = "output-shape",
    ):
        if prompt_name not in PROMPT_PATHS:
            choices = ", ".join(PROMPT_PATHS)
            raise ValueError(f"Unknown prompt '{prompt_name}'. Choose from: {choices}")
        self.config = config
        self.tools: dict[str, Tool] = tools  # mapping from tool name to tool object
        self.prompt_name = prompt_name
        self.client: OpenRouterClient = OpenRouterClient(config)
        self.conversation: Conversation = Conversation()
        self._compression = ContextCompressionSettings(
            enabled=config.compress_context,
            keep_recent=config.compress_keep_recent,
            max_chars=config.compress_max_chars,
        )
        self.reset_conversation()

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get tool definitions in OpenAI-compatible format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self.tools.values()
        ]

    def _execute_tool(self, tool_call: ToolCall) -> str:
        """Execute a tool call and return the result as a string.

        Guaranteed to return a string, swallowing exceptions.
        """
        if tool_call.error:
            return f"Error parsing arguments for tool '{tool_call.name}': {tool_call.error}"

        if tool_call.name not in self.tools:
            return f"Error: Unknown tool '{tool_call.name}'"
        guard_message = self._workflow_guard(tool_call)
        if guard_message is not None:
            return guard_message

        submission_message = self._submission_guard(tool_call)
        if submission_message is not None:
            return submission_message

        duplicate_message = self._duplicate_tool_guard(tool_call)
        if duplicate_message is not None:
            return duplicate_message

        tool = self.tools[tool_call.name]
        try:
            result = tool.function(**tool_call.arguments)
        except Exception as e:
            return f"Error executing {tool_call.name}: {e}"

        if tool_call.name in _NON_REPEATABLE_TOOLS:
            self._tool_call_results[self._tool_call_key(tool_call)] = result
        if tool_call.name == "run_query" and result.startswith("Query succeeded"):
            query = tool_call.arguments.get("query")
            if isinstance(query, str):
                query_identity = self._query_identity(query)
                self._tested_queries.add(query_identity)
        self._record_workflow_step(tool_call.name, result)
        return result

    @staticmethod
    def _query_identity(query: str) -> str:
        """Normalize harmless outer whitespace for tested-query comparisons."""
        return query.strip().removesuffix(";").rstrip()

    def _submission_guard(self, tool_call: ToolCall) -> str | None:
        """Require the submitted SQL to match a query that ran successfully."""
        if tool_call.name != "submit_answer" or "run_query" not in self.tools:
            return None

        query = tool_call.arguments.get("query")
        query_identity = self._query_identity(query) if isinstance(query, str) else None
        if query_identity not in self._tested_queries:
            return (
                "Submission guard: this exact SQL has not succeeded through run_query. "
                "Call run_query with the exact final SQL, fix any error it reports, inspect "
                "the result, and then submit the same SQL without editing it."
            )
        return None

    @staticmethod
    def _tool_call_key(tool_call: ToolCall) -> str:
        """Return a stable identity for a tool name and its arguments."""
        arguments = json.dumps(tool_call.arguments, sort_keys=True, separators=(",", ":"))
        return f"{tool_call.name}:{arguments}"

    def _duplicate_tool_guard(self, tool_call: ToolCall) -> str | None:
        """Reject repeated exploration calls whose result is already in context."""
        if tool_call.name not in _NON_REPEATABLE_TOOLS:
            return None
        key = self._tool_call_key(tool_call)
        if key not in self._tool_call_results:
            return None

        attempts = self._duplicate_tool_attempts.get(key, 0) + 1
        self._duplicate_tool_attempts[key] = attempts
        previous_result = _truncate_tool_result(self._tool_call_results[key], 300)

        if attempts == 1:
            return (
                f"Duplicate tool guard: {tool_call.name} was already called with these exact "
                f"arguments. Previous result: {previous_result}\n"
                "Required next action: do not repeat this call. Use the existing result, "
                "choose meaningfully different arguments based on new evidence, or proceed "
                "with the best-supported query."
            )

        return (
            f"Duplicate tool escalation: this exact {tool_call.name} call has now been "
            f"rejected {attempts} times. Previous result: {previous_result}\n"
            "Required next action: stop exploring this concept. Do not issue this call or an "
            "equivalent search again"
        )

    def _workflow_guard(self, tool_call: ToolCall) -> str | None:
        """Return corrective guidance when iterative-rules tools are out of order."""
        if getattr(self, "prompt_name", "output-shape") not in _GUIDED_WORKFLOW_PROMPTS:
            return None

        tool_name = tool_call.name
        if tool_name == "read_guide" and "search_guides" not in self._workflow_steps:
            return "Workflow guard: call search_guides before read_guide."

        if tool_name == "record_rules":
            if "search_guides" not in self._workflow_steps:
                return "Workflow guard: call search_guides before record_rules."
            guide_status = tool_call.arguments.get("guide_status")
            if (
                guide_status != "no_relevant_guide"
                and "read_guide" not in self._workflow_steps
            ):
                return (
                    "Workflow guard: read the complete relevant guide with read_guide before "
                    "recording applicable guide rules. If no search result is plausibly "
                    "relevant, call record_rules with guide_status='no_relevant_guide' and "
                    "record task rules only."
                )
            if tool_call.arguments.get("phase") == "revised":
                if "rule_hypothesis" not in self._workflow_steps:
                    return "Workflow guard: record a rule hypothesis before revising it."
                if "describe_table" not in self._workflow_steps:
                    return (
                        "Workflow guard: inspect candidate tables with describe_table before "
                        "recording the revised rule contract."
                    )

        if tool_name in _TOOLS_REQUIRING_RECORDED_RULES:
            if "rule_hypothesis" not in self._workflow_steps:
                return (
                    f"Workflow guard: call record_rules with phase='hypothesis' before "
                    f"{tool_name}. First search the guides, read the complete relevant guide, "
                    "and record the important task and candidate guide rules."
                )
            if tool_name == "submit_answer" and "revised_rules" not in self._workflow_steps:
                return (
                    "Workflow guard: call record_rules with phase='revised' after inspecting "
                    "the data and before submit_answer."
                )

        return None

    def _record_workflow_step(self, tool_name: str, result: str) -> None:
        """Update successful iterative-rules workflow checkpoints."""
        if getattr(self, "prompt_name", "output-shape") not in _GUIDED_WORKFLOW_PROMPTS:
            return

        if tool_name == "search_guides":
            self._workflow_steps.add(tool_name)
        elif tool_name == "read_guide" and result.startswith("Guide:"):
            self._workflow_steps.add(tool_name)
            self._workflow_steps.discard("revised_rules")
        elif tool_name == "record_rules" and result.startswith("Rule hypothesis:"):
            self._workflow_steps.add("rule_hypothesis")
            self._workflow_steps.discard("revised_rules")
        elif tool_name == "record_rules" and result.startswith("Revised rule contract:"):
            self._workflow_steps.add("revised_rules")
        elif tool_name == "describe_table" and result.startswith("Columns in"):
            self._workflow_steps.add("describe_table")

    def _generate_response(self, conversation: Conversation) -> Iterator[AgentEvent]:
        """Generate a response from the model, streaming the events out."""
        yield AgentEvent(type=EventType.GENERATION_START)

        messages = conversation.to_api_format(compression=self._compression)
        tools = self._get_tool_definitions() if self.tools else None

        full_content = ""
        tool_calls: list[dict[str, Any]] = []
        in_thinking = False
        finish_reason: str | None = None
        usage: TokenUsage | None = None

        for chunk in self.client.chat_completion_stream(messages, tools):
            # Handle reasoning/thinking tokens
            if chunk.reasoning_details:
                for detail in chunk.reasoning_details:
                    if detail.get("type") == "reasoning.text":
                        text = detail.get("text", "")
                        if text:
                            if not in_thinking:
                                in_thinking = True
                                yield AgentEvent(type=EventType.THINKING_START)
                            yield AgentEvent(
                                type=EventType.THINKING_CHUNK,
                                data={"chunk": text},
                            )

            # Handle regular content
            if chunk.content:
                # Close thinking block if we were in it
                if in_thinking:
                    in_thinking = False
                    yield AgentEvent(type=EventType.THINKING_END)

                full_content += chunk.content
                yield AgentEvent(
                    type=EventType.RESPONSE_CHUNK,
                    data={"chunk": chunk.content},
                )

            # Handle tool calls (accumulated at the end)
            if chunk.tool_calls:
                tool_calls = chunk.tool_calls

            if chunk.finish_reason:
                finish_reason = chunk.finish_reason

            # Capture usage data (comes in final chunk)
            if chunk.usage:
                usage = chunk.usage

        # Close thinking if still open
        if in_thinking:
            yield AgentEvent(type=EventType.THINKING_END)

        event_data: dict[str, Any] = {
            "full_response": full_content,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
        }
        if usage:
            event_data["usage"] = usage

        yield AgentEvent(type=EventType.GENERATION_END, data=event_data)

    def _get_system_message(self) -> str:
        """Get the system message for the agent."""
        prompt_name = getattr(self, "prompt_name", "output-shape")
        return PROMPT_PATHS[prompt_name].read_text(encoding="utf-8").strip()

    def run(self, prompt: str) -> Iterator[AgentEvent]:
        """Run the agent with streaming output, from the user's natural language prompt."""
        self._tested_queries = set()
        # Add the new user message to the ongoing conversation
        self.conversation.messages.append(Message(role="user", content=prompt))

        # Track cumulative token usage across all iterations
        total_usage = TokenUsage()

        for iteration in range(self.config.max_iterations):
            yield AgentEvent(type=EventType.ITERATION_START, data={"iteration": iteration + 1})

            full_response = ""
            tool_calls_data: list[dict[str, Any]] = []

            for event in self._generate_response(self.conversation):
                yield event
                if event.type == EventType.GENERATION_END:
                    full_response = event.data.get("full_response", "")
                    tool_calls_data = event.data.get("tool_calls", [])
                    # Accumulate token usage
                    if "usage" in event.data and event.data["usage"]:
                        total_usage = total_usage + event.data["usage"]

            # Parse tool calls from the structured response
            tool_calls = _parse_tool_calls_from_api(tool_calls_data)

            if not tool_calls:
                # Check if this is an empty response (model just stopped)
                is_empty_response = not full_response or not full_response.strip()

                # Check if response looks like a malformed tool call (JSON with "query" key)
                # This happens when the model outputs tool call arguments as plain text
                looks_like_failed_tool_call = (full_response and "{" in full_response)

                submission_required = "submit_answer" in self.tools
                if submission_required or is_empty_response or looks_like_failed_tool_call:
                    # The SQL workflow is incomplete until submit_answer is called.
                    if looks_like_failed_tool_call:
                        print("\n[DEBUG] Response looks like failed tool call "
                              "- injecting continuation prompt")
                    elif is_empty_response:
                        print("\n[DEBUG] Empty response detected "
                              "- injecting continuation prompt")
                    else:
                        print("\n[DEBUG] Response did not call submit_answer "
                              "- injecting continuation prompt")

                    self.conversation.messages.append(
                        Message(role="assistant", content=full_response if full_response else "")
                    )
                    self.conversation.messages.append(
                        Message(
                            role="user",
                            content=(
                                "You must use the submit_answer TOOL to submit your "
                                "answer - do not output JSON directly. "
                                "Call the submit_answer tool now with your SQL query."
                            ),
                        )
                    )
                    # Continue to next iteration instead of returning
                    continue

                # Non-empty response without tool calls - agent is done
                self.conversation.messages.append(
                    Message(role="assistant", content=full_response)
                )
                yield AgentEvent(
                    type=EventType.AGENT_COMPLETE,
                    data={"response": full_response, "usage": total_usage},
                )
                return

            yield AgentEvent(type=EventType.TOOL_CALL_START, data={"count": len(tool_calls)})

            # Save assistant message with tool calls
            self.conversation.messages.append(
                Message(
                    role="assistant",
                    content=full_response if full_response else None,
                    tool_calls=tool_calls_data,
                )
            )

            for tool_call in tool_calls:
                yield AgentEvent(
                    type=EventType.TOOL_CALL_PARSED,
                    data={"name": tool_call.name, "arguments": tool_call.arguments},
                )
                yield AgentEvent(
                    type=EventType.TOOL_EXECUTION_START,
                    data={"name": tool_call.name},
                )
                tool_result = self._execute_tool(tool_call)
                yield AgentEvent(
                    type=EventType.TOOL_EXECUTION_END,
                    data={"name": tool_call.name, "result": tool_result},
                )

                # Add tool result message with tool_call_id
                self.conversation.messages.append(
                    Message(
                        role="tool",
                        content=tool_result,
                        tool_call_id=tool_call.id,
                    )
                )

                # Check if this tool signals agent completion (e.g., answer submitted)
                if tool_result.startswith(ANSWER_SUBMITTED_PREFIX):
                    yield AgentEvent(
                        type=EventType.AGENT_COMPLETE,
                        data={
                            "reason": "answer_submitted",
                            "tool": tool_call.name,
                            "usage": total_usage,
                        },
                    )
                    return

            yield AgentEvent(type=EventType.ITERATION_END, data={"iteration": iteration + 1})

        yield AgentEvent(
            type=EventType.AGENT_ERROR,
            data={"error": "Max iterations reached", "usage": total_usage},
        )

    def reset_conversation(self) -> None:
        """Reset the conversation to the initial state (with system message)."""
        self._workflow_steps: set[str] = set()
        self._tool_call_results: dict[str, str] = {}
        self._duplicate_tool_attempts: dict[str, int] = {}
        self._tested_queries: set[str] = set()
        self.conversation = Conversation()
        self.conversation.messages.append(
            Message(role="system", content=self._get_system_message())
        )


def _parse_tool_calls_from_api(tool_calls_data: list[dict[str, Any]]) -> list[ToolCall]:
    """Parse tool calls from OpenAI-compatible API response format."""
    tool_calls: list[ToolCall] = []

    for tc in tool_calls_data:
        tc_id = tc.get("id", "")
        function = tc.get("function", {})
        name = function.get("name", "")
        arguments_str = function.get("arguments", "{}")

        try:
            arguments = json.loads(arguments_str)
            error = None
        except json.JSONDecodeError as e:
            # Don't print to stdout, return error in ToolCall
            arguments = {}
            error = f"Invalid JSON arguments: {e}"

        tool_calls.append(
            ToolCall(
                id=tc_id,
                name=name,
                arguments=arguments,
                error=error,
            )
        )

    return tool_calls
