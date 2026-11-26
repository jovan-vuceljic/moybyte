"""The browser page's rows (firmware/web_runner/page_link.py): what the
page's top bar did is the console's. With a page around the console the
system menu offers Full screen and Add a file, the open cart's
group Download (and Play on the console where a console serves
the page), the home's card Save; each row asks the page, and the page's
word comes back as Settings' Carts row, the row's words, a notice or a card.
Without one (a board) none of it shows."""
import os
import sys

from ws_helpers import build_ws, make_drv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "firmware", "web_runner"))
import page_link  # noqa: E402


def _menu(ws, drv):
    ws.toggle_sysmenu()
    drv.frame(1 / 30)
    return [it[4] if len(it) > 4 else it[1] for it in ws.sysmenu.items if it[0] == "item"]


def _pick(ws, text):
    for it in ws.sysmenu.items:
        if it[0] == "item" and len(it) > 4 and it[4] == text:
            it[2]()
            return
    raise AssertionError("no row %r" % text)


def test_a_board_shows_none_of_the_page_s_rows(tmp_path):
    ws = build_ws(tmp_path)
    drv = make_drv(ws)
    rows = _menu(ws, drv)
    for text in ("Full screen", "Add a file", "Download",
                 "Play on the console"):
        assert text not in rows, rows


def test_the_system_menu_asks_the_page_for_full_screen_and_a_file(tmp_path):
    ws = build_ws(tmp_path)
    ws.page = page_link.PageLink()
    drv = make_drv(ws)
    assert "Full screen" not in _menu(ws, drv), "a browser with no full screen has no row"
    ws.sysmenu.open = False
    ws.page.heard(ws, {"canfs": True})
    rows = _menu(ws, drv)
    assert "Full screen" in rows and "Add a file" in rows, rows
    _pick(ws, "Full screen")
    _pick(ws, "Add a file")
    assert ws.page.drain() == [{"do": "fullscreen", "on": True}, {"do": "open"}]
    assert ws.page.drain() is None
    ws.page.heard(ws, {"fs": True})
    ws.sysmenu.open = False
    assert "Leave full screen" in _menu(ws, drv)
    _pick(ws, "Leave full screen")
    assert ws.page.drain() == [{"do": "fullscreen", "on": False}]


def test_a_cart_s_rows_save_it_and_a_served_page_plays_it_on_the_console(tmp_path):
    ws = build_ws(tmp_path)
    ws.page = page_link.PageLink(served=True)
    drv = make_drv(ws)
    ws.launcher.sel = 0
    ws.open()
    folder = page_link.folder_of(ws.cart)
    assert folder
    rows = _menu(ws, drv)
    assert "Download" in rows and "Play on the console" in rows, rows
    _pick(ws, "Download")
    _pick(ws, "Play on the console")
    assert ws.page.drain() == [{"do": "save", "cart": folder}, {"do": "pod", "cart": folder}]


def test_a_static_page_offers_no_play_on_the_console(tmp_path):
    ws = build_ws(tmp_path)
    ws.page = page_link.PageLink(served=False)
    drv = make_drv(ws)
    ws.launcher.sel = 0
    ws.open()
    rows = _menu(ws, drv)
    assert "Download" in rows and "Play on the console" not in rows, rows


def test_the_home_s_card_saves_the_selected_cart_and_plays_it_on_the_console(tmp_path):
    ws = build_ws(tmp_path)
    ws.page = page_link.PageLink()
    make_drv(ws)
    home = ws.launcher_layer
    it = home.grid.selected()
    assert it and it.get("path")
    assert "save" in home.card_verbs() and "pod" not in home.card_verbs()
    home._do_verb("save")
    folder = page_link.folder_of(it)
    assert ws.page.drain() == [{"do": "save", "cart": folder}]
    ws.page.served = True
    assert "pod" in home.card_verbs()
    home._do_verb("pod")
    assert ws.page.drain() == [{"do": "pod", "cart": folder}]


def test_the_page_s_word_is_the_console_s(tmp_path):
    """Where it keeps the carts is Settings' Carts row; what it says is a
    notice, a card, or an import's card whose Open plays the cart."""
    import settings_rows  # noqa: F401
    ws = build_ws(tmp_path)
    opened = []
    ws.page = page_link.PageLink(play=opened.append)
    drv = make_drv(ws)
    ws.page.heard(ws, {"kept": "In this browser"})
    assert ws.page.kept == "In this browser"
    ws.page.heard(ws, {"say": ["Saved x.moy.zip", "", "ok"]})
    assert ws.notice_up[0] == "Saved x.moy.zip"
    # A conversion's progress: said with its time each second, and taken
    # down with 0 where it is the notice up, and only there.
    ws.page.heard(ws, {"say": ["Importing c.p8", "Writing the cart (3s)", "ok", 2500]})
    assert ws.notice_up[:2] == ("Importing c.p8", "Writing the cart (3s)")
    assert ws.notices.notice_active()
    ws.page.heard(ws, {"say": ["Importing other.p8", "", "ok", 0]})
    assert ws.notices.notice_active()
    ws.page.heard(ws, {"say": ["Importing c.p8", "", "ok", 0]})
    assert not ws.notices.notice_active()
    ws.page.heard(ws, {"tell": ["The console stopped answering", ["Do not reload.", "danger"]]})
    assert ws.confirm.open and ws.confirm.verb == "tell"
    assert ws.confirm.line_rows() == (("Do not reload.", "danger"),)
    ws.confirm.cancel()
    ws.page.heard(ws, {"offer": ["tiny dash imported.", "local.tiny_dash.moy",
                                 ["It runs.", "plain"]]})
    assert ws.confirm.verb == "open" and ws.confirm.line_rows() == (("It runs.", "plain"),)
    ws.confirm.answer()
    drv.frame(1 / 30)
    assert opened == ["local.tiny_dash.moy"]


_HOME = "Add to Home Screen"


def test_a_browser_without_full_screen_offers_the_home_screen(tmp_path):
    """An iPhone's Safari has no full screen: the system menu offers Add to
    Home Screen, whose card has the steps, until the page runs as the
    home-screen app."""
    ws = build_ws(tmp_path)
    ws.page = page_link.PageLink()
    drv = make_drv(ws)
    ws.page.heard(ws, {"canfs": False, "app": False, "host": "os.moybyte.com"})
    rows = _menu(ws, drv)
    assert _HOME in rows and "Full screen" not in rows, rows
    _pick(ws, _HOME)
    assert ws.confirm.open and ws.confirm.verb == "tell"
    lines = [t for t, _tone in ws.confirm.line_rows()]
    assert "2. Choose Add to Home Screen." in lines and not any(".local" in t for t in lines)
    ws.confirm.cancel()
    ws.sysmenu.open = False
    ws.page.heard(ws, {"app": True})
    assert _HOME not in _menu(ws, drv), "the home-screen app has no row for it"
    ws.sysmenu.open = False
    ws.page.heard(ws, {"canfs": True, "app": False})
    assert _HOME not in _menu(ws, drv), "a browser with full screen has its row"


def test_a_board_s_page_at_a_number_is_saved_from_its_name(tmp_path):
    """A board's page opened at a number says to save it from the board's
    .local name, which a new lease does not move, and that the app pairs
    with the board once; at its name it says only the pairing."""
    for host, by_number in (("192.168.1.40", True), ("moybyte.local", False)):
        ws = build_ws(tmp_path / host)
        ws.page = page_link.PageLink(served=True)
        ws.page.heard(ws, {"canfs": False, "host": host})
        ws.page.home_screen(ws)
        lines = " ".join(t for t, _tone in ws.confirm.line_rows())
        assert (".local" in lines and host in lines) == by_number, lines
        assert "pairs with it once" in lines, lines


def test_page_link_tells_a_number_from_a_name():
    assert page_link._is_number("192.168.1.40") and page_link._is_number("fe80::1")
    assert not page_link._is_number("moybyte.local") and not page_link._is_number("localhost")


def test_an_iphone_offers_both_full_screens(tmp_path):
    """An iPhone's or an iPad's element full screen keeps the browser's strip
    and Close, so its menu offers Full screen, the quick one, and Add to Home
    Screen, the true one; its home-screen app, full screen already, neither.
    Android's installed app keeps Full screen."""
    ws = build_ws(tmp_path)
    ws.page = page_link.PageLink()
    drv = make_drv(ws)
    cases = (({"canfs": True, "ios": True, "app": False}, True, True),
             ({"canfs": False, "ios": True, "app": False}, False, True),
             ({"canfs": True, "ios": True, "app": True}, False, False),
             ({"canfs": True, "ios": False, "app": False}, True, False),
             ({"canfs": True, "ios": False, "app": True}, True, False))
    for ev, full, home in cases:
        ws.sysmenu.open = False
        ws.page.heard(ws, ev)
        rows = _menu(ws, drv)
        assert ("Full screen" in rows, _HOME in rows) == (full, home), (ev, rows)
    ws.page.home_screen(ws)
    assert ws.confirm.line_rows()[0][0] == "True full screen, no browser bars:"


def test_about_offers_the_fast_console_where_the_board_has_it(tmp_path):
    """Where the board serving the page has the fast console (its https
    origin, loader.html), About's Fast console on iPhone row shows on an
    iPhone's page (Off) and on the fast page itself (On), nowhere else; it
    sends the page to the loader at the board's http address, which asks
    again."""
    import settings_rows
    ws = build_ws(tmp_path)
    ws.page = page_link.PageLink(served=True)
    drv = make_drv(ws)
    ws.open_settings()
    cases = (({"fast": 0, "ios": True}, False, "Off"),
             ({"fast": 1, "ios": False}, False, "Off"),
             ({"fast": 1, "ios": True}, True, "Off"),
             ({"fast": 2, "ios": False}, True, "On"))
    for ev, shown, word in cases:
        ws.page.heard(ws, dict(ev, host="mojbajt.local"))
        drv.frame(1 / 30)
        assert (settings_rows.s.has_fast, settings_rows.s.fast_word) == (shown, word), ev
    ws.page.drain()
    ws.page.fast_again()
    assert ws.page.drain() == [{"do": "go", "url": "http://mojbajt.local/?fast"}]
