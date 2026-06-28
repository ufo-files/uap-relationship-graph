#!/usr/bin/env python3
"""Validate repository data and contribution boundaries."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_graph  # noqa: E402


GENERATED_FILES = {
    "index.html",
    "app-data.js",
    "app-data-mentions.js",
    "app-data-relationships.js",
    "data/entities.json",
    "data/graph.json",
    "data/manifest.json",
    "data/mentions.json",
    "data/reclass-template.json",
    "data/relationships.json",
    "data/segments.json",
}

RECLASS_OBJECT_KEYS = {
    "reclassifications",
    "nameReclassifications",
    "falsePositives",
    "removedFalsePositives",
    "omissions",
    "aliases",
    "merges",
    "nameMerges",
    "removedMerges",
    "removedNameMerges",
    "removedManualRelationships",
    "manualRelationships",
    "notes",
}

RECLASS_STRING_KEYS = {"generatedAt", "note"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--changed-files", type=Path, help="Newline-separated changed file list to validate PR boundaries.")
    args = parser.parse_args()

    errors: list[str] = []
    errors.extend(validate_required_files())
    errors.extend(validate_reclass())
    errors.extend(validate_transcript_directory())
    errors.extend(validate_static_app())
    if args.changed_files:
        errors.extend(validate_changed_files(args.changed_files))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Repository validation passed.")
    return 0


def validate_required_files() -> list[str]:
    required = [
        "build_graph.py",
        "index.html",
        "app-data.js",
        "data/reclass.json",
        "data/transcripts/entity-registry.json",
    ]
    return [f"Missing required file: {path}" for path in required if not (ROOT / path).exists()]


def validate_reclass() -> list[str]:
    path = ROOT / "data/reclass.json"
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"data/reclass.json is invalid JSON: {exc}"]

    if not isinstance(payload, dict):
        return ["data/reclass.json must be a JSON object."]

    allowed_keys = RECLASS_OBJECT_KEYS | RECLASS_STRING_KEYS
    for key, value in payload.items():
        if key not in allowed_keys:
            errors.append(f"data/reclass.json has unknown top-level key: {key}")
            continue
        if key in RECLASS_OBJECT_KEYS and not isinstance(value, dict):
            errors.append(f"data/reclass.json key {key} must be an object.")
        if key in RECLASS_STRING_KEYS and value is not None and not isinstance(value, str):
            errors.append(f"data/reclass.json key {key} must be a string when present.")

    for key in RECLASS_OBJECT_KEYS:
        payload.setdefault(key, {})

    categories = set(build_graph.CATEGORY_LABELS)
    for entity_id, category in payload["reclassifications"].items():
        if not isinstance(entity_id, str) or ":" not in entity_id:
            errors.append(f"reclassifications key must be an entity id with a category prefix: {entity_id}")
        if category not in categories:
            errors.append(f"reclassifications for {entity_id} uses unknown category: {category}")

    for name, category in payload["nameReclassifications"].items():
        if not isinstance(name, str) or not name.strip():
            errors.append("nameReclassifications keys must be non-empty strings.")
        if category not in categories:
            errors.append(f"nameReclassifications for {name} uses unknown category: {category}")

    for key in ("falsePositives", "removedFalsePositives", "omissions", "aliases", "merges", "nameMerges", "removedMerges", "removedNameMerges", "removedManualRelationships", "manualRelationships", "notes"):
        if not isinstance(payload[key], dict):
            continue
        for item_key, value in payload[key].items():
            if not isinstance(item_key, str) or not item_key.strip():
                errors.append(f"{key} keys must be non-empty strings.")
            if key in {"falsePositives", "removedFalsePositives", "merges", "nameMerges", "removedMerges", "removedNameMerges", "removedManualRelationships", "manualRelationships"} and isinstance(value, dict):
                for category_key in ("category", "categoryLabel", "sourceCategory", "targetCategory"):
                    category = value.get(category_key)
                    if category_key.endswith("Label") or not category:
                        continue
                    if category not in categories:
                        errors.append(f"{key}.{item_key}.{category_key} uses unknown category: {category}")
    return errors


def validate_transcript_directory() -> list[str]:
    transcripts = ROOT / "data/transcripts"
    if not transcripts.exists():
        return ["Missing data/transcripts directory."]

    errors: list[str] = []
    allowed = set(build_graph.SOURCE_EXTENSIONS)
    ignored = set(build_graph.NON_TRANSCRIPT_FILES)
    for path in sorted(transcripts.iterdir()):
        if path.name.startswith(".") or path.name in ignored:
            continue
        if path.is_dir():
            errors.append(f"Transcript directory contains nested directory: {path.relative_to(ROOT)}")
            continue
        if path.suffix.lower() not in allowed:
            errors.append(
                f"Unsupported transcript file: {path.relative_to(ROOT)}. "
                f"Use one of: {', '.join(build_graph.SOURCE_EXTENSIONS)}"
            )

    sources = build_graph.select_transcript_sources()
    if not sources:
        errors.append("No transcript sources were selected from data/transcripts.")

    for source in sources:
        try:
            rows = build_graph.parse_source(source)
        except Exception as exc:  # noqa: BLE001 - validator should report file context.
            errors.append(f"Could not parse transcript source {source.relative_to(ROOT)}: {exc}")
            continue
        if not any(build_graph.clean_text(row.get("text", "")) for row in rows):
            errors.append(f"Transcript source has no text rows: {source.relative_to(ROOT)}")
    return errors


def validate_static_app() -> list[str]:
    errors: list[str] = []
    index = ROOT / "index.html"
    app_data = ROOT / "app-data.js"
    if index.exists() and "app-data.js" not in index.read_text(encoding="utf-8", errors="replace"):
        errors.append("index.html does not reference app-data.js.")
    if app_data.exists():
        text = app_data.read_text(encoding="utf-8", errors="replace")
        prefix = "window.TRANSCRIPT_INTELLIGENCE_DATA = "
        if not text.startswith(prefix) or not text.rstrip().endswith(";"):
            errors.append("app-data.js must assign window.TRANSCRIPT_INTELLIGENCE_DATA.")
            return errors
        try:
            payload = json.loads(text[len(prefix) :].rstrip().removesuffix(";"))
        except json.JSONDecodeError as exc:
            errors.append(f"app-data.js embedded payload is invalid JSON: {exc}")
            return errors
        for key in ("manifest", "entities", "mentions", "relationships", "segments", "graph", "reclassDecisions"):
            if key not in payload:
                errors.append(f"app-data.js embedded payload is missing {key}.")
    return errors


def validate_changed_files(path: Path) -> list[str]:
    if not path.exists():
        return [f"Changed-files list does not exist: {path}"]
    changed = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    errors: list[str] = []
    generated_changes = sorted(item for item in changed if item in GENERATED_FILES)
    source_changes_allow_generated = any(
        item == "build_graph.py"
        or item == ".github/workflows/rebuild-report.yml"
        or item.startswith("scripts/")
        or item.startswith("tests/")
        for item in changed
    )
    generated_rebuild_pr = os.environ.get("ALLOW_GENERATED_CHANGES") == "1"
    if generated_changes and not source_changes_allow_generated and not generated_rebuild_pr:
        errors.append(
            "Generated app files should not be edited in contributor PRs. "
            "Change data/reclass.json, data/transcripts/**, or build_graph.py; "
            f"the rebuild workflow will regenerate these files after merge: {', '.join(generated_changes)}"
        )
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
