# Emulators and ROMs

> **Ultra Front End doesn't come with any games, ROMs, BIOS files or console keys, and never downloads them.** Use only
> games and system files you've copied from your own consoles and discs. The emulators it installs are separate
> projects, each with its own licence.

## Systems (Settings › Systems)

Each console you play is a **system**. The setup guide adds the ones you choose; add more with **+ Add a system**, or
**Find installed emulators** to pick up ones already on your PC.

A system's page shows:

- **Its emulator:** installed or not, with **Install** (it downloads from the emulator's own project), **Open emulator
  folder** and **Choose program** for one you already have.
- **BIOS and firmware:** what it needs and what's missing, with **Open BIOS folder**.
- **Remove this system:** takes it off the list. Your games, BIOS files and the emulator stay on your PC.

Emulators are only ever downloaded from their own projects. If an install fails, the message says where the download
was and where it should have been.

## Your ROMs folder

Setup makes a folder for each console in your ROMs folder (`C:\Ultra-Front-End\ROMs` on Windows, `~/ROMs` on Linux).
Drop your games into the right one:

```
ROMs
├── <console>
│   ├── BIOS          ← that console's BIOS files (see the README.txt inside)
│   └── My Game.iso
└── …
```

- Each `BIOS` folder's `README.txt` lists the files that console needs; they're copied to the emulator for you.
- Zipped games are unpacked when you play them.
- Games kept as folders (as some consoles' dumps are) count as one game each.

## Emulator updates

**Settings › About › Emulator updates** checks the emulators the frontend installed for newer versions and updates
them, one at a time.

## Achievements

Connect **RetroAchievements** in **Settings › Accounts**, and an emulated game's page lists its achievements and which
you've unlocked.
