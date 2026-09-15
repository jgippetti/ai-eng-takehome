from unittest.mock import patch

from tools.schema_tools import (
    describe_table,
    list_schemas,
    list_tables,
    search_catalog,
)


def test_list_schemas_formats_all_results() -> None:
    with patch("tools.schema_tools.get_schemas", return_value=["Airline", "financial"]):
        result = list_schemas()

    assert result == (
        "Schemas (2):\n"
        "Each schema represents an original source database. A database named in a guide "
        "generally corresponds to the same-named schema.\n"
        "Airline\nfinancial"
    )


def test_list_tables_formats_all_results() -> None:
    with patch("tools.schema_tools.get_tables", return_value=["account", "loan"]):
        result = list_tables("financial")

    assert result == "Tables in financial (2):\naccount\nloan"


def test_search_catalog_formats_all_matches() -> None:
    matches = [
        "Credit.charge\n"
        "  - charge_code (VARCHAR)\n"
        "  - charge_amt (DOUBLE)",
        "Credit.member\n  - member_no (BIGINT)",
    ]
    with patch("tools.schema_tools.find_catalog_matches", return_value=matches):
        result = search_catalog("charge")

    assert result == (
        "Catalog matches for 'charge' (2 table(s)):\n"
        "Order is alphabetical, not relevance. Compare candidate tables by whether their "
        "columns cover every task and guide requirement. Use describe_table to compare each "
        "genuinely plausible candidate before choosing.\n"
        "- Credit.charge\n"
        "  - charge_code (VARCHAR)\n"
        "  - charge_amt (DOUBLE)\n"
        "- Credit.member\n"
        "  - member_no (BIGINT)"
    )


def test_describe_table_formats_all_columns() -> None:
    columns = [
        "loan_id (BIGINT): min=1, max=4959, approx_unique=682, "
        "count=682, null=0.00%",
        "amount (BIGINT): min=4980, max=590820, approx_unique=663, "
        "count=682, null=0.00%",
    ]
    with patch("tools.schema_tools.get_table_columns", return_value=columns):
        result = describe_table("financial", "loan")

    assert result == "Columns in financial.loan (2):\n" + "\n".join(columns)


def test_schema_tools_explain_empty_results() -> None:
    with (
        patch("tools.schema_tools.get_schemas", return_value=[]),
        patch("tools.schema_tools.find_catalog_matches", return_value=[]),
        patch("tools.schema_tools.get_tables", return_value=[]),
        patch("tools.schema_tools.get_table_columns", return_value=[]),
    ):
        assert list_schemas() == "No schemas found."
        assert search_catalog("missing") == "No catalog matches found for 'missing'."
        assert list_tables("missing") == "No tables found in schema 'missing'."
        assert describe_table("missing", "table") == (
            "No columns found for table 'missing.table'."
        )
