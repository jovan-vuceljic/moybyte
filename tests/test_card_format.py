"""The question the console asks about a card it cannot read
(runtime/system/card_format.py): asked once the desktop is up, through the
console's one dialog; Not now leaves every byte of the card as it was, and
Format writes a FAT volume the store's card then mounts, and restarts."""

import struct

import pytest

from runtime import card_format as F
from runtime.moy_input import InputTable
from ws_helpers import build_ws, make_drv

SECTORS = 65536                     # a 32 MB card
DT = 1 / 30


class Card:
    """moy_sd's verbs over a bytearray."""

    def __init__(self, n=SECTORS):
        self.disk = bytearray(n * 512)

    def sector_count(self):
        return len(self.disk) // 512

    def read(self, start, buf, count):
        buf[:count * 512] = self.disk[start * 512:(start + count) * 512]

    def write(self, start, buf, count):
        self.disk[start * 512:(start + count) * 512] = bytes(buf[:count * 512])


def _gpt(card):
    """A protective MBR and a GPT header: a card FatFS does not read."""
    d = card.disk
    d[446 + 4] = 0xEE
    d[446 + 8:446 + 16] = struct.pack("<II", 1, SECTORS - 1)
    d[510:512] = b"\x55\xaa"
    d[512:520] = b"EFI PART"
    return card


@pytest.fixture(autouse=True)
def clean():
    F.OFFER = None
    F._ASKED[0] = False
    yield
    F.OFFER = None
    F._ASKED[0] = False


def _frames(drv, n=3):
    for _ in range(n):
        drv.frame(DT)


def _press(ws, name):
    was = ws.input
    i = InputTable()
    i.source("kbd").set_button(name, True)
    i.begin_frame()
    ws.input = i
    try:
        ws.router.handle_input()
    finally:
        ws.input = was


def _asked(tmp_path, card):
    ws = build_ws(tmp_path)
    drv = make_drv(ws)
    _frames(drv)
    assert F.noticed(OSError(19, "ENODEV"), card) is not None
    assert F.offer(ws)
    _frames(drv)
    return ws, drv


def test_only_a_card_that_answered_with_nothing_readable_is_a_question():
    assert F.noticed(OSError(16, "EBUSY"), Card()) is None      # no card answered
    assert F.noticed(OSError("moy_sd card_init failed: 263"), Card()) is None
    assert F.noticed(OSError(19, "ENODEV"), Card(0)) is None    # nothing up
    assert F.noticed(OSError(19, "ENODEV"), Card()) == {"sectors": SECTORS, "data": False}
    assert F.noticed(OSError(19, "ENODEV"), _gpt(Card()))["data"] is True
    assert F.words({"sectors": 62333952, "data": True}) == (
        "This card can't be read",
        "Format it for Moybyte? Everything on it will be erased. A 32 GB card. "
        "It seems to hold data.")


def test_not_now_leaves_the_card_untouched(tmp_path):
    card = _gpt(Card())
    before = bytes(card.disk)
    ws, drv = _asked(tmp_path, card)
    assert ws.confirm.open and ws.confirm.verb == "format"
    assert ws.confirm.title == "This card can't be read"
    _press(ws, "b")                                 # the pad's back is Not now
    _frames(drv)
    assert not ws.confirm.open and F.OFFER is None
    assert bytes(card.disk) == before
    assert not F.offer(ws)                          # asked once a finding
    assert F.noticed(OSError(19, "ENODEV"), card) is None   # a retried mount: once a boot


def test_format_formats_the_card_it_found_and_restarts(tmp_path, monkeypatch):
    card = _gpt(Card())
    ws, drv = _asked(tmp_path, card)
    formatted, restarted = [], []
    monkeypatch.setattr(F, "format", formatted.append)
    ws.reboot_hook = lambda: restarted.append(1)
    ws.confirm.answer()
    _frames(drv)
    assert formatted == [card] and restarted == [1] and F.OFFER is None


def test_a_format_that_fails_says_so_and_restarts_nothing(tmp_path, monkeypatch):
    ws, drv = _asked(tmp_path, Card())

    def fails(card):
        raise OSError(5, "EIO")
    monkeypatch.setattr(F, "format", fails)
    restarted = []
    ws.reboot_hook = lambda: restarted.append(1)
    ws.confirm.answer()
    _frames(drv)
    assert restarted == [] and ws.notices.notice_active()


# The card the store cannot read, in the boards' MicroPython: its mount is
# ENODEV, which is the question; the format the question's yes writes is a
# volume the store's own card then mounts.
SESSION = """
import sys, struct
sys.path[:0] = [@STAGE@, @RUNTIME@]
import moy_sd, moy_store, vfs, card_format as F
n = @SECTORS@
d = moy_sd.disk
d[446 + 4] = 0xEE
d[446 + 8:446 + 16] = struct.pack("<II", 1, n - 1)
d[510:512] = b"\\x55\\xaa"
d[512:520] = b"EFI PART"
try:
    moy_store.card(n, moy_sd)
    print("MOUNTED")
except OSError as e:
    print("OFFER", F.noticed(e, moy_sd))
F.format(moy_sd)
vfs.mount(moy_store.card(n, moy_sd), "/sd")
with open("/sd/x.txt", "w") as f:
    f.write("kept")
print("READ", open("/sd/x.txt").read())
"""

FAKE_MOY_SD = """
disk = bytearray(@SECTORS@ * 512)
def sector_count():
    return @SECTORS@
def read(block, buf, n):
    buf[:n * 512] = memoryview(disk)[block * 512:(block + n) * 512]
def write(block, buf, n):
    memoryview(disk)[block * 512:(block + n) * 512] = buf[:n * 512]
"""


def test_a_card_the_store_cannot_read_is_asked_about_and_formats_to_one_it_can(tmp_path):
    import subprocess
    from unix_mp import require_unix_mp, runtime_tree
    exe = require_unix_mp(board_model=True, why="the card's format question")
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "moy_sd.py").write_text(FAKE_MOY_SD.replace("@SECTORS@", str(SECTORS)))
    script = stage / "s.py"
    script.write_text(SESSION.replace("@STAGE@", repr(str(stage)))
                      .replace("@RUNTIME@", repr(runtime_tree()))
                      .replace("@SECTORS@", str(SECTORS)))
    out = subprocess.run([exe, "-X", "heapsize=64m", str(script)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    lines = out.stdout.splitlines()
    assert lines[0] == "OFFER {'sectors': %d, 'data': True}" % SECTORS, lines
    assert lines[1] == "READ kept", lines
