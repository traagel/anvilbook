local _, ns = ...

local button

-- The minimap's frame can be larger than the map you see, so the default distance is a guess
-- that dragging corrects.
local function defaultRadius()
  return Minimap:GetWidth() * 3 / 8 + 10
end

local function place()
  local ui = ns.ui()
  local angle = math.rad(ui.minimapAngle or 200)
  local radius = ui.minimapRadius or defaultRadius()
  button:ClearAllPoints()
  button:SetPoint("CENTER", Minimap, "CENTER", math.cos(angle) * radius, math.sin(angle) * radius)
end

local function follow()
  local mx, my = Minimap:GetCenter()
  local cx, cy = GetCursorPosition()
  local scale = Minimap:GetEffectiveScale()
  local dx, dy = cx / scale - mx, cy / scale - my
  local width = Minimap:GetWidth()
  local ui = ns.ui()
  ui.minimapAngle = math.deg(math.atan2(dy, dx))
  -- Kept near the edge, so a slip of the mouse cannot lose the button.
  ui.minimapRadius = math.max(width / 4, math.min(width, math.sqrt(dx * dx + dy * dy)))
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
