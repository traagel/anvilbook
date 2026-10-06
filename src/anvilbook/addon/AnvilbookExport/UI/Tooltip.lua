local _, ns = ...
local W = ns.W

local LABEL = "|cffd4a017Anvilbook|r "

local function addLines(tooltip, id)
  if not (id and ns.enabled("tooltip")) then
    return
  end
  local m = ns.model()
  local added = false
  local function add(left, right)
    tooltip:AddDoubleLine(LABEL .. left, right, 1, 1, 1, 1, 1, 1)
    added = true
  end
  -- Auctionator prints its own price line; a second one would only add noise.
  local price = m.prices[id]
  if price and not ns.Prices.live(id) then
    add("price", W.money(price.min_price))
  end
  local points = ns.history(id)
  if points then
    local last, previous = points[#points], points[#points - 1]
    add("listed", last and tostring(last.available) or "0 in the last scan")
    if last and previous and previous.min_price > 0 then
      local change = (last.min_price - previous.min_price) / previous.min_price * 100
      local color = change < 0 and "|cff40ff40" or change > 0 and "|cffff6060" or "|cffffffff"
      add("since the scan before", ("%s%+.0f%%|r"):format(color, change))
    end
  end
  local _, byId = ns.rows()
  local row = byId[id]
  if row then
    add("craft profit", W.money(row.per_cast) .. " per cast")
  end
  if m.calc.s.disenchanter then
    local item = m.calc.items[id] or ns.Items.details(id)
    local value = item and m.calc:disenchantValue(item) or 0
    if value > 0 then
      add("disenchant", W.money(value))
    end
  end
  if added then
    tooltip:Show()
  end
end

local function itemId(link)
  return link and tonumber(link:match("item:(%d+)"))
end

if TooltipDataProcessor and TooltipDataProcessor.AddTooltipPostCall and Enum and Enum.TooltipDataType then
  TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, function(tooltip, data)
    -- Comparison and shopping tooltips would repeat the same lines.
    if tooltip == GameTooltip or tooltip == ItemRefTooltip then
      ns.safe(addLines, tooltip, data and data.id)
    end
  end)
else
  for _, tooltip in ipairs({GameTooltip, ItemRefTooltip}) do
    tooltip:HookScript("OnTooltipSetItem", function(self)
      local _, link = self:GetItem()
      ns.safe(addLines, self, itemId(link))
    end)
  end
end
