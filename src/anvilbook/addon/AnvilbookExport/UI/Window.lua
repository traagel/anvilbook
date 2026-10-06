local _, ns = ...
local W = ns.W

local tabs, order = {}, {}
local frame, active

function ns.ui()
  AnvilbookExportDB = AnvilbookExportDB or {}
  local ui = AnvilbookExportDB.ui or {}
  AnvilbookExportDB.ui = ui
  ui.toggles = ui.toggles or {}
  return ui
end

function ns.enabled(key)
  return ns.ui().toggles[key] ~= false
end

-- def: {key, label, create(panel), refresh(panel)}; tabs show in the order their files load.
function ns.addTab(def)
  tabs[def.key] = def
  order[#order + 1] = def.key
end

local function firstEnabled()
  for _, key in ipairs(order) do
    if ns.enabled(key) then
      return key
    end
  end
end

local function status()
  local problem = ns.dataProblem()
  if problem then
    return "|cffff6060" .. problem .. "|r"
  end
  local m = ns.model()
  local scans = m.data and m.data.scans or {}
  local text
  if #scans > 0 then
    text = ("Prices: app scan %s ago"):format(W.age(time() - scans[#scans].time))
  else
    text = "No app data yet: run the anvilbook app, then /reload"
  end
  if m.live > 0 then
    text = text .. (", live from Auctionator for %d items"):format(m.live)
  end
  return text .. ".   " .. m.character
end

local function layoutTabs()
  local x = 0
  for _, key in ipairs(order) do
    local b = frame.tabButtons[key]
    if ns.enabled(key) then
      b:ClearAllPoints()
      b:SetPoint("TOPLEFT", 12 + x, -28)
      b:Show()
      x = x + b:GetWidth() + 2
    else
      b:Hide()
    end
    if key == active then
      b:LockHighlight()
    else
      b:UnlockHighlight()
    end
  end
end

local function create()
  frame = CreateFrame("Frame", "AnvilbookFrame", UIParent, "BasicFrameTemplateWithInset")
  frame:SetSize(780, 480)
  frame:SetFrameStrata("HIGH")
  frame:SetToplevel(true)
  frame:SetMovable(true)
  frame:EnableMouse(true)
  frame:SetClampedToScreen(true)
  frame:RegisterForDrag("LeftButton")
  frame:SetScript("OnDragStart", frame.StartMoving)
  frame:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    local point, _, relative, x, y = self:GetPoint()
    ns.ui().point = {point, relative, x, y}
  end)
  local saved = ns.ui().point
  if saved then
    frame:SetPoint(saved[1], UIParent, saved[2], saved[3], saved[4])
  else
    frame:SetPoint("CENTER")
  end
  if frame.TitleText then
    frame.TitleText:SetText("Anvilbook")
  end
  tinsert(UISpecialFrames, "AnvilbookFrame")
  frame.tabButtons, frame.panels = {}, {}
  for _, key in ipairs(order) do
    frame.tabButtons[key] = W.button(frame, tabs[key].label, 96, function()
      ns.showTab(key)
    end)
  end
  frame.status = W.label(frame, "", "GameFontDisableSmall")
  frame.status:SetPoint("BOTTOMLEFT", 14, 9)
  frame.status:SetPoint("BOTTOMRIGHT", -14, 9)
  frame:SetScript("OnHide", W.hidePopup)
  frame:Hide()
end

function ns.refresh()
  if not (frame and frame:IsShown()) then
    return
  end
  if active and not ns.enabled(active) then
    return ns.showTab(nil)
  end
  layoutTabs()
  ns.safe(function()
    frame.status:SetText(status())
  end)
  local def = active and tabs[active]
  if def and def.refresh then
    ns.safe(def.refresh, frame.panels[active])
  end
end

function ns.showTab(key)
  if not frame then
    create()
  end
  if not (key and ns.enabled(key)) then
    key = firstEnabled()
  end
  active = key
  for _, panel in pairs(frame.panels) do
    panel:Hide()
  end
  W.hidePopup()
  if key then
    local panel = frame.panels[key]
    if not panel then
      panel = CreateFrame("Frame", nil, frame)
      panel:SetPoint("TOPLEFT", 12, -56)
      panel:SetPoint("BOTTOMRIGHT", -12, 26)
      frame.panels[key] = panel
      ns.safe(tabs[key].create, panel)
    end
    panel:Show()
  end
  ns.refresh()
end

function ns.openTab(key)
  if not frame then
    create()
  end
  frame:Show()
  ns.showTab(key)
end

function ns.toggleWindow()
  if frame and frame:IsShown() then
    frame:Hide()
  else
    ns.openTab(active)
  end
end

ns.onChange(ns.refresh)

local events = CreateFrame("Frame")
local itemsArriving = false
ns.listen(events, "GET_ITEM_INFO_RECEIVED")
events:SetScript("OnEvent", function()
  -- Names arrive one item at a time; one redraw covers a burst of them.
  if itemsArriving or not (frame and frame:IsShown()) then
    return
  end
  itemsArriving = true
  C_Timer.After(0.5, function()
    itemsArriving = false
    ns.refresh()
  end)
end)

SLASH_ANVILBOOK1 = "/anvilbook"
SlashCmdList.ANVILBOOK = function(message)
  message = (message or ""):lower():match("^%s*(.-)%s*$")
  if message == "probe" then
    ns.probe()
  elseif message == "options" then
    ns.openOptions()
  else
    ns.toggleWindow()
  end
end
