# Changelog

Each version of anvilbook ships the app and the `AnvilbookExport` addon together. "In game" lists
what changed in the addon, for the CurseForge file notes. "App" lists the rest.

## [0.5.1] - 2026-10-06

### In game

- The game's AddOns list shows the same version as the release. Version 0.5.0 showed 2.0.

### App

- Each GitHub release takes its notes from this changelog.

## [0.5.0] - 2026-10-06

### In game

- A new window shows anvilbook in the game. Type `/anvilbook`, or click the minimap button. It
  has the web page's tabs: Crafts, Plan, History, Sell-through, Share and Settings.
- When you open the auction house, your plan's shopping list docks beside it. A row gets a tick
  when you have bought it. One button searches for the whole list in Auctionator.
- Item tooltips show the listed count, the price change since the scan before, the profit for
  each cast, and the disenchant value for an enchanter.
- Esc > Options > AddOns > Anvilbook turns each part on or off.
- The crafting math runs in the game, so a change applies at once. Auctionator's prices from
  your scans in this session replace the app's prices.
- Crafts, Plan, the shopping panel and the tooltip lines also work without the app, on
  Auctionator's prices.
- The debug command moves from `/anvilbook` to `/anvilbook probe`.
- After you update the addon, restart the game. A `/reload` does not load the new files.

### App

- After each import, the app writes its data into the addon folder. The game reads it at the
  next `/reload`.
- Settings and sharing switches that you change in game reach the app at your next `/reload`.
  For each setting, the newer change wins.
- The Settings form sends only the fields that you change, so it cannot undo a change made in
  game.
- The status line shows an error when the app cannot write the addon's data.

## [0.4.0] - 2026-09-27

### App

- The running version shows in the app header and in the site footer, so a bug report can name
  its build.

## [0.3.0] - 2026-09-26

### App

- The sharing server address moves to Settings, and it starts as anvilbook.traagel.dev. The
  Share tab holds only consent and sign-in.

## [0.2.0] - 2026-09-26

### App

- Optional sharing, off until you turn it on: send your price scans, and publish what a
  character can craft. Each switch is separate.
- Accounts need only a username and a password. "Delete my account and everything I sent"
  removes all of it.
- A public site at anvilbook.traagel.dev shows the shared prices and crafting profits.

## [0.1.3] - 2026-09-26

### App

- The game folder search is faster, and the setup page explains which `Auctionator.lua` to
  pick.

## [0.1.2] - 2026-09-26

### App

- A logo.
- The page loads its own files correctly in the packaged app.

## [0.1.1] - 2026-09-26

### App

- The app searches your disk for the game only when you press the button.

## [0.1.0] - 2026-09-26

### In game

- The addon records the recipes you know, with their reagents, quantities and skill-up colors,
  when you open a profession window. It also records your skill level for each profession.
- It records what is in your bags, and the result of each disenchant.
- `/anvilbook` prints what the profession API returns, for bug reports.

### App

- Reads the prices that Auctionator saves, and keeps every scan as history. A save that is not
  a full auction house scan is skipped.
- Crafts: the cheapest way to get every reagent, and the profit for each recipe that your
  character knows.
- Plan: a shopping list for a budget.
- History and Sell-through.
- Values a crafted item by its disenchant materials, and learns the real yields from your
  disenchants.
- Finds the game and installs the addon from the web page.

[0.5.1]: https://github.com/traagel/anvilbook/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/traagel/anvilbook/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/traagel/anvilbook/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/traagel/anvilbook/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/traagel/anvilbook/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/traagel/anvilbook/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/traagel/anvilbook/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/traagel/anvilbook/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/traagel/anvilbook/releases/tag/v0.1.0
