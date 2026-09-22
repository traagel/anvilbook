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
}
local difficulty = {[111] = 1, [222] = 3, [333] = 1, [444] = 2}
local state = {profession = {professionName = "Blacksmithing", skillLevel = 147, maxSkillLevel = 150}}

Enum = {
  TradeskillRelativeDifficulty = {Optimal = 1, Medium = 2, Easy = 3, Trivial = 4},
  CraftingReagentType = {Basic = 1, Modifying = 2, Finishing = 3},
}
C_TradeSkillUI = {
  GetBaseProfessionInfo = function() return state.profession end,
  GetAllRecipeIDs = function() return {111, 222, 333, 444} end,
  GetRecipeInfo = function(id)
    return {recipeID = id, name = schematics[id].name, learned = id ~= 333, relativeDifficulty = difficulty[id]}
  end,
  GetRecipeSchematic = function(id) return schematics[id] end,
}
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

assert(loadfile(arg[1]))("AnvilbookExport", {})
assert(handler and registered.TRADE_SKILL_SHOW and registered.TRADE_SKILL_LIST_UPDATE, "events registered")

handler(frame, "TRADE_SKILL_SHOW")
assert(#errors == 0, "no errors: " .. tostring(errors[1]))
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
assert(printed[#printed] == "Anvilbook: 2 Blacksmithing recipes recorded", "chat line, got " .. tostring(printed[#printed]))
assert(AnvilbookExportDB.debug and AnvilbookExportDB.debug.api == "modern", "api recorded")
assert(AnvilbookExportDB.debug.recipeCount == 4, "recipe count recorded")

state.profession = nil
handler(frame, "TRADE_SKILL_LIST_UPDATE")
assert(AnvilbookExportDB.lastError == nil, "missing profession info is not an error")
assert(bs.recipes[3490], "recipes are kept")

io.write("OK\n")
