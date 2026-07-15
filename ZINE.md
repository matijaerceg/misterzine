# MiSTerZine: how to make a post

This is the spec for the daily zine at https://misterzine.fyi/. It is written for
whoever or whatever is making the post, human or automated, starting from zero
context. Read all of it before writing anything.

The posts live in `docs/zine.json`, the single source of truth. The site root
`docs/index.html` renders them client-side; it is hand-maintained presentation
and a post never touches it. `docs/feed-zine.xml` is GENERATED from zine.json
by `python misterzine.py zine`; never edit it by hand. (Nothing in
`misterzine.py` may write index.html itself; see the note in `cmd_export_web`.)

Making a post means: add one object to zine.json, add one image, run
`python misterzine.py zine`, push to the `zine-inbox` branch. That is all.
The details are in "The post data" and "Publishing" below.

## The run (step by step, for the automated publisher)

Publish exactly ONE post per run, or skip loudly. Never end a run silently.

1. Read the rest of this file in full before anything else.
2. Read `docs/zine.json`. It is the published record: every existing post is
   an object with id `YYYYMMDD-<k>`. This tells you what is already covered,
   which quotes and images are already used, and the exact shape of a post
   object. Candidate data lives in `docs/releases/data.json`.
3. Pick a candidate using the hooks and variety rules below.
4. Research the candidate with WebSearch and WebFetch. Every fact must come
   from text you fetched this run; never write a fact from memory. Choose
   quotes per "Writing the post" below.
5. Verify mechanically. Save each fetched source's text to a file and check
   with Python or grep that every quoted span in your draft is an exact
   character-for-character substring of the source. A failed check means fix
   the quote to the source's exact text or drop the candidate. Never ship an
   unverified quote.
6. Get the screenshot per "The screenshot" below: an image the site has never
   shown, correct display aspect (mind non-square pixels), native pixels,
   saved to `docs/images/zine/`. You may pip install pillow for conversion.
   If you cannot get a confident image, drop the candidate.
7. Write the post object per "The post data" below, run
   `python misterzine.py zine`, fix anything it flags until clean, then walk
   the "Before you publish" checklist line by line. Use `date -u` for the
   real current UTC time; post ids and timestamps are UTC.
8. Publish per "Publishing" below: commit ONLY `docs/zine.json`,
   `docs/feed-zine.xml`, and the new image, with a short imperative subject
   like `Zine: <Game Name>`. Never add any AI attribution, co-author trailer,
   or "Generated with" line anywhere. Push to `zine-inbox`, NEVER to main.

If a candidate fails at any step, move to the next candidate. If no candidate
ships, publish nothing and report the skip per "When you cannot" at the end of
this file. Do not edit ZINE.md. Touch nothing else in the repo, no matter what
you notice.

## The one rule

**Nothing here is our own writing.** A post is a verbatim quote from a source,
lightly connected by factual glue, with the source linked inline. We do not
editorialize, summarize creatively, or write prose about games. If you find
yourself composing a sentence that makes a claim, stop: it should be a quote or
it should be cut.

This is deliberate. An earlier version of the zine tried editorial voice and it
did not work.

## Picking what to post

Take the first hook that yields a candidate:

1. **New releases.** Rows in `docs/releases/data.json` with a `date` since the
   last post. Use the row's `date` field, never an RSS pubDate (they disagree).
2. **On-this-day core debut.** A core whose debut date is today's day and month
   in an earlier year.
3. **The decade vault.** A game whose `year` is a multiple of 10 years ago
   (1976, 1986, 1996, 2006, 2016 for a 2026 post).

Then apply all of these:

- **Do not cover a game twice within a few weeks.** `docs/zine.json` is the
  record: every post has `id: "YYYYMMDD-<k>"` where `<k>` is the row's key. Read
  it first. After a few weeks a game may come round again, but a repeat must
  have a genuinely **different focus**: a different fact, a different angle, a
  new quote, a new screenshot. A repeat that retells the same story is a
  duplicate, not a post.
- **Never re-quote a passage** already used in any earlier post, however long
  ago.
- **Vary the core type.** Console and computer cores are first-class, not arcade
  leftovers. Every post from launch until 2026-07-14 was arcade; the first
  computer post (Apple Lisa) was better for the variety, not worse.
- **Vary the subject.** Rotate the kind of story: hardware oddity, regional
  censorship, development story, port legacy, core implementation, design
  oddity, cultural footnote, reception.
- **Watch the manufacturer.** The 2026 release wave is heavily Data East.
  Prefer a non-DE core when the choice is close, and avoid the same
  manufacturer or platform family two posts running (two Apple machines
  back to back reads like a theme week nobody announced).
- **Never inflate recency.** Do not let a displayed date drift to make an old
  thing look new.

## Writing the post

**Every quote must be verbatim.** Not paraphrased, not tidied, not
"[sic]"-corrected. Before publishing, check each quoted span is an exact
substring of the fetched source text. If a quote does not match, the post does
not ship. This check is mechanical and it is not optional.

**Never re-punctuate a quote.** If a passage contains quotation marks of its
own, keep them exactly as the source prints them; do not convert double quotes
to single to nest them inside your own. Quote a smaller span or restructure the
glue so the nesting never arises. The substring check runs on the raw text
between your quote marks with no normalization; a check that "passes" after
smartening or swapping quote characters is a failed check.

A consequence: on sources that print curly apostrophes, curly quotes, or en
dashes (Hardcore Gaming 101 does; Wikipedia's plaintext API does not), any
span containing one of those characters cannot ship at all, because typing it
as ASCII fails the substring check and quoting it faithfully breaks the
plain-ASCII rule. Pick spans that contain none of them (they exist; hunt) and
move the apostrophe-bearing facts into your own glue. Example: quote the
single word "pronounceable" and render the title Oni - The Ninja Master
yourself in ASCII, rather than quoting the source's en-dashed title.

**Never write from memory.** Every claim traces to text you actually fetched. If
you did not fetch it, you do not know it.

**Glue is factual connective tissue only.** "Apple's 1983 Lisa", "In Gaelco's
1991 coin-op", "Of one boss:". It exists to make quotes read as prose. It never
makes a claim of its own.

**Pick the surprising thing.** Not the first paragraph. The good posts work
because the fact is genuinely odd: a robot Santa boss, a tape-loading arcade
cassette, an acronym reverse-engineered from a daughter's name. If the best you
can find is dry, skip the candidate and pick another. Failing boring is allowed
and encouraged.

**Two tests for a quote:**
- A curious 12-year-old with no retro-gaming knowledge should get it on one read.
- An expert should not be bored.

**Introduce people.** Full name plus a why-you-know-them anchor on first mention:
"Steve Wozniak (the pair later co-founded Apple)". Companies get a role word:
"game maker Atari". Never a bare surname.

**Jargon budget: one term, glossed.** Exception: vocabulary every MiSTer user
already has needs no gloss. "MiSTer", "core", "FPGA core", "arcade board" are all
fine bare. Chip names, Japanese genre terms, and scene slang (shmup, tate) are
not.

### Attribution

**Never give an impersonal aggregator a speech verb.** Wikipedia does not
"note", "write", or "say" anything: it has no editorial voice to speak with.
Write "per Wikipedia" or use a bare inline citation link with no verb.

Authored sources with a real voice keep their verbs: "writes Hardcore Gaming
101", "a 2006 review at HonestGamers". A named periodical that actually
performed the act is fine: "Japan's Game Machine listed it as the eleventh
most-successful arcade game of the month".

The source link goes **inline at the tail of the body text**, not in the footer.

### Never

- **No release-date talk in the body.** Never "is now on MiSTer", "reached the
  database on <date>", "landed yesterday". The debut date lives only in the
  title's reason or the footer. Mentioning the core as a fact is fine when the
  core IS the story ("the MiSTer core runs the dual-screen version").
- **No slop.** Banned outright: dive into, iconic, beloved, fascinating, stands
  the test of time.
- **Plain ASCII only.** No em dashes, no arrows, no fancy glyphs. Commas, colons
  and parentheses do the job.
- **Keep game and core authorship distinct.** The person who made the game in
  1989 is not the person who made the core in 2026.

## The screenshot

**Never use a shot the release index already shows.** Every arcade row may have
`title`, `snap`, and `ingame` images at `docs/images/{slot}/<img>.png`, where
`<img>` is the row's `img` field (**not** its `k` - they differ on some rows).
The post's shot must be a new one. This is journalistic, not legal: they are just
screenshots, but the reader should see something they have not seen.

Also avoid the same *scene* as an index shot, even from a different source.

**Never reuse a shot from an earlier zine post either.** Everything already used
is in `docs/images/zine/`. This matters most on a repeat: a second post about a
game the zine has covered before needs a new picture as well as a new fact.

**Sources that work:**
- **Wikipedia** article images (`prop=images`, then `prop=imageinfo` for the
  upload.wikimedia.org URL).
- **Hardcore Gaming 101** article images (`wp-content/uploads`). Exclude
  `-NxN.` size variants. Watch for sidebar thumbs belonging to other games.
- **GUIdebook** (`guidebookgallery.org`) for computer and OS screenshots. Only
  `desktop/*` and `startupshutdown/*` are full-screen; everything else in those
  galleries is a cropped UI element.

**Dead ends and traps:**
- MobyGames and arcade-history are Cloudflare 403. Do not try.
- `adb.arcadeitalia.net` media is pixel-identical to our own progettoSNAPS
  slots. Same for libretro `Named_Snaps`. Not distinct sources.
- Some HG101 captures have a decorative frame that is not part of the game's
  framebuffer (the Boogie Wings gold frame). Reject those.
- Wikipedia's "Apple Lisa Office System 3.1.png" is a mislabelled, downscaled
  copy of GUIdebook's Office System **1.0** shot. Do not use it.

**Do not resample the image.** Save native pixels. `.shot img` is stretched to
its container (`width/height:100%` with no `object-fit`), so **the container
aspect is the correction**, not the file. Cropping or rescaling only loses
detail.

**Non-square pixels are on you.** "Native resolution" assumes square pixels and
many systems do not have them. The Apple Lisa's framebuffer is 720x364, but its
pixels are 50% taller than wide, so the true picture is about 1.32:1, which is
essentially 4:3. Look up the pixel aspect and pick the container to match; do not
read the framebuffer dimensions as the display aspect.

Save to `docs/images/zine/<k>.png`.

**If you cannot find a confident image, skip the candidate and try the next
one.** If no candidate yields one, post nothing and say so. A wrong image is
worse than no post.

## The post data

New posts go at the **top of the `posts` array** in `docs/zine.json`.

**Copy the newest existing post object field for field, then swap the
content.** Do not invent fields; `python misterzine.py zine --check` rejects
unknown ones. A post looks like this (the newest one in zine.json is the
authoritative example):

```json
{
 "id": "20260715-ninjaw",
 "k": "ninjaw",
 "title": "The Ninja Warriors",
 "why": "debut",
 "debut": "2026-05-23",
 "shot": "w",
 "aspect": "864 / 224",
 "img": "ninjaw.png",
 "alt": "The Ninja Warriors screenshot: ...",
 "body": ["...one string per paragraph, ending in the inline source link..."],
 "posted": "2026-07-15T12:48:00Z"
}
```

- `id` is `YYYYMMDD-<k>` where the date matches `posted`.
- `k` is the release row's deep-link key; the title links to `releases/#<k>`.
- **`why` is exactly one reason per post.** If the game's year is an exact
  multiple of 10 years ago: `"why": "decadeversary"` plus `"nth": 30` (the
  multiple), and the MiSTer debut date appears **nowhere** in the post: the
  linked release row carries it, so no `debut` field at all. Otherwise:
  `"why": "debut"` plus `"debut": "YYYY-MM-DD"`. Never two datings on one post.
  Say **decadeversary**, never "anniversary": we only know the year, not the
  day, so "anniversary" would falsely imply we are honouring the actual date.
- **`shot`:** `h` = 4:3, `v` = tate (3:4), `w` = multi-screen (8:3). For any
  other true aspect, keep the closest class and add `"aspect": "864 / 224"`
  (the raw pixel dimensions). A tate post also sets `"tate": true`; `v` and
  `tate` go together, always both or neither.
- `img` is the bare filename under `docs/images/zine/`; never reuse an earlier
  post's filename (a repeat post gets a new image AND a new filename).
- `body` strings are HTML, but the only tag allowed is a bare
  `<a href="...">source name</a>`; no `target` or `rel` (the page adds those).
- `posted` is the moment of posting, UTC. Posts stay newest-first by `posted`.

Everything presentational is derived at render time: the `.why` span, the meta
line, relative dates, and the `hr` dividers (wide when they touch a tate post)
all come from these fields. There is no markup to write and no divider to pick.

## The feed

`docs/feed-zine.xml` is generated from zine.json. After editing zine.json run:

```
python misterzine.py zine
```

It validates every structural rule above (missing/unknown fields, id/posted
mismatch, duplicate ids, reused or missing images, non-ASCII, disallowed body
markup, ordering), canonicalizes zine.json's formatting, and rewrites the feed.
Fix what it flags and re-run until it passes; `--check` verifies without
writing. Never edit feed-zine.xml by hand and never set any timestamp in it
from the current time: the output is deliberately byte-deterministic so a
rebuild with no new post produces an identical file.

## Publishing

**Never push to main.** Commit `docs/zine.json`, the new image, and the
regenerated `docs/feed-zine.xml` (nothing else; the landing workflow refuses
other paths), then push the commit to the **`zine-inbox`** branch
(`git push --force origin HEAD:zine-inbox`; the branch is scratch, force is
fine and clears any stale leftover). The "Zine inbox" GitHub Action replays it
onto the latest main, re-validates, lands it, and deletes the branch. If
validation fails, the Action opens an issue and leaves the branch for
inspection; fix and push again.

## Before you publish

- [ ] Every quoted span is an exact substring of the fetched source, checked
      against the raw text with no punctuation normalization
- [ ] The debut date in the `.why` span and the feed title is copied from the
      row's `date` field in `docs/releases/data.json`, re-read this run. The
      date is the one span in a post that is not quoted from a fetched source,
      which makes it the easiest thing to invent; never type it from memory
- [ ] Every quote stands on its own: a reaction or punchline ships together
      with the thing it reacts to, or not at all
- [ ] The game is not already covered in `docs/zine.json`
- [ ] No quote is reused from another post
- [ ] The screenshot is not one the release index shows
- [ ] The container aspect matches the real display aspect
- [ ] No release-date talk in the body
- [ ] Plain ASCII throughout, no banned phrases
- [ ] Wikipedia has no speech verb
- [ ] `python misterzine.py zine` ran clean (it regenerates the feed) and the
      commit is pushed to `zine-inbox`, not main

## When you cannot

Skip and say so, loudly. Open a GitHub issue on matijaerceg/misterzine titled
`Zine skip: <UTC date and time>` saying what you tried and why you bailed. If
issue creation fails, append the same report to `ZINE-SKIPS.md` at the repo
root instead, commit it, and push to `zine-inbox` (the landing workflow accepts
that file). Do not lower the bar to ship something: there are four posts a day and a missed
one costs nothing, while a bad one is on the public site until someone notices.
Silence is the one thing worse than skipping, because a quiet failure looks
exactly like a quiet day.
