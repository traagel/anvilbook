local _, ns = ...
local W = ns.W

-- The same limits as bridge.GAME_KEYS, which checks these again when the app takes them.
local FIELDS = {
  {key = "ah_cut", label = "AH cut (0.05 = 5%)", low = 0, high = 1},
  {key = "cast_seconds", label = "Cast seconds", low = 0.1, high = 3600},
  {key = "min_listed", label = "Min listed", low = 0, high = 1000000, whole = true},
  {key = "max_use_level", label = "Max use level", low = 0, high = 1000, whole = true},
  {key = "min_disenchant_samples", label = "Measured disenchants needed before they replace the table", low = 1,
   high = 1000000, whole = true},
}

local COLUMNS = {
  {key = "quality", label = "Quality", width = 80},
  {key = "maxLevel", label = "Up to level", width = 80, align = "RIGHT"},
  {key = "kind", label = "Type", width = 70},
  {key = "samples", label = "Disenchants", width = 80, align = "RIGHT"},
  {key = "used", label = "In use", width = 80, fmt = function(v) return v and "yes" or "not enough" end},
  {key = "result", label = "Result", width = 360},
}

local function save(panel)
  local current = ns.Sync.settings()
  local changes = {}
  for _, field in ipairs(FIELDS) do
    local value = tonumber(panel.edits[field.key]:GetText())
    if not value or value < field.low or value > field.high or (field.whole and value % 1 ~= 0) then
      panel.message:SetText(("|cffff6060%s must be a %s from %s to %s.|r"):format(
        field.label, field.whole and "whole number" or "number", field.low, field.high))
      return
    end
    if value ~= current[field.key] then
      changes[field.key] = value
    end
  end
  for key, value in pairs(changes) do
    ns.Sync.set(key, value)
  end
  panel.message:SetText(next(changes) and "Saved. The app gets these at your next /reload." or "Nothing changed.")
end

local function measured(m)
  local buckets, order = ns.Calc.observed(m.settings.disenchant_table, m.records)
  local rows = {}
  for _, key in ipairs(order) do
    local b = buckets[key]
    local parts = {}
    for _, y in ipairs(b.yields) do
      parts[#parts + 1] = ("%s %d%% x%.1f"):format(ns.Items.name(y[1]), y[2] * 100 + 0.5, y[3])
    end
    rows[#rows + 1] = {quality = b.quality, maxLevel = b.maxLevel, kind = b.kind, samples = b.samples,
                       used = b.samples >= m.settings.min_disenchant_samples, result = table.concat(parts, ", ")}
  end
  table.sort(rows, function(a, b)
    if a.quality ~= b.quality then
      return a.quality < b.quality
    end
    if a.maxLevel ~= b.maxLevel then
      return a.maxLevel < b.maxLevel
    end
    return a.kind < b.kind
  end)
  return rows
end

ns.addTab({
  key = "settings",
  label = "Settings",
  create = function(panel)
    panel.edits = {}
    for i, field in ipairs(FIELDS) do
      local edit = W.edit(panel, 70)
      edit:SetPoint("TOPLEFT", 6, -(i - 1) * 24)
      local label = W.label(panel, field.label)
      label:SetPoint("LEFT", edit, "RIGHT", 10, 0)
      panel.edits[field.key] = edit
    end
    panel.enchanter = W.check(panel, "Assume enchanter (count disenchanting as an exit for every craft)",
                              function(checked)
                                ns.Sync.set("assume_enchanter", checked)
                              end)
    panel.enchanter:SetPoint("TOPLEFT", 0, -#FIELDS * 24)
    panel.save = W.button(panel, "Save", 90, function()
      save(panel)
    end)
    panel.save:SetPoint("TOPLEFT", 0, -#FIELDS * 24 - 28)
    panel.message = W.label(panel, "")
    panel.message:SetPoint("LEFT", panel.save, "RIGHT", 10, 0)
    local heading = W.label(panel, "Measured disenchants", "GameFontNormal")
    heading:SetPoint("TOPLEFT", 0, -#FIELDS * 24 - 64)
    local note = W.label(panel, "Recorded in game. A group replaces the app's table once it has enough samples.",
                         "GameFontDisableSmall")
    note:SetPoint("LEFT", heading, "RIGHT", 10, 0)
    panel.table = W.table(panel, COLUMNS, {lines = 9})
    panel.table:SetPoint("TOPLEFT", 0, -#FIELDS * 24 - 84)
  end,
  refresh = function(panel)
    local m = ns.model()
    for _, field in ipairs(FIELDS) do
      local edit = panel.edits[field.key]
      if not edit:HasFocus() then
        edit:SetText(tostring(m.settings[field.key]))
      end
    end
    panel.enchanter:SetChecked(m.settings.assume_enchanter and true or false)
    panel.table:SetRows(measured(m))
  end,
})
