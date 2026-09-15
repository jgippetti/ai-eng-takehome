"""Tools for exploring database schemas, tables, and columns."""

from framework.agent import Tool
from framework.database import describe_table as get_table_columns
from framework.database import list_schemas as get_schemas
from framework.database import list_tables as get_tables
from framework.database import search_catalog as find_catalog_matches


def list_schemas() -> str:
    """Return all user-facing database schemas."""
    schemas = get_schemas()
    if not schemas:
        return "No schemas found."
    return (
        f"Schemas ({len(schemas)}):\n"
        "Each schema represents an original source database. A database named in a guide "
        "generally corresponds to the same-named schema.\n"
        + "\n".join(schemas)
    )


def list_tables(schema_name: str) -> str:
    """Return all tables in a database schema."""
    tables = get_tables(schema_name)
    if not tables:
        return f"No tables found in schema '{schema_name}'."
    return f"Tables in {schema_name} ({len(tables)}):\n" + "\n".join(tables)


def search_catalog(search_term: str) -> str:
    """Return catalog matches grouped into candidate tables."""
    matches = find_catalog_matches(search_term)
    if not matches:
        return f"No catalog matches found for '{search_term}'."
    return (
        f"Catalog matches for '{search_term}' ({len(matches)} table(s)):\n"
        "Order is alphabetical, not relevance. Compare candidate tables by whether their "
        "columns cover every task and guide requirement. Use describe_table to compare each "
        "genuinely plausible candidate before choosing.\n"
        + "\n".join(f"- {match}" for match in matches)
    )


def describe_table(schema_name: str, table_name: str) -> str:
    """Return a compact value profile for every column in a database table."""
    columns = get_table_columns(schema_name, table_name)
    qualified_name = f"{schema_name}.{table_name}"
    if not columns:
        return f"No columns found for table '{qualified_name}'."
    return f"Columns in {qualified_name} ({len(columns)}):\n" + "\n".join(columns)


LIST_SCHEMAS = Tool(
    name="list_schemas",
    description=(
        "List all schemas in the consolidated DuckDB. Each schema represents an original "
        "source database, so a database named in a relevant guide generally corresponds to "
        "the same-named schema. Use this first when the relevant schema is unknown."
    ),
    parameters={"type": "object", "properties": {}},
    function=list_schemas,
)

LIST_TABLES = Tool(
    name="list_tables",
    description="List all tables in one schema after identifying the relevant schema.",
    parameters={
        "type": "object",
        "properties": {
            "schema_name": {
                "type": "string",
                "description": "The exact schema name returned by list_schemas.",
            },
        },
        "required": ["schema_name"],
    },
    function=list_tables,
)


SEARCH_CATALOG = Tool(
    name="search_catalog",
    description=(
        "Search across schema, table, and column names. Use this when the task provides "
        "a database identifier, when the relevant table is unclear, or when a label and "
        "related ID may come from a lookup table. Search separately for each distinctive "
        "identifier-like task term before choosing tables. Results are grouped by candidate "
        "table and are not relevance-ranked; compare column coverage instead of choosing "
        "the first result. Exact column matches are stronger evidence than generic "
        "table-name matches."
    ),
    parameters={
        "type": "object",
        "properties": {
            "search_term": {
                "type": "string",
                "description": "A schema, table, or column name or partial name.",
            },
        },
        "required": ["search_term"],
    },
    function=search_catalog,
)


DESCRIBE_TABLE = Tool(
    name="describe_table",
    description=(
        "Profile every column in one table with its type, value range, approximate unique "
        "count, row count, and null percentage. When choosing among genuinely plausible "
        "candidate tables, profile each candidate before deciding; do not profile obviously "
        "irrelevant catalog matches. Also use this for every table in the final query."
    ),
    parameters={
        "type": "object",
        "properties": {
            "schema_name": {
                "type": "string",
                "description": "The exact schema name returned by list_schemas.",
            },
            "table_name": {
                "type": "string",
                "description": "The exact table name returned by list_tables.",
            },
        },
        "required": ["schema_name", "table_name"],
    },
    function=describe_table,
)
