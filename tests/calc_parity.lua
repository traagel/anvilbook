-- usage: luajit calc_parity.lua <path to Calc.lua> <case file>
-- Runs the addon's calculator on a case that test_calc_parity.py wrote, and prints the result
-- in SavedVariables form so the app's own parser can read it back.
local ns = {}
assert(loadfile(arg[1]))("AnvilbookExport", ns)
assert(loadfile(arg[2]))()
local Calc = ns.Calc

local function number(n)
  if n == math.floor(n) and math.abs(n) < 2 ^ 53 then
    return string.format("%d", n)
  end
  return string.format("%.17g", n)
end

local function dump(v)
  local t = type(v)
  if t == "number" then
    return number(v)
  elseif t == "string" then
    return string.format("%q", v)
  elseif t == "boolean" then
    return tostring(v)
  elseif t == "table" then
    local parts = {}
    for k, x in pairs(v) do
      parts[#parts + 1] = "[" .. dump(k) .. "] = " .. dump(x)
    end
    return "{" .. table.concat(parts, ", ") .. "}"
  end
  return "nil"
end

local calc = Calc.new(Case.items, Case.prices, Case.vendor, Case.settings)
local plans = {}
for i, p in ipairs(Case.plans) do
  if p.budget then
    plans[i] = Calc.forBudget(calc, p.item_id, p.budget, p.owned)
  else
    plans[i] = Calc.planFor(calc, p.item_id, p.count, p.owned)
  end
end
local effective = Calc.effectiveTable(Case.settings.disenchant_table, Case.records, Case.min_samples)
io.write("Result = ", dump({rows = calc:rows(), plans = plans, effective = effective}), "\n")
