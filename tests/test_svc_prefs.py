"""An app's prefs rows shared by its service on the board and its window on
the page (native/moy_net/moy_svc_prefs.c, #256; moy_live.c's 'P').

The two ends are the one C file built twice, each loaded as its own library
with its own settings store (tests/svc_prefs/rows_twin.c), and the test
carries each end's 'P' plaintexts to the other as the live socket would.
What it holds: a row the service writes reaches the window's rows, in
pieces a frame holds when it is long; a row the window writes reaches the
board's; neither comes back; a delete crosses; another app's rows stay;
at a session's start the board's rows win over the page's."""

import ctypes
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NET = os.path.join(ROOT, "native", "moy_net")
SPINE = os.path.join(ROOT, "native", "moy_spine")
KERNEL = os.path.join(ROOT, "native", "moy_kernel")
TWIN = os.path.join(ROOT, "tests", "svc_prefs", "rows_twin.c")

pytestmark = pytest.mark.skipif(shutil.which("cc") is None, reason="needs a C compiler")

APPS = (ctypes.c_char_p * 1)(b"moymesh")
FRAME = 256                             # a small frame: a long row crosses in pieces
SAY = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8),
                       ctypes.c_size_t)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("svc_prefs")
    so = str(out / "end.so")
    subprocess.run([shutil.which("cc"), "-shared", "-fPIC", "-O1", "-std=gnu99", "-w",
                    "-D_GNU_SOURCE", "-DMOY_NET_LIVE_PAGE=1", "-DMOY_NET_LINK=1"]
                   + ["-I" + d for d in (NET, SPINE, KERNEL)]
                   + [os.path.join(NET, "moy_svc_prefs.c"), TWIN]
                   + [os.path.join(SPINE, n) for n in ("moy_settings.c", "moy_json.c", "moy_htab.c")]
                   + ["-o", so, "-lpthread"], check=True)
    return out, so


class End:
    def __init__(self, built, name, board):
        out, so = built
        path = str(out / ("%s.so" % name))
        shutil.copy(so, path)
        self.lib = lib = ctypes.CDLL(path)
        lib.twin_rows.restype = ctypes.c_void_p
        lib.twin_set.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        lib.twin_delete.argtypes = [ctypes.c_char_p]
        lib.twin_get.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t]
        lib.moy_svc_prefs_rows.argtypes = [ctypes.c_void_p]
        lib.moy_svc_prefs_baseline.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.moy_svc_prefs_scan.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                           ctypes.c_size_t, SAY, ctypes.c_void_p]
        lib.moy_svc_prefs_give.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p,
                                           ctypes.c_int]
        lib.moy_svc_prefs_rows(lib.twin_rows())
        lib.moy_svc_prefs_start(1 if board else 0)
        self.buf = ctypes.create_string_buffer(FRAME)

    def set(self, k, v):
        assert self.lib.twin_set(k.encode(), v.encode()) == 0

    def get(self, k):
        out = ctypes.create_string_buffer(70000)
        n = self.lib.twin_get(k.encode(), out, len(out))
        return None if n < 0 else out.raw[:n].decode()

    def scan(self):
        frames = []

        def say(_ctx, p, n):
            frames.append(ctypes.string_at(p, n))
            return 0

        cb = SAY(say)
        assert self.lib.moy_svc_prefs_scan(APPS, 1, self.buf, FRAME, cb, None) == 0
        return frames

    def give(self, frames):
        for f in frames:
            assert f[:2] == b"mP" and len(f) <= FRAME
            self.lib.moy_svc_prefs_give(f, len(f), APPS, 1)


def test_rows_cross_both_ways_and_never_come_back(built):
    board, page = End(built, "board", True), End(built, "page", False)
    page.set("moymesh_draft", '"mine"')
    page.lib.moy_svc_prefs_baseline(APPS, 1)
    board.set("moymesh_node", '"!20c410c7"')
    board.set("other_key", "1")
    page.give(board.scan())
    assert page.get("moymesh_node") == '"!20c410c7"'
    assert page.get("other_key") is None, "another app's row stays on the board"
    assert page.scan() == [], "a row taken is agreed on, and does not go back"
    log = "[" + ",".join('{"text":"message %d","t":%d}' % (i, i) for i in range(60)) + "]"
    board.set("moymesh_log", log)
    frames = board.scan()
    assert len(frames) > 3, "a long row crosses in pieces"
    page.give(frames)
    assert page.get("moymesh_log") == log
    page.set("moymesh_region", '"EU_868"')
    board.give(page.scan())
    assert board.get("moymesh_region") == '"EU_868"'
    assert board.scan() == []
    board.lib.twin_delete(b"moymesh_node")
    page.give(board.scan())
    assert page.get("moymesh_node") is None, "a delete crosses"


def test_at_a_session_s_start_the_board_s_rows_win(built):
    board, page = End(built, "board2", True), End(built, "page2", False)
    board.set("moymesh_log", "[1]")
    page.set("moymesh_log", "[0]")
    page.lib.moy_svc_prefs_baseline(APPS, 1)
    page.give(board.scan())
    assert page.get("moymesh_log") == "[1]"
    assert page.scan() == []
