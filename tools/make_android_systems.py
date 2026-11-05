"""Builds android/app/src/main/assets/systems.json from server.py: the consoles (SYSTEMS, SYSTEM_GROUPS) with their ROM
file types, libretro box-art set and the folder names that mean each one, so Android sorts ROMs exactly as Windows does.

The Android emulators for each console are in android/app/src/main/assets/emulators.json, written by hand.
    python tools/make_android_systems.py
"""
import ast
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "android", "app", "src", "main", "assets", "systems.json")


def server_literal(name):
    tree = ast.parse(open(os.path.join(ROOT, "server.py"), encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


def main():
    systems = server_literal("SYSTEMS")
    by_name = {s[1]: s for s in systems}
    out = []
    for group, names in server_literal("SYSTEM_GROUPS"):
        for name in names:
            _, _, thumbs, ext, _ = by_name[name]
            out.append({"name": name, "group": group, "thumbs": thumbs, "ext": ext.split()})
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"patterns": [[s[0], s[1]] for s in systems],  # folder name -> console, first match wins
                   "systems": out}, f, indent=1, ensure_ascii=False)
    print(f"{len(out)} systems -> {OUT}")


if __name__ == "__main__":
    main()
