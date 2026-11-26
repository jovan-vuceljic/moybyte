#!/usr/bin/env python3
"""os.moybyte.com's console folder as static files: My consoles, its service
worker and the pack store (docs/web_console_online_2026-11.md §2's flow 2,
§4, §5, §8).

os.moybyte.com is GitHub Pages (owner, 2026-11-24), and this is one folder
of the site .github/workflows/pages.yml assembles, beside the project site
(site/build.py's flasher and player): /console/. My consoles and the packs
share it, so the address the images name as their mirror
(gen_web_blob.SITE_MIRROR) is the page's own folder and its service
worker's scope. The source is site/os/: the page (index.html, consoles.js),
the packs it keeps (packs.js, shared with the service worker), the worker
(sw.js) and the web app manifest; kept.js (the list), link.js (the link's
site end), improv.js and setup.js (first setup over the cable) are the
flasher's too, which site/build.py copies beside it. The page wears the
project site's look: its top bar, footer, stylesheet, scheme switch and font
are site/build.py's (SITE_CSS, site_nav, SITE_FOOTER, scheme_script), taken
from the tree that builds it: a restyle of the site moves My consoles too, a
page never mixes two trees' looks, and pages.yml builds it with master's
tools once master has them, so it wears the stable site's. It runs no
console and holds no carts: it hands a window on a board's origin the bytes
of a pack, and that window's console keeps its carts on the board (§10,
`.claude/rules/web.md`'s two modes). What a build writes into OUT/console/ (replaced):

    index.html consoles.js packs.js kept.js link.js improv.js setup.js
    manifest.webmanifest icon-*.png
                    index.html and the manifest with their @MARKS@ filled:
                    the site's top bar, footer and colours
    site.css scheme.js petme128.woff2
                    the site's stylesheet, scheme switch and display font
    sw.js           stamped with the build's version and the files it keeps
    packs.json      {"newest": [...]}: the body digests of the newest pack
                    of each release (and of each --pack), which the service
                    worker keeps at install
    <body digest>.pack            tools/pack_store.py's
    releases/<tag>/carts-<board>.json and the official carts' files
                    each release's indexes, mirrored whole, and the zips,
                    covers and licence their official entries name
                    (tools/pack_store.py), which a page on a board's origin
                    reads its release from and the site's player lists and
                    installs its channel's official carts from

Pages sends every file with `Access-Control-Allow-Origin: *` and
`max-age=600` and takes no header file, so none is written: the loader
keeps a pack under its digest, and the service worker fetches its own files
with `cache: "reload"`. No page here may ever send
Cross-Origin-Opener-Policy, which would cut the window the link talks to off
from its opener.

    tools/os_site.py build OUT [--stable DIR]... [--dev DIR]... [--pack FILE]...
                        the folder, from release folders as tools/pack_store.py
                        fetches them, and any pack files (a worktree's)
    tools/os_site.py serve DIR [--port N]
                        a built site served as Pages serves it, on localhost
                        (a secure context, so its service worker runs): My
                        consoles at /console/
"""

import argparse
import base64
import functools
import hashlib
import http.server
import importlib.util
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack_store  # noqa: E402
import web_pack  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "site", "os")
FILES = ("index.html", "consoles.js", "packs.js", "kept.js", "link.js", "improv.js", "setup.js",
         "manifest.webmanifest")
ICONS = {"icon-192.png": 12, "icon-512.png": 32}    # the 16-pixel mascot, scaled
LOOK = ("site.css", "scheme.js", "petme128.woff2")    # the project site's, from site/build.py
STAMPED = ("index.html", "manifest.webmanifest")    # FILES whose @MARKS@ are filled
# The files the service worker keeps, as it names them; "./" is index.html.
SHELL = ["./", "consoles.js", "packs.js", "kept.js", "link.js", "improv.js", "setup.js",
         "manifest.webmanifest", "packs.json"] + sorted(ICONS) + list(LOOK)
# What GitHub Pages sends with every file, which `serve` copies.
PAGES_HEADERS = (("Access-Control-Allow-Origin", "*"), ("Cache-Control", "max-age=600"))


def newest(folder):
    """The body digest of the add-on cart in `folder` (pack_store.wanted) that was
    published last, or None."""
    best = None
    for digest, asset in pack_store.wanted(folder).items():
        path = os.path.join(folder, asset["url"])
        if os.path.exists(path) and (best is None or os.path.getmtime(path) > best[0]):
            best = (os.path.getmtime(path), digest)
    return best and best[1]


@functools.lru_cache(maxsize=None)
def _site():
    """This tree's site/build.py: the project site's look."""
    spec = importlib.util.spec_from_file_location("moy_site_build", os.path.join(ROOT, "site", "build.py"))
    site = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(site)
    return site


def _icons():
    """{name: PNG bytes}: the Moy mascot as the project site draws it."""
    site = _site()
    pal = site.palette()
    return {name: base64.b64decode(site.moy_mark(pal, scale).split(",", 1)[1])
            for name, scale in ICONS.items()}


def _look(out):
    """Write LOOK into `out`; returns the @MARKS@ the STAMPED files take."""
    site = _site()
    with open(os.path.join(out, "site.css"), "w", encoding="utf-8") as f:
        f.write(site.site_css("petme128.woff2"))
    with open(os.path.join(out, "scheme.js"), "w", encoding="utf-8") as f:
        f.write(site.scheme_script())
    shutil.copy(site.FONT, os.path.join(out, "petme128.woff2"))
    return {"@NAV@": site.site_nav(site.palette(), home="/", here="/console/"),
            "@FOOTER@": site.SITE_FOOTER,
            "@NIGHT@": dict(site.theme_roles("dark"))["bg"],
            "@DAY@": dict(site.theme_roles("light"))["bg"]}


def build(out, stable=(), dev=(), packs=(), now=None):
    """Write the console folder into `out`/console/ (replaced; the rest of
    `out` is left as it is). Returns the digests of the packs it holds."""
    held = set(pack_store.build(out, stable=stable, dev=dev, now=now))
    out = os.path.join(out, "console")
    want = [newest(f) for f in list(stable) + list(dev)]
    for path in packs:
        with open(path, "rb") as f:
            data = f.read()
        try:
            digest = web_pack.digest_of(data)
        except web_pack.PageError as e:
            raise pack_store.StoreError("%s: %s" % (path, e))
        with open(os.path.join(out, digest + ".pack"), "wb") as f:
            f.write(data)
        held.add(digest)
        want.append(digest)
    want = [d for i, d in enumerate(want) if d in held and d not in want[:i]]
    marks = _look(out)
    for name in FILES:
        if name not in STAMPED:
            shutil.copy(os.path.join(SOURCE, name), os.path.join(out, name))
            continue
        with open(os.path.join(SOURCE, name), encoding="utf-8") as f:
            text = re.sub(r"@[A-Z]+@", lambda m: marks[m.group(0)], f.read())
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(text)
    for name, png in _icons().items():
        with open(os.path.join(out, name), "wb") as f:
            f.write(png)
    with open(os.path.join(out, "packs.json"), "w") as f:
        json.dump({"newest": want}, f)
    h = hashlib.sha256()
    for name in sorted(FILES) + sorted(ICONS) + sorted(LOOK) + ["packs.json"]:
        with open(os.path.join(out, name), "rb") as f:
            h.update(name.encode() + b"\0" + f.read())
    with open(os.path.join(SOURCE, "sw.js"), encoding="utf-8") as f:
        sw = f.read()
    if sw.count("@VERSION@") != 1 or sw.count("@SHELL@") != 1:
        raise SystemExit("os_site: sw.js must name @VERSION@ and @SHELL@ once each")
    with open(os.path.join(out, "sw.js"), "w", encoding="utf-8") as f:
        f.write(sw.replace("@VERSION@", h.hexdigest()[:16]).replace("@SHELL@", json.dumps(SHELL)))
    return sorted(held)


class Pages(http.server.SimpleHTTPRequestHandler):
    """A built site as GitHub Pages serves it: a folder's index.html at its
    address, and PAGES_HEADERS on every response."""

    extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map,
                          **{".js": "text/javascript", ".webmanifest": "application/manifest+json",
                             ".json": "application/json", ".pack": "application/octet-stream"})

    def log_message(self, *a):
        pass

    def end_headers(self):
        for name, value in PAGES_HEADERS:
            self.send_header(name, value)
        super().end_headers()


def serve(folder, port, host="127.0.0.1"):
    handler = functools.partial(Pages, directory=folder)
    srv = http.server.ThreadingHTTPServer((host, port), handler)
    print("serving %s: My consoles at http://localhost:%d/console/" % (folder, srv.server_address[1]),
          flush=True)
    srv.serve_forever()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="OUT/console/, to deploy")
    b.add_argument("out")
    b.add_argument("--stable", action="append", default=[], metavar="DIR")
    b.add_argument("--dev", action="append", default=[], metavar="DIR")
    b.add_argument("--pack", action="append", default=[], metavar="FILE")
    s = sub.add_parser("serve", help="a built site, served as Pages serves it")
    s.add_argument("folder")
    s.add_argument("--port", type=int, default=8322)
    args = ap.parse_args(argv)
    if args.cmd == "serve":
        serve(os.path.abspath(args.folder), args.port)
        return 0
    try:
        held = build(args.out, args.stable, args.dev, args.pack)
    except pack_store.StoreError as e:
        print("os_site: %s" % e, file=sys.stderr)
        return 1
    print("os_site: %s/console/ holds My consoles and %d pack(s)" % (args.out, len(held)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
