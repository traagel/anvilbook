-- Bumped when a fix makes older saved data wrong; it is then thrown away.
local VERSION = 4

local frame = CreateFrame("Frame")
local busy = false

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
  if not profession then
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

local function run(event)
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
  if profession and event == "TRADE_SKILL_SHOW" then
    print(("Anvilbook: %d %s recipes recorded"):format(recorded, profession))
    -- Item data is cached late, and the client may have no update event.
    if C_Timer then
      C_Timer.After(1, function() run("RETRY") end)
      C_Timer.After(3, function() run("RETRY") end)
    end
  end
end

frame:SetScript("OnEvent", function(_, event) run(event) end)
frame:RegisterEvent("TRADE_SKILL_SHOW")
-- Registering an event this client does not know raises an error.
for _, event in ipairs({"TRADE_SKILL_UPDATE", "TRADE_SKILL_LIST_UPDATE", "TRADE_SKILL_DATA_SOURCE_CHANGED"}) do
  pcall(frame.RegisterEvent, frame, event)
end
