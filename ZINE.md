# MiSTerZine: how to make a post

This is the spec for the daily zine at https://misterzine.fyi/. It is written for
whoever or whatever is making the post, human or automated, starting from zero
context. Read all of it before writing anything.

The site root `docs/index.html` IS the zine. It is hand-maintained. Nothing in
`misterzine.py` may write it (see the note in `cmd_export_web`, which explains
why). `docs/feed-zine.xml` mirrors it and is maintained the same way.

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

- **Do not cover a game twice within a few weeks.** `docs/index.html` is the
  record: every post has `id="YYYYMMDD-<k>"` where `<k>` is the row's key. Read
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
  Prefer a non-DE core when the choice is close.
- **Never inflate recency.** Do not let a displayed date drift to make an old
  thing look new.

## Writing the post

**Every quote must be verbatim.** Not paraphrased, not tidied, not
"[sic]"-corrected. Before publishing, check each quoted span is an exact
substring of the fetched source text. If a quote does not match, the post does
not ship. This check is mechanical and it is not optional.

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

## The markup

New posts go at the **top**, immediately below `</header>`.

**Copy the newest existing post in `docs/index.html` element for element, then
swap the content.** Do not reproduce a template from this document and do not
invent markup. The post design is actively worked on and changes often: the
order of the `<h2>` and the screenshot flipped on 2026-07-14 alone. Whatever the
top post looks like right now is correct by definition; anything written down
here would be a snapshot that quietly goes stale.

The pieces a post is made of: an `<article>` with `id="YYYYMMDD-<k>"`, a
screenshot in a `.shot` div, an `<h2>` holding the game name linked to
`releases/#<k>` plus a `.why` reason span, one or more body paragraphs ending in
the inline source link, and a `.meta` line. Their arrangement is whatever the
newest post does.

**Shot class:** `h` = 4:3, `v` = tate (3:4), `w` = multi-screen (8:3). For any
other true aspect, keep the closest class and add an inline override:
`style="aspect-ratio: 864 / 224"`. A tate post also needs `class="tate"` on the
`<article>`.

**The reason span (`.why`):** if the game's year is an exact multiple of 10 years
ago, the reason is `&middot; Nth decadeversary` and the MiSTer debut moves to the
`.meta` line. Otherwise the reason is `&middot; MiSTer debut <rd>` and `.meta`
carries only the timestamp. The debut always appears somewhere.

Say **decadeversary**, never "anniversary". We only know the year, not the day,
so "anniversary" would falsely imply we are honouring the actual date.

**Relative dates are client-side.** Write the absolute date in the `.rd` span's
text as a no-JS fallback; the page renders "yesterday" or "two weeks ago" at
runtime. Never bake a relative word into the HTML.

**Dividers.** One `<hr>` after every post, including the last one before the
colophon. It is `<hr class="sq wide">` if the article immediately before or after
it has `class="tate"`, otherwise `<hr class="sq">`. Only tate articles are wide;
a `w` shot does not widen its article, so a `w` post's dividers are narrow.

## The feed

Mirror every post into `docs/feed-zine.xml` as the newest `<item>`:

```xml
<item>
<title>Apple Lisa (MiSTer debut 2026-07-13)</title>
<link>https://misterzine.fyi/?ref=rss#20260714-apple-lisa</link>
<guid isPermaLink="false">zine:20260714-apple-lisa</guid>
<pubDate>Tue, 14 Jul 2026 14:55:00 +0000</pubDate>
<description>&lt;p&gt;...the post body, escaped...&lt;/p&gt;</description>
</item>
```

The title suffix is the same reason as the `.why` span: `(MiSTer debut
YYYY-MM-DD)` or `(30th decadeversary)`. Set `<lastBuildDate>` to the newest
post's timestamp. **Never set it from the current time** - a rebuild with no new
post must produce a byte-identical file, or it creates noise commits forever.

## Before you publish

- [ ] Every quoted span is an exact substring of the fetched source
- [ ] The game is not already covered in `docs/index.html`
- [ ] No quote is reused from another post
- [ ] The screenshot is not one the release index shows
- [ ] The container aspect matches the real display aspect
- [ ] No release-date talk in the body
- [ ] Plain ASCII throughout, no banned phrases
- [ ] Wikipedia has no speech verb
- [ ] The `<hr>` before and after the new post have the right width
- [ ] `feed-zine.xml` has the item and its `lastBuildDate` is the post's own time

## When you cannot

Skip and say so, loudly. Open an issue saying what you tried and why you bailed.
Do not lower the bar to ship something: there are four posts a day and a missed
one costs nothing, while a bad one is on the public site until someone notices.
Silence is the one thing worse than skipping, because a quiet failure looks
exactly like a quiet day.
