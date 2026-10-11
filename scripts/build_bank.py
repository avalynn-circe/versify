#!/usr/bin/env python3
"""Turn a reviewed file into a shipped word bank.

    python scripts/build_bank.py poe

Reads library/<poet>/review.json and library/<poet>/meta.json, keeps only
the approved fragments, and writes library/<poet>/bank.json. The meta file
holds the poet's name, the exact source edition(s) and URL(s), a display
color and a voice note. Afterwards library/catalog.json is regenerated so
the shelf always lists what is on it.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import LIBRARY, load_json, poet_dir, save_json  # noqa: E402

REQUIRED_META = ("id", "name", "color")
REQUIRED_SOURCE = ("title", "edition", "url")


def sources_of(meta: dict) -> list[dict]:
    """A meta file names one `source` or a list of `sources`."""
    if "sources" in meta:
        srcs = list(meta["sources"])
    elif "source" in meta:
        srcs = [meta["source"]]
    else:
        raise ValueError("meta file needs a 'source' or a 'sources' list")
    for src in srcs:
        for k in REQUIRED_SOURCE:
            if k not in src:
                raise ValueError(f"a source block is missing '{k}'")
    return srcs


def build(review: dict, meta: dict) -> dict:
    for k in REQUIRED_META:
        if k not in meta:
            raise ValueError(f"meta file is missing '{k}'")
    srcs = sources_of(meta)
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
        "source": srcs[0],
        "sources": srcs,
        "voice": meta.get("voice", ""),
        "reviewed": bool(meta.get("reviewed", False)),
        "built": date.today().isoformat(),
        "counts": {
            "words": sum(1 for f in fragments if f["type"] == "word"),
            "pairs": sum(1 for f in fragments if f["type"] == "pair"),
        },
        "fragments": fragments,
    }


def write_catalog(library: Path = LIBRARY) -> dict:
    """library/catalog.json: one row per built bank, the shelf at a glance."""
    poets = []
    for d in sorted(library.iterdir()):
        bank_path = d / "bank.json"
        if not d.is_dir() or not bank_path.exists():
            continue
        b = load_json(bank_path)
        poets.append({
            "id": b["id"], "name": b["name"], "color": b.get("color"),
            "words": b["counts"]["words"], "pairs": b["counts"]["pairs"],
            "reviewed": b.get("reviewed", False), "built": b.get("built"),
            "sources": [src.get("title") for src in b.get("sources", [b.get("source", {})])],
        })
    catalog = {"generated": date.today().isoformat(), "poets": poets}
    save_json(library / "catalog.json", catalog)
    return catalog


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("poet")
    ap.add_argument("--review", type=Path)
    ap.add_argument("--meta", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    review_path = args.review or poet_dir(args.poet) / "review.json"
    meta_path = args.meta or poet_dir(args.poet) / "meta.json"
    out_path = args.out or poet_dir(args.poet) / "bank.json"
    try:
        bank = build(load_json(review_path), load_json(meta_path))
    except (ValueError, FileNotFoundError) as e:
        print(f"build failed: {e}", file=sys.stderr)
        return 1
    save_json(out_path, bank)
    print(f"wrote {out_path}: {bank['counts']['words']} words, {bank['counts']['pairs']} pairs")
    if out_path.parent.parent == LIBRARY:
        cat = write_catalog()
        print(f"catalog: {len(cat['poets'])} poets on the shelf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
