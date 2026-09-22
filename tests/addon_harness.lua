-- usage: luajit addon_harness.lua <path to AnvilbookExport.lua>
local state = {
  line = {"Blacksmithing", 147, 150},
  expanded = 0,
  skills = {
    {name = "Daggers", kind = "header"},
    {name = "Deadly Bronze Poniard", kind = "optimal", made = {1, 1},
     link = "|cff1eff00|Hitem:3490::::::::20:::::|h[Deadly Bronze Poniard]|h|r",
     reagents = {{"Bronze Bar", 4, "|cffffffff|Hitem:2841::|h[Bronze Bar]|h|r"},
                 {"Strong Flux", 1, "|cffffffff|Hitem:3466::|h[Strong Flux]|h|r"}}},
    {name = "Heavy Sharpening Stone", kind = "medium", made = {1, 1},
     link = "|cffffffff|Hitem:2871::|h[Heavy Sharpening Stone]|h|r",
     reagents = {{"Heavy Stone", 1, nil}}},
  },
}

local frame, handler
local registered, known = {}, {TRADE_SKILL_SHOW = true}
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
function GetTradeSkillLine() return unpack(state.line) end
function ExpandTradeSkillSubClass()
  state.expanded = state.expanded + 1
  handler(frame, "TRADE_SKILL_UPDATE")
end
function GetNumTradeSkills() return #state.skills end
function GetTradeSkillInfo(i) local s = state.skills[i]; return s.name, s.kind, 0, true end
function GetTradeSkillItemLink(i) return state.skills[i].link end
function GetTradeSkillNumMade(i) return unpack(state.skills[i].made) end
function GetTradeSkillNumReagents(i) return #state.skills[i].reagents end
function GetTradeSkillReagentInfo(i, r) local x = state.skills[i].reagents[r]; return x[1], "icon", x[2], 0 end
function GetTradeSkillReagentItemLink(i, r) return state.skills[i].reagents[r][3] end
function UnitName() return "Thordak" end
function GetRealmName() return "Classic Beta PvP" end
local errors, printed = {}, {}
function geterrorhandler() return function(e) errors[#errors + 1] = e end end
function print(...) printed[#printed + 1] = table.concat({...}, " ") end
time = os.time
SlashCmdList = {}

assert(loadfile(arg[1]))("AnvilbookExport", {})

assert(handler and registered.TRADE_SKILL_SHOW, "SHOW is registered although the update events are unknown")

local function fire(event) handler(frame, event) end
local function prof(name) return AnvilbookExportDB.characters["Thordak - Classic Beta PvP"].professions[name] end

fire("TRADE_SKILL_SHOW")
assert(state.expanded == 1, "headers expanded once, got " .. state.expanded)
local bs = prof("Blacksmithing")
assert(bs.rank == 147 and bs.maxRank == 150, "rank recorded")
local poniard = bs.recipes[3490]
assert(poniard and poniard.name == "Deadly Bronze Poniard" and poniard.difficulty == "optimal", "poniard recorded")
assert(poniard.minMade == 1 and poniard.maxMade == 1, "made counts recorded")
assert(poniard.reagents[1].id == 2841 and poniard.reagents[1].count == 4 and poniard.reagents[1].name == "Bronze Bar",
       "first reagent recorded")
assert(poniard.reagents[2].id == 3466, "second reagent recorded")
assert(bs.recipes[2871] == nil, "recipe with an uncached reagent is skipped")
assert(printed[#printed] == "Anvilbook: 1 Blacksmithing recipes recorded", "chat line, got " .. tostring(printed[#printed]))
assert(AnvilbookExportDB.lastEvent.event == "TRADE_SKILL_SHOW", "last event stored")

local realCount = GetNumTradeSkills
GetNumTradeSkills = function() error("boom") end
fire("TRADE_SKILL_UPDATE")
assert(AnvilbookExportDB.lastError and AnvilbookExportDB.lastError:find("boom"), "error stored")
assert(#errors == 1, "error reported to the error handler")
GetNumTradeSkills = realCount
fire("TRADE_SKILL_UPDATE")
assert(AnvilbookExportDB.lastError == nil, "a successful record clears the error")

state.skills[3].reagents[1][3] = "|cffffffff|Hitem:2838::|h[Heavy Stone]|h|r"
table.remove(state.skills, 2)
assert(#timers == 2, "SHOW schedules 2 retries")
runTimers()
assert(state.expanded == 1, "a retry does not expand again")
assert(bs.recipes[2871] and bs.recipes[2871].reagents[1].id == 2838, "cached recipe added by the retry")
assert(bs.recipes[3490], "recipes hidden by a filter are kept")

state.line = {"UNKNOWN", 0, 0}
fire("TRADE_SKILL_UPDATE")
assert(prof("UNKNOWN") == nil, "no profession open records nothing")

state.line = {"Smelting", 99, 150}
state.skills = {{name = "Smelt Bronze", kind = "easy", made = {2, 2},
                 link = "|cffffffff|Hitem:2841::|h[Bronze Bar]|h|r",
                 reagents = {{"Copper Bar", 1, "|Hitem:2840::|h[Copper Bar]|h"}, {"Tin Bar", 1, "|Hitem:3576::|h[Tin Bar]|h"}}}}
fire("TRADE_SKILL_SHOW")
assert(prof("Smelting").recipes[2841].minMade == 2, "smelting recorded under its own name")

io.write("OK\n")
