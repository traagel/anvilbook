-- usage: luajit addon_harness_modern.lua <path to AnvilbookExport.lua>
-- Stubs the retail C_TradeSkillUI API that WoW Forever (1.60.1) uses.
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
-- GetAllRecipeIDs on this client also returns other professions' recipes (555 is Cooking).
local category = {[111] = 10, [222] = 11, [333] = 10, [444] = 10, [555] = 99}
local state = {profession = {professionName = "Blacksmithing", skillLevel = 147, maxSkillLevel = 150}}

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
state.categories = {10}
state.filtered = nil
function C_Item_GetItemNameByID(id) return "Item " .. id end
C_Item = {GetItemNameByID = C_Item_GetItemNameByID}

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
function UnitName() return "Thordak" end
function GetRealmName() return "Classic Beta PvP" end
local errors, printed = {}, {}
function geterrorhandler() return function(e) errors[#errors + 1] = e end end
function print(...) printed[#printed + 1] = table.concat({...}, " ") end
time = os.time

AnvilbookExportDB = {version = 1, characters = {["Stale - Realm"] = {professions = {}}}}
assert(loadfile(arg[1]))("AnvilbookExport", {})
assert(handler and registered.TRADE_SKILL_SHOW and registered.TRADE_SKILL_LIST_UPDATE, "events registered")

handler(frame, "TRADE_SKILL_SHOW")
assert(#errors == 0, "no errors: " .. tostring(errors[1]))
assert(AnvilbookExportDB.characters["Stale - Realm"] == nil, "data from an older addon version is cleared")
local char = AnvilbookExportDB.characters["Thordak - Classic Beta PvP"]
local bs = char.professions["Blacksmithing"]
assert(bs.rank == 147 and bs.maxRank == 150, "skill level recorded")

local poniard = bs.recipes[3490]
assert(poniard and poniard.name == "Deadly Bronze Poniard", "recipe keyed by output item")
assert(poniard.minMade == 1 and poniard.maxMade == 1, "quantities recorded")
assert(poniard.difficulty == "optimal", "difficulty mapped, got " .. tostring(poniard.difficulty))
assert(#poniard.reagents == 2, "only basic reagents, got " .. #poniard.reagents)
assert(poniard.reagents[1].id == 2841 and poniard.reagents[1].count == 4, "reagent id and count")
assert(poniard.reagents[1].name == "Item 2841", "reagent name looked up")

assert(bs.recipes[2841].maxMade == 2 and bs.recipes[2841].difficulty == "easy", "bronze bar recorded")
assert(bs.recipes[4444] == nil, "unlearned recipe skipped")
assert(bs.recipes[279981] == nil, "another profession's recipe skipped")
assert(printed[#printed] == "Anvilbook: 2 Blacksmithing recipes recorded", "chat line, got " .. tostring(printed[#printed]))
assert(AnvilbookExportDB.debug and AnvilbookExportDB.debug.api == "modern", "api recorded")
assert(AnvilbookExportDB.debug.recipeCount == 5, "recipe count recorded")
assert(AnvilbookExportDB.debug.categories == 2, "category count recorded")

bs.recipes[123456] = {name = "Stale recipe from a mixed-up export"}
handler(frame, "TRADE_SKILL_LIST_UPDATE")
assert(bs.recipes[123456] == nil, "a verified list replaces old recipes")
assert(bs.recipes[3490], "current recipes stay")

-- A retry after the window closed cannot tell professions apart, so it must record nothing.
state.categories = {}
state.profession = {professionName = "First Aid", skillLevel = 1, maxSkillLevel = 75}
handler(frame, "TRADE_SKILL_LIST_UPDATE")
assert(char.professions["First Aid"] == nil, "nothing recorded without categories or a filtered list")
assert(AnvilbookExportDB.lastError == nil, "and it is not an error")

-- This client returns nothing from GetCategories, so the window's own list is used.
state.filtered = {111, 222, 333, 444}
state.profession = {professionName = "Blacksmithing", skillLevel = 147, maxSkillLevel = 150}
handler(frame, "TRADE_SKILL_LIST_UPDATE")
local bs2 = char.professions["Blacksmithing"]
assert(bs2.recipes[3490] and bs2.recipes[2841], "recorded from the filtered list")
assert(bs2.recipes[279981] == nil, "the other profession's recipe is not in the filtered list")
assert(AnvilbookExportDB.debug.source == "filtered", "source recorded, got " .. tostring(AnvilbookExportDB.debug.source))
assert(AnvilbookExportDB.debug.filteredCount == 4, "filtered count recorded")
state.categories = {10}

state.profession = nil
handler(frame, "TRADE_SKILL_LIST_UPDATE")
assert(AnvilbookExportDB.lastError == nil, "missing profession info is not an error")
assert(bs.recipes[3490], "recipes are kept")

io.write("OK\n")
