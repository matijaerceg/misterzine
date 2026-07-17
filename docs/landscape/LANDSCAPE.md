# The MiSTer Hardware Landscape — data spec

This folder is the third misterzine channel: a hand-curated map of every way to
own a MiSTer. Nothing here is scraped or automated. Updates happen in normal
Claude sessions by editing `hardware.json` only; the page (`index.html` in
this folder, one self-contained vanilla-JS file like the other two surfaces)
renders entirely from that file, so adding/editing hardware never touches
layout code. The interview questions also live in `hardware.json` (an
`interview` key: answers carry `require` any-of token groups, `effort`
allowlists, or a `budget` cap), and options carry an `effort` grade
(`none | some | diy`) the build question filters on.

Nav name: **Landscape**. Page title: "The MiSTer FPGA Hardware Landscape" (user added FPGA 2026-07-16). Header: MiSTerZine wordmark top-left links home; the freshness chip (meta.updated) IS the whole subtitle (scope sentence removed, user ruling 2026-07-16); pills + theme toggle stay pinned top-right at every width; the zero state shows no fit-count line.
URL: `/landscape/`. Outward copy may say "landscape" or "hardware matrix" —
never "release tracker" (that term belongs to the releases page).

## Design doctrine (agreed 2026-07-16, do not silently reverse)

- The unit is a **purchasable starting point**, not a chip. A bare MiSTer Pi
  and a kit containing one are different options in different lanes.
- Lanes = **assembly effort** (turnkey -> kit -> DIY -> special -> horizon).
  Display type, Y/C, SNAC, budget are cross-cutting filters, never lanes.
- Zero state is **neutral fact only** — no badges, no opinions. Opinion
  (verdicts, "most popular") appears only downstream of visitor answers.
- Complete-setup price is fact, not opinion: computed as option price plus
  its `to_complete` parts. Sticker price alone is a half-truth; never show it
  without the complete figure.
- Capabilities are **paths, not booleans**. "Y/C out" resolves to
  built-in / possible-with-listed-parts(+cost) / no-path. Never a bare check.
- Filtered-out options are **grayed with a stated reason**, never hidden.
- Every fact cell carries a `verified: YYYY-MM` stamp. Prefer "unverified"
  over marketing claims. No live prices — typical USD street, revisited on
  quarterly sweeps.
- `status: announced` items render visibly non-orderable. Discontinued items
  stay in the file with `status: discontinued` (spatial permanence).

## User taste rulings (2026-07-16 review round - do not silently reverse)

- **No Permanent Marker on this page.** Titles are Roboto Condensed 700
  (`.cd`), body is Roboto. (Marker stays a zine/releases brand element.)
- **No budget question.** Price is visible on every card and guides the
  verdict ranking; it is not a filter. Rejected as a main filter by the user.
- **No per-question microcopy.** Questions stand alone; the `why` field was
  removed from the interview schema.
- **Option names include the maker** the way people say them ("MiSTer Addons
  Skeleton Kit"); cards show no separate vendor line (the sheet keeps the
  `vendor` field).
- **Display question is multi-select** (labels: HDMI / RGB - Component /
  S-Video - Composite); every selected output must be satisfiable.
- **Availability is a factor**: options carry `stock`
  (`now | waves | scarce | na`) rendered as a card line, plus a
  single-toggle "Want it soon?" question (ONE checkbox-style answer, user
  ruling 2026-07-16) requiring `now`. Stock drifts fast - re-verify on
  every sweep.
- **Dead ends are loud**: any answer that leaves zero fits shows a warning
  verdict box IMMEDIATELY (whatever the answer count), naming horizon items
  that would fit ("It exists, but only on the horizon: ...").
- **Announced items get slim rows**, not full cards (horizon lane renders
  compact); status tags sit in the card flow, never overlapping the name.
- **Lane zoom is animated** (FLIP, transform-only, ~220ms, no rotation, runs
  under prefers-reduced-motion per the site's standing rationale); the sheet
  gets a 150ms fade/scale-in. Verified by sampling transforms per frame.
- **Discontinued/cancelled items never render "price TBA"**: `price_usd` on
  a dead product means its last known price, shown as "was $X"; null hides
  the price line entirely (user ruling 2026-07-16).
- **Open-source-only hardware stays within existing lanes, no new lane**:
  Multisystem1 (discontinued as a product, buildable from open files) lives
  in special builds with its story in the notes. A dedicated "open-source
  DIY fabrication" lane was considered and scoped out 2026-07-16 - the
  audience is overwhelmed newcomers, not PCB fabricators; revisit only if
  several such entries accumulate.
- **MiSTer Pi bundle tiers are NOT separate cards** (ruling 2026-07-16):
  bundles of the same board + parts you still assemble are price points of
  one starting point, listed in the option's notes. Contrast: a factory-
  ASSEMBLED build (qmtech-assembled) is its own kits-lane card because the
  effort grade differs.
- Options carry `img: "<option-id>.png"` pointing into docs/landscape/img/.
  The user sources the images himself (alpha-transparent PNGs, ~160px on the
  long side is plenty; card slot renders 52px contain-fit). A missing file
  self-removes and is remembered (NOPIC) so re-renders fire no repeat 404s -
  dropping a correctly named PNG into the folder is the entire workflow, no
  code or data change.

## Page UX (agreed 2026-07-16, before any page code exists)

The page mimics an expert being asked "which MiSTer should I buy": the
poster is the expert's mental map, the interview prunes it.

- **Poster**: all lanes visible at once. Semantic zoom in DISCRETE levels
  (landscape -> lane -> card spec sheet), never continuous free pan/zoom.
  Each zoom level is a legible, linkable layout. Transitions must work as
  instant cuts (user's OS runs prefers-reduced-motion).
- **Interview**: persistent side rail on desktop, questions answerable in
  any order, each with an "I don't know" that never prunes, plus microcopy
  on why the question matters. Mobile: rail collapses to sticky removable
  chips ("CRT - S-video x") over a vertical lane scroll.
- **Pruning**: gray, never hide or shrink; every grayed card carries its
  rule-out reason. Spatial permanence: the landscape never rearranges.
- **Verdict**: top pick + runner-up + one-line why, rendered only after
  ~3 answered questions. Before that, only a neutral count survives.
- **Every state is a URL** (answers as query params) — veterans answer
  "which MiSTer?" threads with a link that opens the pre-pruned map.
- `provides_unverified` renders hedged; low-confidence prices render hedged.

## hardware.json schema (v1)

Top-level keys:

- `meta` — `{schema, updated, currency}`. Bump `updated` on every edit.
- `capabilities` — vocabulary of tokens used in `provides`/`requires`.
  `{id: {name, explain}}`. Add a token here before using it anywhere.
- `lanes` — ordered `[{id, name, tagline}]`.
- `parts` — `{id: {name, vendor, price_usd, provides[], requires[], notes,
  verified, sources[]}}`. A part is addable to an option when its `requires`
  tokens are all present in the option's *effective* provides (built-in plus
  included parts, transitively). This is how chains work: an active Y/C
  adapter `requires: [yc-source]`; the analog I/O board `provides: [yc-source]`
  but `requires: [gpio-header]`; boards provide `gpio-header`. The renderer
  computes the closure — parts and options stay independent to edit.
- `options` — the starting points. `[{id, lane, name, vendor, price_usd,
  status, provides[], includes[], to_complete[], notes, verified, sources[]}]`
  - `status`: `orderable | preorder | announced | discontinued | cancelled`.
    "Sells in batches, sold out between them" is `orderable` + a note, not
    a status.
  - `provides`: capability tokens built into the product itself
  - `provides_unverified` (optional): tokens the vendor/press claim but no
    teardown or review confirms. Render visibly hedged, never as plain fact.
  - `includes`: ids physically in the box — part ids OR option ids (kits
    contain boards). Their provides count as built-in; never restate them
    in `provides`.
  - `url`: the official product page, rendered as the "vendor - official
    page" link at the top of the spec sheet. `null` when no stable official
    page exists (QMTech's AliExpress store URL is volatile; announced items
    often have none) - never substitute a review or a reseller.
  - `to_complete`: part ids still needed for a minimal working setup
    (PSU, SD card, controller — and SDRAM for bare boards: a board that
    can't run popular cores is not complete). Complete price = price_usd
    + these.

Field conventions (parts and options both):
  - `price_usd`: number, `[low, high]` range (vendor/batch spread), or
    `null` (= unknown; never guess). EUR-sourced prices are converted
    approximately and say so in notes.
  - `confidence`: `high | medium | low` — high means a vendor/official page
    was fetched directly; medium reviewer-sourced; low snippet/commodity
    estimate. Render low-confidence prices hedged.
- `appendix_not_mister` — `[{name, one_liner, sources[]}]`. The "looks like
  MiSTer, isn't" fence. Keep each to one honest line.

## Known modeling limitation (schema v1)

The chain closure treats an included option's sockets as free. In reality a
kit's own board can occupy the GPIO stack (e.g. iCode's digital-I/O build,
MiSTercade), so a "possible with parts" answer for such kits may mean
"replace a board", not "add one". The renderer must phrase with-parts
answers for kit-lane options as advisory. Proper fix if it ever matters:
a `consumes` field on parts/options that removes socket tokens.

After ANY edit to hardware.json, run the validator (JSON parse + token/id
integrity + chain reachability):

    python validate_landscape.py docs/landscape/hardware.json

## Research access

When WebFetch 403s a source (retrorgb.com, misterfpga.org, aliexpress.com
all do), fetch it through a real browser instead:
`python tools/fetch_page.py <url> [needle]` - Playwright Chromium from this
machine's IP, verified working on all three 2026-07-16. Reddit refuses even
this (blocks headless traffic); don't burn time on it. AliExpress shows
CAD prices from this location - convert and date-stamp.

## Editing recipe for future sessions

1. Read this file fully. 2. Edit `hardware.json` only. 3. New capability?
Define the token in `capabilities` first. 4. Stamp every touched entry's
`verified` with the current YYYY-MM and add a source URL. 5. Bump
`meta.updated`. 6. Normal push policy applies (test locally, user okay).
Visitor-visible landscape changes get a CHANGELOG.md line like everything else.
