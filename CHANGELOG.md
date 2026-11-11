# Changelog

Each version of anvilbook ships the app and the `AnvilbookExport` addon together. "In game" lists
what changed in the addon, for the CurseForge file notes. "App" lists the rest.

## [0.8.0] - 2026-11-11

### In game

- **Alts:** the Crafts tab has a character list. Pick any character on your account that has
  opened its profession windows, and see its crafts. Plan still uses the bags of the character
  you play.
- **Any:** a third choice beside Learned and Unlearned. It prices every recipe of every
  profession, as if you had them all, so you can see what is worth investing in. The recipes
  that the character knows are marked as learned.
- The addon carries Forever's recipe list itself, so Unlearned and Any work without the app.
- After you update the addon, restart the game: this version adds a file.

### App

- The Crafts page has the Any choice too.
- The app no longer sends recipes in the addon's data file, because the addon has its own.

## [0.7.0] - 2026-10-19

### In game

- Unlearned lists Forever's own recipes, with Forever's reagents and learn skills. This adds
  about 930 recipes that classic does not have.
- Unlearned rows show their skill-up color and the skill they need. "~" marks a learn skill
  that the app estimates, for recipes that a trainer teaches.
- A click on an unlearned row says where to learn it: the pattern's name, a trainer, or with
  the profession.

### App

- Every recipe now comes from Forever's own game data (build 1.60.1.70450), not from the
  classic item database. The data ships with the app.
- The Crafts page marks an estimated learn skill with "≈".
- The public site prices Forever's recipes.

## [0.6.0] - 2026-10-19

### In game

- Crafts has an **All** tickbox. It also shows the recipes that lose money, the ones whose
  item has no AH price, and the ones with few listings. One listing far below the usual price
  can make a good recipe look like a loss, so you can now still see it. A loss shows in red.
  When a reagent has no price at all, the cost stays empty.
- **Learned** and **Unlearned** choose which recipes Crafts shows. Unlearned shows the recipes
  that your skill lets you learn now, with the skill they need. These come from the app.
- Tooltips show the craft profit also when it is a loss.
- The minimap button sits on the edge of Forever's larger minimap. Drag it to change its
  distance as well as its angle.

### App

- The Crafts page has the same All, Learned and Unlearned controls.
- The app sends the item database's recipes for your recorded professions to the game, with
  the skill overrides.
- The public site still shows only the recipes that a character knows.

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

[0.8.0]: https://github.com/traagel/anvilbook/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/traagel/anvilbook/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/traagel/anvilbook/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/traagel/anvilbook/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/traagel/anvilbook/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/traagel/anvilbook/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/traagel/anvilbook/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/traagel/anvilbook/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/traagel/anvilbook/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/traagel/anvilbook/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/traagel/anvilbook/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/traagel/anvilbook/releases/tag/v0.1.0
