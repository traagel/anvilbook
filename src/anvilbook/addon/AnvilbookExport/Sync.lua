-- Settings live in the app and can be changed in game too; the newer change wins, key by key.
-- bridge.py reads AnvilbookExportDB.edits and pushRequested from the SavedVariables.
local _, ns = ...
local Sync = {}
ns.Sync = Sync

-- store.DEFAULT_SETTINGS, for a game that has no app data yet.
local DEFAULTS = {ah_cut = 0.05, cast_seconds = 3, min_listed = 3, max_use_level = 20, min_disenchant_samples = 20,
                  assume_enchanter = false, push_prices = false}

local STRANGE_DUST, LESSER_MAGIC, GREATER_MAGIC = 10940, 10938, 10939
local SOUL_DUST, LESSER_ASTRAL, GLIMMERING_SHARD = 11083, 10998, 10978
-- disenchant.DEFAULT_TABLE
Sync.DEFAULT_TABLE = {
  {quality = "Uncommon", maxLevel = 15,
   armor = {{STRANGE_DUST, 0.8, 1.5}, {LESSER_MAGIC, 0.2, 1.5}},
   weapon = {{STRANGE_DUST, 0.2, 1.5}, {LESSER_MAGIC, 0.8, 1.5}}},
  {quality = "Uncommon", maxLevel = 20,
   armor = {{STRANGE_DUST, 0.75, 2}, {GREATER_MAGIC, 0.2, 1}, {GLIMMERING_SHARD, 0.05, 1}},
   weapon = {{STRANGE_DUST, 0.2, 2}, {GREATER_MAGIC, 0.75, 1}, {GLIMMERING_SHARD, 0.05, 1}}},
  {quality = "Uncommon", maxLevel = 25,
   armor = {{STRANGE_DUST, 0.75, 3}, {LESSER_ASTRAL, 0.2, 1}, {GLIMMERING_SHARD, 0.05, 1}},
   weapon = {{STRANGE_DUST, 0.2, 3}, {LESSER_ASTRAL, 0.75, 1}, {GLIMMERING_SHARD, 0.05, 1}}},
  {quality = "Uncommon", maxLevel = 30,
   armor = {{SOUL_DUST, 0.75, 2}, {LESSER_ASTRAL, 0.2, 1}, {GLIMMERING_SHARD, 0.05, 1}},
   weapon = {{SOUL_DUST, 0.2, 2}, {LESSER_ASTRAL, 0.75, 1}, {GLIMMERING_SHARD, 0.05, 1}}},
  {quality = "Rare", maxLevel = 25,
   armor = {{GLIMMERING_SHARD, 1.0, 1}},
   weapon = {{GLIMMERING_SHARD, 1.0, 1}}},
}

local function db()
  AnvilbookExportDB = AnvilbookExportDB or {}
  AnvilbookExportDB.edits = AnvilbookExportDB.edits or {}
  return AnvilbookExportDB
end

function Sync.share()
  local data = ns.data()
  return data and data.share or {}
end

function Sync.settings()
  local data = ns.data()
  local app = data and data.settings or {}
  local share = Sync.share()
  local out = {}
  for key, default in pairs(DEFAULTS) do
    if app[key] ~= nil then
      out[key] = app[key]
    else
      out[key] = default
    end
  end
  if share.push_prices ~= nil then
    out.push_prices = share.push_prices
  end
  out.published_characters = share.published_characters or {}
  out.disenchant_table = app.disenchant_table or Sync.DEFAULT_TABLE
  local changed = app.changed_at or {}
  for key, edit in pairs(db().edits) do
    if type(edit) == "table" and (edit.time or 0) > (changed[key] or 0) then
      out[key] = edit.value
    end
  end
  return out
end

function Sync.set(key, value)
  if type(value) == "table" then
    local copy = {}
    for k, v in pairs(value) do
      copy[k] = v
    end
    value = copy
  end
  db().edits[key] = {value = value, time = time()}
  ns.invalidate()
end

function Sync.requestPush()
  db().pushRequested = time()
end
