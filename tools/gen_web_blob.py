#!/usr/bin/env python3
"""Pack `firmware/web_runner/dist` for the browser console add-on, and name it
in the image beside the loader page.

The browser console is not in the firmware: it is an add-on cart a console
installs into its store (native/moy_net/moy_page.h), whose payload is the
PACK this writes (native/moy_net/moy_page.h's layout: a 4 KiB head naming each asset,
then the PRE-GZIPPED assets of the ASSETS table in
native/moy_net/moy_webhost.c). The image carries the sha256 of the
pack's body (the page it fits, the pack's identity), the sha256 of the whole
pack file (what the loader checks), whether its console is online (board.toml's
`[web] console`) and the bundle's stamp, in the C file this emits, with the
loader (firmware/web_runner/loader.html, docs/web_console_online_2026-11.md
§3) gzipped beside them: the page a board whose console is online serves at
its root, which fetches the pack from the mirrors this build names (§4). A
release publishes the cart for that digest beside the payload
(tools/web_pack.py), and the console's webhost serves a pack only when its
head names the same digest.

Usage (every board's build.sh, through tools/esp32_build_lib.sh):

    tools/gen_web_blob.py --out <native>/moy_web/moy_web_blob.gen.c \
        --pack dist/<board>/moybyte_web.pack [--require] [--online] [--mirror URL]...

THE MIRRORS (§4, §8): where the loader fetches `<mirror><body digest>.pack`
after this origin's cache and the board's own copy, in order. `--mirror`
names them; with none, `MOYBYTE_WEB_MIRRORS` (space-separated) does, else a
CI build names os.moybyte.com alone and any other build names this machine's
`firmware/web_runner/serve.py` first (DEV_PORT on its LAN address), because a
worktree's digest is published nowhere else.

With no usable bundle it names no page and says so loudly, and `--require`
(set by CI and by `MOYBYTE_REQUIRE_WEB_BUNDLE=1`) makes that a failure.
"Usable" is decided by the bytes: every asset's raw file is present, and a
`.gz` beside it inflates to exactly that file (a `.gz` left behind by a
removed bundle, or one a half-finished build did not refresh, is not a
bundle). The output is rewritten whenever its text differs. The default is
soft because building the bundle needs emsdk (~1.7 GB) and a firmware flash
is the daily loop; an image published to a device must never be the one that
names no console, which is what --require is for. Same doctrine as
`MOYBYTE_REQUIRE_UNIX_MP` (.claude/rules/testing.md).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import os
import socket
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_config                                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_RUNNER = os.path.join(ROOT, "firmware", "web_runner")
WEBHOST_C = os.path.join(ROOT, "native", "moy_net", "moy_webhost.c")
DEFAULT_DIST = os.path.join(ROOT, "firmware", "web_runner", "dist")
PACK_MAGIC = b"MOYWEB01"           # moy_page.h's MOY_WEB_PACK_* and its head
PACK_HEAD = 4096
PACK_MAX = 12
PACK_NAME = 40
LOADER = os.path.join(WEB_RUNNER, "loader.html")
LOADER_BUDGET = 4096               # gzipped (docs/web_console_online_2026-11.md §3)
SITE_MIRROR = "https://os.moybyte.com/console/"
DEV_PORT = 8321                    # serve.py's default port
DEFAULT_OUT = os.path.join(
    ROOT, "native", "moy_web",
    "moy_web_blob.gen.c")


def asset_names():
    """The files a browser needs, read from the webhost's own ASSETS table
    (native/moy_net/moy_webhost.c).

    Not a second list. The allowlist the server serves from and the set the
    pack holds have to be the same set -- an asset in one and not the other is
    either a 404 on a board that has the bytes, or dead weight in every pack.
    """
    with open(WEBHOST_C) as f:
        text = f.read()
    table = text[text.index("} ASSETS[] = {"):]
    table = table[:table.index("};")]
    return re.findall(r'\{"([^"]+)", "[^"]+"\}', table)


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def _gz_matches(gz, raw):
    """True when `gz` inflates to exactly the bytes of `raw`."""
    try:
        return gzip.decompress(_read(gz)) == _read(raw)
    except (OSError, EOFError, zlib.error):
        return False


def pick(dist, name):
    """(path, served_name) for one asset, or (None, None) when the bundle has
    no usable copy of it.

    The RAW file is the bundle -- it is what the web build copies into `dist/`
    -- and the `.gz` beside it is derived from it. The board serves
    `<name>.gz` with `Content-Encoding: gzip` and the browser inflates it, so
    the gz is what gets packed when it IS that file's gzip, and the served name
    keeps the `.gz` suffix, which the webhost looks up first.

    Decided by CONTENT, never by which file exists or is newer: a `.gz` whose
    raw file is gone is the leftover of a bundle that was removed (packing it
    ships a console nobody has built in a while), and a `.gz` that does not
    inflate to the raw file beside it is a build that stopped between the two.
    Neither is a bundle. A raw file with no `.gz` is packed as it is.
    """
    gz = os.path.join(dist, name + ".gz")
    raw = os.path.join(dist, name)
    if not os.path.exists(raw):
        return None, None
    if os.path.exists(gz):
        return (gz, name + ".gz") if _gz_matches(gz, raw) else (None, None)
    return raw, name


def diagnose(dist, name):
    """Why `pick` found nothing for `name`, as a phrase for the build log."""
    if not os.path.exists(os.path.join(dist, name)):
        if os.path.exists(os.path.join(dist, name + ".gz")):
            return "%s (only its .gz is there; the file it came from is gone)" % name
        return name
    return "%s (its .gz is not the gzip of the file beside it)" % name


def collect(dist):
    """[(served_name, path, size, sha256)] or [] when the bundle is incomplete.

    ALL OR NOTHING: a console missing its wasm is not a partial console, it is
    a page that fails to boot with a browser-console error nobody will read.
    """
    out, missing = [], []
    for name in asset_names():
        path, served = pick(dist, name)
        if path is None:
            missing.append(name)
            continue
        data = _read(path)
        out.append((served, path, len(data), hashlib.sha256(data).hexdigest()))
    if missing:
        return [], missing
    return out, []


def stamp_of(assets):
    """"<count> <total bytes> <12 hex of the bundle digest>"."""
    total = sum(a[2] for a in assets)
    digest = hashlib.sha256()
    for served, _path, size, sha in assets:
        digest.update(("%s:%d:%s;" % (served, size, sha)).encode())
    return "%d %d %s" % (len(assets), total, digest.hexdigest()[:12])


def pack_bytes(items):
    """(pack bytes, body sha256) of [(served name, bytes)] in moy_web_blob.h's
    PACK layout: the head, then each asset 4-byte aligned at the offset its
    entry names."""
    if len(items) > PACK_MAX:
        raise SystemExit("gen_web_blob: %d assets, a pack holds %d"
                         % (len(items), PACK_MAX))
    body = bytearray()
    entries = []
    for served, data in items:
        if len(served.encode()) >= PACK_NAME:
            raise SystemExit("gen_web_blob: %s is too long a name for a pack" % served)
        body += b"\0" * (-len(body) % 4)
        entries.append((served, PACK_HEAD + len(body), len(data)))
        body += data
    body += b"\0" * (-len(body) % 4)
    digest = hashlib.sha256(bytes(body)).digest()
    head = bytearray(PACK_HEAD)
    struct.pack_into("<8sII32s", head, 0, PACK_MAGIC, len(entries),
                     PACK_HEAD + len(body), digest)
    for i, (served, off, size) in enumerate(entries):
        struct.pack_into("<%dsII" % PACK_NAME, head, 48 + i * (PACK_NAME + 8),
                         served.encode(), off, size)
    return bytes(head) + bytes(body), digest


def pack(assets):
    """pack_bytes of collect()'s assets."""
    return pack_bytes([(served, _read(path)) for served, path, _s, _h in assets])


def lan_address():
    """This machine's address on its LAN, or None: the source address of a
    route out (a UDP connect sends nothing)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return None if ip.startswith("127.") or ip == "0.0.0.0" else ip


def default_mirrors():
    """The mirrors a build names when its command line names none (the
    module docstring, THE MIRRORS)."""
    env = os.environ.get("MOYBYTE_WEB_MIRRORS")
    if env is not None:
        return env.split()
    if os.environ.get("CI"):
        return [SITE_MIRROR]
    ip = lan_address()
    return (["http://%s:%d/console/" % (ip, DEV_PORT)] if ip else []) + [SITE_MIRROR]


def loader_page(mirrors):
    """The loader as the image serves it: loader.html with its mirrors
    substituted and without its comment lines and indentation."""
    with open(LOADER, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.read().splitlines()]
    text = "\n".join(ln for ln in lines if ln and not ln.startswith("//")) + "\n"
    if text.count("@MIRRORS@") != 1:
        raise SystemExit("gen_web_blob: loader.html must name @MIRRORS@ once")
    return text.replace("@MIRRORS@", json.dumps(list(mirrors)))


def loader_gz(mirrors):
    """loader_page gzipped, byte for byte the same for the same mirrors."""
    return gzip.compress(loader_page(mirrors).encode(), 9, mtime=0)


def _bytes_c(name, data):
    rows = [", ".join("0x%02x" % b for b in data[i:i + 16])
            for i in range(0, len(data), 16)]
    return ["const unsigned char %s[%d] = {" % (name, max(len(data), 1)),
            "    " + ",\n    ".join(rows or ["0"]), "};"]


def render(assets, dist, want=None, whole=None, online=False, mirrors=()):
    """The C file: the digests of the pack this image names and the stamp of
    the bundle in it, or none of them when no bundle was built, and the
    loader with `mirrors`."""
    total = sum(a[2] for a in assets)
    L = []
    L.append("/* AUTO-GENERATED by tools/gen_web_blob.py -- do not edit, do")
    L.append(" * not commit (gitignored). Regenerated by every board's build.sh")
    L.append(" * before the moy_web module is staged.")
    L.append(" *")
    L.append(" * Source bundle: %s" % dist)
    for served, _path, size, sha in assets:
        L.append(" *   %-20s %8d B  %s" % (served, size, sha[:16]))
    L.append(" *   %-20s %8d B  total" % ("", total))
    L.append(" * Loader mirrors: %s" % (" ".join(mirrors) or "none"))
    L.append(" */")
    L.append('#include "moy_web_blob.h"')
    L.append("")
    # The stamp and the digest are CODE, not comments: ccache hashes the
    # PREPROCESSED source, where comments are gone, so they are what makes a
    # new bundle a new object.
    L.append("const unsigned char moy_web_named = %du;" % (want is not None))
    hexes = ", ".join("0x%02x" % b for b in (want or bytes(32)))
    L.append("const unsigned char moy_web_want[32] = {%s};" % hexes)
    L.append("const unsigned char moy_web_pack_sha[32] = {%s};"
             % ", ".join("0x%02x" % b for b in (whole or bytes(32))))
    L.append('const char moy_web_stamp[] = "%s";'
             % (stamp_of(assets) if assets and want is not None else "0 0 none"))
    L.append("const unsigned char moy_web_online = %du;" % bool(online))
    gz = loader_gz(mirrors)
    L.extend(_bytes_c("moy_web_loader", gz))
    L.append("const unsigned int moy_web_loader_len = %du;" % len(gz))
    return "\n".join(L) + "\n"


def watched_sources(root=ROOT):
    """Every source the bundle is built FROM, relative to the repo root.

    DERIVED from the web runner's own `board.toml` staging declaration, never
    globbed. A hand-written `runtime/*.py` glob cannot see `device/`, and that
    tree holds `device_canvas.py` -- the class the browser RASTERIZES with since
    moycore stage 4. The single most consequential file in the bundle was the
    one file the staleness check could not look at.

    Plus the runner's own authored modules and page (`web_boot.py`,
    `web_canvas.py`, the driver html/js), which build.sh copies by name and no
    board file describes -- its header says so.
    """
    rels = set()
    try:
        staged = board_config.staged_modules(WEB_RUNNER, root=ROOT)
        pkgs = board_config.staged_packages(WEB_RUNNER, root=ROOT)
    except Exception:  # a broken board file is a build failure, not this warning
        staged, pkgs = {}, {}
    for src in staged.values():
        rels.add(os.path.relpath(str(src), ROOT))
    for pkg in pkgs.values():
        for base, _dirs, names in os.walk(str(pkg)):
            for n in names:
                if n.endswith(".py"):
                    rels.add(os.path.relpath(os.path.join(base, n), ROOT))
    web = os.path.join("firmware", "web_runner")
    d = os.path.join(root, web)
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if name.endswith((".py", ".js", ".html")):
            rels.add(os.path.join(web, name))
    return sorted(rels)


def stale_sources(assets, root=ROOT, limit=3):
    """Console sources NEWER than the bundle about to be packed.

    The staleness the digest cannot catch: the image names the pack it was
    built with, but a dist that is itself behind `runtime/` packs a stale
    console while reporting success -- and the image then names a browser
    console older than the firmware it is part of.

    A warning, never fatal: mtimes are a heuristic (a checkout reorders them, a
    touched file means nothing), and a build that refuses on a heuristic is a
    build people learn to work around.
    """
    if not assets:
        return []
    oldest = min(os.path.getmtime(a[1]) for a in assets)
    out = []
    for rel in watched_sources(root):
        try:
            newer = os.path.getmtime(os.path.join(root, rel)) > oldest
        except OSError:
            continue
        if newer:
            out.append(rel)
            if len(out) >= limit:
                break
    return out


def write_if_changed(path, text):
    try:
        if open(path, "r").read() == text:
            return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dist", default=DEFAULT_DIST,
                    help="the web runner's built bundle (default: %(default)s)")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="the C file to write (default: the moy_web module)")
    ap.add_argument("--pack", metavar="PATH",
                    help="where to write the pack (the add-on cart's payload)")
    ap.add_argument("--require", action="store_true",
                    help="fail instead of emitting an empty bundle")
    ap.add_argument("--online", action="store_true",
                    help="the board's console is online (board.toml's [web] "
                         "console): its root serves the loader")
    ap.add_argument("--mirror", action="append", metavar="URL",
                    help="a mirror the loader fetches <URL><body digest>.pack "
                         "from, in order (default: default_mirrors())")
    ap.add_argument("--quiet", action="store_true",
                    help="no banner when there is no bundle -- for callers "
                         "that are not building a board image (the unix test "
                         "binary), where 'this image has no console' is not "
                         "the news it sounds like")
    args = ap.parse_args(argv)

    assets, missing = collect(args.dist)
    if missing:
        msg = ("no browser console for this image: %s unusable in %s"
               % (", ".join(diagnose(args.dist, n) for n in missing), args.dist))
        # Strict under CI unless explicitly opted out: an image PUBLISHED to a
        # device must never be the one that quietly has no console, which is
        # the whole failure this feature exists to end. A local flash is the
        # daily loop and building the bundle needs emsdk (~1.7GB), so there it
        # only warns. Same shape as MOYBYTE_REQUIRE_UNIX_MP (.claude/rules/testing.md).
        req = os.environ.get("MOYBYTE_REQUIRE_WEB_BUNDLE")
        if args.require or req == "1" or (req is None
                                          and os.environ.get("CI")):
            sys.stderr.write(
                "!! %s\n"
                "!! build it first:  firmware/web_runner/build.sh\n"
                "!! (unset MOYBYTE_REQUIRE_WEB_BUNDLE / drop --require to build\n"
                "!!  an image that names no browser console)\n" % msg)
            return 1
        if not args.quiet:
            sys.stderr.write(
                "\n"
                "!! ============================================================\n"
                "!! %s\n"
                "!! This image names NO BROWSER CONSOLE: no add-on cart fits it.\n"
                "!! Build it with firmware/web_runner/build.sh and rebuild.\n"
                "!! ============================================================\n"
                "\n" % msg)

    want = whole = None
    if assets:
        data, want = pack(assets)
        whole = hashlib.sha256(data).digest()
        if args.pack:
            os.makedirs(os.path.dirname(os.path.abspath(args.pack)), exist_ok=True)
            with open(args.pack, "wb") as f:
                f.write(data)
            print("browser console packed: %s, %d B, digest %s"
                  % (args.pack, len(data), want.hex()[:12]))
        stale = [] if args.quiet else stale_sources(assets)
        if stale:
            sys.stderr.write(
                "!! the bundle being packed is OLDER than console sources, "
                "e.g.\n%s\n!! rebuild it (firmware/web_runner/build.sh) or "
                "this image names a stale browser console\n"
                % "\n".join("!!     " + s for s in stale))
    mirrors = args.mirror if args.mirror is not None else default_mirrors()
    write_if_changed(args.out, render(assets, args.dist, want, whole,
                                      args.online, mirrors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
