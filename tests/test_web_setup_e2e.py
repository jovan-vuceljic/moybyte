"""First setup and adding a console by hand, in My consoles, in a real
Chrome (docs/web_console_online_2026-11.md §2's flow 1, §7, §11 phase 3).

The site is My consoles as tools/os_site.py builds it, on `localhost`. The
board is the real C webhost with its sign-in and NO password (native/
moy_tty's host harness, which names this tree's pack and tells the claim a
board's Improv answer carries) behind serve.py's `--board --loader`. Web
Serial is a stand-in in the page, a board answering Improv with that
board's address, id and claim; the Improv C and its Python are driven by
tests/test_improv.py and tests/test_zero_improv.py, the client in node by
site/os/improv_test.mjs.

What it holds: an address typed by hand is normalised, a bad one refused,
one the list has updated rather than added twice, and a console nobody
reached says so with its address to open by hand; the setup by cable names
the console, joins it, saves it under the board's id over the entry its
address already had, asks for the console's password, and opening it hands
the password over the link: the board takes it by its claim, the console
pairs and signs in, and the list shows it reached and the pack it named.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_setup_e2e.py
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import web_e2e
from web_e2e import DIST, ROOT, RUNNER
from test_web_link_e2e import _add, _js, _tagged, _up

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, str(ROOT / "tools"))

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")

PASSWORD = "kitchen-pass-1"
CART = "moybyte.sakura.moy"

# Web Serial with one port, a board that answers Improv (improv-wifi.com/
# serial) as a Zero does, its join answering ADDR with ID and CLAIM.
SERIAL = r"""
(() => {
    const ADDR = %s, ID = %s, CLAIM = %s;
    const H = [73, 77, 80, 82, 79, 86], enc = new TextEncoder(), dec = new TextDecoder();
    const frame = (t, d) => { const b = [...H, 1, t, d.length, ...d];
        b.push(b.reduce((s, x) => s + x, 0) & 255, 10); return new Uint8Array(b); };
    const strs = (cmd, ...ss) => { const body = [];
        for (const s of ss) { const b = enc.encode(s); body.push(b.length, ...b); }
        return [cmd, body.length, ...body]; };
    let name = "moybyte-zero", q = [], wake = null, closed = false;
    window.__improv = [];
    function answer(cmd, d) {
        window.__improv.push(cmd);
        if (cmd === 2) return [[2, [0]], [1, [2]]];
        if (cmd === 3) return [[2, [0]], [4, strs(3, "Moybyte", "v0.16", "ESP32-C3", name)]];
        if (cmd === 4) return [[2, [0]], [4, strs(4, "home", "-40", "YES")], [4, [4, 0]]];
        if (cmd === 6) { if (d.length) name = dec.decode(new Uint8Array(d.slice(1)));
                         return [[2, [0]], [4, strs(6, name)]]; }
        if (cmd === 1) { const t = "#id=" + ID + "&claim=" + CLAIM;
                         return [[2, [0]], [1, [3]], [1, [4]], [4, strs(1, "http://" + ADDR + "/" + t)]]; }
        return [[2, [2]]];
    }
    const port = { readable: null, writable: null,
        async open() {
            closed = false;
            port.readable = { getReader: () => ({
                async read() { while (!q.length && !closed) await new Promise((r) => { wake = r; });
                               return closed ? { done: true } : { value: q.shift(), done: false }; },
                async cancel() { closed = true; if (wake) wake(); }, releaseLock() { } }) };
            port.writable = { getWriter: () => ({
                async write(b) { const n = b[8], d = Array.from(b.slice(9, 9 + n)), out = [];
                    for (const [t, x] of answer(d[0], d.slice(2))) out.push(...frame(t, x));
                    q.push(new Uint8Array(out)); if (wake) { wake(); wake = null; } },
                releaseLock() { } }) };
        },
        async setSignals() { }, async close() { closed = true; port.readable = null; } };
    Object.defineProperty(navigator, "serial", { value: {
        requestPort: async () => port, getPorts: async () => [port] } });
})();
"""


def _field(sel, value):
    return {"js": "(() => { const e = document.querySelector(%s); e.value = %s; "
                  "e.dispatchEvent(new Event('change')); return 1; })()"
                  % (json.dumps(sel), json.dumps(value))}


def test_my_consoles_sets_a_board_up_by_cable_and_adds_one_by_hand(tmp_path):
    web_e2e.require("sync", "signin")
    import gen_web_blob
    import os_site
    import test_moy_tty

    data, body = gen_web_blob.pack(gen_web_blob.collect(str(DIST))[0])
    pack = tmp_path / "moybyte_web.pack"
    pack.write_bytes(data)
    os_site.build(str(tmp_path / "site"), packs=[str(pack)])
    web_e2e.warm_host_library()

    procs = []
    sport, bport = web_e2e.free_port(), web_e2e.free_port()
    site, board = "http://localhost:%d" % sport, "http://127.0.0.1:%d" % bport
    slog = tmp_path / "site.log"
    sp = subprocess.Popen([sys.executable, str(ROOT / "tools" / "os_site.py"), "serve",
                           str(tmp_path / "site"), "--port", str(sport)],
                          stdout=open(slog, "w"), stderr=subprocess.STDOUT)
    procs.append(sp)
    exe = test_moy_tty._build(Path(tempfile.mkdtemp(prefix="moys", dir=str(tmp_path))))
    host = test_moy_tty.Host(exe, tmp_path, page=(body.hex(), hashlib.sha256(data).hexdigest()))
    try:
        shutil.copytree(ROOT / "system_carts" / CART, host.tree / "sd" / "moybyte" / "carts" / CART)
        host.say("claim")
        _, claim, board_id = host.wait_line("CLAIM ").split()
        assert len(claim) == 32 and len(board_id) == 32
        blog = tmp_path / "board.log"
        bp = subprocess.Popen([sys.executable, "serve.py", str(bport), "dist",
                               "--board", "127.0.0.1:%d" % host.port,
                               "--loader", "--mirror", site + "/console/"],
                              cwd=str(RUNNER), stdout=open(blog, "w"), stderr=subprocess.STDOUT)
        procs.append(bp)
        _up(site + "/console/packs.json", sp, slog)
        _up(board + "/sync", bp, blog)

        addr = "127.0.0.1:%d" % bport
        kept = "JSON.parse(localStorage.getItem('moy.consoles') || '[]')"
        steps = [
            {"waitFor": "typeof render == 'function'", "timeout": 15000},
            {"init": SERIAL % (json.dumps(addr), json.dumps(board_id), json.dumps(claim))},
            {"waitFor": "typeof render == 'function' && !document.getElementById('cable').hidden",
             "timeout": 15000},
            {"note": "by hand: an address with no name is its own name"},
            _add("", " HTTP://%s " % addr),
            _js("HAND", kept),
            _js("HANDREACH", "document.querySelector('#list li .reach').textContent"),
            _add("den", addr + "/"),
            _js("AGAIN", kept),
            _add("x", "ftp://" + addr),
            _js("BAD", "document.getElementById('said').textContent"),
            _add("nobody", "127.0.0.1:9"),
            {"press": "#list li:nth-child(2) button.name"},
            {"waitFor": "document.querySelector('#list li:nth-child(2) .state').textContent"
                        ".startsWith('not reached')", "timeout": 20000},
            _js("NOBODY", "[document.querySelector('#list li:nth-child(2) .state').textContent, "
                          "document.querySelector('#list li:nth-child(2) .state a').href]"),
            {"js": "window.confirm = () => true, document.querySelectorAll('#list li')[1]"
                   ".querySelector('button.quiet + button.quiet').click(), 1"},
            {"note": "by cable: Improv names it, joins it, and it is saved under the board's id"},
            {"press": "#cable"},
            {"waitFor": "document.querySelector('#setup form input[name=name]')", "timeout": 15000},
            _field("#setup form input[name=name]", "Kitchen"),
            _field("#setup form input[name=wifi]", "its password"),
            {"js": "document.querySelector('#setup form').requestSubmit(), 1"},
            {"waitFor": "document.querySelectorAll('#setup form input[type=password]').length == 2",
             "timeout": 15000},
            {"js": "(() => { const p = document.querySelectorAll('#setup form input[type=password]'); "
                   "p[0].value = p[1].value = %s; document.querySelector('#setup form')"
                   ".requestSubmit(); return 1; })()" % json.dumps(PASSWORD)},
            {"waitFor": "document.querySelector('#setup button')", "timeout": 15000},
            _js("SAVED", kept),
            _js("ASKED", "window.__improv"),
            _js("PWSTORED", "JSON.stringify(localStorage).includes(%s)" % json.dumps(PASSWORD)),
            {"note": "opened, the console takes its first password over the link and signs in"},
            {"press": "#setup button"},
            {"tab": board},
            {"waitFor": "window.__moyPersist && window.__moyPersist.mode == 'board'", "timeout": 120000},
            {"tab": site},
            {"waitFor": "document.querySelector('#list li .state').textContent == 'signed in'",
             "timeout": 15000},
            _js("REACHED", "document.querySelector('#list li .reach').textContent"),
            _js("AFTER", kept),
        ]
        out, js = web_e2e.run(tmp_path, "setup", "console/", steps, site, tmp_path / "chrome",
                              boot_ms=1000)
        tail = out[-4000:] + "\n-- board --\n" + host.log()[-1500:]
        hand = _tagged(js, "HAND")
        assert [(c["name"], c["address"]) for c in hand] == [(addr, addr)], tail
        assert _tagged(js, "HANDREACH") == "not reached yet", tail
        again = _tagged(js, "AGAIN")
        assert [(c["id"], c["name"]) for c in again] == [(hand[0]["id"], "den")], tail
        assert "not an address" in _tagged(js, "BAD"), tail
        nobody = _tagged(js, "NOBODY")
        assert nobody[0].startswith("not reached yet") and nobody[1] == "http://127.0.0.1:9/", tail
        saved = _tagged(js, "SAVED")
        assert [(c["id"], c["name"], c["address"]) for c in saved] == [(board_id, "Kitchen", addr)], tail
        assert _tagged(js, "ASKED")[:2] == [2, 3] and 6 in _tagged(js, "ASKED") \
            and _tagged(js, "ASKED")[-1] == 1, tail
        assert _tagged(js, "PWSTORED") is False, "the password reached the site's storage"
        assert (host.tree / "sd" / "moybyte" / "system" / "password").read_text().startswith("$moy2$"), tail
        reached = _tagged(js, "REACHED")
        assert reached.startswith("reached ") and body.hex()[:12] in reached, tail
        after = _tagged(js, "AFTER")[0]
        assert after["page"] == body.hex() and after["pack"] == hashlib.sha256(data).hexdigest(), tail
    finally:
        for p in procs:
            p.terminate()
        host.end()
