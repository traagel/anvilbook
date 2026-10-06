local _, ns = ...
local Items = {}
ns.Items = Items

local QUALITY = {[0] = "Poor", [1] = "Common", [2] = "Uncommon", [3] = "Rare", [4] = "Epic", [5] = "Legendary"}
-- Only weapons and armor disenchant, so the calculator needs no other class names.
local CLASS = {[2] = "Weapon", [4] = "Armor"}
local decoded = {}

local function fromGame(id)
  local info = (C_Item and C_Item.GetItemInfo) or GetItemInfo
  if not info then
    return nil
  end
  local name, _, quality, itemLevel, requiredLevel, _, _, _, _, _, sellPrice, classID = info(id)
  if not name then
    if C_Item and C_Item.RequestLoadItemDataByID then
      C_Item.RequestLoadItemDataByID(id)
    end
    return nil
  end
  return {name = name, quality = QUALITY[quality] or quality, itemLevel = itemLevel, requiredLevel = requiredLevel,
          class = CLASS[classID], sellPrice = sellPrice}
end

-- The app's copy comes first: the game knows nothing about an item it has not cached yet.
function Items.details(id)
  if decoded[id] then
    return decoded[id]
  end
  local data = ns.data()
  local packed = data and data.items and data.items[id]
  if not packed then
    return fromGame(id)
  end
  local item = ns.Codec.item(packed)
  if not item.name then
    local game = fromGame(id)
    item.name = game and game.name
  end
  -- Without a name, ask again later: the game may not have the item cached yet.
  if item.name then
    decoded[id] = item
  end
  return item
end

function Items.name(id)
  local item = Items.details(id)
  return item and item.name or ("item " .. tostring(id))
end

function Items.icon(id)
  local get = (C_Item and C_Item.GetItemIconByID) or GetItemIcon
  return get and get(id)
end
