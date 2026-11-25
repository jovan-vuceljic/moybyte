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
pairs without loading again, saying what it does, and SSH answers at once.

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


def _browse(z, base, steps, out, query="?handheld=1&dev=1", timeout=600, boot_ms=120000):
    """browsershot over `steps` against `base`: its output, scrubbed."""
    path = _scenario(out, steps, query, boot_ms)
    try:
        run = subprocess.run(["node", "browsershot.mjs", str(path), str(out)],
                             cwd=str(RUNNER), env=dict(os.environ, MOY_BASE=base),
                             capture_output=True, text=True, timeout=timeout)
    finally:
        path.unlink()
    text = _scrub(run.stdout + run.stderr[-500:], z)
    print(text[-4000:])
    assert run.returncode == 0, text[-3000:]
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
    ]
    out = _browse(zero, zero.url, steps, tmp_path / "claim",
                  query="?handheld=1&start=1#" + frag, boot_ms=1000)
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
                    heap = _heap(r)
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


def _heap(r, folder=None):
    """(internal free, internal largest, internal low-water since the boot,
    Python heap free) bytes after a collect, and whether `folder` is in the
    store, over the raw REPL `r`."""
    r.run("import gc\ngc.collect()")
    regions = [h for h in r.eval("__import__('esp32').idf_heap_info(%d)" % Z.INTERNAL_HEAP) if h]
    free, big = Z.internal_heap(regions)
    py = r.eval("__import__('gc').mem_free()")
    there = folder is None or folder in r.eval("__import__('os').listdir(%r)" % CARTS)
    return free, big, sum(h[3] for h in regions), py, there


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
        idle = _heap(r)
        kept = {p: r.read(p) for p, size in r.tree(calc).items() if size >= 0}
    print("idle: internal %d free, %d largest, %d low-water; Python heap %d free" % idle[:4])
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
                print("%s, the page open: internal %d free, %d largest, %d low-water"
                      % ((name,) + page[:3]))
            done = [ln for ln in lines if "official: install %s " % folder in ln]
            with zero.repl(clean=False) as r:
                heap = _heap(r, folder)
            print("%s: internal %d free, %d largest, %d low-water; Python heap %d free; "
                  "landed %s" % ((name,) + heap))
            zero.take("zero internal free after %s" % name, heap[0] / 1024.0)
            zero.take("zero internal largest after %s" % name, heap[1] / 1024.0)
            refused = bool(done) and done[-1].endswith(" idle") and any(
                "%s stopped" % folder in ln for ln in lines)
            # The cart runs in the page, and a page has no LoRa face: a Zero's
            # radio reaches it only over the live socket, which #254 plans.
            # Until then the page's needs check refuses it there too.
            unbridged = lands and refused and not heap[4]
            if lands and not unbridged:
                assert done and done[-1].endswith(" done"), \
                    "%s: the board did not install it: %s" % (name, lines[-8:])
                assert heap[4], "%s: the board said done but its store has no %s" % (
                    name, folder)
            else:
                assert refused, \
                    "%s: the board did not stop it at the prompt: %s" % (name, lines[-8:])
                assert not heap[4], "%s: refused, yet the store has %s" % (name, folder)
            assert page[0] >= PAGE_FREE, \
                "%s: the board's internal heap is %d bytes free with its page open" % (
                    name, page[0])
            assert heap[0] >= idle[0] - HEAP_SPREAD, \
                "%s: the board's internal heap is %d bytes free after it, %d idle" % (
                    name, heap[0], idle[0])
            if unbridged:
                pytest.xfail("%s: the page refuses %s, its LoRa radio being the board's "
                             "(#254)" % (zero.name, folder))
    finally:
        with zero.repl() as r:
            if kept:
                r.remove(calc)
                for p, data in sorted(kept.items()):
                    r.mkdirs(p.rsplit("/", 1)[0])
                    r.write(p, data)


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


# -- given back -------------------------------------------------------------------------------


def test_zz_the_board_is_given_back(zero):
    """What the suite made goes, what it changed is written back, and the
    board serves where it served."""
    with zero.repl() as r:
        left = _give_back(zero, r)
    assert zero.url == zero.served_at, (zero.url, zero.served_at)
    assert not left, "the store differs from the suite's start: %s" % left
