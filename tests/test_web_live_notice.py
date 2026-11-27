"""The page's notices of its live socket (firmware/web_runner/web_boot.py,
live_state): a drop and its return are said on the screen only while a
match is being played. A game that holds the board's radio with no match
formed has nothing waiting, and saying "the match waits" and "the match
carries on" over it is a notice about a match that is not there."""
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def page(monkeypatch):
    for p in ("firmware/web_runner", "device", "runtime"):
        if str(ROOT / p) not in sys.path:
            sys.path.insert(0, str(ROOT / p))
    try:
        import web_boot
    except Exception as exc:  # noqa: BLE001 -- a wasm-only dep would skip, not fail
        pytest.skip("web_boot not importable on the host: %s" % exc)
    radio = {"held": True}
    net = types.SimpleNamespace(
        live_open=lambda on: None,
        live_info=lambda: (False, radio["held"], False, False, 0, 0, b"", 0, 0, 0, 0, 0))
    monkeypatch.setitem(sys.modules, "moy_net", net)
    said = []
    ws = types.SimpleNamespace(
        netplay=None,
        notices=types.SimpleNamespace(notice=lambda title, why, kind: said.append(title)))
    monkeypatch.setitem(web_boot._S, "ws", ws)
    monkeypatch.setitem(web_boot._S, "live", {"open": True, "said": None, "hidden": False,
                                              "gap": False, "check": False})
    monkeypatch.setitem(web_boot._S, "gpio", None)
    return web_boot, ws, radio, said


def test_a_drop_with_the_radio_held_and_no_match_says_nothing(page):
    web_boot, ws, radio, said = page
    web_boot.live_state(0, "1006")
    web_boot.live_state(1)
    assert said == []


def test_a_drop_in_a_match_says_it_and_its_return(page):
    import ui_draw
    web_boot, ws, radio, said = page
    ws.netplay = object()
    web_boot.live_state(0, "1006")
    web_boot.live_state(1)
    assert said == [ui_draw.s("notice.link_lost"), ui_draw.s("notice.link_back")]


def test_a_match_that_ended_while_the_socket_was_down_says_its_return(page):
    """What was said down is answered up, so the screen is not left saying
    the link is lost."""
    import ui_draw
    web_boot, ws, radio, said = page
    ws.netplay = object()
    web_boot.live_state(0, "1006")
    ws.netplay = None
    web_boot.live_state(1)
    assert said == [ui_draw.s("notice.link_lost"), ui_draw.s("notice.link_back")]
