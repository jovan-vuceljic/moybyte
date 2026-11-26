"""The live socket's sign-in and requests (native/moy_net/moy_live.c, THE
SIGN-IN and THE REQUESTS; moy_webhost.c, THE SIGN-IN ON THE LIVE SOCKET): a
page signs in to its board on the socket it holds and asks the board's
routes there, and nowhere else.

The board twin is tests/test_live_link.py's, with a files root and a route
its console answers (tty_main's MOY_TTY_DEFER, which parks it as a VM's
does); the page is its socket, the worker's job done by hand, and its
requests are sealed by the same client as a sealed route's
(tests/seal_client.py). What it holds: the probe names the most a piece up
carries; over HTTP the sign-in and every sealed route are refused 410 and
the open ones answer; before its seal a socket serves the sign-in and
nothing else; a wrong credential backs its client off there as over HTTP;
a password's pairing is answered on it; a page that holds its session
opens the socket sealed again; every route answers on the socket; a long
request and a long answer cross in pieces, an answer's frames whole
segments and a small answer one frame; a request whose seal does not
check is refused; the sign-in is not asked on a sealed socket; pieces that
do not add up are refused at once; the page's own sync is no news to it;
and the page asks a request the socket lost again on its next socket, saying
meanwhile that it reconnects (firmware/web_runner/live_test.mjs).
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import seal_client  # noqa: E402
import test_live_dev as D  # noqa: E402
import test_live_link as L  # noqa: E402
import test_moy_tty as T  # noqa: E402
from runtime import ssh_service  # noqa: E402

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
    h = L.live_host(T.Host(twin_exe, tmp_path, sealed=True, files=True))
    _store(h.tree)
    yield h
    h.end()


def _open(board, page_so, tmp_path, name="p", **kw):
    return L.Page(board, L._page_lib(page_so, name, str(tmp_path)), True).open(**kw)


def _said(browser, method, path, body=b""):
    """(status, plaintext) of a sealed answer, or ("clear", status, body)
    of a refusal in the clear."""
    try:
        return browser.call(method, path, body)
    except seal_client.Refused as r:
        return ("clear", r.status, r.doc)


def _batch(path, text):
    return json.dumps({"v": 1, "ops": [{"p": path, "t": text}]}).encode()


def _raw(page, pl):
    """A plaintext up as a page's frame, in the clear (before the seal)."""
    on, page.on = page.on, False
    page.send(pl)
    page.on = on


def _wait(page, until, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        page.pump()
        if until():
            return True
        time.sleep(0.01)
    return False


def test_the_probe_names_the_most_a_piece_up_carries(board):
    assert board.probe()["req"] == IN_CAP - 8 - 16


def test_over_http_the_sign_in_and_the_sealed_routes_are_gone(board, page_so, tmp_path):
    _open(board, page_so, tmp_path)
    for method, target, body in (("POST", "/auth", b'{"op":"hello"}'),
                                 ("GET", "/carts.json", b""), ("GET", "/files.json", b""),
                                 ("GET", "/media", b""), ("POST", "/sync", b"{}"),
                                 ("POST", "/run", b"{}"), ("GET", "/gpio", b"")):
        status, head, raw = seal_client.split(board.send(method, target, body))
        assert (status, json.loads(raw)) == (410, {"error": "live"}), target
    # ...a sealed request too: its session is good, its door is the socket
    target, sealed, _seq = board.page.seal("GET", "/carts.json")
    assert seal_client.split(board.send("GET", target, sealed))[0] == 410
    # what stays HTTP: the marker and the probe (and the page, which a twin lacks)
    assert json.loads(seal_client.split(board.send("GET", "/sync"))[2])["sync"] == 1
    assert board.probe()["live"] == 1


def test_before_its_seal_a_socket_serves_the_sign_in_alone(board, page_so, tmp_path):
    page = L.Page(board, L._page_lib(page_so, "p", str(tmp_path)), True)
    page.open(bare=True)    # opened, not signed in
    assert page.ask("GET", "/carts.json").startswith(b"HTTP/1.1 401 ")
    _raw(page, b"nU")                   # the radio: not before the seal
    _raw(page, b"dO\x01\x00\x04lora")
    _raw(page, b"ce" + b"12345678")     # the socket's own echo is
    assert _wait(page, lambda: page.echoes)
    assert page.echoes == [b"12345678"] and page.closed is None
    assert not any("radio=1" in ln for ln in board.log().splitlines() if ln.startswith("LIVE"))
    b = seal_client.Browser(board.ask)
    assert b.hello()["v"] == 1          # the sign-in is served
    _raw(page, b"cS")                   # a seal with no session ends it
    assert _wait(page, lambda: page.closed)
    assert page.closed[0] == 1008


def test_a_wrong_credential_backs_its_client_off_on_the_socket(board, page_so, tmp_path):
    page = L.Page(board, L._page_lib(page_so, "p", str(tmp_path)), True)
    page.open(bare=True)
    b = seal_client.Browser(board.ask)
    for _ in range(11):
        with pytest.raises(seal_client.Refused) as e:
            b.pair_token("00" * 16)
        assert e.value.status == 403 and e.value.doc == {"error": "token"}
    with pytest.raises(seal_client.Refused) as e:
        b.pair_token(board.token())
    assert e.value.status == 429 and e.value.doc["error"] == "wait"
    assert page.closed is None, "a refusal leaves the socket signing in"


def test_a_password_pairs_on_the_socket_and_a_held_session_opens_it_sealed(board, page_so,
                                                                         tmp_path):
    (board.tree / "sd" / "moybyte" / "system" / "password").write_text(
        ssh_service.hashed("correct horse", "5a1t"))
    page = _open(board, page_so, tmp_path, signin=lambda b: b.pair_password("correct horse"))
    assert board.page.call("GET", "/media")[0] == 200
    page.drop()
    page.open()                         # the session it holds: sealed from the upgrade
    assert page.on and board.page.call("GET", "/media")[0] == 200
    assert "sessions=2" in [ln for ln in board.log().splitlines() if ln.startswith("LIVE")][-1]


def test_every_route_answers_on_the_socket(board, page_so, tmp_path):
    page = _open(board, page_so, tmp_path)
    live = board.page
    hexname = b"song.mp3".hex()
    carts = json.loads(live.call("GET", "/carts.json")[1])
    assert carts["game1.moy/main.py"].startswith("print(1)")
    assert live.call("GET", "/files.json")[0] == 200
    assert json.loads(live.call("GET", "/media")[1]) == {"song.mp3": len(SONG)}
    assert live.call("GET", "/media?f=%s&at=1000&len=32768" % hexname) == (200, SONG[1000:33768])
    status, ran = live.call("POST", "/run", b'{"cart": "game1.moy"}')
    assert status == 200 and json.loads(ran)["t"] == "/run"
    assert _said(live, "GET", "/nothing")[:2] == ("clear", 404)
    # a sync on the socket lands
    assert live.call("POST", "/sync", _batch("game9.moy/main.py", "x = 9\n"))[0] == 200
    pulled = json.loads(live.call("GET", "/carts.json")[1])
    assert pulled["game9.moy/main.py"] == "x = 9\n"
    page.pump()
    assert int(D._live(board)["reqs"]) == 8


def test_a_long_request_and_a_long_answer_cross_in_pieces(board, page_so, tmp_path):
    page = _open(board, page_so, tmp_path)
    live = board.page
    texts = {"long.moy/f%d.py" % k: "".join("line %d of file %d\n" % (i, k) for i in range(400))
             for k in range(8)}
    body = json.dumps({"v": 1, "ops": [{"p": p, "t": t} for p, t in texts.items()]}).encode()
    assert len(body) > 8 * page.piece
    assert live.call("POST", "/sync", body) == (200, b'{"ok": 8, "err": []}')
    status, plain = live.call("GET", "/carts.json")
    assert status == 200 and len(plain) > 30 * 2048
    assert all(json.loads(plain)[p] == t for p, t in texts.items())


# A frame down is at most a segment: the MSS less the frame's head and tag.
FULL = 1440 - 4 - 16


def test_an_answer_goes_in_whole_segments_and_a_small_one_in_one(board, page_so, tmp_path):
    """Each segment the board sends holds a whole MSS of its heap until the
    page acks it (lwIP's single-pbuf send), so an answer's frames are full
    segments but its last, and a small answer, the sign-in's too, is one
    'W'."""
    page = _open(board, page_so, tmp_path)
    assert {k for k, _n in page.frames} == {b"W"}, "the sign-in's answers"
    live = board.page
    texts = {"long.moy/f%d.py" % k: "".join("line %d of file %d\n" % (i, k) for i in range(400))
             for k in range(4)}
    body = json.dumps({"v": 1, "ops": [{"p": p, "t": t} for p, t in texts.items()]}).encode()
    del page.frames[:]
    assert live.call("POST", "/sync", body)[0] == 200
    assert [k for k, _n in page.frames] == [b"W"]
    del page.frames[:]
    status, plain = live.call("GET", "/carts.json")
    assert status == 200 and len(plain) > 10 * FULL
    kinds = [k for k, _n in page.frames]
    assert kinds[0] == b"A" and kinds[-1] == b"Z" and set(kinds[1:-1]) == {b"D"}, kinds
    assert all(n == FULL for _k, n in page.frames[:-1]), page.frames


def test_a_request_whose_seal_does_not_check_is_refused(board, page_so, tmp_path):
    _open(board, page_so, tmp_path)
    target, _b, _seq = board.page.seal("GET", "/carts.json")
    bad = target[:-1] + ("0" if target[-1] != "0" else "1")
    status, head, raw = seal_client.split(board.ask("GET", bad))
    assert status == 401 and "application/json" in head, (status, head)
    assert json.loads(raw) == {"error": "auth"}


def test_the_sign_in_and_the_sockets_are_not_asked_on_a_sealed_socket(board, page_so,
                                                                      tmp_path):
    _open(board, page_so, tmp_path)
    for target in ("/auth", "/live", "/term"):
        status, _h, _b = seal_client.split(board.ask("POST" if target == "/auth" else "GET",
                                                     target, b'{"op":"hello"}'))
        assert status == 404, target


def test_pieces_that_do_not_add_up_are_refused_at_once(board, page_so, tmp_path):
    page = _open(board, page_so, tmp_path)
    page.id = 7
    page.send(b"rQ" + struct.pack("<HI", 7, 10) + b"GET /x\n")
    page.send(b"rB" + struct.pack("<H", 7) + b"far too many bytes")
    assert page.answer()[0] == 503
    page.id = 8
    page.send(b"rQ" + struct.pack("<HI", 8, 1 << 20) + b"GET /x\n")
    assert page.answer()[0] == 503
    # ...and the socket goes on answering
    assert board.page.call("GET", "/media")[0] == 200


def test_the_page_s_own_sync_on_the_socket_is_no_news_to_it(board, page_so, tmp_path):
    page = _open(board, page_so, tmp_path)
    assert board.page.call("POST", "/sync", _batch("mine.moy/main.py", "x = 1\n"))[0] == 200
    end = time.monotonic() + 0.5
    while time.monotonic() < end:
        page.pump()
        time.sleep(0.01)
    assert b"s" not in b"".join(page.hints)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_page_asks_a_lost_request_again_on_its_next_socket():
    """worker.js's end (firmware/web_runner/live_test.mjs): a request whose
    socket dropped is asked again on the socket the page opens next, never
    over HTTP, and the page says it reconnects until that socket is up."""
    p = subprocess.run(["node", "live_test.mjs"],
                       cwd=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
                           __file__))), "firmware", "web_runner"),
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
