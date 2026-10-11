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
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (LIBRARY, load_calendar, load_glue, load_json,  # noqa: E402
                    load_settings, stable_seed, tokenize_line)

KIND_RANK = {"birthday": 0, "deathday": 1, "season": 2}


def list_banks() -> dict[str, Path]:
    """Every library/<id>/bank.json, in shelf order."""
    if not LIBRARY.exists():
        return {}
    return {d.name: d / "bank.json" for d in sorted(LIBRARY.iterdir())
            if d.is_dir() and (d / "bank.json").exists()}


def load_bank(poet: str) -> dict:
    banks = list_banks()
    if poet not in banks:
        known = ", ".join(banks) or "none built yet"
        raise SystemExit(f"no bank for '{poet}' (available: {known})")
    return load_json(banks[poet])


def poet_for_date(day: date, settings: dict) -> str:
    """Rotate through settings.rotation, or through the whole shelf if it is empty."""
    rotation = settings.get("rotation") or list(list_banks())
    if not rotation:
        raise SystemExit("no banks in the library")
    epoch = date.fromisoformat(settings["rotation_epoch"])
    return rotation[(day - epoch).days % len(rotation)]


def _md(day: date) -> str:
    return f"{day.month:02d}-{day.day:02d}"


def event_matches(ev: dict, day: date) -> bool:
    md = _md(day)
    if "date" in ev:
        return ev["date"] == md
    return ev["from"] <= md <= ev["to"]


def occasion_for_date(day: date, calendar: dict, available: set[str] | None = None) -> dict | None:
    """The calendar event that claims this day, if any: birthday beats deathday beats season."""
    found = []
    for ev in calendar.get("events", []):
        if ev.get("kind") == "deathday" and not calendar.get("deathdays", True):
            continue
        if available is not None and ev["poet"] not in available:
            continue
        if event_matches(ev, day):
            found.append(ev)
    if not found:
        return None
    found.sort(key=lambda e: (KIND_RANK.get(e.get("kind"), 9), e["poet"]))
    return found[0]


def choose_poet(day: date, settings: dict, calendar: dict) -> tuple[str, dict | None]:
    """Today's poet: a calendar occasion if one claims the day, else the rotation."""
    ev = occasion_for_date(day, calendar, set(list_banks()))
    if ev:
        return ev["poet"], ev
    return poet_for_date(day, settings), None


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


def eligible_sections(bank: dict, floor: int) -> list[str]:
    """Sections with enough distinct words to deal a whole day from."""
    return sorted(name for name, c in (bank.get("sections") or {}).items() if c.get("words", 0) >= floor)


def pick_section(bank: dict, poet: str, day: date, settings: dict, wanted: str | None) -> str | None:
    """The section today's draw comes from, or None for the whole bank.

    wanted: a section name to force, "none" for the whole bank, or None to
    let the day decide (seeded, so the same day always picks the same one).
    """
    if wanted == "none":
        return None
    if wanted:
        if wanted not in (bank.get("sections") or {}):
            known = ", ".join(sorted(bank.get("sections") or {})) or "no sections"
            raise SystemExit(f"no section '{wanted}' for {poet} (known: {known})")
        return wanted
    if not settings.get("sections", True):
        return None
    options = eligible_sections(bank, settings.get("section_min_words", 400))
    if not options:
        return None
    rng = random.Random(stable_seed(poet, day.isoformat(), "section"))
    return rng.choice(options)


def make_draw(poet: str, day: date, n: int, use: int, scheme: str,
              seed: int | None = None, occasion: dict | None = None,
              section: str | None = None) -> dict:
    settings = load_settings()
    bank = load_bank(poet)
    chosen = pick_section(bank, poet, day, settings, section)
    pool = [f for f in bank["fragments"] if chosen is None or chosen in f.get("sections", [])]
    seed_value = seed if seed is not None else stable_seed(poet, day.isoformat())
    rng = random.Random(seed_value)
    picks = weighted_sample(rng, pool, n, scheme)
    glue = load_glue()
    srcs = bank.get("sources") or [bank.get("source", {})]
    src = srcs[0]
    titles = "; ".join(str(x.get("title", "?")) for x in srcs)
    gids = ", ".join(str(x["gutenberg_id"]) for x in srcs if x.get("gutenberg_id"))
    source_line = f"Source: {titles} (Project Gutenberg" + (f" {gids})." if gids else ").")
    pretty_date = f"{day.day} {day.strftime('%B %Y')}"
    phrase = f", {occasion['phrase']}" if occasion and occasion.get("phrase") else ""
    sec = f" ({chosen})" if chosen else ""
    return {
        "poet": bank["id"],
        "poet_name": bank["name"],
        "date": day.isoformat(),
        "seed": seed_value,
        "weight": scheme,
        "use": use,
        "section": chosen,
        "fragments": [{"text": p["text"], "type": p["type"]} for p in picks],
        "glue": glue,
        "lines": [settings.get("min_lines", 4), settings.get("max_lines", 8)],
        "voice": bank.get("voice", ""),
        "source": src,
        "occasion": {"kind": occasion["kind"], "phrase": occasion.get("phrase", "")} if occasion else None,
        "colophon": {
            "assembled_line": f"Assembled from the words of {bank['name']}{sec}{phrase}, {pretty_date}.",
            "source_line": source_line,
        },
        "rules": [
            f"Use exactly {use} distinct fragments of the {len(picks)} dealt.",
            "One fragment may be used twice, as a refrain, if both uses end a line.",
            "A pair stays together, in order, on one line.",
            "Free glue is unlimited. Budgeted glue may be spent once each. Nothing else may be added.",
            f"Between {settings.get('min_lines', 4)} and {settings.get('max_lines', 8)} lines.",
            "The last word of the poem is a fragment, never glue; make it a noun or a verb.",
            "Line breaks, capitalization and punctuation are free. No em dashes.",
            "Do not change a word's form: no plurals, tenses or possessives the bank did not deal.",
        ],
    }


def print_draw(draw: dict, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(draw, indent=2, ensure_ascii=False))
        return
    print(f"{draw['poet_name']}, {draw['date']}  (seed {draw['seed']})")
    if draw.get("section"):
        print(f"section: {draw['section']}")
    if draw.get("occasion"):
        print(f"occasion: {draw['occasion']['kind']}, {draw['occasion']['phrase']}")
    print(f"use exactly {draw['use']} of these {len(draw['fragments'])} fragments:")
    for i, f in enumerate(draw["fragments"], 1):
        tag = "  [pair]" if f["type"] == "pair" else ""
        print(f"  {i:2d}. {f['text']}{tag}")
    print("free glue: " + ", ".join(draw["glue"]["free"]))
    print("glue, once each: " + ", ".join(draw["glue"]["once"]))
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


def solve(tokens: list, fragments: list[dict], free: set[str], once: list[str], use: int | None = None):
    """Find one assignment of poem tokens to fragments and glue, or None.

    Depth-first search over the token stream. The poem is short and the
    draw is small, so this is instant; a search is used instead of a greedy
    scan so a word that is both glue and a dealt fragment never produces a
    false failure. State: fragments used, fragments whose first use ended a
    line (eligible to become the refrain), the refrain fragment if any, and
    the remaining budgeted glue.
    """
    words = {}
    pairs = {}
    for idx, f in enumerate(fragments):
        parts = f["text"].split()
        if len(parts) == 2:
            pairs.setdefault(tuple(parts), []).append(idx)
        else:
            words.setdefault(parts[0], []).append(idx)
    once_count = Counter(once)
    once_keys = list(once_count.keys())
    n = len(tokens)
    best_fail = {"pos": -1}
    memo: set = set()

    def line_final(j: int) -> bool:
        return j >= n or tokens[j] is None

    def rec(i, used, final_used, refrain, glue_left, trail):
        if i >= n:
            # With a target count, keep searching until an assignment hits it,
            # so a word that is both glue and fragment lands on the right side.
            return trail if use is None or len(used) == use else None
        key = (i, used, final_used, refrain, glue_left)
        if key in memo:
            return None
        tok = tokens[i]
        if tok is None:
            return rec(i + 1, used, final_used, refrain, glue_left, trail)
        nxt = tokens[i + 1] if i + 1 < n else None

        def try_fragment(idx, length, kind):
            ends_line = line_final(i + length)
            if idx not in used:
                fu = final_used | {idx} if ends_line else final_used
                return rec(i + length, used | {idx}, fu, refrain, glue_left, trail + [(kind, idx)])
            if refrain is None and idx in final_used and ends_line:
                return rec(i + length, used, final_used, idx, glue_left, trail + [("refrain", idx)])
            return None

        if nxt is not None:
            for idx in pairs.get((tok, nxt), []):
                r = try_fragment(idx, 2, "pair")
                if r is not None:
                    return r
        for idx in words.get(tok, []):
            r = try_fragment(idx, 1, "word")
            if r is not None:
                return r
        if tok in free:
            r = rec(i + 1, used, final_used, refrain, glue_left, trail + [("glue", tok)])
            if r is not None:
                return r
        if tok in once_count:
            k = once_keys.index(tok)
            if glue_left[k] > 0:
                new = tuple(v - (1 if j == k else 0) for j, v in enumerate(glue_left))
                r = rec(i + 1, used, final_used, refrain, new, trail + [("glue", tok)])
                if r is not None:
                    return r
        if i > best_fail["pos"]:
            best_fail["pos"] = i
        memo.add(key)
        return None

    trail = rec(0, frozenset(), frozenset(), None, tuple(once_count.values()), [])
    return trail, best_fail["pos"]


def check(draw: dict, poem: str, use: int | None = None, lines: tuple | None = None) -> dict:
    use = use if use is not None else draw["use"]
    lo, hi = lines if lines is not None else tuple(draw.get("lines", (1, 10_000)))
    tokens = tokenize_poem(poem)
    fragments = draw["fragments"]
    glue = draw["glue"]
    if isinstance(glue, list):  # older draws: everything budgeted once
        glue = {"free": [], "once": glue}
    free = {g.lower() for g in glue.get("free", [])}
    once = [g.lower() for g in glue.get("once", [])]
    trail, fail_pos = solve(tokens, fragments, free, once, use)
    count_only = False
    if trail is None:
        trail, fail_pos = solve(tokens, fragments, free, once)
        count_only = trail is not None

    vocab = set(free) | set(once)
    for f in fragments:
        vocab.update(f["text"].split())
    unknown = sorted({t for t in tokens if t is not None and t not in vocab})
    n_lines = sum(1 for line in poem.splitlines() if tokenize_line(line))

    if trail is None:
        at = tokens[fail_pos] if 0 <= fail_pos < len(tokens) else None
        problems = []
        if unknown:
            problems.append(f"words not in the draw or glue: {', '.join(unknown)}")
        if at and at not in unknown:
            problems.append(f"could not account for '{at}': a fragment or budgeted glue word used too many times, "
                            "a pair broken apart, or a second refrain")
        if not problems:
            problems.append("could not match the poem to the draw")
        return {"ok": False, "fragments_used": None, "glue_used": None, "problems": problems}

    frag_idx = [idx for kind, idx in trail if kind in ("word", "pair")]
    refrain = [fragments[idx]["text"] for kind, idx in trail if kind == "refrain"]
    glue_used = [tok for kind, tok in trail if kind == "glue"]
    problems = []
    if count_only or len(frag_idx) != use:
        problems.append(f"poem uses {len(frag_idx)} distinct fragments; it must use exactly {use}")
    if not (lo <= n_lines <= hi):
        problems.append(f"poem has {n_lines} lines; it must have between {lo} and {hi}")
    if trail and trail[-1][0] == "glue":
        problems.append(f"the last word '{trail[-1][1]}' is glue; end on a fragment, a noun or a verb")
    return {
        "ok": not problems,
        "fragments_used": len(frag_idx),
        "fragments": [fragments[i]["text"] for i in frag_idx],
        "refrain": refrain[0] if refrain else None,
        "glue_used": glue_used,
        "lines": n_lines,
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
        p.add_argument("--out", type=Path, help="also write the draw as JSON to this file")
        p.add_argument("--section", help="draw from this section only, or 'none' for the whole bank")

    p_today = sub.add_parser("today", help="today's poet by rotation, and the draw")
    add_draw_args(p_today)
    p_draw = sub.add_parser("draw", help="draw from a named poet")
    p_draw.add_argument("--poet", required=True)
    add_draw_args(p_draw)
    p_check = sub.add_parser("check", help="verify a poem against its draw")
    p_check.add_argument("--draw", type=Path, required=True, help="JSON written by draw/today")
    p_check.add_argument("--poem", type=Path, required=True, help="poem text file, or - for stdin")
    p_check.add_argument("--use", type=int, help="override required fragment count")
    p_check.add_argument("--lines", type=int, nargs=2, metavar=("MIN", "MAX"), help="override the line bounds")
    sub.add_parser("poets", help="list available banks")
    p_sec = sub.add_parser("sections", help="list a poet's sections and which are big enough to deal from")
    p_sec.add_argument("--poet", required=True)
    p_cal = sub.add_parser("calendar", help="list the year's overrides and who is up each day")
    p_cal.add_argument("--year", type=int, default=date.today().year)
    p_cal.add_argument("--days", type=int, help="print the next N days from today instead")

    args = ap.parse_args(argv)

    if args.cmd == "poets":
        banks = list_banks()
        for pid, path in banks.items():
            b = load_json(path)
            nsec = len(b.get("sections") or {})
            print(f"{pid}: {b['name']} ({b['counts']['words']} words, {b['counts']['pairs']} pairs, {nsec} sections)")
        print("rotation: " + " -> ".join(settings["rotation"]) + f" from {settings['rotation_epoch']}")
        today_poet, today_ev = choose_poet(date.today(), settings, load_calendar())
        print("today: " + today_poet + (f"  ({today_ev['kind']}: {today_ev.get('phrase', '')})" if today_ev else ""))
        return 0

    if args.cmd == "calendar":
        calendar = load_calendar()
        if args.days:
            start = date.today()
            for i in range(args.days):
                d = start + timedelta(days=i)
                poet, ev = choose_poet(d, settings, calendar)
                tag = f"  ({ev['kind']}: {ev.get('phrase', '')})" if ev else ""
                print(f"{d.isoformat()}  {poet}{tag}")
            return 0
        print(f"overrides for {args.year}:")
        for ev in sorted(calendar.get("events", []), key=lambda e: e.get("date") or e.get("from")):
            if ev.get("kind") == "deathday" and not calendar.get("deathdays", True):
                continue
            when = ev.get("date") or f"{ev['from']} to {ev['to']}"
            print(f"  {when:14s} {ev['poet']:10s} {ev['kind']:9s} {ev.get('phrase', '')}")
        return 0

    if args.cmd in ("today", "draw"):
        day = date.fromisoformat(args.date) if args.date else date.today()
        calendar = load_calendar()
        if args.cmd == "draw":
            poet = args.poet
            ev = occasion_for_date(day, calendar, {poet})
        else:
            poet, ev = choose_poet(day, settings, calendar)
        draw = make_draw(poet, day, args.n, args.use, args.weight, args.seed, ev, args.section)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(draw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print_draw(draw, args.format)
        return 0

    if args.cmd == "sections":
        bank = load_bank(args.poet)
        floor = settings.get("section_min_words", 400)
        secs = bank.get("sections") or {}
        if not secs:
            print(f"{args.poet}: no sections; every draw uses the whole bank")
            return 0
        for name, c in sorted(secs.items(), key=lambda kv: -kv[1]["words"]):
            ok = "dealt from" if c["words"] >= floor else f"too small (floor {floor})"
            print(f"  {name:32s} {c['words']:6d} words {c['pairs']:5d} pairs   {ok}")
        return 0

    if args.cmd == "check":
        draw = load_json(args.draw)
        poem = sys.stdin.read() if str(args.poem) == "-" else args.poem.read_text(encoding="utf-8")
        result = check(draw, poem, args.use, tuple(args.lines) if args.lines else None)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ok"] else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
