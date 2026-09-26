-- usage: luajit addon_harness_modern.lua <path to AnvilbookExport.lua>
-- Stubs the retail C_TradeSkillUI API that WoW Forever (1.60.1) uses, including the lag
-- where the open profession changes before its recipe list does.
local schematics = {
  [111] = {recipeID = 111, name = "Deadly Bronze Poniard", outputItemID = 3490, quantityMin = 1, quantityMax = 1,
           reagentSlotSchematics = {
             {reagentType = 1, quantityRequired = 4, reagents = {{itemID = 2841}}},
             {reagentType = 1, quantityRequired = 1, reagents = {{itemID = 3466}}},
             {reagentType = 2, quantityRequired = 1, reagents = {{itemID = 9999}}},
           }},
  [222] = {recipeID = 222, name = "Bronze Bar", outputItemID = 2841, quantityMin = 2, quantityMax = 2,
           reagentSlotSchematics = {
             {reagentType = 1, quantityRequired = 1, reagents = {{itemID = 2840}}},
             {reagentType = 1, quantityRequired = 1, reagents = {{itemID = 3576}}},
           }},
  [333] = {recipeID = 333, name = "Unlearned Thing", outputItemID = 4444, quantityMin = 1, quantityMax = 1,
           reagentSlotSchematics = {{reagentType = 1, quantityRequired = 1, reagents = {{itemID = 2841}}}}},
  [444] = {recipeID = 444, name = "Enchant Something", quantityMin = 1, quantityMax = 1, reagentSlotSchematics = {}},
  [555] = {recipeID = 555, name = "Basic Campfire", outputItemID = 279981, quantityMin = 1, quantityMax = 1,
           reagentSlotSchematics = {{reagentType = 1, quantityRequired = 1, reagents = {{itemID = 4470}}}}},
}
local difficulty = {[111] = 1, [222] = 3, [333] = 1, [444] = 2, [555] = 3}
local category = {[111] = 10, [222] = 11, [333] = 10, [444] = 10, [555] = 99}
local BLACKSMITHING = {professionName = "Blacksmithing", professionID = 164, skillLevel = 147, maxSkillLevel = 150}
local COOKING = {professionName = "Cooking", professionID = 185, skillLevel = 69, maxSkillLevel = 75}
local state = {profession = BLACKSMITHING, categories = {}, filtered = {555}}

Enum = {
  TradeskillRelativeDifficulty = {Optimal = 1, Medium = 2, Easy = 3, Trivial = 4},
  CraftingReagentType = {Basic = 1, Modifying = 2, Finishing = 3},
}
C_TradeSkillUI = {
  GetBaseProfessionInfo = function() return state.profession end,
  GetAllRecipeIDs = function() return {111, 222, 333, 444, 555} end,
  GetRecipeInfo = function(id)
    return {recipeID = id, name = schematics[id].name, learned = id ~= 333,
            relativeDifficulty = difficulty[id], categoryID = category[id]}
  end,
  GetRecipeSchematic = function(id) return schematics[id] end,
  GetCategories = function() return state.categories end,
  GetSubCategories = function(id) return id == 10 and {11} or {} end,
  GetFilteredRecipeIDs = function() return state.filtered end,
}
C_Item = {GetItemNameByID = function(id) return "Item " .. id end}

local frame, handler
local registered, known = {}, {TRADE_SKILL_SHOW = true, TRADE_SKILL_LIST_UPDATE = true}
function CreateFrame()
  frame = {
    RegisterEvent = function(_, e)
      if not known[e] then error('Attempt to register unknown event "' .. e .. '"') end
      registered[e] = true
    end,
    SetScript = function(_, _, fn) handler = fn end,
  }
  return frame
end
local timers = {}
C_Timer = {After = function(_, fn) timers[#timers + 1] = fn end}
local function runTimers()
  local due = timers
  timers = {}
  for _, fn in ipairs(due) do fn() end
end
function UnitName() return "Thordak" end
function GetRealmName() return "Classic Beta PvP" end
local errors, printed = {}, {}
function geterrorhandler() return function(e) errors[#errors + 1] = e end end
function print(...) printed[#printed + 1] = table.concat({...}, " ") end
time = os.time
SlashCmdList = {}

AnvilbookExportDB = {version = 1, characters = {["Stale - Realm"] = {professions = {}}}}
assert(loadfile(arg[1]))("AnvilbookExport", {})
assert(handler and registered.TRADE_SKILL_SHOW and registered.TRADE_SKILL_LIST_UPDATE, "events registered")

local function professions()
  local char = AnvilbookExportDB.characters and AnvilbookExportDB.characters["Thordak - Classic Beta PvP"]
  return char and char.professions or {}
end

-- The window opens before its list is switched over, so the first read must not be trusted.
handler(frame, "TRADE_SKILL_SHOW")
assert(#errors == 0, "no errors: " .. tostring(errors[1]))
assert(professions()["Blacksmithing"] == nil, "a single unstable read records nothing")

state.filtered = {111, 222, 333, 444}
runTimers()
assert(professions()["Blacksmithing"] == nil, "a changed list records nothing yet")

runTimers()
local bs = professions()["Blacksmithing"]
assert(bs, "a stable list is recorded")
assert(bs.rank == 147 and bs.maxRank == 150, "skill level recorded")
assert(AnvilbookExportDB.characters["Stale - Realm"] == nil, "data from an older addon version is cleared")

local poniard = bs.recipes[3490]
assert(poniard and poniard.name == "Deadly Bronze Poniard", "recipe keyed by output item")
assert(poniard.minMade == 1 and poniard.maxMade == 1, "quantities recorded")
assert(poniard.difficulty == "optimal", "difficulty mapped, got " .. tostring(poniard.difficulty))
assert(#poniard.reagents == 2, "only basic reagents, got " .. #poniard.reagents)
assert(poniard.reagents[1].id == 2841 and poniard.reagents[1].count == 4, "reagent id and count")
assert(poniard.reagents[1].name == "Item 2841", "reagent name looked up")
assert(bs.recipes[2841].maxMade == 2 and bs.recipes[2841].difficulty == "easy", "bronze bar recorded")
assert(bs.recipes[4444] == nil, "unlearned recipe skipped")
assert(bs.recipes[279981] == nil, "another profession's recipe is not in the window's list")
assert(printed[#printed] == "Anvilbook: 2 Blacksmithing recipes recorded", "chat line, got " .. tostring(printed[#printed]))
assert(AnvilbookExportDB.debug.source == "filtered", "source recorded, got " .. tostring(AnvilbookExportDB.debug.source))
assert(AnvilbookExportDB.debug.filteredCount == 4, "filtered count recorded")

-- Switching professions: the new profession must not inherit the old list.
state.profession = COOKING
handler(frame, "TRADE_SKILL_SHOW")
assert(professions()["Cooking"] == nil, "the old list is not stored under the new profession")
state.filtered = {555}
runTimers()
runTimers()
local cooking = professions()["Cooking"]
assert(cooking and cooking.recipes[279981], "cooking recipes recorded once stable")
assert(cooking.recipes[3490] == nil, "cooking did not get blacksmithing recipes")
assert(professions()["Blacksmithing"].recipes[3490], "blacksmithing recipes kept")

-- A window with no profession name (seen on this client) records nothing.
state.profession = {professionName = "", skillLevel = 0, maxSkillLevel = 0}
handler(frame, "TRADE_SKILL_LIST_UPDATE")
runTimers()
runTimers()
assert(professions()[""] == nil, "no profession name records nothing")
assert(AnvilbookExportDB.lastError == nil, "and it is not an error")

-- Categories are the fallback when the window has no filtered list.
state.profession = BLACKSMITHING
state.filtered = nil
state.categories = {10}
handler(frame, "TRADE_SKILL_LIST_UPDATE")
runTimers()
runTimers()
assert(AnvilbookExportDB.debug.source == "categories", "categories used, got " .. tostring(AnvilbookExportDB.debug.source))
assert(professions()["Blacksmithing"].recipes[279981] == nil, "category filter keeps other professions out")

-- Disenchanting: the cast names the item, the loot window holds the result.
known.UNIT_SPELLCAST_SENT = true
known.LOOT_OPENED = true
C_Container = {
  GetContainerNumSlots = function(bag) return bag == 0 and 2 or 0 end,
  GetContainerItemID = function(bag, slot) return bag == 0 and slot == 2 and 3490 or nil end,
}
C_Item.GetItemInfo = function(id)
  if id == 3490 then return "Deadly Bronze Poniard", "link", 2, 25 end
  return "Strange Dust", "link", 1, 5
end
C_Item.GetItemInfoInstant = function() return 3490, "Weapon", "Dagger", "INVTYPE_WEAPON", 0, 2, 15 end
local loot = {{id = 10940, count = 3}}
function GetNumLootItems() return #loot end
function GetLootSlotLink(i) return "|cffffffff|Hitem:" .. loot[i].id .. "::|h[Mat]|h|r" end
function GetLootSlotInfo(i) return "icon", "Strange Dust", loot[i].count, nil, 2 end

known.BAG_UPDATE_DELAYED = true
C_Container.GetContainerItemInfo = function(bag, slot)
  if bag == 0 and slot == 1 then return {itemID = 2841, stackCount = 19} end
  if bag == 0 and slot == 2 then return {itemID = 3490, stackCount = 1} end
end
handler(frame, "BAG_UPDATE_DELAYED")
local bagChar = AnvilbookExportDB.characters["Thordak - Classic Beta PvP"]
assert(bagChar.bags and bagChar.bags[2841] == 19 and bagChar.bags[3490] == 1, "bag contents recorded")
assert(bagChar.updated and bagChar.updated > 0, "playing marks the character as recently used")

handler(frame, "UNIT_SPELLCAST_SENT", "player", "Deadly Bronze Poniard", "cast-1", 13262)
handler(frame, "LOOT_OPENED")
local de = AnvilbookExportDB.disenchants
assert(de and #de == 1, "one disenchant recorded, got " .. tostring(de and #de))
assert(de[1].item.id == 3490 and de[1].item.quality == 2 and de[1].item.itemLevel == 25, "item recorded")
assert(de[1].item.kind == "Weapon", "weapon or armor recorded, got " .. tostring(de[1].item.kind))
assert(de[1].mats[1].id == 10940 and de[1].mats[1].count == 3, "materials recorded")

handler(frame, "LOOT_OPENED")
assert(#AnvilbookExportDB.disenchants == 1, "loot without a disenchant cast is ignored")

state.filtered = {111, 222}
SlashCmdList["ANVILBOOK"]()
local p = AnvilbookExportDB.probe
assert(p.profession == "Blacksmithing" and p.allCount == 5 and p.filteredCount == 2, "probe reports the API state")
assert(p.firstRecipe.name == "Deadly Bronze Poniard", "probe includes the first recipe")
assert(printed[#printed]:find("Anvilbook probe:"), "probe prints a line")

io.write("OK\n")
