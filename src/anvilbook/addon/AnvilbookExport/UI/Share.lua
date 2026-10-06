local _, ns = ...
local W = ns.W

local MAX_CHARACTERS = 8

local function characters()
  local names = {}
  for name in pairs(AnvilbookExportDB and AnvilbookExportDB.characters or {}) do
    names[#names + 1] = name
  end
  table.sort(names)
  return names
end

ns.addTab({
  key = "share",
  label = "Share",
  create = function(panel)
    local y = 0
    local function place(region, height, x)
      region:SetPoint("TOPLEFT", x or 0, -y)
      y = y + height
      return region
    end
    place(W.label(panel, "Share your prices", "GameFontNormalLarge"), 24)
    panel.server = place(W.label(panel, ""), 18)
    panel.who = place(W.label(panel, ""), 18)
    panel.error = place(W.label(panel, ""), 22)
    panel.error:SetTextColor(1, 0.4, 0.4)
    panel.prices = place(W.check(panel, "Send my price scans after each import", function(checked)
      ns.Sync.set("push_prices", checked)
    end), 24)
    place(W.label(panel, "It sends item ids, the lowest price and the listed count, with the realm and the "
                         .. "scan time. Never your gold, your bags or your name.", "GameFontDisableSmall"), 26, 28)
    place(W.label(panel, "Publish what a character can craft", "GameFontNormal"), 22)
    panel.characters = {}
    for i = 1, MAX_CHARACTERS do
      local box = W.check(panel, "", function(checked)
        local published = {}
        for name, on in pairs(ns.Sync.settings().published_characters) do
          published[name] = on
        end
        published[panel.characters[i].character] = checked
        ns.Sync.set("published_characters", published)
      end)
      panel.characters[i] = place(box, 22)
    end
    panel.push = W.button(panel, "Push now", 110, function()
      ns.Sync.requestPush()
      panel.pushed:SetText("The app pushes after your next /reload.")
    end)
    panel.push:SetPoint("BOTTOMLEFT", 0, 22)
    panel.pushed = W.label(panel, "")
    panel.pushed:SetPoint("LEFT", panel.push, "RIGHT", 10, 0)
    local note = W.label(panel, "Changes here reach the app at your next /reload or logout. Sign-in and account "
                                .. "deletion are in the app's Share tab.", "GameFontDisableSmall")
    note:SetPoint("BOTTOMLEFT", 0, 0)
  end,
  refresh = function(panel)
    local share = ns.Sync.share()
    local settings = ns.Sync.settings()
    local signedIn = share.signed_in and true or false
    panel.server:SetText(("Server: %s"):format(share.server_url or "not known yet (run the app, then /reload)"))
    panel.who:SetText(signedIn and ("Signed in as |cffffffff%s|r."):format(share.username or "?")
                      or "Not signed in. Sign in on the Share tab of the anvilbook app in your browser.")
    panel.error:SetText(share.error or "")
    panel.prices:SetChecked(settings.push_prices and true or false)
    panel.prices:SetEnabled(signedIn)
    panel.push:SetEnabled(signedIn)
    local names = characters()
    for i, box in ipairs(panel.characters) do
      local name = names[i]
      box.character = name
      box:SetShown(name ~= nil)
      if name then
        box.label:SetText(name)
        box:SetChecked(settings.published_characters[name] and true or false)
        box:SetEnabled(signedIn)
      end
    end
  end,
})
