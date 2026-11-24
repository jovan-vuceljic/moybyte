#!/usr/bin/env python3
"""The pack store: the browser console's packs as os.moybyte.com serves them
to the loader (docs/web_console_online_2026-11.md §4, §8, §12).

The loader on a board's origin fetches `<mirror><body digest>.pack` and runs
it only when its bytes hash to the digest the board's image names (§3, §6),
so the store carries the packs and decides nothing. Its tree:

    console/<body digest>.pack   the pack file as the add-on cart holds it
                                 (tools/gen_web_blob.py's, moybyte_web.pack)
    _headers                     every pack `Access-Control-Allow-Origin: *`
                                 and `immutable`: a name that is a digest
                                 never changes (Cloudflare Pages' and
                                 Netlify's format)

Its packs are those the add-on entries of the rolling releases' indexes name
(`carts-<board>.json`, tools/web_pack.py), taken from the same add-on carts
the boards install, each checked against its index entry and its digest:
every one of the stable release's, and the beta release's published in the
last DEV_DAYS days (§12: a dev board older than that updates its firmware).

    tools/pack_store.py fetch TAG DIR       a release's indexes and add-on
                                            carts into DIR, each file dated
                                            as the release published it (gh)
    tools/pack_store.py build OUT --stable DIR... [--dev DIR...]
                                            the tree to deploy, from fetched
                                            (or locally published) folders
    tools/pack_store.py check BASE INDEX... every digest the indexes (files
                                            or URLs) name has its pack at
                                            BASE/console/, served with
                                            Access-Control-Allow-Origin; BASE
                                            may be a local serve.py
                                            (firmware/web_runner/serve.py)

The deploy is `fetch` of firmware-latest and firmware-beta, `build`, an
upload of OUT to the host os.moybyte.com is served from, then `check` against
it with both releases' indexes.
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
HEADERS = """/console/*
  Access-Control-Allow-Origin: *
  Cache-Control: public, max-age=31536000, immutable
  Content-Type: application/octet-stream
"""
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
    """The pack bytes of the add-on `asset` (an index entry's) in `folder`,
    checked: the cart's size and sha256 as the index names them, and the
    pack's body digest as the entry's `fits`."""
    path = os.path.join(folder, asset["url"])
    with open(path, "rb") as f:
        data = f.read()
    if len(data) != asset.get("size") or hashlib.sha256(data).hexdigest() != asset.get("sha256"):
        raise StoreError("%s is not the cart its index names" % asset["url"])
    with zipfile.ZipFile(path) as z:
        name = web_pack.cart_id(digest) + ".moy/" + web_pack.PACK_FILE
        pack = z.read(name)
    try:
        got = web_pack.digest_of(pack)
    except web_pack.PageError as e:
        raise StoreError("%s: %s" % (asset["url"], e))
    if got != digest:
        raise StoreError("%s holds the pack %s, not %s" % (asset["url"], got[:12], digest[:12]))
    return pack


def wanted(folder, since=None):
    """{body digest: add-on asset entry} the indexes in `folder` name, only
    those whose cart is dated `since` (a timestamp) or later when given."""
    out = {}
    for name in _indexes(folder):
        with open(os.path.join(folder, name), "rb") as f:
            index = f.read()
        for digest, asset in _addons(index):
            path = os.path.join(folder, asset["url"])
            if since is not None and (not os.path.exists(path)
                                      or os.path.getmtime(path) < since):
                continue
            out.setdefault(digest, asset)
    return out


def build(out, stable=(), dev=(), days=DEV_DAYS, now=None):
    """Write the store's tree into `out` (replaced): every pack the `stable`
    folders' indexes name, and the `dev` folders' of the last `days` days.
    Returns the digests it holds."""
    since = (now if now is not None else time.time()) - days * 86400
    picks = [(folder, None) for folder in stable] + [(folder, since) for folder in dev]
    packs = {}
    for folder, cut in picks:
        for digest, asset in wanted(folder, cut).items():
            if digest not in packs:
                packs[digest] = pack_of(folder, digest, asset)
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "console"))
    for digest, data in packs.items():
        with open(os.path.join(out, "console", digest + ".pack"), "wb") as f:
            f.write(data)
    with open(os.path.join(out, "_headers"), "w") as f:
        f.write(HEADERS)
    return sorted(packs)


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
    """A release's indexes and the add-on carts they name into `dest`, each
    file's mtime the asset's publication date (for build's `dev` cut)."""
    assets = {a["name"]: a for a in _gh_json("release", "view", tag, "--json", "assets")["assets"]}
    os.makedirs(dest, exist_ok=True)
    names = [n for n in assets if n.startswith("carts-") and n.endswith(".json")]
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            _download(tag, name, tmp, dest, assets[name])
        for name in names:
            with open(os.path.join(dest, name), "rb") as f:
                for _digest, asset in _addons(f.read()):
                    if asset["url"] in assets and not os.path.exists(os.path.join(dest, asset["url"])):
                        _download(tag, asset["url"], tmp, dest, assets[asset["url"]])


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
    f = sub.add_parser("fetch", help="a release's indexes and add-on carts, dated")
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
