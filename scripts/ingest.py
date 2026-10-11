#!/usr/bin/env python3
"""Turn a raw Project Gutenberg text into clean verse: one poem line per line.

    python scripts/ingest.py sources/raw/poe.txt -o sources/clean/poe.txt

What gets removed:
  * The Gutenberg header, footer and license (everything outside the
    *** START / *** END markers).
  * Everything before --start REGEX and from --end REGEX onward, if given.
    Use these to cut an editor's introduction or an index.
  * Title and heading lines: lines with letters but no lowercase letters.
  * Roman numeral poem numbers, bare digits, bracketed editorial notes.
  * Any line matching a --drop REGEX (repeatable).
  * Runs of blank lines collapse to one, so stanza breaks survive.

Always eyeball the cleaned file afterwards. Each Gutenberg edition is laid
out a little differently and the flags exist so no code change is needed.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_lines  # noqa: E402

START_RE = re.compile(r"^\s*\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG", re.I)
END_RE = re.compile(r"^\s*\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG", re.I)
ROMAN_RE = re.compile(r"^\s*[IVXLCDM]+\.?\s*$")
DIGITS_RE = re.compile(r"^\s*\d+\.?\s*$")
BRACKET_RE = re.compile(r"^\s*[\[\(].*[\]\)]\s*$")
PAGE_RE = re.compile(r"^\s*(page|index|contents|footnote)\b", re.I)


def strip_boilerplate(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    for i, line in enumerate(lines):
        if START_RE.match(line):
            start = i + 1
            break
    for i in range(len(lines) - 1, start, -1):
        if END_RE.match(lines[i]):
            end = i
            break
    return lines[start:end]


def is_title(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    return bool(letters) and not any(c.islower() for c in letters)


def clean(lines: list[str], start: str | None, end: str | None,
          drops: list[str]) -> tuple[list[str], dict]:
    stats = {"boilerplate": 0, "window": 0, "title": 0, "number": 0,
             "bracket": 0, "editorial": 0, "drop": 0, "kept": 0}
    before = len(lines)
    lines = strip_boilerplate(lines)
    stats["boilerplate"] = before - len(lines)

    if start:
        rx = re.compile(start)
        for i, line in enumerate(lines):
            if rx.search(line):
                stats["window"] += i
                lines = lines[i:]
                break
    if end:
        rx = re.compile(end)
        for i, line in enumerate(lines):
            if rx.search(line):
                stats["window"] += len(lines) - i
                lines = lines[:i]
                break

    drop_res = [re.compile(d) for d in drops]
    out: list[str] = []
    for line in lines:
        s = line.rstrip()
        if not s.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        if any(rx.search(s) for rx in drop_res):
            stats["drop"] += 1
            continue
        if ROMAN_RE.match(s) or DIGITS_RE.match(s):
            stats["number"] += 1
            continue
        if BRACKET_RE.match(s):
            stats["bracket"] += 1
            continue
        if PAGE_RE.match(s):
            stats["editorial"] += 1
            continue
        if is_title(s):
            stats["title"] += 1
            continue
        out.append(s.strip())
        stats["kept"] += 1
    while out and out[-1] == "":
        out.pop()
    while out and out[0] == "":
        out.pop(0)
    return out, stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw", type=Path, help="raw Gutenberg text file")
    ap.add_argument("-o", "--out", type=Path, required=True, help="cleaned output file")
    ap.add_argument("--start", help="regex; drop everything before the first match")
    ap.add_argument("--end", help="regex; drop everything from the first match onward")
    ap.add_argument("--drop", action="append", default=[], help="regex; drop matching lines (repeatable)")
    args = ap.parse_args(argv)

    lines = read_lines(args.raw)
    out, stats = clean(lines, args.start, args.end, args.drop)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({stats['kept']} verse lines)")
    for k, v in stats.items():
        if k != "kept":
            print(f"  removed as {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
