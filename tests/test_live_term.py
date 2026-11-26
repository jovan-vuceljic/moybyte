"""The web terminal on the live socket (native/moy_tty/moy_tty_live.c; the
wire is native/moy_net/moy_live.c's header): a board that builds the live
socket serves its page's shell on that socket's 't' channel and no GET /term,
so a page holds one socket and one session.

The board twin is tests/test_live_link.py's (the web terminal's host harness
with the live socket); the page is its socket, the worker's job done by hand.

What it holds: the probe says the shell is there and /term is not; a face
opens with its size, takes keys and a resize and answers; its exit says its
status; a close and a reopen give a fresh prompt; another page's socket
taking the session ends the first's face and its own opens; the face
another transport holds answers busy.
"""
import os
import shutil
import struct
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import test_live_dev as D  # noqa: E402
import test_live_link as L  # noqa: E402
import seal_client  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("cc") is None, reason="needs a C compiler")

twin_exe = L.twin_exe
page_so = L.page_so
air = D.air


@pytest.fixture
def board(twin_exe, tmp_path, monkeypatch, air):
    h = L._twin(twin_exe, tmp_path, monkeypatch, air, L.MAC_A, sealed=True)
    yield h
    h.end()


def _page(board, page_so, tmp_path, name="p"):
    return L.Page(board, L._page_lib(page_so, name, str(tmp_path)), True)


class Term:
    """The Terminal's side of the 't' channel."""

    def __init__(self, page):
        self.p = page
        self.out = b""

    def say(self, kind, body=b""):
        self.p.send(b"t" + kind + body)

    def open(self, cols=80, rows=24):
        self.say(b"O", struct.pack("<HH", cols, rows))
        return self.wait(lambda m: m[1:2] in (b"A", b"B"))

    def wait(self, ok, timeout=5.0):
        """The first message `ok` takes, the face's bytes gathered meanwhile."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.p.pump()
            while self.p.terms:
                m = self.p.terms.pop(0)
                if m[1:2] == b"D":
                    self.out += m[2:]
                if ok(m):
                    return m
            time.sleep(0.005)
        return None

    def until(self, text, timeout=5.0):
        self.wait(lambda m: text in self.out, timeout)
        got, self.out = self.out, b""
        return got


def test_the_probe_says_the_shell_is_on_the_socket_and_term_is_not(board):
    assert board.probe()["term"] == 1
    assert seal_client.split(board.send("GET", "/term"))[0] == 404


def test_a_face_opens_takes_keys_and_says_its_exit(board, page_so, tmp_path):
    t = Term(_page(board, page_so, tmp_path).open())
    assert t.open(100, 30) == b"tA"
    assert b"$ " in t.until(b"$ ")
    t.say(b"k", b"echo live-$((40+2))\r")
    assert b"live-42" in t.until(b"live-42")
    t.say(b"s", struct.pack("<HH", 90, 28))
    t.say(b"k", b"top\r")
    assert b"\x1b[28;1H" in t.until(b"\x1b[28;1H"), "the resize reached the shell"
    t.say(b"k", b"q")
    t.until(b"$ ")
    t.say(b"k", b"exit 3\r")
    x = t.wait(lambda m: m[1:2] == b"X")
    assert x is not None and struct.unpack("<i", x[2:6])[0] == 3, x
    assert t.p.closed is None, "the socket outlives its face"
    # the Terminal asks again: a fresh face on the same socket
    assert t.open() == b"tA"
    assert b"$ " in t.until(b"$ ")
    t.say(b"C")
    assert D._live(board).get("devs", "0") == "0"


def test_another_page_takes_the_session_and_its_face(board, page_so, tmp_path):
    a = Term(_page(board, page_so, tmp_path, "a").open())
    assert a.open() == b"tA"
    a.until(b"$ ")
    b = _page(board, page_so, tmp_path, "b").open(
        signin=lambda br: br.pair_token(board.token()))
    # (the seal client keeps one slot's keys, b's now: a's bytes are read raw)
    D._until([], lambda: D._ended(a.p))
    tb = Term(b)
    assert tb.open() == b"tA", "the taken page's face let the shell go"
    assert b"$ " in tb.until(b"$ ")
