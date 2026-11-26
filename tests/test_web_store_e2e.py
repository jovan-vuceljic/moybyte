"""Get Carts in the HOSTED console, in real Chrome (#124).

Two local servers stand in for the two kinds of host a carts index names:

  * PAGES -- the carts repository's Pages site, which answers every file with
    `Access-Control-Allow-Origin: *`: index.json, the licence texts, the
    MIRROR of each release asset (the repository's index maker names it), and the
    mirror of an external file the repository gives away itself;
  * RELEASES -- a GitHub release download and Debian's archive, neither of
    which sends a CORS header, so a page may ask and may not read.

The console is the built dist/ served by serve.py from a static directory with
an `indexes.json` beside it naming the PAGES index (the page's own twin of a
board's indexes.json). The page is on a third origin, so every rule here is
Chrome's own CORS, not a fake's.

What it proves, in order: a cart installs from the mirror and never from the
release; it lands in OPFS whole, binary file and record included, with nothing
left in staging; a cart whose external file's host the page cannot read asks
for the player's own copy, takes it, and installs it; a cart whose bytes are
wrong installs nothing; and on a second load in the same browser the carts and
the record come back out of OPFS and the installed cart PLAYS. Apart: an
external file with a mirror on PAGES installs from it, and the page asks the
player nothing and the archive's host not once.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_store_e2e.py

Gated like its siblings (`tests/web_e2e.py`): a missing toolchain SKIPS on a
bench and FAILS under CI. ~3 Chrome boots, ~90s.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

import pytest

import web_e2e
from cart_store_fixtures import sha, stored_zip, tar_gz
from web_e2e import RUNNER, ROOT, DIST

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome for ~90s)")


def _lua(folder, title, colour, extra=None):
    files = {"manifest.json": json.dumps({"format": "moy-1", "title": title,
                                          "runtime": "lua",
                                          "main": "main.lua"}).encode(),
             "main.lua": ("function _draw()\n  cls(%d)\n  print(%r, 8, 8, 7)\nend\n"
                          % (colour, title)).encode(),
             "LICENSES.txt": b"MIT, by the test.\n"}
    files.update(extra or {})
    return folder, files


# Rock Run's cover: one red the console's tiles never draw, so its card
# shows it or does not (_RED_PIXELS counts it on the canvas).
def _red_cover():
    from runtime import cover_png
    return cover_png.encode_indexed(bytes(cover_png.SIDE * cover_png.SIDE), b"\xff\x00\x00")


_RED_PIXELS = """(() => {
  const c = document.getElementById('cv');
  const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  let n = 0;
  for (let i = 0; i < d.length; i += 4) if (d[i] > 200 && d[i + 1] < 40 && d[i + 2] < 40) n++;
  return n;
})()"""


def _shelf(pages, releases):
    """Three Lua carts: one plain (with a binary file and a cover), one
    needing an external file from a host the page may not read, one whose
    mirror is corrupt."""
    lic = b"The MIT licence of the test carts.\n"
    pages.files["/carts/LICENCE.txt"] = lic
    cover = _red_cover()
    pages.files["/carts/rock/cover.png"] = cover
    carts = []
    data_bin = bytes((i * 37 + (i >> 8)) & 255 for i in range(70000))
    wad = bytes((i * 11 + 3) & 255 for i in range(90000))
    for cid, name, colour, extra, ext, corrupt in (
            ("rock", "Rock Run", 12, {"data.bin": data_bin}, None, False),
            ("dm", "Dungeon", 2, None, ("game.wad", wad), False),
            ("zap", "Zap Bad", 8, None, None, True)):
        folder, files = _lua(cid + ".moy", name, colour, extra)
        z = stored_zip(folder, files)
        tag = "%s-v1" % cid
        rel = "releases/%s/%s.zip" % (tag, folder)
        releases.files["/o/carts/releases/download/%s/%s.zip" % (tag, folder)] = z
        pages.files["/" + rel] = (z[:-40] + b"\0" * 40) if corrupt else z
        entry = {
            "id": cid, "name": name, "version": 1, "folder": folder, "runtime": "lua",
            "licence": {"spdx": "MIT", "name": "MIT License", "url": "carts/LICENCE.txt",
                        "size": len(lic), "sha256": sha(lic)},
            "assets": [{"name": folder + ".zip",
                        "url": "%s/o/carts/releases/download/%s/%s.zip"
                               % (releases.base, tag, folder),
                        "mirror": rel, "size": len(z), "sha256": sha(z),
                        "files": dict((fn, {"size": len(b), "sha256": sha(b)})
                                      for fn, b in files.items())}],
            "external": [],
        }
        if cid == "rock":
            entry["cover"] = {"url": "carts/rock/cover.png", "size": len(cover),
                              "sha256": sha(cover), "w": 128, "h": 128}
        if ext:
            path, body = ext
            arc = tar_gz({"pkg/" + path: body})
            releases.files["/debian/pool/%s.tar.gz" % path] = arc
            ltext = b"You may give this file away, and not sell it.\n"
            pages.files["/carts/%s.txt" % path] = ltext
            entry["external"].append({
                "path": path, "size": len(body), "sha256": sha(body),
                "licence": {"name": "The game data's licence", "url": "carts/%s.txt" % path,
                            "size": len(ltext), "sha256": sha(ltext)},
                "archive": {"urls": ["%s/debian/pool/%s.tar.gz" % (releases.base, path)],
                            "format": "tar.gz", "size": len(arc), "sha256": sha(arc),
                            "member": "pkg/" + path}})
        carts.append(entry)
    pages.files["/index.json"] = json.dumps(
        {"version": 1, "name": "Test shelf", "home": releases.base + "/o/carts",
         "carts": carts}).encode()
    return data_bin, wad


def _console(tmp_path, index_url):
    """dist/ as a static site, with the shelves this host chooses beside it."""
    site = tmp_path / "site"
    site.mkdir()
    for name in os.listdir(DIST):
        os.symlink(DIST / name, site / name)
    (site / "indexes.json").write_text(json.dumps({"indexes": [index_url]}))
    return site


# What the browser's store of record holds, read straight out of OPFS.
_OPFS = """(async () => {
  const root = await navigator.storage.getDirectory();
  const out = {carts: {}, record: null, staging: []};
  const carts = await root.getDirectoryHandle('carts');
  for (const id of %s) {
    try {
      const d = await carts.getDirectoryHandle(id);
      const f = {};
      for await (const [n, h] of d.entries()) {
        const b = new Uint8Array(await (await h.getFile()).arrayBuffer());
        const s = new Uint8Array(await crypto.subtle.digest('SHA-256', b));
        f[n] = [b.length, Array.from(s).map(x => x.toString(16).padStart(2, '0')).join('')];
      }
      out.carts[id] = f;
    } catch (e) { out.carts[id] = null; }
  }
  try { out.record = JSON.parse(await (await (await root.getFileHandle('installed.json')).getFile()).text()); } catch (e) {}
  try { for await (const [n] of (await root.getDirectoryHandle('install')).entries()) out.staging.push(n); } catch (e) {}
  return JSON.stringify(out);
})()"""

_FOLDERS = '["rock.moy", "dm.moy", "zap.moy"]'

_FORGET_APP = """(async () => {
  const carts = await (await navigator.storage.getDirectory()).getDirectoryHandle('carts');
  await carts.removeEntry('moybyte.get_carts.moy', {recursive: true});
  return 'gone';
})()"""


def test_a_hosted_console_installs_carts_into_its_own_store(tmp_path):
    web_e2e.require("store", "carts")
    pages, releases = web_e2e.Host(cors=True), web_e2e.Host(cors=False)
    data_bin, wad = _shelf(pages, releases)
    (tmp_path / "doom1.wad").write_bytes(wad)
    site = _console(tmp_path, pages.base + "/index.json")
    server, base = web_e2e.serve(site, web_e2e.free_port())
    profile = tmp_path / "chrome"
    at = web_e2e.get_carts_taps()
    try:
        out, js = web_e2e.run(tmp_path, "install", "?handheld=1&dev=1&cart=moybyte.get_carts.moy", [
            {"note": "Get Carts opened at boot; the index came from PAGES", "wait": 4000},
            {"shot": "list"},
            {"js": "window.__moyPersist ? window.__moyPersist.mode : 'none'"},
            {"note": "Rock Run's card draws its cover", "js": _RED_PIXELS},
            {"note": "Rock Run: the plain cart", "click": at["cards"][1]},
            {"wait": 800}, {"shot": "rock"},
            {"click": at["verb"]},
            {"wait": 5000}, {"shot": "rock_ready"},
            {"js": "window.__moyInstalled || ''"},
            {"js": _OPFS % _FOLDERS},
            {"note": "Back to the shelf, then Dungeon", "key": "Escape"},
            {"wait": 800}, {"click": at["cards"][0]},
            {"wait": 800}, {"click": at["verb"]},
            {"note": "its licence first", "wait": 3000}, {"shot": "licence"},
            {"click": at["agree"]},
            {"note": "the archive's host cannot be read: the page asks", "wait": 4000},
            {"shot": "your_copy"},
            {"js": "JSON.stringify(window.__moyPick || null)"},
            {"js": "window.__moyPick ? 'block' : 'none'"},
            {"file": "$MOY_WAD", "as": "__wad"},
            {"js": "pkSend(new File([window.__wad], 'doom1.wad')), 'sent'"},
            {"wait": 6000}, {"shot": "dm_ready"},
            {"js": "window.__moyPick ? 'block' : 'none'"},
            {"js": _OPFS % _FOLDERS},
            {"note": "Zap: its mirror's bytes are wrong", "key": "Escape"},
            {"wait": 800}, {"click": at["cards"][2]},
            {"wait": 800}, {"click": at["verb"]},
            {"wait": 5000}, {"shot": "zap_failed"},
            {"js": _OPFS % _FOLDERS},
            {"note": "a store from before Get Carts shipped: it is not in OPFS",
             "js": _FORGET_APP},
        ], base, profile, env={"MOY_WAD": str(tmp_path / "doom1.wad")})
        assert len(js) == 11, "the scenario did not run to its end:\n%s" % out[-4000:]
        assert js[10] == "gone", js[10]
        mode, red, installed, after_rock, pick, card, sent, card_after, after_dm, after_zap = \
            js[0], js[1], js[2], json.loads(js[3]), json.loads(js[4]), js[5], js[6], js[7], \
            json.loads(js[8]), json.loads(js[9])
        assert mode == "site", "a static host must keep its carts in the browser"
        assert red > 1000, "Rock Run's card does not draw its cover (%d red pixels)" % red
        assert installed == "rock.moy", out[-3000:]

        rock = after_rock["carts"]["rock.moy"]
        assert rock and rock["data.bin"] == [len(data_bin), hashlib.sha256(data_bin)
                                             .hexdigest()], rock
        assert set(rock) == {"manifest.json", "main.lua", "LICENSES.txt", "data.bin"}
        assert after_rock["record"]["carts"]["rock.moy"]["id"] == "rock"
        assert after_rock["staging"] == []
        assert not [p for p in releases.asked if p.endswith(".zip")], \
            "the page asked the release, which it cannot read: %r" % releases.asked

        assert pick == {"id": pick["id"], "name": "game.wad", "size": len(wad)}, pick
        assert card == "block" and sent == "sent" and card_after == "none"
        dm = after_dm["carts"]["dm.moy"]
        assert dm and dm["game.wad"] == [len(wad), hashlib.sha256(wad).hexdigest()], dm
        assert sorted(after_dm["record"]["carts"]) == ["dm.moy", "rock.moy"]
        assert releases.asked.count("/debian/pool/game.wad.tar.gz") >= 1

        assert after_zap["carts"]["zap.moy"] is None, "a wrong cart reached the store"
        assert sorted(after_zap["record"]["carts"]) == ["dm.moy", "rock.moy"]
        assert after_zap["staging"] == []

        # A SECOND LOAD in the same browser: the shelf, the record and the bytes
        # come back out of OPFS -- and the installed cart plays.
        out2, js2 = web_e2e.run(tmp_path, "reload", "?handheld=1&dev=1", [
            {"wait": 2500},
            {"js": "pzAsk(), 'asked'"}, {"wait": 600},
            {"js": "(window.__moyCarts || []).join(',')"},
            {"js": "window.__moyPersist ? window.__moyPersist.d : 'none'"},
        ], base, profile)
        shelf = js2[1]
        assert "rock.moy" in shelf and "dm.moy" in shelf and "zap.moy" not in shelf, \
            "the installs did not survive a reload:\n%s" % out2[-3000:]
        assert "moybyte.get_carts.moy" in shelf, \
            "a system cart the store never had did not come from the bundle"
        assert js2[2].startswith("loaded "), js2[2]

        out3, js3 = web_e2e.run(tmp_path, "play", "?handheld=1&dev=1&cart=rock.moy", [
            {"wait": 3000}, {"js": "assCart"}, {"shot": "rock_plays"},
            {"js": "JSON.stringify(window.__moyPersist || null)"},
        ], base, profile)
        assert js3[0] == "Rock Run", "the installed cart did not run:\n%s" % out3[-3000:]
        print("\nstore e2e: %s" % js2[2])
    finally:
        server.terminate()
        server.wait(timeout=10)
        pages.stop()
        releases.stop()


def test_a_hosted_console_takes_an_external_file_from_its_mirror(tmp_path):
    web_e2e.require("store", "carts")
    pages, releases = web_e2e.Host(cors=True), web_e2e.Host(cors=False)
    lic = b"The MIT licence of the test carts.\n"
    pages.files["/carts/LICENCE.txt"] = lic
    level = bytes((i * 13 + 5) & 255 for i in range(80000))
    folder, files = _lua("wm.moy", "Warp Map", 3)
    z = stored_zip(folder, files)
    rel = "releases/wm-v1/wm.moy.zip"
    releases.files["/o/carts/releases/download/wm-v1/wm.moy.zip"] = z
    pages.files["/" + rel] = z
    arc = tar_gz({"pkg/level.wad": level})
    releases.files["/debian/pool/level.wad.tar.gz"] = arc
    pages.files["/files/wm/level.wad"] = level
    ltext = b"You may give this file away, and not sell it.\n"
    pages.files["/carts/level.wad.txt"] = ltext
    pages.files["/index.json"] = json.dumps({"version": 1, "name": "Test shelf",
                                             "home": releases.base + "/o/carts", "carts": [{
        "id": "wm", "name": "Warp Map", "version": 1, "folder": folder, "runtime": "lua",
        "licence": {"spdx": "MIT", "name": "MIT License", "url": "carts/LICENCE.txt",
                    "size": len(lic), "sha256": sha(lic)},
        "assets": [{"name": folder + ".zip",
                    "url": "%s/o/carts/releases/download/wm-v1/wm.moy.zip" % releases.base,
                    "mirror": rel, "size": len(z), "sha256": sha(z),
                    "files": dict((fn, {"size": len(b), "sha256": sha(b)})
                                  for fn, b in files.items())}],
        "external": [{
            "path": "level.wad", "size": len(level), "sha256": sha(level),
            "mirror": "files/wm/level.wad",
            "licence": {"name": "The game data's licence", "url": "carts/level.wad.txt",
                        "size": len(ltext), "sha256": sha(ltext)},
            "archive": {"urls": ["%s/debian/pool/level.wad.tar.gz" % releases.base],
                        "format": "tar.gz", "size": len(arc), "sha256": sha(arc),
                        "member": "pkg/level.wad"}}]}]}).encode()
    site = _console(tmp_path, pages.base + "/index.json")
    server, base = web_e2e.serve(site, web_e2e.free_port())
    at = web_e2e.get_carts_taps()
    try:
        out, js = web_e2e.run(tmp_path, "mirror", "?handheld=1&dev=1&cart=moybyte.get_carts.moy", [
            {"note": "Get Carts opened at boot", "wait": 4000},
            {"click": at["cards"][0]},
            {"wait": 800}, {"click": at["verb"]},
            {"note": "its licence first", "wait": 3000},
            {"click": at["agree"]},
            {"note": "from the mirror, asking nothing", "wait": 6000}, {"shot": "wm_ready"},
            {"js": "JSON.stringify(window.__moyPick || null)"},
            {"js": "window.__moyPick ? 'block' : 'none'"},
            {"js": _OPFS % '["wm.moy"]'},
        ], base, tmp_path / "chrome")
        assert len(js) == 3, "the scenario did not run to its end:\n%s" % out[-4000:]
        assert json.loads(js[0]) is None and js[1] == "none", js[:2]
        got = json.loads(js[2])
        wm = got["carts"]["wm.moy"]
        assert wm and wm["level.wad"] == [len(level), hashlib.sha256(level).hexdigest()], \
            "%r\n%s" % (wm, out[-3000:])
        assert sorted(got["record"]["carts"]) == ["wm.moy"] and got["staging"] == []
        assert "/files/wm/level.wad" in pages.asked
        assert releases.asked == [], "the page asked a host it cannot read: %r" % releases.asked
    finally:
        server.terminate()
        server.wait(timeout=10)
        pages.stop()
        releases.stop()


@pytest.mark.parametrize("board,home", [("glass", "board"), ("headless", "headless")])
def test_a_board_served_page_gets_no_carts_of_its_own(tmp_path, board, home):
    """BOARD mode: the carts are the serving console's, so the console in the
    page has no network for Get Carts, no keeper, and says where carts come
    from -- by whether that console has a screen -- and fetches nothing, not
    even an index its host names."""
    web_e2e.require("store", "carts")
    pages = web_e2e.Host(cors=True)
    pages.files["/index.json"] = b'{"version": 1, "carts": []}'
    store = tmp_path / "store"
    store.mkdir()
    shutil.copytree(ROOT / "system_carts" / "moybyte.get_carts.moy", store / "moybyte.get_carts.moy")
    site = _console(tmp_path, pages.base + "/index.json")
    port = web_e2e.free_port()
    p = subprocess.Popen([sys.executable, "serve.py", str(port), str(site),
                          "--carts", str(store), "--update", board],
                         cwd=RUNNER, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/index.html", timeout=1).read(64)
                break
            except OSError:
                time.sleep(0.1)
        out, js = web_e2e.run(tmp_path, "board", "?handheld=1&dev=1&cart=moybyte.get_carts.moy", [
            {"wait": 2500},
            {"js": "window.__moyPersist ? window.__moyPersist.mode : 'none'"},
            {"js": "JSON.stringify((window.__moyUpdate || {}).services || null)"},
            {"shot": "on_the_console"},
        ], base, tmp_path / "chrome")
        assert js[0] == "board", out[-2000:]
        svc = json.loads(js[1])
        assert svc and svc["cart_home"] == home, svc
        assert svc["cart_net"] is False and svc["cart_keep"] is False, svc
        assert pages.asked == [], "a board-served page fetched a carts index"
    finally:
        p.terminate()
        p.wait(timeout=10)
        pages.stop()


def test_a_board_with_a_big_store_serves_a_page_that_boots(tmp_path):
    """A board serves one connection at a time and cuts off a client that
    stops reading for its send budget, so the page has to read carts.json as
    it arrives: the other boot answers queue behind it. The twin here holds
    a store bigger than the browser buffers, over a board's link
    (`serve.py --one-link`): the page boots, and Get Carts says the carts
    are the board's. A compiled cart's main.wasm never crosses the wire, so
    the page's scan leaves it off the shelf (moy_carts.load, a cart with no
    main): asked for by name, nothing opens and the console carries on."""
    import random
    web_e2e.require("store", "carts")
    store = tmp_path / "store"
    store.mkdir()
    shutil.copytree(ROOT / "system_carts" / "moybyte.get_carts.moy", store / "moybyte.get_carts.moy")
    sys.path.insert(0, str(ROOT))
    from tools import wasm_cart
    wasm_cart.build(str(ROOT / "tests" / "fixtures" / "wasm" / "tier.moy"),
                    str(store / "tier.moy"))
    rnd = random.Random(7)
    for i in range(24):
        d = store / ("big%02d.moy" % i)
        d.mkdir()
        (d / "manifest.json").write_text(json.dumps(
            {"format": "moy-1", "title": "Big %d" % i, "runtime": "lua",
             "main": "main.lua"}))
        lines = ["-- %s" % "".join(rnd.choice("abcdefghij ") for _ in range(70))
                 for _ in range(14000)]
        (d / "main.lua").write_text("function _draw() cls(1) end\n" + "\n".join(lines))
    site = _console(tmp_path, "http://127.0.0.1:9/index.json")
    port = web_e2e.free_port()
    from cart_store_fixtures import Repo
    shelf = Repo("http://127.0.0.1:%d/shelf" % port, "A shelf on the page's origin")
    shelf.add("kite", name="Kite", runtime="lua", modules=())
    for url, data in shelf.routes().items():
        path = site / url.split("/", 3)[3]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (tmp_path / "system").mkdir(exist_ok=True)
    (tmp_path / "system" / "sources").write_text(shelf.url("index.json") + "\n")
    p = subprocess.Popen([sys.executable, "serve.py", str(port), str(site),
                          "--carts", str(store), "--update", "glass", "--one-link"],
                         cwd=RUNNER, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    state = ("__moyState().then(s => JSON.stringify({cart: s.cart, err: s.cart_error, "
             "notice: s.notice, stack: s.stack, frames: s.frames}))")
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/index.html", timeout=1).read(64)
                break
            except OSError:
                time.sleep(0.1)
        out, js = web_e2e.run(tmp_path, "big_board", "?handheld=1&dev=1&cart=moybyte.get_carts.moy", [
            {"wait": 2500},
            {"js": "window.__moyPersist ? window.__moyPersist.mode : 'none'"},
            {"js": "JSON.stringify((window.__moyUpdate || {}).services || null)"},
            {"js": state},
            {"shot": "on_the_console"},
        ], base, tmp_path / "chrome", boot_ms=30000)
        assert len(js) == 3, "the page did not boot:\n%s" % out[-3000:]
        assert js[0] == "board", out[-2000:]
        assert json.loads(js[1])["cart_home"] == "board", js[1]
        st = json.loads(js[2])
        assert st["cart"] == "Get Carts" and st["err"] is None, st
        out, js = web_e2e.run(tmp_path, "big_compiled", "?handheld=1&dev=1&cart=tier.moy", [
            {"wait": 2500}, {"js": state}, {"wait": 1000}, {"js": state},
            {"shot": "launcher"},
        ], base, tmp_path / "chrome2", boot_ms=30000)
        assert len(js) == 2, out[-3000:]
        st, later = json.loads(js[0]), json.loads(js[1])
        assert st["cart"] is None and st["err"] is None and st["notice"] is None, st
        assert st["stack"] == ["launcher"], st
        assert later["stack"] == ["launcher"] and later["err"] is None, later
    finally:
        p.terminate()
        p.wait(timeout=10)


def test_a_zero_s_page_asks_the_board_for_an_official_cart(tmp_path):
    """A Zero's page: Get Carts lists the carts of the BOARD's shelves --
    one the page fetches and lists itself (a shelf on this origin, which the
    twin's network cannot reach), and the board's release, which the board
    lists (serve.py's twin runs the board's own /official backend over its
    store) -- and Get asks the board, which fetches from its release and
    writes its own store; the page then has the board's copy and plays it."""
    web_e2e.require("store", "carts", "official")
    sys.path.insert(0, str(ROOT / "tests"))
    sys.path.insert(0, str(ROOT / "tools"))
    import web_pack
    from test_official_carts import _page
    from test_ota_signing import TEST_KEYS
    from test_pkg import _sign
    seeds = tmp_path / "seeds"
    for cid in ("moybyte.calc", "moybyte.tap_only_red"):
        shutil.copytree(ROOT / "system_carts" / (cid + ".moy"), seeds / (cid + ".moy"))
    release = tmp_path / "release"
    release.mkdir()
    page = _page(tmp_path)
    web_pack.publish_addon(page, str(release), "tdeck", 9, seeds=str(seeds))
    idx = release / "carts-tdeck.json"
    idx.write_bytes(_sign(idx.read_bytes()))
    (release / "twin.json").write_text(json.dumps(
        {"index": "carts-tdeck.json", "want": page[1], "keys": TEST_KEYS}))
    store = tmp_path / "store"
    store.mkdir()
    for cid in ("moybyte.get_carts", "moybyte.calc"):
        shutil.copytree(ROOT / "system_carts" / (cid + ".moy"), store / (cid + ".moy"))
    site = _console(tmp_path, "http://127.0.0.1:9/index.json")
    port = web_e2e.free_port()
    from cart_store_fixtures import Repo
    shelf = Repo("http://127.0.0.1:%d/shelf" % port, "A shelf on the page's origin")
    shelf.add("kite", name="Kite", runtime="lua", modules=())
    for url, data in shelf.routes().items():
        path = site / url.split("/", 3)[3]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (tmp_path / "system").mkdir(exist_ok=True)
    (tmp_path / "system" / "sources").write_text(shelf.url("index.json") + "\n")
    p = subprocess.Popen([sys.executable, "serve.py", str(port), str(site),
                          "--carts", str(store), "--update", "headless",
                          "--official", str(release)],
                         cwd=RUNNER, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    state = "__moyState().then(s => JSON.stringify({cart: s.cart, err: s.cart_error}))"
    at = web_e2e.get_carts_taps(3)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/index.html", timeout=1).read(64)
                break
            except OSError:
                time.sleep(0.1)
        out, js = web_e2e.run(tmp_path, "zero", "?handheld=1&dev=1&cart=moybyte.get_carts.moy", [
            {"note": "Get Carts asks the board for its list", "wait": 4000},
            {"js": "JSON.stringify((window.__moyUpdate || {}).services || null)"},
            {"shot": "list"},
            {"note": "Tap Only Red, after the page's own shelf's Kite: on the release, "
                     "not on the board", "click": at["cards"][2]},
            {"wait": 800}, {"shot": "tap_only_red"},
            {"click": at["verb"]},
            {"note": "the board installs it, then the page pulls its copy", "wait": 8000},
            {"shot": "ready"},
            {"note": "Play has the focus", "key": "Enter"},
            {"wait": 2000},
            {"js": state},
        ], base, tmp_path / "chrome")
        assert len(js) == 2, "the scenario did not run to its end:\n%s" % out[-4000:]
        svc = json.loads(js[0])
        assert svc["cart_home"] == "headless" and svc["cart_board"] is True, svc
        assert (store / "moybyte.tap_only_red.moy" / "manifest.json").exists(), out[-3000:]
        st = json.loads(js[1])
        assert st["cart"] == "Tap Only Red" and st["err"] is None, (st, out[-3000:])
    finally:
        p.terminate()
        p.wait(timeout=10)


# -- the site's player and its channel's release ----------------------------------

_TAG = "firmware-beta"


def _site_release(tmp_path, pages, tamper=False):
    """A release of Bullet Storm, an official cart no store is seeded with,
    signed with the test key and mirrored on PAGES as os.moybyte.com mirrors
    one (tools/pack_store.py): the mirror's index URL, the page's `own`.
    `tamper` changes the mirrored index after it was signed."""
    sys.path.insert(0, str(ROOT / "tools"))
    import pack_store
    import web_pack
    from test_official_carts import SEEDS, _page
    from test_pkg import _sign
    seeds = tmp_path / "seeds"
    shutil.copytree(SEEDS / "moybyte.bullet_storm.moy", seeds / "moybyte.bullet_storm.moy")
    rel = tmp_path / "release"
    rel.mkdir()
    web_pack.publish_addon(_page(tmp_path), str(rel), "p4", 9, seeds=str(seeds))
    idx = rel / "carts-p4.json"
    idx.write_bytes(_sign(idx.read_bytes()))
    (rel / pack_store.TAG_FILE).write_text(_TAG + "\n")
    out = tmp_path / "out"
    pack_store.build(str(out), dev=[str(rel)])
    mirror = out / "console" / "releases" / _TAG
    for name in os.listdir(mirror):
        data = (mirror / name).read_bytes()
        if tamper and name == "carts-p4.json":
            data = data.replace(b'"name": "Bullet Storm"', b'"name": "Bullet Storn"')
        pages.files["/console/releases/%s/%s" % (_TAG, name)] = data
    pages.files["/empty.json"] = json.dumps(
        {"version": 1, "name": "Empty shelf", "carts": []}).encode()
    return pages.base + "/console/releases/%s/carts-p4.json" % _TAG


def _site_console(tmp_path, own, pages):
    """dist/ as the site serves its player: an indexes.json naming the
    release (site/build.py's), and the test key in place of the release keys
    the bundle bakes in (modules.json shadows a frozen module, as a
    --stage-only dist's does)."""
    from test_ota_signing import TEST_KEYS
    site = _console(tmp_path, pages.base + "/empty.json")
    (site / "indexes.json").write_text(json.dumps(
        {"indexes": [pages.base + "/empty.json"], "own": own}))
    mods = {}
    if (DIST / "modules.json").exists():
        mods = json.loads((DIST / "modules.json").read_text())
        (site / "modules.json").unlink()
    mods["release_keys.py"] = "KEYS = %r\n" % (TEST_KEYS,)
    (site / "modules.json").write_text(json.dumps(mods))
    return site


_HAS_STORM = _OPFS % '["moybyte.bullet_storm.moy"]'


def test_the_site_s_player_gets_an_official_cart_from_its_release(tmp_path):
    """Bullet Storm is on no store's seed: the player lists it from its
    release's mirrored index, whose signature verifies under the keys the
    page holds, and installs it from the mirror into OPFS."""
    web_e2e.require("store", "carts")
    pages = web_e2e.Host(cors=True)
    site = _site_console(tmp_path, _site_release(tmp_path, pages), pages)
    server, base = web_e2e.serve(site, web_e2e.free_port())
    at = web_e2e.get_carts_taps()
    try:
        out, js = web_e2e.run(tmp_path, "release", "?handheld=1&dev=1&cart=moybyte.get_carts.moy", [
            {"note": "Get Carts lists the release's official carts", "wait": 4000},
            {"shot": "list"},
            {"note": "Bullet Storm, the shelf's one cart", "click": at["cards"][0]},
            {"wait": 800}, {"shot": "storm"},
            {"click": at["verb"]},
            {"wait": 5000}, {"shot": "storm_ready"},
            {"js": _HAS_STORM},
        ], base, tmp_path / "chrome")
        assert len(js) == 1, "the scenario did not run to its end:\n%s" % out[-4000:]
        got = json.loads(js[0])
        storm = got["carts"]["moybyte.bullet_storm.moy"]
        assert storm and "main.lua" in storm, out[-3000:]
        assert got["record"]["carts"]["moybyte.bullet_storm.moy"]["id"] == "moybyte.bullet_storm"
        assert got["staging"] == []
        assert "/console/releases/%s/carts-p4.json" % _TAG in pages.asked
        assert [p for p in pages.asked if p.startswith("/console/releases/%s/moybyte.bullet_storm-"
                                                       % _TAG) and p.endswith(".zip")], pages.asked
    finally:
        server.terminate()
        server.wait(timeout=10)
        pages.stop()


def test_the_site_s_player_lists_nothing_from_a_tampered_release(tmp_path):
    """The same release, its mirrored index changed after it was signed:
    the page refuses it and lists none of its carts, though it came from
    the very address the page names."""
    web_e2e.require("store", "carts")
    pages = web_e2e.Host(cors=True)
    site = _site_console(tmp_path, _site_release(tmp_path, pages, tamper=True), pages)
    server, base = web_e2e.serve(site, web_e2e.free_port())
    at = web_e2e.get_carts_taps()
    try:
        out, js = web_e2e.run(tmp_path, "tampered", "?handheld=1&dev=1&cart=moybyte.get_carts.moy", [
            {"note": "Get Carts reads the release and refuses it", "wait": 4000},
            {"shot": "list"},
            {"click": at["cards"][0]},
            {"wait": 800}, {"click": at["verb"]},
            {"wait": 3000},
            {"js": _HAS_STORM},
        ], base, tmp_path / "chrome")
        assert len(js) == 1, "the scenario did not run to its end:\n%s" % out[-4000:]
        assert "/console/releases/%s/carts-p4.json" % _TAG in pages.asked
        got = json.loads(js[0])
        assert got["carts"]["moybyte.bullet_storm.moy"] is None
        assert not [p for p in pages.asked if p.endswith(".zip")], pages.asked
    finally:
        server.terminate()
        server.wait(timeout=10)
        pages.stop()
