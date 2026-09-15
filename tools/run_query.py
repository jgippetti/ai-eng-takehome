"""Tool for running small, read-only query previews against the database."""

import duckdb

from framework.agent import Tool
from framework.database import execute_query

_MAX_PREVIEW_ROWS = 100


def run_query(query: str) -> str:
    """Run one read-only query and return at most 100 result rows."""
    try:
        statements = duckdb.extract_statements(query)
    except duckdb.Error as error:
        return f"Invalid SQL: {error}"

    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        return "Only one read-only SELECT query is allowed."

    # The outer LIMIT preserves a smaller LIMIT in the submitted query while
    # preventing exploratory calls from returning too much data to the model.
    # Execute the agent's SQL text directly so a successful preview proves the
    # same query can be submitted without a parser silently rewriting it.
    exact_query = query.strip().removesuffix(";").rstrip()
    preview_query = (
        f"SELECT * FROM (\n{exact_query}\n) AS query_preview LIMIT {_MAX_PREVIEW_ROWS}"
    )
    result = execute_query(preview_query)

    if not result.is_success:
        return f"Query failed: {result.error_message}"
    if result.dataframe is None:
        return "Query failed: no result was returned."

    preview = result.dataframe.write_csv()
    return (
        f"Query succeeded. Returned {result.dataframe.height} preview row(s) "
        f"(maximum {_MAX_PREVIEW_ROWS}).\n{preview}"
    )


RUN_QUERY = Tool(
    name="run_query",
    description=(
        "Run one read-only SQL query against the DuckDB database and inspect up to 100 rows. "
        "Use this after the schema tools to inspect representative values and test a candidate "
        "query before calling submit_answer. Use your best judgment about result size; data "
        "exploration should select only the needed columns and use a smaller LIMIT."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A single read-only SELECT query using DuckDB SQL.",
            },
        },
        "required": ["query"],
    },
    function=run_query,
)
