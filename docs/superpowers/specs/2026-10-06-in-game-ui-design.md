# anvilbook in-game UI: design

## Purpose

Give the player the anvilbook views inside the game, so they do not have to switch to the browser
while they play or stand at the auction house.

Intent, as agreed:

- All the web views come into the game: the Crafts list, the Plan (as an AH shopping list), item
  tooltips, History, Sell-through, Share and Settings.
- A menu turns each part on or off.
- The crafting math runs in the game (a full Lua port), so a change applies at once.
- The game uses the app's last scan, and Auctionator's live prices when this session has them.
- Layout: one main window with the web tabs, and a shopping panel that docks beside the AH.

## Non-goals

- Sign-in, account creation and account deletion in the game. A password in SavedVariables would
  be stored as plain text on disk, and deletion cannot be undone. These stay in the browser.
- Editing the disenchant table, the skill overrides or the file paths in the game.
- History older than the last 30 scans in the game.
- Libraries such as Ace3, LibStub or LibDBIcon.

## Constraints

- A WoW addon cannot read files or use the network. The game reads addon files and SavedVariables
  only at load (`/reload` or login), and it writes SavedVariables only at logout or `/reload`.
- The game loads only the files that the `.toc` lists and that exist when the client starts.
  A file that a new addon version adds needs a client restart, not a `/reload`.
- The game's Lua is 5.1. One function holds at most about 262,000 constants, so bulk data goes in
  strings.
- The target client is WoW Forever 1.60.1 (interface 16001). The other interface numbers in the
  `.toc` keep loading, and the code checks for each API before it uses it.

## Architecture and data flow

```
 WoW client                                     anvilbook app
 Auctionator.lua (SavedVariables) ──/reload───▶ watcher imports the scan
 AnvilbookExport.lua (SavedVariables)          (recipes, bags, disenchants,
   + settings changed in game     ──/reload───▶  settings changed in game)
                                                     │
 AddOns/AnvilbookExport/AnvilbookData.lua ◀──writes──┘
        │ read at /reload
        ▼
 Addon: Lua calculator ◀── Auctionator live prices, live bags, GetMoney()
        ▼
 Window tabs, AH panel, tooltips
```

### The bridge file

The app writes `AnvilbookData.lua` into the installed addon folder. It writes the file when its
content changes: after an import, after a settings change, after the game saves a new export, and
when the app starts. The addon ships an empty copy (`AnvilbookData = nil`), because the game loads
only files that exist at client start.

If the addon folder is a symlink (a developer setup), the app still writes the file. The
developer marks the tracked empty copy with `git update-index --skip-worktree`.

Content of `AnvilbookData` (format version 1):

| Field | Content |
|---|---|
| `version`, `generated`, `appVersion` | Format version, Unix time of the write, app version. |
| `realm` | The realm of the latest scan. |
| `scans` | Up to 30 latest scans, oldest first: `{id, time, items}`. |
| `items` | One string for each item in a price row or in a recorded recipe: `quality\|itemLevel\|requiredLevel\|class\|sellPrice\|vendorPrice\|name`. |
| `prices` | One string for the latest scan: `id:min:available:dayHigh;...`. |
| `vendor` | One string: `id:price;...`. |
| `history` | For each item, one string with one `min,available` field for each scan in `scans`, separated by `;`. An empty field means "not listed". |
| `settings` | The calculation settings, the disenchant table, and `changed_at` (Unix time for each key). |
| `share` | `server_url`, `username`, `signed_in`, `push_prices`, `published_characters`, `error`. |

### Prices in the game

1. For each item, the addon starts from the app's latest scan.
2. If Auctionator's API has a price for the item, the addon uses that price. On Forever,
   Auctionator loses its database at each load, so any price that it has comes from this session
   and is newer than the app's scan.
3. Listed counts come only from the app's scan. An item with no app row has an unknown count. The
   min-listed filter lets such an item through, and the Listed column shows `?`.

### Without the app

If `AnvilbookData` is nil, the Crafts and Plan tabs work with live Auctionator prices and
`GetItemInfo`. History and Sell-through show "Run the anvilbook app to see this."

## Addon structure

Files load in this `.toc` order and share state through the addon namespace (`local _, ns = ...`).

| File | Purpose |
|---|---|
| `AnvilbookData.lua` | Written by the app. The shipped copy is empty. |
| `AnvilbookExport.lua` | The recorder (recipes, bags, disenchants). It exposes the database on `ns`. |
| `Codec.lua` | Decodes the strings in `AnvilbookData`. |
| `Calc.lua` | The port of `craft.py`, `plan.py` and `disenchant.py`. |
| `Prices.lua` | Builds the price table: app scan, then Auctionator live prices. |
| `Items.lua` | Item details: `AnvilbookData.items` first, then `GetItemInfo`. |
| `Sync.lua` | Effective settings (app value or game edit, the newer one wins), and the game edits. |
| `Model.lua` | Joins the data file, the live prices and the recorded recipes into one calculator. It rebuilds after a change, and it tells the UI once for each burst of changes. |
| `UI/Widgets.lua` | Shared widgets: the table, the popup list, money text. |
| `UI/Window.lua` | The main window, its tabs, the slash command. |
| `UI/Crafts.lua`, `UI/Plan.lua`, `UI/AhPanel.lua`, `UI/History.lua`, `UI/Sellthrough.lua`, `UI/Share.lua`, `UI/Settings.lua` | One file for each part. |
| `UI/Tooltip.lua`, `UI/Options.lua`, `UI/Minimap.lua` | Tooltip lines, the on/off menu, the minimap button. |

### Calculator inputs

- Recipes: the current character's recorded recipes, with the rules of `recipes.merge`. The
  skills are the recorded ranks.
- Items: the `AnvilbookData.items` details, else `GetItemInfo`. Class IDs 2 and 4 map to `Weapon`
  and `Armor`, and quality numbers map with `QUALITY_NAMES`.
- Disenchant table: `settings.disenchant_table` from the app, with the measured yields from the
  game's own disenchant log (`effective_table`).

## The UI

- `/anvilbook` and the minimap button open or close the main window. `/anvilbook probe` runs the
  old debug probe. `/anvilbook options` opens the menu. Esc closes the window. The window saves its
  position.
- The title bar shows the source and age of the prices. See "Freshness" below.

| Tab | Content |
|---|---|
| Crafts | Sortable table: Item, Skill-up, Cost, Net sale, Profit, Exit, Disenchant, Casts, Per cast, Per hour, Listed. Click: show the cheapest path. Right-click: open in Plan. "Assume enchanter" box. |
| Plan | Item, budget (default: the gold you carry), "Use my bags". Shopping list, steps, bag items used, leftovers. |
| History | Search box and a price chart with the listed count, over the scans in `AnvilbookData.scans`. |
| Sell-through | From and To scans. The rows come from the history strings. |
| Share | Server, user, "Send my price scans", "Publish" for each character, "Push now". |
| Settings | AH cut, cast time, min listed, max use level, min disenchant samples, assume enchanter, and the measured disenchants (read-only). |

### AH panel

The panel docks to `AuctionHouseFrame` or `AuctionFrame`. It shows the active plan. "Plan it"
stores the bag counts at that time. Each row then compares the bags now with that record, and it
gets a tick when the full quantity is bought. "Search in Auctionator" calls
`Auctionator.API.v1.MultiSearchExact` when it exists.

### Tooltips

Lines: listed count, change against the previous scan, profit for each cast (if this character
crafts the item), disenchant value (for enchanters). A price line shows only when Auctionator has
no price for the item.

### On/off menu

Esc > Options > AddOns > Anvilbook: minimap button, AH panel, tooltip lines, and one box for each
of the six tabs. All are on by default and apply to the whole account
(`AnvilbookExportDB.ui.toggles`).

## Settings and Share sync

The game and the app can both change the same settings. The newer change wins, key by key.

- The app stores `changed_at` (Unix time for each key) in its settings. Each save stamps the keys
  that it saves.
- The data file carries the app values and `changed_at`.
- The game stores its edits in `AnvilbookExportDB.edits = {[key] = {value = v, time = t}}`. The
  effective value in the game is the edit when its time is newer than the app's `changed_at` for
  that key, else the app value.
- When the export file changes, the app reads `edits`. It applies each edit that is newer than
  its own `changed_at`, through the same validation as `PUT /api/settings`.
- Keys that the game may change: `ah_cut`, `cast_seconds`, `min_listed`, `max_use_level`,
  `min_disenchant_samples`, `assume_enchanter`, `push_prices`, `published_characters`.
- A change to `published_characters` that turns a character off goes through the same unpublish
  call as the Share tab. If that call fails, the app keeps the character published, and it puts
  the error in `share.error`.
- "Push now" in the game stores `AnvilbookExportDB.pushRequested = time()`. The app pushes when
  that time is newer than its `game_push_handled` setting, and then it stores the time.

### Freshness

The game cannot see a data file that the app writes after the load. Thus the title bar shows the
time of the loaded scan and the price source ("scan 2 h ago" or "live from Auctionator"). It
does not claim that newer data exists.

## Error handling

- The addon wraps each event handler and each UI refresh in `pcall` and sends errors to
  `geterrorhandler()`. One broken part must not stop the others.
- A data file with an unknown `version` is ignored, and the window says "Update the anvilbook app
  or the addon".
- The app never fails an import because of the bridge. A write error goes to the log and to
  `status.bridge_error`.
- The app writes the data file to a temporary name and then renames it, so the game never reads a
  half-written file.

## Testing

- `tests/test_bridge.py`: the data file content, the string formats, the skip when nothing
  changed, the symlink case, and the sync of game edits and push requests.
- `tests/test_calc_parity.py`: builds cases, runs the Python calculator, runs `Calc.lua` in LuaJIT
  on the same input, and compares rows and plans (floats to 1e-6). Skipped without `luajit`.
- `tests/addon_harness_ui.lua`: stubs the frame API, loads every addon file in `.toc` order with a
  sample `AnvilbookData`, opens each tab, fires the AH and tooltip events, and fails on any Lua
  error.
- Python change for parity: craft rows sort by `(-per_hour, item_id)`.
