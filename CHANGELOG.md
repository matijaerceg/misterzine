# Changelog

User-visible changes to the [MiSTerZine Releases site](https://matijaerceg.github.io/misterzine/releases/).

## 2026-07-07
- New opt-in **ROM Name** column showing each arcade title's MAME setname (searchable too), plus click-to-copy ROM name and core name in the detail panel.
- The browser Back button (and swipe-back gesture) now closes the screenshot panel on mobile instead of leaving the site.
- Visual polish: the panel's resize grip is now two crisp pixel-perfect lines, and the panel drop shadow is gone.

## 2026-07-06
- New opt-in **Genre** column for arcade titles (via MAME's catver.ini).
- Arcade rows not yet in the MiSTer Arcade Database now show provisional Rotation/Players/Controls values in gray (sourced from MAME 2003-plus), replaced automatically once verified data lands.
- Brand-new arcade titles get their Year, Manufacturer, and Genre filled from the MAME DAT on the day they appear, instead of showing up blank.
- Screenshot frames now use the Arcade Database's rotation data to pick the right aspect (horizontal vs vertical) automatically.
- Removed a duplicate NeoGeo Pocket row (Jotego lists the handheld under Arcade too).
- Visual polish: Core column in full text color, repo links tinted with the site's blue accent.

## 2026-07-05
- The selected row stays centered in view whenever a filter or sort reshuffles the table.

## 2026-07-04
- Release data now updates **twice a day** (was once).
- Date columns sort newest-first on the first click; rows with blank dates always sort to the bottom.
- Added a **Traffic Stats** link in the header to the site's public analytics dashboard.

## 2026-07-03
- **Type anywhere to filter**: stray keystrokes go straight into the search box — no need to click it first.
- The **Title column stays pinned** to the left edge when scrolling wide tables horizontally.
- App-shell layout: the page itself never scrolls; the table is the single scroll surface with truly sticky headers.
- Self-hosted fonts (Roboto + Roboto Condensed); condensed type for the data columns keeps more on screen.
- Esc now clears an active search filter first; a second Esc closes the screenshot panel.
- MiSTerZine branding, faded logo behind the empty panel, and SEO-friendly page titles.
- Added privacy-friendly visitor analytics (GoatCounter).

## 2026-07-02
- New **opt-in arcade metadata columns** from the MiSTer Arcade Database: Resolution, Rotation, Players, Controls, Flip.
- The Type filter is now a **multi-select dropdown** (pick any combination of Console/Computer/Arcade/etc.).
- **Every column is toggleable** via the Columns dropdown.
- Every row's Core name now **links to its GitHub repository**.
- Flip column distinguishes an explicit "No" from simply-unverified (blank).

## 2026-07-01
- **Patreon-gated Jotego beta cores are excluded** from the index until they graduate to public release.
- Title sorting is now case-insensitive.
- Batch of screenshot corrections: wrong-game matches fixed (Omega, Cobra-Command, Bank Panic) and a dozen square-raster horizontal games pinned to their correct 4:3 aspect.

## 2026-06-30
- **Click-to-open detail panel with arcade screenshots** — self-hosted at native resolution, resizable by dragging its edge, flick left (or Esc) to close, arrow keys to walk rows.
- Theme toggle: auto / light / dark.
- Friendly core names, colored type badges, and a new **Core** column showing the underlying FPGA core.
- Site renamed to **"MiSTer FPGA Core & Arcade Index"**.
- "Last updated" stamp under the title (shown in your local timezone), bumped only when data actually changes.
- Search and filter controls stick to the top alongside the header.
- New arcade titles get screenshots auto-backfilled from libretro in the daily update.
- Corrected Jotego core dates that were inflated by their Feb-2023 monorepo migration.

## 2026-06-29
- **Site launched** at `/releases`: a sortable index of every MiSTer console, computer, and utility core plus every arcade title, with release dates, original hardware years, manufacturers, and genres.
- Hand-verified debut dates for cores whose repo history couldn't be trusted; corrected 18 inflated core dates.
- Default sort: newest releases first.
