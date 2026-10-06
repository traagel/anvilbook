local _, ns = ...
local W = ns.W

local from, to

local function scanText(scan)
  return ("%s (%d items)"):format(date("%b %d %H:%M", scan.time), scan.items or 0)
end

local COLUMNS = {
  {key = "name", label = "Item", width = 250},
  {key = "from_available", label = "Listed before", width = 90, align = "RIGHT"},
  {key = "to_available", label = "Listed after", width = 90, align = "RIGHT"},
  {key = "change", label = "Change", width = 70, align = "RIGHT",
   color = function(v)
     if v < 0 then
       return 0.25, 0.9, 0.25
     end
     return 1, 1, 1
   end},
  {key = "from_price", label = "Price before", width = 120, align = "RIGHT", fmt = W.money},
  {key = "to_price", label = "Price after", width = 120, align = "RIGHT", fmt = W.money},
}

local cache = {}

-- Store.sellthrough, from the history strings. The data file is fixed until the next /reload.
local function rows(data)
  local key = from .. ":" .. to
  if cache[key] then
    return cache[key]
  end
  local out = {}
  for id in pairs(data.history) do
    local points = ns.history(id)
    local a, b = points[from], points[to]
    if a or b then
      local before, after = a and a.available or 0, b and b.available or 0
      out[#out + 1] = {item_id = id, name = ns.Items.name(id), from_available = before, to_available = after,
                       change = after - before, from_price = a and a.min_price, to_price = b and b.min_price}
    end
  end
  table.sort(out, function(x, y)
    if x.change ~= y.change then
      return x.change < y.change
    end
    return x.item_id < y.item_id
  end)
  cache[key] = out
  return out
end

local function picker(panel, which)
  return function(self)
    local scans = ns.data() and ns.data().scans or {}
    local entries = {}
    for i = #scans, 1, -1 do
      entries[#entries + 1] = {text = scanText(scans[i]), value = i}
    end
    W.popup(self, entries, function(value)
      if which == "from" then
        from = value
      else
        to = value
      end
      ns.refresh()
    end)
  end
end

ns.addTab({
  key = "sellthrough",
  label = "Sell-through",
  create = function(panel)
    local fromLabel = W.label(panel, "From", "GameFontNormalSmall")
    fromLabel:SetPoint("TOPLEFT", 0, -4)
    panel.from = W.button(panel, "", 190, picker(panel, "from"))
    panel.from:SetPoint("LEFT", fromLabel, "RIGHT", 6, 0)
    local toLabel = W.label(panel, "To", "GameFontNormalSmall")
    toLabel:SetPoint("LEFT", panel.from, "RIGHT", 14, 0)
    panel.to = W.button(panel, "", 190, picker(panel, "to"))
    panel.to:SetPoint("LEFT", toLabel, "RIGHT", 6, 0)
    panel.note = W.label(panel, "Fewer listed means sales or expired auctions. Green: selling.", "GameFontDisableSmall")
    panel.note:SetPoint("TOPLEFT", 0, -30)
    panel.table = W.table(panel, COLUMNS, {
      lines = 18,
      onEnter = function(line, row)
        W.itemTooltip(line, row.item_id)
      end,
    })
    panel.table:SetPoint("TOPLEFT", 0, -48)
  end,
  refresh = function(panel)
    local data = ns.data()
    local scans = data and data.scans or {}
    if #scans < 2 then
      panel.from:SetText("")
      panel.to:SetText("")
      panel.note:SetText(data and "Sell-through needs 2 scans from the app."
                         or "Run the anvilbook app to see this.")
      panel.table:SetRows({})
      return
    end
    if not (from and to and scans[from] and scans[to]) then
      from, to = #scans - 1, #scans
    end
    panel.from:SetText(scanText(scans[from]))
    panel.to:SetText(scanText(scans[to]))
    panel.note:SetText("Fewer listed means sales or expired auctions. Green: selling.")
    panel.table:SetRows(rows(data))
  end,
})
