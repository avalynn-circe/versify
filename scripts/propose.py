#!/usr/bin/env python3
"""Propose single words and word pairs from a cleaned text, for human review.

    python scripts/propose.py poe
    python scripts/propose.py poe --clean sources/clean/poe.txt --min-pair-count 2

Writes review/<poet>.json. If that file already exists, every decision in it
is preserved: statuses carry over, manual merges survive, counts refresh,
and candidates that vanished from the source are flagged stale rather than
deleted. Re-running is always safe.

Defaults:
  * Single words start as approved, except function words (data/function-words.json),
    which start as pending so the reviewer decides which of them carry meaning.
  * Pairs start as pending. Pairs are adjacent words within one line, never
    across a line break, with both words non-function, count >= min_pair_count
    and pointwise mutual information >= min_pmi.
  * Nothing longer than two words is ever proposed.
"""

import argparse
import math
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (REVIEW, SOURCES, item_key, load_function_words,  # noqa: E402
                    load_json, load_settings, read_lines, relative_to_root,
                    save_json, tokenize_line)


def count_corpus(lines: list[str]) -> tuple[Counter, Counter, int]:
    """Word counts, within-line bigram counts, and total token count."""
    words: Counter = Counter()
    pairs: Counter = Counter()
    total = 0
    for line in lines:
        toks = tokenize_line(line)
        total += len(toks)
        words.update(toks)
        for a, b in zip(toks, toks[1:]):
            pairs[(a, b)] += 1
    return words, pairs, total


def pmi(pair_count: int, a_count: int, b_count: int, total: int) -> float:
    return math.log2((pair_count * total) / (a_count * b_count))


def propose(lines: list[str], function_words: set[str],
            min_pair_count: int, min_pmi: float) -> list[dict]:
    words, pairs, total = count_corpus(lines)
    items: list[dict] = []
    for w, c in words.most_common():
        status = "pending" if w in function_words else "approved"
        items.append({"fragment": w, "type": "word", "count": c, "status": status})
    candidates = []
    for (a, b), c in pairs.items():
        if c < min_pair_count or a in function_words or b in function_words:
            continue
        score = pmi(c, words[a], words[b], total)
        if score < min_pmi:
            continue
        candidates.append({"fragment": f"{a} {b}", "type": "pair", "count": c,
                           "pmi": round(score, 2), "status": "pending"})
    candidates.sort(key=lambda it: (-it["count"], -it["pmi"], it["fragment"]))
    items.extend(candidates)
    return items


def merge(existing: dict | None, fresh: list[dict]) -> list[dict]:
    """Carry every human decision from the old review file into the new one."""
    if not existing:
        return fresh
    old = {item_key(it): it for it in existing.get("items", [])}
    merged: list[dict] = []
    seen = set()
    for it in fresh:
        k = item_key(it)
        seen.add(k)
        prev = old.get(k)
        if prev:
            it["status"] = prev.get("status", it["status"])
            if prev.get("manual"):
                it["manual"] = True
            if prev.get("note"):
                it["note"] = prev["note"]
        merged.append(it)
    for k, prev in old.items():
        if k in seen:
            continue
        # A manual merge, or a candidate the new run no longer proposes.
        kept = dict(prev)
        if not kept.get("manual"):
            kept["stale"] = True
        merged.append(kept)
    return merged


def main(argv=None) -> int:
    settings = load_settings()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("poet", help="poet id, e.g. dickinson")
    ap.add_argument("--clean", type=Path, help="cleaned text (default sources/clean/<poet>.txt)")
    ap.add_argument("--out", type=Path, help="review file (default review/<poet>.json)")
    ap.add_argument("--min-pair-count", type=int, default=settings.get("min_pair_count", 2))
    ap.add_argument("--min-pmi", type=float, default=settings.get("min_pmi", 3.0))
    args = ap.parse_args(argv)

    clean_path = args.clean or SOURCES / "clean" / f"{args.poet}.txt"
    out_path = args.out or REVIEW / f"{args.poet}.json"
    if not clean_path.exists():
        print(f"no cleaned text at {clean_path}; run ingest.py first", file=sys.stderr)
        return 2

    lines = read_lines(clean_path)
    fresh = propose(lines, load_function_words(), args.min_pair_count, args.min_pmi)
    existing = load_json(out_path) if out_path.exists() else None
    items = merge(existing, fresh)

    review = {
        "poet": args.poet,
        "clean_text": relative_to_root(clean_path),
        "generated": date.today().isoformat(),
        "min_pair_count": args.min_pair_count,
        "min_pmi": args.min_pmi,
        "items": items,
    }
    save_json(out_path, review)

    n_words = sum(1 for it in items if it["type"] == "word")
    n_pairs = sum(1 for it in items if it["type"] == "pair")
    n_pending = sum(1 for it in items if it["status"] == "pending")
    longest = max((len(it["fragment"].split()) for it in items), default=0)
    assert longest <= 2, "a fragment longer than two words slipped through"
    print(f"wrote {out_path}: {n_words} words, {n_pairs} pairs, {n_pending} pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
