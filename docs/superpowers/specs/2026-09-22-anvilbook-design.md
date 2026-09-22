# anvilbook: design

## Purpose

anvilbook is a local web app for WoW Classic (Forever beta) crafting economics.
It imports the Auctionator price database that WoW writes to disk, keeps every
import as a snapshot, and shows:

1. Craft profits: the cheapest buy-or-craft path for each recipe, and profit per cast.
2. Price history: the lowest price and listed count of an item over all snapshots.
3. Sell-through: the change in listed count between two snapshots.

It runs for one user on one desktop (Arch Linux, WoW under Steam Proton).

## Constraints

- The game writes `Auctionator.lua` only on `/reload`, logout, or disconnect.
  Addons cannot write files at other times.
- Auctionator stores each realm as one CBOR binary string
  (`C_EncodingUtil.SerializeCBOR`), written as a Lua string literal with Lua escapes.
- The beta caps characters at level 20 and professions at 150.
- Forever changed some recipe levels. Example: Deadly Bronze Poniard (3490)
  is 100 on Forever and 125 in the item database.
- The item database is nexus-devs/wow-classic-items `data/json/data.json`
  (about 35 MB). It has recipes (`createdBy`), required levels, and vendor prices.

## Stack

Python with uv, src layout. Dependencies: `fastapi`, `uvicorn`, `cbor2`.
Storage: stdlib `sqlite3`. UI: one static `index.html` with plain JS and uPlot
for charts. This follows `~/git/daytrade`.

## Units

### importer.py

- Input: path to `Auctionator.lua`, realm key (default: the only realm table key
  that is not `__dbversion`).
- Finds `AUCTIONATOR_PRICE_DATABASE`, then the realm entry `["<realm>"] = "<literal>"`.
- Reverses Lua string escapes: `\\`, `\"`, `\n`, `\r`, `\t`, `\0`, `\ddd`, and a
  backslash before a real newline.
- Decodes the bytes with `cbor2`.
- Output per item key: lowest price now (`m`), listed count and day high for the
  latest day in `a` and `h`.
- Also reads `AUCTIONATOR_VENDOR_PRICE_CACHE` (item id to copper).
- Raises `DecodeError` (own exception) with a clear message if the realm entry is a Lua table
  instead of a string (Auctionator does this when `C_EncodingUtil` is missing).
  Parsing Lua tables is out of scope.

### store.py

SQLite file at `~/.local/share/anvilbook/anvilbook.db`.

- `scans(id INTEGER PK, file_mtime TEXT, imported_at TEXT, realm TEXT, file_hash TEXT UNIQUE, scan_day INTEGER)`
- `prices(scan_id INTEGER, item_id INTEGER, min_price INTEGER, available INTEGER, day_high INTEGER, day INTEGER, PRIMARY KEY(scan_id, item_id))`
- `vendor_prices(item_id INTEGER PK, price INTEGER)`: latest Auctionator vendor cache.
- `settings(key TEXT PK, value TEXT)` with JSON values.

Item keys that are not plain item ids (for example keys with suffixes) are skipped.

Auctionator keeps the last price of items that are no longer listed. `scan_day` is
the latest day in the scan. A price row counts as listed only if its `day` equals
`scan_day`. All reads (crafts, history, sell-through) use only listed rows. An item
that is not listed has 0 available.

### items.py

- Downloads `data.json` on first run to `~/.local/share/anvilbook/items.json`.
- Loads it into a dict by item id. It is read-only.

### craft.py

The recursive cost logic from the prototype (`crafts.py`):

- For each item, the options are: buy (lower of AH price and vendor price,
  0 casts), or craft with each recipe the user can make (reagent options
  combined, plus 1 cast, divided by output amount).
- Recursion depth: 3. Options are reduced to the Pareto set of (price, casts).
- A recipe is craftable if its skill (Forever override first, then the database)
  is at most the user's cap for that profession.
- For each craftable recipe whose output has an AH price: net sale is the higher of
  AH price times (1 - AH cut) and the vendor sell price, times output amount.
- Result per recipe: best path by profit per cast, with profit, casts, profit per
  cast, profit per hour, listed count, and the path text. Also the cheapest path
  (highest profit per craft) with its profit, casts, and path text.
- Filters: output required level at most `max_use_level`, and output listed count
  at least `min_listed`.

### watcher

A background task in the FastAPI app. Every 5 seconds it checks the file mtime.
If the mtime changed, it hashes the file and imports it when the hash is new.
Errors are logged. The last good data stays in use.

- A file with an empty price database is not stored. The status tells the user to
  scan the AH and `/reload`.
- After a decode error, the watcher tries the same file again on the next poll,
  because WoW can be in the middle of a write.
- A save counts as a scan only if at least `min_scan_items` items (default 100) were
  seen on its latest day. On Forever, Auctionator loses its price database on every
  game load, and a single search also causes a save. Without this rule those saves
  would look like everything sold out.
- WoW's `C_EncodingUtil.SerializeCBOR` writes every string as a CBOR byte string.
  The importer converts byte strings to text after decoding.

### api.py

- `GET /api/crafts`: craft table for the latest scan and current settings.
- `GET /api/items/search?q=`: names of items that appear in any scan.
- `GET /api/items/{id}/history`: min price, listed count, and time for each scan.
- `GET /api/sellthrough?from=&to=`: per item, listed count and price in both scans,
  and the change. Defaults: the two latest scans.
- `GET /api/scans`: list of scans.
- `POST /api/import`: import now.
- `GET /api/settings`, `PUT /api/settings`.
- `GET /api/status`: file path, file found or not, last import, last error.
- `GET /`: the static page.

### static/index.html

Tabs: Crafts, History, Sell-through, Settings.

- Crafts: sortable table. Click a row to show the path.
- History: item search, then a uPlot chart of price and listed count.
- Sell-through: two scan pickers and a sortable table. A note says that a drop
  can also be expired auctions.
- Settings: profession caps, Forever overrides (item id to skill), max use level,
  min listed, cast seconds, AH cut, SavedVariables path.
- A banner shows the status from `/api/status`.

## Settings defaults

- SavedVariables path: `~/.local/share/Steam/steamapps/compatdata/2625793156/pfx/drive_c/Program Files (x86)/World of Warcraft/_classic_beta_/WTF/Account/1111708535#1/SavedVariables/Auctionator.lua`
- Caps: Blacksmithing 120, Mining 99. A profession with no cap is not craftable,
  also for recipes with no skill value.
- Forever overrides: `{3490: 100}`.
- max_use_level 20, min_listed 3, cast_seconds 3, ah_cut 0.05.

## Testing

pytest:

- importer: decode a fixture copy of the real `Auctionator.lua`. Check the item
  count and known prices (Copper Ore 2770 = 57c, Tin Ore 2771 = 200c).
- Lua unescape: each escape form.
- craft: a small synthetic item set with the bronze case. Bar path gives 97c per
  cast, ore path 1s 61c over 3 casts.
- sell-through: diff of two small scans.

## Run

`uv run anvilbook` serves on `127.0.0.1:8765`.

## Out of scope

- More than one realm or character in the UI.
- Backfill from Auctionator's own day history.
- The user's own auctions and posting history.
- Parsing the price database when it is a Lua table.
