"""A gamepad held at the browser (#254): the page reads it through the
Gamepad API once a frame (firmware/web_runner/page_tail.js, GP_BTN) and its
presses reach the console as a board's do, from their own source.

* the page's mapping names only the table's buttons, on the standard
  mapping's places, and its shoulders type the tab keys Q and E;
* a pad connecting joins the inputs as the `pad` kind and is the input in
  use, so its focus and its keys show before its first press; the last one
  leaving releases what it held and gives the board's first input back;
* a press and its release in one batch are two frames, so the press is
  seen;
* the pad drives the shell: the home's selection, Start's system menu, and
  the shoulders' tabs, but types nothing into a field or a game.

The browser half is tests/test_web_gamepad_e2e.py.
"""

import re
from pathlib import Path

import pytest

from runtime import host_app, moy_input, ui_draw, web_input
from ws_helpers import build_ws, make_drv

ROOT = Path(__file__).resolve().parent.parent
SRC = web_input.GAMEPAD_SOURCE


@pytest.fixture(autouse=True)
def _keys_after():
    yield
    ui_draw.input_kind("keys")


def _page_table(name):
    text = (ROOT / "firmware/web_runner/page_tail.js").read_text()
    body = re.search(r"\b%s=\{([^}]*)\}" % name, text).group(1)
    return {int(k): v.strip('"') if v.startswith('"') else int(v)
            for k, v in re.findall(r"(\d+):(\"[a-z]+\"|\d+)", body)}


def test_the_pages_mapping_is_the_standard_layout_onto_the_table():
    btn = _page_table("GP_BTN")
    assert set(btn.values()) <= set(web_input.BUTTON_NAMES)
    assert btn == {0: "a", 1: "b", 2: "x", 3: "y", 8: "select", 9: "start",
                   12: "up", 13: "down", 14: "left", 15: "right", 16: "home"}
    assert _page_table("GP_KEY") == {4: ord("q"), 5: ord("e")}, \
        "the shoulders are the T-Deck's L and R, Q and E"


def test_a_press_and_its_release_in_one_batch_are_two_frames():
    down = {"type": "hold", "name": "a", "down": True, "src": SRC}
    up = {"type": "hold", "name": "a", "down": False, "src": SRC}
    assert web_input.frame_cut([down, up]) == 1
    assert web_input.frame_cut([up, down]) == 2, "a release alone is no cut"
    other = {"type": "hold", "name": "a", "down": False, "src": "pad"}
    assert web_input.frame_cut([down, other]) == 2, "another source's release"


class _Page:
    """The worker's end of the page's events: web_boot's `_apply` and
    `_gamepad`, one frame a batch as `_feed_events` takes it."""

    def __init__(self, ws):
        self.ws, self.drv = ws, make_drv(ws)

    def gamepad(self, on):
        if on:
            self.ws.input_joined(SRC, "pad")
        else:
            self.ws.input_left(SRC)

    def send(self, *events):
        q = list(events)
        while q:
            n = web_input.frame_cut(q)
            d = self.drv
            web_input.apply_events(q[:n], d.input, d.pointer, on_hold=d.hold,
                                   on_key=d.type_char, on_gamepad=self.gamepad)
            q = q[n:]
            d.frame(1 / 30)

    def tap(self, name):
        self.send({"type": "hold", "name": name, "down": True, "src": SRC},
                  {"type": "hold", "name": name, "down": False, "src": SRC})
        self.drv.frame(1 / 30)

    def shoulder(self, ch):
        self.send({"type": "key", "code": ord(ch), "src": SRC})
        self.drv.frame(1 / 30)


@pytest.fixture
def page(tmp_path, monkeypatch):
    # the browser's table: the boards' sixteen names (web_boot's InputTable)
    monkeypatch.setattr(host_app, "InputState", moy_input.InputTable)
    ws = build_ws(tmp_path)
    ws.use_inputs((("local", "keys"), ("pad", "pad")))
    p = _Page(ws)
    ws.home.go_home()
    p.drv.frame(1 / 30)
    return p


def test_a_pad_connecting_is_the_input_in_use_and_leaving_gives_the_keys_back(page):
    ws = page.ws
    assert ui_draw.input_kind() == "keys"
    page.send({"type": "gamepad", "on": True})
    assert ws.input_kinds[SRC] == "pad"
    assert ui_draw.input_kind() == "pad" and ui_draw.hint_kind() == "pad"
    page.send({"type": "hold", "name": "right", "down": True, "src": SRC})
    assert ws.input.held("right")
    page.send({"type": "gamepad", "on": False})
    page.drv.frame(1 / 30)
    assert SRC not in ws.input_kinds
    assert not ws.input.held("right"), "a pad that left holds nothing"
    assert ui_draw.input_kind() == "keys"


def test_a_pad_leaving_keeps_another_input_in_use(page):
    page.send({"type": "gamepad", "on": True})
    page.drv.key_down(ord("x"))
    page.drv.frame(1 / 30)
    page.drv.key_up(ord("x"))
    assert ui_draw.input_kind() == "keys"
    page.send({"type": "gamepad", "on": False})
    assert ui_draw.input_kind() == "keys"


def test_the_pad_moves_the_homes_selection(page):
    ws = page.ws
    page.send({"type": "gamepad", "on": True})
    assert len(ws.launcher.items) > 1
    sel = ws.launcher.sel
    page.tap("right")
    for _ in range(10):                 # (the carousel glides onto the card)
        page.drv.frame(1 / 30)
    assert ws.launcher.sel == sel + 1
    assert ui_draw.input_kind() == "pad"


def test_start_is_the_consoles_key(page):
    ws = page.ws
    page.send({"type": "gamepad", "on": True})
    page.tap("start")
    assert ws.sysmenu.open, "Start's tap opened no system menu"
    page.tap("start")
    assert not ws.sysmenu.open


def test_the_shoulders_step_the_homes_tabs(page):
    ws = page.ws
    page.send({"type": "gamepad", "on": True})
    tab = ws.launcher.tab
    page.shoulder("e")
    assert ws.launcher.tab != tab, "R stepped no tab"
    page.shoulder("q")
    assert ws.launcher.tab == tab, "L did not step back"
    assert ui_draw.input_kind() == "pad", "a shoulder is the pad's, not the keyboard's"


@pytest.mark.parametrize("flag", ["text_mode", "cart_keys"])
def test_a_shoulder_types_nothing_into_a_field_or_a_game(page, flag):
    inp = page.ws.input
    events = []

    class Input:
        def __getattr__(self, name):
            return getattr(inp, name)

        def source(self, name):
            events.append(name)
            return inp.source(name)

    i = Input()
    setattr(i, flag, True)
    web_input.apply_events([{"type": "key", "code": ord("q"), "src": SRC}], i, None)
    assert events == []


def test_the_homes_strip_names_the_pads_keys_once_it_connects(page):
    """The home keeps its hint strip while nothing it shows moved, and the
    input whose keys it names is one of those things: a pad connecting
    redraws it in the pad's keys, as a home first drawn for a pad draws it."""
    ws, drv = page.ws, page.drv
    for _ in range(30):
        drv.frame(1 / 30)
    foot = ws.launcher.foot()[5]
    cv = ws.sys_canvas

    def strip():
        row = cv.w * 2
        return bytes(cv._buf)[foot[1] * row:(foot[1] + foot[3]) * row]

    keys = strip()
    page.send({"type": "gamepad", "on": True})
    for _ in range(30):
        drv.frame(1 / 30)
    pad = strip()
    assert pad != keys, "the strip still names the keyboard's keys"
    page.send({"type": "gamepad", "on": False})
    for _ in range(30):
        drv.frame(1 / 30)
    assert strip() == keys
