-- Decodes the packed strings that bridge.py writes into AnvilbookData.
local _, ns = ...
local Codec = {}
ns.Codec = Codec

function Codec.split(s, sep)
  local out, start = {}, 1
  if not s or s == "" then
    return out
  end
  while true do
    local at = s:find(sep, start, true)
    if not at then
      out[#out + 1] = s:sub(start)
      return out
    end
    out[#out + 1] = s:sub(start, at - 1)
    start = at + #sep
  end
end

function Codec.prices(s)
  local out = {}
  for _, entry in ipairs(Codec.split(s, ";")) do
    local f = Codec.split(entry, ":")
    local id = tonumber(f[1])
    if id then
      out[id] = {min_price = tonumber(f[2]), available = tonumber(f[3]), day_high = tonumber(f[4]) or 0}
    end
  end
  return out
end

function Codec.vendor(s)
  local out = {}
  for _, entry in ipairs(Codec.split(s, ";")) do
    local id, price = entry:match("^(%d+):(%d+)$")
    if id then
      out[tonumber(id)] = tonumber(price)
    end
  end
  return out
end

local ITEM_FIELDS = {"quality", "itemLevel", "requiredLevel", "class", "sellPrice", "vendorPrice"}
local TEXT_FIELDS = {quality = true, class = true}

function Codec.item(s)
  if not s then
    return nil
  end
  local f = Codec.split(s, "|")
  local item = {}
  for i, key in ipairs(ITEM_FIELDS) do
    local v = f[i]
    if v and v ~= "" then
      item[key] = TEXT_FIELDS[key] and v or tonumber(v)
    end
  end
  -- The name is last, so a "|" in it cannot shift the other fields.
  local name = table.concat(f, "|", #ITEM_FIELDS + 1)
  item.name = name ~= "" and name or nil
  return item
end

-- One entry for each scan in AnvilbookData.scans: {min_price, available}, or false when unlisted.
function Codec.history(s, scans)
  local out = {}
  local fields = Codec.split(s, ";")
  for i = 1, scans do
    local price, count = (fields[i] or ""):match("^(%d+),(%d+)$")
    out[i] = price and {min_price = tonumber(price), available = tonumber(count)} or false
  end
  return out
end
