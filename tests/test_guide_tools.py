from pathlib import Path
from unittest.mock import patch

from tools.guide_tools import read_guide, search_guides


def _write_guide(directory: Path, name: str, contents: str) -> None:
    (directory / f"{name}.md").write_text(contents, encoding="utf-8")


def test_search_guides_searches_names_and_headings(tmp_path: Path) -> None:
    _write_guide(
        tmp_path,
        "credit_card_operations",
        "# Credit Card Operations\n\n## Charge Classification\n\nRefund rules.",
    )
    _write_guide(
        tmp_path,
        "chess_idiosyncrasies",
        "# Chess Standards\n\n## Opening Analysis\n\nCanonical labels.",
    )

    with patch("tools.guide_tools.GUIDES_DIRECTORY", tmp_path):
        result = search_guides("charges")

    assert "guide_name: credit_card_operations" in result
    assert "sections: Charge Classification" in result
    assert "chess_idiosyncrasies" not in result


def test_search_guides_returns_matching_body_excerpt(tmp_path: Path) -> None:
    _write_guide(
        tmp_path,
        "credit_card_operations",
        "# Credit Card Operations\n\n## Charge Classification\n\nRefund rules.",
    )

    with patch("tools.guide_tools.GUIDES_DIRECTORY", tmp_path):
        result = search_guides("refund")

    assert "guide_name: credit_card_operations" in result
    assert "matching_excerpt: Refund rules." in result
    assert result.endswith(
        "These excerpts are discovery evidence only, not the complete guidance. If any "
        "result is plausible, call read_guide next before using its rules."
    )


def test_search_and_read_guide_keep_discovery_and_content_separate(
    tmp_path: Path,
) -> None:
    contents = (
        "# Financial Database Rules\n\n"
        "Use the `financial` database.\n\n"
        "## Loans\n\nPerforming loan rules."
    )
    _write_guide(tmp_path, "financial_operations", contents)

    with patch("tools.guide_tools.GUIDES_DIRECTORY", tmp_path):
        search_result = search_guides("performing loan")
        read_result = read_guide("financial_operations")

    assert "matching_excerpt: Performing loan rules." in search_result
    assert read_result == f"Guide: financial_operations\n\n{contents}"


def test_search_guides_matches_y_ies_word_forms(tmp_path: Path) -> None:
    _write_guide(
        tmp_path,
        "craft_beer_inventory",
        "# Craft Beer Inventory\n\nBreweries with fewer than 3 beers are microbreweries.",
    )

    with patch("tools.guide_tools.GUIDES_DIRECTORY", tmp_path):
        result = search_guides("microbrewery")

    assert "guide_name: craft_beer_inventory" in result
    assert "matching_excerpt: Breweries with fewer than 3 beers are microbreweries." in result


def test_search_guides_prioritizes_exact_body_phrase(tmp_path: Path) -> None:
    _write_guide(
        tmp_path,
        "financial_operations",
        "# Financial Rules\n\n## Transaction Handling\n\nCategorize transactions.",
    )
    _write_guide(
        tmp_path,
        "credit_card_operations",
        "# Credit Card Operations\n\n## Charges\n\nCalculate average transaction value.",
    )

    with patch("tools.guide_tools.GUIDES_DIRECTORY", tmp_path):
        result = search_guides("transaction value")

    assert result.index("credit_card_operations") < result.index("financial_operations")


def test_read_guide_returns_complete_content(tmp_path: Path) -> None:
    contents = "# Chess Standards\n\n## Opening Analysis\n\nUse the lookup table."
    _write_guide(tmp_path, "chess_idiosyncrasies", contents)

    with patch("tools.guide_tools.GUIDES_DIRECTORY", tmp_path):
        result = read_guide("chess_idiosyncrasies")

    assert result == f"Guide: chess_idiosyncrasies\n\n{contents}"


def test_read_guide_accepts_formatted_search_result(tmp_path: Path) -> None:
    contents = "# Chess Standards\n\nUse the lookup table."
    _write_guide(tmp_path, "chess_idiosyncrasies", contents)

    with patch("tools.guide_tools.GUIDES_DIRECTORY", tmp_path):
        result = read_guide(
            "- guide_name: chess_idiosyncrasies\n  title: Chess Standards"
        )

    assert result == f"Guide: chess_idiosyncrasies\n\n{contents}"


def test_read_guide_rejects_paths(tmp_path: Path) -> None:
    with patch("tools.guide_tools.GUIDES_DIRECTORY", tmp_path):
        result = read_guide("../private")

    assert result == "Invalid guide name '../private'."
