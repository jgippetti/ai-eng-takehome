from types import SimpleNamespace

from framework.agent import (
    ANSWER_SUBMITTED_PREFIX,
    Agent,
    AgentEvent,
    Conversation,
    EventType,
    Tool,
)


def test_plain_text_sql_is_retried_until_submit_answer_is_called() -> None:
    agent = object.__new__(Agent)
    agent.config = SimpleNamespace(max_iterations=2)
    agent.conversation = Conversation()
    agent.tools = {
        "submit_answer": Tool(
            name="submit_answer",
            description="submit",
            parameters={"type": "object", "properties": {}},
            function=lambda query: f"{ANSWER_SUBMITTED_PREFIX}{query}",
        )
    }
    responses = iter(
        [
            AgentEvent(
                type=EventType.GENERATION_END,
                data={
                    "full_response": "SELECT 1",
                    "tool_calls": [],
                    "finish_reason": "stop",
                },
            ),
            AgentEvent(
                type=EventType.GENERATION_END,
                data={
                    "full_response": "",
                    "tool_calls": [
                        {
                            "id": "submit-1",
                            "type": "function",
                            "function": {
                                "name": "submit_answer",
                                "arguments": '{"query":"SELECT 1"}',
                            },
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
            ),
        ]
    )
    agent._generate_response = lambda conversation: iter([next(responses)])  # type: ignore[method-assign]

    events = list(agent.run("Return one"))

    assert any(event.type == EventType.AGENT_COMPLETE for event in events)
    assert not any(event.type == EventType.AGENT_ERROR for event in events)
    assert any(
        message.role == "user" and "submit_answer TOOL" in (message.content or "")
        for message in agent.conversation.messages
    )
