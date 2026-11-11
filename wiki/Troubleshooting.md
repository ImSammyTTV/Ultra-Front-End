# Troubleshooting

## A game is missing

Installed games from the supported stores are found by themselves. For Steam games you haven't installed, and for
Epic, connect the account in **Settings › Accounts**. For anything else, add its folder (or a single game) in
**Settings › Libraries**. **Settings › General › Rescan everything** looks again.

## A game shows Install, but it's installed

Usually a store update that hasn't finished. Steam games being updated count as installed; if one still shows
Install, check the game in Steam itself.

## An emulated game won't start

Open **Settings › Systems** and choose the console. Its page says whether the emulator is installed and which BIOS
files are missing. Some consoles can't start any game without them.

## An emulator won't install

The message says why. **"…isn't on its own project"** means the emulator's download wasn't where the frontend
expected; it names both places. That usually means the project moved: please [open an issue](https://github.com/ImSammyTTV/Ultra-Front-End/issues/new)
with the message.

## A game has no description, or the wrong one

Wait a minute and open it again: Wikipedia sometimes asks the app to slow down for a moment. If it's still missing or
wrong, use **Y › Rename** and pick the right game from the list. See [Your games](Your-games.md#renaming-a-game).

## The wrong cover or background

**Y › Artwork** › **Change cover** (or background), and pick the right game in the list. If you chose art yourself
earlier, **Reset cover** (or background) brings back the automatic one.

## The in-game menu doesn't open

It opens over games started from the frontend. Check that **Settings › General › Open with the Xbox button** is on.
With a Steam Controller, press the Steam button once in the game.

## Wallpaper mode

See [Wallpaper mode › Good to know](Wallpaper-mode.md#good-to-know).

## Where are my settings and logs?

In the `data` folder beside the app (`C:\Ultra-Front-End\App\data` on Windows). `errors.log` holds any errors and
`emulator-install.log` any emulator install that failed. Updating never removes them. Attach `errors.log` when you
[report a bug](https://github.com/ImSammyTTV/Ultra-Front-End/issues/new).
