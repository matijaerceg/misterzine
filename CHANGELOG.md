# Changelog

User-visible changes to the [MiSTerZine Releases site](https://matijaerceg.github.io/misterzine/releases/).

## 2026-07-08
- Every column header now explains itself on hover (what "MiSTer Debut" vs "Last Updated" vs "Original Year" actually mean).
- A search with zero results now says "No matches" (naming the query and any active type filter) instead of showing a blank table.
- Edge shadows hint that the table scrolls sideways: a fade on the right while more columns are off-screen, and a shadow under the Title column once scrolled.
- Esc now closes an open Types/Columns dropdown before it clears the search.
- **RSS feeds**: three feeds (all changes / new only / updates only) via the new "RSS" header link; readers also autodiscover them from the page URL.
- **Last Updated now means "latest shipped build"** (the dated file update_all actually downloads) instead of the repo's latest commit, which often lands before or without a shipped build. The detail panel now shows all three dates: MiSTer debut, Latest update, Latest commit.
- Table opens sorted by **Last Updated** instead of MiSTer Debut; date ties sort alphabetically.
- The sorted column's header is highlighted in the accent color; the search box turns accent-tinted while a filter is active.
- New "Public cores only" note in the header meta line (Patreon beta cores are listed once public).
- Site renamed to **"MiSTer FPGA Core & Arcade Tracker"**.
- The 56 Coin-Op Collection games now show their real FPGA core instead of the generic distribution repo label.

## 2026-07-07
- Arcade titles rewritten the way humans write them, from the MAME database: "Street Fighter II: The World Warrior", "Pac-Man" (not "Pac-Man - Puck Man"), "Q*bert". 121 titles cleaned up; discarded alternate names stay searchable.
- Console and computer rows use proper human names (Nintendo 64, PlayStation, Commodore 64, ~90 renamed); raw core names still show and search in the Core column.
- Console and computer rows show a photo of the actual hardware in the detail panel: 115 systems in a deliberately lo-fi 16-color dithered style.
- Every row now opens the detail panel, not just arcade titles; the screen icon specifically marks rows with screenshots.
- New opt-in **ROM Name** column (MAME setname, searchable), plus click-to-copy ROM/core name in the detail panel.
- New "Report a problem" link in each detail panel (prefilled GitHub issue) and in the header.
- The detail panel shows a new **Note** row for systems that have one.
- Closing the detail panel keeps the row highlighted as a "you were here" marker.
- Browser Back (and swipe-back) closes the panel on mobile instead of leaving the site.
- Search ignores accents ("sam coupe" finds SAM Coupé).
- The Types and Columns dropdowns got one-click resets.
- The two Game & Watch cores are now distinguishable: "(GnW)" vs "(agg23)".
- 2-player link-cable variants (Gameboy2P, GBA2P) folded into notes on the Game Boy/GBA rows; GameGear2P retitled "Game Gear".
- Fixed PDP-1 and Game of Life appearing twice: upstream file renames are now detected and merged, keeping the original debut date.
- The "deprecated" tag on the retired Genesis core moved next to its title.
- Visual polish: crisp pixel-perfect resize grip, panel drop shadow removed.

## 2026-07-06
- New opt-in **Genre** column for arcade titles (via MAME's catver.ini).
- Arcade rows not yet in the MiSTer Arcade Database show provisional Rotation/Players/Controls in gray (from MAME 2003-plus), replaced automatically once verified data lands.
- Brand-new arcade titles get Year/Manufacturer/Genre from the MAME DAT on day one instead of showing up blank.
- Screenshot frames pick horizontal vs vertical aspect automatically from rotation data.
- Removed a duplicate NeoGeo Pocket row (Jotego lists the handheld under Arcade too).
- Visual polish: Core column in full text color, repo links in the accent blue.

## 2026-07-05
- The selected row stays centered in view when a filter or sort reshuffles the table.

## 2026-07-04
- Release data now updates **twice a day** (was once).
- Date columns sort newest-first on the first click; blank dates always sort to the bottom.
- Added a **Traffic Stats** link to the site's public analytics dashboard.

## 2026-07-03
- **Type anywhere to filter**: stray keystrokes go straight into the search box.
- The **Title column stays pinned** left when scrolling horizontally.
- App-shell layout: the page never scrolls; the table is the single scroll surface with truly sticky headers.
- Self-hosted fonts (Roboto + Roboto Condensed); condensed type keeps more data on screen.
- Esc clears an active search first; a second Esc closes the panel.
- MiSTerZine branding and SEO-friendly page titles.
- Added privacy-friendly visitor analytics (GoatCounter).

## 2026-07-02
- New **opt-in arcade metadata columns** from the MiSTer Arcade Database: Resolution, Rotation, Players, Controls, Flip.
- The Type filter is now a **multi-select dropdown**.
- **Every column is toggleable** via the Columns dropdown.
- Every row's Core name **links to its GitHub repository**.
- Flip column distinguishes an explicit "No" from simply-unverified (blank).

## 2026-07-01
- **Patreon-gated Jotego beta cores are excluded** until they graduate to public release.
- Title sorting is now case-insensitive.
- Screenshot corrections: wrong-game matches fixed, a dozen square-raster games pinned to 4:3.

## 2026-06-30
- **Click-to-open detail panel with arcade screenshots**: self-hosted at native resolution, resizable, Esc to close, arrow keys to walk rows.
- Theme toggle: auto / light / dark.
- Friendly core names, colored type badges, and a new **Core** column.
- Site renamed to **"MiSTer FPGA Core & Arcade Index"**.
- "Last updated" stamp under the title, bumped only when data actually changes.
- Search and filter controls stick to the top.
- New arcade titles get screenshots auto-backfilled from libretro daily.
- Corrected Jotego core dates inflated by their Feb-2023 monorepo migration.

## 2026-06-29
- **Site launched** at `/releases`: a sortable index of every MiSTer console, computer, and utility core plus every arcade title, with release dates, hardware years, manufacturers, and genres.
- Hand-verified debut dates for cores whose repo history couldn't be trusted; corrected 18 inflated dates.
- Default sort: newest releases first.
