"""The live socket's hints (native/moy_net/moy_live.c, THE HINTS): a Zero
says on its page's socket when what the page reads from its routes changed,
so the page asks then and not on a clock.

The board twin is tests/test_live_link.py's; the page is its socket, the
worker's job done by hand. What it holds: the probe says the board hints; a
store change the page did not make (an SSH session's command, the page's
own Terminal's) is hinted 's', and the page's own sync is not. (Another
page's sync is that page's socket, which takes the board from this one:
moy_wa_take.)
"""
import json
import os
import shutil
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


def shell_writes(board, rel, text):
    """A cart file written as an SSH session's command writes it (tty_main's
    `run`): a store change no page made."""
    for cmd in ("mkdir /sd/moybyte/carts/" + rel.rsplit("/", 1)[0],
                "echo '%s' > /sd/moybyte/carts/%s" % (text, rel)):
        at = len(board.log())
        board.say("run " + cmd)
        assert board.wait_line("RAN ", at).split()[1] == "0"


def _heard(page, wait=1.0):
    """The hints' letters the page took within `wait` seconds."""
    end = time.monotonic() + wait
    while time.monotonic() < end:
        page.pump()
        time.sleep(0.01)
    got, page.hints = b"".join(page.hints), []
    return got


def test_the_probe_says_the_board_hints(board):
    assert board.probe()["hints"] == 1


def test_a_store_change_the_page_did_not_make_is_hinted(board, page_so, tmp_path):
    page = LT._page(board, page_so, tmp_path).open()
    assert _heard(page, 0.5) == b"", "an open socket starts with no news"
    # the page's own sync: no news to it
    assert board.page.call("POST", "/sync", _batch("mine.moy/main.py", "x = 1\n"))[0] == 200
    assert b"s" not in _heard(page)
    # an SSH session's command: the store changed under this page
    shell_writes(board, "theirs.moy/main.py", "y = 2")
    assert b"s" in _heard(page)
    assert (board.tree / "sd" / "moybyte" / "carts" / "theirs.moy" / "main.py").read_text() \
        == "y = 2\n"
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
