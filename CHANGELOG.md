# Changelog

User-visible changes to the [MiSTerZine Releases site](https://matijaerceg.github.io/misterzine/releases/).

## 2026-07-08
- The 56 Coin-Op Collection games now show their real FPGA core in the Core column (Jaleco Mega System 1, Nichibutsu Armed F, SNK 68000, Toaplan Zero Wing HW, …) instead of the generic "Distribution-MiSTerFPGA" repo label — their MRA files are now parsed like the other sources', which also corrected a few years/manufacturers and setnames along the way.

## 2026-07-07
- Arcade titles are now written the way humans write them, derived from the MAME database: subtitles get their colons back ("Street Fighter II: The World Warrior", "Robotron: 2084"), doubled-up alternate names collapse to the familiar one ("Pac-Man - Puck Man" → "Pac-Man", "Rush'n Attack - Green Beret" → "Rush'n Attack"), and punctuation/capitalisation follow the real marquee ("Q*bert", "SWAT", "Satan of Saturn") — 121 titles cleaned up, and the discarded alternate names remain searchable.
- Closing the detail panel now keeps the row highlighted as a "you were here" marker — handy for re-orienting after the fullscreen panel on mobile (previously the highlight was cleared, and any lingering tint was just a touch-hover accident).
- New "Report a problem" link in each detail panel that opens a GitHub issue prefilled with the entry's title/core/setname, plus a general "Report a Problem" link in the header next to the Changelog.
- The Types and Columns dropdowns now have a one-click reset ("Show all" / "Reset to default") that also puts you back on track to receive any future default-column changes; the click-to-copy buttons in the detail panel lost their border box.
- Console and computer rows now use proper human names instead of raw core filenames — Nintendo 64 (was N64), Game Boy, Master System, Mega Drive, PlayStation, Commodore 64, Acorn Archimedes, TI-99/4A, SAM Coupé, PDP-1, and ~80 more. The raw core name still shows (and is searchable) in the Core column, so "psx" or "n64" still find them.
- The two Game & Watch cores are now distinguishable: "Game & Watch (GnW)" (pierco's 2020 core) and "Game & Watch (agg23)" (the 2026 core from the Analogue Pocket project).
- Search now ignores accents ("sam coupe" finds SAM Coupé, "pokemon" finds Pokémon Mini).
- The 2-player link-cable variants (Gameboy2P, GBA2P) no longer appear as separate rows — the Game Boy and GBA rows carry a note about them instead. GameGear2P is now titled "Game Gear" (it's the only standalone Game Gear core; the 1-player version lives inside the SMS core), with notes on both it and SMS explaining the relationship.
- Fixed PDP-1 and Game of Life appearing twice: a core rebuild renames its file upstream, and the old entry was never retired. Renames are now detected and merged (keeping the original debut date).
- The detail panel shows a new **Note** row for systems that have one.
- The "deprecated" tag on the retired Genesis core moved from the Type column to sit next to its title.
- Console and computer rows now show a photo of the actual hardware at the top of the detail panel — 115 systems, from the NES and C64 to obscurities like the Galaksija, EDSAC, and Compukit UK101 — rendered in a deliberately lo-fi 16-color dithered style with a photo-credit link.
- Every row now opens the detail panel (type, dates, core, repo link, …), not just arcade titles with screenshots; the screen icon now specifically marks rows that have screenshots.
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
