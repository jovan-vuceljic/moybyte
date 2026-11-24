#!/usr/bin/env python3
"""os.moybyte.com as static files: My consoles, its service worker and the
pack store (docs/web_console_online_2026-11.md §2's flow 2, §4, §5, §8).

The site's source is site/os/: the page (index.html, consoles.js), the
packs it keeps (packs.js, shared with the service worker), the worker
(sw.js) and the web app manifest. It runs no console and holds no carts: it
hands a window on a board's origin the bytes of a pack, and that window's
console keeps its carts on the board (§10, `.claude/rules/web.md`'s two
modes). The tree a build writes:

    index.html consoles.js packs.js manifest.webmanifest icon-*.png
    sw.js           stamped with the build's version and the files it keeps
    packs.json      {"newest": [...]}: the body digests of the newest pack
                    of each release (and of each --pack), which the service
                    worker keeps at install
    console/<body digest>.pack    tools/pack_store.py's tree
    _headers        the pack store's, then the site's: its files `no-cache`
                    (a new build is a new service worker, which fetches them
                    again), and the page's content security policy. It is
                    Cloudflare Pages' and Netlify's format; no
                    Cross-Origin-Opener-Policy, which would cut the window
                    the link talks to off from its opener.

    tools/os_site.py build OUT [--stable DIR]... [--dev DIR]... [--pack FILE]...
                        the tree, from release folders as tools/pack_store.py
                        fetches them, and any pack files (a worktree's)
    tools/os_site.py serve DIR [--port N]
                        a built tree served as its host serves it, _headers
                        applied, on localhost (a secure context, so its
                        service worker runs)
"""

import argparse
import functools
import hashlib
import http.server
import importlib.util
import base64
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack_store  # noqa: E402
import web_pack  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "site", "os")
FILES = ("index.html", "consoles.js", "packs.js", "manifest.webmanifest")
ICONS = {"icon-192.png": 12, "icon-512.png": 32}    # the 16-pixel mascot, scaled
# The files the service worker keeps, as it names them; "./" is index.html.
SHELL = ["./", "consoles.js", "packs.js", "manifest.webmanifest", "packs.json"] + sorted(ICONS)
HEADERS = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: no-referrer
  Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'
"""


def newest(folder):
    """The body digest of the add-on cart `folder`'s indexes name that was
    published last, or None."""
    best = None
    for digest, asset in pack_store.wanted(folder).items():
        path = os.path.join(folder, asset["url"])
        if os.path.exists(path) and (best is None or os.path.getmtime(path) > best[0]):
            best = (os.path.getmtime(path), digest)
    return best and best[1]


def _icons():
    """{name: PNG bytes}: the Moy mascot as the project site draws it."""
    spec = importlib.util.spec_from_file_location("moy_site_build", os.path.join(ROOT, "site", "build.py"))
    site = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(site)
    pal = site.palette()
    return {name: base64.b64decode(site.moy_mark(pal, scale).split(",", 1)[1])
            for name, scale in ICONS.items()}


def build(out, stable=(), dev=(), packs=(), now=None):
    """Write the site's tree into `out` (replaced). Returns the digests of
    the packs it holds."""
    held = set(pack_store.build(out, stable=stable, dev=dev, now=now))
    want = [newest(f) for f in list(stable) + list(dev)]
    for path in packs:
        with open(path, "rb") as f:
            data = f.read()
        try:
            digest = web_pack.digest_of(data)
        except web_pack.PageError as e:
            raise pack_store.StoreError("%s: %s" % (path, e))
        with open(os.path.join(out, "console", digest + ".pack"), "wb") as f:
            f.write(data)
        held.add(digest)
        want.append(digest)
    want = [d for i, d in enumerate(want) if d in held and d not in want[:i]]
    for name in FILES:
        shutil.copy(os.path.join(SOURCE, name), os.path.join(out, name))
    for name, png in _icons().items():
        with open(os.path.join(out, name), "wb") as f:
            f.write(png)
    with open(os.path.join(out, "packs.json"), "w") as f:
        json.dump({"newest": want}, f)
    h = hashlib.sha256()
    for name in sorted(FILES) + sorted(ICONS) + ["packs.json"]:
        with open(os.path.join(out, name), "rb") as f:
            h.update(name.encode() + b"\0" + f.read())
    with open(os.path.join(SOURCE, "sw.js"), encoding="utf-8") as f:
        sw = f.read()
    if sw.count("@VERSION@") != 1 or sw.count("@SHELL@") != 1:
        raise SystemExit("os_site: sw.js must name @VERSION@ and @SHELL@ once each")
    with open(os.path.join(out, "sw.js"), "w", encoding="utf-8") as f:
        f.write(sw.replace("@VERSION@", h.hexdigest()[:16]).replace("@SHELL@", json.dumps(SHELL)))
    with open(os.path.join(out, "_headers"), "a") as f:
        f.write(HEADERS)
        for name in ["/", "/index.html", "/sw.js"] + ["/" + s for s in SHELL[1:]]:
            f.write("%s\n  Cache-Control: no-cache\n" % name)
    return sorted(held)


def read_headers(path):
    """[(pattern, [(name, value)])] of a _headers file."""
    rules = []
    with open(path) as f:
        for line in f:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if not line[0].isspace():
                rules.append((line.strip(), []))
            elif rules:
                name, _, value = line.strip().partition(":")
                rules[-1][1].append((name.strip(), value.strip()))
    return rules


def headers_for(rules, path):
    """The headers every rule matching `path` names, in order."""
    out = []
    for pattern, hs in rules:
        if pattern == path or (pattern.endswith("*") and path.startswith(pattern[:-1])):
            out += hs
    return out


class Host(http.server.SimpleHTTPRequestHandler):
    """A built tree as a static host serves it: `/` is index.html, and every
    response carries the headers _headers names for its path."""

    extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map,
                          **{".js": "text/javascript", ".webmanifest": "application/manifest+json",
                             ".json": "application/json"})

    def __init__(self, *a, rules=(), **kw):
        self.rules = rules
        super().__init__(*a, **kw)

    def log_message(self, *a):
        pass

    def end_headers(self):
        path = self.path.split("?", 1)[0]
        named = headers_for(self.rules, path)
        for name, value in named:
            self.send_header(name, value)
        if not any(n.lower() == "cache-control" for n, _ in named):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def guess_type(self, path):
        if path.endswith(".pack"):
            return "application/octet-stream"
        return super().guess_type(path)


def serve(folder, port, host="127.0.0.1"):
    rules = read_headers(os.path.join(folder, "_headers"))
    handler = functools.partial(Host, directory=folder, rules=rules)
    srv = http.server.ThreadingHTTPServer((host, port), handler)
    print("serving %s at http://localhost:%d/" % (folder, srv.server_address[1]), flush=True)
    srv.serve_forever()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="the tree to deploy")
    b.add_argument("out")
    b.add_argument("--stable", action="append", default=[], metavar="DIR")
    b.add_argument("--dev", action="append", default=[], metavar="DIR")
    b.add_argument("--pack", action="append", default=[], metavar="FILE")
    s = sub.add_parser("serve", help="a built tree, served as its host would")
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
    print("os_site: %s holds the site and %d pack(s)" % (args.out, len(held)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
