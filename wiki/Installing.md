# Installing

## Windows 10 and 11

1. Download **`UltraFrontEnd-Setup.exe`** from the [latest release](https://github.com/ImSammyTTV/Ultra-Front-End/releases/latest) and run it.
   No administrator prompt is needed.
2. Follow the **setup guide**: your name and icon, your time zone, your accounts, the consoles you play and whether it
   starts with Windows.
3. Play. Installed games are found by themselves.

> **Windows says it "protected your PC"?** The app isn't signed yet. Choose **More info › Run anyway**.

### Where everything goes

```
C:\Ultra-Front-End
├── App          ← the app, and its data folder (settings, art, logs)
├── ROMs         ← a folder for each console you play
└── Emulators    ← the emulators it installs for you
```

Your settings are in `C:\Ultra-Front-End\App\data`. Updating never removes them, and a fresh download picks them up again.

## Linux and Steam Deck (x86-64)

1. Download **`UltraFrontEnd-linux-x86_64.AppImage`** from the [latest release](https://github.com/ImSammyTTV/Ultra-Front-End/releases/latest).
   On a Steam Deck, do this in **Desktop Mode**.
2. Put it in a folder of your own (`~/Applications` is a good place), then right-click it › **Properties › Permissions ›
   Is executable**.
3. **Steam Deck Game Mode:** in Desktop Mode, right-click the AppImage › **Add to Steam**. It then shows in your Steam
   library under Non-Steam, with the Deck's controls.

Your ROMs go in `~/ROMs` unless you choose another folder (an SD card works). Emulators install from Flathub for your
account, with no password. Emulators you already have from Flathub, EmuDeck (`~/Applications`) or your distribution
are found too.

The in-game menu, screenshots and recording are Windows-only for now.

## Starting with Windows

**Settings › General › Start with Windows** has three choices: open the frontend, start in the background (ready for the
Xbox button), or don't start. [Wallpaper mode](Wallpaper-mode.md) needs it running, so pick one of the first two.

## Removing it

Delete `C:\Ultra-Front-End` (or wherever you installed it). Turn off **Start with Windows** first if it's on.
