local _, ns = ...
local W = ns.W

local selected, planPanel

local function plainMoney(copper)
  return ("%dg %ds %dc"):format(math.floor(copper / 10000), math.floor(copper / 100) % 100, copper % 100)
end

local function counts(title, map, lines)
  local ids = {}
  for id in pairs(map or {}) do
    ids[#ids + 1] = id
  end
  if #ids == 0 then
    return
  end
  table.sort(ids)
  lines[#lines + 1] = ""
  lines[#lines + 1] = "|cffffd100" .. title .. "|r"
  for _, id in ipairs(ids) do
    lines[#lines + 1] = ("  %d %s"):format(map[id], ns.Items.name(id))
  end
end

local function describe(plan)
  if plan.count == 0 then
    if plan.short_by > 0 then
      return ("The budget is %s short of one %s."):format(W.money(plan.short_by), plan.name)
    end
    return ("No way to make %s: a reagent has no price and cannot be crafted."):format(plan.name)
  end
  local profit = (plan.profit >= 0 and "|cff40ff40%s|r" or "|cffff6060%s|r"):format(W.money(plan.profit))
  local lines = {("Make |cffffffff%d %s|r for %s. They sell for %s: profit %s in %d casts."):format(
    plan.count, plan.name, W.money(plan.cost), W.money(plan.revenue), profit, plan.casts)}
  if #plan.purchases > 0 then
    lines[#lines + 1] = ""
    lines[#lines + 1] = "|cffffd100Buy|r"
    for _, p in ipairs(plan.purchases) do
      lines[#lines + 1] = ("  %d %s at %s = %s"):format(p.quantity, ns.Items.name(p.item_id), W.money(p.unit_price),
                                                     W.money(p.total))
    end
  end
  if #plan.steps > 0 then
    lines[#lines + 1] = ""
    lines[#lines + 1] = "|cffffd100Craft|r"
    for _, s in ipairs(plan.steps) do
      lines[#lines + 1] = ("  %d x %s (makes %d each)"):format(s.casts, ns.Items.name(s.item_id), s.makes)
    end
  end
  counts("From your bags", plan.owned_used, lines)
  counts("Left over", plan.leftovers, lines)
  return table.concat(lines, "\n")
end

local function craftable()
  local calc = ns.model().calc
  local entries = {}
  for id, item in pairs(calc.items) do
    for _, recipe in ipairs(item.createdBy or {}) do
      if calc:canCraft(id, recipe) then
        entries[#entries + 1] = {text = item.name or ns.Items.name(id), value = id}
        break
      end
    end
  end
  table.sort(entries, function(a, b)
    return a.text < b.text
  end)
  return entries
end

local function run(panel)
  if not selected then
    panel.result:SetText("Pick an item to plan, or right-click a row on the Crafts tab.")
    return
  end
  local budget = W.parseMoney(panel.budget:GetText())
  if not budget then
    panel.result:SetText("Type a budget, for example 3g 43s, or 12 for 12 gold.")
    return
  end
  local bags = ns.readBags() or {}
  local plan = ns.Calc.forBudget(ns.model().calc, selected, budget, panel.bags:GetChecked() and bags or {})
  plan.name = ns.Items.name(selected)
  local purchases = {}
  for i, p in ipairs(plan.purchases) do
    purchases[i] = {item_id = p.item_id, quantity = p.quantity, total = p.total}
  end
  -- The AH panel ticks a row off by comparing the bags with this record.
  ns.ui().activePlan = {item_id = selected, name = plan.name, count = plan.count, cost = plan.cost, budget = budget,
                        before = bags, purchases = purchases, time = time(), character = ns.characterKey()}
  panel.result:SetText(describe(plan))
  ns.refreshAhPanel()
end

ns.addTab({
  key = "plan",
  label = "Plan",
  create = function(panel)
    local item = W.label(panel, "Item", "GameFontNormalSmall")
    item:SetPoint("TOPLEFT", 0, -4)
    panel.item = W.button(panel, "Pick an item", 220, function(self)
      W.popup(self, craftable(), function(value)
        selected = value
        ns.refresh()
      end)
    end)
    panel.item:SetPoint("LEFT", item, "RIGHT", 6, 0)
    local budget = W.label(panel, "Budget", "GameFontNormalSmall")
    budget:SetPoint("LEFT", panel.item, "RIGHT", 14, 0)
    panel.budget = W.edit(panel, 110)
    panel.budget:SetPoint("LEFT", budget, "RIGHT", 8, 0)
    panel.budget:SetText(plainMoney(GetMoney()))
    panel.bags = W.check(panel, "Use my bags", function() end)
    panel.bags:SetPoint("LEFT", panel.budget, "RIGHT", 10, 0)
    panel.bags:SetChecked(true)
    panel.go = W.button(panel, "Plan it", 90, function()
      run(panel)
    end)
    panel.go:SetPoint("TOPRIGHT", 0, 0)
    panel.result = W.label(panel, "")
    panel.result:SetPoint("TOPLEFT", 0, -36)
    panel.result:SetPoint("BOTTOMRIGHT", 0, 0)
    panel.result:SetJustifyV("TOP")
    panel.result:SetSpacing(2)
  end,
  refresh = function(panel)
    planPanel = panel
    panel.item:SetText(selected and ns.Items.name(selected) or "Pick an item")
  end,
})

function ns.openPlan(itemId)
  selected = itemId
  ns.openTab("plan")
  if planPanel and ns.enabled("plan") then
    run(planPanel)
  end
end
