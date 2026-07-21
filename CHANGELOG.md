# Changelog

User-visible changes to the [MiSTerZine Releases site](https://misterzine.fyi/releases/).

## 2026-07-21
- Hardware landscape: capability chips on a product's spec sheet can now be tapped to show what the capability means - the explanations were previously hover-only tooltips, invisible on phones.
- Hardware landscape: the freshness stamp now separates the last full review of prices and stock from the last page edit, so an edit no longer makes the data look fresher than it is.
- Hardware landscape: the JAMMA I/O board entries (MiSTercade, JAMMIX) now carry a community tip about the alternative cabinet route - hand-wiring cab controls to GP2040-CE USB encoders with a regular analog I/O board for video.
- Hardware landscape: the footer's official-design legend now also states that core developers build and test on official-design hardware, and that bugs appearing only on other boards may go unfixed.

## 2026-07-20
- The RSS feeds now announce arcade core updates. A core shipping a new dated build without touching its .mra files was invisible to the feeds, even though the release tracker's Last Updated column showed it (reported in issue #1). Cores that serve several games announce as a single item listing them, and the past month of missed core updates was backfilled into the feeds.
- Feed cleanup: on big update days a game no longer produces one duplicate feed item per alternative version, so genuinely distinct updates are no longer pushed out of the feeds by duplicates.

## 2026-07-19
- Zine: milestone posts now read "40th anniversary" / "50th anniversary" instead of "40th decadeversary", which double-counted (a decade is ten years, so "40th decadeversary" implied 400).

## 2026-07-18
- Zine: the Atari Jaguar and Fairchild Channel F posts now show gameplay screenshots (Tempest 2000 and Maze) instead of hardware photos, and their titles name the maker so it is clear the subject is the system, not the game in the picture.
- The CRT shadow mask no longer shimmers or shows rainbow banding over screenshots and hardware photos: it was being drawn one lattice slightly too large and squeezed onto the frame, and now lands exactly on the display's pixels.
- The CRT shadow mask keeps screenshots noticeably brighter (it no longer reserves headroom that dimmed the picture ~10-18%), and its phosphor triad is now a consistent fine 1:1 pixel size on every display, including high-density phones.
- Phone header cleanup across all three pages: the Zine / Cores / Hardware nav and the theme picker now sit together on one row at the very top, at a consistent size on every page. This fixes a squeezed, one-word-per-line title on the Hardware page and a theme button that was getting cut off on small phones on the release tracker.
- Release tracker: the links under the title are shorter and now fit on one line (Info, RSS, Traffic, Changelog, Discord), and the filter buttons read Type / Genre / Year / Col. On wider screens the Info link spells itself out as "Public + JT Beta cores only" so its meaning is clear at a glance; it collapses back to "Info" on phones to keep the row on one line.
- The Hardware guide shows two cards per row on tablet-width screens, so card titles no longer overlap the product photos, and the zine's post timestamps are a touch larger.
- The CRT shadow mask over screenshots can now be turned off: a "Shadow mask" toggle sits at the bottom of the theme menu on the zine and the release tracker, and the choice is remembered across both pages.

## 2026-07-17
- Landscape: boards, kits and consoles that deliver full 24-bit analog color now carry a "24-bit analog color" capability chip (dashed with a "?" where the claim is disputed), so color depth reads at a glance while browsing.
- Landscape: spec sheets now list every capability reachable with parts (composite-via-adapter was silently missing on some kits), the collapsed specs section is a clearer call to action ("Full specs, part paths and sources" with a source count), and the copy now notes the active Y/C adapter's filtering chiefly benefits composite.
- Landscape: analog color depth is now called out where it differs - classic VGA I/O boards top out at 18-bit color, the 2024 redesign boards (IO Analog Pro, A/V Pro 9.2) and Direct Video HDMI DACs deliver full 24-bit, and the QMTech/Hamgeek clones' analog depth is flagged as an open community question. Only a few cores (PSX, N64, Saturn) can show the difference.
- The default Light and Dark themes are a touch easier on the eyes: the ink eased off pure black/white and the grounds off pure white/near-black, so both read a little softer while staying crisp and well within the site's contrast floor. The other themes are unchanged.
- The new 3DO core now fills in its details: original year (1993), manufacturer (Panasonic) and a photo of the Panasonic REAL FZ-1 in its detail panel.
- Every console, kit and mainboard card now carries a one-line character sketch under its name ("The value pick", "The default recommendation", "The fully loaded import") so first-timers can tell the options apart at a glance. Lane titles picked up the accent color, the page uses more of a wide screen with roomier cards, and the adapters got grouped subheadings.
- The JAMMIX I/O board joins the Do It Yourself columns: an in-stock route to putting a MiSTer in an arcade cabinet (or an ITX PC case), alongside the MiSTercade. Cabinet cost estimates now prefer parts you can actually order today.
- The Hamgeek MiSTer joins the kits lane: the budget factory-assembled clone (~$155 with case, analog I/O, fan and SD card). Its entry tells the whole story - the early RAM problems were fixed with free replacement boards, owners typically swap the included power supply, and cores are not built with clones as their target. New photos across the consoles and kits lanes.
- The Landscape now asks where you live: every machine's card says where it ships from, highlighted when that is your region, since shipping and import fees change the real answer. The arcade-cabinet and shelf answers now gray out each other's gear, the adapters column is grouped into Video / Controllers / Extras, and prices assume you already own a USB controller (the footer says so).
- Landscape cards got a cleanup: the price sits at the bottom of every card, recommendation badges are stickers on the card corner, lanes render as visible bands, built-in capabilities collapse to one "Covers:" line, and clutter (device prices, part prices) moved into the detail sheets. Do It Yourself mainboard prices now cover only board plus essentials; anything your answers add is priced on its own line.
- A verification sweep hardened the data: the SuperStation One's built-in S-Video is now teardown-verified as actively filtered (its "claimed, not verified" hedge is gone, and its SNAC line explains PS1 ports vs the SuperDock); the Multisystem2 listing was rebuilt around the Analogue version with the HDMI-only Digital as a cheaper variant, its weak mini-DIN flagged per scope tests, and Heber's Super Video Custard cartridge added as its S-Video route; RetroCastle kits' real box contents and prices are itemized (256GB card and case included); and the preorder Multisystem2 Arcade (JAMMA) joined the map with new photos for it, the RetroCastle kit and the original Multisystem.
- The three parts of the site now share one header nav - a single Zine / Cores / Hardware toggle - so you can jump between them from any page.
- The tracker page's heading is now "MiSTer FPGA Cores Tracker + Launcher" with the MiSTerZine wordmark beside it (matching the Hardware page's style), replacing the old address-bar-style title.
- The theme switcher is now one compact dropdown that shows the current theme; Light, Dark and all the fun themes live inside it, which tidies up the header.
- The hardware guide has a clearer home: it now lives at misterzine.fyi/hardware-landscape/ (the old /landscape/ link still works and redirects), and sharing a hardware link now shows a preview card with the title and art.

## 2026-07-16
- The Landscape reorganized around how you actually buy: Consoles, Ready-built kits, and a Do It Yourself section laid out as columns (mainboards, I/O boards, USB, adapters) so the anatomy of a build is visible at a glance. Answering questions highlights the parts your build would need, prices every entry as a complete setup, and collapses whatever no longer fits to a one-line row with the reason. Every part is clickable for its own detail sheet.
- New third section of the site: [The MiSTer Hardware Landscape](https://misterzine.fyi/landscape/) at /landscape/, a hand-verified map of every way to own a MiSTer, from turnkey consoles to bare boards. Every card shows the complete-setup price (power, storage, controller, needed parts), not the sticker price. Answer a few questions in the side rail and the map grays out what doesn't fit you, with the reason stated on each card; three answers in, it names a pick and a runner-up. The state lives in the URL, so a filtered map can be shared as a link. Vendor claims nobody has verified are marked as exactly that.
- Arcade entries now carry a "More info" link to the game's Arcade Database page (arcadeitalia.net): history, flyers, cabinet photos, manuals and videos, one click from the entry panel.
- The Core column is now headed "FPGA Core", spelling out what it lists, and an open entry says "FPGA core" to match. Narrow screens keep the shorter "Core" so the header stays on one line.
- The result tally now lives inside the search box, counting down live as you type ("2 of 1039"). When nothing is filtered it shows just the total, and the filter row gets back the space the old standalone tally took up.
- If the list fails to load (a bad connection, a mid-deploy moment), the page now says so with a "tap to retry" notice instead of sitting on a silent empty table.
- Some vertical arcade games are known to boot rotated the opposite way on MiSTer from the original cabinet, with no screen flip to correct it. Their Rotation cell now carries a small "boots CW"/"boots CCW" tag with the hardware-verified orientation (hover it, or open the entry, for the full story), and searching cw or ccw matches what the core actually boots.
- The site can now be installed as an app: Add to Home Screen on iPhone/iPad and Android, or the Install button in Chrome and Edge on desktop. Installing gives it its own icon and window, and on iPhone/iPad it also makes your favorites permanent (Safari otherwise deletes a site's saved data after 7 days without a visit).
- Every zine post footer now carries a "View [title] in the release tracker" link to the game's entry. The post title already linked there, but nothing said so; the footer link spells it out.
- Jotego's Patreon early-access cores are now listed (Sunset Riders, the Street Fighter IIIs, Turtles in Time and more), each marked with a small beta tag. Hover the tag or open the entry for the details: running one needs his Patreon beta key until it gets a public release, at which point the tag simply disappears. The footer note explains why other paywalled cores can't be listed.
- The table now keeps itself current. When new releases or builds are published, they appear in the list on their own, with a small notice at the bottom naming what landed. Nothing moves under you while you read, and a tab left open for days catches up the moment you come back to it.
- Coming back after a while, a line across the table marks everything new since your last visit, so you can see what you missed without checking dates.

## 2026-07-15
- Favorites: star any entry to keep it, from the row itself or its detail panel. The new star control beside Clear filters narrows the table to what you have saved, and its menu copies a backup link that restores your list in another browser, on your phone, or for anyone you send it to.
- Every date in the detail panel now says how long ago it was, so a game reads as 45 years old and its core as updated 2 days ago without you working it out. The release date also names itself plainly: "MiSTer debut", or "Latest build" for the rare core whose debut nobody knows.
- New releases are flagged for four weeks instead of one, with a NEW badge that fades as the release ages. Hover it to see exactly how old the release is.
- The zine now writes itself: posts are researched, verified and published automatically four times a day. Every quote is still checked word for word against its source before a post goes live.
- Six new color themes join Light and Dark, picked from a new Theme menu in the top-right toggle: MiSTer-y (deep indigo and mauve), Vaporwave, Ice Cream, Pastel, Pink and Unit-01. Your pick follows you across the zine and the release tracker, and Light/Dark look exactly as before.
- Six more themes, all borrowed from the hardware: Phosphor (a green CRT), Game Boy (the four-shade LCD), ZX Spectrum (the bright colors on black), Workbench (Amiga blue and orange), C64 (the two VIC-II blues) and Riso (newsprint with two spot inks).
- Three more: Amber (the orange terminal), Famicom (the console shell's cream, crimson and gold) and Virtual Boy (red LEDs on black). Every theme in the menu now shows two little dots of its palette next to its name.

## 2026-07-14
- Copying from the detail panel is easier: click anywhere on a field to copy it, not just the small icon. That covers the core name, the ROM name and the ZapScript token, and the game's title now copies a link to its entry. The RSS popover's feed rows work the same way. A "Copied" tag appears next to the icon to confirm, instead of the icon briefly turning into a tick.
- Hover the logo on the zine home page and mister-kun, the MiSTer mascot, leans out from behind it to see who is there. He ducks back when you move away.

## 2026-07-13
- The colour theme toggle is now just Light and Dark (the Auto option is gone), and new visitors start in dark mode. If you already picked a theme, that choice is kept.
- The Core Type column now shows an icon instead of a word: a joystick for arcade, a gamepad for console, a monitor for computer and a box for anything else. The colour coding is unchanged, hovering a row's icon still names its type, and searching for "arcade", "console" or "computer" works as before.
- The detail panel now shows a ZapScript field for cores and arcade games, with a copy button: it copies the Zaparoo ZapScript token for that title so you can write it to an NFC tag or add it to a playlist and launch the game by tapping.
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
