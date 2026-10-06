local _, ns = ...

-- Bumped when a fix makes older saved data wrong; it is then thrown away.
local VERSION = 5
local RETRIES = 5

local frame = CreateFrame("Frame")
local busy = false
local lastSeen
local reported = {}

local DIFFICULTY = {}
if Enum and Enum.TradeskillRelativeDifficulty then
  for name, value in pairs(Enum.TradeskillRelativeDifficulty) do
    DIFFICULTY[value] = name:lower()
  end
end

local function itemId(link)
  return link and tonumber(link:match("item:(%d+)"))
end

local function itemName(id)
  if C_Item and C_Item.GetItemNameByID then
    return C_Item.GetItemNameByID(id)
  end
  if GetItemInfo then
    return (GetItemInfo(id))
  end
end

-- GetAllRecipeIDs also returns other professions' recipes, so recipes are kept only
-- when their category belongs to the open profession.
local function categorySet(api)
  if not api.GetCategories then
    return nil
  end
  local ok, top = pcall(api.GetCategories)
  if not ok or type(top) ~= "table" or #top == 0 then
    return nil
  end
  local set, pending, count = {}, {}, 0
  for _, id in ipairs(top) do
    pending[#pending + 1] = id
  end
  while #pending > 0 do
    local id = table.remove(pending)
    if not set[id] then
      set[id] = true
      count = count + 1
      if api.GetSubCategories then
        local okSub, subs = pcall(api.GetSubCategories, id)
        if okSub and type(subs) == "table" then
          for _, sub in ipairs(subs) do
            pending[#pending + 1] = sub
          end
        end
      end
    end
  end
  return set, count
end

-- Forever runs the retail professions UI, so recipes come from C_TradeSkillUI.
local function modernRecipes(db)
  local api = C_TradeSkillUI
  local info = api.GetBaseProfessionInfo and api.GetBaseProfessionInfo()
  local profession = info and (info.professionName or info.parentProfessionName)
  if not profession or profession == "" then
    return nil
  end
  local all = api.GetAllRecipeIDs and api.GetAllRecipeIDs() or {}
  local categories, categoryCount = categorySet(api)
  local filtered = api.GetFilteredRecipeIDs and select(2, pcall(api.GetFilteredRecipeIDs)) or nil
  filtered = type(filtered) == "table" and #filtered > 0 and filtered or nil
  local debug = {api = "modern", recipeCount = #all, professionInfo = info, categories = categoryCount,
                 filteredCount = filtered and #filtered}
  db.debug = debug

  -- GetAllRecipeIDs returns every profession's recipes, so the open profession has to be
  -- told apart by the window's own list, or by its categories.
  local ids = filtered or all
  debug.source = filtered and "filtered" or "categories"
  if not filtered and not categories then
    debug.skipped = "cannot tell which recipes belong to this profession"
    return nil
  end

  -- The open profession changes before its recipe list does, so a single read can mix
  -- one profession's name with another's recipes. Only a repeated reading is trusted.
  local seen = table.concat({info.professionID or profession, #ids, ids[1] or 0, ids[#ids] or 0}, ":")
  if seen ~= lastSeen then
    lastSeen = seen
    debug.skipped = "waiting for the recipe list to settle"
    return nil
  end
  local basic = Enum and Enum.CraftingReagentType and Enum.CraftingReagentType.Basic
  local recipes, recorded = {}, 0
  for _, recipeID in ipairs(ids) do
    local recipe = api.GetRecipeInfo(recipeID)
    local mine = recipe and (filtered or (recipe.categoryID and categories[recipe.categoryID]))
    local schematic = mine and recipe.learned and api.GetRecipeSchematic(recipeID, false)
    local outputId = schematic and schematic.outputItemID
    if outputId and outputId ~= 0 then
      local reagents = {}
      for _, slot in ipairs(schematic.reagentSlotSchematics or {}) do
        local first = slot.reagents and slot.reagents[1]
        -- Optional and finishing reagents are not part of the base cost.
        if first and first.itemID and (not basic or slot.reagentType == basic) then
          reagents[#reagents + 1] = {id = first.itemID, count = slot.quantityRequired or 1,
                                     name = itemName(first.itemID)}
        end
      end
      recipes[outputId] = {name = recipe.name or schematic.name, minMade = schematic.quantityMin or 1,
                           maxMade = schematic.quantityMax or 1, difficulty = DIFFICULTY[recipe.relativeDifficulty],
                           reagents = reagents}
      recorded = recorded + 1
      if not debug.sample then
        debug.sample = {recipeInfo = recipe, schematic = schematic}
      end
    end
  end
  return profession, info.skillLevel, info.maxSkillLevel, recipes, recorded, true
end

local function classicRecipes(db, expand)
  local profession, rank, maxRank = GetTradeSkillLine()
  if not profession or profession == "UNKNOWN" then
    return nil
  end
  -- Collapsed headers hide their recipes from GetTradeSkillInfo.
  if expand and ExpandTradeSkillSubClass then
    ExpandTradeSkillSubClass(0)
  end
  db.debug = {api = "classic", recipeCount = GetNumTradeSkills()}
  local recipes, recorded = {}, 0
  for i = 1, GetNumTradeSkills() do
    local name, kind = GetTradeSkillInfo(i)
    local id = kind ~= "header" and itemId(GetTradeSkillItemLink(i))
    if id then
      local reagents = {}
      for r = 1, GetTradeSkillNumReagents(i) do
        local reagentName, _, count = GetTradeSkillReagentInfo(i, r)
        local reagentId = itemId(GetTradeSkillReagentItemLink(i, r))
        -- Links are nil until the client caches the item; a retry fills them in.
        if not reagentId or not count then
          reagents = nil
          break
        end
        reagents[r] = {id = reagentId, count = count, name = reagentName}
      end
      if reagents then
        local minMade, maxMade = GetTradeSkillNumMade(i)
        recipes[id] = {name = name, minMade = minMade, maxMade = maxMade, difficulty = kind, reagents = reagents}
        recorded = recorded + 1
      end
    end
  end
  return profession, rank, maxRank, recipes, recorded
end

local function record(db, expand)
  local profession, rank, maxRank, recipes, recorded, verified
  if C_TradeSkillUI and C_TradeSkillUI.GetAllRecipeIDs then
    profession, rank, maxRank, recipes, recorded, verified = modernRecipes(db)
  else
    profession, rank, maxRank, recipes, recorded = classicRecipes(db, expand)
  end
  if not profession then
    return nil
  end

  if db.version ~= VERSION then
    db.version, db.characters = VERSION, nil
  end
  db.characters = db.characters or {}
  local key = UnitName("player") .. " - " .. GetRealmName()
  local char = db.characters[key] or {professions = {}}
  db.characters[key] = char
  local prof = char.professions[profession] or {recipes = {}}
  char.professions[profession] = prof
  prof.rank, prof.maxRank = rank, maxRank
  prof.updated = time()
  char.updated = prof.updated
  -- A verified list is complete, so it also clears recipes saved by an earlier version.
  if verified then
    prof.recipes = recipes
  else
    for id, recipe in pairs(recipes) do
      prof.recipes[id] = recipe
    end
  end
  return profession, recorded
end

local function run(event, attempt)
  -- Expanding headers fires an update event.
  if busy then
    return
  end
  busy = true
  AnvilbookExportDB = AnvilbookExportDB or {}
  local db = AnvilbookExportDB
  -- Script errors are hidden by default, so the saved file is the only place to see what happened.
  db.lastEvent = {event = event, time = time()}
  local ok, profession, recorded = pcall(record, db, event == "TRADE_SKILL_SHOW")
  busy = false
  if not ok then
    db.lastError = tostring(profession)
    geterrorhandler()(profession)
    return
  end
  db.lastError = nil
  if profession and reported[profession] ~= recorded then
    reported[profession] = recorded
    print(("Anvilbook: %d %s recipes recorded"):format(recorded, profession))
    ns.invalidate()
  end
  -- Item data and the recipe list arrive late, and the client may have no update event.
  if C_Timer and (attempt or 0) < RETRIES then
    C_Timer.After(1, function() run("RETRY", (attempt or 0) + 1) end)
  end
end

local DISENCHANT_SPELL = 13262
local DISENCHANT_LOG_LIMIT = 500
local KINDS = {[2] = "Weapon", [4] = "Armor"}
local pendingDisenchant

local function bagItem(name)
  local containers = C_Container or _G
  local numSlots = containers.GetContainerNumSlots or GetContainerNumSlots
  local itemIdAt = containers.GetContainerItemID or GetContainerItemID
  if not numSlots or not itemIdAt then
    return nil
  end
  for bag = 0, 4 do
    for slot = 1, (numSlots(bag) or 0) do
      local id = itemIdAt(bag, slot)
      local info = C_Item and C_Item.GetItemInfo or GetItemInfo
      local itemName, quality, itemLevel
      if id and info then
        -- An `and` chain would keep only the first return value.
        itemName, _, quality, itemLevel = info(id)
      end
      if itemName == name then
        local classID = select(6, C_Item.GetItemInfoInstant(id))
        return {id = id, name = itemName, quality = quality, itemLevel = itemLevel, kind = KINDS[classID]}
      end
    end
  end
end

local function character()
  AnvilbookExportDB = AnvilbookExportDB or {}
  local db = AnvilbookExportDB
  db.characters = db.characters or {}
  local key = UnitName("player") .. " - " .. GetRealmName()
  db.characters[key] = db.characters[key] or {professions = {}}
  return db.characters[key]
end

local function readBags()
  local containers = C_Container or _G
  local numSlots = containers.GetContainerNumSlots or GetContainerNumSlots
  local slotInfo = containers.GetContainerItemInfo
  local itemIdAt = containers.GetContainerItemID or GetContainerItemID
  if not numSlots then
    return nil
  end
  local bags = {}
  for bag = 0, 4 do
    for slot = 1, (numSlots(bag) or 0) do
      local id, count
      if slotInfo then
        local info = slotInfo(bag, slot)
        id, count = info and info.itemID, info and info.stackCount
      elseif itemIdAt then
        id, count = itemIdAt(bag, slot), select(2, GetContainerItemInfo(bag, slot))
      end
      if id then
        bags[id] = (bags[id] or 0) + (count or 1)
      end
    end
  end
  return bags
end

-- The shopping list subtracts what the character already carries.
local function recordBags()
  local bags = readBags()
  if not bags then
    return
  end
  local char = character()
  char.bags = bags
  char.bagsUpdated = time()
  -- Bags change while playing, which is what "last played" means.
  char.updated = char.bagsUpdated
end

local function recordDisenchant()
  local item = pendingDisenchant
  pendingDisenchant = nil
  if not item then
    return
  end
  local mats = {}
  for slot = 1, (GetNumLootItems and GetNumLootItems() or 0) do
    local link = GetLootSlotLink and GetLootSlotLink(slot)
    local id = itemId(link)
    local count = select(3, GetLootSlotInfo(slot))
    if id then
      mats[#mats + 1] = {id = id, count = count or 1}
    end
  end
  AnvilbookExportDB = AnvilbookExportDB or {}
  local log = AnvilbookExportDB.disenchants or {}
  AnvilbookExportDB.disenchants = log
  log[#log + 1] = {time = time(), item = item, mats = mats}
  while #log > DISENCHANT_LOG_LIMIT do
    table.remove(log, 1)
  end
  ns.invalidate()
end

-- Reports what the client's API returns, because it differs from retail and from classic.
local function probe()
  local api = C_TradeSkillUI or {}
  local info = api.GetBaseProfessionInfo and api.GetBaseProfessionInfo()
  local all = api.GetAllRecipeIDs and api.GetAllRecipeIDs() or {}
  local okFiltered, filtered = pcall(api.GetFilteredRecipeIDs or function() end)
  filtered = okFiltered and type(filtered) == "table" and filtered or nil
  local _, categoryCount = categorySet(api)
  local first = (filtered or all)[1]
  local recipe = first and api.GetRecipeInfo and api.GetRecipeInfo(first)
  local out = {
    profession = info and info.professionName,
    professionID = info and info.professionID,
    allCount = #all,
    filteredCount = filtered and #filtered,
    categoryCount = categoryCount,
    firstRecipe = recipe,
    firstCategoryInfo = recipe and recipe.categoryID and api.GetCategoryInfo and api.GetCategoryInfo(recipe.categoryID),
  }
  AnvilbookExportDB = AnvilbookExportDB or {}
  AnvilbookExportDB.probe = out
  print(("Anvilbook probe: profession=%s all=%d filtered=%s categories=%s first=%s"):format(
    tostring(out.profession), out.allCount, tostring(out.filteredCount), tostring(out.categoryCount),
    tostring(recipe and recipe.name)))
end

ns.probe = probe
ns.readBags = readBags
ns.characterKey = function()
  return UnitName("player") .. " - " .. GetRealmName()
end
-- Model.lua replaces this; the recorder loads first.
ns.invalidate = function() end

frame:SetScript("OnEvent", function(_, event, ...)
  if event == "UNIT_SPELLCAST_SENT" then
    local unit, target, _, spellID = ...
    if unit == "player" and spellID == DISENCHANT_SPELL then
      pendingDisenchant = bagItem(target)
    end
    return
  end
  if event == "LOOT_OPENED" or event == "BAG_UPDATE_DELAYED" then
    local ok, err = pcall(event == "LOOT_OPENED" and recordDisenchant or recordBags)
    if not ok then
      geterrorhandler()(err)
    end
    return
  end
  run(event)
end)
frame:RegisterEvent("TRADE_SKILL_SHOW")
-- Registering an event this client does not know raises an error.
for _, event in ipairs({"TRADE_SKILL_UPDATE", "TRADE_SKILL_LIST_UPDATE", "TRADE_SKILL_DATA_SOURCE_CHANGED",
                        "UNIT_SPELLCAST_SENT", "LOOT_OPENED", "BAG_UPDATE_DELAYED"}) do
  pcall(frame.RegisterEvent, frame, event)
end
