"""Settings' Works offline on a page a board serves whose console is online
(firmware/web_runner/offline_link.py over the board's /official, whose
"offline" device/zero_offline.py answers): the row is there only
where the board's probe offered it, says what an install takes, its
progress and "Remove", and shows a refusal's sizes."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware" / "web_runner"))


class _Answer:
    def __init__(self, path, status, doc):
        self.path = path
        self.status = status
        self.error = None
        self.ended = True
        with open(path, "w") as f:
            f.write(json.dumps(doc))

    def ready(self, _n):
        return True

    def close(self):
        os.remove(self.path)


class Board:
    """The board's /official as offline_link reads it: its "offline"
    document, and the POSTs it was asked."""

    def __init__(self, tmp):
        self.tmp = tmp
        self.asked = []
        self.offline = {"on": False, "installed": False, "needs": 2100000,
                        "free": 9000000, "busy": False, "progress": None, "error": None}
        self.refuse = None

    def ask(self, doc=None):
        if doc is not None:
            self.asked.append(doc)
            if self.refuse:
                return _Answer(str(self.tmp / "a"), 409, {"ok": False, "message": self.refuse,
                                                         "offline": self.offline})
            self.offline = dict(self.offline, on=doc["on"], busy=True,
                                progress=[0, 2100000] if doc["on"] else None)
        return _Answer(str(self.tmp / "a"), 200, {"state": "idle", "offline": self.offline})


def test_the_row_installs_shows_progress_and_removes(tmp_path, monkeypatch):
    import offline_link
    from ws_helpers import build_ws
    clock = [0]
    monkeypatch.setattr(offline_link, "_ticks_ms", lambda: clock[0])
    ws = build_ws(tmp_path)
    ws.open_settings()
    assert "offline" not in [r[0] for r in ws.settings_layer._settings_rows()]
    board = Board(tmp_path)
    off = ws.console_offline = offline_link.ConsoleOffline(board, ws)
    assert "offline" in [r[0] for r in ws.settings_layer._settings_rows()]
    assert off.word() == "..."
    assert off.press() and board.asked == [], "a press before the board's answer waits for it"
    off.poll()
    assert board.asked == [{"action": "offline", "on": True}]
    off.poll()
    assert off.word() == "Installing 0%"
    board.offline = dict(board.offline, progress=[1050000, 2100000])
    clock[0] += offline_link.POLL_MS
    off.poll()
    off.poll()
    assert off.word() == "Installing 50%"
    board.offline = dict(board.offline, busy=False, installed=True, progress=None)
    clock[0] += offline_link.POLL_MS
    off.poll()
    off.poll()
    assert off.word() == "Remove"
    clock[0] += 10 * offline_link.POLL_MS
    off.poll()
    assert off._answer is None, "nothing runs: the board is not asked again"
    assert off.press() and board.asked[-1] == {"action": "offline", "on": False}
    off.poll()
    assert off.word() == "Removing"
    board.offline = dict(board.offline, busy=False, installed=False)
    clock[0] += offline_link.POLL_MS
    off.poll()
    off.poll()
    assert off.word() == "Install (≈2.1 MB)"
    board.refuse = "It needs 2.1 MB and this board has 1.0 MB free."
    off.press()
    off.poll()
    assert off.word() == board.refuse
