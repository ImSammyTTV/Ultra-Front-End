"""Builds android/app/src/main/assets/systems.json: the consoles (from server.py's SYSTEMS and SYSTEM_GROUPS) and, for
each one, the Android emulators that can play it and the intent that starts a game in them.

The emulator packages and launch intents come from ES-DE's Android tables (MIT licence, see THIRD_PARTY_NOTICES.md):
    python tools/make_android_tables.py <dir with ES-DE's resources/systems/android/es_systems.xml and es_find_rules.xml>
"""
import ast
import json
import os
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "android", "app", "src", "main", "assets", "systems.json")

# our console name -> ES-DE's system name on Android
ESDE = {
    "Wii U": "wiiu", "Wii": "wii", "GameCube": "gc", "Switch 2": "switch", "Switch": "switch", "3DS": "n3ds", "DS": "nds",
    "64DD": "n64dd", "N64": "n64", "SNES": "snes", "FDS": "fds", "NES": "nes", "GBA": "gba", "GBC": "gbc", "Game Boy": "gb",
    "Virtual Boy": "virtualboy", "Pokemon Mini": "pokemini", "Game & Watch": "gameandwatch", "PS4": "ps4", "PS Vita": "psvita",
    "PS3": "ps3", "PS2": "ps2", "PSP": "psp", "PS1": "psx", "NAOMI 2": "naomi2", "NAOMI": "naomi", "Atomiswave": "atomiswave",
    "Model 3": "model3", "Dreamcast": "dreamcast", "Saturn": "saturn", "Sega CD": "segacd", "32X": "sega32x", "Genesis": "genesis",
    "Master System": "mastersystem", "Game Gear": "gamegear", "SG-1000": "sg-1000", "Xbox 360": "xbox360", "Xbox": "xbox",
    "PC-FX": "pcfx", "PC Engine CD": "pcenginecd", "PC Engine": "pcengine", "Neo Geo Pocket": "ngpc", "Neo Geo CD": "neogeocd",
    "Neo Geo": "neogeo", "Atari Jaguar": "atarijaguar", "Atari Lynx": "atarilynx", "Atari 7800": "atari7800",
    "Atari 5200": "atari5200", "Atari 2600": "atari2600", "Atari ST": "atarist", "Atari 8-bit": "atari800",
    "WonderSwan": "wonderswancolor", "Arcade": "arcade", "3DO": "3do", "CD-i": "cdimono1", "ColecoVision": "colecovision",
    "Intellivision": "intellivision", "Vectrex": "vectrex", "Odyssey 2": "odyssey2", "N-Gage": "ngage", "DOS": "dos",
    "ScummVM": "scummvm", "C64": "c64", "VIC-20": "vic20", "Amiga": "amiga", "ZX Spectrum": "zxspectrum",
    "Amstrad CPC": "amstradcpc", "MSX": "msx", "Apple II": "apple2", "Flash": "flash",
}
# tokens the app knows how to fill in; a command using any other is left out
KNOWN = {"%ROM%", "%ROMSAF%", "%ROMPROVIDER%", "%ROMPATH%", "%EXTERNALDATA%", "%INTERNALDATA%", "%ANDROIDPACKAGE%",
         "%ACTION%", "%DATA%", "%CATEGORY%", "%MIMETYPE%", "%ACTIVITY_CLEAR_TASK%", "%ACTIVITY_CLEAR_TOP%", "%BASENAME%"}


def server_literal(name):
    tree = ast.parse(open(os.path.join(ROOT, "server.py"), encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


def main(esde_dir):
    import re
    systems = {s[1]: s for s in server_literal("SYSTEMS")}
    groups = server_literal("SYSTEM_GROUPS")
    rules = ET.parse(os.path.join(esde_dir, "es_find_rules.xml")).getroot()
    packages = {}
    for emu in rules.iter("emulator"):
        entries = [e.text.strip() for r in emu.iter("rule") if r.get("type") == "androidpackage" for e in r.iter("entry") if e.text]
        if entries:
            packages[emu.get("name")] = entries
    esde = {s.findtext("name"): s for s in ET.parse(os.path.join(esde_dir, "es_systems.xml")).getroot()}
    out, used = [], set()
    for group, names in groups:
        for name in names:
            _, _, thumbs, ext, _ = systems[name]
            exts = set(ext.split())
            emus = []
            s = esde.get(ESDE.get(name, ""))
            if s is not None:
                exts |= {e.lower() for e in (s.findtext("extension") or "").split()}
                for c in s.iter("command"):
                    cmd = (c.text or "").strip()
                    m = re.match(r"%EMULATOR_([A-Z0-9!+_-]+)%\s*(.*)", cmd)
                    if not m or m.group(1) not in packages:
                        continue
                    tokens = set(re.findall(r"%[A-Z0-9_]+%", re.sub(r"%EXTRA[A-Z]*_[A-Za-z0-9_.]+%", "", m.group(2))))
                    if tokens - KNOWN:
                        continue
                    label = (c.get("label") or m.group(1).title()).replace(" (Standalone)", "")
                    emus.append({"label": label, "emu": m.group(1), "cmd": m.group(2)})
                    used.add(m.group(1))
            out.append({"name": name, "group": group, "thumbs": thumbs, "ext": sorted(exts), "emulators": emus})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"source": "Emulator packages and launch intents: ES-DE (MIT), resources/systems/android",
                   "patterns": [[s[0], s[1]] for s in server_literal("SYSTEMS")],  # folder name -> console, first match wins
                   "systems": out, "packages": {k: v for k, v in packages.items() if k in used}}, f, indent=1, ensure_ascii=False)
    print(f"{len(out)} systems, {sum(len(s['emulators']) for s in out)} launch commands, {len(used)} emulators -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
