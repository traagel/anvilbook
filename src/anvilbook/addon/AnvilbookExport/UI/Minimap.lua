local _, ns = ...

local RADIUS = 80
local button

local function place()
  local angle = math.rad(ns.ui().minimapAngle or 200)
  button:ClearAllPoints()
  button:SetPoint("CENTER", Minimap, "CENTER", math.cos(angle) * RADIUS, math.sin(angle) * RADIUS)
end

local function follow()
  local mx, my = Minimap:GetCenter()
  local cx, cy = GetCursorPosition()
  local scale = Minimap:GetEffectiveScale()
  ns.ui().minimapAngle = math.deg(math.atan2(cy / scale - my, cx / scale - mx))
  place()
end

local function create()
  button = CreateFrame("Button", "AnvilbookMinimapButton", Minimap)
  button:SetSize(31, 31)
  button:SetFrameStrata("MEDIUM")
  button:SetFrameLevel(8)
  local icon = button:CreateTexture(nil, "BACKGROUND")
  icon:SetTexture("Interface\\Icons\\Trade_BlackSmithing")
  icon:SetSize(20, 20)
  icon:SetPoint("CENTER")
  local border = button:CreateTexture(nil, "OVERLAY")
  border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
  border:SetSize(53, 53)
  border:SetPoint("TOPLEFT")
  button:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
  button:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  button:RegisterForDrag("LeftButton")
  button:SetScript("OnClick", function(_, which)
    if which == "RightButton" then
      ns.openOptions()
    else
      ns.toggleWindow()
    end
  end)
  button:SetScript("OnDragStart", function(self)
    self:SetScript("OnUpdate", follow)
  end)
  button:SetScript("OnDragStop", function(self)
    self:SetScript("OnUpdate", nil)
  end)
  button:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:AddLine("Anvilbook")
    GameTooltip:AddLine("Click: open the window", 1, 1, 1)
    GameTooltip:AddLine("Right-click: options", 1, 1, 1)
    GameTooltip:AddLine("Drag: move this button", 1, 1, 1)
    GameTooltip:Show()
  end)
  button:SetScript("OnLeave", function()
    GameTooltip:Hide()
  end)
end

function ns.updateMinimap()
  if ns.enabled("minimap") then
    if not button then
      create()
    end
    place()
    button:Show()
  elseif button then
    button:Hide()
  end
end

local events = CreateFrame("Frame")
ns.listen(events, "PLAYER_LOGIN")
events:SetScript("OnEvent", function()
  ns.safe(ns.updateMinimap)
end)
