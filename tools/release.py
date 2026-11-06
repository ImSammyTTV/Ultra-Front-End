"""Publish a release on the GitHub project: every copy of the exe picks it up and updates itself (server.py update_step).

    1. Raise VERSION in server.py, commit, push.
    2. python tools/release.py [notes.md] [--venv DIR] [--dry-run [--skip-build]]

Every release has a picture of its own, shown on its card in the app's What's new: assets/whatsnew/<VERSION>.jpg, committed
and pushed with the release's commit (16:9, about 1280x720). It goes at the top of the notes. Without a notes file, GitHub
writes the notes from the commits. It builds Game Frontend.exe with PyInstaller and uploads it
as UltraFrontEnd.exe under the tag v<VERSION>, with THIRD_PARTY_NOTICES.md and licenses.zip beside it (the updater only ever
takes UltraFrontEnd.exe). Needs the GitHub CLI (gh), signed in to an account that can publish to the project.

    --venv DIR    build in a fresh venv at DIR (made with --clear), with the build packages pinned to the versions installed
                  in this Python, so the exe holds only what they pull in
    --dry-run     every check and the build, then print the gh command instead of running it
    --skip-build  with --dry-run only: check the exe already in dist/ instead of building
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from importlib.metadata import version as installed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET = "UltraFrontEnd.exe"
SETUP = "UltraFrontEnd-Setup.exe"  # what people download first; ASSET is what copies update themselves from
NOTICES = "THIRD_PARTY_NOTICES.md"  # shipped beside the exe on every release, with licenses/ zipped as licenses.zip
BUILT = os.path.join(ROOT, "dist", "Game Frontend.exe")
PKG_TOC = os.path.join(ROOT, "build", "Game Frontend", "PKG-00.toc")
BUILD_PACKAGES = ["pywebview", "pystray", "pillow", "pyinstaller"]
MIN_SIZE = 5 * 1024 * 1024

# Run by the build's own Python (same version and PyInstaller as the build): prints the VERSION the exe's server module sets.
EMBEDDED_VERSION = r"""
import dis, sys
from PyInstaller.archive.readers import CArchiveReader
code = CArchiveReader(sys.argv[1]).open_embedded_archive("PYZ.pyz").extract("server")
prev = None
for ins in dis.get_instructions(code):
    if ins.opname == "STORE_NAME" and ins.argval == "VERSION" and prev is not None and prev.opname == "LOAD_CONST":
        print(prev.argval)
        break
    prev = ins
"""


def run(*cmd, check=True):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"{' '.join(cmd[:3])} failed:\n{r.stderr or r.stdout}")
    return r


def version_key(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def read_server():
    server = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    version = re.search(r'^VERSION = "([^"]+)"', server, re.M)
    repo = re.search(r'^UPDATE_REPO = "([^"]+)"', server, re.M)
    if not version or not repo:
        sys.exit("Couldn't read VERSION and UPDATE_REPO from server.py.")
    return version[1], repo[1]


def check_git(tag):
    if run("git", "status", "--porcelain").stdout.strip():
        sys.exit("Commit (or put aside) your changes first: a release is built from exactly what's committed.")
    head = run("git", "rev-parse", "HEAD").stdout.strip()
    run("git", "fetch", "--quiet", "origin")
    if run("git", "merge-base", "--is-ancestor", head, "origin/main", check=False).returncode:
        sys.exit("Push this commit to GitHub first (git push): the release points at it.")
    if run("git", "tag", "-l", tag).stdout.strip():
        sys.exit(f"Tag {tag} already exists here: raise VERSION in server.py.")
    if run("git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}").stdout.strip():
        sys.exit(f"Tag {tag} already exists on GitHub: raise VERSION in server.py.")
    return head


def check_github(repo, version):
    if run("gh", "auth", "status", "--hostname", "github.com", check=False).returncode:
        sys.exit("gh isn't signed in to github.com: run gh auth login.")
    run("gh", "repo", "view", repo, "--json", "nameWithOwner")  # stops on network errors or a repo gh can't see
    latest = run("gh", "release", "view", "--repo", repo, "--json", "tagName", check=False)
    if latest.returncode:
        if (latest.stderr or latest.stdout).strip() != "release not found":
            sys.exit(f"gh release view failed:\n{latest.stderr or latest.stdout}")
        return  # no releases yet
    tag = json.loads(latest.stdout)["tagName"]
    if version_key(version) <= version_key(tag):
        sys.exit(f"VERSION in server.py is {version}, but {tag} is already out: raise it first.")


def make_venv(path):
    path = os.path.abspath(path)
    if os.path.exists(path) and not os.path.isfile(os.path.join(path, "pyvenv.cfg")):
        sys.exit(f"{path} exists and isn't a venv: pick an empty or new folder.")
    pins = [f"{p}=={installed(p)}" for p in BUILD_PACKAGES]
    print(f"Making a fresh venv at {path} with {' '.join(pins)}…")
    run(sys.executable, "-m", "venv", "--clear", path)
    py = os.path.join(path, "Scripts", "python.exe")
    run(py, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *pins)
    return py


def verify(py, version):
    if not os.path.isfile(BUILT):
        sys.exit(f"No exe at {BUILT}.")
    size = os.path.getsize(BUILT)
    if size <= MIN_SIZE:
        sys.exit(f"{BUILT} is only {size / 1e6:.1f} MB: the build is broken.")
    with open(BUILT, "rb") as f:
        if f.read(2) != b"MZ":
            sys.exit(f"{BUILT} isn't a Windows exe.")
    if not os.path.isfile(PKG_TOC) or NOTICES not in open(PKG_TOC, encoding="utf-8", errors="replace").read():
        sys.exit(f"{NOTICES} isn't in {PKG_TOC}: the exe would ship without it.")
    embedded = run(py, "-c", EMBEDDED_VERSION, BUILT).stdout.strip()
    if embedded != version:
        sys.exit(f"The exe says VERSION {embedded or '(none found)'}, but the tag is v{version}.")


def mac_assets(folder, version, out):
    """The Mac build's zip (what Mac copies update from) and disk image (the first install), checked to be this version."""
    import plistlib
    import zipfile
    zip_path, dmg = os.path.join(folder, "UltraFrontEnd-mac.zip"), os.path.join(folder, "UltraFrontEnd.dmg")
    for f in (zip_path, dmg):
        if not os.path.isfile(f):
            sys.exit(f"No {os.path.basename(f)} in {folder}: run build-mac.sh on the Mac first.")
    with zipfile.ZipFile(zip_path) as z:
        plist = next((n for n in z.namelist() if n.endswith(".app/Contents/Info.plist") and n.count("/") == 2), None)
        got = str(plistlib.loads(z.read(plist)).get("CFBundleShortVersionString") or "") if plist else ""
    if got != version:
        sys.exit(f"The Mac app says version {got or '(none)'}, but the tag is v{version}: rebuild it on the Mac.")
    zip_out, dmg_out = os.path.join(out, "UltraFrontEnd-mac.zip"), os.path.join(out, "UltraFrontEnd-mac.dmg")
    shutil.copyfile(zip_path, zip_out)
    shutil.copyfile(dmg, dmg_out)
    return [zip_out, dmg_out]


def picture_notes(notes, version, repo, head, out):
    """The notes with the release's own picture at the top (What's new shows it on the release's card). The picture must be
    in the release's commit, so its address (by tag) never changes."""
    path = f"assets/whatsnew/{version}.jpg"
    if subprocess.run(["git", "-C", ROOT, "cat-file", "-e", f"{head}:{path}"], capture_output=True).returncode:
        sys.exit(f"No picture for this release: add {path} (16:9, about 1280x720), commit and push it. Every release has its own.")
    text = open(notes, encoding="utf-8").read() if notes else ""
    line = f"![Ultra Front End {version}](https://raw.githubusercontent.com/{repo}/v{version}/{path})"
    with_picture = os.path.join(out, "notes.md")
    with open(with_picture, "w", encoding="utf-8") as f:
        f.write(text if line in text else line + "\n\n" + text)
    return with_picture


def main():
    ap = argparse.ArgumentParser(description="Publish a GitHub release of Ultra Front End.")
    ap.add_argument("notes", nargs="?", help="release notes file (default: GitHub writes them from the commits)")
    ap.add_argument("--venv", help="build in a fresh venv at this folder")
    ap.add_argument("--dry-run", action="store_true", help="check and build, then print the gh command")
    ap.add_argument("--skip-build", action="store_true", help="with --dry-run: check the exe already in dist/")
    ap.add_argument("--mac", help="folder holding the Mac build from build-mac.sh (UltraFrontEnd-mac.zip and UltraFrontEnd.dmg): published beside the Windows files")
    args = ap.parse_args()
    if args.skip_build and not args.dry_run:
        sys.exit("--skip-build only works with --dry-run.")
    if args.notes and not os.path.isfile(args.notes):
        sys.exit(f"No notes file at {args.notes}.")

    version, repo = read_server()
    tag = f"v{version}"
    head = check_git(tag)
    check_github(repo, version)

    py = make_venv(args.venv) if args.venv else sys.executable
    if args.skip_build:
        print("Skipping the build: checking the exe already in dist/.")
    else:
        print(f"Building {version}…")
        start = time.time()
        run(py, "-m", "PyInstaller", "--noconfirm", "--clean", "Game Frontend.spec")
        if not os.path.isfile(BUILT) or os.path.getmtime(BUILT) < start - 2:
            sys.exit(f"PyInstaller didn't write {BUILT}.")
    verify(py, version)

    out = os.path.join(ROOT, "dist", "release")
    os.makedirs(out, exist_ok=True)
    exe = os.path.join(out, ASSET)
    shutil.copyfile(BUILT, exe)
    with open(exe, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    notices = os.path.join(out, NOTICES)
    shutil.copyfile(os.path.join(ROOT, NOTICES), notices)
    licenses = shutil.make_archive(os.path.join(out, "licenses"), "zip", ROOT, "licenses")
    # the installer people download first: the same exe under the Setup name, which opens its install window (setup_ui.py)
    setup = os.path.join(out, SETUP)
    shutil.copyfile(exe, setup)

    mac_files = mac_assets(args.mac, version, out) if args.mac else []
    if not args.notes:
        sys.exit("Write the release notes (a .md file) and pass it: the release's picture goes at their top.")
    notes = picture_notes(args.notes, version, repo, head, out)
    cmd = ["gh", "release", "create", tag, setup, exe, *mac_files, notices, licenses, "--repo", repo, "--target", head,
           "--title", f"Ultra Front End {version}", "--notes-file", notes]
    print(f"{tag} for {repo}: {os.path.getsize(exe) / 1e6:.1f} MB, SHA-256 {digest}, Setup {os.path.getsize(setup) / 1e6:.1f} MB, with {NOTICES} and licenses.zip.")
    if args.dry_run:
        print("Dry run: would run\n  " + subprocess.list2cmdline(cmd))
        return
    print("Publishing…")
    run(*cmd)
    print(f"Done: https://github.com/{repo}/releases/tag/{tag}")


if __name__ == "__main__":
    main()
