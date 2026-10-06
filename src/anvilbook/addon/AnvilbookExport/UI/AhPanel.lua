local _, ns = ...
local W = ns.W

local DONE = "|TInterface\\RaidFrame\\ReadyCheck-Ready:14|t"
local WAITING = "|TInterface\\RaidFrame\\ReadyCheck-Waiting:14|t"
local LINES = 16
local panel

local function auctionHouse()
  return AuctionHouseFrame or AuctionFrame
end

local function searchable()
  local api = ns.Prices.auctionator()
  return api and (api.MultiSearchExact or api.MultiSearch)
end

local function search()
  local plan = ns.ui().activePlan
  if not (plan and plan.character == ns.characterKey()) then
    return
  end
  local names = {}
  for _, p in ipairs(plan.purchases) do
    names[#names + 1] = ns.Items.name(p.item_id)
  end
  pcall(searchable(), ns.Prices.CALLER, names)
end

local function create()
  panel = CreateFrame("Frame", "AnvilbookAhPanel", UIParent, "BasicFrameTemplateWithInset")
  panel:SetSize(270, 120 + LINES * 16)
  if panel.TitleText then
    panel.TitleText:SetText("Anvilbook shopping")
  end
  panel.title = W.label(panel, "", "GameFontNormal")
  panel.title:SetPoint("TOPLEFT", 12, -30)
  panel.title:SetPoint("TOPRIGHT", -12, -30)
  panel.lines = {}
  for i = 1, LINES do
    local line = W.label(panel, "")
    line:SetPoint("TOPLEFT", 12, -50 - (i - 1) * 16)
    line:SetPoint("TOPRIGHT", -12, -50 - (i - 1) * 16)
    line:SetWordWrap(false)
    panel.lines[i] = line
  end
  panel.footer = W.label(panel, "")
  panel.footer:SetPoint("BOTTOMLEFT", 12, 36)
  panel.search = W.button(panel, "Search in Auctionator", 150, search)
  panel.search:SetPoint("BOTTOMLEFT", 10, 8)
  panel.open = W.button(panel, "Plan", 90, function()
    ns.openTab("plan")
  end)
  panel.open:SetPoint("BOTTOMRIGHT", -10, 8)
end

local function render()
  local plan = ns.ui().activePlan
  -- The ticks compare this character's bags with the bags of the character who planned.
  if plan and plan.character ~= ns.characterKey() then
    plan = nil
  end
  for _, line in ipairs(panel.lines) do
    line:SetText("")
  end
  panel.search:SetShown(plan ~= nil and searchable() ~= nil)
  if not plan then
    panel.title:SetText("No shopping list")
    panel.lines[1]:SetText("Plan a craft: /anvilbook, Plan tab.")
    panel.footer:SetText("")
    return
  end
  panel.title:SetText(("%d %s"):format(plan.count, ns.Items.name(plan.item_id)))
  local bags = ns.readBags() or {}
  local left = 0
  for i, p in ipairs(plan.purchases) do
    local bought = math.max(0, (bags[p.item_id] or 0) - (plan.before[p.item_id] or 0))
    local done = bought >= p.quantity
    if not done then
      left = left + 1
    end
    if panel.lines[i] then
      panel.lines[i]:SetText(("%s %d/%d %s  %s"):format(done and DONE or WAITING, math.min(bought, p.quantity),
                                                         p.quantity, ns.Items.name(p.item_id), W.money(p.total)))
    end
  end
  if #plan.purchases > LINES then
    panel.lines[LINES]:SetText(("... and %d more on the Plan tab"):format(#plan.purchases - LINES + 1))
  end
  panel.footer:SetText(left == 0 and "|cff40ff40Everything is bought.|r"
                       or ("Cost %s of %s budget"):format(W.money(plan.cost), W.money(plan.budget)))
end

function ns.refreshAhPanel()
  if panel and panel:IsShown() then
    ns.safe(render)
  end
end

local events = CreateFrame("Frame")
ns.listen(events, "AUCTION_HOUSE_SHOW", "AUCTION_HOUSE_CLOSED", "BAG_UPDATE_DELAYED")
events:SetScript("OnEvent", function(_, event)
  if event == "AUCTION_HOUSE_SHOW" then
    local ah = auctionHouse()
    if not (ns.enabled("ahpanel") and ah) then
      return
    end
    if not panel then
      ns.safe(create)
    end
    panel:ClearAllPoints()
    panel:SetPoint("TOPLEFT", ah, "TOPRIGHT", 4, 0)
    panel:Show()
    ns.refreshAhPanel()
  elseif event == "AUCTION_HOUSE_CLOSED" then
    if panel then
      panel:Hide()
    end
  else
    ns.refreshAhPanel()
  end
end)

function ns.hideAhPanel()
  if panel then
    panel:Hide()
  end
end
