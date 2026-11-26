#!/usr/bin/env python3
"""Serve the web runner's dist/ statically for local testing.

Plain `python -m http.server` minus two gotchas: .mjs must ship as
text/javascript (older CPython mimetypes map it to text/plain, which browsers
refuse for ES modules) and .wasm as application/wasm (streaming compile).

    python serve.py [port] [dir]            # defaults: 8321, dist/
                                            # dir may be absolute (the _site build);
                                            # this tree's dist/ built before a
                                            # commit to what it bakes is named
                                            # STALE on stderr (tools/web.py)
    python serve.py [port] [dir] --carts D  # BOARD-TWIN mode: serve carts.json
                                            # (and files.json, the #108 layer
                                            # beside D) LIVE and accept POST
                                            # /sync back into either -- the same
                                            # pull+push pair moy_webhost serves
                                            # on a board, against a plain
                                            # directory. The no-hardware way to
                                            # watch a browser edit land as files
                                            # on disk. The console's own
                                            # documents beside D
                                            # (system/settings, the badges
                                            # among its rows) are the
                                            # board's too: GET /console.json,
                                            # and a system batch merged key by
                                            # key (moy_sync.SYSTEM_KEYS). So
                                            # are the apps' folders beside D:
                                            # GET /apps.json, an apps batch.
    python serve.py ... --carts D --update glass|headless
                                            # ...and a board's FIRMWARE routes
                                            # (GET/POST /update) on top, faked.
                                            # `headless` is a Zero -- the page
                                            # IS its update screen, so the
                                            # whole check/offer/download/
                                            # install/reboot arc plays out
                                            # there. `glass` is a console: the
                                            # trigger hands its own screen back
                                            # and this page stops being it.
    python serve.py ... --carts D --official R
                                            # ...and a Zero's /official on top:
                                            # the board's own backend
                                            # (web_addon.OfficialCarts) with D
                                            # as its store and R as its
                                            # release (R/twin.json names the
                                            # index, the page digest it fits
                                            # and the keys it is signed with),
                                            # stepped in the background as a
                                            # board's poll steps it.
    python serve.py ... --carts D --wifi W  # ...and a Zero's /wifi on top: the
                                            # board's own backend
                                            # (zero_wifi.ZeroWifi) over a fake
                                            # radio whose networks W names
                                            # ({"on": SSID, "nets": [{"ssid",
                                            # "password", "rssi"}], "join_ms",
                                            # "back_ms"}), its saved networks
                                            # D/../wifi.json. While the radio
                                            # is off the network it started
                                            # on, every request is dropped
                                            # unanswered: the page reached it
                                            # over that one.
    python serve.py ... --carts D --one-link  # ...over a board's LINK: one
                                            # connection at a time, each send
                                            # held to the board's budget
                                            # (moy_net.h's MOY_HTTP_SEND_MS),
                                            # so a request waits behind the
                                            # one being served and a client
                                            # that stops reading is cut off,
                                            # as on glass.
    python serve.py ... --carts D --no-system  # ...as a board flashed before
                                            # the system root: /console.json
                                            # 404s and a system batch is
                                            # refused 400, as that firmware's
                                            # C refuses it ("bad batch").
    python serve.py ... --carts D --loader  # ...as a board whose console is
                                            # online: `/` is the loader
                                            # (firmware/web_runner/loader.html)
                                            # naming this server as its one
                                            # mirror, and GET /sync names the
                                            # pack's digests with `local` 0.
                                            # The no-hardware way to boot the
                                            # console through the loader.
    python serve.py ... --loader --mirror URL...  # ...naming URL as its
                                            # mirrors instead, whose origins
                                            # are the sites its link takes
                                            # (docs/web_console_online_2026-11.md
                                            # §5): My consoles on a local
                                            # tools/os_site.py serve.

Every mode serves the pack of the bundle it serves (tools/gen_web_blob.py's,
the one a board build of this tree names) at /console/<body digest>.pack with
`Access-Control-Allow-Origin: *`, as os.moybyte.com serves the published ones
(docs/web_console_online_2026-11.md §4): a board built here names this server
on its LAN address (gen_web_blob.default_mirrors), so its loader reaches a
pack no site publishes.

    python serve.py [port] [dir] --board HOST:PORT  # ...the bundle from
                                            # here and every other request,
                                            # bytes both ways, to a REAL C
                                            # webhost (native/moy_tty's host
                                            # harness, tests/test_moy_tty.py):
                                            # its sign-in, its sealed routes
                                            # and its shell on GET /term. The
                                            # twin modes above are an open
                                            # host (no sign-in, as a host with
                                            # no system folder is); the sign-in
                                            # is driven here, against the
                                            # board's own C, never a copy.
                                            # With --loader, `/` is the
                                            # loader, and the board names
                                            # the pack (the harness's
                                            # MOY_TTY_PAGE).

Bind the directory by PATH, never by chdir. Every build here REPLACES its output
folder (build.sh and site/build.py both remove and recreate it), and a server
sitting inside the old one keeps a deleted inode as its cwd: the socket stays
open, and every request then dies in os.getcwd() with FileNotFoundError. Binding
by path re-resolves per request, so a rebuild mid-session is invisible.
"""

import functools
import hashlib
import http.server
import json
import os
import sys
import threading
import time

_here = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:]]
carts_dir = None
if "--carts" in args:
    i = args.index("--carts")
    carts_dir = os.path.abspath(args[i + 1])
    del args[i:i + 2]
update_mode = None
if "--update" in args:
    i = args.index("--update")
    update_mode = args[i + 1]
    del args[i:i + 2]
    if update_mode not in ("glass", "headless"):
        raise SystemExit("--update takes glass or headless")
    if "--carts" not in sys.argv:
        # The firmware routes ride the BOARD-TWIN handler; without --carts this
        # is a plain static server and the flag would be accepted and ignored,
        # which is how a scenario ends up testing nothing.
        raise SystemExit("--update needs --carts (it is part of the board twin)")
# THE GOODBYE, on a timer. A board that is going away on purpose -- WEB CONSOLE
# switched off, an update about to reboot -- keeps answering for a few seconds
# to SAY so (moy_webhost.stop's closing window), because from the browser a
# deliberate shutdown and an unplugged board look identical. `--close-after N`
# makes this twin do the same N seconds in, which is the only way to drive that
# path from a browser test: killing the process proves the opposite case.
close_after = None
_started = time.time()
if "--close-after" in args:
    i = args.index("--close-after")
    close_after = float(args[i + 1])
    del args[i:i + 2]
official_dir = None
if "--official" in args:
    i = args.index("--official")
    official_dir = os.path.abspath(args[i + 1])
    del args[i:i + 2]
    if "--carts" not in sys.argv:
        raise SystemExit("--official needs --carts (it is part of the board twin)")
wifi_file = None
if "--wifi" in args:
    i = args.index("--wifi")
    wifi_file = os.path.abspath(args[i + 1])
    del args[i:i + 2]
    if "--carts" not in sys.argv:
        raise SystemExit("--wifi needs --carts (it is part of the board twin)")
no_system = "--no-system" in args
if no_system:
    args.remove("--no-system")
    if "--carts" not in sys.argv:
        raise SystemExit("--no-system needs --carts (it is part of the board twin)")
one_link = "--one-link" in args
if one_link:
    args.remove("--one-link")
    if "--carts" not in sys.argv:
        raise SystemExit("--one-link needs --carts (it is part of the board twin)")
loader_twin = "--loader" in args
if loader_twin:
    args.remove("--loader")
    if "--carts" not in sys.argv and "--board" not in sys.argv:
        raise SystemExit("--loader needs --carts or --board (it is part of a board)")
mirrors = []
while "--mirror" in args:
    i = args.index("--mirror")
    mirrors.append(args[i + 1])
    del args[i:i + 2]
if mirrors and not loader_twin:
    raise SystemExit("--mirror needs --loader (it names the loader's mirrors)")
mirrors = mirrors or ["/console/"]
board_to = None
if "--board" in args:
    i = args.index("--board")
    h, _, p = args[i + 1].rpartition(":")
    board_to = (h or "127.0.0.1", int(p))
    del args[i:i + 2]
    if "--carts" in sys.argv:
        raise SystemExit("--board takes no --carts: the board serves its own store")
root = os.path.join(_here, args[1] if len(args) > 1 else "dist")
port = int(args[0]) if args else 8321
if os.path.realpath(root) == os.path.realpath(os.path.join(_here, "dist")):
    try:
        sys.path.insert(0, os.path.join(_here, "..", "..", "tools"))
        from web import behind_note
        _stale = behind_note(root, os.path.join(_here, "..", ".."))
    except ImportError:
        _stale = None
    if _stale:
        print(_stale, file=sys.stderr, flush=True)

http.server.SimpleHTTPRequestHandler.extensions_map[".mjs"] = "text/javascript"
http.server.SimpleHTTPRequestHandler.extensions_map[".js"] = "text/javascript"
http.server.SimpleHTTPRequestHandler.extensions_map[".wasm"] = "application/wasm"

sys.path.insert(0, os.path.join(_here, "..", "..", "tools"))
import gen_web_blob                                     # noqa: E402

_pack = {"key": None}


def dist_pack():
    """(pack bytes, body hex, whole hex) of the bundle served here, packed as
    a board build packs it, or None where the bundle is incomplete; made
    again when an asset changes."""
    assets, missing = gen_web_blob.collect(root)
    if missing:
        return None
    key = tuple((a[1], os.path.getmtime(a[1])) for a in assets)
    if _pack["key"] != key:
        data, body = gen_web_blob.pack(assets)
        _pack.update(key=key, got=(data, body.hex(),
                                   hashlib.sha256(data).hexdigest()))
    return _pack["got"]


def serve_pack(h, path):
    """Answer GET /console/<body digest>.pack on handler `h`: True when the
    path is one, answered."""
    if not (path.startswith("/console/") and path.endswith(".pack")):
        return False
    got = dist_pack()
    hit = got is not None and path == "/console/%s.pack" % got[1]
    body = got[0] if hit else b"not found"
    h.send_response(200 if hit else 404)
    h.send_header("Content-Type", "application/octet-stream" if hit else "text/plain")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Cache-Control", "public, max-age=31536000, immutable" if hit
                  else "no-store")
    h.end_headers()
    h.wfile.write(body)
    return True


def serve_loader(h, path):
    """Answer the loader's paths on handler `h` as a board whose console is
    online does: True when the path is one, answered."""
    if not (loader_twin and path in ("/", "/index.html", "/loader.html")):
        return False
    body = gen_web_blob.loader_page(mirrors).encode()
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-cache")
    h.end_headers()
    h.wfile.write(body)
    return True


class Static(http.server.SimpleHTTPRequestHandler):
    """A static host, as the site's (GitHub Pages) serves: a file whose
    build left its gzip beside it (build.sh) goes as that gzip, labelled,
    to a browser that takes gzip -- the wasm crosses a LAN at half its size,
    as it does from the site."""

    def do_GET(self):
        if not serve_pack(self, self.path.split("?", 1)[0]):
            super().do_GET()

    def end_headers(self):
        # A rebuilt dist is served at the same names: a browser that kept a
        # file by its own heuristic would pair an old wasm with a new worker.
        if not self._headers_buffer or b"Cache-Control" not in b"".join(
                self._headers_buffer):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def send_head(self):
        path = self.translate_path(self.path)
        gz = path + ".gz"
        if ("gzip" not in (self.headers.get("Accept-Encoding") or "")
                or not os.path.isfile(path) or not os.path.isfile(gz)):
            return super().send_head()
        f = open(gz, "rb")
        st = os.fstat(f.fileno())
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(st.st_size))
        self.send_header("Last-Modified", self.date_time_string(st.st_mtime))
        self.end_headers()
        return f


if carts_dir is None:
    handler = functools.partial(Static, directory=root)
else:
    _repo = os.path.dirname(os.path.dirname(_here))
    sys.path.insert(0, _repo)
    sys.path.insert(0, os.path.join(_repo, "device"))   # flat sibling imports
    import moy_webhost                                  # noqa: E402
    # A board's send budget: native/moy_net/moy_net.h's MOY_HTTP_SEND_MS.
    WEB_SEND_TIMEOUT = 2.0
    # The twin's piece of a body over `--one-link`. A board's is the kernel
    # webhost's chunk; this is bigger only so a loopback link moves a
    # big store at a rate a test can wait for -- the budget per piece, which is
    # what cuts a client off, is the board's own.
    _LINK_CHUNK = 65536
    from runtime import moy_sync                        # noqa: E402

    class TwinConsole(moy_webhost.StoreSystem):
        """The board's Settings, the badges among them, as a board keeps them
        beside its carts (D/../system/settings), merged through the Zero's
        own body (moy_webhost.StoreSystem): what a page served by this twin
        may change is moy_sync.SYSTEM_KEYS'. One request at a time."""

        def __init__(self, carts):
            import threading
            super().__init__(carts)
            self.lock = threading.Lock()

        def pull(self):
            with self.lock:
                return super().pull()

        def apply(self, ops):
            with self.lock:
                return super().apply(ops)

    console = None if no_system else TwinConsole(carts_dir)

    class _TwinOta:
        """The handful of things `moy_webhost.update_status` asks an updater."""

        def __init__(self):
            self.boot_verdict = None

        def version(self):
            return 5

        def version_label(self):
            return "0.8"

        def channel(self):
            return "stable"

        def slot(self):
            return "ota_0"

    class TwinUpdate:
        """A SCRIPTED /update backend -- the wire SHAPE, not a state machine.

        The document goes through `moy_webhost.update_status`, the one body
        both real backends call, so a twin cannot drift from a board about what
        the page reads. What is faked is the behaviour behind it, and it is
        faked DETERMINISTICALLY: a request is answered without doing it (as a
        board's is -- the work happens in its poll loop), and the next STATUS
        READ is what advances things. That is what lets a browser walk the
        whole check -> offer -> download -> install -> reboot arc in a bounded
        number of polls with no board, no network and no clock.

        `screen` is the whole difference between the two modes, and it is the
        difference between the two real backends too: with glass, a trigger
        hands the glass back and this page stops being the console; without,
        this page is the only place the update can be watched.
        """

        DL_TOTAL = 2100000
        SLICES = 3

        def __init__(self, screen):
            self.screen = screen
            self.ota = _TwinOta()
            self.state = "idle"
            self.error = None
            self._want = None
            self._n = 0

        def request(self, action):
            if action not in ("check", "install", "cancel"):
                return False, "action must be check, install or cancel"
            if action == "cancel":
                self.state = "idle"
                self._want = None
                return True, "cancelled"
            if self.screen:
                if self.state == "glass":
                    return False, "the console already has this on its screen"
                self._want = "glass"
                return True, "the console took this onto its own screen"
            if self.state in ("downloading", "installing", "reboot"):
                return False, "busy: " + self.state
            self._want = "install" if action == "install" else "check"
            return True, "queued"

        def _advance(self):
            """One slice, taken on a status READ (a board takes it in its own
            poll loop; this twin has none)."""
            want, self._want = self._want, None
            if want == "glass":
                self.state = "glass"
                return
            if want == "check":
                self.state = "offer"
                return
            if want == "install":
                self.state = "downloading"
                self._n = 0
                return
            if self.state == "downloading":
                self._n += 1
                if self._n >= self.SLICES:
                    self.state = "installing"
                    self._n = 0
            elif self.state == "installing":
                self._n += 1
                if self._n >= self.SLICES:
                    self.state = "reboot"

        def status(self, advance=True):
            if advance:
                self._advance()
            offer = progress = None
            if self.state in ("offer", "downloading", "installing"):
                offer = {"version": 6, "label": "0.9", "channel": "stable",
                         "size": self.DL_TOTAL}
            if self.state == "downloading":
                progress = {"done": self._n * self.DL_TOTAL // self.SLICES,
                            "total": self.DL_TOTAL}
            elif self.state == "installing":
                progress = {"done": self._n * self.DL_TOTAL // self.SLICES,
                            "total": self.DL_TOTAL}
            return moy_webhost.update_status(
                self.ota, self.state, self.screen, error=self.error,
                offer=offer, progress=progress)

    update = TwinUpdate(update_mode == "glass") if update_mode else None

    def twin_official(release, carts):
        """`--official`: the board's own /official backend over this twin's
        store, its release a directory, stepped in a thread a slice at a
        time as a board's poll steps it. (backend, lock)."""
        import io
        from runtime import cart_index, web_addon
        with open(os.path.join(release, "twin.json")) as f:
            cfg = json.load(f)
        cart_index.INDEX_KEYS = tuple(tuple(k) for k in cfg["keys"])
        cart_index.page_want = lambda: cfg["want"]
        base = "http://release.invalid/"

        class Resp:
            def __init__(self, data, status=200):
                self._b = io.BytesIO(data)
                self.status = status
                self.length = len(data)

            def readinto(self, buf):
                return self._b.readinto(buf)

            def close(self):
                pass

        class Net:
            def online(self):
                return True

            def open(self, url):
                name = url[len(base):] if url.startswith(base) else ""
                path = os.path.join(release, name)
                if not name or "/" in name or not os.path.isfile(path):
                    return Resp(b"not found", 404)
                with open(path, "rb") as f:
                    return Resp(f.read())

        class Inst:
            net_ = Net()

            def net(self):
                return self.net_

            def root(self):
                return carts

            def op(self, fn):
                return fn()

            def chip(self):
                return None, None

            def hold(self):
                return True

            def release(self):
                pass

            def rescan(self, folder=None):
                pass

        backend = web_addon.OfficialCarts(Inst(), base + cfg["index"])
        lock = threading.Lock()

        def pump():
            while True:
                with lock:
                    more = backend.busy() and backend.step(40)
                time.sleep(0.005 if more else 0.05)
        threading.Thread(target=pump, daemon=True).start()
        return backend, lock

    official = twin_official(official_dir, carts_dir) if official_dir else None

    class TwinRadio:
        """moy_net's wifi functions over the networks `--wifi` names: a
        join takes `delay` seconds and comes up where the network is named
        and its password matches; a wrong password is refused (reason 15),
        a network not named never answers (201), as a station's would."""

        def __init__(self, doc):
            self.nets = {n["ssid"]: n for n in doc.get("nets") or ()}
            self.delay = float(doc.get("delay", 0.8))
            self.ssid = doc.get("on")
            self.up = self.ssid in self.nets
            self.want = None
            self.at = 0.0
            self.reason = 0
            self.scan_at = None

        def _tick(self):
            if self.want is None or time.time() < self.at:
                return
            ssid, pw = self.want
            n = self.nets.get(ssid)
            if n is not None and (n.get("password") or "") == pw:
                self.ssid, self.up, self.want = ssid, True, None
            else:
                self.reason = 15 if n is not None else 201

        def wifi_status(self):
            self._tick()
            return (True, True, self.up, self.ssid if self.up else None,
                    "10.0.%d.2" % (sorted(self.nets).index(self.ssid) + 1)
                    if self.up else None, self.reason, True)

        def wifi_scan(self, wait=True):
            if self.scan_at is None:
                self.scan_at = time.time()
            if not wait and time.time() - self.scan_at < 0.5:
                return None
            self.scan_at = None
            return [(n["ssid"].encode(), int(n.get("rssi", -60)),
                     3 if n.get("password") else 0) for n in self.nets.values()]

        def wifi_connect(self, ssid, password):
            self.up = False
            self.want = (ssid, password or "")
            self.at = time.time() + self.delay
            self.reason = 0

        def wifi_disconnect(self):
            self.up = False
            self.want = None

        def wifi_mdns(self, name):
            return True

    def twin_wifi(path, carts):
        """`--wifi`: the board's own /wifi backend over a TwinRadio,
        stepped in the background as a board's poll steps it; and the
        network the page reached the twin over."""
        import zero_wifi
        with open(path) as f:
            doc = json.load(f)
        radio = TwinRadio(doc)
        backend = zero_wifi.ZeroWifi(
            os.path.join(os.path.dirname(carts), "wifi.json"), "moybyte-twin",
            radio=radio, join_ms=int(doc.get("join_ms", 3000)),
            back_ms=int(doc.get("back_ms", 3000)))
        lock = threading.Lock()

        def pump():
            while True:
                with lock:
                    if backend.busy():
                        backend.step()
                time.sleep(0.05)
        threading.Thread(target=pump, daemon=True).start()
        return backend, lock, radio, doc.get("on")

    wifi = twin_wifi(wifi_file, carts_dir) if wifi_file else None

    def wifi_away():
        """True while the twin's radio is off the network the page reached
        it over: a request then reaches nothing."""
        if wifi is None:
            return False
        with wifi[1]:
            st = wifi[2].wifi_status()
        return not (st[2] and st[3] == wifi[3])

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if not one_link:
                self.wfile.write(body)
                return
            # A board's send: piece by piece, each held to the send budget
            # (the handler's `timeout`), so a client that stops reading for
            # longer than that is cut off mid-body.
            mv = memoryview(body)
            for at in range(0, len(mv), _LINK_CHUNK):
                self.wfile.write(mv[at:at + _LINK_CHUNK])

        def _closing(self):
            """True (and the 503 already sent) once the goodbye window opens.

            Ahead of routing AND ahead of the sign-in, exactly as the board
            does it: a page that never signed in still deserves to know the
            console was switched off rather than be left to decide it vanished.
            """
            if close_after is None or (time.time() - _started) < close_after:
                return False
            self._send(503, b'{"error":"closing","why":"off"}')
            return True

        def _away(self):
            """Dropped unanswered while the radio is elsewhere (`--wifi`)."""
            if not wifi_away():
                return False
            self.close_connection = True
            return True

        def do_GET(self):
            if self._closing() or self._away():
                return
            path = self.path.split("?", 1)[0]
            if serve_pack(self, path):
                return
            if path == "/sync":
                # The MODE MARKER (#193): a host that answers this owns the
                # carts, so the page keeps nothing locally. Static hosting
                # 404s here, which is how moybyte.com gets a browser store.
                # Open on a board too: it says a board lives here and nothing
                # else, and the page decides its mode before it signs in.
                # As an online board, it names the digests the loader checks.
                got = dist_pack() if loader_twin else None
                self._send(200, json.dumps(
                    {"sync": 1, "page": got[1], "pack": got[2], "local": 0}).encode()
                    if got else b'{"sync":1}')
                return
            if serve_loader(self, path):
                return
            if path == "/carts.json":
                # The board's own packer, over a plain directory -- one body,
                # so this twin cannot drift from what a board serves.
                body = json.dumps(moy_webhost.pack_store(carts_dir)).encode()
                self._send(200, body)
                return
            if path == "/files.json":
                # The #108 user files beside the carts, kind-filtered so
                # .history/ and trash/ stay home -- and serving this at all is
                # what tells the page this twin speaks files.
                body = json.dumps(moy_webhost.pack_store(
                    moy_sync.files_root(carts_dir),
                    tops=moy_sync.file_folders())).encode()
                self._send(200, body)
                return
            if path == moy_sync.APPS_ROOT.endpoint:
                # The apps' private folders, every file as bytes.
                body = json.dumps(moy_webhost.pack_store(
                    moy_sync.apps_root(carts_dir), binary=True)).encode()
                self._send(200, body)
                return
            if path == moy_sync.SYSTEM_PULL and console is not None:
                # The console's own documents, as a board's VM answers them.
                self._send(200, json.dumps(console.pull()).encode())
                return
            if path == "/update":
                if update is None:
                    self._send(404, b'{"error":"not found"}')
                    return
                self._send(200, json.dumps(update.status()).encode())
                return
            if path == "/official" and official is not None:
                with official[1]:
                    self._send(200, official[0].answer().encode())
                return
            if path == "/wifi" and wifi is not None:
                with wifi[1]:
                    self._send(200, wifi[0].answer().encode())
                return
            super().do_GET()          # the boot assets: never gated

        def do_POST(self):
            if self._closing() or self._away():
                return
            path = self.path.split("?", 1)[0]
            if path == "/update":
                if update is None:
                    self._send(404, b'{"error":"not found"}')
                    return
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    doc = json.loads(self.rfile.read(n) or b"{}")
                    action = doc.get("action") or "check"
                except ValueError:
                    self._send(400, b'{"error":"bad json"}')
                    return
                ok, msg = update.request(action)
                # ANSWERED WITHOUT ADVANCING, like a board: the request is
                # queued and the reader is what sees it happen.
                out = update.status(advance=False)
                out["ok"] = ok
                out["message"] = msg
                self._send(200 if ok else 409, json.dumps(out).encode())
                return
            if path == "/official" and official is not None:
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    doc = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    self._send(400, b'{"error":"bad json"}')
                    return
                with official[1]:
                    ok, msg = official[0].request(doc.get("action") or "",
                                                  doc.get("folder"), doc)
                    body = official[0].answer(ok, msg).encode()
                self._send(200 if ok else 409, body)
                return
            if path == "/wifi" and wifi is not None:
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    doc = json.loads(self.rfile.read(n) or b"{}")
                    doc.get("action")
                except (ValueError, AttributeError):
                    self._send(400, b'{"error":"bad json"}')
                    return
                with wifi[1]:
                    ok, msg = wifi[0].request(doc)
                    body = wifi[0].answer(ok, msg).encode()
                self._send(200 if ok else 409, body)
                return
            if path == "/auth":
                # An open host says so, as a board with no system folder
                # does: a page that holds no key believes it, and only then.
                self._send(200, b'{"v":1,"open":true}')
                return
            if path != "/sync":
                self._send(404, b'{"error":"not found"}')
                return
            n = int(self.headers.get("Content-Length") or 0)
            ops, root_id = moy_sync.parse_batch(self.rfile.read(n))
            if ops is None:
                self._send(400, b'{"error":"bad batch"}')
                return
            if root_id == moy_sync.SYSTEM_ROOT_ID:
                if console is None:
                    print("sync: system batch refused (no system root)",
                          flush=True)
                    self._send(400, b'{"error":"bad batch"}')
                    return
                # Merged key by key into the twin's Settings and badges, as a
                # board's VM merges the batch its C parked.
                applied, errors = console.apply(ops)
                print("sync: system %d applied" % applied, flush=True)
                self._send(200, json.dumps(
                    {"ok": applied, "err": [list(e) for e in errors]}).encode())
                return
            target = moy_sync.root_by_id(root_id).path(carts_dir)
            # JOURNALED, like a board's apply: this directory is the store of
            # record for the page it serves, so a browser commit lands in the
            # cart's own journal/ here too (moy_sync's docstring has the
            # doctrine). It is also what lets the E2E prove the journal half
            # with no hardware.
            applied, errors, _ = moy_sync.apply_ops(target, ops, root_id,
                                                    journal=True)
            if errors:
                print("sync: %d applied, %d refused: %s"
                      % (applied, len(errors), errors[0][1]))
            self._send(200, json.dumps(
                {"ok": applied, "err": [list(e) for e in errors[:8]]}).encode())

    if one_link:
        Handler.timeout = WEB_SEND_TIMEOUT

    handler = Handler

if board_to is not None:
    import socket

    class BoardHandler(http.server.SimpleHTTPRequestHandler):
        """The bundle from this folder; anything it does not hold, the board's."""

        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def log_message(self, *a):
            pass

        def _asset(self):
            path = self.path.split("?", 1)[0].split("#", 1)[0]
            local = self.translate_path(path)
            # The store is the board's, sealed: the bundle's seed carts.json
            # never stands in for it.
            if path in ("/carts.json", "/files.json", "/apps.json"):
                return False
            return path == "/" or os.path.isfile(local)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if serve_pack(self, path) or serve_loader(self, path):
                return
            if self._asset():
                super().do_GET()
            else:
                self._pipe()

        def do_POST(self):
            self._pipe()

        def _pipe(self):
            """The request as it came, to the board, and then the two sockets
            joined until either side closes (a /term upgrade's stream too)."""
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            try:
                up = socket.create_connection(board_to, timeout=5)
            except OSError:
                self.send_error(502)
                return
            up.settimeout(None)
            head = self.requestline + "\r\n" + "".join(
                "%s: %s\r\n" % kv for kv in self.headers.items()) + "\r\n"
            up.sendall(head.encode() + body)
            down = self.connection

            def pipe(a, b):
                try:
                    while True:
                        d = a.recv(65536)
                        if not d:
                            break
                        b.sendall(d)
                except OSError:
                    pass
                try:
                    b.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

            t = threading.Thread(target=pipe, args=(down, up), daemon=True)
            t.start()
            pipe(up, down)
            t.join(2)
            up.close()
            self.close_connection = True

    handler = BoardHandler

server_class = http.server.HTTPServer if one_link else http.server.ThreadingHTTPServer
with server_class(("0.0.0.0", port), handler) as srv:
    note = (" + carts/sync over %s" % carts_dir) if carts_dir else ""
    if update_mode:
        note += " + a faked /update (%s)" % update_mode
    if official_dir:
        note += " + /official from %s" % official_dir
    if wifi_file:
        note += " + /wifi over %s" % wifi_file
    if one_link:
        note += " over one link at a time"
    if loader_twin:
        note += " + the loader at /"
    if board_to:
        note += " + the board at %s:%d" % board_to
    print("serving %s at http://127.0.0.1:%d/%s" % (root, port, note))
    srv.serve_forever()
