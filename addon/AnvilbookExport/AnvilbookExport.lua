local frame = CreateFrame("Frame")
local busy = false

local function itemId(link)
  return link and tonumber(link:match("item:(%d+)"))
end

local function record(expand)
  local profession, rank, maxRank = GetTradeSkillLine()
  if not profession or profession == "UNKNOWN" then
    return
  end
  -- Collapsed headers hide their recipes from GetTradeSkillInfo.
  if expand then
    ExpandTradeSkillSubClass(0)
  end

  AnvilbookExportDB = AnvilbookExportDB or {}
  local db = AnvilbookExportDB
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
      end
    end
  end
end

frame:RegisterEvent("TRADE_SKILL_SHOW")
frame:RegisterEvent("TRADE_SKILL_UPDATE")
frame:SetScript("OnEvent", function(_, event)
  -- ExpandTradeSkillSubClass fires TRADE_SKILL_UPDATE.
  if busy then
    return
  end
  busy = true
  local ok, err = pcall(record, event == "TRADE_SKILL_SHOW")
  busy = false
  if not ok then
    geterrorhandler()(err)
  end
end)
