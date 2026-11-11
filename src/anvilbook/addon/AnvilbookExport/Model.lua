-- Joins the app's data, the live prices and the recorded recipes into one calculator, and
-- tells the UI when that picture changes.
local _, ns = ...

local FORMAT = 1
local model
local database
local listeners = {}
local pending = false

function ns.safe(f, ...)
  local ok, err = pcall(f, ...)
  if not ok then
    geterrorhandler()(err)
  end
  return ok
end

-- Registering an event this client does not know raises an error.
function ns.listen(frame, ...)
  for _, event in ipairs({...}) do
    pcall(frame.RegisterEvent, frame, event)
  end
end

function ns.data()
  local data = AnvilbookData
  if type(data) == "table" and data.version == FORMAT then
    return data
  end
end

function ns.dataProblem()
  local data = AnvilbookData
  if type(data) == "table" and data.version ~= FORMAT then
    return "The app's data file has another format. Update the anvilbook app and the addon."
  end
end

function ns.onChange(listener)
  listeners[#listeners + 1] = listener
end

local function notify()
  pending = false
  for _, listener in ipairs(listeners) do
    ns.safe(listener)
  end
end

-- A scan updates Auctionator many times a second, so listeners hear about it once.
function ns.invalidate()
  model = nil
  if pending then
    return
  end
  pending = true
  if C_Timer and C_Timer.After then
    C_Timer.After(0.3, notify)
  else
    notify()
  end
end

-- Above any profession's cap: the Any view ignores skill.
local ANY_SKILL = 1000

-- AnvilbookRecipes.lua, decoded once.
function ns.recipeDatabase()
  if not database then
    database = {}
    for itemId, packed in pairs(AnvilbookRecipes and AnvilbookRecipes.recipes or {}) do
      database[itemId] = ns.Codec.recipes(packed)
    end
  end
  return database
end

-- The character whose recipes the window shows: the one picked there, else the one playing.
-- The addon's saved data is account-wide, so it holds every character that opened a profession window.
function ns.viewedKey()
  local characters = AnvilbookExportDB and AnvilbookExportDB.characters or {}
  local picked = ns.ui().view
  if picked and characters[picked] then
    return picked
  end
  return ns.characterKey()
end

function ns.character()
  local key = ns.viewedKey()
  local characters = AnvilbookExportDB and AnvilbookExportDB.characters or {}
  return key, characters[key] or {professions = {}}
end

local function itemTable(prices, ids)
  local items, missing = {}, {}
  local function add(id)
    if not items[id] then
      local details = ns.Items.details(id)
      local copy = {}
      for k, v in pairs(details or {}) do
        copy[k] = v
      end
      items[id] = copy
      missing[id] = not (details and details.name) or nil
    end
  end
  for id in pairs(prices) do
    add(id)
  end
  for id in pairs(ids) do
    add(id)
  end
  return items, missing
end

local function calcSettings(m, skills)
  local settings = m.settings
  return {
    skills = skills, skill_overrides = settings.skill_overrides, max_use_level = settings.max_use_level,
    min_listed = settings.min_listed, cast_seconds = settings.cast_seconds, ah_cut = settings.ah_cut,
    disenchanter = settings.assume_enchanter and true or m.skills.Enchanting ~= nil,
    disenchant_table = ns.Calc.effectiveTable(settings.disenchant_table, m.records, settings.min_disenchant_samples),
  }
end

function ns.model()
  if model then
    return model
  end
  local data = ns.data()
  local settings = ns.Sync.settings()
  local key, char = ns.character()
  local professions, skills, ids, known = {}, {}, {}, {}
  for name, profession in pairs(char.professions or {}) do
    name = ns.Calc.ALIASES[name] or name
    professions[name] = profession
    skills[name] = tonumber(profession.rank) or 0
    for itemId, recipe in pairs(profession.recipes or {}) do
      ids[itemId] = true
      known[name .. ":" .. itemId] = true
      for _, reagent in ipairs(recipe.reagents or {}) do
        ids[reagent.id] = true
      end
    end
  end
  local db = ns.recipeDatabase()
  for itemId, recipes in pairs(db) do
    for _, recipe in ipairs(recipes) do
      if professions[recipe.category] then
        ids[itemId] = true
        for _, reagent in ipairs(recipe.reagents) do
          ids[reagent.itemId] = true
        end
      end
    end
  end

  local prices, live = ns.Prices.build(data, ids)
  local vendor = ns.Prices.vendor(data, ids)
  local items, missing = itemTable(prices, ids)
  ns.Calc.merge(items, professions, db)

  model = {data = data, settings = settings, character = key, professions = professions, skills = skills,
           prices = prices, live = live, records = AnvilbookExportDB and AnvilbookExportDB.disenchants or {},
           missing = missing, known = known}
  model.calc = ns.Calc.new(items, prices, vendor, calcSettings(model, skills))
  return model
end

-- Every recipe of every profession, as if the character had them all at full skill, to show
-- what is worth investing in. app.py's calculator(everything=True) does the same.
function ns.anyModel()
  local m = ns.model()
  if not m.any then
    local db, ids, skills = ns.recipeDatabase(), {}, {}
    for itemId, recipes in pairs(db) do
      ids[itemId] = true
      for _, recipe in ipairs(recipes) do
        skills[recipe.category] = ANY_SKILL
        for _, reagent in ipairs(recipe.reagents) do
          ids[reagent.itemId] = true
        end
      end
    end
    local prices = ns.Prices.build(m.data, ids)
    local items = itemTable(prices, ids)
    for itemId, recipes in pairs(db) do
      items[itemId].createdBy = recipes
    end
    m.any = {calc = ns.Calc.new(items, prices, ns.Prices.vendor(m.data, ids), calcSettings(m, skills))}
  end
  return m.any
end

-- The calculator behind the Crafts view in use, for Plan.
function ns.planCalc()
  local crafts = ns.ui().crafts
  return (crafts and crafts.view == "any") and ns.anyModel().calc or ns.model().calc
end

-- The rows, and the learned rows by item id. showAll keeps losses too (Calculator:rows).
-- view "any" prices every recipe; its rows say whether this character knows them.
function ns.rows(showAll, view)
  local m = ns.model()
  local key = (view == "any" and "any " or "") .. (showAll and "all" or "profitable")
  m.rows = m.rows or {}
  if not m.rows[key] then
    local rows, byId
    if view == "any" then
      rows = ns.anyModel().calc:rows(showAll)
      for _, row in ipairs(rows) do
        row.learned = m.known[row.profession .. ":" .. row.item_id] == true
      end
    else
      rows = m.calc:rows(showAll)
    end
    byId = {}
    for _, row in ipairs(rows) do
      if row.learned and not byId[row.item_id] then
        byId[row.item_id] = row
      end
    end
    m.rows[key] = {rows = rows, byId = byId}
  end
  return m.rows[key].rows, m.rows[key].byId
end

-- Points for each scan in data.scans: {min_price, available}, or false when the item was not listed.
function ns.history(id)
  local data = ns.data()
  local packed = data and data.history and data.history[id]
  if not packed then
    return nil
  end
  return ns.Codec.history(packed, #data.scans)
end

local events = CreateFrame("Frame")
ns.listen(events, "PLAYER_LOGIN", "AUCTION_HOUSE_CLOSED", "GET_ITEM_INFO_RECEIVED")
events:SetScript("OnEvent", function(_, event, itemId)
  -- This event fires for every item the client loads; only the calculator's own gaps matter.
  if event == "GET_ITEM_INFO_RECEIVED" then
    if model and model.missing[itemId] then
      ns.invalidate()
    end
    return
  end
  if event == "PLAYER_LOGIN" then
    local api = ns.Prices.auctionator()
    if api and api.RegisterForDBUpdate then
      pcall(api.RegisterForDBUpdate, ns.Prices.CALLER, ns.invalidate)
    end
  end
  ns.invalidate()
end)
