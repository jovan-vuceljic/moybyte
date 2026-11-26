#!/usr/bin/env python3
"""The pack store: the browser console's packs as os.moybyte.com serves them
to the loader (docs/web_console_online_2026-11.md §4, §8, §12).

The loader on a board's origin fetches `<mirror><body digest>.pack` and runs
it only when its bytes hash to the digest the board's image names (§3, §6),
so the store carries the packs and decides nothing. Its tree is
`console/<body digest>.pack`, the pack file as the add-on cart holds it
(tools/gen_web_blob.py's, moybyte_web.pack). os.moybyte.com is GitHub Pages
(owner, 2026-11-24), which sends `Access-Control-Allow-Origin: *` on every
file, so the loader on a board's origin can read it; a name that is a
digest never changes, and the loader keeps what it read under it.

Its packs are those of the rolling releases' add-on carts
(`moybyte_web-<body digest>.moy.zip`, tools/web_pack.py), the carts the
boards install, read by their names, so a board whose console is online
(the C3 Zero's), whose index names no add-on, finds its pack too: every one
of the stable release's, and the beta release's published in the last
DEV_DAYS days (§12: a dev board older than that updates its firmware). Each
is checked against its name's digest, and against its entry where an index
(`carts-<board>.json`) names it.

Beside them it mirrors each release's indexes whole, at
`console/releases/<tag>/carts-<board>.json` (cart_index.index_mirror names
the address), and every file beside them that their official entries name
(web_pack.shelf_files: each official cart's zip, its cover, the licence),
because no page can read a release download. A page on a board's origin
lists its console's release from there; the site's own player lists its
channel's release from there and installs its official carts from the
files beside it (site/build.py's RELEASE_INDEX). The copy is the release's
bytes, its signature with them, and a page and a board alike take it only
once that signature verifies (cart_index.parse_index, cart_index.EntryRead),
which is what vouches for every file's sha256 beside it. A release folder
holds only what its current indexes name: an official cart's earlier zip,
still on the release, is not mirrored, and the folder is replaced with the
store on every deploy. `fetch` writes the tag it read into the folder
(TAG_FILE), so `build` knows where each folder's indexes go.

    tools/pack_store.py fetch TAG DIR       a release's indexes, add-on
                                            carts and official carts' files
                                            into DIR, each file dated as the
                                            release published it (gh)
    tools/pack_store.py build OUT --stable DIR... [--dev DIR...]
                                            OUT/console/ (replaced) from
                                            fetched (or locally published)
                                            folders: the packs, and the
                                            indexes and official carts'
                                            files of each folder that names
                                            its tag
    tools/pack_store.py check BASE INDEX... every digest the indexes (files
                                            or URLs) name has its pack at
                                            BASE/console/, served with
                                            Access-Control-Allow-Origin; BASE
                                            may be a local serve.py
                                            (firmware/web_runner/serve.py)

The deploy is .github/workflows/pages.yml's: `fetch` of firmware-latest and
firmware-beta, `tools/os_site.py build` (this `build` with My consoles
beside the packs) into the Pages site it assembles, and the upload. `check`
against https://os.moybyte.com with both releases' indexes says whether it
holds every pack they name.
"""

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import web_pack  # noqa: E402

DEV_DAYS = 30
TAG_FILE = "release-tag"         # in a fetched folder: the release it holds
# The origin a check's requests name: a board's, which is what the loader runs under.
CHECK_ORIGIN = "http://192.168.4.1"


class StoreError(Exception):
    """A pack the store cannot carry, said so a person can act."""


def _addons(index_bytes):
    """[(body digest, add-on asset entry)] of an index's add-on entries."""
    out = []
    for c in web_pack.earlier_entries(index_bytes):
        assets = [a for a in c.get("assets") or () if isinstance(a, dict)]
        if assets:
            out.append((c["moybyte"]["fits"], assets[0]))
    return out


def _indexes(folder):
    return sorted(n for n in os.listdir(folder)
                  if n.startswith("carts-") and n.endswith(".json"))


def pack_of(folder, digest, asset):
    """The pack bytes of the add-on `asset` (wanted's) in `folder`, checked:
    the cart's size and sha256 as an index names them, where one does, and
    the pack's body digest as `digest`."""
    path = os.path.join(folder, asset["url"])
    with open(path, "rb") as f:
        data = f.read()
    if "sha256" in asset and (len(data) != asset.get("size")
                              or hashlib.sha256(data).hexdigest() != asset["sha256"]):
        raise StoreError("%s is not the cart its index names" % asset["url"])
    name = web_pack.cart_id(digest) + ".moy/" + web_pack.PACK_FILE
    try:
        with zipfile.ZipFile(path) as z:
            pack = z.read(name)
    except (KeyError, zipfile.BadZipFile):
        raise StoreError("%s holds no %s" % (asset["url"], name))
    try:
        got = web_pack.digest_of(pack)
    except web_pack.PageError as e:
        raise StoreError("%s: %s" % (asset["url"], e))
    if got != digest:
        raise StoreError("%s holds the pack %s, not %s" % (asset["url"], got[:12], digest[:12]))
    return pack


def wanted(folder, since=None):
    """{body digest: add-on asset entry} of the add-on carts in `folder`,
    only those dated `since` (a timestamp) or later when given: the entry an
    index in `folder` names, else one of the cart's name alone."""
    named = {}
    for name in _indexes(folder):
        with open(os.path.join(folder, name), "rb") as f:
            index = f.read()
        for digest, asset in _addons(index):
            named.setdefault(asset["url"], (digest, asset))
    out = {}
    for name in sorted(os.listdir(folder)):
        if not web_pack.ADDON_ASSET.match(name):
            continue
        path = os.path.join(folder, name)
        if since is not None and os.path.getmtime(path) < since:
            continue
        digest, asset = named.get(name) or (name[len("moybyte_web-"):-len(".moy.zip")],
                                            {"url": name})
        out.setdefault(digest, asset)
    return out


def build(out, stable=(), dev=(), days=DEV_DAYS, now=None):
    """Write the store into `out`/console/ (replaced; the rest of `out` is
    left as it is): every pack the `stable` folders' indexes name, and the
    `dev` folders' of the last `days` days. Returns the digests it holds."""
    since = (now if now is not None else time.time()) - days * 86400
    picks = [(folder, None) for folder in stable] + [(folder, since) for folder in dev]
    packs = {}
    for folder, cut in picks:
        for digest, asset in wanted(folder, cut).items():
            if digest not in packs:
                packs[digest] = pack_of(folder, digest, asset)
    folder = os.path.join(out, "console")
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    for digest, data in packs.items():
        with open(os.path.join(folder, digest + ".pack"), "wb") as f:
            f.write(data)
    for src in list(stable) + list(dev):
        mirror_release(src, folder)
    return sorted(packs)


def release_tag(folder):
    """The release tag `fetch` recorded in `folder`, or None."""
    try:
        with open(os.path.join(folder, TAG_FILE)) as f:
            tag = f.read().strip()
    except OSError:
        return None
    return tag if tag and "/" not in tag and not tag.startswith(".") else None


def mirror_release(src, console):
    """`src`'s indexes, byte for byte, into `console`/releases/<its tag>/,
    and beside them every file their official entries name
    (web_pack.shelf_files), each held to the size and sha256 its entry
    names; none where the folder names no tag. A file the folder lacks or
    holds wrong is left out and said on stderr: its cart's install fails
    as an unreachable one, and nothing else of the store does. Returns the
    names written."""
    tag = release_tag(src)
    if tag is None:
        return []
    dest = os.path.join(console, "releases", tag)
    os.makedirs(dest, exist_ok=True)
    names = _indexes(src)
    files = {}
    for name in names:
        with open(os.path.join(src, name), "rb") as f:
            files.update(web_pack.shelf_files(f.read()))
        shutil.copyfile(os.path.join(src, name), os.path.join(dest, name))
    for name, ref in sorted(files.items()):
        try:
            with open(os.path.join(src, name), "rb") as f:
                data = f.read()
        except OSError:
            print("pack_store: %s names %s, which %s does not hold" % (tag, name, src),
                  file=sys.stderr)
            continue
        if len(data) != ref.get("size") or hashlib.sha256(data).hexdigest() != ref.get("sha256"):
            print("pack_store: %s's %s is not the file its index names" % (tag, name),
                  file=sys.stderr)
            continue
        with open(os.path.join(dest, name), "wb") as f:
            f.write(data)
        names.append(name)
    return names


def _read(where):
    if "://" in where:
        with urllib.request.urlopen(where, timeout=30) as r:
            return r.read()
    with open(where, "rb") as f:
        return f.read()


def check(base, indexes, origin=CHECK_ORIGIN):
    """[problem] for every digest the `indexes` (paths or URLs) name whose
    pack `base` does not serve whole, checked, to a board's origin; [] when
    every one is there."""
    digests = sorted({d for where in indexes for d, _a in _addons(_read(where))})
    problems = []
    for digest in digests:
        url = base.rstrip("/") + "/console/%s.pack" % digest
        req = urllib.request.Request(url, headers={"Origin": origin})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                allow = r.headers.get("Access-Control-Allow-Origin")
                data = r.read()
        except (urllib.error.URLError, OSError) as e:
            problems.append("%s: %s" % (url, getattr(e, "code", None) or e))
            continue
        if allow not in ("*", origin):
            problems.append("%s: no Access-Control-Allow-Origin for %s" % (url, origin))
        try:
            got = web_pack.digest_of(data)
        except web_pack.PageError as e:
            problems.append("%s: %s" % (url, e))
            continue
        if got != digest:
            problems.append("%s: serves the pack %s" % (url, got[:12]))
    if not digests:
        problems.append("the indexes name no browser console")
    return problems


def _gh_json(*args):
    p = subprocess.run(("gh",) + args, capture_output=True, text=True)
    if p.returncode != 0:
        raise StoreError("gh %s: %s" % (" ".join(args), p.stderr.strip()))
    return json.loads(p.stdout)


def fetch(tag, dest):
    """A release's indexes, its add-on carts and the official carts' files
    the indexes name (web_pack.shelf_files) into `dest`, each file's mtime
    the asset's publication date (for build's `dev` cut)."""
    assets = {a["name"]: a for a in _gh_json("release", "view", tag, "--json", "assets")["assets"]}
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, TAG_FILE), "w") as f:
        f.write(tag + "\n")
    names = [n for n in assets if n.startswith("carts-") and n.endswith(".json")]
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            _download(tag, name, tmp, dest, assets[name])
        want = {n for n in assets if web_pack.ADDON_ASSET.match(n)}
        for name in names:
            with open(os.path.join(dest, name), "rb") as f:
                index = f.read()
            want |= set(web_pack.shelf_files(index))
        for name in sorted(want):
            if name in assets and not os.path.exists(os.path.join(dest, name)):
                _download(tag, name, tmp, dest, assets[name])


def _download(tag, name, tmp, dest, meta):
    p = subprocess.run(("gh", "release", "download", tag, "-p", name, "-D", tmp, "--clobber"),
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise StoreError("gh release download %s %s: %s" % (tag, name, p.stderr.strip()))
    path = os.path.join(dest, name)
    os.replace(os.path.join(tmp, name), path)
    when = datetime.datetime.fromisoformat(meta["createdAt"].replace("Z", "+00:00")).timestamp()
    os.utime(path, (when, when))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="a release's indexes, add-on carts and the carts they name, dated")
    f.add_argument("tag")
    f.add_argument("dest")
    b = sub.add_parser("build", help="the store's tree to deploy")
    b.add_argument("out")
    b.add_argument("--stable", action="append", default=[], metavar="DIR")
    b.add_argument("--dev", action="append", default=[], metavar="DIR")
    b.add_argument("--days", type=int, default=DEV_DAYS)
    c = sub.add_parser("check", help="every digest the indexes name is served")
    c.add_argument("base")
    c.add_argument("index", nargs="+")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "fetch":
            fetch(args.tag, args.dest)
        elif args.cmd == "build":
            got = build(args.out, args.stable, args.dev, args.days)
            print("pack store: %d packs in %s" % (len(got), args.out))
        else:
            problems = check(args.base, args.index)
            for p in problems:
                print("!! " + p, file=sys.stderr)
            if problems:
                return 1
            print("pack store: every pack the indexes name is served at %s" % args.base)
    except StoreError as e:
        print("pack_store: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
