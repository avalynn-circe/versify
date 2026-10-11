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

1. **Deal.** From the repository root, run the dealer as one plain
   command (no redirection or chaining; `--out` writes the file):

   ```bash
   python3 scripts/deal.py today --format json --out /tmp/versify-draw.json
   ```

   Use `draw --poet poe` (or
   `dickinson`) instead of `today` only when the user names a poet. Add
   `--date YYYY-MM-DD` to replay another day's draw. Read the printed JSON:
   `fragments` (each with `text` and `type`), `glue` (`free` and `once`),
   `use` (how many distinct fragments the poem must contain, normally 16),
   `lines`, `voice`, `rules` and `colophon`.

2. **Compose.** Write a poem using exactly `use` of the dealt fragments.
   The hard rules, which the checker enforces:
   - Exactly `use` distinct fragments. A `pair` fragment stays together,
     in order, on one line, and counts as one.
   - One refrain is allowed: a single fragment may appear twice if both
     appearances end a line. Any other repeat is a violation.
   - Glue comes in two kinds, listed in the draw. `free` glue (articles
     and the smallest connectives) is unlimited, so the poem can be
     grammatical English; use as much as the sentences need. `once` glue
     (I, you, my, not, but) may be spent one time each, because those
     words set the poem's stance and that stance should come from the
     fragments.
   - Nothing else. No word outside the draw and the glue, and no change
     of form: if the bank dealt "soul" you may not write "souls".
   - Between the line counts the draw gives in `lines`, normally four to
     eight. Fewer gets dense, more gets thin.
   - The last word of the poem is a fragment, and it should be a noun or
     a verb: a thing or an act, never a modifier and never glue.
   - Line breaks, capitalization and punctuation are free. No em dashes,
     even for Dickinson; a line break or a comma does that work.
   - No title. The colophon after the poem is the only heading.

   How to arrange the words. These are what separate a poem from a pile
   of interesting words, so follow them in order:

   a. **Find the poem before writing it.** Read the whole draw twice. Pick
      the two or three fragments that make one image together. That image
      is the subject, and every line serves it. Half the draw is meant to
      be left out; choosing what to leave out is most of the craft.
   b. **Count the verbs.** The draw usually holds only a few. Plan each
      line around one. A line with no verb is a list; allow at most one
      such line, as the opening or the close.
   c. **Plain grammar.** Every line must read as English a stranger could
      paraphrase. If you cannot say in prose what a line means, it is
      word salad: cut it or rebuild it. Free glue is there so every line
      can be a sentence or a clear phrase; "the" and "and" cost nothing,
      so never write "heads in row" when you mean "heads in a row". Do
      not invert word order to sound antique.
   d. **One gesture per line,** two to six words. Each line adds one
      image, one turn, or one claim. Do not stack three adjectives.
   e. **Use the pairs.** They are phrases the poet actually wrote, and
      they usually carry the poem's music.
   f. **Build toward the ending.** The last line is the shortest and the
      most concrete. End on a thing or an act, never on an abstraction.
   g. **Read the voice note** in the draw and lean into it. It describes
      how this poet's lines move.
   h. **Do not use a rare word because it was dealt.** Use it because the
      poem needs it. "Subterfuge" and "acknowledgment" are in the bank;
      most days they should stay there.
   i. **Revise once.** After the checker passes, read the poem aloud. Cut
      the weakest line, rebuild to the required count, and check again.

   Two arrangements of one past Dickinson draw, which held, among others:
   mists, morns, scarlet, auburn, breezes, cold, water, heads, row, year's,
   electricity, ceded, firmaments, taste, good-by, shame, subterfuge,
   ballot, docile, supple, and the pair "slow slow".

   Word salad (rare words for their own sake, no subject, the fourth line
   cannot be paraphrased):

   ```
   Mists, docile;
   morns a supple scarlet.
   I stole the year's electricity
   and ceded my shame to battles.
   Auburn heads in row:
   taste good-by.
   ```

   A poem (one image, autumn dawn; plain grammar with free glue doing the
   joining; the pair used whole; a short concrete ending). It is an
   illustration of the method, not a template: never reuse its lines or
   its shape, even on a day that deals some of the same words:

   ```
   The mists were scarlet,
   the morns auburn and cold.
   The breezes, slow, slow,
   bear the year's electricity
   to the firmaments.
   I stole a taste of the water.
   Good-by.
   ```

3. **Verify.** Save the poem to `/tmp/versify-poem.txt` with your file
   writing tool (not a shell heredoc), then run the checker, again as one
   bare command:

   ```bash
   python3 scripts/deal.py check --draw /tmp/versify-draw.json --poem /tmp/versify-poem.txt
   ```

   It exits 0 and prints `"ok": true` when the poem is legal. If it fails
   it names the problem (an invented word, a glue word spent twice, a pair
   broken, the wrong fragment count). Fix the poem and check again. Never
   present a poem the checker has not passed. If three revisions still
   fail, say so plainly and show the checker's output instead of the poem.

4. **Present.** Output exactly this shape, nothing more:

   ```
   <poem, as written>

   Assembled from the words of Emily Dickinson, 14 October 2026.
   Source: Poems by Emily Dickinson, Three Series, Complete (Project Gutenberg 12242).
   ```

   Both lines after the poem come verbatim from the draw's `colophon`
   (`assembled_line` and `source_line`). Copy them; do not reword them.

   Do not explain the poem, do not rate it, do not list the fragments or
   the glue, and do not add a greeting or a sign-off. The poem is the
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
