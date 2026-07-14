# Changelog

User-visible changes to the [MiSTerZine Releases site](https://misterzine.fyi/releases/).

## 2026-07-13
- Fixed screenshots for two arcade games: Adventure Canoe, which previously had none, now shows gameplay shots, and Tecmo World Cup '98's corrupt title screen was removed (its gameplay shots remain).
- Arcade entries now show their Region (World, Japan, USA and so on), sourced from the MiSTer Arcade Database: it appears in the detail panel, is searchable, and there is a matching opt-in Region column you can turn on from the Columns menu. It reflects the region of the mainline set that is listed.
- The footer note now reads "Public cores only, no alternatives" and its popover explains that each arcade game is listed once, as its mainline version, with regional and revision variants, clones and bootlegs folded into that one row.
- MiSTerZine now has its own domain: the site lives at misterzine.fyi. The old github.io address still works and redirects here.
- If you have saved more than one MiSTer, the detail panel's Launch button now shows one button per device side by side, so you can start a game on either MiSTer with a single click.
- You can now filter the table by arcade genre: a new Genre menu (next to Types and Year) lets you check off Shooter, Platform, Fighter and the rest. Selecting a genre hides consoles and computers, which have no genre.
- A single Clear filters button now clears every active filter (search, Types, Genres, Year) at once, and filters reset when you reload the page so you always start from the full list (your chosen columns are still remembered).
- Titles that debuted on MiSTer within the last week now show a NEW badge.

## 2026-07-12
- You can now filter the release table by original release year: a new Year menu with From and To pickers, plus one-tap decade shortcuts (70s, 80s, 90s...). Consoles and computers with no listed year are hidden while a year range is active.
- The zine is now a collection of quotes: each post pairs a short title with a passage quoted verbatim from a linked source (interviews, reviews, retro-gaming sites) instead of our own write-up.

## 2026-07-11
- **The site root is now a daily zine**: short, source-checked tidbits about newly released MiSTer cores (and decade anniversaries of old favorites), written automatically from cited sources. Has its own RSS feed (feed-zine.xml); the zine and the release index link to each other.
- Screenshots now render through a CRT shadow mask, drawn at your display's native pixel grid so it stays crisp at any scale, phones included.
- Every entry's detail panel now shows its Source: which downloader database delivers it (MiSTer Distribution, Jotego, or Coin-Op Collection), and searching "jotego" or "coin-op" filters to that provider's games.
- Multi-monitor games now render at true cabinet width (triple screen = three 4:3 displays), show a "Screens" row in the panel, and turn up when searching "dual screen" or "triple screen".

## 2026-07-10
- **Launch games on your MiSTer from this page**: every entry's detail panel now has a Launch button (arcade games start the actual game, console/computer entries load the core). Needs wizzo's Remote script running on the MiSTer and a browser on the same network.
- Search now treats each word as its own filter: "horizontal 4-way" finds entries matching both terms, in any order, across any field.

## 2026-07-08
- **Every entry now has a shareable link** (e.g. releases/#dmnfrnt opens Demon Front's panel): row clicks update the URL, and a button in the panel copies it.
- **RSS feeds**: three feeds (all changes / new only / updates only) via the "RSS" header link; readers also autodiscover them from the page URL.
- **Last Updated now means "latest shipped build"** (the dated file update_all actually downloads) instead of the repo's latest commit. The detail panel shows all three dates: MiSTer debut, Latest update, Latest commit.

## 2026-07-07
- Arcade, console and computer rows now use human-readable names ("Street Fighter II: The World Warrior", "Pac-Man", "Nintendo 64"); the raw core and discarded alternate names stay searchable.
- Console and computer rows show a photo of the actual hardware in the detail panel.
- Every row now opens a detail panel, not just arcade titles.
- New opt-in **ROM Name** column (MAME setname, searchable).

## 2026-07-06
- New opt-in **Genre** column for arcade titles.
- Arcade rows not yet in the MiSTer Arcade Database show provisional Rotation/Players/Controls in gray, replaced automatically once verified data lands.

## 2026-07-03
- **Type anywhere to filter**: stray keystrokes go straight into the search box.
- The **Title column stays pinned** left when scrolling horizontally.

## 2026-07-02
- New **opt-in arcade metadata columns** from the MiSTer Arcade Database: Resolution, Rotation, Players, Controls, Flip.
- The Type filter is now a **multi-select dropdown**.
- **Every column is toggleable** via the Columns dropdown.
- Every row's Core name **links to its GitHub repository**.

## 2026-07-01
- **Patreon-gated Jotego beta cores are excluded** until they graduate to public release.

## 2026-06-30
- **Click-to-open detail panel with arcade screenshots**: self-hosted at native resolution, resizable, Esc to close, arrow keys to walk rows.
- Theme toggle: auto / light / dark.
- Friendly core names, colored type badges, and a new **Core** column.

## 2026-06-29
- **Site launched** at `/releases`: a sortable index of every MiSTer console, computer, and utility core plus every arcade title, with release dates, hardware years, manufacturers, and genres.
