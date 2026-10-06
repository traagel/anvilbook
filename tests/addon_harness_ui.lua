-- usage: luajit addon_harness_ui.lua <addon folder> [<AnvilbookData.lua>]
-- Loads every file in the .toc on a stub of the frame API, then drives each part of the UI.
-- Without a data file it checks the addon on live Auctionator prices only.
local dir, dataFile = arg[1], arg[2]
local errors, timers, created = {}, {}, {}

function geterrorhandler()
  return function(e)
    errors[#errors + 1] = tostring(e)
  end
end

local function check(condition, message)
  if not condition then
    error(message .. (#errors > 0 and ("\nerrors:\n" .. table.concat(errors, "\n")) or ""), 2)
  end
end

local Object = {}
local methods = {}
Object.__index = methods

local function new(kind, name, template)
  -- _text, not text: the addon keeps its own FontStrings in a "text" field.
  local o = setmetatable({kind = kind, scripts = {}, shown = true, _text = "", events = {}, checked = false,
                          enabled = true, width = 100, height = 20, lines = {}}, Object)
  if template and template:find("BasicFrameTemplate") then
    o.TitleText = new("FontString")
  end
  if name then
    _G[name] = o
  end
  created[#created + 1] = o
  return o
end

local function noop() end
for _, name in ipairs({"SetPoint", "ClearAllPoints", "SetAllPoints", "SetFrameStrata", "SetFrameLevel", "SetToplevel",
                       "SetMovable", "EnableMouse", "EnableMouseWheel", "SetClampedToScreen", "RegisterForDrag",
                       "StartMoving", "StopMovingOrSizing", "SetBackdrop", "SetBackdropColor", "RegisterForClicks",
                       "LockHighlight", "UnlockHighlight", "SetHighlightTexture", "SetAutoFocus", "ClearFocus",
                       "SetJustifyH", "SetJustifyV", "SetTextColor", "SetWordWrap", "SetSpacing", "SetColorTexture",
                       "SetTexture", "SetThickness", "SetStartPoint", "SetEndPoint", "SetItemByID", "SetHyperlink",
                       "UnregisterEvent"}) do
  methods[name] = noop
end

function methods:SetSize(w, h) self.width, self.height = w, h end
function methods:SetWidth(w) self.width = w end
function methods:SetHeight(h) self.height = h end
function methods:GetWidth() return self.width end
function methods:GetHeight() return self.height end
function methods:GetPoint() return "CENTER", UIParent, "CENTER", 0, 0 end
function methods:GetCenter() return 0, 0 end
function methods:GetEffectiveScale() return 1 end
function methods:SetScript(event, f) self.scripts[event] = f end
function methods:GetScript(event) return self.scripts[event] end
function methods:HookScript(event, f)
  local old = self.scripts[event]
  self.scripts[event] = function(...)
    if old then old(...) end
    f(...)
  end
end
function methods:RegisterEvent(event) self.events[event] = true end
function methods:Show()
  local was = self.shown
  self.shown = true
  if not was and self.scripts.OnShow then self.scripts.OnShow(self) end
end
function methods:Hide()
  local was = self.shown
  self.shown = false
  if was and self.scripts.OnHide then self.scripts.OnHide(self) end
end
function methods:IsShown() return self.shown end
function methods:SetShown(shown) if shown then self:Show() else self:Hide() end end
function methods:SetText(text)
  local kind = type(text)
  assert(kind == "string" or kind == "number" or kind == "nil", "SetText with a " .. kind)
  self._text = text and tostring(text) or ""
end
function methods:GetText() return self._text end
function methods:SetChecked(checked) self.checked = checked and true or false end
function methods:GetChecked() return self.checked end
function methods:SetEnabled(enabled) self.enabled = enabled and true or false end
function methods:HasFocus() return false end
function methods:CreateFontString() return new("FontString") end
function methods:CreateTexture() return new("Texture") end
function methods:CreateLine() return new("Line") end
function methods:SetOwner() self.lines = {} end
function methods:AddLine(text) self.lines[#self.lines + 1] = text end
function methods:AddDoubleLine(left, right) self.lines[#self.lines + 1] = left .. " = " .. right end
function methods:GetItem() return "Deadly Bronze Poniard", "|cff1eff00|Hitem:3490::|h[Deadly Bronze Poniard]|h|r" end

local function click(button, which)
  check(button.scripts.OnClick, "the button has a click handler")
  button.scripts.OnClick(button, which or "LeftButton")
end

local function fire(event, ...)
  for _, o in ipairs(created) do
    if o.events[event] and o.scripts.OnEvent then
      o.scripts.OnEvent(o, event, ...)
    end
  end
end

local function runTimers()
  local due = timers
  timers = {}
  for _, f in ipairs(due) do f() end
end

local function texts(pattern)
  local out = {}
  for _, o in ipairs(created) do
    if o._text ~= "" and o._text:find(pattern, 1, true) then
      out[#out + 1] = o
    end
  end
  return out
end

UIParent = new("Frame", "UIParent")
Minimap = new("Frame", "Minimap")
GameTooltip = new("GameTooltip", "GameTooltip")
ItemRefTooltip = new("GameTooltip", "ItemRefTooltip")
function CreateFrame(kind, name, _, template) return new(kind, name, template) end
UISpecialFrames, SlashCmdList = {}, {}
tinsert = table.insert
time, date = os.time, os.date
BackdropTemplateMixin = {}
C_Timer = {After = function(_, f) timers[#timers + 1] = f end}
function GetMoney() return 34310 end
function UnitName() return "Thordak" end
function GetRealmName() return "Classic Beta PvP" end
function GetCursorPosition() return 10, 10 end

local bags = {[2840] = 2}
C_Container = {
  GetContainerNumSlots = function(bag) return bag == 0 and 20 or 0 end,
  GetContainerItemInfo = function(bag, slot)
    local i = 0
    for id, count in pairs(bags) do
      i = i + 1
      if bag == 0 and i == slot then return {itemID = id, stackCount = count} end
    end
  end,
}
local NAMES = {[2770] = "Copper Ore", [2771] = "Tin Ore", [2840] = "Copper Bar", [3576] = "Tin Bar",
               [2841] = "Bronze Bar", [3490] = "Deadly Bronze Poniard"}
C_Item = {
  GetItemInfo = function(id)
    if id == 3490 then return NAMES[id], "link", 2, 25, 20, "Weapon", "Daggers", 1, "", 0, 1500, 2, 15 end
    if NAMES[id] then return NAMES[id], "link", 1, 10, 0, "Trade Goods", "Metal", 20, "", 0, 10, 7, 0 end
  end,
  GetItemIconByID = function() return 134400 end,
  RequestLoadItemDataByID = function() end,
}

local optionsOpened, tooltipHook
Settings = {
  RegisterCanvasLayoutCategory = function(_, name) return {ID = 42, name = name, GetID = function(self) return self.ID end} end,
  RegisterAddOnCategory = function() end,
  OpenToCategory = function(id) optionsOpened = id end,
}
Enum = {TooltipDataType = {Item = 0}}
TooltipDataProcessor = {AddTooltipPostCall = function(_, f) tooltipHook = f end}

local live, searched = {}, nil
if not dataFile then
  live = {[2770] = 57, [2771] = 200, [2840] = 73, [3576] = 248, [2841] = 220, [3490] = 17500}
end
Auctionator = {API = {v1 = {
  GetAuctionPriceByItemID = function(_, id) return live[id] end,
  GetVendorPriceByItemID = function() return nil end,
  RegisterForDBUpdate = function() end,
  MultiSearchExact = function(_, terms) searched = terms end,
}}}

AnvilbookExportDB = {
  version = 5,
  characters = {["Thordak - Classic Beta PvP"] = {professions = {
    Smelting = {rank = 120, maxRank = 150, recipes = {
      [2840] = {name = "Copper Bar", minMade = 1, maxMade = 1, difficulty = "trivial", reagents = {{id = 2770, count = 1}}},
      [3576] = {name = "Tin Bar", minMade = 1, maxMade = 1, difficulty = "easy", reagents = {{id = 2771, count = 1}}},
      [2841] = {name = "Bronze Bar", minMade = 2, maxMade = 2, difficulty = "medium",
                reagents = {{id = 2840, count = 1}, {id = 3576, count = 1}}}}},
    Blacksmithing = {rank = 120, maxRank = 150, recipes = {
      [3490] = {name = "Deadly Bronze Poniard", minMade = 1, maxMade = 1, difficulty = "optimal",
                reagents = {{id = 2841, count = 4}}}}},
  }}, ["Alt - Classic Beta PvP"] = {professions = {}}},
  disenchants = {{time = 1, item = {id = 3490, quality = 2, itemLevel = 25, kind = "Weapon"},
                  mats = {{id = 10940, count = 2}}}},
}

local ns = {}
local toc = assert(io.open(dir .. "/AnvilbookExport.toc")):read("*a")
for file in toc:gmatch("[^\r\n]+") do
  if not file:find("^##") and file:find("%S") then
    local path = dir .. "/" .. file:gsub("\\", "/")
    if file == "AnvilbookData.lua" and dataFile then
      path = dataFile
    end
    assert(loadfile(path))("AnvilbookExport", ns)
  end
end
check(dataFile == nil or type(AnvilbookData) == "table", "the data file sets AnvilbookData")
check(dataFile ~= nil or AnvilbookData == nil, "the shipped data file is empty")

fire("PLAYER_LOGIN")
runTimers()
check(AnvilbookMinimapButton and AnvilbookMinimapButton.shown, "the minimap button shows")

SlashCmdList.ANVILBOOK("")
runTimers()
check(AnvilbookFrame and AnvilbookFrame.shown, "/anvilbook opens the window")
local rows = ns.rows()
check(#rows > 0, "there are craft rows")
check(#texts("Deadly Bronze Poniard") > 0, "the crafts table shows the poniard")
if dataFile then
  check(#texts("Prices: app scan") > 0, "the status line names the app scan")
else
  check(#texts("live from Auctionator for 6 items") > 0, "the status line counts the live prices")
  check(rows[1].listed == nil, "a live-only price has no listed count")
end

ns.openPlan(3490)
check(#texts("Make ") > 0, "the plan describes the batch")
local plan = AnvilbookExportDB.ui.activePlan
check(plan and plan.item_id == 3490 and #plan.purchases > 0, "the plan is stored for the AH panel")
check(plan.before[2840] == 2, "the plan records the bags at plan time")

AuctionHouseFrame = new("Frame", "AuctionHouseFrame")
fire("AUCTION_HOUSE_SHOW")
check(AnvilbookAhPanel and AnvilbookAhPanel.shown, "the shopping panel opens beside the AH")
check(#texts("ReadyCheck-Waiting") > 0, "nothing is bought yet")
for _, p in ipairs(plan.purchases) do
  bags[p.item_id] = (bags[p.item_id] or 0) + p.quantity
end
fire("BAG_UPDATE_DELAYED")
check(#texts("Everything is bought.") > 0, "buying the list ticks every row")
click(AnvilbookAhPanel.search)
check(searched and #searched == #plan.purchases, "Auctionator searches for the list")
fire("AUCTION_HOUSE_CLOSED")
check(not AnvilbookAhPanel.shown, "the panel closes with the AH")

GameTooltip:SetOwner()
tooltipHook(GameTooltip, {id = 3490})
local lines = table.concat(GameTooltip.lines, "\n")
check(lines:find("craft profit", 1, true), "the tooltip shows the craft profit:\n" .. lines)
check(lines:find("disenchant", 1, true) == nil, "no disenchant line for a non-enchanter")
if dataFile then
  check(lines:find("listed", 1, true) and lines:find("since the scan before", 1, true),
        "the tooltip shows the listed count and the trend:\n" .. lines)
end

local tabs = AnvilbookFrame.tabButtons
for _, key in ipairs({"crafts", "plan", "history", "sellthrough", "share", "settings"}) do
  click(tabs[key])
  runTimers()
end

ns.openTab("history")
local search = texts("Type an item name")[1] or texts("Run the anvilbook app")[1]
check(search, "the history tab explains itself")
if dataFile then
  local box
  for _, o in ipairs(created) do
    if o.kind == "EditBox" and o.scripts.OnTextChanged then box = o end
  end
  box:SetText("bronze")
  box.scripts.OnTextChanged(box, true)
  check(AnvilbookPopup.shown, "typing lists matching items")
  local first
  for _, o in ipairs(created) do
    if o.kind == "Button" and o.value and o.shown and not first then first = o end
  end
  click(first)
  local drawn = 0
  for _, o in ipairs(created) do
    if o.kind == "Line" and o.shown then drawn = drawn + 1 end
  end
  check(drawn == 2, "picking an item draws its price and count lines, got " .. drawn)
end

ns.openTab("sellthrough")
if dataFile then
  check(#texts("items)") >= 2, "the from and to scans are named")
  -- test_addon_ui.py lists every item 100 times in the first scan and 80 in the second.
  check(#texts("-20") > 0, "sell-through shows the drop in the listed count")
else
  check(#texts("Run the anvilbook app to see this.") > 0, "sell-through needs the app")
end

ns.openTab("settings")
local edits = {}
for _, o in ipairs(created) do
  if o.kind == "EditBox" and o._text == "0.05" then edits.ah_cut = o end
end
check(edits.ah_cut, "the AH cut field shows the setting")
edits.ah_cut:SetText("0.06")
click(texts("Save")[1])
check(AnvilbookExportDB.edits.ah_cut.value == 0.06, "a saved setting becomes an edit for the app")
runTimers()
check(ns.model().settings.ah_cut == 0.06, "the edit applies in game at once")

ns.openTab("share")
local publish = texts("Thordak - Classic Beta PvP")[1]
check(publish, "the share tab lists the characters")
if dataFile then
  click(texts("Push now")[1])
  check(AnvilbookExportDB.pushRequested, "push now is stored for the app")
end

local box = texts("Crafts tab")[1]
check(box, "the options list the crafts tab")
local crafts
for _, o in ipairs(created) do
  if o.kind == "CheckButton" and o.label == box then crafts = o end
end
crafts:SetChecked(false)
click(crafts)
check(AnvilbookExportDB.ui.toggles.crafts == false and not tabs.crafts.shown, "the crafts tab is off")
local shareBox
for _, o in ipairs(created) do
  if o.kind == "CheckButton" and o.label == texts("Share tab")[1] then shareBox = o end
end
shareBox:SetChecked(false)
click(shareBox)
check(not AnvilbookFrame.panels.share.shown, "turning off the open tab moves the window to another tab")
check(AnvilbookFrame.panels.plan.shown, "the first tab still on takes its place")

local merged = ns.Calc.merge({}, {Mining = {recipes = {[1] = {minMade = 0, reagents = {}}}}})
check(merged[1].createdBy[1].amount[1] == 1, "a zero count reads as one, like the app")

UnitName = function() return "Alt" end
fire("AUCTION_HOUSE_SHOW")
check(#texts("No shopping list") > 0, "another character does not see this character's plan")
SlashCmdList.ANVILBOOK("options")
check(optionsOpened == 42, "/anvilbook options opens the panel")
click(AnvilbookMinimapButton)
check(not AnvilbookFrame.shown, "the minimap button closes the window")

runTimers()
check(#errors == 0, "no errors")
io.write("OK\n")
