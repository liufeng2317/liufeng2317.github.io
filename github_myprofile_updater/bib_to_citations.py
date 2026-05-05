#!/usr/bin/env python3

"""Convert BibTeX entries into markdown citation bullets used by this site."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


MONTH_ORDER = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def clean_value(value: str) -> str:
    value = value.strip().rstrip(",").strip()
    if value.startswith("{") and value.endswith("}"):
        value = value[1:-1]
    elif value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    value = value.replace("\n", " ")
    value = re.sub(r"\s+", " ", value)
    value = value.replace("{{", "").replace("}}", "")
    value = value.replace("{", "").replace("}", "")
    return value.strip()


def split_top_level(text: str, delimiter: str = ",") -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_quote = False
    escape = False
    for ch in text:
        if escape:
            buf.append(ch)
            escape = False
            continue
        if ch == "\\":
            buf.append(ch)
            escape = True
            continue
        if ch == '"':
            in_quote = not in_quote
            buf.append(ch)
            continue
        if not in_quote:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == delimiter and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
                continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def parse_entry(block: str) -> dict[str, str]:
    header_match = re.match(r"@(\w+)\s*\{\s*([^,]+)\s*,", block, re.DOTALL)
    if not header_match:
        raise ValueError(f"Invalid BibTeX entry: {block[:40]!r}")
    entry_type = header_match.group(1).lower()
    entry_key = header_match.group(2).strip()
    body = block[header_match.end():].rstrip().rstrip("}").strip()
    fields: dict[str, str] = {"entry_type": entry_type, "key": entry_key}
    for part in split_top_level(body):
        if "=" not in part:
            continue
        name, raw_value = part.split("=", 1)
        fields[name.strip().lower()] = clean_value(raw_value)
    return fields


def parse_bibtex(content: str) -> list[dict[str, str]]:
    blocks: list[str] = []
    i = 0
    while True:
        start = content.find("@", i)
        if start == -1:
            break
        brace = content.find("{", start)
        if brace == -1:
            break
        depth = 0
        j = brace
        while j < len(content):
            if content[j] == "{":
                depth += 1
            elif content[j] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(content[start:j + 1])
                    i = j + 1
                    break
            j += 1
        else:
            break
    return [parse_entry(block) for block in blocks]


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def abbreviate_given_names(given: str) -> str:
    tokens = re.split(r"[\s-]+", given.strip())
    initials = [token[0].upper() + "." for token in tokens if token]
    return "-".join(initials) if "-" in given else " ".join(initials)


def format_author(name: str, highlight: str | None) -> str:
    name = name.strip()
    if "," in name:
        family, given = [part.strip() for part in name.split(",", 1)]
    else:
        parts = name.split()
        family = parts[-1]
        given = " ".join(parts[:-1])
    formatted = f"{family}, {abbreviate_given_names(given)}".strip().rstrip(",")
    if highlight and normalize_name(name) == normalize_name(highlight):
        return f"**{formatted}**"
    return formatted


def format_authors(raw: str, highlight: str | None) -> str:
    authors = [format_author(name, highlight) for name in raw.split(" and ") if name.strip()]
    if not authors:
        return ""
    if len(authors) > 8:
        return ", ".join(authors[:5]) + ", et al."
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return f"{authors[0]}, & {authors[1]}"
    return ", ".join(authors[:-1]) + f", & {authors[-1]}"


def infer_status(entry: dict[str, str]) -> tuple[str, str]:
    journal = entry.get("journal")
    booktitle = entry.get("booktitle")
    publisher = entry.get("publisher", "").lower()
    archiveprefix = entry.get("archiveprefix", "").lower()
    eprint = entry.get("eprint")

    if journal:
        return "Published in", journal
    if booktitle:
        venue = re.sub(r"^Forty-Third\s+", "", booktitle)
        venue = venue.replace("International Conference on Machine Learning (ICML)", "ICML")
        return "Published in", venue
    if archiveprefix == "arxiv" or publisher == "arxiv" or eprint:
        return "Online on", "arXiv"
    if publisher:
        return "Published in", entry["publisher"]
    return "Preprint", "Unknown Venue"


def entry_link(entry: dict[str, str]) -> str | None:
    doi = entry.get("doi", "").strip()
    eprint = entry.get("eprint", "").strip()
    url = entry.get("url", "").strip()
    if doi.lower().startswith("10."):
        return f"https://doi.org/{doi}"
    if eprint:
        return f"https://arxiv.org/abs/{eprint}"
    if url:
        return url
    return None


def sort_key(entry: dict[str, str]) -> tuple[int, int, str]:
    year = int(entry.get("year", "0") or 0)
    month = MONTH_ORDER.get(entry.get("month", "").lower()[:3], 0)
    title = entry.get("title", "")
    return (-year, -month, title.lower())


def format_entry(entry: dict[str, str], highlight: str | None) -> str:
    status, venue = infer_status(entry)
    authors = format_authors(entry.get("author", ""), highlight)
    year = entry.get("year", "")
    title = entry.get("title", "Untitled")
    link = entry_link(entry)
    linked_title = f"[{title}]({link})" if link else title
    if status == "Online on":
        return f"- {status} `{venue}`: {authors} ({year}). {linked_title}"
    return f"- {status} `{venue}`: {authors} ({year}). {linked_title}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bibfile", type=Path, help="Path to the BibTeX file")
    parser.add_argument("--highlight-author", default="Liu, Feng", help="Author name to highlight in bold")
    args = parser.parse_args()

    entries = parse_bibtex(args.bibfile.read_text(encoding="utf-8"))
    for entry in sorted(entries, key=sort_key):
        print(format_entry(entry, args.highlight_author))


if __name__ == "__main__":
    main()
