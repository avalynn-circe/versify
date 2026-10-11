#!/usr/bin/env python3
"""The dealer. All randomness in Versify goes through here.

    python scripts/deal.py today                  # today's poet and fragments
    python scripts/deal.py draw --poet poe        # a draw from one poet
    python scripts/deal.py draw --poet poe --date 2026-10-14
    python scripts/deal.py check --draw draw.json --poem poem.txt
    python scripts/deal.py poets                  # list banks and rotation

Draws are seeded from the poet and the date, so there is exactly one draw
per poet per day and anyone running it that day sees the same fragments.
Pass --seed to override. A draw never repeats a fragment.

By default fragments are weighted by log frequency: the words a poet
returns to show up often, the one-off oddities still appear, just rarely.
Use --weight uniform or --weight freq to change that.

`check` verifies a finished poem against the draw it came from: every word
must be a drawn fragment (pairs used intact, in order, on one line) or a
glue word spent at most once, and exactly `use` fragments must appear.
"""

import argparse
import json
import math
import random
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (POETS, load_glue, load_json, load_settings,  # noqa: E402
                    stable_seed, tokenize_line)


def list_banks() -> dict[str, Path]:
    return {p.stem: p for p in sorted(POETS.glob("*.json")) if not p.name.endswith(".meta.json")}


def load_bank(poet: str) -> dict:
    banks = list_banks()
    if poet not in banks:
        known = ", ".join(banks) or "none built yet"
        raise SystemExit(f"no bank for '{poet}' (available: {known})")
    return load_json(banks[poet])


def poet_for_date(day: date, settings: dict) -> str:
    rotation = settings["rotation"]
    epoch = date.fromisoformat(settings["rotation_epoch"])
    return rotation[(day - epoch).days % len(rotation)]


def weight_of(count: int, scheme: str) -> float:
    if scheme == "uniform":
        return 1.0
    if scheme == "freq":
        return float(max(count, 1))
    if scheme == "log":
        return 1.0 + math.log(max(count, 1))
    raise SystemExit(f"unknown weight scheme '{scheme}'")


def weighted_sample(rng: random.Random, items: list[dict], n: int, scheme: str) -> list[dict]:
    """Sample n distinct items with probability proportional to their weight."""
    pool = list(items)
    weights = [weight_of(it["count"], scheme) for it in pool]
    out = []
    while pool and len(out) < n:
        total = sum(weights)
        r = rng.random() * total
        acc = 0.0
        for i, w in enumerate(weights):
            acc += w
            if r < acc:
                out.append(pool.pop(i))
                weights.pop(i)
                break
        else:
            out.append(pool.pop())
            weights.pop()
    return out


def make_draw(poet: str, day: date, n: int, use: int, scheme: str,
              seed: int | None = None) -> dict:
    bank = load_bank(poet)
    seed_value = seed if seed is not None else stable_seed(poet, day.isoformat())
    rng = random.Random(seed_value)
    picks = weighted_sample(rng, bank["fragments"], n, scheme)
    glue = load_glue()
    src = bank.get("source", {})
    gid = src.get("gutenberg_id")
    source_line = f"Source: {src.get('title', '?')} (Project Gutenberg" + (f" {gid})." if gid else ").")
    pretty_date = f"{day.day} {day.strftime('%B %Y')}"
    return {
        "poet": bank["id"],
        "poet_name": bank["name"],
        "date": day.isoformat(),
        "seed": seed_value,
        "weight": scheme,
        "use": use,
        "fragments": [{"text": p["text"], "type": p["type"]} for p in picks],
        "glue": glue,
        "voice": bank.get("voice", ""),
        "source": src,
        "colophon": {
            "assembled_line": f"Assembled from the words of {bank['name']}, {pretty_date}.",
            "source_line": source_line,
        },
        "rules": [
            f"Use exactly {use} of the {len(picks)} fragments, each at most once.",
            "A pair stays together, in order, on one line.",
            "Each glue word may be spent once. Nothing else may be added.",
            "Line breaks, capitalization and punctuation are free.",
            "Do not change a word's form: no plurals, tenses or possessives the bank did not deal.",
        ],
    }


def print_draw(draw: dict, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(draw, indent=2, ensure_ascii=False))
        return
    print(f"{draw['poet_name']}, {draw['date']}  (seed {draw['seed']})")
    print(f"use exactly {draw['use']} of these {len(draw['fragments'])} fragments:")
    for i, f in enumerate(draw["fragments"], 1):
        tag = "  [pair]" if f["type"] == "pair" else ""
        print(f"  {i:2d}. {f['text']}{tag}")
    print("glue, once each: " + ", ".join(draw["glue"]))
    if draw.get("voice"):
        print("voice: " + draw["voice"])
    print(draw["colophon"]["assembled_line"])
    print(draw["colophon"]["source_line"])


# ---------------------------------------------------------------- check ----

def tokenize_poem(text: str) -> list[str | None]:
    """Tokens with None between lines so pairs cannot straddle a line break."""
    toks: list[str | None] = []
    for line in text.splitlines():
        lt = tokenize_line(line)
        if lt:
            toks.extend(lt)
            toks.append(None)
    return toks


def solve(tokens: list[str | None], fragments: list[dict], glue: list[str]):
    """Find one assignment of poem tokens to fragments and glue, or None.

    Depth-first search over the token stream. The poem is short and the
    draw is small, so this is instant; a search is used instead of a greedy
    scan so a word that is both glue and a dealt fragment never produces a
    false failure.
    """
    words = {}
    pairs = {}
    for idx, f in enumerate(fragments):
        parts = f["text"].split()
        if len(parts) == 2:
            pairs.setdefault(tuple(parts), []).append(idx)
        else:
            words.setdefault(parts[0], []).append(idx)
    glue_count = Counter(glue)
    n = len(tokens)
    best_fail = {"pos": -1}
    memo: set = set()

    def rec(i: int, used: frozenset, glue_left: tuple, trail: list):
        if i >= n:
            return trail
        key = (i, used, glue_left)
        if key in memo:
            return None
        tok = tokens[i]
        if tok is None:
            return rec(i + 1, used, glue_left, trail)
        nxt = tokens[i + 1] if i + 1 < n else None
        if nxt is not None:
            for idx in pairs.get((tok, nxt), []):
                if idx not in used:
                    r = rec(i + 2, used | {idx}, glue_left, trail + [("pair", idx)])
                    if r is not None:
                        return r
        for idx in words.get(tok, []):
            if idx not in used:
                r = rec(i + 1, used | {idx}, glue_left, trail + [("word", idx)])
                if r is not None:
                    return r
        gl = dict(zip(glue_count.keys(), glue_left))
        if gl.get(tok, 0) > 0:
            new = tuple(gl[k] - (1 if k == tok else 0) for k in glue_count.keys())
            r = rec(i + 1, used, new, trail + [("glue", tok)])
            if r is not None:
                return r
        if i > best_fail["pos"]:
            best_fail["pos"] = i
        memo.add(key)
        return None

    trail = rec(0, frozenset(), tuple(glue_count.values()), [])
    return trail, best_fail["pos"]


def check(draw: dict, poem: str, use: int | None = None) -> dict:
    use = use if use is not None else draw["use"]
    tokens = tokenize_poem(poem)
    fragments = draw["fragments"]
    glue = [g.lower() for g in draw["glue"]]
    trail, fail_pos = solve(tokens, fragments, glue)

    vocab = set(glue)
    for f in fragments:
        vocab.update(f["text"].split())
    unknown = sorted({t for t in tokens if t is not None and t not in vocab})

    if trail is None:
        at = tokens[fail_pos] if 0 <= fail_pos < len(tokens) else None
        problems = []
        if unknown:
            problems.append(f"words not in the draw or glue: {', '.join(unknown)}")
        if at and at not in unknown:
            problems.append(f"could not account for '{at}': a fragment or glue word used too many times, or a pair broken apart")
        if not problems:
            problems.append("could not match the poem to the draw")
        return {"ok": False, "fragments_used": None, "glue_used": None, "problems": problems}

    frag_idx = [idx for kind, idx in trail if kind != "glue"]
    glue_used = [tok for kind, tok in trail if kind == "glue"]
    problems = []
    if len(frag_idx) != use:
        problems.append(f"poem uses {len(frag_idx)} fragments; it must use exactly {use}")
    return {
        "ok": not problems,
        "fragments_used": len(frag_idx),
        "fragments": [fragments[i]["text"] for i in frag_idx],
        "glue_used": glue_used,
        "problems": problems,
    }


# ----------------------------------------------------------------- main ----

def main(argv=None) -> int:
    settings = load_settings()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_draw_args(p):
        p.add_argument("--n", type=int, default=settings["draw"], help="fragments to deal")
        p.add_argument("--use", type=int, default=settings["use"], help="fragments the poem must use")
        p.add_argument("--weight", default=settings["weight"], choices=["log", "uniform", "freq"])
        p.add_argument("--date", help="YYYY-MM-DD (default today)")
        p.add_argument("--seed", type=int, help="override the date seed")
        p.add_argument("--format", default="json", choices=["json", "text"])

    p_today = sub.add_parser("today", help="today's poet by rotation, and the draw")
    add_draw_args(p_today)
    p_draw = sub.add_parser("draw", help="draw from a named poet")
    p_draw.add_argument("--poet", required=True)
    add_draw_args(p_draw)
    p_check = sub.add_parser("check", help="verify a poem against its draw")
    p_check.add_argument("--draw", type=Path, required=True, help="JSON written by draw/today")
    p_check.add_argument("--poem", type=Path, required=True, help="poem text file, or - for stdin")
    p_check.add_argument("--use", type=int, help="override required fragment count")
    sub.add_parser("poets", help="list available banks")

    args = ap.parse_args(argv)

    if args.cmd == "poets":
        banks = list_banks()
        for pid, path in banks.items():
            b = load_json(path)
            print(f"{pid}: {b['name']} ({b['counts']['words']} words, {b['counts']['pairs']} pairs)")
        print("rotation: " + " -> ".join(settings["rotation"]) + f" from {settings['rotation_epoch']}")
        print("today: " + poet_for_date(date.today(), settings))
        return 0

    if args.cmd in ("today", "draw"):
        day = date.fromisoformat(args.date) if args.date else date.today()
        poet = args.poet if args.cmd == "draw" else poet_for_date(day, settings)
        draw = make_draw(poet, day, args.n, args.use, args.weight, args.seed)
        print_draw(draw, args.format)
        return 0

    if args.cmd == "check":
        draw = load_json(args.draw)
        poem = sys.stdin.read() if str(args.poem) == "-" else args.poem.read_text(encoding="utf-8")
        result = check(draw, poem, args.use)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ok"] else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
