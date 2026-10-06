local _, ns = ...
local W = ns.W

local TOGGLES = {
  {"minimap", "Minimap button"},
  {"ahpanel", "Shopping panel beside the auction house"},
  {"tooltip", "Anvilbook lines on item tooltips"},
  {"crafts", "Crafts tab"},
  {"plan", "Plan tab"},
  {"history", "History tab"},
  {"sellthrough", "Sell-through tab"},
  {"share", "Share tab"},
  {"settings", "Settings tab"},
}

local panel = CreateFrame("Frame")
panel.name = "Anvilbook"
local title = W.label(panel, "Anvilbook", "GameFontNormalLarge")
title:SetPoint("TOPLEFT", 16, -16)
local note = W.label(panel, "Turn each part of the addon on or off. The choices apply to every character.")
note:SetPoint("TOPLEFT", 16, -42)
panel.boxes = {}
for i, toggle in ipairs(TOGGLES) do
  local key = toggle[1]
  local box = W.check(panel, toggle[2], function(checked)
    ns.ui().toggles[key] = checked
    ns.applyToggles()
  end)
  box:SetPoint("TOPLEFT", 16, -64 - (i - 1) * 28)
  panel.boxes[key] = box
end
local open = W.button(panel, "Open the window", 150, function()
  ns.openTab()
end)
open:SetPoint("TOPLEFT", 16, -72 - #TOGGLES * 28)
panel:SetScript("OnShow", function()
  for key, box in pairs(panel.boxes) do
    box:SetChecked(ns.enabled(key))
  end
end)

local category
if Settings and Settings.RegisterCanvasLayoutCategory then
  category = Settings.RegisterCanvasLayoutCategory(panel, panel.name)
  Settings.RegisterAddOnCategory(category)
elseif InterfaceOptions_AddCategory then
  InterfaceOptions_AddCategory(panel)
end

function ns.openOptions()
  if category and Settings.OpenToCategory then
    Settings.OpenToCategory(category.GetID and category:GetID() or category.ID)
  elseif InterfaceOptionsFrame_OpenToCategory then
    -- The first call only opens the frame when it has never been shown.
    InterfaceOptionsFrame_OpenToCategory(panel)
    InterfaceOptionsFrame_OpenToCategory(panel)
  end
end

function ns.applyToggles()
  ns.updateMinimap()
  if not ns.enabled("ahpanel") then
    ns.hideAhPanel()
  end
  ns.refresh()
end
