#!/usr/bin/env python3
"""Clean OCR'd public PDF text files into transcript-style TSV sources."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DOCUMENTS_DIR = DATA_DIR / "documents"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
OUTPUT_PREFIX = "document-"
SOURCE_SUFFIX = ".pdf.txt"


@dataclass(frozen=True)
class ConvertedOcrDocument:
    source: Path
    output: Path
    segments: int
    words: int


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert OCR'd public PDF text files into data/transcripts TSV sources.")
    parser.add_argument("--source-dir", type=Path, default=DOCUMENTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=TRANSCRIPTS_DIR)
    parser.add_argument("--prefix", default=OUTPUT_PREFIX, help="Prefix for generated TSV filenames.")
    parser.add_argument("--max-words", type=int, default=450, help="Approximate words per generated evidence segment.")
    parser.add_argument("--min-words", type=int, default=24, help="Minimum cleaned document words required before output.")
    parser.add_argument("--keep-existing", action="store_true", help="Do not delete existing generated OCR TSV files first.")
    parser.add_argument("--normalize-source-names", action="store_true", help="Rename OCR source files to stable lowercase slugs first.")
    args = parser.parse_args()

    if args.normalize_source_names:
        renamed = normalize_source_names(args.source_dir)
        if renamed:
            print(f"Normalized {renamed} OCR source filenames.")

    converted = convert_directory(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        prefix=args.prefix,
        max_words=args.max_words,
        min_words=args.min_words,
        keep_existing=args.keep_existing,
    )
    if not converted:
        print(f"No OCR PDF text files converted from {relative(args.source_dir)}.")
        return 0

    total_segments = sum(item.segments for item in converted)
    total_words = sum(item.words for item in converted)
    print(f"Converted {len(converted)} OCR PDF text files into {total_segments} segments ({total_words} words).")
    for item in converted:
        print(f"- {item.source.name} -> {relative(item.output)} ({item.segments} segments)")
    return 0


def convert_directory(
    source_dir: Path = DOCUMENTS_DIR,
    output_dir: Path = TRANSCRIPTS_DIR,
    prefix: str = OUTPUT_PREFIX,
    max_words: int = 140,
    min_words: int = 24,
    keep_existing: bool = False,
) -> list[ConvertedOcrDocument]:
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not keep_existing:
        for path in sorted(output_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() != ".tsv" or not path.stem.startswith(prefix):
                continue
            path.unlink()

    converted: list[ConvertedOcrDocument] = []
    for path in sorted(source_dir.iterdir()):
        if path.is_dir() or path.name.startswith(".") or not path.name.lower().endswith(SOURCE_SUFFIX):
            continue
        text = clean_ocr_document(path.read_text(encoding="utf-8", errors="replace"))
        words = text.split()
        if len(words) < min_words:
            continue

        rows = chunk_words(words, max_words=max_words)
        output = output_dir / f"{prefix}{source_slug(path)}.tsv"
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["start", "end", "text"], delimiter="\t", lineterminator="\n")
            writer.writeheader()
            for index, row in enumerate(rows):
                writer.writerow({"start": index * 1000, "end": (index + 1) * 1000, "text": row})
        converted.append(ConvertedOcrDocument(source=path, output=output, segments=len(rows), words=len(words)))
    return converted


def normalize_source_names(source_dir: Path) -> int:
    source_dir = source_dir.resolve()
    paths = sorted(path for path in source_dir.iterdir() if path.is_file() and path.name.lower().endswith(SOURCE_SUFFIX))
    targets: dict[Path, Path] = {}
    existing_names = {path.name.lower(): path for path in paths}
    used: set[str] = set()
    for path in paths:
        base = source_slug(path)
        candidate = f"{base}{SOURCE_SUFFIX}"
        counter = 2
        while candidate.lower() in used or (
            candidate.lower() in existing_names and existing_names[candidate.lower()] != path
        ):
            candidate = f"{base}-{counter}{SOURCE_SUFFIX}"
            counter += 1
        used.add(candidate.lower())
        target = source_dir / candidate
        if target != path:
            targets[path] = target

    temp_targets: dict[Path, Path] = {}
    for index, path in enumerate(targets):
        temp = source_dir / f".rename-{index:05d}{SOURCE_SUFFIX}"
        path.rename(temp)
        temp_targets[temp] = targets[path]
    for temp, target in temp_targets.items():
        temp.rename(target)
    return len(targets)


def source_slug(path: Path) -> str:
    source = ocr_metadata_source(path)
    document_name = Path(source).stem if source else path.name.removesuffix(SOURCE_SUFFIX)
    document_slug = slugify(document_name)
    collection_slug = source_collection_slug(source)
    if collection_slug:
        return f"{collection_slug}-{document_slug}"
    return document_slug


def ocr_metadata_source(path: Path) -> str:
    try:
        first_line = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except IndexError:
        return ""
    except OSError:
        return ""
    try:
        metadata = json.loads(first_line)
    except json.JSONDecodeError:
        return ""
    source = metadata.get("source")
    return source if isinstance(source, str) else ""


def source_collection_slug(source: str) -> str:
    if not source:
        return ""
    normalized = source.replace("\\", "/")
    marker = "/Documents/Personal/UAP/"
    if marker in normalized:
        relative_parts = normalized.split(marker, 1)[1].split("/")
    else:
        relative_parts = normalized.split("/")

    parts = [part for part in relative_parts[:-1] if part]
    if not parts:
        return ""

    collection = parts[0]
    if collection.lower() == "department of war":
        release = next((part for part in parts[1:] if re.search(r"\brelease\b", part, flags=re.I)), "")
        match = re.search(r"(\d+)", release)
        if match:
            return f"dow-release-{int(match.group(1))}"
        return "dow"
    return slugify(collection)


def clean_ocr_document(raw: str) -> str:
    pages = extract_pages(raw)
    cleaned_pages: list[list[str]] = []
    line_counts: Counter[str] = Counter()
    for page in pages:
        lines = [clean_line(line) for line in page.splitlines()]
        lines = [line for line in lines if line and not discard_line(line)]
        if likely_contents_page(lines):
            continue
        cleaned_pages.append(lines)
        line_counts.update(canonical_line(line) for line in lines)

    paragraphs: list[str] = []
    for lines in cleaned_pages:
        lines = [line for line in lines if not repeated_boilerplate(line, line_counts)]
        paragraphs.extend(lines_to_paragraphs(lines))
    return "\n\n".join(paragraph for paragraph in paragraphs if keep_paragraph(paragraph))


def extract_pages(raw: str) -> list[str]:
    raw = raw.replace("\ufeff", "").replace("\r", "\n")
    matches = list(re.finditer(r"^===== PAGE \d+ =====\s*$", raw, flags=re.MULTILINE))
    if not matches:
        return [strip_leading_json(raw)]

    pages: list[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        pages.append(strip_leading_json(raw[start:end]))
    return pages


def strip_leading_json(text: str) -> str:
    lines = text.splitlines()
    while lines and (not lines[0].strip() or looks_like_json_metadata(lines[0])):
        lines.pop(0)
    return "\n".join(lines)


def clean_line(line: str) -> str:
    line = unicodedata.normalize("NFKC", line)
    replacements = {
        "\u019f": "O",
        "\u01a0": "O",
        "\u01a1": "o",
        "\u01af": "U",
        "\u01b0": "u",
        "\u021a": "T",
        "\u021b": "t",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "-",
        "\u2212": "-",
    }
    for old, new in replacements.items():
        line = line.replace(old, new)
    line = re.sub(r"\b(?:\([b-d]\)\s*)+\(\d+\)", " ", line, flags=re.I)
    line = re.sub(r"\b\d\.\d\([a-z]\)", " ", line, flags=re.I)
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def discard_line(line: str) -> bool:
    lowered = line.lower().strip()
    if looks_like_json_metadata(line):
        return True
    if re.fullmatch(r"\d{1,4}", line):
        return True
    if re.fullmatch(r"[-_=~|./\\ ]{3,}", line):
        return True
    if re.fullmatch(r"(?:unclassified|classified|secret|top secret|cui|for official use only|official record copy)", lowered):
        return True
    if re.fullmatch(r"(?:page\s*)?\d{1,4}\s*(?:of|/)\s*\d{1,4}", lowered):
        return True
    if "place form 490 here" in lowered:
        return True
    if lowered.startswith("form 9969"):
        return True
    if lowered == "warning":
        return True
    if "official historical record" in lowered:
        return True
    if "federal records act" in lowered:
        return True
    if "chief, cia archives" in lowered:
        return True
    if lowered.startswith("return immediately after use"):
        return True
    if lowered in {"cia archives and records center", "archives and records center"}:
        return True
    if "return immediately after use to the cia archives" in lowered:
        return True
    if "approved for release" in lowered and ("national defense" in lowered or len(line) < 160):
        return True
    if lowered.startswith("approved for release ") and len(line) < 120:
        return True
    if lowered.startswith("classification:") and len(line) < 80:
        return True
    if len(line) < 3:
        return True

    letters = len(re.findall(r"[A-Za-z]", line))
    visible = len(re.sub(r"\s+", "", line))
    if visible >= 12 and letters / visible < 0.22:
        return True
    return False


def likely_contents_page(lines: list[str]) -> bool:
    if not lines:
        return False
    sample = " ".join(lines[:80])
    lowered = sample.lower()
    contents_like = (
        "table of contents" in lowered
        or lowered.startswith("contents ")
        or "list of illustrations" in lowered
        or "list of tables" in lowered
    )
    if not contents_like:
        return False
    figure_count = len(re.findall(r"\bfigure\s+\d+", sample, flags=re.I))
    table_count = len(re.findall(r"\btable\s+[ivxlcdm\d]+", sample, flags=re.I))
    page_number_count = len(re.findall(r"\b\d{1,3}\b", sample))
    dot_leader_count = sample.count(" .") + sample.count(". ")
    return figure_count >= 5 or table_count >= 5 or page_number_count >= 18 or dot_leader_count >= 20


def repeated_boilerplate(line: str, line_counts: Counter[str]) -> bool:
    canonical = canonical_line(line)
    count = line_counts[canonical]
    if count < 3:
        return False
    lowered = canonical.lower()
    if len(canonical) <= 80:
        return True
    boilerplate_terms = (
        "office of the under secretary",
        "washington dc",
        "national defense authorization",
        "cia archives and records center",
        "department of defense",
        "defense intelligence agency",
    )
    return any(term in lowered for term in boilerplate_terms)


def lines_to_paragraphs(lines: list[str]) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if not current:
            current.append(line)
            continue
        previous = current[-1]
        if previous.endswith("-") and re.match(r"^[a-z]", line):
            current[-1] = previous[:-1] + line
            continue
        if starts_new_paragraph(line, previous):
            paragraphs.append(clean_paragraph(" ".join(current)))
            current = [line]
        else:
            current.append(line)
    if current:
        paragraphs.append(clean_paragraph(" ".join(current)))
    return paragraphs


def starts_new_paragraph(line: str, previous: str) -> bool:
    if re.match(r"^(?:\d+|[a-z]|[ivxlcdm]+)\.\s+", line, flags=re.I):
        return True
    if re.match(r"^[A-Z][A-Z0-9 ,;:'\"()/.-]{8,}$", line) and len(line) < 100:
        return True
    if previous.endswith((".", "?", "!", ":")) and re.match(r"^[A-Z0-9]", line):
        return True
    return False


def clean_paragraph(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"([a-z])-\s+([a-z])", r"\1\2", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text


def keep_paragraph(text: str) -> bool:
    if len(text) < 24:
        return False
    if not re.search(r"[A-Za-z]", text):
        return False
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text)
    if len(words) < 4:
        return False
    return True


def chunk_words(words: list[str], max_words: int) -> list[str]:
    rows: list[str] = []
    for index in range(0, len(words), max_words):
        row = " ".join(words[index : index + max_words]).strip()
        if row:
            rows.append(row)
    return rows


def looks_like_json_metadata(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("{") and stripped.endswith("}") and any(key in stripped for key in ('"page"', '"chars"', '"created_utc"'))


def canonical_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def slugify(value: str) -> str:
    value = value.removesuffix(SOURCE_SUFFIX)
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower().replace("&", " and ")
    value = re.sub(r"['’]", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "document"


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
