#!/usr/bin/env python3
"""Static accessibility checks for the generated graph app."""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ElementCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str]]] = []
        self.labels_for: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        self.elements.append((tag, attr_map))
        if tag == "label" and attr_map.get("for"):
            self.labels_for.add(attr_map["for"])


def main() -> int:
    errors: list[str] = []
    index = (ROOT / "index.html").read_text(encoding="utf-8", errors="replace")
    source = (ROOT / "build_graph.py").read_text(encoding="utf-8", errors="replace")
    parser = ElementCollector()
    parser.feed(index)
    styles = collect_document_styles(index, parser)

    errors.extend(check_document(index, styles, parser))
    errors.extend(check_template_source(source))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Accessibility audit passed.")
    return 0


def collect_document_styles(index: str, parser: ElementCollector) -> str:
    styles = [index]
    for tag, attrs in parser.elements:
        if tag != "link" or "stylesheet" not in attrs.get("rel", "").lower().split():
            continue
        href = attrs.get("href", "").split("?", 1)[0]
        if not href or re.match(r"^[a-z]+:", href, flags=re.IGNORECASE):
            continue
        stylesheet = (ROOT / href.lstrip("./")).resolve()
        try:
            stylesheet.relative_to(ROOT)
        except ValueError:
            continue
        if stylesheet.exists():
            styles.append(stylesheet.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(styles)


def check_document(index: str, styles: str, parser: ElementCollector) -> list[str]:
    errors: list[str] = []
    elements = parser.elements
    by_id = {attrs["id"]: (tag, attrs) for tag, attrs in elements if attrs.get("id")}

    if not re.search(r"<html[^>]+lang=\"en\"", index):
        errors.append("Document must declare html lang=\"en\".")
    if "<title>UFO Files Relationship Graph</title>" not in index:
        errors.append("Document title is missing or unexpected.")
    if "input:focus-visible" not in styles or ".html-graph-label:focus-visible" not in styles:
        errors.append("Visible focus styles are missing for form controls or graph labels.")

    search = by_id.get("search")
    if not search:
        errors.append("Search input is missing.")
    elif "search" not in parser.labels_for:
        errors.append("Search input needs an explicit label.")

    expected = {
        "graph": {"role": "img", "aria-describedby": "graph-help status"},
        "status": {"role": "status", "aria-live": "polite"},
        "review-status": {"role": "status", "aria-live": "polite"},
        "node-card": {"tabindex": "-1", "aria-live": "polite"},
        "hover-card": {"aria-hidden": "true"},
        "corner-label": {"role": "status", "aria-live": "polite"},
    }
    for element_id, required_attrs in expected.items():
        element = by_id.get(element_id)
        if not element:
            errors.append(f"Missing #{element_id}.")
            continue
        _, attrs = element
        for name, value in required_attrs.items():
            if attrs.get(name) != value:
                errors.append(f"#{element_id} must have {name}=\"{value}\".")

    for _, attrs in (item for item in elements if item[0] == "button"):
        if attrs.get("aria-label"):
            continue
        # Static buttons in this app all contain visible text immediately in the source.
        button_id = attrs.get("id", "unknown")
        pattern = r"<button[^>]*id=\"" + re.escape(button_id) + r"\"[^>]*>\s*[^<\s]"
        if button_id != "unknown" and not re.search(pattern, index):
            errors.append(f"Button #{button_id} needs visible text or an aria-label.")

    return errors


def check_template_source(source: str) -> list[str]:
    errors: list[str] = []
    required_snippets = [
        'role="button" tabindex="0"',
        'aria-label="',
        'graphLabelsEl.addEventListener("keydown"',
        'graphLabelsEl.addEventListener("focusin"',
        'focusDetailsCard()',
        'focusSelectedGraphLabel()',
        'function stepBackGraph()',
        'document.getElementById("search-form").addEventListener("submit"',
        'document.addEventListener("keydown"',
    ]
    for snippet in required_snippets:
        if snippet not in source:
            errors.append(f"Generated graph template is missing accessibility hook: {snippet}")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
