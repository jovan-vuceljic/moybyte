"""The Terminal and the sign-in in a real browser, in both web modes.

BOARD-SERVED: the page a board serves pairs with it and opens its Terminal
straight into `remote`, a face of the board's shell
(native/moy_sh/moy_sh_link.h), over the worker's WebSocket to GET /term, every
frame sealed. The board is real C: the web terminal's host harness (the
kernel's webhost with its sign-in, the bridge, the face and the board's shell,
tests/test_moy_tty.py), and serve.py --board serves the bundle in front of it.
A page paired by the QR's link reloads signed in with its device key; a page
pairs by the console's password in its prompt; a wrong one, a wait, a board
that no longer takes the browser and one that does not answer each say so.

SITE: the site's console (dist_site/, `build.sh --site`) runs the shell
itself in the wasm on the browser's store; a command past its run's budget
gives the tab back.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_term_e2e.py
"""

import base64
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import pytest

import web_e2e
from web_e2e import RUNNER, ROOT

sys.path.insert(0, os.path.dirname(__file__))

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")

PASSWORD = "correct horse"


@pytest.fixture(scope="module")
def tty_exe(tmp_path_factory):
    web_e2e.require("term", "signin")
    import test_moy_tty
    return test_moy_tty._build(tmp_path_factory.mktemp("tty"))


@pytest.fixture
def short():
    """The harness's folder: short enough for the webhost's paths, whose
    system folder past MOY_WEB_PATH_MAX (96 bytes) is refused, however deep
    pytest's tmp_path runs (xdist's popen-gwN, a long test name)."""
    d = tempfile.mkdtemp(prefix="moyw")
    yield pathlib.Path(d)
    shutil.rmtree(d, ignore_errors=True)


def _board(tty_exe, root, password=None):
    """The harness under `root` with the seed carts in its store (and the
    console's password, as `passwd` writes it, when given)."""
    import test_moy_tty
    from runtime.system import ssh_service
    host = test_moy_tty.Host(tty_exe, root)
    store = host.tree / "sd" / "moybyte" / "carts"
    for cart in sorted((ROOT / "system_carts").glob("*.moy")):
        shutil.copytree(cart, store / cart.name)
    if password:
        (host.tree / "sd" / "moybyte" / "system" / "password").write_text(
            ssh_service.hashed(password, "e2e0salt"))
    return host


def _serve(tmp_path, board_port, dist="dist", extra=()):
    web_e2e.warm_host_library()
    port = web_e2e.free_port()
    log = tmp_path / "serve.log"
    args = [sys.executable, "serve.py", str(port), dist, "--board",
            "127.0.0.1:%d" % board_port] + list(extra)
    p = subprocess.Popen(args, cwd=RUNNER, stdout=open(log, "w"), stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/index.html", timeout=1).read(64)
            return p, base
        except OSError:
            if p.poll() is not None:
                pytest.fail("serve.py died on startup:\n" + log.read_text())
            time.sleep(0.1)
    p.terminate()
    pytest.fail("serve.py never answered")


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _qr_fragment(host, board=None):
    """What the console's QR carries after its address: the token, and the
    first 8 bytes of the board's id (moy_webconsole.c's paired URL)."""
    import seal_client
    if board is None:
        try:
            board = seal_client.Browser(host.send).hello()["id"]
        except seal_client.Refused as no:        # a board with the live socket
            if no.status != 410:
                raise
            import test_live_link as L
            board = L.board_id(host)
    return "#t=%s&b=%s" % (_b64url(bytes.fromhex(host.token())),
                           _b64url(bytes.fromhex(board)[:8]))


def _lines(tag):
    return {"js": "window.__moyState().then(s => '%s ' + JSON.stringify(s.term))" % tag}


def _until(test, timeout=30000):
    """A step that holds until a grid line passes `test` (a JS predicate over
    one line), so each check waits on what it checks, never on a guess."""
    return {"waitFor": "window.__moyState().then(s => s.term.some(%s))" % test,
            "timeout": timeout}


def _says(text):
    return _until("ln => ln.includes(%s)" % json.dumps(text))


_SHELL = "ln => /\\$\\s*$/.test(ln)"

# The sign-in's prompt as the page shows it, and the keys it holds.
_PROMPT = ("({shown: getComputedStyle(document.getElementById('pin')).display, "
           "said: document.getElementById('pinm').textContent, url: location.href, "
           "keys: Object.keys(JSON.parse(localStorage.getItem('moybyte.keys') || '{}'))"
           ".length})")


def _prompt(tag):
    return {"js": "'%s ' + JSON.stringify(%s)" % (tag, _PROMPT)}


def _asks(test, timeout=30000):
    """A step that holds until the prompt's state passes `test` (a JS
    predicate over _PROMPT's object)."""
    return {"waitFor": "(%s)(%s)" % (test, _PROMPT), "timeout": timeout}


def _gone(timeout=30000):
    """A step that holds until the board behind serve.py stops answering."""
    return {"waitFor": "fetch('/no-such-route').then(r => r.status === 502, () => true)",
            "timeout": timeout}


def _password(pw):
    return {"js": "(document.getElementById('pinf').value = %s, "
                  "document.getElementById('pinb').click(), 'typed')" % json.dumps(pw)}


def _tagged(js, tag):
    for j in js:
        if isinstance(j, str) and j.startswith(tag + " "):
            return json.loads(j[len(tag) + 1:])
    return None


def _typed(text):
    return [{"key": c} for c in text]


def _neofetch(tag):
    """neofetch run, its lines taken once its Shell row is up."""
    return (_typed("clear; neofetch") + [{"key": "Enter"}, _says("Shell: moy_sh"),
                                         _lines(tag)])


def _beside(lines, word):
    """Whether Moy stands left of the row that holds `word`: his 15 columns
    (an ink in them), three blank, the row from the 18th."""
    rows = [re.sub("\x1b\\[[0-9;]*m", "", ln) for ln in lines or []]
    row = next((ln for ln in rows if word in ln), "")
    return row.find(word) >= 18 and row[:18].strip() != "" and row[15:18] == "   "


def _lost(key):
    """`key` down, then the window's blur before its up: HELD before the
    blur, LOST after it, each {held buttons, typing level}."""
    held = ("window.__moyState().then(s => '%s ' + JSON.stringify("
            "{held: s.held, typing: s.typing}))")
    return [{"js": "cv.dispatchEvent(new KeyboardEvent('keydown', {key: %s})), 'down'"
                   % json.dumps(key)},
            {"wait": 300}, {"js": held % "HELD"},
            {"js": "window.dispatchEvent(new Event('blur')), 'blur'"},
            {"wait": 300}, {"js": held % "LOST"}]


def _late(key, ms=1000):
    """`key` down, and its up behind a main-thread task of `ms`: the page
    delivers the up late, as a busy phone's or a loaded machine's does."""
    k = json.dumps(key)
    return [{"js": "cv.dispatchEvent(new KeyboardEvent('keydown', {key: %s})), 'down'" % k},
            {"wait": 150},
            {"js": "(() => { const t = performance.now(); while (performance.now() - t < %d) {} "
                   "cv.dispatchEvent(new KeyboardEvent('keyup', {key: %s})); return 'up'; })()"
                   % (ms, k)}]


def _sides(host, tmp_path, out):
    """Each side's own account, for a failure to say which one stuck: the
    shell's host (its STATS: sessions, live, bytes each way), serve.py's log
    and the page's run."""
    return "\n".join(["", "-- the shell's host:", host.log()[-1500:],
                      "-- serve.py:", (tmp_path / "serve.log").read_text()[-1500:],
                      "-- the page:", out[-2500:]])


_GRANT = {"grant": ["clipboardReadWrite", "clipboardSanitizedWrite"]}


# Ctrl+V as a hand presses it: the browser runs its paste on it.
_PASTE = {"key": "v", "mods": ["ctrl"], "commands": ["paste"]}


def _menu(tag):
    """Whether the system menu shows, under `tag`."""
    return {"js": "window.__moyState().then(s => '%s ' + JSON.stringify(s.edit.sysmenu))" % tag}


def _alt_tap_opens_the_menu(tag):
    """The page's console key: Alt with a key is a chord and opens nothing, a
    lone Alt tap opens the system menu (`<tag>_OPEN`) and Esc closes it."""
    return [{"key": "b", "mods": ["alt"]}, {"wait": 300}, _menu(tag + "_CHORD"),
            {"key": "Alt"},
            {"waitFor": "window.__moyState().then(s => s.edit.sysmenu)", "timeout": 5000},
            _menu(tag + "_OPEN"), {"key": "Escape"},
            {"waitFor": "window.__moyState().then(s => !s.edit.sysmenu)", "timeout": 5000}]


# The system menu's Full screen, chosen: the page's own fullscreen, which its
# keyboard lock holds in.
_FULL = (web_e2e.menu_pick("Full screen")
         + [{"js": "new Promise(ok => setTimeout(ok, 800)).then(() => window.__moyState())"
                   ".then(s => 'LOCK ' + JSON.stringify({fs: !!document.fullscreenElement, "
                   "locked: window.__moyLocked, said: s.page.fs}))"}])


def _assert_alt_tap(js, tag):
    assert _tagged(js, tag + "_CHORD") is False, js
    assert _tagged(js, tag + "_OPEN") is True, js


def _clipboard_holds(text):
    """The browser's clipboard holding `text` (the page's origin granted it)."""
    return {"js": "navigator.clipboard.writeText(%s).then(() => 'held')" % json.dumps(text)}


def _play(tmp_path, name, base, steps, after="", profile="chrome", env=None):
    q = "?dev=1&desktop=1&cart=Terminal" + after
    return web_e2e.run(tmp_path, name, q, steps, base, tmp_path / profile, env=env,
                       boot_ms=30000)


def test_a_page_paired_by_the_qr_reloads_signed_in_and_its_terminal_is_sealed(
        tty_exe, tmp_path, short):
    host = _board(tty_exe, short)
    server, base = _serve(tmp_path, host.port)
    try:
        steps = ([_GRANT, {"note": "paired by the token, the Terminal connects"},
                  _until(_SHELL), _prompt("PAIRED"), _lines("OPEN")]
                 + _typed("echo web-$((6*7))") + [{"key": "Enter"}, _says("web-42"),
                                                   _lines("ECHO")]
                 + _neofetch("NF") + [{"shot": "term_board"}]
                 # the board's vi over the socket: Esc leaves INSERT, `:wq` saves
                 + _typed("vi v.txt") + [{"key": "Enter"}, _says("v.txt"), {"key": "i"},
                                         _says("-- INSERT --")] + _typed("over the socket")
                 + [{"key": "Escape"}, _until("ln => ln.includes('[+]')")]
                 + _typed(":wq") + [{"key": "Enter"}, _until(_SHELL)]
                 + _typed("cat v.txt") + [{"key": "Enter"}, _says("over the socket"),
                                          _lines("VI")]
                 # the browser's paste, whole, into the board's shell
                 + [_clipboard_holds("echo sealed-$((6*7))\necho sealed-two\n"),
                    _PASTE, _says("sealed-two"), _lines("PASTE")]
                 + _alt_tap_opens_the_menu("BOARD"))
        out, js = _play(tmp_path, "term_board", base, steps, after=_qr_fragment(host))
        paired = _tagged(js, "PAIRED")
        assert paired and paired["keys"] == 1 and "#" not in paired["url"], (
            str(paired) + _sides(host, tmp_path, out))
        assert any(ln.rstrip().endswith("$") for ln in _tagged(js, "OPEN")), js
        assert "web-42" in "\n".join(_tagged(js, "ECHO")), (
            str(js) + _sides(host, tmp_path, out))
        assert int(host.stats()["in"]) > 0, "no key crossed the sealed socket"
        assert _after(js, "VI", "cat v.txt") == ["over the socket"], js
        assert _after(js, "PASTE", "echo sealed-$((6*7))")[:1] == ["sealed-42"], js
        assert _after(js, "PASTE", "echo sealed-two") == ["sealed-two"], js
        _assert_alt_tap(js, "BOARD")
        assert _beside(_tagged(js, "NF"), "Board: host harness"), _tagged(js, "NF")
        # the same profile, no token: the stored key signs in, nothing typed;
        # then the board goes away, and the next connect says so
        gone = threading.Thread(target=_end_when, args=(host, "2"), daemon=True)
        gone.start()
        steps = ([_until(_SHELL), _prompt("AGAIN"), _lines("OPEN")]
                 + _typed("exit 4") + [{"key": "Enter"}, _says("[the shell exited 4]"),
                                       _lines("EXIT"), _gone(), {"key": "Enter"},
                                       _says("does not answer"), _lines("GONE")])
        out, js = _play(tmp_path, "term_again", base, steps)
        assert _tagged(js, "AGAIN")["shown"] == "none", js
        assert any(ln.rstrip().endswith("$") for ln in _tagged(js, "OPEN")), js
        assert "[the shell exited 4]" in "\n".join(_tagged(js, "EXIT")), (
            str(js) + _sides(host, tmp_path, out))
        assert any("does not answer" in ln for ln in _tagged(js, "GONE")), js
        gone.join(5)
    finally:
        server.terminate()
        host.end()


# The Terminal's window closed by its strip's X: a press and a release at
# the strip's last button (runtime/wm/wm_strip.py, `close` the rightmost).
_CLOSE_TERMINAL = {"js": (
    "window.__moyState().then(function (s) { var w = s.wins.terminal, "
    "x = w[0] + w[2] - Math.round(w[4] / 2), y = w[1] + Math.round(w[4] / 2); "
    "send({type: 'down', x: x, y: y, mods: 0}); return new Promise(function (ok) { "
    "setTimeout(function () { send({type: 'up'}); ok('X ' + JSON.stringify([x, y])); }, 80); "
    "}); })")}


def test_a_closed_terminal_gives_the_board_s_shell_back_to_ssh(tty_exe, tmp_path, short):
    """The Terminal's window closed and its page left open: the board's face
    ends (the link's close, native/moy_sh/moy_sh_link.h), so SSH opens one
    while the page stays."""
    host = _board(tty_exe, short)
    server, base = _serve(tmp_path, host.port)
    try:
        steps = [_GRANT, _until(_SHELL), _CLOSE_TERMINAL,
                 {"waitFor": "window.__moyState().then(s => (s.order || []).indexOf("
                             "'terminal') < 0)", "timeout": 10000},
                 {"wait": 1500},
                 {"js": "'CLOSED'"},
                 {"wait": 8000}]
        scenario = tmp_path / "closed.json"
        scenario.write_text(json.dumps({"query": "?dev=1&desktop=1&cart=Terminal"
                                        + _qr_fragment(host), "boot_ms": 30000,
                                        "steps": steps}))
        proc = subprocess.Popen(
            ["node", "browsershot.mjs", str(scenario), str(tmp_path / "closed")], cwd=RUNNER,
            env=dict(os.environ, MOY_BASE=base, MOY_PROFILE=str(tmp_path / "chrome")),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        lines, ran = [], None
        try:
            for line in proc.stdout:
                lines.append(line)
                if ran is None and 'js -> "CLOSED"' in line:
                    at = len(host.log())
                    host.say("run echo ssh")
                    ran = host.wait_line("RAN ", after=at)
            proc.wait(timeout=120)
        finally:
            if proc.poll() is None:
                proc.kill()
        out = "".join(lines)
        assert ran == "RAN 0", "%s\n%s" % (ran, out[-3000:] + _sides(host, tmp_path, out))
    finally:
        server.terminate()
        host.end()


def _end_when(host, sessions):
    """The board gone once `sessions` sockets were served and none is live."""
    end = time.monotonic() + 120
    while time.monotonic() < end:
        try:
            s = host.stats()
        except (IndexError, ValueError, OSError):
            s = {}
        if s.get("sessions") == sessions and s.get("live") == "0":
            host.proc.kill()
            return
        time.sleep(0.1)


def test_a_dropped_browser_is_asked_to_pair_again(tty_exe, tmp_path, short):
    host = _board(tty_exe, short)
    server, base = _serve(tmp_path, host.port)
    try:
        steps = [_asks("p => p.keys === 1 && p.shown === 'none'"), _prompt("PAIRED")]
        _out, js = _play(tmp_path, "paired", base, steps, after=_qr_fragment(host))
        assert _tagged(js, "PAIRED")["keys"] == 1, js
        host.say("drop")
        host.wait_line("DROPPED 1")
        steps = [_asks("p => p.shown === 'flex' && p.keys === 0"), _prompt("ASKED")]
        _out, js = _play(tmp_path, "dropped", base, steps)
        asked = _tagged(js, "ASKED")
        assert asked["shown"] == "flex" and asked["keys"] == 0, asked
    finally:
        server.terminate()
        host.end()


def test_a_page_pairs_by_the_console_s_password(tty_exe, tmp_path, short):
    host = _board(tty_exe, short, password=PASSWORD)
    server, base = _serve(tmp_path, host.port)
    try:
        wrong = "that password did not work -- try again"
        steps = ([_asks("p => p.shown === 'flex'"), _prompt("ASK"), _password("wrong horse"),
                  _asks("p => p.said === %s" % json.dumps(wrong)), _prompt("WRONG"),
                  _password(PASSWORD), _until(_SHELL), _prompt("PAIRED"), _lines("OPEN")]
                 + _typed("echo pw-ok") + [{"key": "Enter"}, _says("pw-ok"),
                                           _lines("ECHO")]
                 + _neofetch("NF"))
        out, js = _play(tmp_path, "term_password", base, steps)
        assert _tagged(js, "ASK")["shown"] == "flex", js
        assert _tagged(js, "WRONG")["said"] == wrong, js
        paired = _tagged(js, "PAIRED")
        assert paired["shown"] == "none" and paired["keys"] == 1, (
            str(paired) + _sides(host, tmp_path, out))
        assert "pw-ok" in "\n".join(_tagged(js, "ECHO")), js
        # the page laid the Terminal out while it asked: that size reached
        # the board's shell when the socket opened, and Moy stands beside
        assert _beside(_tagged(js, "NF"), "Board: host harness"), _tagged(js, "NF")
    finally:
        server.terminate()
        host.end()


def test_a_page_says_how_long_a_board_holding_wrong_tries_off_waits(tty_exe, tmp_path, short):
    """Wrong tokens from this source past its free tries open a window; the
    page's hello meets the wait, and its prompt says the backoff's one
    sentence."""
    import seal_client
    host = _board(tty_exe, short)
    page = seal_client.Browser(host.send)
    board = page.hello()["id"]
    for _ in range(11):
        with pytest.raises(seal_client.Refused) as e:
            page.pair_token("00" * 16)
        assert e.value.status == 403, e.value.doc
    # The eleventh wrong try's window is a second; the clock stepped back a
    # minute holds it open past the page's boot, however long that takes.
    host.skew(-60000)
    qr = _qr_fragment(host, board)
    server, base = _serve(tmp_path, host.port)
    try:
        steps = [_asks("p => p.said.startsWith('Too many wrong tries')"), _prompt("ASK"),
                 {"shot": "signin_wait"}]
        _out, js = _play(tmp_path, "signin_wait", base, steps, after=qr)
        ask = _tagged(js, "ASK")
        assert ask["shown"] == "flex", ask
        m = re.match(r"^Too many wrong tries -- try again in (\d+) s$", ask["said"])
        assert m and 1 <= int(m.group(1)) <= 61, ask
    finally:
        server.terminate()
        host.end()


def _site(tmp_path):
    """serve.py over dist_site/: (the process, its base)."""
    port = web_e2e.free_port()
    p = subprocess.Popen([sys.executable, "serve.py", str(port), "dist_site"], cwd=RUNNER,
                         stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/index.html", timeout=1).read(64)
            break
        except OSError:
            time.sleep(0.1)
    return p, base


def test_the_site_s_terminal_runs_the_shell_on_the_browser_s_store(tmp_path):
    """The site's console: the session's root is the store's folder (/moy in
    the page), home its files; a run past its budget gives the tab back; a
    key let go late types once (the browser's repeat is the only one), and
    a key held as the page loses the keyboard goes up; neofetch draws Moy
    beside its rows."""
    web_e2e.require("site_shell")
    p, base = _site(tmp_path)
    try:
        steps = ([{"note": "the site's shell", "wait": 1500}]
                 + _typed("pwd; ls /") + [{"key": "Enter"}, {"wait": 600}, _lines("LS")]
                 + _typed("sleep 30") + [{"key": "Enter"}, {"wait": 4500}, _lines("SLEPT")]
                 + _typed("echo back") + [{"key": "Enter"}, {"wait": 600}, _lines("BACK")]
                 + _typed("echo late-") + _late("i") + _typed("-key")
                 + [{"key": "Enter"}, {"wait": 600}, _lines("LATE")]
                 + _lost("ArrowDown")
                 + _typed("cd; printf 'import sys\\nprint(sys.argv)\\n' > p.py; python p.py web;"
                          " printf '#!python\\nprint(6 * 7)\\n' > q.py; ./q.py")
                 + [{"key": "Enter"}, {"wait": 1200}, _lines("PY")]
                 + _neofetch("NF"))
        _out, js = _play(tmp_path, "term_site", base, steps)
        ls = "\n".join(_tagged(js, "LS"))
        assert "/files" in ls and "carts/" in ls and "files/" in ls, ls
        # the typed line in the palette's accent (base 12), as on the desk
        assert "\x1b[38;2;41;173;255mpwd; ls /" in ls, ls
        slept = "\n".join(_tagged(js, "SLEPT"))
        assert "[stopped: a command in the browser runs for 3 s at most]" in slept, slept
        assert "back" in "\n".join(_tagged(js, "BACK"))
        late = _tagged(js, "LATE")
        assert any(ln.strip() == "late-i-key" for ln in late), late
        assert "down" in _tagged(js, "HELD")["held"], _tagged(js, "HELD")
        assert _tagged(js, "LOST") == {"held": [], "typing": 0}, _tagged(js, "LOST")
        py = "\n".join(_tagged(js, "PY"))
        assert "['p.py', 'web']" in py and "42" in py, py
        assert _beside(_tagged(js, "NF"), "@moybyte"), _tagged(js, "NF")
    finally:
        p.terminate()


def _site_with(tmp_path, carts):
    """dist_site/ as a static site whose bundled shelf also carries `carts`
    (built cart folders, {folder name: path}), each file as the bundle
    carries one: text, or a binary file's base64."""
    site = tmp_path / "site"
    site.mkdir()
    for name in os.listdir(web_e2e.DIST_SITE):
        if name != "carts.json":
            os.symlink(web_e2e.DIST_SITE / name, site / name)
    bundle = json.loads((web_e2e.DIST_SITE / "carts.json").read_text())
    for folder, path in carts.items():
        for dp, dn, fn in os.walk(path):
            dn[:] = [d for d in dn if d != "src"]
            for f in fn:
                full = os.path.join(dp, f)
                rel = os.path.relpath(full, path).replace(os.sep, "/")
                data = open(full, "rb").read()
                bundle[folder + "/" + rel] = ({"b": base64.b64encode(data).decode()}
                                              if rel.endswith(".wasm") else data.decode())
    (site / "carts.json").write_text(json.dumps(bundle))
    return site


def _wasi_carts(tmp_path):
    """The WASI fixtures (tests/fixtures/wasm), built by wasi-sdk as
    test_wasi_commands.py builds them, for the site's bundle, whose carts
    are this console's own (made here: they ask nothing): the probe and cat,
    each with `files`, and the crypto program. And the probe again as
    `wasi.asks`, zipped as a .moy for a drop: a cart that arrived as files,
    asked before its first run."""
    from cart_store_fixtures import stored_zip
    from tools import jet_cart, wasm_cart
    try:
        jet_cart.wasi_sdk(fetch=True)
    except Exception as exc:  # noqa: BLE001
        if os.environ.get("CI") or os.environ.get("MOYBYTE_REQUIRE_WEB_E2E"):
            pytest.fail("no wasi-sdk: %s" % exc)
        pytest.skip("no wasi-sdk: %s" % exc)
    fixtures = ROOT / "tests" / "fixtures" / "wasm"
    out = {}
    for name in ("wasi_probe", "wasi_cat", "wasi_crypto"):
        built = tmp_path / "built" / (name + ".moy")
        wasm_cart.build(str(fixtures / (name + ".moy")), str(built))
        out[name + ".moy"] = built
    man = json.loads((out["wasi_probe.moy"] / "manifest.json").read_text())
    man["id"], man["title"] = "wasi.asks", "Asks Wasi"
    drop = tmp_path / "wasi_asks.moy"
    drop.write_bytes(stored_zip("wasi_asks.moy", {
        "manifest.json": json.dumps(man).encode(),
        "main.wasm": (out["wasi_probe.moy"] / "main.wasm").read_bytes()}))
    return out, drop


def _after(js, tag, line, prompt="$ "):
    """The grid's lines under tag `tag` after the typed line `line`'s echo
    (its prompt's line and the lines it wrapped onto), blank ones and the
    next prompt dropped."""
    lines = [re.sub("\x1b\\[[0-9;]*m", "", ln).rstrip() for ln in _tagged(js, tag) or []]
    want = line.replace(" ", "")
    for i in range(len(lines) - 1, -1, -1):
        if prompt not in lines[i]:
            continue
        echo = lines[i].split(prompt, 1)[1].replace(" ", "")
        j = i + 1
        while len(echo) < len(want) and j < len(lines):
            echo += lines[j].replace(" ", "")
            j += 1
        if echo == want:
            return [ln for ln in lines[j:] if ln and not ln.endswith("$")]
    raise AssertionError("no %r on the grid:\n%s" % (line, "\n".join(lines)))


_ASK = "Open it? [y/N] "
# A REAL drop of the .moy the step before loaded, through the page's own handler.
_DROP = ("(function(){var f=new File([window.__drop],window.__dropName,"
         "{type:'application/octet-stream'});var dt=new DataTransfer();dt.items.add(f);"
         "window.dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,"
         "cancelable:true}));return 'dropped '+window.__dropName;})()")


def test_the_site_s_terminal_runs_a_wasi_command_on_the_page_s_engine(tmp_path):
    """A WASI module (wasi-sdk's, unchanged) typed in the site's Terminal runs
    on the browser's own WebAssembly engine, its rows the boards' adapter
    (native/moy_wasm/moy_wasi.c over native/moy_wasm_web/moy_wasi_web.h).
    Its first run asks at the shell's prompt and the next line typed answers;
    then its args, the session's exported variables, stdout and stderr on
    the grid, the exit code in $?, a pipe on stdin, the page's clocks and
    random, the moybyte.os rows served where they are called (files over its
    folder, the crypto rows), and the store's files, which a reload finds
    again out of OPFS."""
    import crypto_vectors
    web_e2e.require("site_shell", "site_wasi")
    carts, drop = _wasi_carts(tmp_path)
    site = _site_with(tmp_path, carts)
    server, base = web_e2e.serve(site, web_e2e.free_port())
    lines = []

    def line(tag, text):
        lines.append(text)
        return _typed(text) + [{"key": "Enter"}, {"wait": 800}, _lines(tag)]

    try:
        steps = ([{"note": "the site's shell", "wait": 1500},
                  {"file": "$MOY_DROP", "as": "__drop"},
                  {"js": _DROP}, {"wait": 3000}]
                 + line("ASK", "mkdir -p /files/Documents; cd /files/Documents; "
                               'wasi.asks/asks args one "two words"')
                 + line("ARGS", "y")
                 + line("ENV", "export GREETING=hi; wasi.probe/probe env GREETING")
                 + line("EXIT", "wasi.probe/probe exit 7; echo status $?")
                 + line("ERR", "wasi.probe/probe nothing; echo status $?")
                 + line("STDIN", "printf 'a\\nbc\\n' | wasi.probe/probe stdin")
                 + line("CLOCK", "wasi.probe/probe clock; wasi.probe/probe random")
                 + line("APP", "wasi.probe/probe app")
                 + line("FILES", "printf 'hello\\nweb\\n' > n.txt; "
                                 "wasi.cat/cat n.txt > m.txt; wasi.cat/cat m.txt")
                 + line("TERM", "wasi.probe/probe term")
                 + line("TRAP", "wasi.probe/probe trap; echo status $?")
                 + line("CRYPTO", "wasi.crypto/crypto; echo status $?")
                 + _typed("wasi.probe/probe spin") + [{"key": "Enter"}, {"wait": 4500}]
                 + line("SPIN", "echo status $?")
                 + [{"wait": 3000}])
        out, js = _play(tmp_path, "term_wasi", base, steps, profile="wasi",
                        env={"MOY_DROP": str(drop)})
        asked = _after(js, "ASK", lines[0])
        assert asked == ["Read and save your documents"], (asked, out[-3000:])
        assert _after(js, "ARGS", "y", _ASK) == ["0=asks", "1=args", "2=one", "3=two words"]
        assert _after(js, "ENV", lines[2]) == ["hi"]
        assert _after(js, "EXIT", lines[3]) == ["leaving with 7", "status 7"]
        assert _after(js, "ERR", lines[4]) == ["probe: no verb nothing", "status 64"]
        assert _after(js, "STDIN", lines[5]) == ["5 bytes 2 lines"]
        assert _after(js, "CLOCK", lines[6]) == ["since 2000 yes, slept yes", "random yes"]
        assert _after(js, "APP", lines[7]) == [
            "files.ready 1", "files.save probe", "files.count 1", "files.list probe,",
            "files.load # probe,", "files.load.other -1 errno 2", "files.rename moved",
            "files.load.moved # probe,", "files.delete moved", "files.count.after 0"]
        assert _after(js, "FILES", lines[8]) == ["hello", "web"]
        term = _after(js, "TERM", lines[9])
        assert len(term) == 1 and re.fullmatch(r"0 \d+ \d+", term[0]), term
        trap = _after(js, "TRAP", lines[10])
        assert trap[-1] == "status 134" and "unreachable" in trap[0], trap
        assert _after(js, "CRYPTO", lines[11]) == crypto_vectors.PROGRAM + ["status 0"]
        # a run past the browser's budget is stopped at its next import, as Ctrl-C stops it
        spin = [re.sub("\x1b\\[[0-9;]*m", "", ln).strip() for ln in _tagged(js, "SPIN")]
        assert "[stopped: a command in the browser runs for 3 s at most]" in spin, spin
        assert _after(js, "SPIN", lines[12]) == ["status 130"]
        again = (_typed("cat /files/Documents/m.txt") + [{"key": "Enter"}, {"wait": 800},
                                                          _lines("AGAIN")])
        _out, js = _play(tmp_path, "term_wasi_again", base,
                         [{"note": "reloaded", "wait": 1500}] + again, profile="wasi")
        assert _after(js, "AGAIN", "cat /files/Documents/m.txt") == ["hello", "web"], js
    finally:
        server.terminate()


def test_the_site_s_terminal_takes_esc_and_the_browser_s_clipboard(tmp_path):
    """The site's Terminal: Esc is vi's (INSERT left, `:wq` saves), the
    browser's paste (Ctrl+V) types a multi-line text whole, and a mouse's
    drag over the log then Ctrl+Shift+C puts its text on the browser's
    clipboard; a lone Alt tap is the console's key (the OS keeps Super), and
    a fullscreen locks Super and Esc for the page."""
    web_e2e.require("site_shell")
    p, base = _site(tmp_path)
    try:
        steps = ([_GRANT, {"note": "the site's shell", "wait": 1500}, _until(_SHELL)]
                 + _typed("vi /files/v.txt") + [{"key": "Enter"}, _says("v.txt")]
                 + [{"key": "i"}, _says("-- INSERT --")] + _typed("hi esc")
                 + [{"key": "Escape"}, _until("ln => ln.includes('[+]')")]
                 + _typed(":wq") + [{"key": "Enter"}, {"wait": 600}]
                 + _typed("cat /files/v.txt") + [{"key": "Enter"}, {"wait": 600}, _lines("VI")]
                 + [_clipboard_holds("echo pasted-$((6*7))\necho pasted-two\n"),
                    _PASTE, _says("pasted-two"), _lines("PASTE")]
                 + _typed("echo copy-me") + [{"key": "Enter"}, _says("copy-me")]
                 # the log's rows as the site's desk lays the Terminal's window
                 + [{"move": [262, 223]}, {"drag": [262, 223, 330, 237, 6]},
                    {"shot": "term_selected"}, {"key": "c", "mods": ["ctrl", "shift"]},
                    {"waitFor": "window.__moyClipped !== undefined", "timeout": 5000},
                    {"js": "navigator.clipboard.readText().then(t => 'COPIED ' + "
                           "JSON.stringify(t))"}]
                 + _alt_tap_opens_the_menu("SITE")
                 + _FULL)
        _out, js = _play(tmp_path, "term_clip", base, steps)
        assert _after(js, "VI", "cat /files/v.txt") == ["hi esc"], js
        assert _after(js, "PASTE", "echo pasted-$((6*7))")[:1] == ["pasted-42"], js
        assert _after(js, "PASTE", "echo pasted-two") == ["pasted-two"], js
        assert _tagged(js, "COPIED") == "files$ echo copy-me\ncopy-me", js
        _assert_alt_tap(js, "SITE")
        assert _tagged(js, "LOCK") == {"fs": True, "locked": 1, "said": True}, js
    finally:
        p.terminate()


def test_the_site_s_notes_takes_the_browser_s_paste_whole(tmp_path):
    """A multi-line paste (Ctrl+V) into a note in the site's console lands
    whole, which the note keeps: the Terminal of the page reloaded reads it
    in the note's file."""
    web_e2e.require("site_shell")
    p, base = _site(tmp_path)
    try:
        steps = ([_GRANT, {"note": "Notes", "wait": 2500}, {"key": "n"}, {"wait": 400}]
                 + _typed("pasted") + [{"key": "Enter"}, {"wait": 800},
                                       _clipboard_holds("first line\nsecond line\n"),
                                       _PASTE, {"wait": 800},
                                       {"shot": "notes_paste"}, {"key": "Escape"},
                                       {"wait": 3000}])
        web_e2e.run(tmp_path, "notes_paste", "?dev=1&desktop=1&cart=Notes", steps, base,
                    tmp_path / "notes", boot_ms=30000)
        steps = ([{"note": "the Terminal", "wait": 1500}, _until(_SHELL)]
                 + _typed("cat /files/Documents/pasted.md") + [{"key": "Enter"}, {"wait": 800},
                                                               _lines("NOTE")])
        _out, js = _play(tmp_path, "notes_read", base, steps, profile="notes")
        assert _after(js, "NOTE", "cat /files/Documents/pasted.md") == [
            "first line", "second line"], js
    finally:
        p.terminate()


def _focus(tag):
    return {"js": "window.__moyState().then(s => '%s ' + JSON.stringify("
                  "{focus: s.focus, menu: s.edit.sysmenu}))" % tag}


def test_alt_tab_walks_the_site_s_windows_in_its_fullscreen(tmp_path):
    """In the page's own fullscreen (the system menu's Full screen), whose
    keyboard lock gives it the chord, Alt+Tab brings the window behind
    forward, Alt+Shift+Tab walks back, and neither is the lone Alt tap that
    opens the system menu."""
    web_e2e.require("site_shell")
    p, base = _site(tmp_path)
    try:
        steps = ([{"note": "the Editor and the Terminal on the desk", "wait": 1500},
                  _until(_SHELL)] + _FULL + [_focus("FRONT"),
                  {"key": "Tab", "mods": ["alt"]}, {"wait": 400}, _focus("ALT_TAB"),
                  {"key": "Tab", "mods": ["alt", "shift"]}, {"wait": 400}, _focus("BACK"),
                  {"shot": "alt_tab"}])
        _out, js = web_e2e.run(tmp_path, "alt_tab",
                               "?dev=1&desktop=1&edit=moybyte.star_catcher.moy&tab=code"
                               "&cart=Terminal", steps, base, tmp_path / "chrome",
                               boot_ms=30000)
        assert _tagged(js, "LOCK")["locked"] == 1, js
        assert _tagged(js, "FRONT") == {"focus": "terminal", "menu": False}, js
        assert _tagged(js, "ALT_TAB") == {"focus": "menu", "menu": False}, js
        assert _tagged(js, "BACK") == {"focus": "terminal", "menu": False}, js
    finally:
        p.terminate()
