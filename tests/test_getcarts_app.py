"""Get Carts' `uitree` page: the shelf's cards and what they say, the cart's
page, Remove's question, the pages that say why there is no shelf and the
Wi-Fi page they open, the desk's pane, and a settled page painting nothing.
The fetching and installing under them are tests/test_cart_store.py's."""

import pytest

from cart_store_fixtures import MemNet, Repo
from runtime import getcarts_app as gc
from runtime import host_app
from ws_helpers import quiesce

_DT = 1 / 30


class _In:
    def __init__(self, *names):
        self.names = set(names)
        self.last_key = 0

    def steps(self, n):
        return int(bool(self.pressed(n)))

    def pressed(self, name):
        return name in self.names


def _shelf():
    repo = Repo("https://mit.example/carts", "Test carts")
    repo.add("jet", name="Jet Pot")
    repo.add("rock", name="Rock Run", runtime="lua", modules=())
    repo.add("zap", name="Zap", runtime="lua", modules=())
    return repo, MemNet(repo.routes())


def _ws(tmp_path, net, urls, **kw):
    import json
    from runtime import cart_index as ci
    ws = host_app.build_workstation(str(tmp_path / "carts"), **kw)
    ci.save_sources(str(tmp_path / "carts"), urls)
    ws.cart_net = net
    ws.pointer.visible = False
    return ws, ws.app("getcarts")


def _frames(ws, n=3):
    for _ in range(n):
        ws.mark_dirty()
        ws.frame(_DT)


def _open(ws, app):
    ws.spine.open_app(app)
    for _ in range(40):
        _frames(ws, 1)
        if app.phase != "checking":
            break
    _frames(ws, 2)


def _focus(app):
    """The focused stop: a card's "<folder>/open", a verb's action."""
    return app.engine.focus_key


def _press(ws, app, *names):
    app.handle_input(_In(*names))
    _frames(ws, 2)


def test_the_shelf_says_where_each_cart_stands(tmp_path):
    repo, net = _shelf()
    ws, app = _ws(tmp_path, net, [repo.url("index.json")])
    _open(ws, app)
    assert app.phase == "list"
    rows = {r["cart"]["name"]: r for r in app.rows}
    rows["Rock Run"]["state"] = "installed"
    rows["Zap"]["runs"] = False
    assert app._shown(rows["Jet Pot"]) == "get"
    assert app._shown(rows["Rock Run"]) == "installed"
    assert app._shown(rows["Zap"]) == "noplay"
    app.free = (1000, 4096)                       # no room for anything
    assert app._shown(rows["Jet Pot"]) == "too_big"
    left, right = app._caption()
    assert left == "3 carts" and right.endswith(" free")
    app.unreached = 1
    assert app._caption()[0].endswith("1 shelf away")


def test_a_cart_for_a_newer_api_level_is_listed_as_needing_an_update(tmp_path):
    """#271: an entry whose `moybyte.api` is above this console's level is
    on the shelf, says so and cannot be got; one that names none needs the
    lowest and lists as any other."""
    from runtime import cart_index as ci, moy_store_base, pkg
    repo, net = _shelf()
    ws, app = _ws(tmp_path, net, [repo.url("index.json")])
    _open(ws, app)
    rows = {r["cart"]["name"]: r for r in app.rows}
    zap, jet = rows["Zap"], rows["Jet Pot"]
    level = moy_store_base.API_LEVEL + 1
    zap["cart"]["moybyte"] = {"api": level}
    assert app._shown(zap) == "newer" and gc.STATE_WORD["newer"] == "Needs update"
    why = ci.newer_why(zap["cart"])
    assert "API level %d" % level in why and "Update in Settings" in why
    assert app._state_line(zap) == (why, "warn", "danger")
    assert app.blocker(zap) == why
    assert app._shown(jet) == "get" and ci.newer_why(jet["cart"]) is None
    zap["state"] = "update"
    assert app._shown(zap) == "newer", "an update that needs a newer firmware waits too"
    assert pkg.blocker(app._inst, zap["cart"], zap["plan"], None, True) == why
    assert not app.no_addon
    app.no_addon = True
    assert app._caption()[0].endswith(gc.NO_ADDON)


def test_a_card_opens_its_page_and_back_lands_on_it(tmp_path):
    repo, net = _shelf()
    ws, app = _ws(tmp_path, net, [repo.url("index.json")])
    _open(ws, app)
    assert _focus(app) == app._card_id(app.rows[0])
    _press(ws, app, "right")
    _press(ws, app, "a")
    assert app.phase == "cart" and app.cur is app.rows[1]
    assert _focus(app) == gc.vid("GET")
    assert ws.bar_layer._title("app") == app.rows[1]["cart"]["name"]
    assert app.back() and app.phase == "list"
    _frames(ws)
    assert _focus(app) == app._card_id(app.rows[1])
    assert ws.bar_layer._title("app") == "Get Carts"


def test_wifi_off_offers_the_wifi_page_and_looks_again_on_the_way_back(tmp_path):
    repo, net = _shelf()
    net.up = False
    ws, app = _ws(tmp_path, net, [repo.url("index.json")])
    _open(ws, app)
    assert app.phase == "nowifi"
    assert app._current_verbs() == ("TRY AGAIN", "WIFI")
    assert _focus(app) == gc.vid("WIFI"), "Wi-Fi is the verb that goes on"
    assert ws.wifi_icon_kind() == "wifi_off"
    _press(ws, app, "a")
    assert app._away and app._inst.wifi_open()
    assert ws.settings_layer.showing("wifi")
    net.up = True                                 # a network joined there
    ws.settings_layer.back()                      # B on the panel: back to Get Carts
    assert ws.wm.top_is("getcarts")
    for _ in range(40):
        _frames(ws, 1)
        if app.phase not in ("nowifi", "checking"):
            break
    assert not app._away
    assert app.phase == "list", app.phase


@pytest.mark.parametrize("phase,title", [("unreached", "Shelf away"), ("nomemory", "Memory full"),
                                         ("nonet", "No internet")])
def test_a_shelf_out_of_reach_offers_try_again_alone(tmp_path, phase, title):
    repo, net = _shelf()
    ws, app = _ws(tmp_path, net, [repo.url("index.json")])
    _open(ws, app)
    app._go(phase)
    _frames(ws)
    icon, got, _lines = app._empty_words()
    assert (icon, got) == ("warn", title)
    assert app._current_verbs() == ("TRY AGAIN",)
    assert _focus(app) == gc.vid("TRY AGAIN")


def test_remove_asks_in_a_dialog_whose_first_stop_is_cancel(tmp_path):
    repo, net = _shelf()
    ws, app = _ws(tmp_path, net, [repo.url("index.json")])
    _open(ws, app)
    app._tap_row(0)
    app._press("GET")
    for _ in range(40):
        _frames(ws, 1)
        if app.phase == "done":
            break
    assert app.phase == "done"
    _frames(ws)
    assert app.toast is not None and app.toast[0] == "Jet Pot is on your shelf"
    _press(ws, app, "left")                       # Remove
    assert _focus(app) == gc.vid("REMOVE")
    _press(ws, app, "a")
    _frames(ws)
    assert app.asking and _focus(app) == "Cancel"
    _press(ws, app, "a")                          # Cancel: nothing removed
    assert not app.asking and (tmp_path / "carts" / "jet.moy").exists()


def test_a_toast_goes_with_the_next_key(tmp_path):
    repo, net = _shelf()
    ws, app = _ws(tmp_path, net, [repo.url("index.json")])
    _open(ws, app)
    app._say("Hello")
    _frames(ws)
    assert app.toast is not None
    _press(ws, app, "right")
    assert app.toast is None


def test_a_settled_shelf_paints_nothing(tmp_path):
    """With no input the redraw gate draws no frame, and a press that moves
    nothing draws one frame of the same pixels and asks for none after it."""
    repo, net = _shelf()
    ws, app = _ws(tmp_path, net, [repo.url("index.json")])
    _open(ws, app)
    quiesce(ws)
    drv = host_app.ConsoleDriver(ws)
    for _ in range(4):
        drv.frame(_DT)
    quiesce(ws)                                   # the first open's achievement toast
    ws.mark_dirty()
    for _ in range(4):
        drv.frame(_DT)
    drawn = ws.frame_state.frames_drawn
    for _ in range(10):
        drv.frame(_DT)
    assert ws.frame_state.frames_drawn == drawn, "an idle shelf painted"
    before = bytes(ws.sys_canvas._buf)
    drv.press("left")                             # on a row with nothing beside it
    for _ in range(6):
        drv.frame(_DT)
    assert ws.frame_state.frames_drawn == drawn + 1, "one frame for the press, then none"
    assert bytes(ws.sys_canvas._buf) == before


def test_the_desk_shows_the_focused_card_in_the_pane(tmp_path):
    repo, net = _shelf()
    ws, app = _ws(tmp_path, net, [repo.url("index.json")], sys_size=(1024, 600),
                  panel_diagonal_in=7.0, windowed=True)
    ws.home.open_desk()
    _open(ws, app)
    win = ws.wm.windows["getcarts"]
    win.x, win.y = 112, 52
    ws.wm.resize_window(win, 900, 536)           # the target's window
    _frames(ws)
    assert app.desk and app.cur is app.rows[0] and app.phase == "list"
    _press(ws, app, "right")
    assert app.cur is app.rows[1] and app.phase == "cart"
    assert not app.has_page(), "the pane is the shelf's: no back chevron"
    host = app.page_host()
    assert host.box(gc.vid("GET")) is not None, "the pane's verbs are in the foot"
    assert host.box("check") is not None


@pytest.mark.parametrize("desk", [False, True])
def test_an_open_lands_on_the_shelf_first_card(tmp_path, desk):
    """The first open after a boot (the check's way) and a later one (the
    shelf held) land alike: the shelf, the keys on its first card, no
    cart's page and no verbs. The focus landing there is no pick: on the
    desk the pane shows that card beside the shelf."""
    repo, net = _shelf()
    kw = dict(sys_size=(1024, 600), panel_diagonal_in=7.0, windowed=True) if desk else {}
    ws, app = _ws(tmp_path, net, [repo.url("index.json")], **kw)
    if desk:
        ws.home.open_desk()

    def landed():
        _frames(ws, 4)
        st = app.state()
        assert app.phase == "list" and not app.has_page()
        assert st.view == ("desk" if desk else "shelf")
        assert _focus(app) == app._card_id(app.rows[0])
        assert not (st.v_get or st.v_play or st.v_remove), "a verb shows with no card picked"
        if desk:
            assert app.cur is app.rows[0] and st.name == app.rows[0]["cart"]["name"]

    _open(ws, app)
    landed()
    _press(ws, app, "right")
    if desk:
        assert app.phase == "cart" and app.cur is app.rows[1]
    ws.wm._close_window("getcarts") if desk else app.close()
    _open(ws, app)
    landed()


def test_a_needed_file_names_its_host_only_where_the_cart_does_not_say_it(tmp_path):
    """A Needs fact from the host the From fact names is the file alone; one
    from another host names that host too."""
    repo = Repo("https://mit.example/carts", "Test carts")
    for cid, name in (("dm", "Dungeon"), ("dx", "Dungeon X")):
        repo.add(cid, name=name, runtime="lua", modules=(),
                 external=[("game.wad", b"WAD!" * 3000, "pkg/game.wad")])
    other = [c for c in repo.carts if c["id"] == "dx"][0]["external"][0]
    other["archive"]["urls"] = ["https://files.example/game.tar.gz"]
    repo.files["index.json"] = repo.index()
    ws, app = _ws(tmp_path, MemNet(repo.routes()), [repo.url("index.json")])
    _open(ws, app)
    facts = {r["cart"]["id"]: dict(app._info(r, True)) for r in app.rows}
    assert facts["dm"]["From"] == "mit.example" and facts["dm"]["Needs"] == "game.wad"
    assert facts["dx"]["Needs"] == "game.wad from files.example"


def test_enter_never_cancels_a_download_and_b_does(tmp_path):
    """A kid presses A at anything, and twice after Get: while the download
    runs no key but B (Esc) reaches Cancel, and the hint strip says so."""
    import os
    repo = Repo("https://mit.example/carts", "Test carts")
    repo.add("jet", name="Jet Pot", extra={"big.bin": os.urandom(400000)})
    net = MemNet(repo.routes())
    ws, app = _ws(tmp_path, net, [repo.url("index.json")])
    _open(ws, app)
    app._tap_row(0)
    _frames(ws, 1)
    _press(ws, app, "a")                          # Get
    for _ in range(4):
        if app.phase == "getting":
            break
        _frames(ws, 1)
    assert app.phase == "getting"
    app.job.step_ms = 0                           # a slice a frame, never the whole
    _press(ws, app, "a")                          # the second press of Get's
    _press(ws, app, "down")
    _press(ws, app, "a")
    assert app.phase == "getting", "A cancelled the download"
    app.handle_input(_In("b"))
    assert app.phase == "cart" and app.toast[0] == "Stopped. Nothing changed."
    assert not (tmp_path / "carts" / "jet.moy").exists()


def test_the_browsers_taps_are_buttons_the_page_draws(tmp_path):
    """The browser suites tap Get and I agree where the page draws them
    (`web_e2e.get_carts_taps`)."""
    repo = Repo("https://mit.example/carts", "Test carts")
    repo.add("dm", name="Dungeon", runtime="lua", modules=(),
             external=[("game.wad", b"WAD!" * 3000, "pkg/game.wad")])
    ws, app = _ws(tmp_path, MemNet(repo.routes()), [repo.url("index.json")])
    _open(ws, app)
    _press(ws, app, "a")
    assert app.phase == "cart" and app.page_host().box(gc.vid("GET")) is not None
    _press(ws, app, "a")
    for _ in range(40):
        _frames(ws, 1)
        if app.phase == "licence":
            break
    assert app.phase == "licence"
    assert _focus(app) == gc.vid("NO"), "No has the focus on a licence"
    assert app.page_host().box(gc.vid("I AGREE")) is not None
    assert "fun" in app.state().licence


def test_a_press_owes_the_next_frame_a_repaint(tmp_path):
    """Get is pressed in the cart page's frame: the page it opens is owed
    to the frame after, which the console paints with no input."""
    repo, net = _shelf()
    ws, app = _ws(tmp_path, net, [repo.url("index.json")])
    _open(ws, app)
    _press(ws, app, "a")
    assert app.phase == "cart"
    app.handle_input(_In("a"))
    ws.mark_dirty()
    ws.frame(_DT)
    assert app.phase != "cart" and app.moved()
    drawn = ws.frame_state.frames_drawn
    ws.frame(_DT)
    assert ws.frame_state.frames_drawn == drawn + 1


def test_play_on_an_installed_app_opens_the_app_not_its_stub(tmp_path):
    """An app's folder carries a stub main.py for an older console; Play on
    its page opens the app, as the home's tap does."""
    repo, net = _shelf()
    ws, app = _ws(tmp_path, net, [repo.url("index.json")])
    _open(ws, app)
    app.cur = {"cart": {"folder": "moybyte.calc.moy", "runtime": "python"},
               "state": "installed"}
    app._go("cart")
    app._press("PLAY")
    _frames(ws)
    assert ws.wm.top_kind() == "calc", "the stub ran: " + str(ws.wm.top_kind())
