"""Tests for the Versify pipeline and dealer. Run with: python -m unittest discover -s tests"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_bank  # noqa: E402
import common  # noqa: E402
import deal  # noqa: E402
import ingest  # noqa: E402
import propose  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "gutenberg_sample.txt"


class TokenizerTests(unittest.TestCase):
    def test_keeps_apostrophes_and_hyphens_inside_words(self):
        toks = common.tokenize_line("O'er the _pallid_--bust, 'tis to-day; “I” said")
        self.assertEqual(toks, ["o'er", "the", "pallid", "bust", "'tis", "to-day", "i", "said"])

    def test_strips_quotation_apostrophes_and_stray_letters(self):
        self.assertEqual(common.tokenize_line("'quoted' x a b"), ["quoted", "a"])

    def test_stable_seed_is_deterministic(self):
        self.assertEqual(common.stable_seed("poe", "2026-10-13"), common.stable_seed("poe", "2026-10-13"))
        self.assertNotEqual(common.stable_seed("poe", "2026-10-13"), common.stable_seed("poe", "2026-10-14"))


class IngestTests(unittest.TestCase):
    def test_strips_boilerplate_titles_numbers_and_notes(self):
        lines = common.read_lines(FIXTURE)
        out, stats = ingest.clean(lines, None, None, [])
        text = "\n".join(out)
        self.assertNotIn("Project Gutenberg", text)
        self.assertNotIn("THE LANTERN", text)
        self.assertNotIn("Transcriber", text)
        self.assertNotIn("Updated editions", text)
        self.assertFalse(any(re.fullmatch(r"[IVX]+\.", l) for l in out))
        self.assertIn("The lantern swings above the pallid bust,", out)
        self.assertEqual(stats["kept"], 20)
        self.assertNotIn("\n\n\n", text, "blank lines should collapse to single stanza breaks")

    def test_start_end_and_drop_windows(self):
        lines = common.read_lines(FIXTURE)
        out, _ = ingest.clean(lines, start=r"To-day the garden", end=r"The clover and the bee", drops=[r"marble"])
        self.assertEqual(out[0], "To-day the garden sleeps beneath the frost,")
        self.assertFalse(any("marble" in l for l in out))
        self.assertFalse(any("clover and the bee" in l for l in out))


    def test_cut_blocks_multiline_brackets_and_symbol_lines(self):
        lines = [
            "PREFACE.", "Some prose about the poet.", "More prose.", "",
            "THE LANTERN.", "[Published in a magazine",
            "at the request of a friend.]", "The lantern swings,",
            "       *       *       *", "NOTES.",
            "1. The lantern was first printed in 1890.", "THE BUST.", "The bust is pale.",
        ]
        out, stats = ingest.clean(lines, None, None, [], cuts=[(r"^PREFACE", r"^THE LANTERN"), (r"^NOTES\.$", r"^THE BUST")])
        self.assertEqual(out, ["The lantern swings,", "The bust is pale."])
        self.assertEqual(stats["symbols"], 1)
        self.assertEqual(stats["bracket"], 2)
        self.assertGreaterEqual(stats["cut"], 5)


class ProposeTests(unittest.TestCase):
    def setUp(self):
        lines, _ = ingest.clean(common.read_lines(FIXTURE), None, None, [])
        self.lines = lines
        self.fw = common.load_function_words()
        self.items = propose.propose(lines, self.fw, min_pair_count=2, min_pmi=3.0)

    def test_nothing_longer_than_two_words(self):
        self.assertTrue(all(len(it["fragment"].split()) <= 2 for it in self.items))

    def test_pairs_surface_and_default_pending(self):
        pairs = {it["fragment"]: it for it in self.items if it["type"] == "pair"}
        self.assertIn("pallid bust", pairs)
        self.assertIn("hollow wind", pairs)
        self.assertIn("marble eyes", pairs)
        self.assertEqual(pairs["pallid bust"]["count"], 3)
        self.assertTrue(all(p["status"] == "pending" for p in pairs.values()))
        self.assertNotIn("the lantern", pairs, "function words never form half of a pair")

    def test_words_default_approved_except_function_words(self):
        words = {it["fragment"]: it for it in self.items if it["type"] == "word"}
        self.assertEqual(words["lantern"]["status"], "approved")
        self.assertEqual(words["the"]["status"], "pending")
        self.assertEqual(words["o'er"]["status"], "pending")
        self.assertEqual(words["to-day"]["status"], "approved")

    def test_sorted_by_frequency(self):
        words = [it for it in self.items if it["type"] == "word"]
        self.assertEqual(words[0]["fragment"], "the")
        counts = [w["count"] for w in words]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_rerun_preserves_decisions(self):
        existing = {"items": [dict(it) for it in self.items]}
        for it in existing["items"]:
            if it["fragment"] == "pallid bust":
                it["status"] = "approved"
            if it["fragment"] == "lantern":
                it["status"] = "rejected"
        existing["items"].append({"fragment": "cold frost", "type": "pair", "count": 0,
                                  "status": "approved", "manual": True})
        existing["items"].append({"fragment": "vanished", "type": "word", "count": 1,
                                  "status": "approved"})
        merged = propose.merge(existing, propose.propose(self.lines, self.fw, 2, 3.0))
        by_key = {common.item_key(it): it for it in merged}
        self.assertEqual(by_key["pair:pallid bust"]["status"], "approved")
        self.assertEqual(by_key["word:lantern"]["status"], "rejected")
        self.assertTrue(by_key["pair:cold frost"]["manual"])
        self.assertNotIn("stale", by_key["pair:cold frost"])
        self.assertTrue(by_key["word:vanished"]["stale"])


class BuildBankTests(unittest.TestCase):
    def test_only_approved_fragments_ship(self):
        review = {"items": [
            {"fragment": "lantern", "type": "word", "count": 3, "status": "approved"},
            {"fragment": "the", "type": "word", "count": 30, "status": "pending"},
            {"fragment": "pallid bust", "type": "pair", "count": 4, "status": "approved"},
            {"fragment": "hollow wind", "type": "pair", "count": 4, "status": "rejected"},
        ]}
        meta = {"id": "sample", "name": "Nobody", "color": "#000",
                "source": {"title": "t", "edition": "e", "url": "u"}}
        bank = build_bank.build(review, meta)
        texts = {f["text"] for f in bank["fragments"]}
        self.assertEqual(texts, {"lantern", "pallid bust"})
        self.assertEqual(bank["counts"], {"words": 1, "pairs": 1})
        self.assertEqual(bank["source"]["url"], "u")

    def test_rejects_missing_meta(self):
        with self.assertRaises(ValueError):
            build_bank.build({"items": [{"fragment": "a", "type": "word", "count": 1, "status": "approved"}]},
                             {"id": "x", "name": "x", "color": "x", "source": {"title": "t"}})


class DealTests(unittest.TestCase):
    """End to end: fixture -> review -> bank -> draw -> check, in a temp poets dir."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.poets = Path(cls.tmp.name)
        lines, _ = ingest.clean(common.read_lines(FIXTURE), None, None, [])
        items = propose.propose(lines, common.load_function_words(), 2, 3.0)
        for it in items:
            if it["status"] == "pending":
                it["status"] = "approved" if it["type"] == "pair" else "rejected"
        meta = {"id": "sample", "name": "Nobody", "color": "#000", "voice": "Plain.",
                "source": {"title": "Sample Verses", "edition": "e", "url": "u", "gutenberg_id": 99}}
        cls.bank = build_bank.build({"items": items}, meta)
        common.save_json(cls.poets / "sample.json", cls.bank)
        common.save_json(cls.poets / "sample.meta.json", meta)
        cls._orig = deal.POETS
        deal.POETS = cls.poets

    @classmethod
    def tearDownClass(cls):
        deal.POETS = cls._orig
        cls.tmp.cleanup()

    def draw(self, n=12, use=6, **kw):
        return deal.make_draw("sample", date(2026, 10, 13), n, use, "log", **kw)

    def test_draw_is_deterministic_per_date_and_never_repeats(self):
        a, b = self.draw(), self.draw()
        self.assertEqual(a["fragments"], b["fragments"])
        c = deal.make_draw("sample", date(2026, 10, 14), 12, 6, "log")
        self.assertNotEqual(a["fragments"], c["fragments"])
        texts = [f["text"] for f in a["fragments"]]
        self.assertEqual(len(texts), len(set(texts)))
        self.assertEqual(len(texts), 12)

    def test_draw_uses_only_approved_fragments_and_bank_limit(self):
        approved = {f["text"] for f in self.bank["fragments"]}
        for f in self.draw(n=500, use=6)["fragments"]:
            self.assertIn(f["text"], approved)
        self.assertEqual(len(self.draw(n=500, use=6)["fragments"]), len(approved))

    def test_draw_carries_voice_source_and_colophon(self):
        d = self.draw()
        self.assertEqual(d["voice"], "Plain.")
        self.assertEqual(d["source"]["url"], "u")
        self.assertEqual(d["colophon"]["assembled_line"], "Assembled from the words of Nobody, 13 October 2026.")
        self.assertEqual(d["colophon"]["source_line"], "Source: Sample Verses (Project Gutenberg 99).")

    def test_rotation(self):
        settings = {"rotation": ["dickinson", "poe"], "rotation_epoch": "2026-10-13"}
        self.assertEqual(deal.poet_for_date(date(2026, 10, 13), settings), "dickinson")
        self.assertEqual(deal.poet_for_date(date(2026, 10, 14), settings), "poe")
        self.assertEqual(deal.poet_for_date(date(2026, 10, 15), settings), "dickinson")
        self.assertEqual(deal.poet_for_date(date(2026, 10, 12), settings), "poe")

    def fixed_draw(self):
        return {"poet": "sample", "use": 4,
                "fragments": [{"text": "pallid bust", "type": "pair"}, {"text": "lantern", "type": "word"},
                              {"text": "frost", "type": "word"}, {"text": "bee", "type": "word"},
                              {"text": "i", "type": "word"}, {"text": "sleeps", "type": "word"}],
                "glue": ["the", "a", "and", "of", "in", "to", "my", "you", "I", "is"]}

    def test_check_accepts_a_legal_poem(self):
        poem = "The pallid bust, a lantern:\nFrost and I.\n"
        r = deal.check(self.fixed_draw(), poem)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["fragments_used"], 4)
        self.assertEqual(sorted(r["glue_used"]), ["a", "and", "the"])

    def test_check_resolves_glue_versus_fragment_ambiguity(self):
        # "i" is both a dealt fragment and a glue word; two uses need one of each.
        poem = "I, the lantern; I, a frost; my bee."
        r = deal.check(self.fixed_draw(), poem)
        self.assertTrue(r["ok"], r)

    def test_check_rejects_invented_word(self):
        r = deal.check(self.fixed_draw(), "The pallid bust, a lantern, my frost, of moon.")
        self.assertFalse(r["ok"])
        self.assertIn("moon", r["problems"][0])

    def test_check_rejects_glue_reuse(self):
        r = deal.check(self.fixed_draw(), "The lantern and a frost and my bee and pallid bust")
        self.assertFalse(r["ok"])
        self.assertIn("and", r["problems"][0])

    def test_check_rejects_broken_pair(self):
        r = deal.check(self.fixed_draw(), "pallid\nbust lantern frost bee")
        self.assertFalse(r["ok"])

    def test_check_rejects_wrong_fragment_count(self):
        r = deal.check(self.fixed_draw(), "lantern frost bee")
        self.assertFalse(r["ok"])
        self.assertIn("exactly 4", r["problems"][0])

    def test_check_rejects_changed_word_form(self):
        r = deal.check(self.fixed_draw(), "The lanterns, a frost, my bee, of pallid bust")
        self.assertFalse(r["ok"])
        self.assertIn("lanterns", r["problems"][0])

    def test_cli_round_trip(self):
        env = dict(os.environ)
        with tempfile.TemporaryDirectory() as d:
            draw_path = Path(d) / "draw.json"
            poem_path = Path(d) / "poem.txt"
            draw_path.write_text(json.dumps(self.fixed_draw()))
            poem_path.write_text("The pallid bust, a lantern:\nFrost and I.\n")
            r = subprocess.run([sys.executable, str(ROOT / "scripts" / "deal.py"), "check",
                                "--draw", str(draw_path), "--poem", str(poem_path)],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(json.loads(r.stdout)["ok"])


class StyleTests(unittest.TestCase):
    def test_no_em_dashes_anywhere(self):
        """Avalynn's rule: no em dashes in anything we write."""
        offenders = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "sources" in path.parts:
                continue
            if path.suffix not in {".py", ".md", ".json", ".html", ".txt", ".yml", ".yaml"}:
                continue
            if path == Path(__file__):
                continue
            if "—" in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
