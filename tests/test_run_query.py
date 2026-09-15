from unittest.mock import patch

import polars as pl

from framework.database import QueryExecutionResult, execute_query
from tools.run_query import run_query


def test_run_query_adds_a_preview_limit() -> None:
    dataframe = pl.DataFrame({"status": ["A", "B"]})

    with patch(
        "tools.run_query.execute_query",
        return_value=QueryExecutionResult(dataframe=dataframe),
    ) as execute:
        result = run_query("SELECT status FROM financial.loan LIMIT 5")

    executed_sql = execute.call_args.args[0]
    assert "SELECT status FROM financial.loan LIMIT 5" in executed_sql
    assert executed_sql.endswith("LIMIT 100")
    assert "Returned 2 preview row(s)" in result
    assert "status\nA\nB\n" in result


def test_run_query_executes_the_exact_sql_without_rewriting_it() -> None:
    query = "SELECT  status\nFROM financial.loan\nORDER BY status;"
    dataframe = pl.DataFrame({"status": ["A"]})

    with patch(
        "tools.run_query.execute_query",
        return_value=QueryExecutionResult(dataframe=dataframe),
    ) as execute:
        run_query(query)

    assert execute.call_args.args[0] == (
        "SELECT * FROM (\n"
        "SELECT  status\nFROM financial.loan\nORDER BY status\n"
        ") AS query_preview LIMIT 100"
    )


def test_run_query_rejects_sql_that_only_a_rewriter_could_repair() -> None:
    query = """
        SELECT d.dept_name
        FROM employee.dept_emp de
        WHERE de.to_date = DATE '9999-01-01'
        JOIN employee.departments d ON de.dept_no = d.dept_no
    """

    with patch("tools.run_query.execute_query") as execute:
        result = run_query(query)

    execute.assert_not_called()
    assert result.startswith("Invalid SQL: Parser Error:")


def test_run_query_rejects_non_read_only_sql() -> None:
    with patch("tools.run_query.execute_query") as execute:
        result = run_query("DELETE FROM financial.loan")

    execute.assert_not_called()
    assert result == "Only one read-only SELECT query is allowed."


def test_run_query_rejects_multiple_statements() -> None:
    with patch("tools.run_query.execute_query") as execute:
        result = run_query("SELECT 1; SELECT 2")

    execute.assert_not_called()
    assert result == "Only one read-only SELECT query is allowed."


def test_run_query_returns_database_errors() -> None:
    failure = QueryExecutionResult(dataframe=None, error_message="missing table")

    with patch("tools.run_query.execute_query", return_value=failure):
        result = run_query("SELECT * FROM missing_table")

    assert result == "Query failed: missing table"


def test_execute_query_returns_connection_errors() -> None:
    with patch("framework.database.duckdb.connect", side_effect=OSError("unavailable")):
        result = execute_query("SELECT 1")

    assert not result.is_success
    assert result.error_message == "unavailable"
