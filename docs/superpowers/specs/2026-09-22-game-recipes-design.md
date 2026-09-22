# anvilbook: recipes from the game

Extends `2026-09-22-anvilbook-design.md`.

## Problem

The recipe data comes from a Classic Era item database. Forever has new recipes,
changed recipe levels, and possibly changed reagents. Manual overrides do not scale.

## Solution

A small WoW addon, `AnvilbookExport`, records the recipes the character knows from
the game API. The app uses those recipes instead of the database recipes for each
exported profession.

### Addon (`addon/AnvilbookExport/`)

- TOC `## Interface: 16001` (client 1.60.1). Account-wide SavedVariables `AnvilbookExportDB`.
- On `TRADE_SKILL_SHOW` it expands all headers (`ExpandTradeSkillSubClass(0)`), then
  records. On `TRADE_SKILL_UPDATE` it records again without expanding (expanding
  fires another update). A busy flag stops re-entry.
- Record per recipe with an item output: output item id, name, min and max made,
  difficulty (`optimal`, `medium`, `easy`, `trivial`), and reagents (item id, count,
  name). A recipe whose reagent links are not cached yet is skipped; the next
  update records it.
- Records merge by output item id. The addon never deletes recipes, so a
  filtered window ("Have materials") only means a partial update.
- Shape:

```lua
AnvilbookExportDB = {
  version = 1,
  characters = {
    ["Thordak - Classic Beta PvP"] = {
      updated = 1790000000,
      professions = {
        ["Blacksmithing"] = {
          rank = 147, maxRank = 150, updated = 1790000000,
          recipes = {
            [3490] = { name = "Deadly Bronze Poniard", minMade = 1, maxMade = 1, difficulty = "optimal",
                       reagents = { { id = 2841, count = 4, name = "Bronze Bar" }, ... } },
          },
        },
      },
    },
  },
}
```

- Install: symlink `addon/AnvilbookExport` into the game's `Interface/AddOns`.

### App

- `luatable.py`: parses a SavedVariables file into Python values. Supports tables
  with `["key"] =` and `[number] =` keys, array items, `--` comments, strings with Lua
  escapes (decoded as UTF-8), integers, floats, `true`, `false`, `nil`.
- `recipes.py`:
  - `load_export(path) -> GameExport | None`: reads the file, picks the character
    with the latest `updated`. Profession `Smelting` maps to `Mining`.
  - `merge(items, export) -> dict`: returns a new items dict. For each exported
    profession, database recipes of that profession are removed and the game
    recipes are added (`requiredSkill` 0, because a known recipe is craftable;
    `difficulty` kept). Items that are not in the database get an entry with the
    game name.
- Craft settings: a profession's cap is the exported rank when an export exists,
  else the `skills` setting. `CraftRow` gets `difficulty` (None for database recipes).
- Setting `export_path` defaults to `AnvilbookExport.lua` next to the Auctionator file.
- `/api/crafts` reads the export on each call. `/api/status` adds
  `export: {character, updated, professions: {name: rank}}` or `null`.
- UI: a Skill-up column (difficulty) in Crafts, and the export summary in the status.

## Out of scope

- Trainer recipes that are not learned yet.
- Enchanting (uses the Craft API in Classic).

## Testing

- `luatable`: nested tables, array items with comments, escapes, number forms.
- Addon: run the Lua file under LuaJIT with stubbed WoW API functions, and check the
  table it builds (the test is skipped when LuaJIT is missing).
- `recipes`: character choice, Smelting alias, merge rules, Forever-only items.
- App: crafts use the game reagents when an export exists; status shows the export.
