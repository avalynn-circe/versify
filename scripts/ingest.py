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
  * --sub REGEX REPLACEMENT (repeatable) rewrites each line before the
    other rules run, for editions that wrap verse in markers such as
    "[Music:" blocks.
  * --keep-caps keeps all-caps lines instead of treating them as titles,
    for a text whose capitalized headings are part of the work (Stein's
    Tender Buttons). Drop the few real headings with --drop.
  * --unwrap joins each run of consecutive lines into one line, for prose
    that Gutenberg wraps at seventy characters, so pairs can be found
    across the wraps. All-caps lines stay on their own line.
  * Everything from a line matching --cut START up to, but not including,
    the next line matching END (repeatable; a cut re-arms after it ends).
    Use this for prefaces, notes sections and prose that sit between poems.
  * Multi-line bracketed notes (a line opening with "[" through the line
    that closes with "]") and lines with no letters at all (rules of
    asterisks, bare dashes).
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


def unwrap(lines: list[str]) -> list[str]:
    """Join wrapped prose into one line per paragraph; caps lines stay separate."""
    out: list[str] = []
    buf: list[str] = []

    def flush():
        if buf:
            out.append(" ".join(buf))
            buf.clear()

    for line in lines:
        if not line.strip():
            flush()
            out.append("")
        elif is_title(line):
            flush()
            out.append(line)
        else:
            buf.append(line.strip())
    flush()
    return out


def clean(lines: list[str], start: str | None, end: str | None,
          drops: list[str], cuts: list[tuple[str, str]] | None = None,
          subs: list[tuple[str, str]] | None = None, keep_caps: bool = False,
          do_unwrap: bool = False) -> tuple[list[str], dict]:
    stats = {"boilerplate": 0, "window": 0, "cut": 0, "title": 0, "number": 0,
             "symbols": 0, "bracket": 0, "editorial": 0, "drop": 0, "kept": 0}
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
    cut_res = [(re.compile(a), re.compile(b)) for a, b in (cuts or [])]
    sub_res = [(re.compile(a), b) for a, b in (subs or [])]
    active_end = None
    in_bracket = False
    out: list[str] = []
    for line in lines:
        s = line.rstrip()
        for rx, repl in sub_res:
            s = rx.sub(repl, s)
        # Em and en dashes become Gutenberg's own "--": the tokenizer treats both
        # as separators, and the repository's no-em-dash rule covers these files.
        s = s.replace("\u2014", "--").replace("\u2013", "--")
        if active_end is not None:
            if active_end.search(s):
                active_end = None  # the END line itself is processed normally below
            else:
                stats["cut"] += 1
                continue
        for start_rx, end_rx in cut_res:
            if start_rx.search(s):
                active_end = end_rx
                stats["cut"] += 1
                break
        if active_end is not None:
            continue
        if in_bracket:
            stats["bracket"] += 1
            if s.rstrip().endswith("]"):
                in_bracket = False
            continue
        if not s.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        # Bracket blocks are recognized before --drop, so a drop pattern that
        # happens to match a block's opening line cannot let the rest leak.
        if BRACKET_RE.match(s):
            stats["bracket"] += 1
            continue
        if s.lstrip().startswith("["):
            in_bracket = True
            stats["bracket"] += 1
            continue
        if any(rx.search(s) for rx in drop_res):
            stats["drop"] += 1
            continue
        if ROMAN_RE.match(s) or DIGITS_RE.match(s):
            stats["number"] += 1
            continue
        if not any(c.isalpha() for c in s):
            stats["symbols"] += 1
            continue
        if PAGE_RE.match(s):
            stats["editorial"] += 1
            continue
        if is_title(s) and not keep_caps:
            stats["title"] += 1
            continue
        out.append(s.strip())
        stats["kept"] += 1
    if do_unwrap:
        out = unwrap(out)
        stats["kept"] = sum(1 for line in out if line)
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
    ap.add_argument("--cut", nargs=2, action="append", default=[], metavar=("START", "END"),
                    help="drop from a line matching START up to the next line matching END (repeatable)")
    ap.add_argument("--sub", nargs=2, action="append", default=[], metavar=("REGEX", "REPLACEMENT"),
                    help="rewrite each line with re.sub before other rules (repeatable)")
    ap.add_argument("--keep-caps", action="store_true", help="keep all-caps lines instead of dropping them as titles")
    ap.add_argument("--unwrap", action="store_true", help="join wrapped prose into one line per paragraph")
    args = ap.parse_args(argv)

    lines = read_lines(args.raw)
    out, stats = clean(lines, args.start, args.end, args.drop, [tuple(c) for c in args.cut],
                       [tuple(c) for c in args.sub], args.keep_caps, args.unwrap)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({stats['kept']} verse lines)")
    for k, v in stats.items():
        if k != "kept":
            print(f"  removed as {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
