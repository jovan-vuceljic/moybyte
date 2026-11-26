"""The live socket's apps' messages (#256; native/moy_net/moy_live.c's THE
APPS' MESSAGES): an app's window on the page and its service on the board
exchange the `send`/`on` messages they exchange on one device.

The board twin is tests/test_live_link.py's, built with the kernel's event
queues and the channel's board half (moy_live_svc.c), running tty_main's
FIXTURE SERVICE of app "echo" (MOY_TTY_SVC: "ping" answered "pong", the OS
message "page" answered "seen"). The page is the browser's C: its link's
queue (moy_link_web.c), the channel's page half (moy_svc_web.c) and the
kernel's queues, loaded as a library; the window is a process of app "echo"
on it, as the Python scheduler opens one; the worker's job is done by hand.

What it holds: the board's apps reach the page; a window's send reaches the
service and its answer the window, from the app itself; the service hears
the page come and go; a dropped socket is said to the window, a send
meanwhile reaches nobody, and the reopened socket carries messages again.
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import test_live_dev as D  # noqa: E402
import test_live_link as L  # noqa: E402
import test_moy_tty as T  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("cc") is None, reason="needs a C compiler")

APP = b"echo"
WIN = 7


@pytest.fixture(scope="module")
def twin_exe(tmp_path_factory):
    out = tmp_path_factory.mktemp("live_svc")
    return T._build(out, extra=[os.path.join(T.NET, "moy_live.c"),
                                os.path.join(T.NET, "moy_live_svc.c"),
                                os.path.join(T.NET, "moy_link_host.c")] + D.TABLE,
                    defines=("MOY_NET_LIVE=1", "MOY_NET_LINK=1", "MOY_TTY_LEASES=1",
                             "MOY_TTY_SVC=1"),
                    incs=(D.KERNEL, D.INPUT))


@pytest.fixture(scope="module")
def page_so(tmp_path_factory):
    out = tmp_path_factory.mktemp("page_svc")
    so = str(out / "page_svc.so")
    subprocess.run([shutil.which("cc"), "-shared", "-fPIC", "-O1", "-std=gnu99", "-w",
                    "-D_GNU_SOURCE", "-DMOY_NET_LINK=1", "-DMOY_NET_LIVE_PAGE=1"]
                   + ["-I" + d for d in (T.NET, D.KERNEL, D.INPUT, T.SPINE, T.STORE)]
                   + [os.path.join(T.NET, n) for n in ("moy_link_web.c", "moy_svc_web.c",
                                                       "moy_svc_prefs.c")]
                   + [os.path.join(T.SPINE, n) for n in ("moy_settings.c", "moy_json.c")]
                   + [os.path.join(D.KERNEL, "moy_log.c")] + D.TABLE + ["-o", so, "-lpthread"],
                   check=True)
    return so


class Window:
    """A window of app "echo" on the page: its process's queue, listening as
    a window's `moybyte.on` does."""

    def __init__(self, lib):
        self.lib = lib
        U, I, Z, B = ctypes.c_uint32, ctypes.c_int, ctypes.c_size_t, ctypes.c_char_p
        for fn, args, res in (
                ("moy_evq_open", [U, B, B, U], I), ("moy_evq_listen", [U, B, ctypes.c_bool], I),
                ("moy_evq_step", [U], U),
                ("moy_evq_take", [U, ctypes.POINTER(D._Ev), B, Z], I),
                ("moy_evq_send_text", [U, B, Z, B, Z, B, Z, ctypes.POINTER(U)], I),
                ("moy_link_web_take", [B, Z], Z), ("moy_link_web_give", [B, Z], None),
                ("moy_link_web_open", [I], None)):
            f = getattr(lib, fn)
            f.argtypes = args
            f.restype = res
        assert lib.moy_evq_open(WIN, APP, None, 0) == 0
        for name in (b"pong", b"seen", b"board"):
            assert lib.moy_evq_listen(WIN, name, True) == 0
        self.got = []

    def send(self, name, args):
        took = ctypes.c_uint32()
        a = json.dumps(args).encode()
        rc = self.lib.moy_evq_send_text(WIN, APP, len(APP), name, len(name), a, len(a),
                                        ctypes.byref(took))
        return rc, took.value

    def take(self):
        ev, args = D._Ev(), ctypes.create_string_buffer(512)
        self.lib.moy_evq_step(WIN)
        while self.lib.moy_evq_take(WIN, ctypes.byref(ev), args, 512) == 0:
            self.got.append((ev.app.decode(), ev.name.decode(), json.loads(args.value.decode())))
        return self.got


@pytest.fixture
def board(twin_exe, tmp_path, monkeypatch):
    air = L.Air()
    monkeypatch.setenv("MOY_TTY_SVC", APP.decode())
    h = L._twin(twin_exe, tmp_path, monkeypatch, air, L.MAC_A, sealed=True)
    yield h
    h.end()
    air.close()


def _until(page, win, cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        page.pump()
        if cond(win.take()):
            return True
        time.sleep(0.01)
    return False


def test_a_window_s_message_reaches_its_service_and_the_answer_comes_back(board, page_so,
                                                                          tmp_path):
    lib = L._page_lib(page_so, "p", str(tmp_path))
    win = Window(lib)
    page = L.Page(board, lib, True).open()
    assert _until(page, win, lambda g: ("system", "board", [1]) in g), win.got
    assert _until(page, win, lambda g: ("echo", "seen", [1]) in g), \
        "the service heard the page come: %s" % win.got
    rc, took = win.send(b"ping", [42, "hi"])
    assert rc == 0 and took == 1, "the page's stand-in of the board's echo took it"
    assert _until(page, win, lambda g: ("echo", "pong", [42, "hi"]) in g), win.got
    live = D._live(board)
    assert int(live["msgs_up"]) >= 1 and int(live["msgs_down"]) >= 2, live


def test_a_dropped_socket_is_said_and_a_send_meanwhile_reaches_nobody(board, page_so,
                                                                      tmp_path):
    lib = L._page_lib(page_so, "q", str(tmp_path))
    win = Window(lib)
    page = L.Page(board, lib, True).open()
    assert _until(page, win, lambda g: ("system", "board", [1]) in g), win.got
    page.drop()
    assert ("system", "board", [0, "lost"]) in win.take(), win.got
    assert win.send(b"ping", [1]) == (0, 0), "no stand-in: nobody took it"
    win.got.clear()
    page.open()
    assert _until(page, win, lambda g: ("system", "board", [1]) in g), win.got
    win.send(b"ping", [2])
    assert _until(page, win, lambda g: ("echo", "pong", [2]) in g), win.got
    assert ("echo", "pong", [1]) not in win.got, "a send with no socket went nowhere, said"
