local _, ns = ...
local W = ns.W

local PRICE_COLOR = {1, 0.82, 0}
local COUNT_COLOR = {0.4, 0.7, 1}
local selected

local function matches(text)
  local data = ns.data()
  local out = {}
  text = text:lower()
  if not (data and data.history) or #text < 2 then
    return out
  end
  for id in pairs(data.history) do
    local name = ns.Items.name(id)
    if name:lower():find(text, 1, true) then
      out[#out + 1] = {text = name, value = id}
    end
  end
  table.sort(out, function(a, b)
    return a.text < b.text
  end)
  return out
end

local function line(panel, n, x1, y1, x2, y2, color)
  local l = panel.linePool[n]
  if not l then
    l = panel.chart:CreateLine(nil, "ARTWORK")
    l:SetThickness(2)
    panel.linePool[n] = l
  end
  l:SetColorTexture(color[1], color[2], color[3], 1)
  l:SetStartPoint("BOTTOMLEFT", panel.chart, x1, y1)
  l:SetEndPoint("BOTTOMLEFT", panel.chart, x2, y2)
  l:Show()
end

local function draw(panel, points, scans)
  for _, l in ipairs(panel.linePool) do
    l:Hide()
  end
  local low, high, most = math.huge, 0, 0
  for _, p in ipairs(points) do
    if p then
      low, high, most = math.min(low, p.min_price), math.max(high, p.min_price), math.max(most, p.available)
    end
  end
  local width, height = panel.chart:GetWidth(), panel.chart:GetHeight()
  local span = math.max(high - low, 1)
  local x = function(i)
    return #points > 1 and (i - 1) / (#points - 1) * width or width / 2
  end
  local n = 0
  for i = 2, #points do
    local a, b = points[i - 1], points[i]
    -- A scan where the item was not listed breaks both lines.
    if a and b then
      n = n + 1
      line(panel, n, x(i - 1), (a.min_price - low) / span * height, x(i), (b.min_price - low) / span * height,
           PRICE_COLOR)
      n = n + 1
      line(panel, n, x(i - 1), a.available / math.max(most, 1) * height, x(i),
           b.available / math.max(most, 1) * height, COUNT_COLOR)
    end
  end
  panel.high:SetText(W.money(high))
  panel.low:SetText(W.money(low))
  panel.most:SetText(("%d listed"):format(most))
  panel.first:SetText(date("%b %d %H:%M", scans[1].time))
  panel.last:SetText(date("%b %d %H:%M", scans[#scans].time))
end

local function text(points, scans)
  local lines = {}
  for i = #points, math.max(1, #points - 20), -1 do
    local p = points[i]
    lines[#lines + 1] = ("%s   %s   %s"):format(date("%b %d %H:%M", scans[i].time),
                                               p and W.money(p.min_price) or "not listed",
                                               p and (p.available .. " listed") or "")
  end
  return table.concat(lines, "\n")
end

ns.addTab({
  key = "history",
  label = "History",
  create = function(panel)
    local label = W.label(panel, "Item", "GameFontNormalSmall")
    label:SetPoint("TOPLEFT", 0, -4)
    panel.search = W.edit(panel, 240)
    panel.search:SetPoint("LEFT", label, "RIGHT", 10, 0)
    panel.search:SetScript("OnTextChanged", function(self, typed)
      if typed then
        W.popup(self, matches(self:GetText()), function(value)
          selected = value
          self:ClearFocus()
          ns.refresh()
        end, true)
      end
    end)
    panel.title = W.label(panel, "", "GameFontNormal")
    panel.title:SetPoint("TOPLEFT", 0, -32)
    panel.chart = CreateFrame("Frame", nil, panel)
    panel.chart:SetPoint("TOPLEFT", 70, -60)
    panel.chart:SetPoint("BOTTOMRIGHT", -70, 24)
    panel.linePool = {}
    panel.high = W.label(panel, "")
    panel.high:SetPoint("TOPRIGHT", panel.chart, "TOPLEFT", -6, 0)
    panel.low = W.label(panel, "")
    panel.low:SetPoint("BOTTOMRIGHT", panel.chart, "BOTTOMLEFT", -6, 0)
    panel.most = W.label(panel, "")
    panel.most:SetPoint("TOPLEFT", panel.chart, "TOPRIGHT", 6, 0)
    panel.most:SetTextColor(unpack(COUNT_COLOR))
    panel.first = W.label(panel, "")
    panel.first:SetPoint("TOPLEFT", panel.chart, "BOTTOMLEFT", 0, -4)
    panel.last = W.label(panel, "")
    panel.last:SetPoint("TOPRIGHT", panel.chart, "BOTTOMRIGHT", 0, -4)
    panel.listing = W.label(panel, "")
    panel.listing:SetPoint("TOPLEFT", 0, -60)
    panel.listing:SetJustifyV("TOP")
  end,
  refresh = function(panel)
    local data = ns.data()
    local labels = {panel.high, panel.low, panel.most, panel.first, panel.last}
    for _, l in ipairs(panel.linePool) do
      l:Hide()
    end
    for _, l in ipairs(labels) do
      l:SetText("")
    end
    panel.listing:SetText("")
    if not data then
      panel.title:SetText("Run the anvilbook app to see this.")
      return
    end
    local points = selected and ns.history(selected)
    if not points then
      panel.title:SetText(("Type an item name. History covers the last %d scans."):format(#data.scans))
      return
    end
    local last = points[#points]
    panel.title:SetText(("%s   |cffffd100%s|r   %s"):format(ns.Items.name(selected),
                                                          last and W.money(last.min_price) or "",
                                                          last and (last.available .. " listed")
                                                          or "not listed in the last scan"))
    if panel.chart.CreateLine then
      draw(panel, points, data.scans)
    else
      panel.listing:SetText(text(points, data.scans))
    end
  end,
})
