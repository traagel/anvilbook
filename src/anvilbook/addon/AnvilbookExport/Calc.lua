-- A port of craft.py, plan.py and disenchant.py. Keep the two in step:
-- tests/test_calc_parity.py runs both on the same input and compares the results.
local _, ns = ...
local Calc = {}
ns.Calc = Calc

-- Deep enough for ore -> bar -> alloy -> item; also stops recipe cycles.
Calc.MAX_DEPTH = 3
Calc.MAX_COUNT = 500
Calc.QUALITY_NAMES = {[2] = "Uncommon", [3] = "Rare", [4] = "Epic"}
Calc.ALIASES = {Smelting = "Mining"}
local KINDS = {Armor = "armor", Weapon = "weapon"}
local KIND_KEYS = {"armor", "weapon"}

-- table.sort is not stable and Python's sorted is; ties keep their input order.
local function stableSort(list, less)
  local wrapped = {}
  for i, v in ipairs(list) do
    wrapped[i] = {v = v, i = i}
  end
  table.sort(wrapped, function(a, b)
    if less(a.v, b.v) then
      return true
    end
    if less(b.v, a.v) then
      return false
    end
    return a.i < b.i
  end)
  for i, w in ipairs(wrapped) do
    list[i] = w.v
  end
  return list
end
Calc.stableSort = stableSort

local function nonzero(n)
  return n and n ~= 0 and n or nil
end

-- Python's `int(x or 1)`: a missing or zero count means one.
local function count(x)
  return nonzero(tonumber(x)) or 1
end

-- An option is {price, casts, path, node}; a node is {buy = true, item_id} or {item_id, recipe, children}.
function Calc.pareto(opts)
  local sorted = {}
  for i, o in ipairs(opts) do
    sorted[i] = o
  end
  stableSort(sorted, function(a, b)
    return a[1] < b[1] or (a[1] == b[1] and a[2] < b[2])
  end)
  local front = {}
  for _, o in ipairs(sorted) do
    if #front == 0 or o[2] < front[#front][2] then
      front[#front + 1] = o
    end
  end
  return front
end

local function byMaxLevel(rows)
  local out = {}
  for i, row in ipairs(rows or {}) do
    out[i] = row
  end
  return stableSort(out, function(a, b)
    return a.maxLevel < b.maxLevel
  end)
end

local function bucket(tbl, quality, itemLevel, kind)
  local name = Calc.QUALITY_NAMES[quality] or quality
  local key = KINDS[tostring(kind)]
  if not key then
    return nil
  end
  for _, row in ipairs(byMaxLevel(tbl)) do
    if row.quality == name and itemLevel <= row.maxLevel then
      return name .. "|" .. row.maxLevel .. "|" .. key, name, row.maxLevel, key
    end
  end
end

-- Returns the buckets keyed "quality|maxLevel|kind", and their keys in first-seen order.
function Calc.observed(tbl, records)
  local counts, order = {}, {}
  for _, record in ipairs(records or {}) do
    local item = record.item or {}
    local id, quality, maxLevel, kind = bucket(tbl, item.quality, tonumber(item.itemLevel) or 0, item.kind)
    if id then
      local stats = counts[id]
      if not stats then
        stats = {quality = quality, maxLevel = maxLevel, kind = kind, samples = 0, mats = {}, matOrder = {}}
        counts[id] = stats
        order[#order + 1] = id
      end
      stats.samples = stats.samples + 1
      for _, mat in ipairs(record.mats or {}) do
        local matId = tonumber(mat.id)
        local got = stats.mats[matId]
        if not got then
          got = {0, 0}
          stats.mats[matId] = got
          stats.matOrder[#stats.matOrder + 1] = matId
        end
        got[1] = got[1] + 1
        got[2] = got[2] + count(mat.count)
      end
    end
  end
  local out = {}
  for _, id in ipairs(order) do
    local stats = counts[id]
    local yields = {}
    for _, matId in ipairs(stats.matOrder) do
      local times, total = stats.mats[matId][1], stats.mats[matId][2]
      yields[#yields + 1] = {matId, times / stats.samples, total / times}
    end
    out[id] = {quality = stats.quality, maxLevel = stats.maxLevel, kind = stats.kind, samples = stats.samples,
               yields = yields}
  end
  return out, order
end

function Calc.effectiveTable(tbl, records, minSamples)
  local buckets = Calc.observed(tbl, records)
  local out = {}
  for i, source in ipairs(tbl or {}) do
    local row = {}
    for k, v in pairs(source) do
      row[k] = v
    end
    for _, key in ipairs(KIND_KEYS) do
      local measured = buckets[tostring(row.quality) .. "|" .. tostring(row.maxLevel) .. "|" .. key]
      if measured and measured.samples >= minSamples then
        local yields = {}
        for j, y in ipairs(measured.yields) do
          yields[j] = {y[1], y[2], y[3]}
        end
        row[key] = yields
      end
    end
    out[i] = row
  end
  return out
end

function Calc.yields(tbl, quality, itemLevel, kind)
  local key = KINDS[tostring(kind)]
  if not key then
    return {}
  end
  for _, row in ipairs(byMaxLevel(tbl)) do
    if row.quality == quality and itemLevel <= row.maxLevel then
      local out = {}
      for i, y in ipairs(row[key] or {}) do
        out[i] = {tonumber(y[1]), tonumber(y[2]), tonumber(y[3])}
      end
      return out
    end
  end
  return {}
end

function Calc.expectedValue(tbl, prices, quality, itemLevel, kind, ahCut)
  local total = 0
  for _, y in ipairs(Calc.yields(tbl, quality, itemLevel, kind)) do
    if prices[y[1]] then
      total = total + y[2] * y[3] * prices[y[1]]
    end
  end
  return total * (1 - ahCut)
end

-- Recipes recorded in game, merged into item details that carry no createdBy of their own.
function Calc.merge(items, professions)
  for profession, data in pairs(professions or {}) do
    profession = Calc.ALIASES[profession] or profession
    for itemId, rec in pairs(data.recipes or {}) do
      local reagents = {}
      for i, r in ipairs(rec.reagents or {}) do
        if not items[r.id] then
          items[r.id] = {name = r.name}
        end
        reagents[i] = {itemId = r.id, amount = r.count}
      end
      local item = items[itemId]
      if not item then
        item = {name = rec.name}
        items[itemId] = item
      end
      item.createdBy = item.createdBy or {}
      item.createdBy[#item.createdBy + 1] = {
        amount = {count(rec.minMade), count(rec.maxMade)}, requiredSkill = 0,
        category = profession, known = true, difficulty = rec.difficulty, reagents = reagents,
      }
    end
  end
  return items
end

local Calculator = {}
Calculator.__index = Calculator

-- settings: skills, skill_overrides, max_use_level, min_listed, cast_seconds, ah_cut,
-- disenchanter, disenchant_table. Prices with no available count pass the min-listed filter.
function Calc.new(items, prices, vendor, settings)
  local minPrices = {}
  for id, p in pairs(prices) do
    minPrices[id] = p.min_price
  end
  return setmetatable({items = items, prices = prices, vendor = vendor or {}, s = settings, memo = {},
                       minPrices = minPrices}, Calculator)
end

function Calculator:skill(itemId, recipe)
  if recipe.known then
    return 0
  end
  local override = (self.s.skill_overrides or {})[itemId]
  if override ~= nil then
    return override
  end
  return recipe.requiredSkill or 0
end

function Calculator:canCraft(itemId, recipe)
  local cap = self.s.skills[recipe.category or ""]
  return cap ~= nil and self:skill(itemId, recipe) <= cap
end

function Calculator:buyPrice(itemId)
  local ah = nonzero((self.prices[itemId] or {}).min_price)
  local vendor = nonzero(self.vendor[itemId]) or nonzero((self.items[itemId] or {}).vendorPrice)
  if ah and vendor then
    return math.min(ah, vendor)
  end
  return ah or vendor
end

function Calculator:disenchantValue(item)
  if not self.s.disenchanter then
    return 0
  end
  return Calc.expectedValue(self.s.disenchant_table, self.minPrices, item.quality, item.itemLevel or 0,
                            item.class, self.s.ah_cut)
end

function Calculator:options(itemId, depth)
  depth = depth or 0
  local key = itemId .. ":" .. depth
  if not self.memo[key] then
    local opts = {}
    local price = self:buyPrice(itemId)
    if price then
      opts[#opts + 1] = {price, 0, "buy", {buy = true, item_id = itemId}}
    end
    if depth < Calc.MAX_DEPTH then
      for _, recipe in ipairs((self.items[itemId] or {}).createdBy or {}) do
        if self:canCraft(itemId, recipe) then
          local n = (recipe.amount[1] + recipe.amount[2]) / 2
          for _, o in ipairs(self:recipeOptions(recipe, depth + 1, itemId)) do
            opts[#opts + 1] = {o[1] / n, o[2] / n, o[3], o[4]}
          end
        end
      end
    end
    self.memo[key] = Calc.pareto(opts)
  end
  return self.memo[key]
end

function Calculator:recipeOptions(recipe, depth, itemId)
  local perReagent = {}
  for i, r in ipairs(recipe.reagents) do
    local item = self.items[r.itemId]
    local name = item and item.name or tostring(r.itemId)
    local list = {}
    for _, o in ipairs(self:options(r.itemId, depth)) do
      list[#list + 1] = {o[1] * r.amount, o[2] * r.amount, name, o[3], o[4]}
    end
    perReagent[i] = list
  end
  local out, combo = {}, {}
  -- Same order as itertools.product: the last reagent varies fastest.
  local function walk(i)
    if i > #perReagent then
      local price, casts, crafted, children = 0, 0, {}, {}
      for j = 1, #perReagent do
        local o = combo[j]
        price = price + o[1]
        casts = casts + o[2]
        if o[4] ~= "buy" then
          crafted[#crafted + 1] = o[3] .. "=" .. o[4]
        end
        children[j] = o[5]
      end
      local path = "craft" .. (#crafted > 0 and ("[" .. table.concat(crafted, ", ") .. "]") or "")
      out[#out + 1] = {price, 1 + casts, path, {item_id = itemId or 0, recipe = recipe, children = children}}
      return
    end
    for _, o in ipairs(perReagent[i]) do
      combo[i] = o
      walk(i + 1)
    end
  end
  walk(1)
  return Calc.pareto(out)
end

function Calculator:rows()
  local out, ids = {}, {}
  for id in pairs(self.prices) do
    ids[#ids + 1] = id
  end
  table.sort(ids)
  for _, itemId in ipairs(ids) do
    local price, item = self.prices[itemId], self.items[itemId]
    if item and (item.requiredLevel or 0) <= self.s.max_use_level
        and (price.available == nil or price.available >= self.s.min_listed) then
      for _, recipe in ipairs(item.createdBy or {}) do
        if self:canCraft(itemId, recipe) then
          local n = (recipe.amount[1] + recipe.amount[2]) / 2
          local sale = math.max(price.min_price * (1 - self.s.ah_cut), item.sellPrice or 0)
          local deValue = self:disenchantValue(item)
          local revenue = math.max(sale, deValue) * n
          local opts = self:recipeOptions(recipe, 0, itemId)
          if #opts > 0 then
            local best, bestScore
            for _, o in ipairs(opts) do
              local score = (revenue - o[1]) / o[2]
              if not best or score > bestScore then
                best, bestScore = o, score
              end
            end
            local cheap = opts[1]
            if revenue - best[1] > 0 then
              local perCast = (revenue - best[1]) / best[2]
              out[#out + 1] = {
                item_id = itemId, name = item.name, profession = recipe.category,
                skill = self:skill(itemId, recipe), cost = best[1], revenue = revenue,
                profit = revenue - best[1], casts = best[2], per_cast = perCast,
                per_hour = perCast * 3600 / self.s.cast_seconds, listed = price.available, path = best[3],
                cheapest_profit = revenue - cheap[1], cheapest_casts = cheap[2], cheapest_path = cheap[3],
                difficulty = recipe.difficulty, de_value = deValue,
                exit = deValue > sale and "disenchant" or "sell",
              }
            end
          end
        end
      end
    end
  end
  return stableSort(out, function(a, b)
    if a.per_hour ~= b.per_hour then
      return a.per_hour > b.per_hour
    end
    return a.item_id < b.item_id
  end)
end

local function ordered()
  return {keys = {}, v = {}}
end

local function add(map, key, n)
  if map.v[key] == nil then
    map.keys[#map.keys + 1] = key
    map.v[key] = 0
  end
  map.v[key] = map.v[key] + n
end

local function gather(node, units, owned, acc)
  local id = node.item_id
  local have = owned[id] or 0
  local used = math.min(have, units)
  owned[id] = have - used
  local spares = acc.spares[id] or 0
  if used ~= 0 and used > spares then
    add(acc.usedOwned, id, used - spares)
  end
  local need = units - used
  if need <= 0 then
    return
  end
  if node.buy then
    add(acc.buys, id, need)
    return
  end
  -- A craft makes whole batches, so the last one can leave spares.
  local perCast = math.min(node.recipe.amount[1], node.recipe.amount[2])
  local runs = math.ceil(need / perCast)
  add(acc.casts, id, runs)
  acc.makes[id] = perCast
  local spare = runs * perCast - need
  if spare ~= 0 then
    add(acc.leftovers, id, spare)
    owned[id] = (owned[id] or 0) + spare
    acc.spares[id] = (acc.spares[id] or 0) + spare
  end
  for i, child in ipairs(node.children) do
    gather(child, runs * node.recipe.reagents[i].amount, owned, acc)
  end
end

local function itemName(calc, id)
  return (calc.items[id] or {}).name or tostring(id)
end

function Calc.planFor(calc, itemId, count, owned)
  local item = calc.items[itemId] or {}
  local plan = {item_id = itemId, name = item.name or tostring(itemId), count = 0, cost = 0, revenue = 0,
                profit = 0, casts = 0, purchases = {}, steps = {}, leftovers = {}, owned_used = {}, short_by = 0}
  -- The plan always crafts the item asked for, even when buying it outright is cheaper.
  local craftable = {}
  for _, recipe in ipairs(item.createdBy or {}) do
    if calc:canCraft(itemId, recipe) then
      for _, o in ipairs(calc:recipeOptions(recipe, 0, itemId)) do
        craftable[#craftable + 1] = o
      end
    end
  end
  local options = Calc.pareto(craftable)
  if #options == 0 then
    options = calc:options(itemId)
  end
  if #options == 0 or count <= 0 then
    return plan
  end

  local acc = {buys = ordered(), casts = ordered(), makes = {}, leftovers = ordered(), usedOwned = ordered(),
               spares = {}}
  local mine = {}
  for k, v in pairs(owned or {}) do
    mine[k] = v
  end
  gather(options[1][4], count, mine, acc)

  local bought = {}
  for i, id in ipairs(acc.buys.keys) do
    bought[i] = id
  end
  stableSort(bought, function(a, b)
    return acc.buys.v[a] > acc.buys.v[b]
  end)
  local cost = 0
  for _, id in ipairs(bought) do
    local quantity, unit = acc.buys.v[id], calc:buyPrice(id) or 0
    plan.purchases[#plan.purchases + 1] = {item_id = id, name = itemName(calc, id), quantity = quantity,
                                           unit_price = unit, total = unit * quantity}
  end
  for _, p in ipairs(plan.purchases) do
    cost = cost + p.total
  end
  local casts = 0
  for _, id in ipairs(acc.casts.keys) do
    plan.steps[#plan.steps + 1] = {item_id = id, name = itemName(calc, id), casts = acc.casts.v[id],
                                   makes = acc.makes[id]}
    casts = casts + acc.casts.v[id]
  end
  local sale = (calc.prices[itemId] or {}).min_price or 0
  local revenue = math.max(sale * (1 - calc.s.ah_cut), item.sellPrice or 0, calc:disenchantValue(item)) * count
  plan.count, plan.cost, plan.revenue, plan.profit, plan.casts = count, cost, revenue, revenue - cost, casts
  plan.leftovers, plan.owned_used = acc.leftovers.v, acc.usedOwned.v
  return plan
end

-- The largest batch that fits the budget. Cost per item is not linear: batches leave spares.
function Calc.forBudget(calc, itemId, budget, owned)
  local best
  local low, high = 1, Calc.MAX_COUNT
  while low <= high do
    local middle = math.floor((low + high) / 2)
    local plan = Calc.planFor(calc, itemId, middle, owned)
    if plan.cost <= budget then
      best = plan
      low = middle + 1
    else
      high = middle - 1
    end
  end
  if best then
    return best
  end
  local one = Calc.planFor(calc, itemId, 1, owned)
  one.count, one.short_by = 0, math.max(0, one.cost - budget)
  one.purchases, one.steps, one.leftovers = {}, {}, {}
  one.revenue, one.profit = 0, 0
  return one
end
