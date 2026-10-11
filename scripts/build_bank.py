#!/usr/bin/env python3
"""Turn a reviewed file into a shipped word bank.

    python scripts/build_bank.py poe

Reads review/<poet>.json and data/poets/<poet>.meta.json, keeps only the
approved fragments, and writes data/poets/<poet>.json. The meta file holds
the poet's name, the exact source edition and URL, and a display color.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import POETS, REVIEW, load_json, save_json  # noqa: E402

REQUIRED_META = ("id", "name", "color", "source")
REQUIRED_SOURCE = ("title", "edition", "url")


def build(review: dict, meta: dict) -> dict:
    for k in REQUIRED_META:
        if k not in meta:
            raise ValueError(f"meta file is missing '{k}'")
    for k in REQUIRED_SOURCE:
        if k not in meta["source"]:
            raise ValueError(f"meta file source block is missing '{k}'")
    fragments = []
    for it in review["items"]:
        if it.get("status") != "approved":
            continue
        if len(it["fragment"].split()) > 2:
            raise ValueError(f"fragment longer than two words: {it['fragment']!r}")
        frag = {"text": it["fragment"], "type": it["type"], "count": int(it.get("count", 0))}
        fragments.append(frag)
    if not fragments:
        raise ValueError("no approved fragments; nothing to build")
    fragments.sort(key=lambda f: (f["type"], -f["count"], f["text"]))
    return {
        "schema": 1,
        "id": meta["id"],
        "name": meta["name"],
        "color": meta["color"],
        "source": meta["source"],
        "built": date.today().isoformat(),
        "counts": {
            "words": sum(1 for f in fragments if f["type"] == "word"),
            "pairs": sum(1 for f in fragments if f["type"] == "pair"),
        },
        "fragments": fragments,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("poet")
    ap.add_argument("--review", type=Path)
    ap.add_argument("--meta", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    review_path = args.review or REVIEW / f"{args.poet}.json"
    meta_path = args.meta or POETS / f"{args.poet}.meta.json"
    out_path = args.out or POETS / f"{args.poet}.json"
    try:
        bank = build(load_json(review_path), load_json(meta_path))
    except (ValueError, FileNotFoundError) as e:
        print(f"build failed: {e}", file=sys.stderr)
        return 1
    save_json(out_path, bank)
    print(f"wrote {out_path}: {bank['counts']['words']} words, {bank['counts']['pairs']} pairs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
