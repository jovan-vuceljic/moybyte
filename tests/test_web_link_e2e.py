"""The link between the windows (docs/web_console_online_2026-11.md §5, §11
phase 2), across two origins in a real Chrome.

The site is My consoles as tools/os_site.py builds it, at /console/ on
`localhost` as Pages serves it (a secure context, so its service worker
runs). The board is
the real C webhost with its sign-in (native/moy_tty's host harness, which
names this tree's pack) behind serve.py's `--board --loader` on
`http://127.0.0.1`: its root is the loader, whose one mirror is the site.

The first run, with the site up, installs its service worker, which keeps
the site and the newest pack. The same site on another origin opens the
board: the loader hears nothing from it, boots from the mirror, and leaves
what that window sends unanswered. Then the site goes down, and the second
run opens My consoles from the service worker and taps the console: the
hand-off boots it with nothing to fetch, it signs in by its password and
syncs a cart onto the board, an unknown kind is answered as unknown, and
bytes the site holds that are not the pack are refused (and the site drops
them) while the console boots from its own cache.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_link_e2e.py
"""

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
from pathlib import Path

import pytest

import web_e2e
from web_e2e import DIST, ROOT, RUNNER

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, str(ROOT / "tools"))

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")

PASSWORD = "correct horse"
CART = "moybyte.sakura.moy"


def _up(url, proc, log):
    for _ in range(100):
        try:
            urllib.request.urlopen(url, timeout=1).read(64)
            return
        except urllib.error.HTTPError:
            return
        except OSError:
            if proc.poll() is not None:
                pytest.fail("%s died on startup:\n%s" % (url, log.read_text()))
            time.sleep(0.1)
    pytest.fail("%s never answered" % url)


def _down(url):
    try:
        urllib.request.urlopen(url, timeout=1)
    except urllib.error.HTTPError:
        return False
    except OSError:
        return True
    return False


def _tagged(js, tag):
    for j in js:
        if isinstance(j, str) and j.startswith(tag + " "):
            return json.loads(j[len(tag) + 1:])
    return None


def _js(tag, expr):
    return {"js": "Promise.resolve(%s).then(v => '%s ' + JSON.stringify(v))" % (expr, tag)}


def _add(name, address):
    return {"js": "document.getElementById('name').value = %s, "
                  "document.getElementById('address').value = %s, "
                  "document.getElementById('add').requestSubmit(), 1"
                  % (json.dumps(name), json.dumps(address))}


# The window My consoles opened for its first console, from that page.
_WIN = "window.open('', 'moy-' + JSON.parse(localStorage.getItem('moy.consoles'))[0].id)"
_STATE = "document.querySelector('#list li .state').textContent"


def _post_unknown(board):
    """From the page: listen for what comes back, and send the console's
    window a kind no version of the link has."""
    return {"js": "window.__got = [], addEventListener('message', (e) => "
                  "{ if (e.data && e.data.re === 9) __got.push([e.origin, e.data]); }), "
                  "%s.postMessage({moylink: 1, id: 9, kind: 'backup'}, %s), 1"
                  % (_WIN, json.dumps(board))}


def test_my_consoles_hands_a_board_its_console_over_the_link(tmp_path):
    web_e2e.require("sync", "signin")
    import gen_web_blob
    import os_site
    import test_moy_tty
    from runtime.system import ssh_service

    data, body = gen_web_blob.pack(gen_web_blob.collect(str(DIST))[0])
    pack = tmp_path / "moybyte_web.pack"
    pack.write_bytes(data)
    os_site.build(str(tmp_path / "site"), packs=[str(pack)])
    web_e2e.warm_host_library()

    procs = []
    sport, bport = web_e2e.free_port(), web_e2e.free_port()
    site, other = "http://localhost:%d" % sport, "http://127.0.0.1:%d" % sport
    board = "http://127.0.0.1:%d" % bport
    slog = tmp_path / "site.log"
    sp = subprocess.Popen([sys.executable, str(ROOT / "tools" / "os_site.py"), "serve",
                           str(tmp_path / "site"), "--port", str(sport)],
                          stdout=open(slog, "w"), stderr=subprocess.STDOUT)
    procs.append(sp)
    exe = test_moy_tty._build(Path(tempfile.mkdtemp(prefix="moyl", dir=str(tmp_path))))
    host = test_moy_tty.Host(exe, tmp_path, page=(body.hex(), hashlib.sha256(data).hexdigest()))
    try:
        shutil.copytree(ROOT / "system_carts" / CART, host.tree / "sd" / "moybyte" / "carts" / CART)
        (host.tree / "sd" / "moybyte" / "system" / "password").write_text(
            ssh_service.hashed(PASSWORD, "e2e0salt"))
        blog = tmp_path / "board.log"
        bp = subprocess.Popen([sys.executable, "serve.py", str(bport), "dist",
                               "--board", "127.0.0.1:%d" % host.port,
                               "--loader", "--mirror", site + "/console/"],
                              cwd=str(RUNNER), stdout=open(blog, "w"), stderr=subprocess.STDOUT)
        procs.append(bp)
        _up(other + "/console/packs.json", sp, slog)
        _up(board + "/sync", bp, blog)
        doc = json.loads(urllib.request.urlopen(board + "/sync").read())
        assert doc["page"] == body.hex() and doc["local"] == 0, doc

        profile = tmp_path / "chrome"
        booted = "window.moyBoot && window.moyBoot.from"
        steps = [
            {"note": "the site's service worker keeps the site and the newest pack"},
            {"waitFor": "navigator.serviceWorker.ready.then(() => caches.open('moy-packs'))"
                        ".then((c) => c.keys()).then((k) => k.length)", "timeout": 60000},
            _js("KEPT", "caches.open('moy-packs').then((c) => c.keys()).then((k) => k.length)"),
            {"note": "the same site on another origin opens the board"},
            {"open": other + "/console/"},
            {"waitFor": "typeof render == 'function'", "timeout": 15000},
            _add("elsewhere", "127.0.0.1:%d" % bport),
            {"press": "#list li button.open"},
            {"tab": board},
            {"waitFor": booted, "timeout": 60000},
            _js("OTHERBOOT", "window.moyBoot.from"),
            {"tab": other},
            _post_unknown(board),
            {"wait": 2000},
            _js("OTHERGOT", "window.__got"),
            _js("OTHERSTATE", _STATE),
        ]
        out, js = web_e2e.run(tmp_path, "online", "console/", steps, site, profile, boot_ms=1000)
        assert _tagged(js, "KEPT") == 1, out[-3000:]
        assert _tagged(js, "OTHERBOOT") == site + "/console/", out[-3000:]
        assert _tagged(js, "OTHERGOT") == [], out[-3000:]
        assert _tagged(js, "OTHERSTATE") == "opening...", out[-3000:]

        sp.terminate()
        sp.wait(timeout=10)
        assert _down(site + "/console/"), "the site is still up"

        password = ("document.getElementById('pinf').value = %s, "
                    "document.getElementById('pinb').click(), 1" % json.dumps(PASSWORD))
        export = ("window.__zip = null, pzDownload = function (n, b) { window.__zip = b; }, "
                  "asks([{do: 'save', cart: %s}]), 1" % json.dumps(CART))
        steps = [
            {"note": "the site is down: My consoles opens from its service worker"},
            {"waitFor": "typeof render == 'function' && navigator.serviceWorker.controller",
             "timeout": 15000},
            _add("kitchen", "127.0.0.1:%d" % bport),
            {"press": "#list li button.open"},
            {"tab": board},
            {"waitFor": booted, "timeout": 60000},
            _js("BOOT1", "window.moyBoot.from"),
            {"waitFor": "document.getElementById('pin').style.display == 'flex'", "timeout": 60000},
            {"tab": site},
            {"waitFor": _STATE + ".startsWith('asks')", "timeout": 15000},
            _js("STATE1", _STATE),
            {"note": "signed in by its password, the page loads again through the link"},
            {"tab": board},
            {"js": password},
            {"waitFor": "window.__moyPersist && window.__moyPersist.mode == 'board'",
             "timeout": 90000},
            _js("BOOT2", "window.moyBoot.from"),
            {"tab": site},
            {"waitFor": _STATE + " == 'signed in'", "timeout": 15000},
            _js("STATE2", _STATE),
            {"note": "a cart made in that window lands on the board"},
            {"tab": board},
            {"js": "window.__moyStart(), 1"},
            {"waitFor": "document.getElementById('s').textContent == 'live'", "timeout": 30000},
            {"wait": 1500},
            {"js": export},
            {"waitFor": "window.__zip", "timeout": 15000},
            {"js": "WORKER.postMessage({t: 'import', name: 'copy.moy.zip', buf: window.__zip}), 1"},
            {"waitFor": "window.__moyImported", "timeout": 15000},
            _js("IMPORTED", "window.__moyImported"),
            {"wait": 6000},
            {"note": "an unknown kind is answered as unknown"},
            {"tab": site},
            _post_unknown(board),
            {"waitFor": "window.__got.length", "timeout": 5000},
            _js("UNKNOWN", "window.__got"),
            {"note": "bytes the site keeps that are not the pack are refused"},
            {"js": "window.__packs = [], addEventListener('message', (e) => { if (e.data "
                   "&& e.data.kind == 'pack' && 're' in e.data) __packs.push(e.data.ok); }), 1"},
            {"js": "caches.open('moy-packs').then((c) => c.keys().then((k) => "
                   "c.put(k[0], new Response(new Uint8Array(8192))))).then(() => 1)"},
            {"tab": board},
            {"js": "window.moyBoot = null, location.reload(), 1"},
            {"waitFor": booted, "timeout": 60000},
            _js("BOOT3", "window.moyBoot.from"),
            {"tab": site},
            {"waitFor": "window.__packs.length", "timeout": 15000},
            _js("REFUSED", "window.__packs"),
            _js("DROPPED", "caches.open('moy-packs').then((c) => c.keys()).then((k) => k.length)"),
        ]
        out, js = web_e2e.run(tmp_path, "offline", "console/", steps, site, profile, boot_ms=1000)
        tail = out[-4000:] + "\n-- board --\n" + host.log()[-1500:]
        assert _tagged(js, "BOOT1") == "link", tail
        assert _tagged(js, "STATE1").startswith("asks for its password"), tail
        assert _tagged(js, "BOOT2") == "link", tail
        assert _tagged(js, "STATE2") == "signed in", tail
        imported = _tagged(js, "IMPORTED")
        assert imported and imported.startswith("imported "), tail
        folder = imported.split()[1]
        assert (host.tree / "sd" / "moybyte" / "carts" / folder / "manifest.json").is_file(), (
            folder, sorted(os.listdir(host.tree / "sd" / "moybyte" / "carts")), tail)
        assert _tagged(js, "UNKNOWN") == [[board, {"moylink": 1, "re": 9, "kind": "unknown"}]], tail
        assert _tagged(js, "BOOT3") == "cache", tail
        assert _tagged(js, "REFUSED") == [False], tail
        assert _tagged(js, "DROPPED") == 0, tail
    finally:
        for p in procs:
            p.terminate()
        host.end()
