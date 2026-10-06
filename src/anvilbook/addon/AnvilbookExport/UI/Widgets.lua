local _, ns = ...
local W = {}
ns.W = W

local GOLD, SILVER, COPPER = "|cffffd700g|r", "|cffc7c7cfs|r", "|cffeda55fc|r"

function W.money(copper)
  if type(copper) ~= "number" then
    return ""
  end
  local sign = copper < 0 and "-" or ""
  copper = math.floor(math.abs(copper) + 0.5)
  local g, s, c = math.floor(copper / 10000), math.floor(copper / 100) % 100, copper % 100
  if g > 0 then
    return ("%s%d%s %02d%s %02d%s"):format(sign, g, GOLD, s, SILVER, c, COPPER)
  end
  if s > 0 then
    return ("%s%d%s %02d%s"):format(sign, s, SILVER, c, COPPER)
  end
  return ("%s%d%s"):format(sign, c, COPPER)
end

-- "3g 43s 10c", or a plain number of gold.
function W.parseMoney(text)
  text = (text or ""):lower()
  local total, found = 0, false
  for amount, unit in text:gmatch("(%d+%.?%d*)%s*([gsc])") do
    found = true
    total = total + tonumber(amount) * (unit == "g" and 10000 or unit == "s" and 100 or 1)
  end
  if found then
    return math.floor(total)
  end
  local gold = tonumber(text:match("^%s*(%d+%.?%d*)%s*$") or "")
  return gold and math.floor(gold * 10000) or nil
end

function W.age(seconds)
  if seconds < 3600 then
    return ("%d min"):format(math.max(1, math.floor(seconds / 60)))
  elseif seconds < 86400 then
    return ("%d h"):format(math.floor(seconds / 3600))
  end
  return ("%d d"):format(math.floor(seconds / 86400))
end

function W.label(parent, text, template)
  local fs = parent:CreateFontString(nil, "OVERLAY", template or "GameFontHighlightSmall")
  fs:SetJustifyH("LEFT")
  fs:SetText(text or "")
  return fs
end

function W.button(parent, text, width, onClick)
  local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
  b:SetSize(width, 22)
  b:SetText(text)
  b:SetScript("OnClick", function(self, button)
    ns.safe(onClick, self, button)
  end)
  return b
end

function W.check(parent, text, onClick)
  local c = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
  c:SetSize(24, 24)
  c.label = W.label(c, text)
  c.label:SetPoint("LEFT", c, "RIGHT", 2, 1)
  c:SetScript("OnClick", function(self)
    ns.safe(onClick, self:GetChecked() and true or false)
  end)
  return c
end

function W.edit(parent, width)
  local e = CreateFrame("EditBox", nil, parent, "InputBoxTemplate")
  e:SetSize(width, 20)
  e:SetAutoFocus(false)
  e:SetScript("OnEscapePressed", e.ClearFocus)
  e:SetScript("OnEnterPressed", e.ClearFocus)
  return e
end

function W.itemTooltip(owner, id)
  GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
  if GameTooltip.SetItemByID then
    GameTooltip:SetItemByID(id)
  else
    GameTooltip:SetHyperlink("item:" .. id)
  end
  GameTooltip:Show()
end

local function compare(key, dir)
  return function(a, b)
    local x, y = a[key], b[key]
    if x == y then
      return false
    end
    -- Missing values sort as the smallest, like the web page.
    if x == nil then
      return dir > 0
    end
    if y == nil then
      return dir < 0
    end
    if dir > 0 then
      return x < y
    end
    return x > y
  end
end

-- A scrolling, sortable table. cols: {key, label, width, align, fmt(value, row), color(value, row)}.
-- opts: lines, onClick(row, button), onEnter(line, row), sortKey.
function W.table(parent, cols, opts)
  local t = CreateFrame("Frame", nil, parent)
  t.cols, t.rows, t.shown, t.offset = cols, {}, {}, 0
  t.sortKey, t.sortDir = opts.sortKey, -1
  local lineHeight, width = 16, 0
  t.headers = {}
  for i, col in ipairs(cols) do
    local h = CreateFrame("Button", nil, t)
    h:SetPoint("TOPLEFT", width, 0)
    h:SetSize(col.width, 18)
    h.text = W.label(h, col.label, "GameFontNormalSmall")
    h.text:SetAllPoints()
    h.text:SetJustifyH(col.align or "LEFT")
    h:SetScript("OnClick", function()
      if t.sortKey == col.key then
        t.sortDir = -t.sortDir
      else
        t.sortKey, t.sortDir = col.key, -1
      end
      t:SetRows(t.rows)
    end)
    t.headers[i] = h
    width = width + col.width
  end
  t.lines = {}
  for r = 1, opts.lines do
    local line = CreateFrame("Button", nil, t)
    line:SetPoint("TOPLEFT", 0, -20 - (r - 1) * lineHeight)
    line:SetSize(width, lineHeight)
    line:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    local highlight = line:CreateTexture(nil, "HIGHLIGHT")
    highlight:SetAllPoints()
    highlight:SetColorTexture(1, 1, 1, 0.08)
    line.cells = {}
    local x = 0
    for i, col in ipairs(cols) do
      local cell = W.label(line, "")
      cell:SetPoint("LEFT", x + 2, 0)
      cell:SetWidth(col.width - 4)
      cell:SetJustifyH(col.align or "LEFT")
      cell:SetWordWrap(false)
      line.cells[i] = cell
      x = x + col.width
    end
    line:SetScript("OnClick", function(self, button)
      if self.row and opts.onClick then
        ns.safe(opts.onClick, self.row, button)
      end
    end)
    line:SetScript("OnEnter", function(self)
      if self.row and opts.onEnter then
        ns.safe(opts.onEnter, self, self.row)
      end
    end)
    line:SetScript("OnLeave", function()
      GameTooltip:Hide()
    end)
    t.lines[r] = line
  end
  t.count = W.label(t, "", "GameFontDisableSmall")
  t.count:SetPoint("TOPRIGHT", t, "BOTTOMRIGHT", 0, -2)
  t:SetSize(width, 20 + opts.lines * lineHeight)
  t:EnableMouseWheel(true)
  t:SetScript("OnMouseWheel", function(_, delta)
    t.offset = math.max(0, math.min(t.offset - delta * 3, #t.shown - #t.lines))
    t:Render()
  end)

  function t:SetRows(rows)
    self.rows = rows or {}
    local shown = {}
    for i, row in ipairs(self.rows) do
      shown[i] = row
    end
    if self.sortKey then
      ns.Calc.stableSort(shown, compare(self.sortKey, self.sortDir))
    end
    self.shown = shown
    self.offset = math.max(0, math.min(self.offset, #shown - #self.lines))
    self:Render()
  end

  function t:Render()
    for i, col in ipairs(self.cols) do
      local arrow = col.key == self.sortKey and (self.sortDir > 0 and " ^" or " v") or ""
      self.headers[i].text:SetText(col.label .. arrow)
    end
    for r, line in ipairs(self.lines) do
      local row = self.shown[self.offset + r]
      line.row = row
      if row then
        for i, col in ipairs(self.cols) do
          local value = row[col.key]
          local text = col.fmt and col.fmt(value, row) or (value ~= nil and tostring(value) or "")
          line.cells[i]:SetText(text)
          if col.color then
            line.cells[i]:SetTextColor(col.color(value, row))
          end
        end
        line:Show()
      else
        line:Hide()
      end
    end
    local total = #self.shown
    self.count:SetText(total > #self.lines and ("%d-%d of %d, scroll for more"):format(
      self.offset + 1, math.min(total, self.offset + #self.lines), total) or "")
  end

  return t
end

-- One shared pick list. entries: {text, value}. A second call on the same anchor closes it,
-- unless `live` is set (a search box that calls it on each key press).
local popup
function W.popup(anchor, entries, onPick, live)
  if not popup then
    popup = CreateFrame("Frame", "AnvilbookPopup", UIParent, BackdropTemplateMixin and "BackdropTemplate" or nil)
    popup:SetFrameStrata("FULLSCREEN_DIALOG")
    popup:SetSize(240, 15 * 16 + 10)
    if popup.SetBackdrop then
      popup:SetBackdrop({bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
                         edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border", edgeSize = 12,
                         insets = {left = 3, right = 3, top = 3, bottom = 3}})
      popup:SetBackdropColor(0, 0, 0, 0.95)
    end
    popup.buttons = {}
    for i = 1, 15 do
      local b = CreateFrame("Button", nil, popup)
      b:SetPoint("TOPLEFT", 6, -5 - (i - 1) * 16)
      b:SetSize(228, 16)
      b.text = W.label(b, "")
      b.text:SetAllPoints()
      b.text:SetWordWrap(false)
      local highlight = b:CreateTexture(nil, "HIGHLIGHT")
      highlight:SetAllPoints()
      highlight:SetColorTexture(1, 1, 1, 0.12)
      b:SetScript("OnClick", function(self)
        popup:Hide()
        ns.safe(popup.onPick, self.value)
      end)
      popup.buttons[i] = b
    end
    popup:EnableMouseWheel(true)
    popup:SetScript("OnMouseWheel", function(_, delta)
      popup.offset = math.max(0, math.min(popup.offset - delta * 3, #popup.entries - #popup.buttons))
      popup:Render()
    end)
    function popup:Render()
      for i, b in ipairs(self.buttons) do
        local entry = self.entries[self.offset + i]
        b.value = entry and entry.value
        b.text:SetText(entry and entry.text or "")
        b:SetShown(entry ~= nil)
      end
    end
    tinsert(UISpecialFrames, "AnvilbookPopup")
  end
  if (popup:IsShown() and popup.anchor == anchor and not live) or #entries == 0 then
    popup:Hide()
    return
  end
  popup.anchor, popup.entries, popup.onPick, popup.offset = anchor, entries, onPick, 0
  popup:ClearAllPoints()
  popup:SetPoint("TOPLEFT", anchor, "BOTTOMLEFT", 0, -2)
  popup:Render()
  popup:Show()
end

function W.hidePopup()
  if popup then
    popup:Hide()
  end
end
