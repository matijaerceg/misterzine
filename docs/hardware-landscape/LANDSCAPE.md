# The MiSTer Hardware Landscape — data spec

This folder is the third misterzine channel: a hand-curated map of every way to
own a MiSTer. Nothing here is scraped or automated. Updates happen in normal
Claude sessions by editing `hardware.json` only; the page (`index.html` in
this folder, one self-contained vanilla-JS file like the other two surfaces)
renders entirely from that file, so adding/editing hardware never touches
layout code. The interview questions also live in `hardware.json` (an
`interview` key: answers carry `require` any-of token groups, `effort`
allowlists, or a `budget` cap), and options carry an `effort` grade
(`none | some | diy`) the build question filters on. A question may carry
`when: {q, any[]}` - it only renders (and its answer only applies) while
one of the named answers to the referenced question is picked; unchecking
the trigger silently drops the gated answer everywhere including the URL.
Validator-checked. CURRENTLY UNUSED: built for a 24-bit color-depth
question that the user retired the same day (2026-07-17, "overkill" -
depth is discovered while browsing entries instead); the mechanism stays
for future gated questions.

Nav name: **Hardware** (was "Landscape" until 2026-07-17, when the site-wide nav became Zine / Cores / Hardware). Page title: "The MiSTer FPGA Hardware Landscape" (user added FPGA 2026-07-16). Header: MiSTerZine wordmark top-left links home; the freshness stamp (meta.updated, plain muted text, NOT a chip) IS the whole subtitle (scope sentence removed 2026-07-16, de-chipped 2026-07-17); pills + theme toggle stay pinned top-right at every width; the zero state shows no fit-count line.
URL: `/hardware-landscape/` (renamed from `/landscape/` on 2026-07-17; a
redirect stub stays at `/landscape/`). Outward copy may say "landscape" or
"hardware matrix" — never "release tracker" (that term belongs to the
releases page).

## Page structure (restructured 2026-07-16, user's design)

Four lanes: **Consoles** (custom-shell machines, "starting at" pricing,
variants in the panel) - **Ready-built kits** (standard modular stack,
assembled; checkmark-or-priced-add-on per answered question) - **Do It
Yourself** (rendered as COLUMNS: Mainboards | I/O boards | USB | Adapters -
the columns ARE the anatomy lesson; parts carry `category: io|hub|adapter`
and get their own small sheets at `#p-<id>`; answers HIGHLIGHT the parts a
build would use; each mainboard needing RAM carries "+ 128MB RAM stick"
INSIDE ITS TITLE (muted suffix - beta feedback 2026-07-17: the DE10
needing RAM must be unmissable), no RAM column) - **On the horizon**. The Special builds lane is GONE:
ironclad-dx and mistercade-lite are IO-column parts now (the JAMMA/cab
answer resolves as a parts chain), multisystem1 lives in Consoles as a
discontinued row. Once any answer exists, entries that do not fit collapse
to slim reasoned rows in every lane (gray-never-hide, evolved). No
clickable configurator - configurations are IMPLIED educationally (user
ruling; revisit only if he asks).

**Vendor exclusion (user, personal, 2026-07-16): Antonio Villena products
are NOT listed anywhere on the landscape. Do not add them on any sweep.**

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
  (`now | waves | scarce | unconfirmed | na`) rendered as a card line,
  plus a single-toggle availability question (ONE checkbox-style answer,
  user ruling 2026-07-16) requiring `now`. Stock drifts fast - re-verify
  on every sweep. `unconfirmed` (added 2026-07-17, beta feedback) means
  sold out with NO announced restock (the MiSTer Pi): it renders a
  warn-colored "restock unconfirmed" FACT tag even at the zero state,
  and the card stays a full card until an answer prunes it.
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
- **MiSTer Pi bundles ARE a kits-lane card** (user reversal 2026-07-17,
  beta round; supersedes the 2026-07-16 not-separate-cards ruling): ONE
  entry (mister-pi-turbo, Turbo Pack as the face) with Mega/RAM tiers as
  negative-delta variants, effort `some` (light assembly - the kits lane
  tolerates this one non-assembled member by explicit user request). The
  bare board keeps its own DIY-lane card; both wear the restock tag.
  Still never split tiers into separate cards.
- Options carry `img: "<option-id>.png"` pointing into docs/hardware-landscape/img/.
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

- `meta` — `{schema, updated, reviewed, currency}`. Bump `updated` on EVERY
  edit; bump `reviewed` ONLY after a full sweep that re-verifies prices and
  stock (2026-07-21, user-ordered recency honesty). The freshness stamp and
  subtitle read `reviewed` - a copy edit must never make the data look
  fresher than it is.
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
    + these. May also name an OPTION id (Ironclad DX needs a whole board).
  - `what` (REQUIRED): one plain-language identity sentence. The first
    thing a newcomer reads on the sheet.
  - `advice` (REQUIRED): the expert's orientation. TONE RULE (user,
    2026-07-16): popularity and fit, never put-downs — "most commonly
    recommended", "the pick if you want X" are the register; no
    pooh-poohing any product or brand. Factual trade-offs allowed.
    May point across lanes ("the kits lane is this stack pre-built").
  - `variants` (optional): first-party configurations,
    `[{id, name, price_delta, adds[], note}]`. Rendered as chain-style
    answers ("Fits with: the Analogue version (+$50)") and a Versions
    line on the sheet. Use when a configuration changes capabilities or
    price meaningfully; NEVER split an option into multiple cards for
    SKU differences (ruling 2026-07-16 — the noob decision is which
    product, not which SKU). Variant tokens beat parts chains in the
    requirement check (buying the right version beats bolting on parts).
    `price_delta` MAY BE NEGATIVE for a cheaper stripped trim: when one
    trim has strictly more capability, model THAT as the base (per the
    ecosystem ruling) and the stripped one as a negative-delta variant
    with empty `adds` (precedent: Multisystem2 Analogue base, "Digital
    version -$50"). The renderer prints "-$X" for negative deltas.

Sheet structure (redesigned 2026-07-16 for newcomers — the sheet is an
ONBOARDING view, not a data dump): photo, price, `what`, generated
"To get playing" sentence (from to_complete, plus a CRT-budget line when
Y/C needs parts), `advice`, Versions line, capability chips, then
everything else (research notes, unverified flags, chains, sources,
confidence) behind a collapsed disclosure labeled **"Full specs, part
paths and sources (N)"** with a source count, styled as an accent CTA
button (user asked for more call-to-action 2026-07-17; earlier label
"Specs and sources" was too quiet, and "The fine print" was rejected
before that — not a contract). Still boots collapsed.
Sheet capability chips are BUTTONS (2026-07-21, user-approved): tap
toggles the chip's explain in a muted .capex line under the chip row
(title tooltips are hover-only and the audience does not know the
jargon). Card chips stay spans - a card is itself a button and buttons
cannot nest. Part sheets have no chips; unchanged.

Interview/rail rulings (user, 2026-07-16 overhaul round):
- Verdict + tally render BELOW the questions. Nothing that appears on
  answering may push the questions down - no layout shift above the
  interaction point.
- Questions are flat in the rail (no per-question card boxes).
- Multi-select questions AND single-answer toggles render as literal
  checkboxes (accent-colored native inputs); only mutually-exclusive
  choices are buttons.
- Price display: ONE headline number - the complete price, which includes
  whatever the visitor's answers require. Device/sticker price and
  availability follow muted on one secondary line (availability ranks
  below price but stays visible). Never show "range + from-X-complete"
  side by side.
- Cards explain themselves per answered question: one line per answered
  requirement, labeled with the ANSWER'S OWN WORDS ("S-Video / Composite:
  built in" / "with parts (~$27)" / "with the Analogue version (+$50)" /
  "claimed by vendor, unverified").

Reddit research (WORKING since 2026-07-16): `tools/reddit_search.py` -
official API with the user's own keys from `.secrets/reddit.json` in the
MAIN checkout ({"client_id": "...", "client_secret": ""} - empty secret =
installed-app grant, which is what the user has). NEVER commit or echo the
keys. Usage: `python tools/reddit_search.py "query" [--sub X --limit N
--sort new]` for search, `--comments POST_ID` for a thread. r/MiSTerFPGA
is dense with owner reports - it corrected the SSOne DIN10 story
(Saturn PINOUT, round-plug aftermarket cables fit, OEM keyed shells do
not) on day one. Prefer this over the --headed browser hack.

Field conventions (parts and options both):
  - `price_usd`: number, `[low, high]` range (vendor/batch spread), or
    `null` (= unknown; never guess). EUR-sourced prices are converted
    approximately and say so in notes.
  - `confidence`: `high | medium | low` — high means a vendor/official page
    was fetched directly; medium reviewer-sourced; low snippet/commodity
    estimate. Render low-confidence prices hedged.
- `appendix_not_mister` — `[{name, one_liner, sources[]}]`. The "looks like
  MiSTer, isn't" fence. Keep each to one honest line.

## Card + rail rendering rules (2026-07-17 round, all shipped - do not
## silently reverse)

- **Prices sit at the BOTTOM of every card** in every lane: one scan line
  across the page. Order inside a card: status tag, photo, name, capability
  chips, per-answer lines, RAM reminder, then complete price + muted
  availability line. NO device price on cards and NO price on the RAM
  reminder line (user: too much text; the sheet keeps the device price).
- **Recommendation stickers are REMOVED FOR GOOD** (user, 2026-07-17
  evening, reversing the same-day sticker approval): "cheapest fit" /
  "community favorite" / "cheap and in stock" were judged not neutral
  enough for a page that also warns how uneven non-official hardware can
  be. The `popular` data field is gone too. Differentiation is carried by
  the tag line, per-answer lines, prices and the official-design mark.
  Do not re-propose computed or editorial recommendation badges. (The
  FACT tags - status, "restock unconfirmed", "official design" - are a
  different thing and stay.)
- **The rail is 16.5rem wide** (narrowed from 19.5, user 2026-07-17: the
  CTA banner read wider than any answer).
- **On phones the interview is OPT-IN** (user 2026-07-17): the railfold
  boots CLOSED on <=52rem viewports so the poster comes first and "Find
  my MiSTer" invites - UNLESS the URL carries answers (a shared pre-pruned
  link keeps the fold open so the pruning is explained). Desktop is
  untouched. "(Optional)" copy in the CTA was considered and rejected as
  form-speak - do not add it.
- **One gray language**: dimmed pcards match the mini grayed cards (dashed
  hairline, page bg, .45 text). colsdim dims only the column headers -
  the cards inside carry their own dim/mini styling. Mini cards are
  COMPACT CARDS (column layout, card bones), not bare text rows - a
  discontinued console must still read as a card (user, 2026-07-17).
- **Lanes are visible BANDS**: each lane section gets a tinted rounded
  band (surface/bg mix + rule border) so the lanes read as lanes.
- **Lane subtitles are user copy** (2026-07-17): Consoles "Plug and play;
  less open ecosystem." / Kits "Standard MiSTer sandwiches, assembled.
  Play today, but easy to tinker and swap parts later." / DIY "Pick a
  mainboard, add what you need, put it together yourself."
- **The rail CTA is a BANNER**: a full-rail-width accent-tinted box with
  CSS-drawn down-arrows flanking "Your requirements here". NO tilt on the
  text (user ruling 2026-07-17). The plain-ASCII rule governs copy, not
  CSS decoration.
- **The freshness stamp is plain muted text** under the title, not a chip
  (user ruling 2026-07-17).
- **Availability is IMPLIED, never asserted**: all stock copy is an
  impression ("tends to sell out between batches", "usually in stock") and
  the footer tells visitors to check the shop themselves before counting
  on stock.
- **Visitors are assumed to own a USB controller**: no option lists
  usb-controller in to_complete (the part stays as a reference record);
  one footer sentence states the assumption.
- **Shelf and cabinet are INVERSE filters**: shelf dims JAMMA gear; the
  cabinet answer dims every io-category board that does NOT provide jamma
  (a required-token highlight beats the dim). (2026-07-17)
- **DIY card prices NEVER absorb answer-driven chain costs**: a mainboard
  card shows board + its own essentials (`baseLo`), full stop - the
  per-answer line carries the chain cost ("with parts (~$275)"). A QMTech
  jumping to $423 on the cab answer read as "QMTech sells JAMMA gear"
  (user, 2026-07-17). Consoles/kits keep answer-inclusive complete prices -
  that IS their meaning.
- **The controllers question never says SNAC**: label "Plug in original
  console controllers", short "Original controllers" - the jargon appears
  only in results/parts (user, 2026-07-17).
- **The region question (id `region`) NEVER prunes** - it annotates. Every
  orderable option carries `ships_from: us|eu|cn|tw` (validator-checked);
  answering paints "ships from X" on each card, green "- your region" on
  matches, muted otherwise. Import friction is the visitor's own algebra;
  the sheet's vendor line states origin permanently. The silence/fanless
  question was considered and REJECTED (user 2026-07-17: "no solution is
  that loud") - don't re-propose.
- **The adapters column is grouped by subheads**: parts carry
  `subcat: video|input|other`, rendered as Video / Controllers / Extras.
  New adapter parts must set subcat (default bucket is Extras).
- **`design: "official"` (option AND part field, beta feedback
  2026-07-17)**: marks the Terasic reference board and boards built to
  the MiSTer project's own published designs - the guarantee boundary
  cores are developed against. Renders as an ok-colored "official design"
  tag on cards/pcards; a footer legend explains it and tells readers
  everything unmarked is third-party (DYOR). Marked DELIBERATELY
  NARROWLY: de10-nano, io-analog (v6/9.2 class), sdram-128. Things the
  community trusts but that are NOT project designs (MiSTer Pi board,
  IO Analog Pro, MikeS11 adapters, USB hub) stay unmarked - diluting the
  marker kills it. A DE10-vs-clones sub-grouping of the mainboard column
  was considered and NOT done: three boards, and the marker communicates
  lineage without re-architecture.
  2026-07-21 (user-approved): the footer legend gained one factual
  sentence - core devs build/test on official designs, bugs appearing
  only on other boards may go unfixed, some devs decline such reports.
  This is the WHOLE dev-support caveat: a per-entry warning badge on
  third-party boards was considered and rejected (would invert/dilute
  the official marker and collide with the no-editorial-badges ruling).
- **QMTech mixed-vendor caveat (researched 2026-07-17)**: the Discord
  claim "QMTech boards don't work with normal IO boards" is NOT fully
  true (Irken Labs ran third-party JAMMA/JVS expanders on one), but
  dual-RAM setups, the mirrored RAM header, and QMTech-IO-on-other-boards
  are real traps - notes carry the nuance; gpio-header was NOT stripped
  from qmtech-cv. Revisit only with new owner reports.
- **`tag` (option field, 2026-07-17)**: the glance-level positioning line
  rendered in muted italics under the card name ("The value pick") -
  community perception in one phrase, distinct from the sheet's `what`.
  User-approved slate on consoles/kits/mainboards; ghosts and horizon
  entries carry none. "Premium" belongs to MiSTer Addons (boards +
  support reputation), NOT to the priciest kit - RetroCastle's tag is
  about completeness ("The fully loaded import"), a user correction.
- **Lane names render in the accent color** (structure, not decoration -
  the agreed one-notch answer to "more color?"). Card titles stay fg.
- **Chain tie-break**: equal-price chains prefer the one with fewer
  sells-out parts (the in-stock JAMMIX must beat the equal-priced
  MiSTercade when both provide jamma).
- **Layout: 88rem page cap + 15rem card minimum + .6rem lane gutter**
  (2026-07-17): extra width goes into wider cards and roomier DIY
  columns, never into extra grid columns.
- **JAMMA update**: jammix added as a second io-column JAMMA part
  (~$275 board at Ultimate MiSTer, in stock; kits EUR499.90+ WITHOUT
  the DE10). RetroCastle's old JAMMA kit is delisted everywhere
  (their store + CastleMania both empty 2026-07-17) - noted in the
  jammix entry, do not resurrect without a live listing.
- **Built-in per-answer lines collapse to one "Covers: X, Y" line**; costed
  paths and overridden lines stay separate.
- **`line_overrides`** (option field): `{token: "text"}` replaces the
  "built in" line for a token the option provides - e.g. the SuperStation
  One's snac override "built in (PS1 ports); others via the SuperDock +
  adapter" (r/MiSTerFPGA 1obnro9 / 1q53mss / 1tjuym2: unit SNAC is
  PS1-ports-only, USB ports carry no SNAC; the dock adds the SNAC port).
  Validator checks the keys are capability tokens.
- **"To get playing" sentences never end "and you are playing"** (the
  prefix already says it); options with an empty to_complete get "Nothing
  else to buy - it plays out of the box."
- **Sheet "Specs and sources" stays COLLAPSED** (user agreed 2026-07-17;
  default-open was considered and dropped).
- RULING: variant-beats-cheaper-chain confirmed for consoles - the buyer
  of a less-open ecosystem wants the ecosystem version, not a dongle
  (MS2 RGB = Analogue version, never a Direct Video dongle).
- Data facts landed 2026-07-17: iCode digital + Analog builds as variants
  (both in stock, SD preloaded 64GB-1TB, 256GB anchors $459.95/$479.95);
  QMTech assembled includes its 32GB card; Multisystem2 ships with NO SD
  card and NO PSU (Heber's own "Extras you will need" list) - both are in
  its to_complete now. RetroCastle per-variant contents fully verified via
  the CDP sweep (256GB SD + case in every kit, USB-C power, no hub/PSU;
  $517/$527/$527/$624). QMTech AliExpress listings browser-verified:
  assembled base ~C$274 (~$200), bare-board SKUs ~C$141-266 (~$105-195).
- **Multisystem2 deep-verify (2026-07-17, RetroRGB scope test + Ken's
  teardown + Heber listings)**: remodeled with the ANALOGUE trim as base
  ($285) and "Digital version -$50" as variant - the Digital drops analog
  video, Ethernet, optical/3.5mm audio AND the cartridge bay (no SNAC).
  HD15 RGB scope-verified excellent (R2R ladder DAC); the Genesis-2-style
  mini-DIN is dim (100mV low, sync on composite pin only, csync unwired,
  no composite circuit) - steer people to HD15-to-SCART; YPbPr sync is a
  low 44mV. New part ms2-svideo-cart (Heber Super Video Custard, ~$47,
  in stock): the in-ecosystem composite/S-Video route via ms2-slot.
  MikeS11-on-HD15 still untested (Discord question outstanding). Both MS2
  versions support Direct Video via external HDMI DAC (vendor-stated), so
  the dongle chain shown on cards is legitimate. Mini cards now render a
  small dimmed thumbnail (ghosts included).
- **SSOne Y/C settled 2026-07-17**: Ken's teardown (YouTube transcript
  scrape) - ADV7125 DAC, LMH6722 buffer, 3x THS7374 on ALL analog outs,
  Sony CXA2075M alternate encoder via DIP3. yc-active-filtered moved from
  provides_unverified to provides. QMTech V2.1 + MikeS11: one Discord
  owner says it works, but iffy-IO-board reports pending the owner's own
  investigation - noted, not yet modeled as verified.
- **Clone sweep (2026-07-17)**: hamgeek-mister added to the kits lane -
  the QMTech-design "clone of a clone" sold assembled on AliExpress
  (~$155, SD included, PSU-swap advice, early RAM issues fixed with free
  replacement boards per core dev, misterfpga.org t=10139; optical audio
  hedged). No other unlisted DE10-Nano clones exist: every no-name
  AliExpress "MiSTer" checked is the QMTech/Hamgeek family. Tang-based
  partial ports (MiSTeryNano) and DECA/SoCkit ports are NOT clones and
  stay off the map.
- **JAMMA landscape (swept 2026-07-17)**: ms2-arcade added as a turnkey
  PREORDER entry (Heber Multisystem2 Arcade, GBP215 ex VAT ~ $280, ships
  from Aug 2026 - the first turnkey JAMMA MiSTer). Budget alternatives
  exist but are NOTES ONLY on mistercade-lite, not paths: the QMTech
  AliExpress JAMMA conversion board (~C$27, 3 sold, owner-reported P1
  input bugs, r/MiSTerFPGA 1pfrd5i) and JammASD V3 (EUR65.90, PC-to-JAMMA
  via VGA+USB, no hardware-verified MiSTer report found). Too thinly
  attested to enter the chain solver - revisit if reports accumulate.
  (Heber's MultiPi JAMMA is Raspberry-Pi-based, not FPGA - ignore.)
  2026-07-21 (user-approved): a "Community tip" sentence on BOTH JAMMA
  I/O parts (mistercade-lite, jammix) notes the non-JAMMA cab route -
  hand-wire cab controls to GP2040-CE USB encoders + regular analog I/O
  for video; more work, fits any cabinet. Notes-only per the
  budget-alternatives precedent, never a chain path.
- **Analog color depth axis (2026-07-17, reader-prompted)**: classic
  v6-class ladder I/O boards are 18-bit (6 bits/channel, GPIO-pinout
  limit - misterfpga t=6531); Sorg's 2024 redesign added true 24-bit
  (IO Analog Pro is its first store build, RetroRGB scope-verified
  June 2024; A/V Pro 9.2 same generation, vendor-stated ADV7125).
  Direct Video + any HDMI DAC = 24-bit from any unit, clones included.
  QMTech/Hamgeek analog path: community-reported 18-bit (r/MiSTerFPGA
  1u2gv60) vs a listing-claimed 24-bit VGA DAC - modeled as UNVERIFIED
  both ways, don't resolve without a teardown or scope test. Only
  24-bit cores (PSX/N64/Saturn-class) can show the difference; say so
  wherever the axis is raised. Notes carry this on hamgeek-mister,
  qmtech-assembled, io-analog, io-analog-pro, direct-video-dac.
  NOW MODELED as capability token `analog-24bit` (chips on lane-zoom
  cards and sheets carry it; the `what` copy on io-analog/io-analog-pro
  states the 18/24 split). A gated `depth` interview question was built,
  shipped to staging and RETIRED the same day (user 2026-07-17:
  "overkill" - people see the depth as they browse entries; don't
  re-add). Granting policy (user-tuned 2026-07-17): citing a solid
  source is enough for plain `provides` - scope tests (io-analog-pro),
  framework docs (direct-video-dac, reflex-prism), vendor-documented
  DACs (ironclad-dx, mistercade-lite, ultimate-mister-pro +
  mister-pi-turbo via their A/V Pro 9.2), teardown-verified chip
  (superstation-one). The `provides_unverified` hedge marks DISPUTES,
  not the absence of a lab test: qmtech-assembled keeps it (listing
  says 24-bit, owners report the QMTech/Hamgeek path as 18-bit).
  io-analog spans both generations so gets NO token (its `what` carries
  the split); hamgeek gets none (vendor claims nothing). Mainboards
  correctly have nothing to do with depth - it is the I/O board's or
  dongle's property.

## Chain-honesty rules (overnight audit 2026-07-17)

- **I/O-class parts (category io) only chain onto DIY mainboards.** An
  assembled kit's GPIO stack is occupied; "add a MiSTercade to your Armor
  bundle" would mean gutting the kit, so it renders as no-path, matching
  the sealed products. This resolves the socket-occupancy limitation for
  the io category specifically.
- **Chains leaning on a part that itself sells out say so**: "with parts
  (~$50, sells out)" - driven by the part's optional `stock` field (the
  SuperDock case).
- **The dead-end banner names near-misses that failed only on
  availability** ("Would fit, but sells out between batches: ...") in
  addition to horizon matches.
- The verdict/tally stay retired; only the dead-end banner renders.
- Answers may carry `short` - the compact wording used for card info lines
  and failure reasons; `label` stays the full checkbox/radio text.
- **Sheet "Possible with parts" is DATA-DRIVEN (2026-07-17 evening)**:
  every non-internal capability in vocabulary order. A hard-coded token
  list here once silently dropped "composite via adapter" from kit
  sheets - never re-hardcode it. chainText counts `to_complete` parts
  as already owned, so "Still needed" keeps sole custody of those.
- **Direct-provider part highlight only fires for tokens some fitting
  DIY board LACKS built-in** (2026-07-17): the MiSTercade must not
  light up on the HDMI answer just because it has HDMI passthrough -
  a highlighted part must be able to be the thing delivering the
  answer.
- **sdram-128-second requires sdram128 AND sdram-slot** (2026-07-17):
  the chain only offers a second stick where a module socket exists
  (bare DIY boards); sealed consoles/kits model dual RAM as variants -
  the sheet used to offer a $20 stick on the SuperStation One.
- **Y/C active framing is COMPOSITE-centric (user fact 2026-07-17)**:
  the THS7374 filtering chiefly benefits composite (luma+chroma merge,
  dot crawl); S-Video keeps them separate and mainly gains correct
  levels. yc-active-filtered explain + yc-active copy carry this; do
  not re-frame active as "the cleanest S-Video chain".
- **io-analog-pro also provides analog-audio + toslink** (vendor page
  2026-07-17: audio over the Saturn AV port, 3.5mm jack switchable to
  SPDIF) - the Armor bundle sheet used to claim a dongle was needed
  for a headphone jack.

## Known modeling limitation (schema v1)

The chain closure treats an included option's sockets as free. In reality a
kit's own board can occupy the GPIO stack (e.g. iCode's digital-I/O build,
MiSTercade), so a "possible with parts" answer for such kits may mean
"replace a board", not "add one". The renderer must phrase with-parts
answers for kit-lane options as advisory. Proper fix if it ever matters:
a `consumes` field on parts/options that removes socket tokens.

After ANY edit to hardware.json, run the validator (JSON parse + token/id
integrity + chain reachability):

    python validate_landscape.py docs/hardware-landscape/hardware.json

## Research access

When WebFetch 403s a source (retrorgb.com, misterfpga.org, aliexpress.com
all do), fetch it through a real browser instead:
`python tools/fetch_page.py <url> [needle]` - Playwright Chromium from this
machine's IP, verified working on all three 2026-07-16. Reddit refuses even
this (blocks headless traffic); don't burn time on it. AliExpress shows
CAD prices from this location - convert and date-stamp.

For sites that block even headless-with-UA (RetroCastle is Cloudflare
"Just a moment"-walled): `--cdp` attaches to a Chrome running with
`--remote-debugging-port=9222`. NO USER ACTION NEEDED for public pages:
Claude spawns its own real Chrome on a scratch profile
(`chrome.exe --remote-debugging-port=9222 --user-data-dir=<scratchpad>\chrome-cdp-profile`
via Start-Process), fetches through it, then kills only that instance
(match on the profile path in CommandLine). Verified beating RetroCastle's
Cloudflare 2026-07-17 - the full per-variant kit sweep came through it.
A visible Chrome window appears on the user's screen while it runs; tell
him when doing it. Only login-gated pages would need HIS profile, which
requires him to relaunch his own Chrome with the flag - coordinate then.

## Editing recipe for future sessions

1. Read this file fully. 2. Edit `hardware.json` only. 3. New capability?
Define the token in `capabilities` first. 4. Stamp every touched entry's
`verified` with the current YYYY-MM and add a source URL. 5. Bump
`meta.updated`. 6. Normal push policy applies (test locally, user okay).
Visitor-visible landscape changes get a CHANGELOG.md line like everything else.

On quarterly sweeps also run `python tools/check_landscape_links.py` (from
the repo root; needs the CDP Chrome running for AliExpress/RetroCastle -
see Research access). It checks every option/part `url` for liveness AND
that the page title still matches the product. All 18 passed 2026-07-17.
