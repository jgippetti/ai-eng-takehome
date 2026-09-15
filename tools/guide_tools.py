"""Tools for finding and reading business guidance."""

import re
from pathlib import Path

from framework.agent import Tool

GUIDES_DIRECTORY = Path(__file__).parent.parent / "evaluation" / "data" / "guides"
_HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_WORD_PATTERN = re.compile(r"[a-z0-9]+")
_MAX_MATCHES = 10
_MAX_EXCERPTS = 2


def _words(value: str) -> set[str]:
    """Return normalized words for lightweight guide matching."""
    words = set()
    for word in _WORD_PATTERN.findall(value.casefold()):
        if len(word) > 4 and word.endswith("ies"):
            word = f"{word[:-3]}y"
        elif len(word) > 4 and word.endswith("s"):
            word = word[:-1]
        words.add(word)
    return words


def _normalized_text(value: str) -> str:
    """Normalize text for phrase matching."""
    return " ".join(_WORD_PATTERN.findall(value.casefold()))


def _matching_excerpts(content: str, query_words: set[str], query_text: str) -> list[str]:
    """Return the most relevant non-heading lines from a guide."""
    candidates: list[tuple[bool, int, int, str]] = []
    for index, line in enumerate(content.splitlines()):
        stripped = line.strip()
        if not stripped or _HEADING_PATTERN.fullmatch(stripped):
            continue

        normalized_line = _normalized_text(stripped)
        overlap = len(query_words & _words(stripped))
        if not overlap:
            continue

        excerpt = re.sub(r"^[-*]\s+", "", stripped)
        candidates.append((query_text in normalized_line, overlap, index, excerpt))

    candidates.sort(
        key=lambda candidate: (not candidate[0], -candidate[1], candidate[2])
    )
    return [excerpt for _, _, _, excerpt in candidates[:_MAX_EXCERPTS]]


def search_guides(search_term: str) -> str:
    """Search guide names, headings, and body text."""
    query_words = _words(search_term)
    if not query_words:
        return "Provide a distinctive term to search the guides."

    query_text = _normalized_text(search_term)
    matches: list[tuple[tuple[bool, bool, int, int, str], str]] = []
    for path in GUIDES_DIRECTORY.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        headings = _HEADING_PATTERN.findall(content)
        title = headings[0] if headings else path.stem.replace("_", " ")
        metadata = f"{path.stem} {' '.join(headings)}"
        body = "\n".join(
            line for line in content.splitlines() if not _HEADING_PATTERN.fullmatch(line)
        )
        normalized_metadata = _normalized_text(metadata)
        normalized_body = _normalized_text(body)

        metadata_overlap = len(query_words & _words(metadata))
        body_overlap = len(query_words & _words(body))
        if not metadata_overlap and not body_overlap:
            continue

        lines = [f"- guide_name: {path.stem}", f"  title: {title}"]
        if headings[1:]:
            lines.append(f"  sections: {'; '.join(headings[1:])}")
        for excerpt in _matching_excerpts(content, query_words, query_text):
            lines.append(f"  matching_excerpt: {excerpt}")

        rank = (
            query_text not in normalized_metadata,
            query_text not in normalized_body,
            -metadata_overlap,
            -(metadata_overlap + body_overlap),
            path.stem,
        )
        matches.append((rank, "\n".join(lines)))

    if not matches:
        return f"No guides match '{search_term}'."

    matches.sort(key=lambda match: match[0])
    rendered_matches = [result for _, result in matches[:_MAX_MATCHES]]
    lines = [f"Guide matches for '{search_term}' ({len(rendered_matches)}):"]
    lines.extend(rendered_matches)
    lines.extend(
        [
            "",
            "These excerpts are discovery evidence only, not the complete guidance. If any "
            "result is plausible, call read_guide next before using its rules.",
        ]
    )
    return "\n".join(lines)


def read_guide(guide_name: str) -> str:
    """Read a guide by the name returned from search_guides."""
    normalized_name = guide_name.strip()
    field_match = re.search(
        r"(?:^|\s)guide_name:\s*([A-Za-z0-9_-]+)", normalized_name
    )
    if field_match:
        normalized_name = field_match.group(1)
    elif ":" in normalized_name:
        normalized_name = normalized_name.split(":", 1)[0].strip()
    if normalized_name.endswith(".md"):
        normalized_name = normalized_name[:-3]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", normalized_name):
        return f"Invalid guide name '{guide_name}'."

    path = GUIDES_DIRECTORY / f"{normalized_name}.md"
    if not path.is_file():
        return f"Guide '{guide_name}' was not found. Use search_guides to find its name."

    content = path.read_text(encoding="utf-8")
    return f"Guide: {normalized_name}\n\n{content}"


SEARCH_GUIDES = Tool(
    name="search_guides",
    description=(
        "Search business guide names, headings, and body text. Results include a guide_name "
        "and short discovery excerpts, not complete guidance. Search with one or two "
        "distinctive domain or metric terms. If any result is plausible, call read_guide next "
        "before using its rules."
    ),
    parameters={
        "type": "object",
        "properties": {
            "search_term": {
                "type": "string",
                "description": "One or two distinctive terms, such as a domain or metric.",
            },
        },
        "required": ["search_term"],
    },
    function=search_guides,
)

READ_GUIDE = Tool(
    name="read_guide",
    description=(
        "Read the complete contents of one business guide. Use the exact guide name returned "
        "by search_guides and apply relevant rules when constructing the SQL."
    ),
    parameters={
        "type": "object",
        "properties": {
            "guide_name": {
                "type": "string",
                "description": "The value of guide_name returned by search_guides.",
            },
        },
        "required": ["guide_name"],
    },
    function=read_guide,
)
