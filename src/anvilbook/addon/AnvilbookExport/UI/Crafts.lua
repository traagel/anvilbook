local _, ns = ...
local W = ns.W

local DIFFICULTY = {optimal = {1, 0.5, 0.25}, medium = {1, 1, 0}, easy = {0.25, 0.75, 0.25},
                    trivial = {0.5, 0.5, 0.5}}
local WHITE = {1, 1, 1}

local function money(v)
  return W.money(v)
end

local COLUMNS = {
  {key = "name", label = "Item", width = 160, fmt = function(v, row) return v or ns.Items.name(row.item_id) end},
  {key = "profession", label = "Profession", width = 76},
  {key = "skill", label = "Skill-up", width = 54, fmt = function(v, row) return row.difficulty or tostring(v) end,
   color = function(_, row) return unpack(DIFFICULTY[row.difficulty or ""] or WHITE) end},
  {key = "cost", label = "Cost", width = 66, align = "RIGHT", fmt = money},
  {key = "revenue", label = "Net sale", width = 66, align = "RIGHT", fmt = money},
  {key = "profit", label = "Profit", width = 66, align = "RIGHT", fmt = money},
  {key = "exit", label = "Exit", width = 58,
   color = function(v) return unpack(v == "disenchant" and DIFFICULTY.optimal or WHITE) end},
  {key = "casts", label = "Casts", width = 38, align = "RIGHT", fmt = function(v) return ("%.1f"):format(v) end},
  {key = "per_cast", label = "Per cast", width = 66, align = "RIGHT", fmt = money},
  {key = "per_hour", label = "Per hour", width = 70, align = "RIGHT", fmt = money},
  {key = "listed", label = "Listed", width = 36, align = "RIGHT", fmt = function(v) return v and tostring(v) or "?" end},
}

local profession -- nil shows every profession

local function emptyText(m, rows)
  if #rows > 0 then
    return ""
  end
  if next(m.professions) == nil then
    return "No recipes recorded for this character. Open each profession window for a few seconds."
  end
  if next(m.prices) == nil then
    return "No prices yet. Scan the auction house with Auctionator, or run the anvilbook app and /reload."
  end
  return "Nothing profitable to craft at the current prices and settings."
end

local function describe(row)
  local text = ("|cffffd100Best path:|r %s\n|cffffd100Cheapest:|r %s, profit %s in %.1f casts"):format(
    row.path, row.cheapest_path, W.money(row.cheapest_profit), row.cheapest_casts)
  if row.de_value and row.de_value > 0 then
    text = text .. ("   |cffffd100Disenchant:|r %s"):format(W.money(row.de_value))
  end
  return text .. "   (right-click a row to plan it)"
end

ns.addTab({
  key = "crafts",
  label = "Crafts",
  create = function(panel)
    panel.enchanter = W.check(panel, "Assume enchanter", function(checked)
      ns.Sync.set("assume_enchanter", checked)
    end)
    panel.enchanter:SetPoint("TOPLEFT", 0, 0)
    panel.filter = W.button(panel, "All professions", 150, function(self)
      local names = {}
      for name in pairs(ns.model().professions) do
        names[#names + 1] = name
      end
      table.sort(names)
      local entries = {{text = "All professions"}}
      for _, name in ipairs(names) do
        entries[#entries + 1] = {text = name, value = name}
      end
      W.popup(self, entries, function(value)
        profession = value
        ns.refresh()
      end)
    end)
    panel.filter:SetPoint("TOPRIGHT", 0, 0)
    panel.table = W.table(panel, COLUMNS, {
      lines = 19,
      onClick = function(row, button)
        if button == "RightButton" then
          ns.openPlan(row.item_id)
        else
          panel.detail:SetText(describe(row))
        end
      end,
      onEnter = function(line, row)
        W.itemTooltip(line, row.item_id)
      end,
    })
    panel.table:SetPoint("TOPLEFT", 0, -28)
    panel.empty = W.label(panel, "", "GameFontNormal")
    panel.empty:SetPoint("TOP", 0, -90)
    panel.detail = W.label(panel, "Click a row to see its paths.")
    panel.detail:SetPoint("BOTTOMLEFT", 0, 0)
    panel.detail:SetPoint("BOTTOMRIGHT", 0, 0)
  end,
  refresh = function(panel)
    local m = ns.model()
    panel.enchanter:SetChecked(m.settings.assume_enchanter and true or false)
    panel.filter:SetText(profession or "All professions")
    local all = ns.rows()
    local rows = {}
    for _, row in ipairs(all) do
      if not profession or row.profession == profession then
        rows[#rows + 1] = row
      end
    end
    panel.table:SetRows(rows)
    panel.empty:SetText(emptyText(m, rows))
  end,
})
