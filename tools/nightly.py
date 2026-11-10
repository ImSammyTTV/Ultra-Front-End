"""Nightly builds (run by .github/workflows/nightly.yml, never by hand for a release).

    python tools/nightly.py version   sets VERSION in server.py (in the build's checkout only, never committed) to the next
                                      release's number plus the build time, e.g. 1.2.7-nightly.202611080300, and prints it
    python tools/nightly.py version dev   the same for a dev build (.github/workflows/dev.yml): 1.2.7-dev.202611080300,
                                      which updates itself to the newer dev builds only
    python tools/nightly.py smoke EXE starts the built exe as a test copy (port 8141) and waits for its helper to answer
                                      with that version: a build that doesn't start is never published

The updater (server.py version_key) puts 1.2.7-nightly.* after 1.2.6 and before 1.2.7, so people on the nightly channel
move on to the release when it comes out, and people on the main channel never get a nightly build.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "server.py")


def set_version(kind="nightly"):
    text = open(SERVER, encoding="utf-8").read()
    m = re.search(r'^VERSION = "(\d+)\.(\d+)\.(\d+)"', text, re.M)
    if not m:
        sys.exit("Couldn't read VERSION from server.py")
    major, minor, patch = map(int, m.groups())
    version = f"{major}.{minor}.{patch + 1}-{kind}.{datetime.now(timezone.utc):%Y%m%d%H%M}"
    text = text[:m.start()] + f'VERSION = "{version}"' + text[m.end():]
    open(SERVER, "w", encoding="utf-8", newline="").write(text)
    print(version)


def smoke(exe):
    version = re.search(r'^VERSION = "([^"]+)"', open(SERVER, encoding="utf-8").read(), re.M)[1]
    proc = subprocess.Popen([exe, "--background", "--port", "8141"], cwd=os.path.dirname(os.path.abspath(exe)))
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            if proc.poll() is not None:
                sys.exit(f"The exe quit on its own (code {proc.returncode})")
            try:
                with urllib.request.urlopen("http://127.0.0.1:8141/api/ping", timeout=3) as r:
                    ping = json.load(r)
                if ping.get("version") != version:
                    sys.exit(f"The exe says it is {ping.get('version')}, not {version}")
                with urllib.request.urlopen("http://127.0.0.1:8141/", timeout=5) as r:
                    if b"<html" not in r.read(4000).lower():
                        sys.exit("The exe's page didn't load")
                print(f"Started and answered as {version}")
                return
            except OSError:
                time.sleep(1)
        sys.exit("The exe's helper never answered")
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["version"]:
        set_version("dev" if sys.argv[2:3] == ["dev"] else "nightly")
    elif sys.argv[1:2] == ["smoke"] and len(sys.argv) == 3:
        smoke(sys.argv[2])
    else:
        sys.exit(__doc__)
