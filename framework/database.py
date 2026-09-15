"""Database tooling for executing SQL queries against the consolidated DuckDB database.

All CTU Relational databases are consolidated into a single DuckDB file (hecks.duckdb)
with each original database as its own schema. Queries use schema.table syntax.

Example:
    >>> result = execute_query("SELECT * FROM financial.account LIMIT 10")
    >>> if result.is_success:
    ...     print(result.dataframe)
"""

from dataclasses import dataclass
from pathlib import Path

import duckdb
import polars as pl

# Path to the consolidated database file
DATABASE_PATH = Path(__file__).parent.parent / "hecks.duckdb"

@dataclass
class QueryExecutionResult:
    """Result of executing a SQL query.

    Attributes:
        dataframe: The query results as a Polars DataFrame, or None if error.
        error_message: Error message if execution failed, None otherwise.
    """

    dataframe: pl.DataFrame | None
    error_message: str | None = None

    @property
    def is_success(self) -> bool:
        """Return True if the query executed successfully."""
        return self.error_message is None

    @property
    def is_empty(self) -> bool:
        """Return True if the query succeeded but returned no rows."""
        return self.is_success and self.dataframe is not None and self.dataframe.is_empty()


def execute_query(query: str) -> QueryExecutionResult:
    """Execute a SQL query against the consolidated database.

    Queries should use schema.table syntax (e.g., "SELECT * FROM financial.account").

    Args:
        query: SQL query string with schema-qualified table names.

    Returns:
        QueryExecutionResult containing either:
        - A Polars DataFrame with the query results (on success)
        - An error message describing what went wrong (on failure)

    Example:
        >>> result = execute_query("SELECT * FROM financial.account LIMIT 10")
        >>> if result.is_success:
        ...     print(result.dataframe)
        ... else:
        ...     print(f"Error: {result.error_message}")
    """
    try:
        with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
            result = connection.execute(query)
            df = pl.DataFrame(result.fetch_arrow_table())
        return QueryExecutionResult(dataframe=df)
    except duckdb.Error as e:
        return QueryExecutionResult(dataframe=None, error_message=f"DuckDB error: {e}")
    except Exception as e:
        return QueryExecutionResult(dataframe=None, error_message=str(e))


# Helpers used by the schema exploration tools
def list_schemas() -> list[str]:
    """List all available schemas (databases) in the consolidated database.

    Returns:
        Sorted list of schema names.
    """
    try:
        with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
            result = connection.execute("""
                SELECT DISTINCT table_schema
                FROM information_schema.tables
                WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
                ORDER BY table_schema
            """).fetchall()
        return [row[0] for row in result]
    except Exception:
        return []


def list_tables(schema_name: str) -> list[str]:
    """List all tables in a schema.

    Args:
        schema_name: Name of the schema (e.g., "financial").

    Returns:
        List of table names, or an empty list if the schema is not found.
    """
    try:
        with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
            result = connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = ? AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """,
                [schema_name],
            ).fetchall()
        return [row[0] for row in result]
    except Exception:
        return []


def search_catalog(search_term: str) -> list[str]:
    """Search the catalog and group matching columns by schema and table."""
    if not search_term.strip():
        return []

    pattern = f"%{search_term.strip()}%"
    try:
        # Keep discovery deterministic; the agent compares plausible matches by coverage.
        with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
            result = connection.execute(
                """
                SELECT table_schema, table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
                  AND (
                      table_schema ILIKE ?
                      OR table_name ILIKE ?
                      OR column_name ILIKE ?
                  )
                ORDER BY table_schema, table_name, ordinal_position
                LIMIT 100
                """,
                [pattern, pattern, pattern],
            ).fetchall()
        grouped: dict[tuple[str, str], list[str]] = {}
        for schema_name, table_name, column_name, data_type in result:
            grouped.setdefault((schema_name, table_name), []).append(
                f"  - {column_name} ({data_type})"
            )

        return [
            f"{schema_name}.{table_name}\n" + "\n".join(columns)
            for (schema_name, table_name), columns in grouped.items()
        ]
    except Exception:
        return []


def describe_table(schema_name: str, table_name: str) -> list[str]:
    """Describe a table's columns using a compact DuckDB value profile.

    Args:
        schema_name: Name of the schema (e.g., "financial").
        table_name: Name of the table (e.g., "account").

    Returns:
        Column types and useful value statistics, or an empty list if not found.
    """
    try:
        with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
            result = connection.execute(
                "SUMMARIZE SELECT * FROM query_table(?)",
                [f"{schema_name}.{table_name}"],
            ).fetchall()

        columns: list[str] = []
        for row in result:
            columns.append(
                f"{row[0]} ({row[1]}): min={row[2]}, max={row[3]}, "
                f"approx_unique={row[4]}, count={row[10]}, null={row[11]}%"
            )
        return columns
    except Exception:
        return []
