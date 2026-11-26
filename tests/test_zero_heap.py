"""THE HEAP'S SHAPE (device/zero_host.py), held on a host (#319).

A C3 has one Python heap of 64 KB and its store host keeps two thirds of it
for good. What a request works in is the rest, and it stays one run only
while three rules hold: what lives for good is made at start, the heap
collects every GC_STEP bytes, and a request leaves what it found. Each was
broken once without a test failing, and the board then refused an install or
an upload some minutes into a session, on whichever request met the hole.

The twin (tests/zero_twin.py) is the board's own start and loop under the
board model's MicroPython, over the kernel's webhost on a real socket, with
the free heap a C3 has after its start. A page's session is played at it
round after round (sign in, pull, a cart saved with its cover, Settings, Get
Carts' list, an install and its removal, the Wi-Fi panel's scan, an update
check), and after each round the heap must be what it was after the first.
"""
import base64
import http.server
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "device"))
sys.path.insert(0, str(ROOT))

import seal_client                                      # noqa: E402
from test_install_heap import _repo                     # noqa: E402
from test_ota_signing import TEST_KEYS                  # noqa: E402

import zero_host                                        # noqa: E402
from tools import board_config                          # noqa: E402

# What a C3's Python heap has free once its host is up (the suite's soak
# prints the board's own; tests/test_zero_on_glass.py holds it there).
C3_FREE = 20 * 1024
# What a session may leave behind. KEPT: the bytes the host holds over what
# it held at its start (the last request's state: a folder's name, a verdict).
# TORN: the free bytes outside the largest free run, which is where those
# few objects lie: no further above what is live than the collect's step
# and the request's own work let them be made.
KEPT = 1536
TORN = 2 * zero_host.GC_STEP
ROUNDS = 6
HOLD_MS = 200                       # zero_wifi.NETS_HOLD_MS here
BLOCK = 16                          # a 32-bit heap's block
PASSWORD = "twin-bench-1"


# -- rule 1: what a running host can import is in LASTING ---------------------

# The staged modules a running host never imports, and why.
NEVER_AT_RUN = {
    "boot": "the image's entry",
    "main": "the image's entry",
    "zero_host": "the host itself",
    "rsa_check": "the signature check of a host without the kernel's (a page)",
    "moy_backup": "a store format step: sweep_store's, inside start",
}


def _imports(path):
    """(at import, inside a function) of one module: the base names."""
    import ast
    top, late = set(), set()

    def walk(node, deep):
        for n in ast.iter_child_nodes(node):
            inner = deep or isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            names = ()
            if isinstance(n, ast.Import):
                names = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                names = [n.module]
            elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "__import__" and n.args
                  and isinstance(n.args[0], ast.Constant)):
                names = [str(n.args[0].value)]
            (late if deep else top).update(x.split(".")[0] for x in names)
            walk(n, inner)

    walk(ast.parse(path.read_text()), False)
    return top, late


def _source(name):
    for d in ("device", "runtime"):
        got = sorted((ROOT / d).rglob(name))
        if got:
            return got[0]
    return None


@pytest.mark.parametrize("board", ["esp32c3_zero", "seeed_xiao_esp32s3_zero"])
def test_every_module_a_running_zero_can_import_is_made_at_its_start(board):
    """A module first imported by a request is a few KB made for good in the
    middle of that request's work. So every module the image stages is one
    of: in LASTING, imported by a LASTING module as it loads, or named in
    NEVER_AT_RUN with the reason no request reaches it."""
    staged = board_config.staged_modules(ROOT / "firmware" / board, ROOT)
    tops = {}
    for name in staged:
        src = _source(name)
        assert src is not None, name
        tops[name[:-3]] = _imports(src)[0]
    made = set()
    todo = [m for m in zero_host.LASTING if m in tops]
    while todo:
        m = todo.pop()
        if m not in made:
            made.add(m)
            todo.extend(d for d in tops[m] if d in tops)
    late = sorted(m for m in tops if m not in made and m not in NEVER_AT_RUN)
    assert late == [], (
        "%s stages %s, which nothing imports at the host's start: add it to "
        "zero_host.LASTING, or to NEVER_AT_RUN with why no request imports it"
        % (board, late))


# The modules a staged module imports inside a function that no Zero has:
# the import fails there, or its line is never reached.
NOT_ON_A_ZERO = {
    "runtime": "the host's package",
    "blocks": "the block compiler: a console's editor",
    "cover_png": "a console's cover reader",
    "shell_servers": "a console's servers",
    "traceback": "the host's",
    "ubinascii": "the name an older MicroPython gave binascii",
    "wallclock": "a console's clock",
    "carts_data": "the image's roster, read by the seed inside start",
    "zero_svc": "the apps' services, staged where the image runs them (the XIAO); "
                "zero_host.make_services imports it at the start, before the host",
    "zero_offline": "Works offline, staged where the image has an updater (the XIAO)",
}


@pytest.mark.parametrize("board", ["esp32c3_zero", "seeed_xiao_esp32s3_zero"])
def test_every_built_in_a_request_can_import_is_imported_at_the_start(board):
    """A built-in's first import grows sys.modules where the heap then
    stands: each one a staged module imports inside a function is in
    BUILT_IN, or in NOT_ON_A_ZERO with why."""
    staged = board_config.staged_modules(ROOT / "firmware" / board, ROOT)
    mods = {n[:-3] for n in staged}
    late = set()
    for name in staged:
        late |= _imports(_source(name))[1]
    unknown = sorted(late - mods - set(zero_host.BUILT_IN) - set(NOT_ON_A_ZERO))
    assert unknown == [], (
        "%s: %s imported inside a function of a staged module: add it to "
        "zero_host.BUILT_IN, or to NOT_ON_A_ZERO with why" % (board, unknown))


def test_lasting_names_only_modules_a_zero_stages():
    staged = set()
    for board in ("esp32c3_zero", "seeed_xiao_esp32s3_zero"):
        staged |= {n[:-3] for n in board_config.staged_modules(ROOT / "firmware" / board, ROOT)}
    assert sorted(m for m in zero_host.LASTING if m not in staged) == []


# -- the twin ----------------------------------------------------------------


class _Shelf(http.server.BaseHTTPRequestHandler):
    """An index and its release assets over HTTP, by range as a board asks."""
    routes = {}
    protocol_version = "HTTP/1.1"

    def do_GET(self):                                   # noqa: N802
        data = self.routes.get(self.path)
        if data is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        span = re.match(r"bytes=(\d+)-(\d+)", self.headers.get("Range") or "")
        if span:
            a, b = int(span.group(1)), int(span.group(2))
            part = data[a:b + 1]
            self.send_response(206)
            self.send_header("Content-Range", "bytes %d-%d/%d" % (a, a + len(part) - 1, len(data)))
        else:
            part = data
            self.send_response(200)
        self.send_header("Content-Length", str(len(part)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(part)
        self.close_connection = True

    def log_message(self, *a):
        pass


class Twin:
    def __init__(self, tmp_path, step=None, free=C3_FREE):
        from unix_mp import require_unix_mp, runtime_tree
        exe = require_unix_mp(board_model=True, why="a board's heap is the boards' model's")
        self.web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Shelf)
        base = "http://127.0.0.1:%d" % self.web.server_address[1]
        repo = _repo(base + "/shelf")
        _Shelf.routes = dict((u[len(base):], d) for u, d in repo.routes().items())
        threading.Thread(target=self.web.serve_forever, daemon=True).start()
        self.shelf = repo.url("index.json")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        conf = tmp_path / "twin.json"
        conf.write_text(json.dumps({
            "port": self.port, "keys": TEST_KEYS, "free": free, "step": step,
            "hold_ms": HOLD_MS,
            "password": PASSWORD, "shelf": self.shelf,
            "manifest": base + "/release/ota.json"}))
        self.store = tmp_path / "moy"
        self.logpath = tmp_path / "twin.log"
        self.logf = open(self.logpath, "w")
        self.proc = subprocess.Popen(
            [exe, "-X", "heapsize=1M", str(ROOT / "tests" / "zero_twin.py"), runtime_tree(),
             str(ROOT / "device"), str(conf)],
            cwd=str(tmp_path), stdin=subprocess.PIPE, stdout=self.logf,
            stderr=subprocess.STDOUT)
        self.wait("READY", timeout=60)

    def log(self):
        return self.logpath.read_text(errors="replace")

    def wait(self, line, timeout=20.0):
        end = time.monotonic() + timeout
        while True:
            text = self.log()
            if any(ln.strip() == line for ln in text.splitlines()):
                return text
            assert self.proc.poll() is None and time.monotonic() < end, text[-3000:]
            time.sleep(0.02)

    def send(self, method, target, body=b""):
        with socket.create_connection(("127.0.0.1", self.port), timeout=20) as c:
            c.sendall(("%s %s HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\n\r\n"
                       % (method, target, len(body))).encode() + body)
            data = b""
            while True:
                k = c.recv(65536)
                if not k:
                    return data
                data += k

    def heap(self, tag):
        """(free, held, largest free run, modules imported since start)."""
        self.proc.stdin.write(tag.encode() + b"\n")
        self.proc.stdin.flush()
        text = self.wait("END " + tag)
        said = text[text.rindex("HEAP " + tag):]
        _h, _t, free, used, *mods = said.splitlines()[0].split()
        run = int(re.search(r"max free sz: (\d+)", said).group(1)) * BLOCK
        return int(free), int(used), run, [m for m in mods if m != "-"]

    def end(self):
        self.proc.kill()
        self.proc.wait()
        self.logf.close()
        self.web.shutdown()
        self.web.server_close()


def _until(page, path, done, timeout=30.0):
    end = time.monotonic() + timeout
    while True:
        st, doc = page.json("GET", path)
        assert st == 200, doc
        if done(doc):
            return doc
        assert time.monotonic() < end, doc
        time.sleep(0.02)


def _ask(page, path, body):
    st, doc = page.json("POST", path, body)
    assert st == 200 and doc.get("ok") is not False, (st, doc.get("message"), doc.get("state"))
    return doc


def _sync(page, ops, root=None):
    doc = {"v": 1, "ops": ops} if root is None else {"v": 2, "root": root, "ops": ops}
    st, got = page.json("POST", "/sync", doc)
    assert st == 200 and got == {"ok": len(ops), "err": []}, got


def _round(page, twin, k):
    """One visit of a page, as its worker makes one."""
    page.sign_in()
    assert page.call("GET", "/carts.json")[0] == 200
    st, console = page.json("GET", "/console.json")
    assert st == 200
    # a cart made on the page: its text, then its cover in two parts
    cover = os.urandom(20000)
    b64 = [base64.b64encode(cover[i:i + 12000]).decode() for i in (0, 12000)]
    _sync(page, [{"p": "twin.moy/manifest.json",
                  "t": json.dumps({"format": "moy-1", "title": "Twin %d" % k,
                                   "runtime": "python", "main": "main.py"})},
                 {"p": "twin.moy/main.py", "t": "# a line of a cart\n" * 600}])
    _sync(page, [{"p": "twin.moy/cover.png", "b": b64[0], "part": 0}])
    _sync(page, [{"p": "twin.moy/cover.png", "b": b64[1], "part": 1},
                 {"p": "twin.moy/cover.png", "pub": 1}])
    assert (twin.store / "carts" / "twin.moy" / "cover.png").read_bytes() == cover
    # Settings
    _sync(page, [{"p": "system/settings", "t": console["system/settings"]}], root="system")
    # Get Carts: the shelves (the page reads each shelf's index itself), an
    # install and its removal
    _ask(page, "/official", {"action": "check"})
    assert twin.shelf in _until(page, "/official", lambda d: "shelves" in d)["shelves"]
    _ask(page, "/official", {"action": "install", "folder": "target.moy", "index": twin.shelf})
    got = _until(page, "/official", lambda d: d["state"] in ("idle", "done", "asking") or d["error"])
    if got["state"] == "asking":
        _ask(page, "/official", {"action": "agree", "password": PASSWORD})
        got = _until(page, "/official", lambda d: d["state"] in ("idle", "done") or d["error"])
    assert not got["error"], got
    assert (twin.store / "carts" / "target.moy" / "level.bin").stat().st_size == 40000
    _ask(page, "/official", {"action": "remove", "folder": "target.moy"})
    assert not _until(page, "/official", lambda d: d["state"] in ("idle", "done") or d["error"])["error"]
    assert not (twin.store / "carts" / "target.moy").exists()
    # the Wi-Fi panel's scan
    _ask(page, "/wifi", {"action": "scan"})
    wifi = _until(page, "/wifi", lambda d: not d["scanning"])
    assert len(wifi["nets"]) == 12 and wifi["signal"] is None
    # an update check
    _ask(page, "/update", {"action": "check"})
    _until(page, "/update", lambda d: d.get("state") not in ("checking", "queued"))
    # the cart removed on the page
    _sync(page, [{"p": "twin.moy", "dc": 1}])


def _session(tmp_path, rounds, **kw):
    """[(free, held, run, modules)] after each round of one twin's session."""
    twin = Twin(tmp_path, **kw)
    try:
        page = seal_client.Browser(twin.send)
        page.pair_password(PASSWORD)
        out = [twin.heap("start")]
        # The twin compiles what a board has frozen, in a heap far larger
        # than a board's, so that its start ends as a board's does: with
        # what is free in one run. A twin that starts torn is not the board.
        assert out[0][0] - out[0][2] <= 1024, "the twin's own start left %d free in a run of %d" % (
            out[0][0], out[0][2])
        for k in range(rounds):
            _round(page, twin, k)
            time.sleep(2 * HOLD_MS / 1000)           # the panel closed
            out.append(twin.heap("round%d" % k))
        assert "MemoryError" not in twin.log(), twin.log()[-3000:]
        return out
    finally:
        twin.end()


def _verdict(rows):
    """Why the session's heap is not the start's, or None."""
    free0, held0, run0, _m = rows[0]
    for k, (free, held, run, mods) in enumerate(rows[1:], 1):
        if mods:
            return "round %d imported %s: a module made for good mid-session" % (k, mods)
        if held > held0 + KEPT:
            return "round %d holds %d bytes more than the start did" % (k, held - held0)
        if free - run > (free0 - run0) + TORN:
            return "round %d: %d bytes free, the largest run of them %d" % (k, free, run)
    return None


def _table(rows):
    return "\n".join("free %6d  held %+6d  run %6d  %s"
                     % (r[0], r[1] - rows[0][1], r[2], " ".join(r[3])) for r in rows)


def test_a_session_leaves_the_heap_as_the_start_left_it(tmp_path):
    rows = _session(tmp_path, ROUNDS)
    print("\n" + _table(rows))
    assert _verdict(rows) is None, _table(rows)


def test_a_heap_left_to_fill_before_it_collects_fails_the_same_session(tmp_path):
    """Rule 2 taken away (no step: the collect runs when the heap is full),
    the same session ends as the board's did: a request refused for want of
    memory with most of the heap free, or the free run torn. The twin sees
    the failure it is there for."""
    try:
        rows = _session(tmp_path, 3, step=-1)
    except AssertionError as refused:
        assert "emory" in str(refused), refused
        return
    assert "largest run" in (_verdict(rows) or ""), _table(rows)
