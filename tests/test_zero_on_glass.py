"""The two Zeros on the board: the XIAO (`xiao_zero`) and the C3 (`c3_zero`),
one suite parametrised by board, each gated on its own port variable.

    tools/board.py pass xiao_zero c3_zero       build, flash, reboot, this suite
    MOYBYTE_C3_ZERO_PORT=$(tools/board.py c3_zero port) \\
        .venv/bin/python -m pytest tests/test_zero_on_glass.py -s

A Zero has no dev channel: the suite asks it over the cable through Improv
and the raw REPL (tests/zero_glass.py), and over the network through its
pages, which headless Chrome boots (firmware/web_runner/browsershot.mjs).

  SETUP OVER THE CABLE. The board's networks are saved and cleared, so it
  hosts its setup access point; a real Improv join to a bench network
  follows, answered with the board's URL once it serves; then the saved
  networks go back. The bench network comes from MOYBYTE_BENCH_WIFI, a file
  in wifi.json's shape ({"networks": [{"ssid", "password"}]}), its first
  network or the one MOYBYTE_BENCH_SSID names; without it the test skips. No
  password prints: a URL prints without its fragment (the claim).

  THE BROWSER CONSOLE. The XIAO serves its add-on's page; the C3's console is
  online (`[web] console`), its root the loader, which boots the pack its
  image names from this machine's serve.py (run here on the port the image
  names) or the browser's cache. Both sign in and sync a cart.

  THE LIVE SOCKET. The page's echo round trip to its board (`__moyState().
  live.rtt`, one beat a second), bounded where power save (about 100 ms a
  round trip) cannot pass, and the board's internal RAM while the page holds
  the socket.

  GET CARTS. The page's Get Carts, driven by its keys, has the board
  install an official cart it lacks, remove the flash's Calc and get it
  back, and Get moybyte-org/carts' Moy Mesh, which needs a LoRa radio: a
  board whose board.toml has a `lora` row installs it, one without refuses
  it with nothing written; each ends as the board's lines say (an
  out-of-memory names its frames), with PAGE_FREE free while the page is
  open, and its internal heap after each is the idle one's within
  HEAP_SPREAD.

  A MATCH, where a T-Deck is on MOYBYTE_TDECK_PORT (the pass gives the
  T-Deck's port when it is in the same pass, after the T-Deck's own row): the
  page plays a Lua cart's and a Python cart's match against it, the world
  check armed on both sides (the page's `?linkcheck=1`, the T-Deck's `link
  check on`), and both report checkpoints and no desync. The T-Deck's
  math.atan2 is probed against the wasm's too.

THE CLAIM. The password removed, the board serves no SSH; the cable's
fresh claim opens the console on its URL, the page sets the password and
pairs without loading again, saying what it does, SSH answers at once, and
Get Carts opens and lists.

WHAT A PERSON DOES WITH IT, past setup:
  the terminal over SSH (this machine's OpenSSH): `edit` and `vi` save what
    was typed, a pipe and its cap's message, `find`/`du`/`rm -r` over a deep
    folder, `cat` of 64 KB, a second session ending the first;
  files and saves through the page: a cart imported on it reads back byte
    for byte from the board and through another browser, a game's pmem is
    back after a reboot, a full store refuses a cart with a message and
    corrupts nothing;
  the update screen saying what the channel offers, installing nothing;
  a cart and a setting surviving a reset, the open page reconnecting across
    one and across a Wi-Fi drop (an Improv join to a network that is not
    there), a second browser displacing the first (owner, 2026-11-25);
  the mDNS name and the clock;
  and last, a soak of all of it whose internal RAM must not keep falling.
The board's internal RAM is printed where a test is about it: free from
`free` in the SSH session, and free with its largest block over the cable
(which resets the board).

THE PASSWORD. A board with one is signed into with MOYBYTE_XIAO_ZERO_PASSWORD
or MOYBYTE_C3_ZERO_PASSWORD (without it the signed-in tests skip); a board
with none gets a bench one for the suite, which goes with the browsers it
paired when the suite ends.

THE BOARD IS GIVEN BACK. Every file of the store but the carts' is read at
the start; at the end what is new goes, what changed is written back (the
networks, the password, the paired browsers), the board restarts on the
network it served on, and the store's tree is compared with the start's.

THE NUMBERS. Internal RAM idle and with the socket open, the Improv join, the
loader's and /sync's serving time, the page's boot and the claim's submit to
a live console. Where the pass names
a file (MOYBYTE_ZERO_PERF_OUT, with MOYBYTE_ZERO_IMAGE the image's stamp)
they are written there as one perf record (tools/perf_pass.py), which the
pass appends to the board's history for tools/perf_ledger.py.
"""

import ast
import contextlib
import gzip
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

import on_glass
import zero_glass as Z
from on_glass import ROOT

BOARDS = (
    ("MOYBYTE_XIAO_ZERO_PORT", ROOT / "firmware" / "seeed_xiao_esp32s3_zero"),
    ("MOYBYTE_C3_ZERO_PORT", ROOT / "firmware" / "esp32c3_zero"),
)
RUNNER = ROOT / "firmware" / "web_runner"
SERVING = re.compile(r"ZERO serving (\S+)\s+\(mDNS (\S+)\)")
SETUP = "ZERO SETUP  join "
STORE = "/moy"
CARTS = STORE + "/carts"
MATCH_CARTS = ("Brick Siege Lua", "Brick Siege")
# The live socket's echo, median: about 100 ms with the station's power save
# on, a few ms without; and the beats it takes (one a second).
RTT_MEDIAN_MS = 40.0
RTT_BEATS = 30
LIVE_LOG = re.compile(r"LIVE|live|WEBHOST|WEBAUTH|alloc|refus|busy|ssh", re.I)

sys.path.insert(0, str(ROOT / "tools"))
import board_config  # noqa: E402
import gen_web_blob  # noqa: E402
from p4_autotest import P4Board  # noqa: E402

TDECK_PORT = os.environ.get("MOYBYTE_TDECK_PORT")
needs_tdeck = pytest.mark.skipif(not TDECK_PORT, reason="MOYBYTE_TDECK_PORT not set "
                                 "(the T-Deck a page plays a match against)")


def _ota(board_dir):
    return board_config.load(board_dir)["board"]["ota"]


def _params():
    out = []
    for var, d in BOARDS:
        name = _ota(d)
        _port, gate = on_glass.gate(var, name)
        out.append(pytest.param((name, var, d), id=name, marks=gate))
    return out


# -- the board ------------------------------------------------------------------


class Zero:
    """One Zero for the module: its port held open, what the store held at
    the start, the numbers taken."""

    def __init__(self, name, var, board_dir):
        self.name, self.dir = name, board_dir
        self.port = os.environ[var]
        cfg = board_config.load(board_dir)
        self.online = cfg.get("web", {}).get("console") == "online"
        self.pack = ROOT / os.path.dirname(cfg["flash"]["image"]) / "moybyte_web.pack"
        self.env_password = os.environ.get("MOYBYTE_%s_PASSWORD" % name.upper())
        self.b = P4Board(self.port, board_dir=str(board_dir))
        self.url = self.local = None
        self.password = None
        self.before_tree = {}
        self.before_files = {}
        self.taken, self.errors = {}, {}
        self.t0 = time.monotonic()

    @contextlib.contextmanager
    def repl(self, then=None, clean=True):
        """The raw REPL, the store host stopped (`clean`: on an empty heap,
        tests/zero_glass.py's Repl.enter), then the board reset to its boot
        line; `then` the line that ends it (default: serving)."""
        r = Z.Repl(self.b.ser)
        r.enter(clean=clean)
        try:
            yield r
        finally:
            self.restart(then)

    def restart(self, then=None):
        """A reset through esptool, as `tools/board.py ZERO reboot` makes it,
        and the port opened again. A soft reset is no way back on the C3: the
        heap its native blocks leave cannot hold a second start."""
        self.b.close()
        run = subprocess.run([sys.executable, str(ROOT / "tools" / "board.py"), self.name,
                              "reboot", "--port", self.port],
                             capture_output=True, text=True, timeout=240, cwd=str(ROOT))
        self.b = P4Board(self.port, board_dir=str(self.dir))
        up = [ln for ln in run.stdout.splitlines() if " is up on " in ln]
        assert run.returncode == 0 and up, "%s did not come back from its reset: %s" % (
            self.name, (run.stdout + run.stderr)[-800:])
        assert (then or "ZERO serving") in up[-1], up[-1]
        m = SERVING.search(up[-1])
        if m:
            self.url = m.group(1).rstrip("/")
            self.local = "http://" + m.group(2)
        return up[-1]

    def take(self, name, value, samples=()):
        self.taken[name] = (value, list(samples))

    def close(self):
        self.b.close()


def _snapshot(r):
    """(tree, {path: bytes}) of the store: every path's size, and the bytes
    of each file outside the carts' folders."""
    tree = r.tree(STORE)
    files = {p: r.read(p) for p, size in tree.items()
             if size >= 0 and not p.startswith(CARTS + "/")}
    return tree, files


def _give_back(z, r):
    """Remove what is new, write back what changed: what differs after."""
    now = r.tree(STORE)
    for p in sorted((p for p in now if p not in z.before_tree), key=len):
        if any(p.startswith(q + "/") for q in now if q not in z.before_tree and q != p):
            continue
        r.remove(p)
    for p, data in z.before_files.items():
        if r.read(p) != data:
            r.write(p, data)
    after = r.tree(STORE)
    return sorted(set(after.items()) ^ set(z.before_tree.items()))


def _bench_password():
    return "zero-bench-%s" % os.urandom(4).hex()


@pytest.fixture(scope="module", params=_params())
def zero(request):
    name, var, d = request.param
    z = Zero(name, var, d)
    try:
        with z.repl(clean=False) as r:
            r.run("import gc\ngc.collect()")
            free, big = Z.internal_heap(r.eval("__import__('esp32').idf_heap_info(%d)"
                                               % Z.INTERNAL_HEAP))
            z.take("zero internal free idle", free / 1024.0)
            z.take("zero internal largest idle", big / 1024.0)
            r.clean()
            z.before_tree, z.before_files = _snapshot(r)
            had = z.before_files.get(STORE + "/system/password")
            if had and had.startswith(b"$moy2$"):
                z.password = z.env_password
            else:
                from runtime.system import ssh_service
                z.password = _bench_password()
                r.mkdirs(STORE + "/system")
                r.write(STORE + "/system/password",
                        (ssh_service.hashed(z.password, os.urandom(16).hex()) + "\n").encode())
        z.served_at = z.url
        yield z
    finally:
        try:
            with z.repl() as r:
                _give_back(z, r)
        finally:
            _record(z)
            z.close()


def _record(z):
    out = os.environ.get("MOYBYTE_ZERO_PERF_OUT")
    if not out:
        return
    stamp = os.environ.get("MOYBYTE_ZERO_IMAGE") or "?"
    image = {"stamp": stamp, "flashed": bool(os.environ.get("MOYBYTE_ZERO_IMAGE"))}
    rec = Z.zero_record(z.name, z.taken, z.errors, image, secs=time.monotonic() - z.t0)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        json.dump(rec, f, indent=1)


# -- the browser ----------------------------------------------------------------


def _get(url, timeout=30):
    t = time.monotonic()
    with urllib.request.urlopen(url, timeout=timeout) as r:
        body, head = r.read(), r.headers
    return body, head, (time.monotonic() - t) * 1000


def _pack(z):
    with open(z.pack, "rb") as f:
        data = f.read()
    return hashlib.sha256(data[4096:]).hexdigest(), hashlib.sha256(data).hexdigest()


def _mirrors(zero):
    """The mirrors the loader the board serves names, in its order."""
    page = gzip.decompress(_get(zero.url + "/")[0]).decode()
    return json.loads(re.search(r"\}\)\((\[.*?\])\)\.catch", page, re.S).group(1))


@pytest.fixture(scope="module")
def mirror(zero):
    """For an online board, this worktree's serve.py on the port of the
    mirror on this machine the image names (gen_web_blob's DEV_PORT, unless
    the build was given MOYBYTE_WEB_MIRRORS), or the one already there when
    it serves this pack."""
    if not zero.online:
        yield
        return
    here = "http://%s:" % gen_web_blob.lan_address()
    mine = [m for m in _mirrors(zero) if m.startswith(here)]
    assert mine, "the image names no mirror on this machine (%s...)" % here
    port = int(mine[0][len(here):].split("/", 1)[0])
    page, _whole = _pack(zero)
    url = "http://127.0.0.1:%d/console/%s.pack" % (port, page)
    server = None
    try:
        urllib.request.urlopen(url, timeout=2).read()
    except urllib.error.HTTPError:
        pytest.fail("port %d serves another tree's pack: stop that serve.py, or "
                    "build with MOYBYTE_WEB_MIRRORS naming another port" % port)
    except OSError:
        server = subprocess.Popen([sys.executable, "serve.py", str(port),
                                   "dist"], cwd=str(RUNNER),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        for _ in range(100):
            try:
                urllib.request.urlopen(url, timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            server.terminate()
            pytest.fail("serve.py did not serve this tree's pack (is dist/ the one "
                        "the image was built from?)")
    try:
        yield
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=10)


def _scrub(text, z):
    return text.replace(z.password, "***") if z.password else text


def _scenario(out, steps, query, boot_ms=120000):
    out.mkdir(parents=True, exist_ok=True)
    path = out / "scenario.json"
    path.write_text(json.dumps({"query": query, "boot_ms": boot_ms, "steps": steps}))
    return path


def _browse(z, base, steps, out, query="?handheld=1&dev=1", timeout=600, boot_ms=120000,
            env=None, profile=None, on_line=None, check=True):
    """browsershot over `steps` against `base`: its output, scrubbed.
    `env` adds to its environment, `profile` keeps its Chrome profile (a
    browser that stays paired), `on_line(line)` sees each line as it comes
    (the board's side of a step the page waits on), `check` fails the test
    on a failed step."""
    path = _scenario(out, steps, query, boot_ms)
    env = dict(os.environ, MOY_BASE=base, **(env or {}))
    if profile is not None:
        env["MOY_PROFILE"] = str(profile)
    lines = []
    proc = subprocess.Popen(["node", "browsershot.mjs", str(path), str(out)],
                            cwd=str(RUNNER), env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    end = time.monotonic() + timeout
    try:
        for line in proc.stdout:
            lines.append(line)
            if on_line is not None:
                on_line(line)
            if time.monotonic() > end:
                break
        proc.wait(timeout=max(1, end - time.monotonic()))
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
        path.unlink()
    text = _scrub("".join(lines), z)
    print(text[-4000:])
    if check:
        assert proc.returncode == 0, text[-3000:]
        assert "STEP FAILED" not in text, text[-3000:]
    return text


def _tagged(text, tag):
    """The JSON a `js` step returned as "<tag> <json>", the last of them."""
    found = None
    for line in text.splitlines():
        m = re.search(r'js -> "%s (.*)"$' % re.escape(tag), line.strip())
        if m:
            found = json.loads(json.loads('"%s"' % m.group(1)))
    return found


def sign_in(z):
    """The steps that type the board's password where the page asks for it,
    then wait for its sync to be live. The password is read from nowhere
    the page prints, and a failing step names no step's text."""
    pw = json.dumps(z.password)
    return [
        {"waitFor": "(function () { var p = document.getElementById('pin'); "
                    "var s = document.getElementById('s'); return !!(p && "
                    "getComputedStyle(p).display == 'flex') || !!(s && "
                    "s.textContent == 'live'); })()", "timeout": 120000},
        {"js": "(function () { var p = document.getElementById('pin'), "
               "f = document.getElementById('pinf'), b = document.getElementById('pinb'); "
               "if (!p || !f || !b || getComputedStyle(p).display != 'flex') return 'paired'; "
               "f.value = %s; b.click(); return 'typed'; })()" % pw},
        {"waitFor": "(function () { var s = document.getElementById('s'); "
                    "return !!(s && s.textContent == 'live'); })()", "timeout": 120000},
    ]


def _needs_password(z):
    if not z.password:
        pytest.skip("%s has a password and MOYBYTE_%s_PASSWORD is not set"
                    % (z.name, z.name.upper()))


# -- setup over the cable ---------------------------------------------------------


def _bench_network():
    path = os.environ.get("MOYBYTE_BENCH_WIFI")
    if not path:
        return None
    with open(path) as f:
        nets = json.load(f).get("networks", [])
    want = os.environ.get("MOYBYTE_BENCH_SSID")
    for n in nets:
        if not want or n.get("ssid") == want:
            return n["ssid"], n.get("password") or ""
    return None


@pytest.mark.skipif(not os.environ.get("MOYBYTE_BENCH_WIFI"),
                    reason="MOYBYTE_BENCH_WIFI not set (a wifi.json of the bench network)")
def test_improv_over_the_cable_joins_a_board_with_no_network(zero):
    """Its networks saved and cleared, the board hosts its setup access point;
    an Improv join over the cable puts it on the bench network and answers
    with its URL once it serves; its own networks then go back, and it serves
    on the network it served on."""
    net = _bench_network()
    assert net, "MOYBYTE_BENCH_WIFI names no network %s" % (
        os.environ.get("MOYBYTE_BENCH_SSID") or "")
    ssid, password = net
    saved = zero.before_files.get(STORE + "/wifi.json")
    try:
        with zero.repl(then=SETUP) as r:
            r.remove(STORE + "/wifi.json")
            r.run("import moy_net\nmoy_net.wifi_disconnect()")
        imp = Z.Improv(zero.b.ser)
        st, _urls = imp.state()
        assert st == 0x02, "the board in setup answers READY, not %r" % st
        st, urls, secs, err = imp.join(ssid, password)
        zero.take("zero improv join", secs * 1000.0)
        print("%s: Improv joined %r in %.1f s: %s" % (zero.name, ssid, secs,
                                                     [Z.bare(u) for u in urls]))
        assert err is None, "the join failed with Improv error %d" % err
        assert st == 0x04, "the board answers PROVISIONED, not %r" % st
        assert urls and urls[0].startswith("http://") and "#id=" in urls[0], \
            [Z.bare(u) for u in urls]
        assert any(u.startswith("http://") and ".local/" in u for u in urls[1:]), \
            [Z.bare(u) for u in urls]
    finally:
        with zero.repl() as r:
            if saved is None:
                r.remove(STORE + "/wifi.json")
            else:
                r.write(STORE + "/wifi.json", saved)
            r.run("import moy_net\nmoy_net.wifi_disconnect()")
    assert zero.url == zero.served_at, "back on its network at %s, not %s" % (
        zero.url, zero.served_at)


# -- the browser console ------------------------------------------------------------


def test_sync_names_the_pack_the_image_names(zero):
    """GET /sync carries both digests of the pack this build wrote beside
    the image; `local` says whether the board serves its copy: the C3, whose
    console is online, keeps none."""
    page, whole = _pack(zero)
    doc = json.loads(_get(zero.url + "/sync")[0])
    assert doc == {"sync": 1, "page": page, "pack": whole,
                   "local": 0 if zero.online else 1}


def test_the_root_and_what_a_page_load_costs_the_board(zero):
    """`/` is gzipped: on an online board the loader, never cached, naming
    this machine's serve.py first; on the XIAO the console's page. The board
    serves it inside its loop, so its serving time is the stall a page load
    costs (#256)."""
    body, head, _ms = _get(zero.url + "/")
    assert head.get("Content-Encoding") == "gzip"
    page = gzip.decompress(body).decode()
    if zero.online:
        assert "no-cache" in head.get("Cache-Control")
        mirrors = _mirrors(zero)
        assert mirrors[-1] == gen_web_blob.SITE_MIRROR and len(mirrors) == 2, mirrors
    else:
        assert "<canvas id=cv" in page, "the root is the console's page"
    for path, metric in (("/", "zero page root"), ("/sync", "zero page sync")):
        ms = [_get(zero.url + path)[2] for _ in range(10)]
        zero.take(metric, statistics.median(ms), ms)
        print("%s %s: %d B, served in %.0f ms median, %.0f ms max over 10"
              % (zero.name, path, len(body) if path == "/" else 0,
                 statistics.median(ms), max(ms)))


BOOTED = "window.__moyState().then(function (s) { return s && s.stack ? " \
         "Math.round(performance.now()) : 0; })"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_chrome_boots_the_console(zero, mirror, tmp_path):
    """Signed in, the console boots in Chrome, then again on a reload: on an
    online board the first from this machine's serve.py, checked, and the
    reload from this origin's cache, over the IP and over `.local` (§11). The
    reload's boot, to the console's first state, is the page's boot cost. A
    board with a password boots no console in a browser it has not paired."""
    _needs_password(zero)
    steps = [{"js": "'FIRST ' + JSON.stringify({boot: window.moyBoot || null})"}] + \
        sign_in(zero) + [{"waitFor": BOOTED, "timeout": 120000},
             {"js": "location.reload(), 1"},
             {"waitFor": BOOTED, "timeout": 120000},
             {"js": "'BOOT ' + JSON.stringify({boot: window.moyBoot || null})"}]
    for name, base in (("ip", zero.url), ("local", zero.local)):
        if base is None:
            continue
        out = _browse(zero, base, steps, tmp_path / name)
        boot = _tagged(out, "BOOT")
        took = [float(v) for v in re.findall(r"waitFor -> (\d+)", out)]
        assert len(took) == 2 and all(took), "the console booted twice: %s" % took
        if name == "ip":
            zero.take("zero page reload boot", took[-1], took[-1:])
        if zero.online:
            first = _tagged(out, "FIRST")
            assert first and first["boot"]["from"].startswith("http://"), first
            assert boot and boot["boot"] and boot["boot"]["from"] == "cache", boot


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_console_signs_in_and_syncs_a_cart(zero, mirror, tmp_path):
    """Booted, the console pairs with the password, makes a cart through the
    real UI, and after a reload (the board's pull) the shelf it pulled holds
    it."""
    _needs_password(zero)
    steps = sign_in(zero) + [
        {"wait": 1500}, {"click": [117, 9]}, {"wait": 1500},
        {"click": [160, 100]}, {"wait": 8000},
        {"js": "location.reload(), 1"},
        {"waitFor": "document.getElementById('s').textContent == 'live'", "timeout": 120000},
        {"js": "pzAsk(), 1"}, {"wait": 1000},
        {"js": "Array.from(pzC.options).map(function (o) { return o.value; }).join(',')"},
    ]
    out = _browse(zero, zero.url, steps, tmp_path / "sync")
    assert "local.new_cart.moy" in out.rsplit("js ->", 1)[-1], out[-2000:]


# -- the claim: setup's password ----------------------------------------------------------


def _ssh_banner(z, timeout=3.0):
    """The SSH server's first line at the board's port 22, or None when
    nothing answers there."""
    import socket
    host = z.url.split("//", 1)[1].split("/", 1)[0].split(":", 1)[0]
    try:
        with socket.create_connection((host, 22), timeout=timeout) as s:
            s.settimeout(timeout)
            return s.recv(64).split(b"\r\n", 1)[0].decode(errors="replace")
    except OSError:
        return None


# What the page's card and the worker's answers did from the password's
# submit on, in ms: the card's changes [ms, class, heading, line, the card's
# display, the field's], `claimed`, `key`, and an unload, which a pairing
# that goes on with the boot never makes.
CLAIM_WATCH = """(function () {
  var t0 = Date.now(), T = {t0: t0, cards: []}, last = "";
  function keep() { try { sessionStorage.setItem('moyClaim', JSON.stringify(T)); } catch (e) {} }
  function card() { var p = document.getElementById('pin'), h = document.getElementById('pinh'),
      m = document.getElementById('pinm'), r = document.getElementById('pinr');
    var c = [p.className, h ? h.textContent : '', m.textContent,
             getComputedStyle(p).display, getComputedStyle(r).display];
    var k = JSON.stringify(c);
    if (k != last) { last = k; T.cards.push([Date.now() - t0].concat(c)); keep(); }
    return c; }
  WORKER.addEventListener('message', function (e) {
    var t = e.data && e.data.t;
    if ((t == 'claimed' || t == 'key' || t == 'pair') && !(t in T)) { T[t] = Date.now() - t0; keep(); } });
  addEventListener('pagehide', function () { T.unload = Date.now() - t0; card(); keep(); });
  setInterval(card, 50);
  var f = document.getElementById('pinf'), b = document.getElementById('pinb');
  f.value = %s; b.click();
  return 'CARD ' + JSON.stringify(card());
})()"""


def test_a_claim_sets_the_password_and_ssh_answers_at_once(zero, mirror, tmp_path):
    """With no password the board serves no SSH. The cable's fresh claim
    (Improv's 0xF0) opens the console on the URL it answers, whose prompt
    chooses the password: from the submit the card says what it does (never a
    bare prompt) while the board's curve runs, the console signs in without
    loading the page again, and the SSH server answers at once, with no
    reboot. The steps' times are the setup's: the page to its prompt, then
    from the submit the claim, the pairing and the console live."""
    pw = zero.password or _bench_password()
    with zero.repl() as r:
        r.remove(STORE + "/system/password")
    assert _ssh_banner(zero) is None, "SSH answers a board with no password"
    urls, err = Z.Improv(zero.b.ser).claim()
    assert err is None and urls and "&claim=" in urls[0], [Z.bare(u) for u in urls]
    frag = urls[0].split("#", 1)[1]
    zero.password = pw
    steps = [
        {"waitFor": "(function () { var p = document.getElementById('pinp'); "
                    "return !!p && getComputedStyle(document.getElementById('pin')).display "
                    "== 'flex' && p.textContent.indexOf('Choose') == 0 && "
                    "Math.round(performance.now()); })()", "timeout": 120000},
        {"js": CLAIM_WATCH % json.dumps(pw)},
        {"waitFor": "document.getElementById('s').textContent == 'live'", "timeout": 120000},
        {"js": "'TIMES ' + JSON.stringify({t: JSON.parse(sessionStorage.getItem('moyClaim')), "
               "live: Date.now()})"},
    ] + _get_carts_steps()
    log = []
    out = _browse(zero, zero.url, steps, tmp_path / "claim",
                  query="?handheld=1&start=1#" + frag, boot_ms=1000,
                  on_line=lambda _l: log.extend(_board_lines(zero)))
    took = [float(v) for v in re.findall(r"waitFor -> (\d+)", out)]
    times = _tagged(out, "TIMES")
    t = times["t"]
    live = times["live"] - t["t0"]
    split = {"prompt": took[0] if took else None, "claimed": t.get("claimed"),
             "key": t.get("key"), "live": live}
    print("%s: claim, from the page's load to its prompt, then from the submit (ms): %s"
          % (zero.name, json.dumps(split)))
    print("%s: the card from the submit: %s" % (zero.name, json.dumps(t["cards"])))
    zero.take("zero claim to live", float(live))
    asks = [c for c in t["cards"] if c[4] == "flex" and c[5] != "none"]
    assert not asks, "the card asked for something after the submit: %s" % asks
    assert t.get("claimed") and t.get("key") and "pair" not in t, t
    assert "unload" not in t, "the pairing loaded the page again"
    banner = _ssh_banner(zero)
    assert banner and banner.startswith("SSH-2.0"), \
        "SSH does not answer after the claim set the password: %r" % banner
    _get_carts_listed(zero, out, log)


# What Get Carts is, opened on the page signed in: its state a while after it
# opened, the shelves' fetch run (the page lists them itself on an online
# board, carts_link.BoardCheck).
GET_CARTS = "moybyte.get_carts.moy"
GET_CARTS_TITLE = "Get Carts"
BOARD_TROUBLE = re.compile(r"Traceback|MemoryError|out of memory|Errno|refused|abort|panic",
                           re.I)


def _get_carts_steps():
    """The steps that open Get Carts on the signed-in page (its key kept,
    so the load signs in unasked), wait for it to list, and report."""
    return [
        {"js": "location.search = '?handheld=1&dev=1&cart=%s', 1" % GET_CARTS},
        {"wait": 3000},
        {"waitFor": "document.getElementById('s').textContent == 'live'", "timeout": 120000},
        {"waitFor": "window.__moyState().then(function (s) { return s.cart == '%s'; })"
                    % GET_CARTS_TITLE, "timeout": 60000},
        {"wait": 20000},
        {"js": "window.__moyState().then(function (s) { return 'GETCARTS ' + JSON.stringify("
               "{cart: s.cart, error: s.cart_error, notice: s.notice, screen: s.screen}); })"},
        {"shot": "get_carts"},
    ]


def _board_lines(z, secs=0.02):
    """The board's serial lines that came since the last read (its log)."""
    try:
        return [ln for ln in z.b.drain(secs) if ln.strip()]
    except Exception:  # noqa: BLE001 -- a port mid-reset reads nothing
        return []


def _get_carts_listed(z, out, log):
    """Get Carts opened and stayed up with no error, and the board's log
    while it listed says nothing went wrong."""
    got = _tagged(out, "GETCARTS")
    trouble = [ln for ln in log if BOARD_TROUBLE.search(ln)]
    print("%s: Get Carts %s; the board's lines meanwhile: %s" % (z.name, got, log[-15:]))
    assert got and got["cart"] == GET_CARTS_TITLE, "Get Carts did not open: %s" % got
    assert not got["error"] and not got["notice"], "Get Carts says: %s" % got
    assert not trouble, "the board's log while Get Carts listed: %s" % trouble


# -- the live socket --------------------------------------------------------------------


LIVE = ("window.__moyState().then(function (s) { return '%s ' + JSON.stringify("
        "{live: s.live && {opens: s.live.opens, drops: s.live.drops, rtt: s.live.rtt}, "
        "link: s.link}); })")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_live_socket_answers_without_power_save(zero, mirror, tmp_path):
    """The page's echo over its live socket, a beat a second: the median is
    far under the ~100 ms the station's power save cost it. The board's
    internal RAM is read while the page still holds the socket."""
    _needs_password(zero)
    steps = sign_in(zero) + [
        {"waitFor": "window.__moyState().then(function (s) { return !!(s.live && "
                    "s.live.rtt.length >= %d); })" % RTT_BEATS,
         "timeout": (RTT_BEATS + 60) * 1000},
        {"js": LIVE % "RTT"},
        {"wait": 25000},
        {"js": LIVE % "END"},
    ]
    path = _scenario(tmp_path / "live", steps, "?dev=1&desktop=1")
    proc = subprocess.Popen(["node", "browsershot.mjs", str(path), str(tmp_path / "live")],
                            cwd=str(RUNNER), env=dict(os.environ, MOY_BASE=zero.url),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines, heap, live, log = [], None, None, []
    try:
        for line in proc.stdout:
            lines.append(line)
            if heap is None and 'js -> "RTT ' in line:
                log = [ln for ln in zero.b.drain(0.5) if LIVE_LOG.search(ln)]
                with zero.repl(clean=False) as r:
                    r.run("import gc\ngc.collect()")
                    heap = Z.internal_heap(r.eval("__import__('esp32').idf_heap_info(%d)"
                                                  % Z.INTERNAL_HEAP))
                    live = r.eval("__import__('moy_net').live_stats()")
        proc.wait(timeout=120)
    finally:
        if proc.poll() is None:
            proc.kill()
        path.unlink()
    out = _scrub("".join(lines), zero)
    print(out[-3000:])
    got = _tagged(out, "RTT")
    assert got and got["live"], "the page opened no live socket:\n" + out[-2000:]
    samples = got["live"]["rtt"]
    assert samples, ("the socket echoed nothing: the page's opens %s, drops %s, link %s; "
                     "the board's live_stats %s, internal RAM %s; its log: %s") % (
        got["live"]["opens"], got["live"]["drops"], got["link"], live, heap, log[-12:])
    med, p90 = Z.rtt(samples)
    zero.take("zero live rtt median", med, samples)
    zero.take("zero live rtt p90", p90, samples)
    if heap is not None and got["live"]["opens"]:
        zero.take("zero internal free live", heap[0] / 1024.0)
        zero.take("zero internal largest live", heap[1] / 1024.0)
    print("%s live echo over %d beats: median %.1f ms, p90 %.1f ms, max %.1f ms; "
          "internal RAM with the socket open: %s"
          % (zero.name, len(samples), med, p90, max(samples), heap))
    assert med < RTT_MEDIAN_MS, "median echo %.1f ms: the station's power save is on?" % med
    assert heap is not None, "the board's RAM was not read with the socket open"


TERM = ("window.__moyState().then(function (s) { return '%s ' + JSON.stringify("
        "{term: s.term, live: s.live && {opens: s.live.opens, drops: s.live.drops}}); })")


def test_the_page_s_terminal_runs_the_board_s_shell(zero, mirror, tmp_path):
    """The page's Terminal runs the board's shell (on a Zero, over its live
    socket's terminal channel: native/moy_tty/moy_tty_live.c), and the
    board's internal RAM is read while the page holds it open."""
    _needs_password(zero)
    shell = "ln => /\\$\\s*$/.test(ln)"
    steps = sign_in(zero) + [
        {"waitFor": "window.__moyState().then(function (s) { return !!(s.term && "
                    "s.term.some(%s)); })" % shell, "timeout": 60000},
    ] + [{"key": c} for c in "echo zero-$((6*7))"] + [
        {"key": "Enter"},
        {"waitFor": "window.__moyState().then(function (s) { return s.term.some("
                    "function (ln) { return ln.indexOf('zero-42') >= 0; }); })",
         "timeout": 30000},
        {"js": TERM % "TERM"},
        {"wait": 25000},
    ]
    path = _scenario(tmp_path / "term", steps, "?dev=1&desktop=1&cart=Terminal")
    proc = subprocess.Popen(["node", "browsershot.mjs", str(path), str(tmp_path / "term")],
                            cwd=str(RUNNER), env=dict(os.environ, MOY_BASE=zero.url),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines, heap = [], None
    try:
        for line in proc.stdout:
            lines.append(line)
            if heap is None and 'js -> "TERM ' in line:
                with zero.repl(clean=False) as r:
                    r.run("import gc\ngc.collect()")
                    info = r.eval("__import__('esp32').idf_heap_info(%d)" % Z.INTERNAL_HEAP)
                    heap = Z.internal_heap(info) + (sum(x[3] for x in info if x),)
        proc.wait(timeout=120)
    finally:
        if proc.poll() is None:
            proc.kill()
        path.unlink()
    out = _scrub("".join(lines), zero)
    got = _tagged(out, "TERM")
    assert got and any("zero-42" in ln for ln in got["term"]), out[-3000:]
    assert heap is not None, "the board's RAM was not read with the Terminal open"
    zero.take("zero internal free terminal", heap[0] / 1024.0)
    zero.take("zero internal largest terminal", heap[1] / 1024.0)
    zero.take("zero internal low-water terminal", heap[2] / 1024.0)
    print("%s with the page and its Terminal open: internal %d free, %d largest, "
          "%d low-water; live socket %s" % (zero.name, heap[0], heap[1], heap[2], got["live"]))


# -- the board's Wi-Fi from its page -------------------------------------------------------


WRONG_PASSWORD = "not-the-bench-password"


def _wifi_browse(z, base, steps, out, secrets):
    """`_browse` with the console's Settings -> Wi-Fi open first, every one of
    `secrets` (the bench passwords) scrubbed from what it prints."""
    from test_web_zero_wifi_e2e import ENTER, _keys, _panel
    import web_e2e
    steps = (sign_in(z) + [{"wait": 2000}] + web_e2e.menu_pick("Settings")
             + [{"wait": 1500}] + _keys(ENTER)
             + [_panel("p.nets.length > 0 && p.focus", 60000)] + steps)
    path = _scenario(out, steps, "?handheld=1&dev=1")
    try:
        run = subprocess.run(["node", "browsershot.mjs", str(path), str(out)],
                             cwd=str(RUNNER), env=dict(os.environ, MOY_BASE=base),
                             capture_output=True, text=True, timeout=900)
    finally:
        path.unlink()
    text = _scrub(run.stdout + run.stderr[-500:], z)
    for pw in secrets:
        if pw:
            text = text.replace(pw, "***")
    print(text[-4000:])
    assert run.returncode == 0, text[-3000:]
    assert "STEP FAILED" not in text, text[-3000:]
    return text


def _where(url):
    """The board's page at `url` (its .local name), as an address this
    machine reaches: the name resolved here."""
    import socket
    import urllib.parse
    u = urllib.parse.urlsplit(url)
    ip = socket.gethostbyname(u.hostname)
    return "http://%s%s" % (ip, ":%d" % u.port if u.port else "")


def test_the_page_manages_the_boards_wifi(zero, mirror, tmp_path):
    """From the console's own Wi-Fi panel on the board's page: a saved network
    forgotten and saved again (nothing dropped); with a second saved network
    in range, a move to it with a wrong password (the board comes back and the
    page says so), a move to it that works, and a move back. The passwords are
    the board's own saved ones, read over the cable and never printed."""
    from test_web_zero_wifi_e2e import ENTER, _forget, _keys, _move, _panel, _say
    _needs_password(zero)
    doc = json.loads((zero.before_files.get(STORE + "/wifi.json") or b"{}").decode())
    saved = {n["ssid"]: n.get("password") or "" for n in doc.get("networks", []) if n.get("ssid")}
    assert saved, "%s has no saved network" % zero.name
    secrets = list(saved.values()) + [WRONG_PASSWORD]
    look = _tagged(_wifi_browse(zero, zero.url, [_say("LOOK")], tmp_path / "look", secrets),
                   "LOOK")
    on = look["w"][1]
    assert look["w"][0] and on in saved, "the page's station says %s" % (look["w"],)
    others = [s for s in saved if s != on and s in look["p"]["nets"]]
    x = others[0] if others else on
    steps = (_forget(x) + [_panel("p.known.indexOf(%s) < 0" % json.dumps(x)), {"wait": 1500},
                           _say("FORGOT")])
    if others:
        steps += (_move(x, WRONG_PASSWORD, 2)
                  + [_panel("p.card && p.card[0] == 'tell'", 90000), _say("FAILED")]
                  + _keys(ENTER) + [_panel("!p.card", 5000)]
                  + _move(x, saved[x], 1))
    else:
        from test_web_zero_wifi_e2e import _focus, _typed
        steps += (_focus(ssid=x) + _keys(ENTER) + [_panel("p.pick", 5000)]
                  + _typed(saved[x]) + _keys(ENTER))
    steps += [_panel("p.known.indexOf(%s) >= 0 && !p.card" % json.dumps(x)), {"wait": 1500},
              _say("SAVED")]
    if others:
        steps += (_move(x, None, 1, card="switch")
                  + [{"waitFor": "window.__moyState().then(s => (window.__moyLinkCard && "
                                 "window.__moyLinkCard.go) || (s.wifi_panel && "
                                 "!s.wifi_panel.joining && s.wifi && s.wifi[1] == %s))"
                                 % json.dumps(x), "timeout": 90000},
                     {"wait": 1000}, _say("MOVED")])
    out = _wifi_browse(zero, zero.url, steps, tmp_path / "manage", secrets)
    forgot, saved_again = _tagged(out, "FORGOT"), _tagged(out, "SAVED")
    assert x not in forgot["p"]["known"], forgot
    assert forgot["w"][:2] == [True, on], "forgetting dropped the network: %s" % (forgot["w"],)
    assert x in saved_again["p"]["known"], saved_again
    assert saved_again["w"][:2] == [True, on], saved_again["w"]
    if not others:
        print("%s: one saved network in range (%s): no move to make" % (zero.name, on))
        return
    failed = _tagged(out, "FAILED")
    assert failed["p"]["card"] == ["tell", "Still on %s" % on], failed
    assert failed["w"][:2] == [True, on], failed["w"]
    moved = _tagged(out, "MOVED")
    card = moved["link"]
    if card and card.get("go"):
        # This page lost the board, by design: it is where the card says.
        assert card["head"] == "the console moved to %s" % x, card
        assert card["bad"] is False, card
        base = _where(card["go"])
    else:
        assert moved["w"][:2] == [True, x], moved
        base = zero.url
    print("%s moved to %s (%s)" % (zero.name, x, "the page lost it" if base != zero.url
                                   else "the page still reaches it"))
    back = (_move(on, None, 1, card="switch")
            + [{"waitFor": "window.__moyState().then(s => (window.__moyLinkCard && "
                           "window.__moyLinkCard.go) || (s.wifi_panel && "
                           "!s.wifi_panel.joining && s.wifi && s.wifi[1] == %s))"
                           % json.dumps(on), "timeout": 90000},
               {"wait": 1000}, _say("BACK")])
    out = _wifi_browse(zero, base, back, tmp_path / "back", secrets)
    back = _tagged(out, "BACK")
    if not (back["link"] or {}).get("go"):
        assert back["w"][:2] == [True, on], back
    # ...and it answers where it served at the start.
    for _ in range(30):
        try:
            _get(zero.served_at + "/sync", timeout=5)
            break
        except OSError:
            time.sleep(2)
    else:
        pytest.fail("%s does not answer at %s after the move back" % (zero.name, zero.served_at))


# -- the terminal over SSH ------------------------------------------------------------------


# The bench folder of the SSH tests, in the folder a session starts in (the
# store's files), and the pipe's stream at most: 4 KB on a board without
# PSRAM, 1 MB with (native/moy_sh/moy_sh_sys.c, PIPE_MAX).
BENCH = "zbench"
PIPE_CAP = {"c3_zero": 4 * 1024, "xiao_zero": 1024 * 1024}
PIPE_SAID = re.compile(rb"pipe: (stream over|out of memory at) \d+ KB; write it to a file")


def _host(z):
    return z.url.split("//", 1)[1].split("/", 1)[0].split(":", 1)[0]


@pytest.fixture(scope="module")
def ssh(zero, tmp_path_factory):
    """The board's shell over SSH with the suite's password; the bench
    folder made empty for each test and removed after it (`_bench`)."""
    _needs_password(zero)
    assert (_ssh_banner(zero) or "").startswith("SSH-2.0"), \
        "SSH does not answer a board with a password"
    return Z.Ssh(_host(zero), zero.password, str(tmp_path_factory.mktemp("ssh")))


@contextlib.contextmanager
def _bench(ssh):
    ssh.run("rm -r %s; mkdir %s" % (BENCH, BENCH))
    try:
        yield
    finally:
        ssh.run("rm -r %s" % BENCH)


def _text_file(n, tag="line"):
    """`n` bytes of numbered lines of text."""
    out, i = b"", 0
    while len(out) < n:
        out += b"%s %05d of the zero bench file\n" % (tag.encode(), i)
        i += 1
    return out[:n - 1] + b"\n"


def _session(ssh, z):
    """A terminal session at its prompt, and the board's internal free RAM
    `free` reads in it."""
    t = ssh.term()
    assert t.expect(rb"\$ $", timeout=30), "no prompt over SSH: %r" % t.since(0)[-300:]
    return t, _free_live(t)


def _free_live(t):
    got = Z.free_internal((t.command("free") or b"").decode(errors="replace"))
    return got[2] if got else None


def _still_up(z, t):
    """The session answers a command, and the board its page's /sync."""
    said = t.command("echo still-here")
    assert t.alive() and said is not None and b"still-here" in said, \
        "the SSH session did not stay up: %r" % t.since(0)[-500:]
    assert json.loads(_get(z.url + "/sync")[0]).get("sync") == 1, "the board left the network"


def _heap(z, label):
    """The board's internal RAM, free and its largest block, read over the
    cable (the store host stopped, its heap collected; a reset after):
    (free, largest) bytes."""
    with z.repl(clean=False) as r:
        r.run("import gc\ngc.collect()")
        free, big = Z.internal_heap(r.eval("__import__('esp32').idf_heap_info(%d)"
                                           % Z.INTERNAL_HEAP))
    print("%s %s: internal RAM free %.1f KB, largest block %.1f KB"
          % (z.name, label, free / 1024.0, big / 1024.0))
    return free, big


def _editor(t, line, keys, timeout=20.0):
    """`line` (an editor on a file) typed, then `keys` once its screen is
    up: None once it is back at the prompt, else what it said instead."""
    at = t.mark()
    t.send(line.encode() + b"\r")
    up = t.expect(rb"\x1b\[\?1049h|\$ $", at, timeout)
    if up is None or up.group(0) != b"\x1b[?1049h":
        return re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", t.since(at)).decode(errors="replace")
    time.sleep(0.5)
    for k in keys:
        t.send(k, 0.3)
    back = t.expect(rb"\x1b\[\?1049l[^\r\n]*\$ $", at, timeout)
    return None if back else "did not come back to the prompt: %r" % t.since(at)[-300:]


EDITS = (
    # (the editor's line, the keys typed into it, what the file holds after
    # from what it held: None, a new file)
    ("edit %s/new_edit.txt", (b"hello edit\r", b"\x13", b"\x18"), lambda old: b"hello edit\n"),
    ("vi %s/new_vi.txt", (b"ihello vi\r\x1b", b":wq\r"), lambda old: b"hello vi\n"),
    ("edit %s/big.txt", (b"EDIT\r", b"\x13", b"\x18"), lambda old: b"EDIT\n" + old),
    ("vi %s/big.txt", (b"gg", b"OTOP\x1b", b":wq\r"), lambda old: b"TOP\n" + old),
)


def test_edit_and_vi_save_what_was_typed_over_ssh(zero, ssh):
    """`edit` and `vi` over SSH, each on a new file and on a ~20 KB one:
    text typed in, saved, the editor quit, and the file holds what was
    typed (its md5sum, read in the same session: a second session would
    end this one). The session stays up throughout and the board on the
    network;
    its internal RAM is read in the session before and after, and over the
    cable once it ends."""
    big = _text_file(20 * 1024)
    failed = []
    with _bench(ssh):
        assert ssh.run("cat > %s/big.txt" % BENCH, stdin=big)[0] == 0
        t, free0 = _session(ssh, zero)
        try:
            held = big
            for line, keys, want in EDITS:
                line = line % BENCH
                path = line.split()[1]
                said = _editor(t, line, keys)
                if said is not None:
                    failed.append("%s: %s" % (line, said.strip()[-200:]))
                    continue
                expect = want(held if path.endswith("big.txt") else None)
                sums = t.command("md5sum %s; wc -c %s" % (path, path)) or b""
                if hashlib.md5(expect).hexdigest().encode() not in sums:
                    failed.append("%s: the file is not what was typed (%d bytes "
                                  "expected): %r" % (line, len(expect), sums[-200:]))
                elif path.endswith("big.txt"):
                    held = expect
            free1 = _free_live(t)
            _still_up(zero, t)
        finally:
            t.close()
    print("%s: internal RAM free in the session %s -> %s; failed: %s"
          % (zero.name, free0, free1, failed))
    _heap(zero, "after edit and vi")
    assert not failed, "\n".join(failed)


def test_a_pipe_carries_a_file_and_says_where_it_stops(zero, ssh):
    """`cat ... | wc -c` counts a stream under the pipe's cap whole; past the
    cap the pipe says so (the message that tells the user to write it to a
    file) and the session goes on. The stream is one file `cat` names as
    often as it takes, so a 1 MB cap needs no 1 MB file in the store."""
    cap = PIPE_CAP[zero.name]
    part = _text_file(min(cap - 1024, 32 * 1024))
    under = max(1, (cap - 1024) // len(part))
    over = cap // len(part) + 1
    cat = lambda n: "cat" + (" %s/part.txt" % BENCH) * n  # noqa: E731
    with _bench(ssh):
        assert ssh.run("cat > %s/part.txt" % BENCH, stdin=part)[0] == 0
        rc, out, err = ssh.run("%s | wc -c" % cat(under))
        assert (rc, out.strip(), err) == (0, str(len(part) * under).encode(), b""), \
            (rc, out, err)
        rc, out, err = ssh.run("%s | wc -c" % cat(over))
        print("%s: %d bytes through a pipe capped at %d: %r %r"
              % (zero.name, len(part) * over, cap, out, err))
        assert PIPE_SAID.search(out + err), "a stream past the cap: %r %r" % (out, err)
        assert int(out.strip().rsplit(b"\n", 1)[-1] or 0) <= cap, out
        t, free0 = _session(ssh, zero)
        try:
            said = t.command("%s | wc -c" % cat(over))
            assert said is not None and PIPE_SAID.search(said), said
            free1 = _free_live(t)
            _still_up(zero, t)
        finally:
            t.close()
    print("%s: internal RAM free in the session %s -> %s" % (zero.name, free0, free1))
    _heap(zero, "after the pipes")


DEEP = 10            # folders, one inside the next
PER_LEVEL = 3        # files in each


def test_find_du_and_rm_walk_a_deep_folder(zero, ssh):
    """A folder ten deep with three files in each, and at the bottom a file
    with a user's own `.bak` beside it, a file like any other:
    `find` names every file and finds one by name, `du -s` counts them,
    `rm -r` takes it all, and the session stays up."""
    with _bench(ssh):
        make = ("d=%s/deep; mkdir $d; for i in %s; do d=$d/d$i; mkdir $d; "
                "for j in %s; do echo level $i file $j > $d/f${i}_$j.txt; done; done; "
                "echo note > $d/notes.txt; echo older > $d/notes.txt.bak"
                % (BENCH, " ".join(str(i) for i in range(1, DEEP + 1)),
                   " ".join(str(j) for j in range(1, PER_LEVEL + 1))))
        rc, _out, err = ssh.run(make)
        assert rc == 0, err
        t, free0 = _session(ssh, zero)
        try:
            files = t.command("find %s/deep -type f | wc -l" % BENCH)
            assert files is not None and files.strip() == str(DEEP * PER_LEVEL + 2).encode(), \
                files
            one = t.command("find %s/deep -name 'f7_2.txt'" % BENCH)
            assert one is not None and one.strip().endswith(b"/d7/f7_2.txt"), one
            du = t.command("du -s %s/deep" % BENCH)
            assert du is not None and re.match(rb"\s*\d+\s+\S*deep", du.strip()), du
            gone = t.command("rm -r %s/deep; echo rc=$?; ls %s" % (BENCH, BENCH))
            assert gone is not None and b"rc=0" in gone and b"deep" not in gone, gone
            free1 = _free_live(t)
            _still_up(zero, t)
        finally:
            t.close()
    print("%s: find/du/rm over %d files %d deep; internal RAM free %s -> %s"
          % (zero.name, DEEP * PER_LEVEL, DEEP, free0, free1))


def test_cat_of_a_64_kb_file_arrives_whole(zero, ssh):
    """64 KB of bytes over an exec arrive as they are, and 64 KB of text
    reaches a terminal session to its last line, which stays up."""
    data = os.urandom(64 * 1024)
    text = _text_file(64 * 1024, tag="row")
    last = text.rstrip(b"\n").rsplit(b"\n", 1)[-1]
    with _bench(ssh):
        assert ssh.run("cat > %s/c64.bin" % BENCH, stdin=data)[0] == 0
        assert ssh.run("cat > %s/c64.txt" % BENCH, stdin=text)[0] == 0
        t0 = time.monotonic()
        rc, got, err = ssh.run("cat %s/c64.bin" % BENCH)
        secs = time.monotonic() - t0
        assert rc == 0 and got == data, "cat over an exec: %d of %d bytes, %r" % (
            len(got), len(data), err)
        t, free0 = _session(ssh, zero)
        try:
            at = t.mark()
            t.send(b"cat %s/c64.txt\r" % BENCH.encode())
            assert t.expect(re.escape(last) + rb"\r\n[^\r\n]*\$ $", at, 120), \
                "the terminal did not get to the last line: %r" % t.since(at)[-300:]
            free1 = _free_live(t)
            _still_up(zero, t)
        finally:
            t.close()
    print("%s: 64 KB by cat over an exec in %.1f s; internal RAM free %s -> %s"
          % (zero.name, secs, free0, free1))
    _heap(zero, "after cat of 64 KB")


SSH_TAKEN = b"another session signed in; this one is closing"


def test_a_second_ssh_session_ends_the_first(zero, ssh, tmp_path):
    """Owner, 2026-11-25: one session at a time, the newest. A wrong
    password and a connection that never signs in (held past the server's
    30 s sign-in timeout) end nobody; a second session that signs in runs,
    and the first reads why it closes and is ended."""
    import socket
    a, _f = _session(ssh, zero)
    b = None
    try:
        assert b"one" in (a.command("echo one") or b"")
        wrong = Z.Ssh(_host(zero), "not-" + zero.password, str(tmp_path / "wrong"))
        rc, _o, _e = wrong.run("echo in", timeout=60)
        assert rc != 0, "a wrong password signed in"
        with socket.create_connection((_host(zero), 22), timeout=10):
            time.sleep(35)
        said = a.command("echo still-one")
        assert a.alive() and said is not None and b"still-one" in said, \
            "a session that did not sign in ended the one signed in: %r" % a.since(0)[-300:]
        b, _f = _session(ssh, zero)
        said = b.command("echo two")
        assert said is not None and b"two" in said, "the second session: %r" % b.since(0)[-300:]
        end = time.monotonic() + 20
        while a.alive() and time.monotonic() < end:
            time.sleep(0.2)
        print("%s: the first session %s once the second signed in: %r"
              % (zero.name, "ended" if not a.alive() else "ran on", a.since(0)[-200:]))
        assert not a.alive(), "the first session ran on beside the second"
        assert SSH_TAKEN in a.since(0), "the first session was not told why: %r" % \
            a.since(0)[-300:]
        _still_up(zero, b)
    finally:
        a.close()
        if b is not None:
            b.close()


# -- files and saves through the page ---------------------------------------------------------


PLAIN_MAIN = "def _init():\n    pass\n\ndef _update(dt):\n    pass\n\ndef _draw():\n    cls(1)\n"

# A game that keeps a count of its runs in pmem(0) and cells 1-8 from it: in
# Lua, which runs without the trust a Python cart asks the person for.
SAVES_LUA = """n = 0

function _init()
  n = pmem(0) + 1
  pmem(0, n)
  for i = 1, 8 do pmem(i, n * 1000 + i) end
end

function _update(dt)
end

function _draw()
  cls(n % 16)
end
"""


def _png(w, h):
    """A PNG of random pixels: bytes that do not compress, as a photo's."""
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + \
            struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + os.urandom(w * 3) for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b"")


def _bench_cart(tmp, stem, title, main=PLAIN_MAIN, files=None, lua=False):
    """A cart `zbench.<stem>.moy` (a Python one, or `lua`), packed as the
    archive the page imports under that name: (the archive's path, the
    folder it lands in, {file: bytes})."""
    from runtime.carts import moy_pack
    folder = "zbench.%s.moy" % stem
    src = tmp / "src" / folder
    src.mkdir(parents=True)
    content = {"manifest.json": json.dumps({
        "format": "moy-1", "version": 1, "title": title, "id": folder[:-4],
        "runtime": "lua" if lua else "python", "main": "main.lua" if lua else "main.py",
        "canvas": "128x128", "input": ["keyboard", "touch"],
        "moybyte": {"type": "game", "permissions": ["graphics", "input"]}},
        indent=1).encode(), "main.lua" if lua else "main.py": main.encode()}
    content.update(files or {})
    for name, data in content.items():
        (src / name).write_bytes(data)
    drop = tmp / "drop"
    drop.mkdir(exist_ok=True)
    archive = drop / folder
    moy_pack.pack(str(src), str(archive))
    return archive, folder, content


# The page's sync after a change: a batch the board took since `__ack0`
# was read, and none on its way.
ACK0 = {"js": "window.__moyState().then(function (s) { window.__ack0 = s.sync.acked; return 1; })"}
SYNCED = [
    {"wait": 3000},
    {"waitFor": "window.__moyState().then(function (s) { return !!(s.sync && "
                "s.sync.acked > window.__ack0 && !s.sync.busy); })", "timeout": 180000},
    {"wait": 5000},
    {"waitFor": "window.__moyState().then(function (s) { return !s.sync.busy; })",
     "timeout": 180000},
]
LIVE_NOW = {"waitFor": "document.getElementById('s').textContent == 'live'", "timeout": 120000}


def _import_steps(tag, synced=True):
    """The archive MOY_UPLOAD names imported through the page's import (the
    file a person picks or drops), then synced to the board."""
    return [
        {"file": "$MOY_UPLOAD", "as": "__up"},
        ACK0,
        {"js": "pzImport(new File([window.__up], window.__upName)), 1"},
        {"waitFor": "!!window.__moyImported", "timeout": 60000},
        {"js": "'%s ' + JSON.stringify(window.__moyImported)" % tag},
    ] + (SYNCED if synced else [])


def _open_steps(folder, title):
    return [ACK0, {"js": "WORKER.postMessage({t: 'open', cart: %s}), 1" % json.dumps(folder)},
            {"waitFor": "window.__moyState().then(function (s) { return s.cart == %s; })"
                        % json.dumps(title), "timeout": 60000},
            {"wait": 4000}] + SYNCED


SHELF = {"js": "(pzAsk(), new Promise(function (ok) { setTimeout(function () { ok('SHELF ' + "
               "JSON.stringify(Array.from(pzC.options).map(function (o) { return o.value; }))); "
               "}, 1500); }))"}
STATE = ("window.__moyState().then(function (s) { return '%s ' + JSON.stringify({cart: s.cart, "
         "stack: s.stack, screen: s.screen, error: s.cart_error, notice: s.notice, "
         "system: s.system, sync: s.sync, live: s.live && {opens: s.live.opens, "
         "drops: s.live.drops}}); })")
# What the page shows a person: every visible element's own text.
PAGE_SAYS = ("'%s ' + JSON.stringify({imported: window.__moyImported || null, "
             "s: document.getElementById('s').textContent, said: Array.prototype.slice.call("
             "document.querySelectorAll('body *')).filter(function (e) { return "
             "e.offsetParent !== null && !e.children.length && e.textContent.trim(); })"
             ".map(function (e) { return e.textContent.trim(); }).slice(0, 60)})")


def _remove(ssh, folder):
    """A bench cart taken off the board as its shell does (`rm -r` of its
    folder): (status, stdout, stderr)."""
    return ssh.run("rm -r %s/%s" % (CARTS, folder))


def _cat(ssh, path):
    rc, data, err = ssh.run("cat %s" % path)
    return data if rc == 0 else None


def _differs(ssh, folder, content):
    """The files of `content` the board's `folder` does not hold byte for byte."""
    return [n for n, data in content.items()
            if _cat(ssh, "%s/%s/%s" % (CARTS, folder, n)) != data]


EXPORT = ("(function () { window.__exp = null; pzDownload = function (name, buf) { "
          "var b = new Uint8Array(buf), s = ''; for (var i = 0; i < b.length; i += 0x8000) "
          "s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000)); "
          "window.__exp = JSON.stringify({name: name, b64: btoa(s)}); }; "
          "WORKER.postMessage({t: 'export', cart: %s}); return 1; })()")


def _exported(out, folder):
    """The files of the archive the page exported: {name: bytes}."""
    import base64
    import io
    import zipfile
    got = _tagged(out, "EXPORTED")
    assert got, "the page exported nothing:\n" + out[-1500:]
    z = zipfile.ZipFile(io.BytesIO(base64.b64decode(got["b64"])))
    return {n.split("/", 1)[1]: z.read(n) for n in z.namelist()
            if n.startswith(folder + "/") and not n.endswith("/")}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_cart_uploaded_from_the_page_reads_back_byte_exact(zero, mirror, ssh, tmp_path):
    """A `.moy` archive picked in the page's import (a cover of random
    pixels and 16 KB of text beside its code) lands on the board byte for
    byte; a browser that never saw it exports it back from the board's copy
    byte for byte; removed, the next page's shelf lacks it."""
    archive, folder, content = _bench_cart(
        tmp_path, "files", "Zero Bench Files",
        files={"cover.png": _png(64, 48), "notes.txt": _text_file(16 * 1024)})
    try:
        out = _browse(zero, zero.url, sign_in(zero) + _import_steps("IMPORTED"),
                      tmp_path / "up", env={"MOY_UPLOAD": str(archive)})
        said = _tagged(out, "IMPORTED")
        assert said and folder in said, "the page's import: %s" % said
        assert not _differs(ssh, folder, content), \
            "the board's copy differs: %s" % _differs(ssh, folder, content)
        steps = sign_in(zero) + [{"wait": 3000}, {"js": EXPORT % json.dumps(folder)},
                                 {"waitFor": "!!window.__exp", "timeout": 60000},
                                 {"js": "'EXPORTED ' + window.__exp"}]
        back = _exported(_browse(zero, zero.url, steps, tmp_path / "back"), folder)
        apart = [n for n in content if back.get(n) != content[n]]
        assert not apart, "the page's read-back differs in %s (it holds %s)" % (
            apart, sorted(back))
        # the store's backups of what it saved are its own: no listing shows one
        rc, ls, _e = ssh.run("ls -a %s/%s; find %s/%s" % (CARTS, folder, CARTS, folder))
        assert rc == 0 and b"moybak" not in ls, ls
        rc, _o, err = _remove(ssh, folder)
        assert rc == 0, "rm -r of the cart's folder: %r; the folder: %r" % (
            _o + err, ssh.run("ls -l %s/%s" % (CARTS, folder)))
        shelf = _tagged(_browse(zero, zero.url, sign_in(zero) + [{"wait": 3000}, SHELF],
                                tmp_path / "gone"), "SHELF")
        assert shelf is not None and folder not in shelf, shelf
    finally:
        _remove(ssh, folder)


def _pmem(ssh, folder, tmp):
    """The cart's pmem cells as the board keeps them, None with no record."""
    data = _cat(ssh, "%s/%s/pmem.bin" % (CARTS, folder))
    if data is None:
        return None
    d = tmp / ("pmem%d" % len(list(tmp.glob("pmem*"))))
    d.mkdir(parents=True)
    (d / "pmem.bin").write_bytes(data)
    from runtime.carts import moy_carts
    return moy_carts.load_pmem(str(d))


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_game_s_pmem_saves_are_back_after_a_reboot(zero, mirror, ssh, tmp_path):
    """A game run on the page writes its pmem cells; the board keeps them
    across a reboot, and the game run again on a new page reads them back
    (its count of runs goes on from them)."""
    title = "Zero Bench Saves"
    archive, folder, _c = _bench_cart(tmp_path, "saves", title, main=SAVES_LUA, lua=True)
    try:
        steps = sign_in(zero) + _import_steps("IMPORTED") + _open_steps(folder, title) + \
            [{"js": STATE % "RAN"}]
        out = _browse(zero, zero.url, steps, tmp_path / "run1", env={"MOY_UPLOAD": str(archive)})
        ran = _tagged(out, "RAN")
        assert ran and ran["cart"] == title and not ran["error"], ran
        first = _pmem(ssh, folder, tmp_path)
        zero.restart()
        kept = _pmem(ssh, folder, tmp_path)
        print("%s: pmem after the run %s, after the reboot %s"
              % (zero.name, first and first[:9], kept and kept[:9]))
        assert kept is not None and kept[:9] == [1] + [1000 + i for i in range(1, 9)], kept
        out = _browse(zero, zero.url, sign_in(zero) + [{"wait": 3000}] +
                      _open_steps(folder, title), tmp_path / "run2")
        again = _pmem(ssh, folder, tmp_path)
        print("%s: pmem after the second run %s" % (zero.name, again and again[:9]))
        assert again is not None and again[:9] == [2] + [2000 + i for i in range(1, 9)], \
            "the game did not read its cells back: %s" % (again and again[:9])
    finally:
        _remove(ssh, folder)


FILL = STORE + "/zbench_fill.bin"
FILL_SLACK = 4               # blocks left free: a pairing's keys and a batch's staging
FULL_WORDS = re.compile(r"full|no room|no space|out of space|storage|not enough", re.I)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_full_store_refuses_a_cart_says_so_and_corrupts_nothing(zero, mirror, tmp_path):
    """The store filled by a bench file to a few blocks, a cart imported on
    the page does not fit: the page tells the person (not a silent loss),
    no file of the store changes, none is left half-written, and the
    bench file and what landed go after."""
    _needs_password(zero)
    archive, folder, content = _bench_cart(tmp_path, "full", "Zero Bench Full",
                                           files={"cover.png": _png(128, 96)})
    with zero.repl() as r:
        tree0, files0 = _snapshot(r)
        bs, free = r.eval("(lambda s: (s[0], s[3]))(__import__('os').statvfs(%r))" % STORE)
        fill = max(0, free - FILL_SLACK) * bs
        r.run("f=open(%r,'wb')\nb=bytes(4096)\nn=%d\nwhile n>0:\n k=min(n,4096)\n"
              " f.write(b[:k])\n n-=k\nf.close()" % (FILL, fill), timeout=600)
        left = r.eval("__import__('os').statvfs(%r)[3]" % STORE)
    print("%s: the store filled with %d KB, %d blocks of %d B left"
          % (zero.name, fill // 1024, left, bs))
    log = []
    try:
        steps = sign_in(zero) + _import_steps("IMPORTED", synced=False) + \
            [{"wait": 30000}, {"js": PAGE_SAYS % "SAID"}, {"js": STATE % "STATE"},
             {"shot": "full"}]
        out = _browse(zero, zero.url, steps, tmp_path / "full", check=False,
                      env={"MOY_UPLOAD": str(archive)},
                      on_line=lambda _l: log.extend(_board_lines(zero)))
    finally:
        with zero.repl() as r:
            left_after = r.eval("__import__('os').statvfs(%r)[3]" % STORE)
            filled = r.eval("__import__('os').stat(%r)[6]" % FILL)
            r.remove(FILL)
            try:
                landed = r.tree(CARTS + "/" + folder)
            except Z.ReplError:
                landed = {}
            r.remove(CARTS + "/" + folder)
            tree1, files1 = _snapshot(r)
    said, state = _tagged(out, "SAID"), _tagged(out, "STATE")
    refused = [ln for ln in log if "refused" in ln or "Errno" in ln]
    print("%s: the page said %s; its state %s; the board: %s; landed: %s; after it "
          "the fill held %d B and %d blocks were free"
          % (zero.name, said, state, refused[-5:], landed, filled, left_after))
    # what a page's pairing writes, and the publish marker every save
    # overwrites (runtime/carts/moy_fs.py: never cleared)
    ours = (STORE + "/system/webkeys", STORE + "/.publish")
    changed = sorted(p for p, data in files0.items() if p not in ours and files1.get(p) != data)
    sizes = sorted(p for p, s in tree0.items() if p not in ours and tree1.get(p) != s)
    new = sorted(p for p in tree1 if p not in tree0 and p not in ours)
    half = sorted(p for p, s in landed.items()
                  if s >= 0 and p.rsplit("/", 1)[-1] in content
                  and s != len(content[p.rsplit("/", 1)[-1]]))
    assert not changed and not sizes, "files of the store changed: %s %s" % (changed, sizes)
    assert not new, "left behind: %s" % new
    assert not half, "half-written: %s" % half
    texts = " | ".join((said or {}).get("said", [])) + " " + str((said or {}).get("imported"))
    assert FULL_WORDS.search(texts), \
        "the page did not say the store is full; it shows: %s" % texts[-1500:]


# -- updates ------------------------------------------------------------------------------------------


# The console's way to its update screen on a page this board serves: the
# menu (the bar's logo), Settings (counted up from its last row, Restart,
# past About: the rows above it change with the card selected and the radio
# link, and the menu clamps at its ends), then Updates' "Update online" (ten
# rows down: General's six, Play's two, Updates' Channel).
TO_UPDATE = [{"click": [14, 13]}, {"wait": 800}] + [{"key": "ArrowDown"}] * 20 + \
    [{"key": "ArrowUp"}] * 2 + [{"wait": 300}, {"key": "Enter"}, {"wait": 1500}] + \
    [{"key": "ArrowDown"}] * 10 + [{"wait": 300}, {"key": "Enter"}]
OTA_VERDICT = re.compile(r"ZERO ota: (up to date|.* available|no build published|check failed)")
OTA_INSTALLS = re.compile(r"ZERO ota: (downloading|writing|installed|rebooting|image already)")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_update_screen_shows_what_the_channel_offers_without_installing(
        zero, mirror, tmp_path):
    """Settings' Update online on the page asks the board, which looks at
    its channel and answers what it offers (on the C3, with one app slot,
    nothing to install); the screen shows it, and leaving it installs
    nothing: the board neither downloads nor resets."""
    _needs_password(zero)
    log = []
    steps = sign_in(zero) + [{"wait": 3000}] + TO_UPDATE + [
        {"waitFor": "window.__moyState().then(function (s) { return s.screen == 'update'; })",
         "timeout": 20000},
        {"wait": 20000}, {"shot": "update"}, {"js": STATE % "UPDATE"},
        {"key": "Escape"}, {"wait": 1500}, {"key": "Escape"}, {"wait": 1500},
        {"js": STATE % "LEFT"}, {"wait": 10000},
    ]
    out = _browse(zero, zero.url, steps, tmp_path / "update",
                  on_line=lambda _l: log.extend(_board_lines(zero)))
    log.extend(_board_lines(zero, 2.0))
    ota = [ln for ln in log if "ZERO ota" in ln]
    print("%s: the update screen %s (%s); the board said %s"
          % (zero.name, _tagged(out, "UPDATE"), tmp_path / "update" / "update.png", ota))
    assert (_tagged(out, "UPDATE") or {}).get("screen") == "update", out[-1500:]
    assert (_tagged(out, "LEFT") or {}).get("screen") != "update", "the screen did not close"
    assert any(OTA_VERDICT.search(ln) for ln in ota), \
        "the board did not say what its channel offers: %s" % log[-20:]
    assert not any(OTA_INSTALLS.search(ln) for ln in ota), "it installed: %s" % ota
    assert not any("ZERO serving" in ln for ln in log), "the board reset"


# -- across a reboot ----------------------------------------------------------------------------


SETTING = ("show_fps", True)     # a row of the board's system/settings


def _setting(ssh, key):
    rc, out, _err = ssh.run("settings get %s" % key)
    return json.loads(out) if rc == 0 and out.strip() else None


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_an_imported_cart_and_a_setting_survive_a_reset(zero, mirror, ssh, tmp_path):
    """A cart imported on the page and a setting changed (over SSH, the
    store's own `settings`) are both there after a reset: on the board, and
    the cart on the shelf of a page opened after it. A Zero's page keeps its
    own Settings in the browser: the board has no VM to serve them
    (/console.json, moy_webhost.c's SYSTEM_PULL)."""
    key, value = SETTING
    archive, folder, _c = _bench_cart(tmp_path, "keep", "Zero Bench Keep")
    had = _setting(ssh, key)
    try:
        out = _browse(zero, zero.url, sign_in(zero) + _import_steps("IMPORTED"),
                      tmp_path / "in", env={"MOY_UPLOAD": str(archive)})
        assert folder in (_tagged(out, "IMPORTED") or ""), out[-1500:]
        rc, _o, err = ssh.run("settings set %s %s" % (key, json.dumps(value)))
        assert rc == 0, err
        zero.restart()
        rc, ls, _err = ssh.run("ls %s" % CARTS)
        assert folder.encode() in ls, "the cart is gone after the reset: %r" % ls
        assert _setting(ssh, key) == value, "the setting after the reset: %r" % _setting(ssh, key)
        out = _browse(zero, zero.url, sign_in(zero) + [{"wait": 3000}, SHELF],
                      tmp_path / "after")
        shelf = _tagged(out, "SHELF")
        assert shelf and folder in shelf, "the page's shelf after the reset: %s" % shelf
    finally:
        _remove(ssh, folder)
        ssh.run("settings unset %s" % key if had is None
                else "settings set %s %s" % (key, json.dumps(had)))


# What the page did while its board went away: `#s` as it changed, and an
# unload (a reload), which a reconnect must not need.
WATCH = """(function () {
  var W = window.__moyWatch = {t0: Date.now(), s: [], unload: false};
  var last = '';
  setInterval(function () { var t = document.getElementById('s').textContent;
    if (t != last) { last = t; W.s.push([Date.now() - W.t0, t]); } }, 100);
  addEventListener('pagehide', function () { W.unload = true;
    try { sessionStorage.setItem('moyWatch', JSON.stringify(W)); } catch (e) {} });
  return 'READY';
})()"""


WEB_LINE = re.compile(r"live|seal|sign|webkey|pair|ZERO|refus", re.I)


def _across(zero, ssh, tmp_path, stem, go_away):
    """The page open and signed in with a game running, `go_away()` takes
    the board from it: the page comes back to live without loading again,
    its console as it was (the game still running), its live socket open
    again, and a cart imported after it reaches the board. What `go_away`
    returned, and the page's state before and after."""
    title = "Brick Siege"
    archive, folder, content = _bench_cart(tmp_path, stem, "Zero Bench %s" % stem.title())
    done, log = [], []

    def on_line(line):
        log.extend(_board_lines(zero))
        if '"READY"' in line and not done:
            done.append(go_away())

    steps = sign_in(zero) + [
        {"js": "WORKER.postMessage({t: 'open', cart: %s}), 1" % json.dumps(folder_of_title(title))},
        {"waitFor": "window.__moyState().then(function (s) { return s.cart == %s; })"
                    % json.dumps(title), "timeout": 60000},
        {"wait": 5000}, {"js": STATE % "BEFORE"}, {"js": WATCH},
        {"wait": 120000}, LIVE_NOW, {"wait": 15000},
        {"js": STATE % "AFTER"},
        {"js": "'WATCH ' + JSON.stringify(window.__moyWatch)"},
    ] + _import_steps("IMPORTED")
    try:
        out = _browse(zero, zero.url, steps, tmp_path / stem, query="?dev=1&desktop=1",
                      env={"MOY_UPLOAD": str(archive)}, on_line=on_line, check=False)
        before, after = _tagged(out, "BEFORE"), _tagged(out, "AFTER")
        watch = _tagged(out, "WATCH")
        log.extend(_board_lines(zero, 2.0))
        print("%s: %s: the page said %s; before %s; after %s; the board's web lines: %s"
              % (zero.name, stem, watch and watch["s"], before, after,
                 [ln for ln in log if WEB_LINE.search(ln)][-20:]))
        assert done, "the board was not taken away (the page never got READY):\n" + out[-1500:]
        assert "STEP FAILED" not in out, out[-2500:]
        assert watch and not watch["unload"], "the page loaded again"
        assert after["cart"] == before["cart"] == title and after["stack"] == before["stack"], \
            "the console is not as it was: %s -> %s" % (before, after)
        assert (after["live"] or {}).get("opens", 0) > (before["live"] or {}).get("opens", 0), \
            "the live socket did not open again: %s -> %s" % (before["live"], after["live"])
        assert not _differs(ssh, folder, content), "the cart imported after it"
        return done[0], before, after
    finally:
        _remove(ssh, folder)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_page_reconnects_after_the_board_reboots(zero, mirror, ssh, tmp_path):
    """The board resets under an open page (_across)."""
    _across(zero, ssh, tmp_path, "reboot", zero.restart)


# A network no bench has: an Improv join to it drops the board's station
# until the join gives up and the board goes back onto its saved network
# (zero_host's ZeroBoard.join, about 15 s).
NOWHERE = ("moy-bench-nowhere", "nowhere-at-all")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_page_reconnects_after_the_board_s_wifi_drops(zero, mirror, ssh, tmp_path):
    """The board's Wi-Fi drops under an open page and comes back, the board
    not reset (_across): over the cable, an Improv join to a network that is
    not there, which the board refuses and then rejoins its own. The page's
    live socket dropped meanwhile, and SSH answers where it answered."""
    def drop():
        st, _urls, secs, err = Z.Improv(zero.b.ser).join(*NOWHERE, timeout=120.0)
        return st, secs, err

    (st, secs, err), before, after = _across(zero, ssh, tmp_path, "wifidrop", drop)
    print("%s: the station was gone for the join's %.1f s (Improv error %r, state %r)"
          % (zero.name, secs, err, st))
    assert err == 0x03, "the join to %r answered error %r, not UNABLE" % (NOWHERE[0], err)
    assert after["live"]["drops"] > before["live"]["drops"], \
        "the page's live socket never dropped: %s -> %s" % (before["live"], after["live"])
    rc, out, _e = ssh.run("date")
    assert rc == 0, "SSH at %s after the drop: %r" % (zero.url, out)


def folder_of_title(title):
    return _folder_of(title).name


# What a page shows once another browser took its board (owner, 2026-11-25;
# worker.js TAKEN): the card says so and offers it back, its field hidden,
# and the status reads disconnected. `%s` the tag.
TAKEN_SAYS = "Another browser signed in to this console, so this one was disconnected."
DISCONNECTED = ("(function () { var b = document.getElementById('pinb'); return "
                "document.getElementById('s').textContent == 'disconnected' && !!b && "
                "b.offsetParent !== null && b.textContent == 'take it back'; })()")
TOLD = ("'%s ' + JSON.stringify({h: document.getElementById('pinh').textContent, "
        "p: document.getElementById('pinp').textContent, "
        "b: document.getElementById('pinb').textContent, "
        "f: getComputedStyle(document.getElementById('pinf')).display, "
        "s: document.getElementById('s').textContent})")
LIVE_OPEN = ("window.__moyState().then(function (s) { return !!(s.live && s.live.opens && "
             "document.getElementById('s').textContent == 'live'); })")


def _told(got):
    """What is wrong with a page's card once its board was taken, or None."""
    want = {"h": "disconnected", "p": TAKEN_SAYS, "b": "take it back", "f": "none",
            "s": "disconnected"}
    return None if got == want else "it shows %s, not %s" % (got, want)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_second_browser_signing_in_displaces_the_first(zero, mirror, ssh, tmp_path):
    """Two browsers on one board (owner, 2026-11-25): the second pairs and
    signs in, syncs a cart and holds the live socket; the first is
    disconnected, its page says so with a button that takes the board back,
    and it does not reconnect by itself; pressed, the button takes the
    board back and the second page shows the card in turn."""
    archive, folder, content = _bench_cart(tmp_path, "second", "Zero Bench Second")
    query = "?dev=1&desktop=1"
    first = sign_in(zero) + [
        {"waitFor": LIVE_OPEN, "timeout": 120000}, {"js": STATE % "A_LIVE"},
        {"waitFor": DISCONNECTED, "timeout": 240000},
        {"js": TOLD % "A_TOLD"}, {"js": STATE % "A_TAKEN"}, {"shot": "a_told"},
        {"wait": 15000}, {"js": STATE % "A_STILL"},
        {"js": "window.__moyState().then(function (s) { window.__opens = s.live.opens; "
               "document.getElementById('pinb').click(); return 1; })"},
        {"waitFor": "window.__moyState().then(function (s) { return s.live.opens > "
                    "window.__opens; })", "timeout": 120000},
        {"js": STATE % "A_BACK"}, {"wait": 30000},
    ]
    second = sign_in(zero) + [{"waitFor": LIVE_OPEN, "timeout": 120000},
                              {"js": STATE % "B_LIVE"}] + _import_steps("B_SYNCED") + [
        {"waitFor": DISCONNECTED, "timeout": 180000},
        {"js": TOLD % "B_TOLD"}, {"shot": "b_told"},
    ]
    import threading
    got = {}

    def run_second():
        got["b"] = _browse(zero, zero.url, second, tmp_path / "b", query=query, check=False,
                           env={"MOY_UPLOAD": str(archive)}, timeout=900)

    def on_line(line):
        if '"A_LIVE ' in line and "thread" not in got:
            got["thread"] = threading.Thread(target=run_second)
            got["thread"].start()

    try:
        a = _browse(zero, zero.url, first, tmp_path / "a", query=query, check=False,
                    on_line=on_line, timeout=900)
        if "thread" in got:
            got["thread"].join(timeout=900)
        b = got.get("b", "")
        t = {k: _tagged(a, k) for k in ("A_LIVE", "A_TOLD", "A_TAKEN", "A_STILL", "A_BACK")}
        t.update({k: _tagged(b, k) for k in ("B_LIVE", "B_SYNCED", "B_TOLD")})
        print("%s: two browsers: %s" % (zero.name, json.dumps(
            {k: (v.get("live") if isinstance(v, dict) and "live" in v else v)
             for k, v in t.items()})))
        assert t["A_LIVE"], "the first browser did not go live:\n" + a[-1500:]
        assert t["B_LIVE"], "the second browser did not sign in:\n" + b[-1500:]
        assert folder in (t["B_SYNCED"] or "") and not _differs(ssh, folder, content), \
            "the second browser's cart did not reach the board"
        assert t["A_TOLD"] and not _told(t["A_TOLD"]), \
            "the first page, its board taken: %s" % _told(t["A_TOLD"])
        opens = lambda k: ((t[k] or {}).get("live") or {}).get("opens") or 0  # noqa: E731
        assert opens("A_STILL") == opens("A_TAKEN"), \
            "the first page reconnected by itself: %s -> %s" % (opens("A_TAKEN"), opens("A_STILL"))
        assert t["A_BACK"] and opens("A_BACK") > opens("A_STILL"), \
            "the first page did not take the board back: %s" % t["A_BACK"]
        assert t["B_TOLD"] and not _told(t["B_TOLD"]), \
            "the second page, its board taken back: %s" % _told(t["B_TOLD"])
    finally:
        if "thread" in got:
            got["thread"].join(timeout=900)
        _remove(ssh, folder)


# -- the network: the name and the clock ---------------------------------------------------------


def test_the_board_answers_at_its_mdns_name(zero):
    """The `.local` name the board's boot line gives resolves on this
    machine's network to the address it serves at, and `/sync` answers
    there."""
    import socket
    if not zero.local:
        pytest.skip("the board's boot line names no mDNS name")
    name = zero.local.split("//", 1)[1].split("/", 1)[0]
    t = time.monotonic()
    addr = socket.getaddrinfo(name, 80, socket.AF_INET)[0][4][0]
    ms = (time.monotonic() - t) * 1000
    print("%s: %s resolves to %s in %.0f ms" % (zero.name, name, addr, ms))
    assert addr == _host(zero), (name, addr, zero.url)
    assert json.loads(_get(zero.local + "/sync")[0]).get("sync") == 1


CLOCK_SKEW_S = 10


def test_the_board_s_clock_is_set_from_the_network(zero, ssh):
    """`date` on the board is this machine's UTC to a few seconds: its clock
    was set over the network."""
    import calendar
    rc, out, err = ssh.run("date '+%Y-%m-%d %H:%M:%S'")
    now = time.time()
    assert rc == 0, err
    board = calendar.timegm(time.strptime(out.decode().strip(), "%Y-%m-%d %H:%M:%S"))
    print("%s: the board's clock is %+.1f s from this machine's" % (zero.name, board - now))
    assert abs(board - now) < CLOCK_SKEW_S, "the board says %s" % out.decode().strip()


# -- Get Carts ---------------------------------------------------------------------------

CARTS_LOG = re.compile(r"Moybyte carts|ZERO|official|Memory|Traceback|alloc", re.I)


def _browse_logged(z, steps, out, query, peek=None):
    """browsershot over `steps` on the board's page while the board's serial
    is read: (the page's output, scrubbed; the board's lines CARTS_LOG keeps;
    `_heap` read over the REPL with the page still open, once a board line
    matches the regex `peek`, which ends the browse, else None)."""
    path = _scenario(out, steps, query)
    log = out / "browsershot.log"
    lines, heap = [], None
    with open(log, "w") as f:
        proc = subprocess.Popen(["node", "browsershot.mjs", str(path), str(out)],
                                cwd=str(RUNNER), env=dict(os.environ, MOY_BASE=z.url),
                                stdout=f, stderr=subprocess.STDOUT)
        try:
            end = time.monotonic() + 900
            while proc.poll() is None and time.monotonic() < end:
                got = [ln for ln in z.b.drain(1.0) if CARTS_LOG.search(ln)]
                lines += got
                if peek is not None and any(re.search(peek, ln) for ln in got):
                    lines += [ln for ln in z.b.drain(2.0) if CARTS_LOG.search(ln)]
                    r = Z.Repl(z.b.ser)
                    r.enter(clean=False)
                    heap = _carts_heap(r)
                    break
        finally:
            if proc.poll() is None:
                proc.kill()
            path.unlink()
    text = _scrub(log.read_text(), z)
    return text, lines, heap


# The page as a person opens it: `start` skips the play button, where `dev`
# would also poll the board's /stamp (the moy CLI's hot reload) twice a
# second, a load no page a person opens puts on it.
GET_CARTS = "?handheld=1&start=1&cart=moybyte.get_carts.moy"
# Get Carts' shelf on the handheld page, three cards a row in the order of
# their names (the release's carts and moybyte-org/carts'), the focus on the
# first: Achievements, Appearance, Brick Siege; Bullet Storm (an official
# cart no store is seeded with), Calc (an app the flash installs, which
# Remove may take off), Coin Quest; Doom, ESP 88, Files; Get Carts, Harpoon
# Pop, Jet Teapot; Letter Blitz, Moy Mesh (moybyte-org/carts' Lua cart).
BULLET_STORM = ["ArrowDown"]
CALC = ["ArrowDown", "ArrowRight"]
MOY_MESH = ["ArrowDown"] * 4 + ["ArrowRight"]
# An install's wait: the page asks, and the board streams the index and
# fetches the cart over TLS at a few KB/s.
INSTALL_WAIT_MS = 75000
# A cart of moybyte-org/carts a board can take asks before it lands (Get
# Carts' consent, its focus on No): the wait for the prompt after Get.
CONSENT_WAIT_MS = 40000
# What an install may leave of the board's internal heap below the idle
# read, after a collect with the store host stopped: the spread of a boot's
# own allocations. An install that keeps a buffer, a socket or a task's
# stack takes more.
HEAP_SPREAD = 8 * 1024
# The board's internal heap free with its page open, an install done: the
# room the next install's TLS handshake takes its 16 KB record buffer from.
PAGE_FREE = 30 * 1024


def _lora(z):
    """Whether the board's board.toml declares a LoRa radio (a `lora` row)."""
    rows = board_config.load(str(z.dir)).get("hardware", {}).get("resource", [])
    return any(r.get("name") == "lora" for r in rows)


def _keys(*keys, wait=700):
    out = []
    for k in keys:
        out += [{"key": k}, {"wait": wait}]
    return out


# The largest block the Python heap gives (#319): a bytearray's size,
# halved until one is taken.
PY_RUN = """
def _py_run():
    import gc
    gc.collect()
    lo, hi = 0, gc.mem_free()
    while lo < hi:
        m = (lo + hi + 1) // 2
        try:
            b = bytearray(m)
            del b
            lo = m
        except MemoryError:
            hi = m - 1
    return lo
"""


def _carts_heap(r, folder=None):
    """(internal free, internal largest, internal low-water since the boot,
    Python heap free, its largest run) bytes after a collect, and whether
    `folder` is in the store, over the raw REPL `r`."""
    r.run("import gc\ngc.collect()")
    regions = [h for h in r.eval("__import__('esp32').idf_heap_info(%d)" % Z.INTERNAL_HEAP) if h]
    free, big = Z.internal_heap(regions)
    py = r.eval("__import__('gc').mem_free()")
    r.run(PY_RUN)
    run = r.eval("_py_run()")
    there = folder is None or folder in r.eval("__import__('os').listdir(%r)" % CARTS)
    return free, big, sum(h[3] for h in regions), py, run, there


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_get_carts_installs_and_reinstalls_on_the_board(zero, mirror, tmp_path):
    """The page's Get Carts asks the board to install an official cart that
    is not on it, to remove a cart the flash installed and get it back, and
    to Get Moy Mesh from moybyte-org/carts, which requires the LoRa radio:
    the two land, and Moy Mesh lands on a board with a `lora` row and is
    refused, nothing written, on one without; the board's internal heap
    after each is the idle one's, give or take HEAP_SPREAD (no install keeps
    RAM). Calc's own files are written back at the end, as the
    release's copy the page got may differ from the one the flash put
    there."""
    _needs_password(zero)
    calc = CARTS + "/moybyte.calc.moy"
    with zero.repl(clean=False) as r:
        idle = _carts_heap(r)
        kept = {p: r.read(p) for p, size in r.tree(calc).items() if size >= 0}
    print("idle: internal %d free, %d largest, %d low-water; Python heap %d free, "
          "%d largest run" % idle[:5])
    sessions = [        # (name, folder, keys, whether it lands)
        ("bullet_storm", "moybyte.bullet_storm.moy",
         _keys(*BULLET_STORM) + _keys("Enter", "Enter", wait=1500), True),
        ("calc", "moybyte.calc.moy",
         _keys(*CALC) + _keys("Enter", wait=1500) + _keys("ArrowLeft", "Enter", "ArrowRight")
         + _keys("Enter", wait=8000) + [{"shot": "calc_removed"}]
         + _keys("Enter", "Enter", wait=1500), True),
        ("moy_mesh", "moymesh.moy",
         _keys(*MOY_MESH) + _keys("Enter", "Enter", wait=1500)
         + ([{"wait": CONSENT_WAIT_MS}] + _keys("ArrowRight", "Enter", wait=1500)
            if _lora(zero) else []), _lora(zero)),
    ]
    try:
        for name, folder, keys, lands in sessions:
            steps = sign_in(zero) + [{"wait": 15000}] + keys \
                + [{"wait": INSTALL_WAIT_MS}, {"shot": name}]
            _out, lines, page = _browse_logged(zero, steps, tmp_path / name, GET_CARTS,
                                               peek=r"official: install %s " % re.escape(folder))
            print("%s: the board's lines:\n  %s" % (name, "\n  ".join(lines)))
            if page is not None:
                print("%s, the page open: internal %d free, %d largest, %d low-water; "
                      "Python heap %d free, %d largest run" % ((name,) + page[:5]))
                zero.take("zero python largest run, %s just installed" % name, page[4] / 1024.0)
            done = [ln for ln in lines if "official: install %s " % folder in ln]
            with zero.repl(clean=False) as r:
                heap = _carts_heap(r, folder)
            print("%s: internal %d free, %d largest, %d low-water; Python heap %d free, "
                  "%d largest run; landed %s" % ((name,) + heap))
            zero.take("zero internal free after %s" % name, heap[0] / 1024.0)
            zero.take("zero internal largest after %s" % name, heap[1] / 1024.0)
            refused = bool(done) and done[-1].endswith(" idle") and any(
                "%s stopped" % folder in ln for ln in lines)
            if lands:
                assert done and done[-1].endswith(" done"), \
                    "%s: the board did not install it: %s" % (name, lines[-8:])
                assert heap[5], "%s: the board said done but its store has no %s" % (
                    name, folder)
            else:
                assert refused, \
                    "%s: the board did not stop it at the prompt: %s" % (name, lines[-8:])
                assert not heap[5], "%s: refused, yet the store has %s" % (name, folder)
            assert page[0] >= PAGE_FREE, \
                "%s: the board's internal heap is %d bytes free with its page open" % (
                    name, page[0])
            assert heap[0] >= idle[0] - HEAP_SPREAD, \
                "%s: the board's internal heap is %d bytes free after it, %d idle" % (
                    name, heap[0], idle[0])
    finally:
        with zero.repl() as r:
            if kept:
                r.remove(calc)
                for p, data in sorted(kept.items()):
                    r.mkdirs(p.rsplit("/", 1)[0])
                    r.write(p, data)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_page_has_the_devices_its_board_relays(zero, mirror, tmp_path):
    """The page's live socket names the device kinds the board relays
    (native/moy_kernel/moy_dev_kinds.h's THE RELAY): LoRa where board.toml
    has a `lora` row, nothing where it has none, and the page's console
    lists exactly those as its device APIs (what an install check reads)."""
    _needs_password(zero)
    st = ("window.__moyState().then(function (s) { return 'KINDS ' + JSON.stringify("
          "{devs: s.devs}); })")
    out = _browse(zero, zero.url, sign_in(zero) + [{"wait": 3000}, {"js": st}],
                  tmp_path / "kinds", query="?dev=1&desktop=1")
    got = _tagged(out, "KINDS")
    assert got is not None, out[-2000:]
    if _lora(zero):
        assert got["devs"] and got["devs"]["kinds"] == 1, got
    else:
        assert got["devs"] is None, got


MESH = "moymesh.moy"
MESH_STATE = ("window.__moyState().then(function (s) { return '%s ' + JSON.stringify({cart: "
              "s.cart, devs: s.devs, card: s.card, error: s.cart_error, live: s.live && "
              "{opens: s.live.opens, rtt: s.live.rtt}}); })")


def _radio(r):
    """(the live socket's device rows open, the calls it served, the writes a
    device took, the records and events it pushed; the LoRa radio's owner)
    over the raw REPL `r`."""
    live = r.eval("__import__('moy_net').live_stats()")
    return tuple(live[10:14]) + (r.eval("__import__('moy_lora').owner()"),)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_moy_mesh_holds_the_board_s_radio_from_the_page(zero, mirror, tmp_path):
    """Moy Mesh, which the Get Carts test above installed on a board with a
    `lora` row, opened on the page: its service holds the board's radio over
    the live socket's device channel (native/moy_net/moy_live_dev.c), so the
    board's process for the page holds the radio and its driver took the
    node's announce; the page's end gives the radio back. The device channel
    call's round trip is the page's echo's (the same socket and task)."""
    if not _lora(zero):
        pytest.skip("%s has no LoRa radio (no `lora` row)" % zero.name)
    _needs_password(zero)
    with zero.repl(clean=False) as r:
        if MESH not in r.eval("__import__('os').listdir(%r)" % CARTS):
            pytest.skip("Moy Mesh is not on %s (the Get Carts test installs it)" % zero.name)
        before = _radio(r)
    steps = sign_in(zero) + [
        {"js": "WORKER.postMessage({t: 'open', cart: %s}), 1" % json.dumps(MESH)},
        # its first run asks: the card names the radio, No focused; Open
        # records the consent and runs it
        {"waitFor": "window.__moyState().then(function (s) { return !!(s.card && "
                    "/LoRa/.test(s.card.lines.join(' '))); })", "timeout": 60000},
        {"js": "cv.focus(), 'focused'"}, {"key": "ArrowRight"}, {"wait": 300},
        {"key": "Enter"},
        {"waitFor": "window.__moyState().then(function (s) { return !!(s.devs && "
                    "s.devs.rows >= 1 && s.devs.down >= 3); })", "timeout": 60000},
        {"wait": 8000},
        {"js": MESH_STATE % "MESH"},
        {"wait": 2000},
    ]
    path = _scenario(tmp_path / "mesh", steps, "?dev=1&desktop=1")
    proc = subprocess.Popen(["node", "browsershot.mjs", str(path), str(tmp_path / "mesh")],
                            cwd=str(RUNNER), env=dict(os.environ, MOY_BASE=zero.url),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines, held = [], None
    try:
        for line in proc.stdout:
            lines.append(line)
            if held is None and 'js -> "MESH ' in line:
                with zero.repl(clean=False) as r:
                    held = _radio(r)
        proc.wait(timeout=120)
    finally:
        if proc.poll() is None:
            proc.kill()
        path.unlink()
    out = _scrub("".join(lines), zero)
    got = _tagged(out, "MESH")
    time.sleep(8)                       # the board's session ends with the page's socket
    with zero.repl(clean=False) as r:
        after = _radio(r)
    print("Moy Mesh on the page: %s\nthe board before %s, while open %s, after %s"
          % (got, before, held, after))
    assert got and got["cart"] == "Moy Mesh", "Moy Mesh did not open:\n" + out[-3000:]
    assert got["devs"]["opens"] >= 1 and got["devs"]["rows"] >= 1, got
    assert held is not None and held[0] == 1, "the board holds no radio row for the page"
    assert held[4] != 0, "the radio has no owner while the page holds it"
    assert held[2] > before[2], "the radio took no packet from the page (its announce)"
    assert after[0] == 0 and after[4] == 0, "the page's end left the radio held: %r" % (after,)
    d = got["devs"]
    if d.get("timed"):
        zero.take("zero device call round trip mean", d["rtt_sum_us"] / d["timed"] / 1000.0)
        print("a device call's round trip at the page, over %d calls: min %.1f, mean %.1f, "
              "max %.1f ms" % (d["timed"], d["rtt_min_us"] / 1000.0,
                               d["rtt_sum_us"] / d["timed"] / 1000.0, d["rtt_max_us"] / 1000.0))
    if got["live"] and got["live"]["rtt"]:
        med, p90 = Z.rtt(got["live"]["rtt"])
        zero.take("zero live rtt median with the radio", med, got["live"]["rtt"])
        print("the socket's round trip with the radio held: median %.1f ms, p90 %.1f ms"
              % (med, p90))


# -- a match against a T-Deck --------------------------------------------------------------


def _tdeck(*args, timeout=180):
    run = subprocess.run([sys.executable, str(ROOT / "tools" / "board.py"), "tdeck"]
                         + list(args) + ["--port", TDECK_PORT],
                         capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
    assert run.returncode == 0, "board.py tdeck %s: %s" % (
        " ".join(args), (run.stdout + run.stderr)[-1500:])
    return run.stdout


def _tdeck_py(expr, timeout=60):
    out = _tdeck("py", expr, "--timeout", str(timeout), timeout=timeout + 60)
    return ast.literal_eval(out.strip().splitlines()[-1].split(" -> ", 1)[1])


def _folder_of(title):
    for d in sorted((ROOT / "system_carts").glob("*.moy")):
        with open(d / "manifest.json") as f:
            if json.load(f).get("title") == title:
                return d
    raise AssertionError("no system cart titled %r" % title)


@pytest.fixture(scope="module")
def match_carts(zero):
    """The match's carts on both sides, each pushed where it is not there,
    and taken back after (the Zero's by the module's give-back)."""
    _needs_password(zero)
    pushed = []
    with zero.repl() as r:
        for title in MATCH_CARTS:
            src = _folder_of(title)
            if CARTS + "/" + src.name not in zero.before_tree:
                r.put_folder(str(src), CARTS + "/" + src.name)
    shelf = _tdeck_py("[c.get('title') for c in ws.carts.all]")
    for title in MATCH_CARTS:
        if title not in shelf:
            _tdeck("push", str(_folder_of(title)))
            pushed.append(_folder_of(title).name)
    try:
        yield
    finally:
        _tdeck("desk")
        for folder in pushed:
            _tdeck("remove", folder)


@needs_tdeck
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("cart", MATCH_CARTS)
def test_the_page_plays_a_match_against_a_tdeck(zero, mirror, match_carts, cart, tmp_path):
    """The T-Deck runs the cart with the world check armed; the page the
    board serves opens the same cart with it armed too; the match forms,
    plays its frames, and neither side finds its checkpoints apart."""
    _needs_password(zero)
    _tdeck("run", cart)
    try:
        _tdeck("tail", "1", "--send", "link check on", "--grep", "REMOTE")
        state = ("window.__moyState().then(function (s) { return '%s ' + JSON.stringify("
                 "{link: s.link, cart: s.cart, stats: s.link_stats}); })")
        steps = sign_in(zero) + [
            {"waitFor": "window.__moyState().then(function (s) { return !!(s.link && "
                        "s.link[2] && s.link[3] > 600); })", "timeout": 120000},
            {"js": state % "PLAYED"},
        ]
        query = "?dev=1&desktop=1&linkcheck=1&cart=" + cart.replace(" ", "%20")
        out = _browse(zero, zero.url, steps, tmp_path / "match", query=query)
        page = _tagged(out, "PLAYED")
        deck = _tdeck_py("ws.link.stats()")
    finally:
        _tdeck("leave")
    pm, dm = (page or {}).get("stats", {}).get("match"), deck.get("match")
    print("%s %s: page %s | tdeck %s" % (zero.name, cart, pm, dm))
    assert page and page["link"][2] and pm, "the match formed on the page:\n" + out[-2000:]
    assert dm, "the match formed on the T-Deck: %s" % deck
    assert page["stats"]["world_check"] and deck["world_check"], "both armed the world check"
    assert pm["checks"] >= 10 and dm["checks"] >= 10, (pm, dm)
    assert pm["desync"] is None and dm["desync"] is None, (pm, dm)


ATAN2_ARGS = [(y, x) for y in (-7.5, -1.0, -0.3, 0.0, 0.2, 1.0, 3.25, 100.0)
              for x in (-9.0, -1.0, -0.05, 0.0, 0.4, 1.0, 2.5, 1e-3)]
ATAN2 = ("[__import__('binascii').hexlify(__import__('struct').pack('<f', "
         "__import__('math').atan2(y, x))).decode() for (y, x) in %r]" % (ATAN2_ARGS,))
RUN_WASM = """
import { pathToFileURL } from "node:url";
const { MOY_DIST: dist, MOY_CODE: code } = process.env;
const { loadMicroPython } = await import(pathToFileURL(dist + "/micropython.mjs").href);
const out = [];
const mp = await loadMicroPython({ heapsize: 8 << 20, stdout: (l) => out.push(l) });
mp.runPython(code);
process.stdout.write(out.join("\\n") + "\\n");
"""


@needs_tdeck
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_tdeck_atan2_is_the_wasm_s(tmp_path):
    """math.atan2 over every quadrant and both axes, as the single the VM
    keeps, on the T-Deck and in the browser's wasm: one answer, or a Python
    cart that steers by it parts the two sides of a match."""
    dist = RUNNER / "dist"
    if not (dist / "micropython.mjs").exists():
        pytest.skip("web_runner dist/ not built")
    deck = _tdeck_py(ATAN2)
    script = tmp_path / "atan2.mjs"
    script.write_text(RUN_WASM)
    run = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=120,
                         env=dict(os.environ, MOY_DIST=str(dist),
                                  MOY_CODE="print(repr(%s))" % ATAN2))
    assert run.returncode == 0, run.stderr[-1500:]
    wasm = ast.literal_eval(run.stdout.strip().splitlines()[-1])
    apart = [(a, d, w) for a, d, w in zip(ATAN2_ARGS, deck, wasm) if d != w]
    print("atan2: %d of %d agree between the T-Deck and the wasm; apart: %s"
          % (len(ATAN2_ARGS) - len(apart), len(ATAN2_ARGS), apart))
    assert len(deck) == len(wasm) == len(ATAN2_ARGS)
    assert not apart, apart


# -- a session soak ---------------------------------------------------------------------------------


# How long the soak runs, and how far the board's internal RAM may fall
# across it before it is a leak: free, read in an SSH session each round
# (the best of the last three rounds against the first, Z.drift), and the
# largest block over the cable at the start and the end (the host stopped,
# its heap collected, so what a round leaves held shows). Calibrated on the
# C3 (2026-11-25): a round's reading moves by a few KB with what the board
# is doing as `free` runs; a leak of a sign-in or a sync is a fall that
# keeps on round after round.
SOAK_S = int(os.environ.get("MOYBYTE_ZERO_SOAK_S") or 12 * 60)
SOAK_FREE_BAND = 6 * 1024
SOAK_LARGEST_BAND = 8 * 1024


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_zy_a_session_soak_keeps_the_board_s_ram(zero, mirror, ssh, tmp_path):
    """About twelve minutes of what a person does, round after round: a new
    browser loads the page and signs in, reloads it, syncs a cart, opens Get
    Carts and leaves it; an SSH session runs a few commands. The board's
    internal RAM is read each round and must not keep falling. Last in the
    file but the give-back: it is the slow one."""
    free0, big0 = _heap(zero, "before the soak")
    archive, folder, _c = _bench_cart(tmp_path, "soak", "Zero Bench Soak")
    steps = sign_in(zero) + [{"js": "location.reload(), 1"}, {"wait": 3000}, LIVE_NOW] + \
        _import_steps("IMPORTED") + _get_carts_steps() + \
        [{"js": "location.search = '?handheld=1&dev=1', 1"}, {"wait": 3000}, LIVE_NOW]
    rounds, frees, log = [], [], []
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < SOAK_S or len(rounds) < 3:
            n = len(rounds) + 1
            r0 = time.monotonic()
            out = _browse(zero, zero.url, steps, tmp_path / ("round%d" % n),
                          env={"MOY_UPLOAD": str(archive)},
                          on_line=lambda _l: log.extend(_board_lines(zero)))
            assert folder in (_tagged(out, "IMPORTED") or ""), out[-1500:]
            _get_carts_listed(zero, out, log[-40:])
            t, free = _session(ssh, zero)
            assert free is not None, "free said no internal row: %r" % t.since(0)[-300:]
            try:
                for cmd in ("ls %s" % CARTS, "df", "date", "cat %s/%s/manifest.json"
                            % (CARTS, folder)):
                    assert t.command(cmd) is not None, "%s: %r" % (cmd, t.since(0)[-300:])
                _still_up(zero, t)
            finally:
                t.close()
            _remove(ssh, folder)
            frees.append(free)
            rounds.append(time.monotonic() - r0)
            print("%s soak round %d (%.0f s): internal RAM free in SSH %.1f KB"
                  % (zero.name, n, rounds[-1], free / 1024.0))
    finally:
        _remove(ssh, folder)
    free1, big1 = _heap(zero, "after the soak")
    drop, past = Z.drift(frees, SOAK_FREE_BAND)
    print("%s soak: %d rounds in %.0f s; free in SSH by round (KB) %s, fell %.1f KB "
          "(band %.1f); over the cable free %.1f -> %.1f KB, largest %.1f -> %.1f KB "
          "(band %.1f)" % (zero.name, len(rounds), time.monotonic() - t0,
                           [round(f / 1024.0, 1) for f in frees], drop / 1024.0,
                           SOAK_FREE_BAND / 1024.0, free0 / 1024.0, free1 / 1024.0,
                           big0 / 1024.0, big1 / 1024.0, SOAK_LARGEST_BAND / 1024.0))
    assert not past, "free internal RAM kept falling: %s" % frees
    assert big0 - big1 <= SOAK_LARGEST_BAND, \
        "the largest block fell %.1f KB over the soak" % ((big0 - big1) / 1024.0)
    assert free0 - free1 <= SOAK_FREE_BAND, \
        "free internal RAM fell %.1f KB over the soak" % ((free0 - free1) / 1024.0)


# -- given back -------------------------------------------------------------------------------


def test_zz_the_board_is_given_back(zero):
    """What the suite made goes, what it changed is written back, and the
    board serves where it served."""
    with zero.repl() as r:
        left = _give_back(zero, r)
    assert zero.url == zero.served_at, (zero.url, zero.served_at)
    assert not left, "the store differs from the suite's start: %s" % left
