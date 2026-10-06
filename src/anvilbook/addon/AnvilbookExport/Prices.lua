local _, ns = ...
local Prices = {}
ns.Prices = Prices

Prices.CALLER = "Anvilbook"

local function auctionator()
  return Auctionator and Auctionator.API and Auctionator.API.v1
end
Prices.auctionator = auctionator

local function ask(name, id)
  local api = auctionator()
  if not (api and api[name]) then
    return nil
  end
  local ok, price = pcall(api[name], Prices.CALLER, id)
  return ok and type(price) == "number" and price > 0 and price or nil
end

-- On Forever, Auctionator loses its database at each load, so any price it has is from this
-- session and newer than the app's last import.
function Prices.live(id)
  return ask("GetAuctionPriceByItemID", id)
end

-- The app's latest scan with live prices on top. Listed counts exist only in the app's scan;
-- an item priced only by Auctionator has available = nil.
function Prices.build(data, ids)
  local prices = data and ns.Codec.prices(data.prices) or {}
  local live, seen = 0, {}
  local function check(id)
    if seen[id] then
      return
    end
    seen[id] = true
    local price = Prices.live(id)
    if price then
      local entry = prices[id] or {day_high = 0}
      entry.min_price, entry.live = price, true
      prices[id] = entry
      live = live + 1
    end
  end
  for id in pairs(prices) do
    check(id)
  end
  for id in pairs(ids) do
    check(id)
  end
  return prices, live
end

function Prices.vendor(data, ids)
  local vendor = data and ns.Codec.vendor(data.vendor) or {}
  for id in pairs(ids) do
    vendor[id] = vendor[id] or ask("GetVendorPriceByItemID", id)
  end
  return vendor
end
