---
name: versify
description: Composes the day's Versify poem, a short poem built only from fragments of a public-domain poet's own vocabulary (Emily Dickinson, Edgar Allan Poe) dealt at random by a script, plus a tiny fixed set of glue words. Use this whenever the user asks for today's poem, a daily poem, a Versify poem, a Dickinson or Poe poem, a morning poem, or when a routine or scheduled task says to run Versify. Also use it if the user asks to verify, redo or explain a Versify poem, or asks which poet is up today.
---

# Versify

Versify makes one small poem a day out of a dead poet's own words. A script
deals a handful of fragments from the poet's vocabulary (single words and a
few two-word phrases the poet actually wrote together). You arrange exactly
sixteen of them, with up to ten glue words, into a poem. Nothing else goes
in. The constraint is the whole point: the vocabulary carries the poet's
voice, and the arrangement is yours.

All randomness comes from `scripts/deal.py`. Never pick fragments yourself
and never guess what the bank contains; the dealer is deterministic per
poet per day, so the same day always yields the same draw.

## Steps

1. **Deal.** From the skill directory run:

   ```bash
   python scripts/deal.py today --format json > /tmp/versify-draw.json
   ```

   Use `draw --poet poe` (or `dickinson`) instead of `today` only when the
   user names a poet. Add `--date YYYY-MM-DD` to replay another day's draw.
   Read the JSON: `fragments` (each with `text` and `type`), `glue`, `use`
   (how many fragments the poem must contain, normally 16), and `rules`.

2. **Compose.** Write a poem using exactly `use` of the dealt fragments.
   The rules, in full:
   - Each fragment at most once. A `pair` fragment stays together, in
     order, on one line. It counts as one fragment.
   - Each glue word may be spent once. You need not spend any.
   - Nothing else. No word outside the draw and the glue, and no change
     of form: if the bank dealt "soul" you may not write "souls".
   - Line breaks, capitalization and punctuation are free. Use them.
   - No title. The poet and date are the only heading.

   Take the draw seriously as material rather than as an obstacle. Read
   the fragments a few times before writing. Pairs are often the spine of
   the poem; the oddest single word is often the ending. Short lines are
   fine. Fragments can be stretched across many lines or packed tightly.

3. **Verify.** Save the poem to a file and run the checker:

   ```bash
   python scripts/deal.py check --draw /tmp/versify-draw.json --poem /tmp/versify-poem.txt
   ```

   It exits 0 and prints `"ok": true` when the poem is legal. If it fails
   it names the problem (an invented word, a glue word spent twice, a pair
   broken, the wrong fragment count). Fix the poem and check again. Never
   present a poem the checker has not passed. If three revisions still
   fail, say so plainly and show the checker's output instead of the poem.

4. **Present.** Output exactly this shape, nothing more:

   ```
   <poem, as written>

   Emily Dickinson, 14 October 2026
   sixteen of her words, glued with: the, a, of
   ```

   The second line names the poet and the date from the draw. The third
   lists the glue actually spent, in the order used, or reads
   "no glue" if none was. Use "her words" for Dickinson, "his words" for
   Poe, and "their words" for any poet whose pronouns you do not know.

   Do not explain the poem, do not rate it, do not list the unused
   fragments, and do not add a greeting or a sign-off. The poem is the
   message. If the user then wants to talk about it, talk.

## When running from a routine

A scheduled routine may invoke this skill with no human present. Follow the
same four steps and make the presented poem the whole of your final
message, since that message is what gets delivered by push or email. Do
not ask questions; if something is broken (no bank for today's poet, the
checker will not pass), deliver one plain sentence saying what failed.

## Tone

Warm and quiet. This is a small daily gift, not a performance. Never quote
real lines or whole poems from the source poet; the fragments are the only
borrowing allowed, and the poem must be new.

## Files

- `scripts/deal.py` deals, lists poets, and checks poems. Run it with `-h`.
- `data/poets/<poet>.json` are the word banks. `data/glue-words.json` is
  the glue set. `data/settings.json` holds the draw size, the required
  fragment count and the poet rotation.
- `README.md` explains how a bank is built and how to add a poet. Only
  read it if the user asks about the pipeline.
