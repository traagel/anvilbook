# anvilbook

A local auction house and crafting ledger for **WoW Forever (Classic beta)**.

It reads the prices that the [Auctionator](https://www.curseforge.com/wow/addons/auctionator)
addon saves, keeps every scan as history, and tells you what is worth crafting with the
recipes your characters actually know.

Everything runs on your own computer. Nothing is uploaded anywhere.

## What it does

- **Crafts**: for each recipe, the cheapest way to get every reagent (buy it, or craft it
  from its own reagents), the profit, and the profit for each cast. Skill-up colors come
  from the game.
- **Plan**: "I have 3g 43s, what do I buy?" It answers with a batch size, a shopping list
  with quantities, the crafting steps, what comes from your bags, and the leftovers.
- **History**: the lowest price and the listed count of any item over all your scans.
- **Sell-through**: what sold between 2 scans, which shows real demand.
- **Disenchanting**: values a crafted item by its disenchant materials as well as its sale
  price, and learns the real yields from the disenchants you do.

## Install

You need [Auctionator](https://www.curseforge.com/wow/addons/auctionator) in game.

**Windows:** download `anvilbook.exe` from the
[releases page](https://github.com/traagel/anvilbook/releases) and run it. Your browser
opens on the app.

**Anything else, with [uv](https://docs.astral.sh/uv/):**

```bash
uvx anvilbook
```

**From source:**

```bash
git clone https://github.com/traagel/anvilbook
cd anvilbook
uv run anvilbook
```

## First run

1. anvilbook looks for World of Warcraft by itself. If it finds one game folder it uses it.
   If it finds several, pick one on the setup screen.
2. Press **Install addon**. That copies the small `AnvilbookExport` addon into the game.
3. Start WoW. Open each profession window for a few seconds, then type `/reload`.
4. Scan the auction house with Auctionator, then type `/reload` again.

Step 3 gives anvilbook your recipes and skill levels. Step 4 gives it prices. Repeat step 4
whenever you want fresh prices; the app imports the file within 5 seconds of each `/reload`.

## Why `/reload`

WoW writes addon data to disk only when you log out, disconnect, or type `/reload`. No addon
can write files at another time, so `/reload` is how the data reaches anvilbook.

## Settings

The Settings tab holds the auction cut, the cast time, filters, the disenchant table, and the
file paths. A small config file also exists for values needed before the app starts:

`~/.config/anvilbook/config.toml` (Windows: `%APPDATA%\anvilbook\config.toml`)

```toml
savedvariables_path = "/path/to/WTF/Account/12345#1/SavedVariables/Auctionator.lua"
port = 8765
open_browser = true
```

Data lives in `~/.local/share/anvilbook/` (Windows: `%APPDATA%\anvilbook\`): the price
history database and a cached copy of the item database.

## Known limits

- Built for **WoW Forever beta, client 1.60.1**, with an **English** client.
- Prices come from the lowest listing of each item, not the full price ladder, so a large
  buy costs more than the estimate.
- Disenchant yields start as estimates, and get replaced by your measured results.
- On Forever, Auctionator loses its own price database on each game load. anvilbook imports
  each save before that happens, which is a good reason to keep it running.

## Development

```bash
uv run pytest                 # 98 tests
luajit tests/addon_harness.lua src/anvilbook/addon/AnvilbookExport/AnvilbookExport.lua
luajit tests/addon_harness_modern.lua src/anvilbook/addon/AnvilbookExport/AnvilbookExport.lua
```

The addon harnesses stub the WoW API, so they need [LuaJIT](https://luajit.org/) but not the
game.

## Credits

- Item and recipe data: [nexus-devs/wow-classic-items](https://github.com/nexus-devs/wow-classic-items) (MIT)
- Charts: [uPlot](https://github.com/leeoniya/uPlot) (MIT)
- Prices: the [Auctionator](https://www.curseforge.com/wow/addons/auctionator) addon

anvilbook is not affiliated with Blizzard Entertainment.

## Licence

MIT. See [LICENSE](LICENSE).
