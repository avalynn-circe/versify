# Versify

A Claude skill that composes one short poem a day from the vocabulary of a
public-domain poet. Launch poets: Emily Dickinson and Edgar Allan Poe.

The idea comes from Poet Laureate, a poetry board game by Avalynn Circe:
take everything a poet ever wrote, break it into single words and small
word pairs, and arrange those fragments into something new. The curated
word bank and the constraints do the creative heavy lifting.

Versify is the daily, digital form of that. A script deals fragments at
random (seeded by poet and date, so each day has one draw), Claude arranges
exactly sixteen of them plus a few glue words into a poem, and a checker
proves nothing was invented.

Everything is Python standard library. There is nothing to install.

## Layout

```
SKILL.md              what Claude follows to produce the daily poem
README.md             this file
data/
  settings.json       draw size, required fragment count, poet rotation
  glue-words.json     the glue set (articles and pronouns), spent once each
  function-words.json grammar words: reviewed by hand, never half of a pair
  poets/
    <poet>.meta.json  name, exact source edition and URL, display color
    <poet>.json       the built bank (only approved fragments)
review/
  <poet>.json         the review file: every candidate and its decision
scripts/
  ingest.py           raw Gutenberg text -> clean verse lines
  propose.py          clean verse -> candidate words and pairs for review
  review.py           local review tool (serves review.html, autosaves)
  review.html         the review page
  build_bank.py       approved review file -> data/poets/<poet>.json
  deal.py             random draws, poet rotation, poem checker
sources/
  raw/                Gutenberg downloads (git-ignored)
  clean/              ingest output (git-ignored)
tests/                python -m unittest discover -s tests
```

## Adding a poet

No code changes. Four steps and one evening of review.

1. **Get the text.** Download the plain-text Project Gutenberg edition to
   `sources/raw/<poet>.txt`. Use Gutenberg editions only. Copyright note
   for Dickinson: the 1890s Todd and Higginson editions on Gutenberg are
   public domain; the Johnson (1955) and Franklin (1998) editions are not
   and must never be used.

2. **Ingest.**

   ```bash
   python scripts/ingest.py sources/raw/poe.txt -o sources/clean/poe.txt
   ```

   This strips the Gutenberg header, footer and license, all-caps title
   lines, roman numeral poem numbers, bracketed notes, and collapses blank
   lines so stanza breaks survive. Then look at the cleaned file. Every
   edition is laid out differently. Trim what is left with flags:
   `--start REGEX` drops everything before the first match (an editor's
   introduction), `--end REGEX` drops everything from the first match
   onward (an index), and `--drop REGEX` (repeatable) drops matching lines.
   Only verse should remain.

3. **Propose and review.**

   ```bash
   python scripts/propose.py poe
   python scripts/review.py poe
   ```

   `propose.py` tokenizes the verse (lowercase, apostrophes and hyphens kept
   inside words), counts the vocabulary, and proposes pairs: adjacent words
   within a single line, both non-function words, seen at least twice, with
   a pointwise mutual information score above the threshold. Nothing longer
   than two words is ever proposed. Single words start as approved, except
   function words, which start as pending. Pairs start as pending.

   `review.py` opens a local page. Every action saves to `review/<poet>.json`
   immediately. Keys: `j`/`k` move, `a` approve, `r` reject, `p` back to
   pending, `s` split a pair (rejects the pair, approves both words), `m`
   merge two words into a pair (the tool reports whether they are ever
   adjacent in the source), `u` undo, `A`/`R` approve or reject everything
   currently shown, `1`/`2` switch between pairs and words, `/` search.
   Suggested order: pairs first (that is where the judgment goes), then the
   pending function words, then skim the approved words high-frequency first
   and bulk-reject anything that is not a word.

   Re-running `propose.py` later is safe: every decision carries over,
   manual merges survive, and candidates that no longer appear are marked
   stale rather than deleted.

4. **Build the bank.** Write `data/poets/<poet>.meta.json` (copy an existing
   one: id, name, color, and the source title, edition and URL), then:

   ```bash
   python scripts/build_bank.py poe
   python scripts/deal.py poets
   ```

   Add the poet id to `rotation` in `data/settings.json` to put them in the
   daily cycle.

## Launch poet recipes

The exact commands used for the two launch poets, so a re-run is one copy
and paste. Both raw files are the Plain Text UTF-8 downloads from the
URLs in `data/poets/<poet>.meta.json`, saved as `sources/raw/<id>.txt`.

Dickinson (Gutenberg 12242). One cut removes each series' front matter,
the three editors' prefaces and the transcriber's note, and ends at the
first poem of each series:

```bash
python scripts/ingest.py sources/raw/12242.txt -o sources/clean/dickinson.txt \
  --cut '^POEMS$' '^(I\. LIFE\.|\s+This is my letter to the world)'
```

Poe (Gutenberg 10031). The window starts after Ingram's memoir and ends
before the prose poems and essays. Cuts remove Poe's own preface, the four
notes sections, the verse drama Politian (speaker labels and stage
directions would pollute the bank; it can be added back later), and the
prose letter that introduces the 1831 poems:

```bash
python scripts/ingest.py sources/raw/10031.txt -o sources/clean/poe.txt \
  --start '^\s*POEMS OF LATER LIFE\s*$' \
  --end '^\s*PROSE POEMS\.\s*$' \
  --cut '^PREFACE\.$' '^THE RAVEN\.$' \
  --cut '^NOTES\.$' '^\s*(POEMS OF MANHOOD|AN UNPUBLISHED DRAMA|DOUBTFUL POEMS|PROSE POEMS)\.?\s*$' \
  --cut '^\s*AN UNPUBLISHED DRAMA\.?\s*$' '^\s*POEMS OF YOUTH\s*$' \
  --cut '^INTRODUCTION TO POEMS\.--1831\.$' '^SONNET--TO SCIENCE\.$'
```

Then `python scripts/propose.py dickinson` and `python scripts/propose.py poe`.

## Dealing

```bash
python scripts/deal.py today                       # today's poet and draw
python scripts/deal.py draw --poet dickinson       # one poet
python scripts/deal.py draw --poet poe --date 2026-11-01 --format text
python scripts/deal.py check --draw draw.json --poem poem.txt
```

The seed is derived from the poet and the date, so a day's draw is the same
everywhere. `--seed N` overrides it. A draw never repeats a fragment.
Fragments are weighted by log frequency by default (`--weight uniform` or
`--weight freq` to change), so the words a poet returns to appear often and
the one-off oddities still turn up.

`check` tokenizes the poem with the same tokenizer the bank was built with
and searches for an assignment of every poem word to a dealt fragment or a
glue word. Pairs must be intact, in order, on one line. It fails on any word
outside the draw, any glue word spent twice, or the wrong number of
fragments. Claude runs it before presenting a poem.

## Daily delivery

The skill does not fire on its own. For a poem every morning, create a
Routine in claude.ai that runs daily, checks out this repository, and sends
the prompt "Run Versify for today and deliver the poem", with push or email
notifications on. The SKILL.md has a section on running unattended.

## Settings

`data/settings.json`: `draw` fragments dealt (24), `use` fragments the poem
must contain (16), `weight`, `rotation` and `rotation_epoch` (the date on
which the first poet in the rotation is up), and the pair thresholds.

`data/glue-words.json`: the glue set. `free` words (articles and the
smallest connectives) are unlimited. `once` words (pronouns, not, but)
may be spent once each; list one twice to allow it twice. `min_lines`
and `max_lines` in settings bound the poem. One fragment may repeat as
a refrain when both uses end a line.

## Style rule

No em dashes anywhere, in code, comments, docs or poems. The test suite
checks the repository for them.

## Tests

```bash
python -m unittest discover -s tests
```

## Out of scope for now

No MCP server or hosted backend. No printable card PDF for the board game,
though the bank format is kept simple enough that a print-layout script can
reuse it later. No marketplace packaging yet.
