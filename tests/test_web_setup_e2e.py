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
address already had, asks for the console's password, names its terminal
(ssh, with that password), and opening it hands the password over the link:
the board takes it by its claim, the console pairs and signs in, and the
list shows it reached and the pack it named.
A join the board refuses opens the setup's "Board log" on the board's own
lines, which never show the Wi-Fi password.

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

import seal_client
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
# serial) as a Zero does, its join answering ADDR with ID and CLAIM, or
# refusing the network when FAIL. SAYS[cmd] is what it prints on the cable
# before its answer to that command, as a board's log does. With MANAGE
# ({claims}) the board is already on a network at ADDR, a join moves it to
# the network's name in MANAGE.at, and Moybyte's 0xF0 answers each claim of
# MANAGE.claims in turn.
SERIAL = r"""
(() => {
    let ADDR = %s;
    const ID = %s, CLAIM = %s, FAIL = %s, SAYS = %s, MANAGE = %s;
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
        if (cmd === 2 && MANAGE) return [[2, [0]], [1, [4]], [4, strs(2, "http://" + ADDR + "/#id=" + ID)]];
        if (cmd === 2) return [[2, [0]], [1, [2]]];
        if (cmd === 1 && MANAGE) {
            ADDR = MANAGE.at[dec.decode(new Uint8Array(d.slice(1, 1 + d[0])))] || ADDR;
            return [[2, [0]], [1, [3]], [1, [4]], [4, strs(1, "http://" + ADDR + "/#id=" + ID)]];
        }
        if (cmd === 240 && MANAGE) return [[2, [0]], [4, strs(240, "http://" + ADDR + "/#id=" + ID
                                                                 + "&claim=" + MANAGE.claims.shift())]];
        if (cmd === 3) return [[2, [0]], [4, strs(3, "Moybyte", "v0.16", "ESP32-C3", name)]];
        if (cmd === 4) return [[2, [0]], [4, strs(4, "home", "-40", "YES")], [4, [4, 0]]];
        if (cmd === 6) { if (d.length) name = dec.decode(new Uint8Array(d.slice(1)));
                         return [[2, [0]], [4, strs(6, name)]]; }
        if (cmd === 1 && FAIL) return [[2, [0]], [1, [3]], [2, [3]], [1, [2]]];
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
                async write(b) { const n = b[8], d = Array.from(b.slice(9, 9 + n)),
                                       out = [...enc.encode(SAYS[d[0]] || "")];
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
            {"init": SERIAL % (json.dumps(addr), json.dumps(board_id), json.dumps(claim), "false", "{}", "null")},
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
            {"press": "#list li:nth-child(2) button.open"},
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
            _js("SSH", "document.querySelector('#setup .ssh').textContent"),
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
        assert _tagged(js, "SSH").startswith("Its terminal: ssh %s, with that password" % addr), tail
        assert (host.tree / "sd" / "moybyte" / "system" / "password").read_text().startswith("$moy2$"), tail
        reached = _tagged(js, "REACHED")
        assert reached.startswith("reached ") and body.hex()[:12] in reached, tail
        after = _tagged(js, "AFTER")[0]
        assert after["page"] == body.hex() and after["pack"] == hashlib.sha256(data).hexdigest(), tail
    finally:
        for p in procs:
            p.terminate()
        host.end()


WIFI = "hunter2-wifi"
BOARD_SAYS = {
    2: "I (310) moybyte: zero serving improv\r\n",
    1: ("I (5120) wifi: joining home with %s\r\n"
        "\x1b[0;33mW (9120) wifi: disconnected, reason 2 (auth expired): "
        "a weak antenna?\x1b[0m\r\nE (9121) improv: join failed" % WIFI),
}


def test_a_refused_join_opens_the_board_log_without_the_wifi_password(tmp_path):
    web_e2e.require()
    import os_site

    os_site.build(str(tmp_path / "site"))
    sport = web_e2e.free_port()
    site = "http://localhost:%d" % sport
    slog = tmp_path / "site.log"
    sp = subprocess.Popen([sys.executable, str(ROOT / "tools" / "os_site.py"), "serve",
                           str(tmp_path / "site"), "--port", str(sport)],
                          stdout=open(slog, "w"), stderr=subprocess.STDOUT)
    log = "document.querySelector('#setup details.boardlog')"
    try:
        _up(site + "/console/", sp, slog)
        steps = [
            {"waitFor": "typeof render == 'function'", "timeout": 15000},
            {"init": SERIAL % ('"x"', '"x"', '"x"', "true", json.dumps(BOARD_SAYS), "null")},
            {"waitFor": "typeof render == 'function' && !document.getElementById('cable').hidden",
             "timeout": 15000},
            {"press": "#cable"},
            {"waitFor": "document.querySelector('#setup form input[name=name]')", "timeout": 15000},
            _js("CLOSED", "[%s.open, %s.querySelector('pre').textContent]" % (log, log)),
            _field("#setup form input[name=name]", "Kitchen"),
            _field("#setup form input[name=wifi]", WIFI),
            {"js": "document.querySelector('#setup form').requestSubmit(), 1"},
            {"waitFor": "%s.open" % log, "timeout": 15000},
            _js("SAID", "document.querySelector('#setup .setup-said').textContent"),
            _js("LOG", "%s.querySelector('pre').textContent" % log),
            {"js": "navigator.clipboard.writeText = (t) => (window.__copied = t, Promise.resolve()), "
                   "%s.querySelector('button').click(), 1" % log},
            {"waitFor": "window.__copied !== undefined", "timeout": 5000},
            _js("COPIED", "window.__copied"),
            _js("PAGE", "document.body.innerHTML.includes(%s)" % json.dumps(WIFI)),
        ]
        out, js = web_e2e.run(tmp_path, "boardlog", "console/", steps, site, tmp_path / "chrome",
                              boot_ms=1000)
        tail = out[-3000:]
        closed = _tagged(js, "CLOSED")
        assert closed == [False, "I (310) moybyte: zero serving improv\n"], tail
        assert "could not join" in _tagged(js, "SAID"), tail
        lines = _tagged(js, "LOG").splitlines()
        assert lines[-3:] == [
            "I (5120) wifi: joining home with ********",
            "W (9120) wifi: disconnected, reason 2 (auth expired): a weak antenna?",
            "E (9121) improv: join failed"], tail
        copied = _tagged(js, "COPIED")
        assert "reason 2" in copied and WIFI not in copied and "\x1b" not in copied, tail
        assert _tagged(js, "PAGE") is False, "the Wi-Fi password is on the page"
    finally:
        sp.terminate()


OLD_PASSWORD, NEW_PASSWORD = "old-password-1", "den-password-2"


def test_manage_by_cable_moves_its_wifi_renames_it_and_replaces_its_password(tmp_path):
    """A Zero already on a network, from the setup entry: it joins another
    network and the card takes its new address, it takes a new name, and a
    new password crosses as a claim the cable minted. A claim a newer one
    replaced is refused and the console's pairing prompt says why, with its
    button live, in a Zero's words; the fresh one replaces the password,
    every paired browser is signed out (its key kept), and this one pairs."""
    web_e2e.require("sync", "signin")
    import gen_web_blob
    import os_site
    import test_moy_tty
    sys.path.insert(0, str(ROOT))
    from runtime.system import ssh_service

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
        system = host.tree / "sd" / "moybyte" / "system"
        old_record = ssh_service.hashed(OLD_PASSWORD, "5a1t")
        (system / "password").write_text(old_record)
        host.say("cable")
        old = host.browser()
        assert old.json("GET", "/carts.json")[0] == 200
        at = len(host.log())
        host.say("claim new")
        _, stale, board_id = host.wait_line("CLAIM ", at).split()
        at = len(host.log())
        host.say("claim new")
        _, fresh, _ = host.wait_line("CLAIM ", at).split()
        assert stale != fresh
        blog = tmp_path / "board.log"
        bp = subprocess.Popen([sys.executable, "serve.py", str(bport), "dist",
                               "--board", "127.0.0.1:%d" % host.port,
                               "--loader", "--mirror", site + "/console/"],
                              cwd=str(RUNNER), stdout=open(blog, "w"), stderr=subprocess.STDOUT)
        procs.append(bp)
        _up(site + "/console/packs.json", sp, slog)
        _up(board + "/sync", bp, blog)

        addr = "127.0.0.1:%d" % bport
        manage = {"at": {"office": addr}, "claims": [stale, fresh]}
        kept = "JSON.parse(localStorage.getItem('moy.consoles') || '[]')"
        said = "document.querySelector('#setup .setup-said').textContent"
        card = "document.querySelector('#list li .state').textContent"
        pw = ("(() => { const f = document.querySelector('#setup form[name=password]'); "
              "const p = f.querySelectorAll('input[type=password]'); p[0].value = p[1].value = %s; "
              "f.requestSubmit(); return 1; })()" % json.dumps(NEW_PASSWORD))
        steps = [
            {"waitFor": "typeof render == 'function'", "timeout": 15000},
            {"init": SERIAL % (json.dumps("10.9.9.9:1"), json.dumps(board_id), '""', "false", "{}",
                               json.dumps(manage))},
            {"waitFor": "typeof render == 'function' && !document.getElementById('cable').hidden",
             "timeout": 15000},
            {"note": "the setup entry on a board already on a network manages it"},
            {"press": "#cable"},
            {"waitFor": "document.querySelector('#setup form[name=wifi] option[value=home]')",
             "timeout": 15000},
            _js("FIRST", kept),
            _js("CARDBUTTON", "!!document.querySelector('#list li button.manage')"),
            {"js": "(() => { const f = document.querySelector('#setup form[name=wifi]'); "
                   "f.querySelector('select').value = ''; f.querySelector('select').onchange(); "
                   "f.querySelector('input[name=ssid]').value = 'office'; "
                   "f.querySelector('input[name=wifi]').value = 'office pass'; f.requestSubmit(); "
                   "return 1; })()"},
            {"waitFor": "%s.includes('joined') || !!document.querySelector('#setup .setup-said.bad')" % said,
             "timeout": 15000},
            _js("JOINED", "[%s, %s]" % (kept, said)),
            {"js": "(() => { const f = document.querySelector('#setup form[name=rename]'); "
                   "f.querySelector('input').value = 'Den'; f.requestSubmit(); return 1; })()"},
            {"waitFor": "%s.startsWith('Named')" % said, "timeout": 15000},
            _js("NAMED", "[%s, window.__improv.includes(6)]" % kept),
            {"note": "a claim a newer one replaced: refused, and the prompt says why"},
            {"js": pw},
            {"waitFor": "document.querySelector('#setup button.opener')", "timeout": 15000},
            _js("PWSTORED", "JSON.stringify(localStorage).includes(%s)" % json.dumps(NEW_PASSWORD)),
            {"press": "#setup button.opener"},
            {"tab": board},
            {"waitFor": "document.getElementById('pin').style.display == 'flex' && "
                        "document.getElementById('pinm').textContent.includes('run out')",
             "timeout": 120000},
            _js("PROMPT", "[document.getElementById('pinm').textContent, "
                          "document.getElementById('pinp').textContent, "
                          "document.getElementById('pinb').disabled]"),
            {"tab": site},
            {"waitFor": "%s.includes('not set')" % card, "timeout": 15000},
            _js("CARDSAID", card),
            {"note": "the fresh claim replaces the password and this browser pairs"},
            {"js": pw},
            {"waitFor": "document.querySelector('#setup button.opener')", "timeout": 15000},
            {"press": "#setup button.opener"},
            {"waitFor": "%s == 'signed in'" % card, "timeout": 60000},
            _js("ASKED", "window.__improv"),
            {"press": "#setup button[name=done]"},
            _js("CLOSED", "document.getElementById('setup').hidden"),
        ]
        out, js = web_e2e.run(tmp_path, "manage", "console/", steps, site, tmp_path / "chrome",
                              boot_ms=1000)
        tail = out[-4000:] + "\n-- board --\n" + host.log()[-1500:]
        first = _tagged(js, "FIRST")
        assert [(c["id"], c["address"]) for c in first] == [(board_id, "10.9.9.9:1")], tail
        assert _tagged(js, "CARDBUTTON") is True, tail
        joined, line = _tagged(js, "JOINED")
        assert [c["address"] for c in joined] == [addr] and "joined office" in line, tail
        named, renamed = _tagged(js, "NAMED")
        assert [c["name"] for c in named] == ["Den"] and renamed, tail
        assert _tagged(js, "PWSTORED") is False, "the password reached the site's storage"
        why, prompt, disabled = _tagged(js, "PROMPT")
        assert "run out" in why and "Manage by cable" in why, tail
        assert "by cable" in prompt and "WEB CONSOLE" not in prompt and disabled is False, tail
        assert "run out" in _tagged(js, "CARDSAID"), tail
        assert _tagged(js, "ASKED").count(240) == 2, tail
        assert _tagged(js, "CLOSED") is True, tail
        rec = (system / "password").read_text()
        assert rec.startswith("$moy2$") and rec != old_record, tail
        with pytest.raises(seal_client.Refused) as e:
            old.call("GET", "/carts.json")
        assert e.value.status == 401, "the old browser's session outlived the new password"
        old.sign_in()
        assert old.json("GET", "/carts.json")[0] == 200, "its key is kept"
    finally:
        for p in procs:
            p.terminate()
        host.end()
