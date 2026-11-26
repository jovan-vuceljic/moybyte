"""The live socket's requests (native/moy_net/moy_live.c, THE REQUESTS): a
page asks its board's routes on the socket it holds, and the board answers
them as it answers them over HTTP.

The board twin is tests/test_live_link.py's, with a files root and a route
its console answers (tty_main's MOY_TTY_DEFER, which parks it as a VM's
does); the page is its socket, the worker's job done by hand, and its
requests are sealed by the same client as over HTTP (tests/seal_client.py).
What it holds: the probe names the most a piece up carries; every route a
page asks -- the pulls, a song's bytes, a sync, a parked route -- answers
the same plaintext and status on the socket as over HTTP; a long request
and a long answer cross in pieces; a request whose seal does not check is
refused as over HTTP; the sign-in is not asked on the socket; pieces that
do not add up are refused at once; and the page's own sync is no news to it.
"""
import json
import os
import shutil
import struct
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import seal_client  # noqa: E402
import test_live_dev as D  # noqa: E402
import test_live_link as L  # noqa: E402
import test_moy_tty as T  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("cc") is None, reason="needs a C compiler")

twin_exe = L.twin_exe
page_so = L.page_so
air = D.air

IN_CAP = 4096                           # moy_live.c's MOY_LIVE_IN on the twin
SONG = bytes(range(256)) * 160          # 40 KiB


def _store(tree):
    carts = tree / "sd" / "moybyte" / "carts"
    for i in range(3):
        d = carts / ("game%d.moy" % i)
        d.mkdir()
        (d / "main.py").write_text("print(%d)\n" % i + "# pad\n" * 900)
        (d / "cover.png").write_bytes(os.urandom(9000))
    music = tree / "sd" / "moybyte" / "files" / "Music"
    music.mkdir(parents=True)
    (music / "song.mp3").write_bytes(SONG)


@pytest.fixture
def board(twin_exe, tmp_path, monkeypatch, air):
    monkeypatch.setenv("MOY_AIR", str(air.port))
    monkeypatch.setenv("MOY_AIR_MAC", L.MAC_A.hex())
    monkeypatch.setenv("MOY_TTY_DEFER", "/run")
    h = T.Host(twin_exe, tmp_path, sealed=True, files=True)
    _store(h.tree)
    h.page = h.browser()
    yield h
    h.end()


class Asker:
    """The worker's request channel: a request in pieces up, its answer
    back as the raw HTTP the seal client reads."""

    def __init__(self, page, piece):
        self.page, self.piece = page, piece
        self.id = 0
        self.frames = []            # (kind, plaintext length) of each answer frame, in order

    def pieces(self, req):
        self.id += 1
        first = self.piece - 8
        yield b"rQ" + struct.pack("<HI", self.id, len(req)) + req[:first]
        for at in range(first, len(req), self.piece - 4):
            yield b"rB" + struct.pack("<H", self.id) + req[at:at + self.piece - 4]

    def answer(self, timeout=10.0):
        """(status, Content-Type, body) of request self.id, once its 'Z' came."""
        status, ctype, body = None, b"", b""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.page.pump()
            got, self.page.answers = self.page.answers, []
            for m in got:
                kind, mid = m[1:2], struct.unpack("<H", m[2:4])[0]
                assert mid == self.id, (mid, self.id)
                self.frames.append((kind, len(m)))
                at = 4
                if kind in (b"A", b"W"):
                    assert status is None, "a second head"
                    status, at = struct.unpack("<H", m[4:6])[0], 7 + m[6]
                    ctype = m[7:at]
                else:
                    assert kind in (b"D", b"Z"), kind
                    assert status is not None, "a body before its head"
                body += m[at:]
                if kind in (b"Z", b"W"):
                    return status, ctype, body
            time.sleep(0.005)
        raise AssertionError("no answer to request %d" % self.id)

    def send(self, method, target, body=b""):
        for pl in self.pieces(method.encode() + b" " + target.encode() + b"\n" + body):
            self.page.send(pl)
        status, ctype, body = self.answer()
        return b"HTTP/1.1 %d -\r\nContent-Type: %s\r\n\r\n" % (status, ctype) + body


def _open(board, page_so, tmp_path):
    page = L.Page(board, L._page_lib(page_so, "p", str(tmp_path)), True).open()
    piece = board.page.json("GET", "/live")[1]["req"]
    return page, Asker(page, piece)


def _said(browser, method, path, body=b""):
    """(status, plaintext) of a sealed answer, or ("clear", status, body)
    of a refusal in the clear."""
    try:
        return browser.call(method, path, body)
    except seal_client.Refused as r:
        return ("clear", r.status, r.doc)


def _batch(path, text):
    return json.dumps({"v": 1, "ops": [{"p": path, "t": text}]}).encode()


def test_the_probe_names_the_most_a_piece_up_carries(board):
    assert board.page.json("GET", "/live")[1]["req"] == IN_CAP - 8 - 16


def test_every_route_answers_on_the_socket_as_over_http(board, page_so, tmp_path):
    page, asker = _open(board, page_so, tmp_path)
    live = seal_client.Browser(asker.send)
    hexname = b"song.mp3".hex()
    asks = [("GET", "/carts.json", b""), ("GET", "/files.json", b""), ("GET", "/media", b""),
            ("GET", "/media?f=%s&at=1000&len=32768" % hexname, b""),
            ("POST", "/run", b'{"cart": "game1.moy"}'), ("GET", "/nothing", b"")]
    for method, path, body in asks:
        over_http = _said(board.page, method, path, body)
        on_socket = _said(live, method, path, body)
        assert on_socket == over_http, path
    assert live.call("GET", "/media?f=%s&at=1000&len=32768" % hexname)[1] == SONG[1000:33768]
    # a sync on the socket lands as one over HTTP does
    assert live.call("POST", "/sync", _batch("game9.moy/main.py", "x = 9\n"))[0] == 200
    pulled = json.loads(board.page.call("GET", "/carts.json")[1])
    assert pulled["game9.moy/main.py"] == "x = 9\n"
    assert json.loads(live.call("GET", "/carts.json")[1]) == pulled
    page.pump()
    assert int(D._live(board)["reqs"]) == len(asks) + 3


def test_a_long_request_and_a_long_answer_cross_in_pieces(board, page_so, tmp_path):
    page, asker = _open(board, page_so, tmp_path)
    live = seal_client.Browser(asker.send)
    texts = {"long.moy/f%d.py" % k: "".join("line %d of file %d\n" % (i, k) for i in range(400))
             for k in range(8)}
    body = json.dumps({"v": 1, "ops": [{"p": p, "t": t} for p, t in texts.items()]}).encode()
    assert len(body) > 8 * asker.piece
    assert live.call("POST", "/sync", body) == (200, b'{"ok": 8, "err": []}')
    status, plain = live.call("GET", "/carts.json")
    assert status == 200 and len(plain) > 30 * 2048
    assert all(json.loads(plain)[p] == t for p, t in texts.items())
    assert plain == board.page.call("GET", "/carts.json")[1]


# A frame down is at most a segment: the MSS less the frame's head and tag.
FULL = 1440 - 4 - 16


def test_an_answer_goes_in_whole_segments_and_a_small_one_in_one(board, page_so, tmp_path):
    """Each segment the board sends holds a whole MSS of its heap until the
    page acks it (lwIP's single-pbuf send), so an answer's frames are full
    segments but its last, and a small answer is one 'W'."""
    page, asker = _open(board, page_so, tmp_path)
    live = seal_client.Browser(asker.send)
    texts = {"long.moy/f%d.py" % k: "".join("line %d of file %d\n" % (i, k) for i in range(400))
             for k in range(4)}
    body = json.dumps({"v": 1, "ops": [{"p": p, "t": t} for p, t in texts.items()]}).encode()
    del asker.frames[:]
    assert live.call("POST", "/sync", body)[0] == 200
    assert [k for k, _n in asker.frames] == [b"W"]
    del asker.frames[:]
    status, plain = live.call("GET", "/carts.json")
    assert status == 200 and len(plain) > 10 * FULL
    kinds = [k for k, _n in asker.frames]
    assert kinds[0] == b"A" and kinds[-1] == b"Z" and set(kinds[1:-1]) == {b"D"}, kinds
    assert all(n == FULL for _k, n in asker.frames[:-1]), asker.frames


def test_a_request_whose_seal_does_not_check_is_refused_as_over_http(board, page_so,
                                                                     tmp_path):
    page, asker = _open(board, page_so, tmp_path)
    for send in (board.send, asker.send):
        target, _b, _seq = board.page.seal("GET", "/carts.json")
        bad = target[:-1] + ("0" if target[-1] != "0" else "1")
        status, head, raw = seal_client.split(send("GET", bad))
        assert status == 401 and "application/json" in head, (send, status, head)
        assert json.loads(raw) == {"error": "auth"}


def test_the_sign_in_and_the_sockets_are_not_asked_on_the_socket(board, page_so, tmp_path):
    page, asker = _open(board, page_so, tmp_path)
    for target in ("/auth", "/live", "/term"):
        status, _h, _b = seal_client.split(asker.send("POST" if target == "/auth" else "GET",
                                                      target, b'{"op":"hello"}'))
        assert status == 404, target


def test_pieces_that_do_not_add_up_are_refused_at_once(board, page_so, tmp_path):
    page, asker = _open(board, page_so, tmp_path)
    asker.id = 7
    page.send(b"rQ" + struct.pack("<HI", 7, 10) + b"GET /x\n")
    page.send(b"rB" + struct.pack("<H", 7) + b"far too many bytes")
    assert asker.answer()[0] == 503
    asker.id = 8
    page.send(b"rQ" + struct.pack("<HI", 8, 1 << 20) + b"GET /x\n")
    assert asker.answer()[0] == 503
    # ...and the socket goes on answering
    assert seal_client.Browser(asker.send).call("GET", "/media")[0] == 200


def test_the_page_s_own_sync_on_the_socket_is_no_news_to_it(board, page_so, tmp_path):
    page, asker = _open(board, page_so, tmp_path)
    live = seal_client.Browser(asker.send)
    assert live.call("POST", "/sync", _batch("mine.moy/main.py", "x = 1\n"))[0] == 200
    end = time.monotonic() + 0.5
    while time.monotonic() < end:
        page.pump()
        time.sleep(0.01)
    assert b"s" not in b"".join(page.hints)
