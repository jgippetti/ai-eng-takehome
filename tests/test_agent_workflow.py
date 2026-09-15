from framework.agent import Agent, Tool, ToolCall


def _tool(name: str, result: str) -> Tool:
    return Tool(
        name=name,
        description=name,
        parameters={"type": "object", "properties": {}},
        function=lambda **_arguments: result,
    )


def _agent() -> Agent:
    agent = object.__new__(Agent)
    agent._tool_call_results = {}
    agent._duplicate_tool_attempts = {}
    agent._tested_queries = set()
    agent.tools = {
        "search_catalog": _tool("search_catalog", "Catalog matches"),
        "run_query": _tool(
            "run_query", "Query succeeded. Returned 1 preview row(s)."
        ),
        "submit_answer": _tool("submit_answer", "ANSWER_SUBMITTED:SELECT 1"),
    }
    return agent


def _call(name: str, **arguments: str) -> ToolCall:
    return ToolCall(id=name, name=name, arguments=arguments)


def test_duplicate_tool_call_is_rejected_but_new_arguments_are_allowed() -> None:
    agent = _agent()

    assert agent._execute_tool(_call("search_catalog", search_term="sprint")) == (
        "Catalog matches"
    )
    duplicate = agent._execute_tool(_call("search_catalog", search_term="sprint"))

    assert duplicate.startswith("Duplicate tool guard:")
    assert "Previous result: Catalog matches" in duplicate
    assert agent._execute_tool(_call("search_catalog", search_term="race")) == (
        "Catalog matches"
    )


def test_repeated_duplicate_escalates_without_removing_tool() -> None:
    agent = _agent()
    call = _call("search_catalog", search_term="sprint")
    agent._execute_tool(call)
    agent._execute_tool(call)

    escalation = agent._execute_tool(call)

    assert escalation.startswith("Duplicate tool escalation:")
    assert "rejected 2 times" in escalation
    assert "search_catalog" in {
        definition["function"]["name"] for definition in agent._get_tool_definitions()
    }


def test_submission_requires_the_exact_successfully_tested_query() -> None:
    agent = _agent()

    assert agent._execute_tool(_call("submit_answer", query="SELECT 1")).startswith(
        "Submission guard:"
    )
    agent._execute_tool(_call("run_query", query="SELECT 1"))

    assert agent._execute_tool(_call("submit_answer", query="SELECT 2")).startswith(
        "Submission guard:"
    )
    assert agent._execute_tool(_call("submit_answer", query="SELECT 1;")) == (
        "ANSWER_SUBMITTED:SELECT 1"
    )


def test_failed_query_cannot_be_submitted() -> None:
    agent = _agent()
    agent.tools["run_query"] = _tool("run_query", "Query failed: parser error")

    agent._execute_tool(_call("run_query", query="SELECT broken"))

    assert agent._execute_tool(
        _call("submit_answer", query="SELECT broken")
    ).startswith("Submission guard:")
