"""Shared helpers for the Versify pipeline.

Everything here is standard library only. The tokenizer is the single
definition of what a "word" is, so propose.py (which builds the bank) and
deal.py check (which verifies a finished poem) can never disagree.
"""

import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LIBRARY = ROOT / "library"
SOURCES = ROOT / "sources"


def poet_dir(poet: str) -> Path:
    """Every poet lives in library/<id>/ with meta.json, clean.txt, review.json, bank.json."""
    return LIBRARY / poet

# Contractions that genuinely begin with an apostrophe in older verse.
# Any other leading apostrophe is a quotation mark and gets stripped.
LEADING_APOSTROPHE_OK = {
    "'tis", "'twas", "'twere", "'twill", "'twould", "'neath", "'mid",
    "'midst", "'mongst", "'gainst", "'ere", "'cross", "'round", "'til",
}

_TOKEN_RE = re.compile(r"'?[a-z]+(?:['\-][a-z]+)*")


def normalize_line(line: str) -> str:
    """Lowercase and turn every kind of dash and italics marker into a space."""
    # Fold accents (Hopkins's "Rankèd" becomes "ranked") and odd Unicode forms.
    s = unicodedata.normalize("NFKD", line)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("--", " ").replace("\u2014", " ").replace("\u2013", " ")
    s = s.replace("_", " ")
    return s


def tokenize_line(line: str) -> list[str]:
    """Split one line of verse into word tokens.

    Keeps apostrophes inside words (o'er, don't) and hyphens inside words
    (to-day, sea-foam). Drops stray single letters other than a, i, o.
    """
    out = []
    for m in _TOKEN_RE.finditer(normalize_line(line)):
        tok = m.group(0)
        if tok.startswith("'") and tok not in LEADING_APOSTROPHE_OK:
            tok = tok[1:]
        if not tok:
            continue
        if len(tok) == 1 and tok not in ("a", "i", "o"):
            continue
        out.append(tok)
    return out


def read_lines(path: Path) -> list[str]:
    """Read a text file as a list of lines, tolerating latin-1 Gutenberg files."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return text.splitlines()


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj) -> None:
    """Write JSON atomically so a crash mid-save never corrupts a review file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def load_settings() -> dict:
    return load_json(DATA / "settings.json")


def load_glue() -> dict:
    """The glue set: {"free": [...unlimited...], "once": [...one use each...]}."""
    g = load_json(DATA / "glue-words.json")
    if "words" in g and "free" not in g:  # older single-list format
        return {"free": [], "once": [w.lower() for w in g["words"]]}
    return {"free": [w.lower() for w in g.get("free", [])],
            "once": [w.lower() for w in g.get("once", [])]}


def load_calendar() -> dict:
    path = DATA / "calendar.json"
    return load_json(path) if path.exists() else {"deathdays": True, "events": []}


def load_function_words() -> set[str]:
    return {w.lower() for w in load_json(DATA / "function-words.json")["words"]}


def stable_seed(*parts: str) -> int:
    """A seed that is the same on every machine and every Python version."""
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def relative_to_root(path: Path) -> str:
    """Path as stored in review files: relative to the repo when possible."""
    path = Path(path).resolve()
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def item_key(item: dict) -> str:
    return f"{item['type']}:{item['fragment']}"
