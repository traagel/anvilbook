# Anvilbook Export

**This addon records data for [anvilbook](https://github.com/traagel/anvilbook), a small app that
runs on your own computer. On its own the addon does nothing you can see in game, apart from one
line in chat when it records your recipes.**

anvilbook answers the questions the auction house cannot:

- What is worth crafting right now, with the recipes **this character** knows?
- I have 3g 43s. How many can I make, and what exactly do I buy?
- Did that item actually sell, or is it just sitting there?
- Is this green worth more disenchanted than sold?

## What the addon records

Everything is written to its own SavedVariables file. Nothing is sent anywhere, and nothing is
uploaded.

| Recorded | When |
|---|---|
| Recipes you know, with reagents and quantities | You open a profession window |
| Your skill level for that profession | Same |
| Whether a recipe is orange, yellow, green or grey | Same |
| What is in your bags | While you play |
| Disenchant results (item, level, quality, materials) | You disenchant something |

The recipes come from the game itself, so they match this server, including any changed reagents
or skill levels.

## Setup

1. Install this addon and [Auctionator](https://www.curseforge.com/wow/addons/auctionator).
2. Download anvilbook for your computer from the
   [releases page](https://github.com/traagel/anvilbook/releases) and run it.
3. In game, open each profession window for a few seconds, then type `/reload`.
4. Scan the auction house with Auctionator, then type `/reload` again.

`/reload` matters: World of Warcraft writes addon data to disk only when you log out, disconnect,
or reload. No addon can write at any other moment, so that is how the data reaches the app.

## Commands

- `/anvilbook` prints what the profession API returns for the open window. Useful when something
  looks wrong, and for bug reports.

## Notes

- Built for **WoW Forever (Classic beta)**, client 1.60.1, English client.
- The addon never sends, receives, or changes anything in game. It reads the profession, bag, and
  loot APIs and writes its own saved file.
- Free and open source, MIT licence. Code, issues, and the app itself:
  [github.com/traagel/anvilbook](https://github.com/traagel/anvilbook)

Not affiliated with Blizzard Entertainment.
