"""The live socket's hints (native/moy_net/moy_live.c, THE HINTS): a Zero
says on its page's socket when what the page reads over HTTP changed, so the
page asks then and not on a clock.

The board twin is tests/test_live_link.py's; the page is its socket, the
worker's job done by hand. What it holds: the probe says the board hints; a
store change the page did not make (another page's sync, a shell's write)
is hinted 's', and the page's own sync is not.
"""
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
import test_live_term as LT  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("cc") is None, reason="needs a C compiler")

twin_exe = L.twin_exe
page_so = L.page_so
air = D.air
board = LT.board


def _batch(path, text):
    return json.dumps({"v": 1, "ops": [{"p": path, "t": text}]}).encode()


# Another page, in a process of its own (the seal client keeps one session's
# keys a process): paired by `token`, it signs in and syncs one batch.
_OTHER = """
import socket, sys
sys.path.insert(0, %r)
import seal_client
port, token, body = int(sys.argv[1]), sys.argv[2], sys.argv[3].encode()
def send(method, target, b=b""):
    with socket.create_connection(("127.0.0.1", port), timeout=5) as c:
        c.sendall(("%%s %%s HTTP/1.1\\r\\nHost: x\\r\\nContent-Length: %%d\\r\\n\\r\\n"
                   %% (method, target, len(b))).encode() + b)
        data = b""
        while True:
            k = c.recv(65536)
            if not k:
                return data
            data += k
b = seal_client.Browser(send)
b.pair_token(token)
print(b.call("POST", "/sync", body)[0])
""" % os.path.dirname(os.path.abspath(__file__))


def _other_syncs(board, body):
    run = subprocess.run([sys.executable, "-c", _OTHER, str(board.port), board.token(),
                          body.decode()], capture_output=True, text=True, timeout=60,
                         cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert run.stdout.strip() == "200", run.stdout + run.stderr


def _heard(page, wait=1.0):
    """The hints' letters the page took within `wait` seconds."""
    end = time.monotonic() + wait
    while time.monotonic() < end:
        page.pump()
        time.sleep(0.01)
    got, page.hints = b"".join(page.hints), []
    return got


def test_the_probe_says_the_board_hints(board):
    assert board.page.json("GET", "/live")[1]["hints"] == 1


def test_a_store_change_the_page_did_not_make_is_hinted(board, page_so, tmp_path):
    page = LT._page(board, page_so, tmp_path).open()
    assert _heard(page, 0.5) == b"", "an open socket starts with no news"
    # the page's own sync: no news to it
    assert board.page.call("POST", "/sync", _batch("mine.moy/main.py", "x = 1\n"))[0] == 200
    assert b"s" not in _heard(page)
    # another page's: the store changed under this one
    _other_syncs(board, _batch("theirs.moy/main.py", "y = 2\n"))
    assert b"s" in _heard(page)
    # a shell's write (the page's own Terminal on the board, as an SSH
    # session's would be)
    t = LT.Term(page)
    assert t.open() == b"tA"
    t.until(b"$ ")
    assert b"s" not in _heard(page, 0.3)
    t.say(b"k", b"echo hi > hinted.txt\r")
    t.until(b"$ ")
    assert b"s" in _heard(page)
    assert int(D._live(board)["hints"]) >= 2
