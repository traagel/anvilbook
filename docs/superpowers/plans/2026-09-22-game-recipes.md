# Game recipes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use the recipes the character knows, read from the game, instead of Classic Era database recipes.

**Architecture:** A WoW addon writes known recipes to SavedVariables. A Lua table parser reads that file. A merge step replaces database recipes per exported profession before the craft calculator runs.

**Tech Stack:** Lua (WoW 1.60.1 API), Python 3.12+, existing anvilbook stack. LuaJIT only for the addon test.

**Spec:** `docs/superpowers/specs/2026-09-22-game-recipes-design.md`

## Global Constraints

- TOC interface `16001`. SavedVariables name `AnvilbookExportDB`.
- Profession alias: `Smelting` -> `Mining`.
- Game recipes get `requiredSkill` 0 and keep `difficulty`.
- No new Python dependencies.
- Commit trailer: `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

Execution is inline in the same session as the design, so each task's code is written
test-first directly in its commit. The interfaces below are the contract between tasks.

### Task 1: Lua table parser

**Files:** Create `src/anvilbook/luatable.py`, `tests/test_luatable.py`.

**Produces:** `parse_savedvariables(text: bytes) -> dict[str, object]`. Lua tables become
`dict` (keys `str` or `int`); array items get keys 1..n. Strings are `str`.
`LuaParseError(Exception)` on bad input.

Tests: top-level assignments; nested tables; `["k"] =` and `[3] =` keys; array items with
`-- [1]` comments; string escapes; `-5`, `1.25`, `1e3`; `true`, `false`, `nil`; an
unterminated table raises `LuaParseError`.

### Task 2: Addon

**Files:** Create `addon/AnvilbookExport/AnvilbookExport.toc`,
`addon/AnvilbookExport/AnvilbookExport.lua`, `tests/addon_harness.lua`, `tests/test_addon.py`.

**Produces:** `AnvilbookExportDB` in the shape of the spec.

Tests (LuaJIT, skipped if missing): with a stubbed trade skill of 1 header and 2
recipes (1 with an uncached reagent), `TRADE_SKILL_SHOW` expands headers once and
records 1 recipe with its reagents, rank, and max rank. A later update with the
reagent cached adds the second recipe and keeps the first. `GetTradeSkillLine`
returning `UNKNOWN` records nothing.

Then install: symlink into the game's AddOns folder.

### Task 3: Recipe merge and difficulty

**Files:** Create `src/anvilbook/recipes.py`, `tests/test_recipes.py`. Modify
`src/anvilbook/craft.py` (add `CraftRow.difficulty`), `tests/test_craft.py`.

**Produces:**
- `@dataclass GameExport(character: str, updated: int, professions: dict[str, dict])`
  where each profession dict has `rank`, `maxRank`, `recipes` (item id -> recipe dict).
- `load_export(path: Path) -> GameExport | None` (None if the file is missing or has no characters).
- `merge(items: dict[int, dict], export: GameExport) -> dict[int, dict]`.
- `export_skills(export: GameExport) -> dict[str, int]`.

Tests: latest character wins; Smelting maps to Mining; exported profession drops DB
recipes of that profession but keeps other professions' recipes; game recipe shape
(`amount`, `requiredSkill` 0, `category`, `reagents`, `difficulty`); unknown item gets a
name entry; input dict is not mutated; `CraftRow.difficulty` carries the recipe value.

### Task 4: App and UI

**Files:** Modify `src/anvilbook/store.py` (setting `export_path`),
`src/anvilbook/app.py`, `src/anvilbook/static/index.html`, `tests/test_app.py`.

**Consumes:** Tasks 1 and 3.

Tests: with an export file that gives Bronze Bar a different reagent amount, `/api/crafts`
reflects the game recipe cost and difficulty; `/api/status` has `export.professions`
with the rank; without an export file, `export` is `null` and crafts still work.
