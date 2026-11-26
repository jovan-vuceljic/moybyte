"""A Zero's Wi-Fi, managed from the page it serves.

Three halves, each against the next one's real body:

  * the board's backend (`device/zero_wifi.py`) over a fake radio and a
    fake clock: what the document says (SSIDs, never a password), saving and
    forgetting without leaving the network, a scan asked and polled, and the
    move -- saved only once joined, and a failed one back on the network it
    left;
  * the route on the boards' WebHost: sealed both ways, a POST only asks,
    the poll steps the backend;
  * the page's station (`firmware/web_runner/wifi_link.py`) under the
    console's own Settings panel, pumped against the backend as the worker
    pumps it: the panel asks before a move, saves instead where asked, and
    says where the console is after a move that failed.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "device"))
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "firmware" / "web_runner"))

import zero_wifi                                               # noqa: E402

HOME, RPT, AWAY = "Home", "Home_RPT", "Elsewhere"


class Clock:
    def __init__(self):
        self.ms = 1000

    def __call__(self):
        return self.ms


class Radio:
    """moy_net's wifi functions: `nets` {ssid: (password, rssi)} in range; a
    join comes up `delay` ms after it is asked where the password matches,
    is refused (15) where it does not, and never answers (201) out of range."""

    def __init__(self, clock, nets, on=None, delay=300):
        self.clock = clock
        self.nets = nets
        self.delay = delay
        self.ssid = on
        self.up = on is not None
        self.want = None
        self.at = 0
        self.reason = 0
        self.scans = 0
        self.scan_at = None
        self.mdns = []
        self.forgot = []
        self.asked = []

    def _tick(self):
        if self.want is None or self.clock() < self.at:
            return
        ssid, pw = self.want
        net = self.nets.get(ssid)
        if net is not None and net[0] == pw:
            self.ssid, self.up, self.want = ssid, True, None
        else:
            self.reason = 15 if net is not None else 201

    def wifi_status(self):
        self._tick()
        ip = "10.0.0.%d" % (sorted(self.nets).index(self.ssid) + 2) if self.up else None
        return (True, True, self.up, self.ssid if self.up else None, ip, self.reason, True)

    def wifi_scan(self, wait=True):
        if self.scan_at is None:
            self.scan_at = self.clock()
            self.scans += 1
        if not wait and self.clock() - self.scan_at < 500:
            return None
        self.scan_at = None
        return [(s.encode(), r, 3 if p else 0) for s, (p, r) in self.nets.items()]

    def wifi_connect(self, ssid, password):
        self.asked.append(ssid)
        self.up = False
        self.want = (ssid, password)
        self.at = self.clock() + self.delay
        self.reason = 0

    def wifi_disconnect(self):
        self.up = False
        self.want = None

    def wifi_mdns(self, name):
        self.mdns.append(name)
        return True

    def wifi_forget(self, ssid):
        self.forgot.append(ssid)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(zero_wifi, "ticks_ms", c)
    return c


def _board(tmp_path, clock, saved=((HOME, "homepw"),), on=HOME, stranded=None):
    store = tmp_path / "wifi.json"
    store.write_text(json.dumps({"networks": [{"ssid": s, "password": p} for s, p in saved]}))
    radio = Radio(clock, {HOME: ("homepw", -50), RPT: ("rptpw", -70)}, on=on)
    return zero_wifi.ZeroWifi(str(store), "zero", radio=radio, stranded=stranded,
                              join_ms=4000, back_ms=4000, leave_ms=500), radio, store


def _run(w, clock, ms, step=100):
    for _ in range(ms // step):
        clock.ms += step
        w.step()


def _saved(store):
    return json.loads(store.read_text())["networks"]


# -- the board's backend ---------------------------------------------------------

def test_the_refusals_are_the_consoles():
    import device_wifi
    assert zero_wifi.REFUSED == device_wifi.REFUSED


def test_the_document_names_networks_and_never_a_password(tmp_path, clock):
    w, _radio, _ = _board(tmp_path, clock, saved=((HOME, "homepw"), (RPT, "rptpw")))
    doc = json.loads(w.answer())
    assert doc["connected"] and doc["ssid"] == HOME and doc["ip"]
    assert doc["saved"] == [HOME, RPT]
    assert doc["host"] == "zero.local"
    assert "homepw" not in w.answer() and "rptpw" not in w.answer()


def test_a_scan_is_asked_and_polled_never_waited(tmp_path, clock):
    w, radio, _ = _board(tmp_path, clock)
    assert w.request({"action": "scan"}) == (True, "scanning")
    doc = json.loads(w.answer())
    assert doc["scanning"] and doc["scan_id"] == 0
    assert w.busy()
    _run(w, clock, 600)
    doc = json.loads(w.answer())
    assert not doc["scanning"] and doc["scan_id"] == 1
    assert [n[0] for n in doc["nets"]] == [HOME, RPT]       # strongest first
    assert doc["nets"][0][1] == 100 and doc["nets"][0][2] is True
    assert doc["signal"] == 100
    assert radio.scans == 1 and not w.busy()


def test_a_scan_keeps_the_strongest_and_the_saved_and_gives_them_back(tmp_path, clock):
    """What a scan leaves in the board's heap is bounded, and goes when the
    panel's asks stop (zero_host, THE HEAP'S SHAPE)."""
    w, radio, _ = _board(tmp_path, clock, saved=((HOME, "homepw"), (RPT, "rptpw")))
    radio.nets = dict(("street %02d" % i, ("pw", -40 - i)) for i in range(30))
    radio.nets.update({HOME: ("homepw", -85), RPT: ("rptpw", -90)})
    w.request({"action": "scan"})
    _run(w, clock, 600)
    doc = json.loads(w.answer())
    names = [n[0] for n in doc["nets"]]
    assert names[:zero_wifi.NETS_KEPT] == ["street %02d" % i for i in range(zero_wifi.NETS_KEPT)]
    assert sorted(names[zero_wifi.NETS_KEPT:]) == sorted([HOME, RPT])    # saved, in range
    assert doc["signal"] == 30                      # the joined network's, as heard
    clock.ms += zero_wifi.NETS_HOLD_MS - 100
    assert not w.busy() and w.nets                  # the panel may still ask
    w.answer()
    clock.ms += zero_wifi.NETS_HOLD_MS - 100
    assert not w.busy() and w.nets                  # ...and each ask holds it
    clock.ms += 200
    assert not w.busy() and w.nets == []
    doc = json.loads(w.answer())
    assert doc["nets"] == [] and doc["signal"] == 30 and doc["scan_id"] == 1


def test_saving_and_forgetting_leave_the_network_alone(tmp_path, clock):
    w, radio, store = _board(tmp_path, clock)
    assert w.request({"action": "add", "ssid": RPT, "password": "rptpw"}) == (True, "saved")
    assert [n["ssid"] for n in _saved(store)] == [HOME, RPT]    # after, not first
    assert w.request({"action": "add", "ssid": RPT, "password": "new"})[0]
    assert _saved(store)[1] == {"ssid": RPT, "password": "new"}
    assert w.request({"action": "forget", "ssid": HOME}) == (True, "forgotten")
    assert [n["ssid"] for n in _saved(store)] == [RPT]
    assert radio.forgot == [HOME]
    assert w.request({"action": "forget", "ssid": AWAY}) == (False, "not saved")
    assert radio.asked == [] and radio.up and not w.busy()


def test_junk_is_refused_by_name(tmp_path, clock):
    w, _radio, _ = _board(tmp_path, clock)
    assert w.request({"action": "fly"})[0] is False
    assert w.request({"action": "join"}) == (False, "no network named")
    assert w.request({"action": "add", "ssid": "x" * 33})[0] is False
    assert w.request({"action": "add", "ssid": "x", "password": "p" * 64})[0] is False


def test_a_move_is_answered_before_the_radio_leaves(tmp_path, clock):
    w, radio, store = _board(tmp_path, clock)
    assert w.request({"action": "join", "ssid": RPT, "password": "rptpw"}) == (True, "switching")
    doc = json.loads(w.answer())
    assert doc["switch"]["ssid"] == RPT and doc["connected"]
    w.step()
    assert radio.asked == []                   # the answer has its LEAVE_MS
    _run(w, clock, 600)
    assert radio.asked == [RPT]
    _run(w, clock, 400)
    doc = json.loads(w.answer())
    assert doc["ssid"] == RPT and doc["switch"] is None
    assert doc["last"] == {"id": 1, "ssid": RPT, "ok": True, "on": RPT, "why": ""}
    assert _saved(store)[0] == {"ssid": RPT, "password": "rptpw"}   # first: the next boot's
    assert radio.mdns == ["zero"]


def test_a_refused_password_goes_back_and_saves_nothing(tmp_path, clock):
    w, radio, store = _board(tmp_path, clock)
    before = store.read_text()
    w.request({"action": "join", "ssid": RPT, "password": "wrong"})
    _run(w, clock, 1000)
    assert radio.asked == [RPT, HOME]          # refused at once, not at the window
    _run(w, clock, 500)
    doc = json.loads(w.answer())
    assert doc["ssid"] == HOME and doc["connected"]
    assert doc["last"]["ok"] is False and doc["last"]["on"] == HOME
    assert doc["last"]["why"] == "the password was refused"
    assert store.read_text() == before


def test_a_network_out_of_range_waits_its_window_then_goes_back(tmp_path, clock):
    w, radio, _store = _board(tmp_path, clock)
    w.request({"action": "join", "ssid": AWAY, "password": "x"})
    _run(w, clock, 3000)
    assert radio.asked == [AWAY]
    _run(w, clock, 2000)
    assert radio.asked == [AWAY, HOME]
    _run(w, clock, 500)
    last = json.loads(w.answer())["last"]
    assert last["ok"] is False and last["on"] == HOME and last["why"] == "no answer"


def test_a_saved_network_moves_with_its_saved_password(tmp_path, clock):
    w, radio, _ = _board(tmp_path, clock, saved=((HOME, "homepw"), (RPT, "rptpw")))
    w.request({"action": "join", "ssid": RPT})
    _run(w, clock, 1200)
    assert json.loads(w.answer())["last"]["ok"] is True


def test_joining_the_network_it_is_on_moves_nothing(tmp_path, clock):
    w, radio, _ = _board(tmp_path, clock)
    assert w.request({"action": "join", "ssid": HOME}) == (True, "already")
    assert not w.busy() and radio.asked == []


def test_one_move_at_a_time(tmp_path, clock):
    w, _radio, _ = _board(tmp_path, clock)
    w.request({"action": "join", "ssid": RPT, "password": "rptpw"})
    assert w.request({"action": "join", "ssid": HOME}) == (False, "a switch is under way")


def test_a_board_that_reaches_neither_network_is_stranded(tmp_path, clock):
    told = []
    w, radio, _ = _board(tmp_path, clock, stranded=lambda: told.append(1))
    w.request({"action": "join", "ssid": AWAY, "password": "x"})
    radio.nets.pop(HOME)                       # ...and the old one went too
    _run(w, clock, 10000)
    assert told == [1]
    assert json.loads(w.answer())["last"]["on"] is None


# -- the route ------------------------------------------------------------------

@pytest.fixture
def host(tmp_path, clock):
    import seal_client
    from runtime import net_binding as nb
    from moy_webhost import WebHost
    carts = tmp_path / "carts"
    carts.mkdir()
    (tmp_path / "system").mkdir()
    h = WebHost(str(carts), auth=str(tmp_path / "system"))
    h.wifi, h.radio, h.store = _board(tmp_path, clock)
    h.handle_http("GET", "/sync", b"")
    h.page = seal_client.Browser(h.handle_http)
    h.page.pair_token(nb.web_token())
    return h


def _call(host, method, path, body=None):
    import seal_client
    try:
        code, plain = host.page.call(method, path, (body or "").encode())
    except seal_client.Refused as e:
        return e.status, e.doc
    return code, json.loads(plain.decode())


def test_the_route_is_sealed_both_ways(host):
    for method, body in (("GET", None), ("POST", '{"action":"forget","ssid":"Home"}')):
        resp = host.handle_http(method, "/wifi", body)
        assert int(resp.split(b" ")[1]) == 401, method
    assert host.radio.forgot == []


def test_a_paired_page_reads_and_asks(host, clock):
    code, doc = _call(host, "GET", "/wifi")
    assert code == 200 and doc["ssid"] == HOME and doc["saved"] == [HOME]
    code, doc = _call(host, "POST", "/wifi", '{"action":"add","ssid":"Home_RPT","password":"rptpw"}')
    assert code == 200 and doc["ok"] is True and doc["saved"] == [HOME, RPT]
    code, doc = _call(host, "POST", "/wifi", '{"action":"forget","ssid":"Nope"}')
    assert code == 409 and doc["ok"] is False
    code, _ = _call(host, "POST", "/wifi", "not json")
    assert code == 400


def test_the_poll_steps_a_move(host, clock, monkeypatch):
    import moy_webhost
    _call(host, "POST", "/wifi", '{"action":"join","ssid":"Home_RPT","password":"rptpw"}')
    assert host.wifi.busy()
    monkeypatch.setattr(moy_webhost.moy_net, "web_take", lambda: None, raising=False)
    for _ in range(20):
        clock.ms += 100
        host.poll()
    assert not host.wifi.busy() and host.wifi.last["ok"] is True


# -- the page's station under the console's own panel ------------------------------

class Pump:
    """The worker's pump between the page's station and the board, with the
    page reaching the board only over the network it started on."""

    def __init__(self, link, board, radio):
        self.link, self.board, self.radio = link, board, radio
        self.page_net = radio.ssid
        self.said = []

    def reached(self):
        st = self.radio.wifi_status()
        return st[2] and st[3] == self.page_net

    def once(self):
        body = self.link.take_json()
        if not body and not self.link.wants_poll():
            return
        if not self.reached():
            self.said.append(self.link.ack(False, ""))
            return
        if body:
            ok, msg = self.board.request(json.loads(body))
            out = self.link.ack(ok, self.board.answer(ok, msg))
        else:
            out = self.link.ack(True, self.board.answer())
        if out:
            self.said.append(out)


@pytest.fixture
def panel(tmp_path, clock, monkeypatch):
    import wifi_link
    from ws_helpers import build_ws
    monkeypatch.setattr(wifi_link, "_ticks_ms", clock)
    board, radio, store = _board(tmp_path, clock)
    link = wifi_link.BoardWifi(json.loads(board.answer()))
    ws = build_ws(tmp_path)
    ws.wifi = link
    pump = Pump(link, board, radio)

    def run(ms):
        for _ in range(ms // 100):
            clock.ms += 100
            board.step()
            pump.once()
            if sl._wifi_wake is not None:     # the panel's wake, on this clock
                sl._wifi_tick()
            ws.frame(1 / 30)
    ws.open_settings()
    sl = ws.settings_layer
    sl.open_page("wifi")
    run(1500)
    return ws, sl, link, board, radio, store, pump, run


def test_the_panel_lists_the_boards_networks(panel):
    ws, sl, link, *_ = panel
    assert [n[0] for n in sl.wifi_nets] == [HOME, RPT]
    assert sl.wifi_known == [HOME]
    assert link.status() == (True, HOME, "10.0.0.2")
    assert ws.wifi_icon_kind() == "wifi"


def test_a_new_network_is_saved_without_a_move(panel):
    ws, sl, link, board, radio, store, pump, run = panel
    sl._wifi_connect(RPT, "rptpw")
    assert ws.confirm.open and ws.confirm.verb == "switch_save"
    ws.frame(1 / 30)                          # the three-button question draws
    ws.confirm.saved()
    run(500)
    assert sl.wifi_known == [HOME, RPT]
    assert [n["ssid"] for n in _saved(store)] == [HOME, RPT]
    assert radio.asked == [] and link.status()[1] == HOME


def test_forgetting_drops_nothing(panel):
    ws, sl, link, board, radio, store, pump, run = panel
    board.request({"action": "add", "ssid": RPT, "password": "rptpw"})
    run(3000)
    sl.wifi_sel = [n[0] for n in sl.wifi_nets].index(RPT)
    sl._wifi_forget()
    run(500)
    assert sl.wifi_known == [HOME] and [n["ssid"] for n in _saved(store)] == [HOME]
    assert radio.up and radio.ssid == HOME


def test_a_move_asks_first_and_one_that_fails_says_where_the_console_is(panel):
    ws, sl, link, board, radio, store, pump, run = panel
    sl._wifi_connect(RPT, "wrong")
    assert ws.confirm.open and ws.confirm.title == "Move the console to %s?" % RPT
    assert radio.asked == []
    ws.confirm.answer()
    ws.frame(1 / 30)
    assert sl.wifi_joining is not None
    run(3000)
    assert any('"move"' in s for s in pump.said)
    assert radio.ssid == HOME and radio.up
    assert sl.wifi_joining is None
    assert ws.confirm.open and ws.confirm.verb == "tell"
    assert ws.confirm.title == "Still on %s" % HOME
    assert RPT not in [n["ssid"] for n in _saved(store)]


def test_a_move_that_worked_leaves_the_page_waiting_for_the_worker(panel):
    ws, sl, link, board, radio, store, pump, run = panel
    sl._wifi_connect(RPT, "rptpw")
    ws.confirm.answer()
    ws.frame(1 / 30)
    run(3000)
    moves = [json.loads(s) for s in pump.said if '"move"' in s]
    assert moves and moves[0]["move"]["host"] == "zero.local"
    assert moves[0]["move"]["ms"] == 4000 + 4000 + 6000
    assert radio.ssid == RPT
    assert _saved(store)[0]["ssid"] == RPT
    assert sl.wifi_joining is not None        # the page never hears: the worker says it moved
    link.moved(RPT)                           # ...once it has waited out the board's windows
    run(300)
    assert sl.wifi_joining is None and not ws.confirm.open
    assert link.status() == (True, "moved to %s" % RPT, None)   # the bar's popover, the row
    assert link.take_json() == "" and not link.wants_poll()
    assert ws.wifi_icon_kind() == "wifi"     # the board is on a network, elsewhere


def test_a_cart_is_never_handed_the_boards_station(panel):
    ws, _sl, link, *_ = panel
    assert link.CARTS is False
    assert link.connect(RPT, "rptpw") is False


def test_forget_is_the_network_the_cursor_is_on(panel):
    """Focus walked up to a network and back down to Forget: Forget names and
    forgets that one, not the network that last left the rows."""
    from runtime import host_app
    ws, sl, link, board, radio, store, pump, run = panel
    board.request({"action": "add", "ssid": RPT, "password": "rptpw"})
    sl._wifi_rescan()
    run(1500)
    drv = host_app.ConsoleDriver(ws)

    def key(code):
        drv.key_down(code)
        drv.frame(1 / 30)
        drv.key_up(code)
        for _ in range(2):
            board.step()
            pump.once()
            drv.frame(1 / 30)
    assert sl._sub_focused == "rescan" and sl.wifi_sel == 0
    key(274)                                   # up: the last network, Home_RPT
    key(275)
    key(275)                                   # down, down: Forget
    assert sl._sub_focused == "forget"
    key(13)
    run(500)
    assert [n["ssid"] for n in _saved(store)] == [HOME]
