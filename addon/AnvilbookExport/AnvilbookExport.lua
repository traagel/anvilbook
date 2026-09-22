local frame = CreateFrame("Frame")
local busy = false

local function itemId(link)
  return link and tonumber(link:match("item:(%d+)"))
end

local function record(db, expand)
  local profession, rank, maxRank = GetTradeSkillLine()
  if not profession or profession == "UNKNOWN" then
    return nil
  end
  -- Collapsed headers hide their recipes from GetTradeSkillInfo.
  if expand then
    ExpandTradeSkillSubClass(0)
  end

  db.version = 1
  db.characters = db.characters or {}
  local key = UnitName("player") .. " - " .. GetRealmName()
  local char = db.characters[key] or {professions = {}}
  db.characters[key] = char
  local prof = char.professions[profession] or {recipes = {}}
  char.professions[profession] = prof
  prof.rank, prof.maxRank = rank, maxRank
  prof.updated = time()
  char.updated = prof.updated

  local recorded = 0
  for i = 1, GetNumTradeSkills() do
    local name, kind = GetTradeSkillInfo(i)
    local id = kind ~= "header" and itemId(GetTradeSkillItemLink(i))
    if id then
      local reagents = {}
      for r = 1, GetTradeSkillNumReagents(i) do
        local reagentName, _, count = GetTradeSkillReagentInfo(i, r)
        local reagentId = itemId(GetTradeSkillReagentItemLink(i, r))
        -- Links are nil until the client caches the item; a later update fills them in.
        if not reagentId or not count then
          reagents = nil
          break
        end
        reagents[r] = {id = reagentId, count = count, name = reagentName}
      end
      if reagents then
        local minMade, maxMade = GetTradeSkillNumMade(i)
        prof.recipes[id] = {name = name, minMade = minMade, maxMade = maxMade, difficulty = kind, reagents = reagents}
        recorded = recorded + 1
      end
    end
  end
  return profession, recorded
end

frame:RegisterEvent("TRADE_SKILL_SHOW")
frame:RegisterEvent("TRADE_SKILL_UPDATE")
frame:SetScript("OnEvent", function(_, event)
  -- ExpandTradeSkillSubClass fires TRADE_SKILL_UPDATE.
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
  end
end)
