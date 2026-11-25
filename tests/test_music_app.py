"""The Music app (#110, runtime/apps/music_app.py, docs/media/music_2026-11/
README.md): its identity cart registers it; a station plays through the
media face and puts the app's status item in the bar, whose section's ids
are the app's own; Add a station refuses an address that will not play and
keeps the one that will; Back leaves (on the desk, minimises) and the stream
plays on; Now playing's keys and a tap on a file's bar seek it; a console with no media service shows the no-audio page; and the
media face's place and length reach the card."""

from pathlib import Path

import pytest

from runtime import music_app as M
from runtime.status_items import ITEMS, ON, PAUSED, ERROR
from ws_helpers import build_desktop_ws, build_ws, make_drv

TONE = Path(__file__).resolve().parent / "fixtures" / "media" / "tone_1k.mp3"
GROOVE = M.STATIONS[0]


class Face:
    """The media face, faked: what `now()` answers and what was asked."""

    def __init__(self):
        self.n = None
        self.played = []
        self.seeks = []
        self.end = None             # last(): how the last run ended

    def now(self):
        return dict(self.n) if self.n else None

    def last(self):
        return self.end

    def play(self, src, label=None):
        if src.startswith("https://"):
            raise OSError(93, "https is refused")
        self.played.append(src)
        self.n = {"state": "playing", "paused": False, "src": src, "station": "",
                  "title": "Boards of Canada - Dayvan Cowboy", "entry": 0, "entries": 1,
                  "volume": 60, "pid": 9, "label": label or "", "who": "jukebox"}

    def pause(self):
        self.n["paused"] = True

    def resume(self):
        self.n["paused"] = False

    def stop(self):
        self.n = None

    def next(self):
        return True

    def prev(self):
        return True

    def volume(self, v=None):
        if v is not None:
            self.n["volume"] = v
        return self.n["volume"]

    def seek(self, s):
        self.seeks.append(s)
        self.n["at"] = s
        return True


@pytest.fixture
def face():
    s = M.STREAM
    s._end()
    f = Face()
    s.face = f
    yield f
    s._end()
    s.face = None
    s.stations = M.STATIONS
    for it in ITEMS.slots:
        if it.pid:
            ITEMS._free(it)


def _app(ws):
    return ws.app("jukebox")


def _put(app, **values):
    """States of the page written as its handler."""
    app.do(lambda: [setattr(M.s, k, v) for k, v in values.items()])


def _frames(drv, n=1):
    for _ in range(n):
        drv.frame(1 / 30)


def _settle(ws, n=4):
    for _ in range(n):
        ws.mark_dirty()
        ws.frame(1 / 30)
        ws.input_policy.sync()          # the next key pass's mode (handle_input's)


def test_music_is_a_registered_app_its_cart_claims(tmp_path):
    ws = build_ws(tmp_path)
    app = _app(ws)
    cart = next(c for c in ws.carts.all if c["title"] == "Music")
    assert app.is_app(cart) and ws.spine.is_system_app(cart)
    assert ws.spine.open_app(app) and ws.wm.top_kind() == "jukebox"


def test_a_station_plays_and_its_status_item_follows_the_stream(tmp_path, face):
    ws = build_ws(tmp_path)
    app = _app(ws)
    ws.spine.open_app(app)
    _settle(ws)
    app.do(M.play, "r0")
    assert face.played == [GROOVE[2]]
    it = ITEMS.at(0)
    assert it is not None and it.icon == "music" and it.app == "Music" and it.state == ON
    c = M.STREAM.card
    assert M.lines(c) == ("Dayvan Cowboy", "Boards of Canada · Groove Salad")
    _settle(ws, 1)
    app.do(M.play, "r0")                            # the playing row: Enter pauses
    assert face.n["paused"] and ITEMS.at(0).state == PAUSED
    M.STREAM.step(1)                                # the next station
    assert face.played[-1] == M.STATIONS[1][2]
    M.STREAM.stop()
    assert face.n is None and ITEMS.count() == 0


class StampedFace(Face):
    """A face with the board's stamp: one int over what now() shows, and a
    count of the now() reads."""

    def __init__(self):
        Face.__init__(self)
        self.reads = 0

    def now(self):
        self.reads += 1
        return Face.now(self)

    def stamp(self):
        n = self.n
        return None if n is None else hash((n["paused"], n["volume"], n["title"]))


def test_a_still_stamp_skips_the_read_and_a_moved_one_reads(tmp_path, face):
    """A station playing on under a game: the poll reads the stamp alone;
    a pause moves it and the card follows."""
    f = StampedFace()
    M.STREAM.face = f
    build_ws(tmp_path)
    M.STREAM.play("radio", "Groove Salad", GROOVE[2])
    M.STREAM.poll()
    reads = f.reads
    for _ in range(5):
        M.STREAM.poll()
    assert f.reads == reads
    f.n["paused"] = True
    M.STREAM.poll()
    assert f.reads == reads + 1 and M.STREAM.card["paused"]


def test_music_plays_as_the_shell_while_a_game_is_current(tmp_path, face):
    """Music is the shell's: a game's run current on the desk (in its
    window, or the Editor's run) does not make Music's verbs that game's,
    so the face hears the shell and the wake and status item are the
    shell's."""
    from runtime import moy_log as L
    from runtime import moybyte
    ws = build_desktop_ws(tmp_path)
    ws.home.open_desk()
    cart = next(c for c in ws.carts.all if c.get("title") == "Star Catcher")
    ws.open_in_editor(cart)
    _settle(ws)
    game = ws.run.player.pid
    assert game and L.current() == game
    heard = []
    play = face.play
    face.play = lambda src, label=None: (heard.append(L.current()), play(src, label))[1]
    app = _app(ws)
    ws.spine.open_app(app)
    _settle(ws)
    app.do(M.play, "r0")
    assert heard == [L.SHELL] and L.current() == game
    assert moybyte.WAKES.by_id[M.STREAM.wake][1] == L.SHELL
    assert ITEMS.at(0).pid == L.SHELL
    M.STREAM.stop()


def test_a_station_that_fails_shows_the_danger_state_and_tries_again(tmp_path, face):
    ws = build_ws(tmp_path)
    ws.spine.open_app(_app(ws))
    M.STREAM.play("radio", "Secret Agent", "http://x/y")
    face.n["state"] = "failed"
    M.STREAM.poll()
    assert M.lines(M.STREAM.card) == ("Secret Agent", "Not answering")
    assert ITEMS.at(0).state == ERROR
    M.STREAM.toggle()                               # Try again: played again
    assert face.played == ["http://x/y", "http://x/y"]


def test_the_section_is_music_s_card_in_the_control_center_and_acts(tmp_path, face):
    """Music's section is a page, its compact card (music_card): the control
    center gives it a slot under Music's name, in the first view, and its
    main button plays or pauses; the head opens the app."""
    import music_card
    ws = build_ws(tmp_path)
    ws.spine.open_app(_app(ws))         # a station is played from Music, which makes the section
    _settle(ws, 1)
    M.STREAM.play("radio", GROOVE[0], GROOVE[2])
    ws.home.go_home()
    _settle(ws)
    ws.widget_tap("battery")
    assert ws.sysmenu.open and ws.sysmenu.widget == "battery"
    _settle(ws, 2)
    it = M.STREAM.item
    assert ITEMS.page(it) is music_card.page and ITEMS.panels[it.k].n == 0
    sc = next(s for s in ws.sysmenu.comp.secs if s is not None)
    x, y, w, h = sc.host.box("main")
    px, py, pw, ph = ws.sysmenu.panel_rect()
    assert py <= y and y + h <= py + ph, "the transport in the first view"
    stopped = []
    M.STREAM.toggle = lambda: stopped.append(1)
    try:
        drv = make_drv(ws)
        drv.click(x + w // 2, y + h // 2)
        for _ in range(2):
            drv.frame(1 / 30)
    finally:
        del M.STREAM.toggle
    assert stopped == [1]
    opened = []
    M.STREAM.section.nav = type("Nav", (), {"open_app": lambda self, n: opened.append(n)})()
    hx, hy, hw, hh = sc.engine.slot_rect("head")
    drv.click(hx + hw // 2, hy + hh // 2)
    for _ in range(2):
        drv.frame(1 / 30)
    assert opened == ["jukebox"]


def test_add_a_station_refuses_https_and_keeps_an_http_one(tmp_path, face):
    ws = build_ws(tmp_path)
    app = _app(ws)
    ws.spine.open_app(app)
    _settle(ws, 1)
    app.do(M.add_open)
    _settle(ws, 2)
    assert app.state().view == "add" and ws.input.text_mode
    assert app.page_title() == "Add a station" and app.has_page()
    assert M._check("https://stream.example.org/live.mp3", False) == M.ERR_ADDRESS
    assert M.ERR_ADDRESS == "This address won't play. Use one that starts with http://"
    assert M._check("http://ice1.somafm.com/lush-128-mp3", False) is None
    assert M._check("htt", False) is None and M._check("htt", True) == M.ERR_ADDRESS
    _put(app, url="https://stream.example.org/live.mp3")
    app.do(M.submit)
    assert app.state().view == "add" and app.state().err == M.ERR_ADDRESS
    _put(app, url="http://ice1.somafm.com/lush-128-mp3", name="Lush", err="")
    app.do(M.submit)
    _settle(ws, 2)
    assert app.state().view == "radio" and not ws.input.text_mode
    assert M.STREAM.stations[-1] == ("Lush", "Added", "http://ice1.somafm.com/lush-128-mp3")
    assert face.played[-1] == "http://ice1.somafm.com/lush-128-mp3"
    assert app._prefs.get(M.STATIONS_KEY, None) == [["Lush", "http://ice1.somafm.com/lush-128-mp3"]]
    M.STREAM.stations = M.STATIONS
    app.load_stations()
    assert M.STREAM.stations[-1][0] == "Lush", "the station is read back from the prefs"


@pytest.mark.parametrize("desk", [False, True])
def test_enter_on_add_a_station_types_into_its_address(tmp_path, face, desk):
    """Enter on Add a station opens it with Address focused, so the keys
    typed straight after go there, Enter moves on to Name, and Enter again
    adds and plays it."""
    ws = build_desktop_ws(tmp_path) if desk else build_ws(tmp_path)
    app = _app(ws)
    if desk:
        ws.home.open_desk()
    ws.spine.open_app(app)
    drv = make_drv(ws)
    _settle(ws)
    _put(app, scur=M.ADD)                           # the Add a station row
    app.page_host().focus(M.ADD + "/pick")
    for code in (13, "http://a.example/live", 13, "Test FM", 13):
        if code == 13:
            drv.key_down(13)
            drv.frame(1 / 30)
            drv.key_up(13)
            drv.frame(1 / 30)
            continue
        for ch in code:
            drv.type_char(ord(ch))
            drv.frame(1 / 30)
        for _ in range(3):                          # the typed queue drained
            drv.frame(1 / 30)
    st = app.state()
    assert st.view == "radio", (st.view, st.url, st.name)
    assert M.STREAM.stations[-1] == ("Test FM", "Added", "http://a.example/live")
    assert face.played[-1] == "http://a.example/live"
    M.STREAM.stations = M.STATIONS


def test_mic_cancels_add_a_station(tmp_path, face):
    ws = build_ws(tmp_path)
    app = _app(ws)
    ws.spine.open_app(app)
    app.do(M.add_open)
    assert ws.input_policy.cancel() and app.state().view == "radio"


def test_back_leaves_and_the_stream_plays_on(tmp_path, face):
    ws = build_ws(tmp_path)
    app = _app(ws)
    ws.spine.open_app(app)
    M.STREAM.play("radio", GROOVE[0], GROOVE[2])
    _settle(ws, 1)
    app.do(M.now)
    assert app.page_title() == "Now playing"
    ws.input_policy.back()
    _settle(ws, 1)
    assert app.state().view == "radio" and ws.wm.top_kind() == "jukebox"
    ws.input_policy.back()
    assert ws.wm.top_kind() != "jukebox"
    assert face.n is not None and ITEMS.count() == 1


def test_back_on_the_desk_minimises_the_window(tmp_path, face):
    ws = build_desktop_ws(tmp_path)
    app = _app(ws)
    ws.home.open_desk()
    ws.spine.open_app(app)
    _settle(ws)
    assert "jukebox" in ws.wm.windows and not ws.wm.windows["jukebox"].minimized
    ws.input_policy.back(leave=True)
    assert ws.wm.windows["jukebox"].minimized and ws.wm.focus_key != "jukebox"
    assert ws.spine.open_app(app) and not ws.wm.windows["jukebox"].minimized


def test_a_console_without_media_shows_the_no_audio_page(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "_media", lambda: None)
    M.STREAM.face = None
    assert M.STREAM.media() is None
    ws = build_ws(tmp_path)
    app = _app(ws)
    ws.spine.open_app(app)
    _settle(ws, 2)
    assert not app.state().audio
    assert app.page_host().box("home") is not None, "Back to home is on the page"
    app.leave_asked = True                            # Back to home
    drv = make_drv(ws)
    drv.frame(1 / 30)
    assert ws.wm.top_kind() != "jukebox"


def test_the_folder_lists_songs_and_playlists_with_their_lengths(tmp_path):
    folder = tmp_path / "music"
    folder.mkdir()
    (folder / "Beach trip.mp3").write_bytes(TONE.read_bytes())
    (folder / "Road trip.m3u").write_text("#EXTM3U\nBeach trip.mp3\na.mp3\n")
    (folder / "notes.txt").write_text("not music")
    songs, lists = M._scan(str(folder))
    assert [s[0] for s in songs] == ["Beach trip"] and songs[0][2] == "0:02"
    assert lists == (("Road trip", str(folder / "Road trip.m3u"), "2 songs"),)
    assert M._scan(str(tmp_path / "none")) is None


def test_a_files_place_reaches_the_card():
    c = M.card_of({"state": "playing", "paused": True, "title": "Sunny day drive",
                   "entry": 2, "entries": 12, "volume": 40, "at": 72, "len": 221},
                  ("list", "Road trip mix", "/m/r.m3u"))
    assert (c["at"], c["len"]) == (72, 221)
    assert M.lines(c) == ("Sunny day drive", "Road trip mix · 3 of 12")


def test_left_and_right_seek_a_file_and_a_tap_on_its_bar_seeks_along_it(tmp_path, face):
    """Now playing's keys seek a file SEEK_STEP seconds a press, right
    and left, and a tap at the end of the bar in its head seeks near the
    end; a station has no place to seek."""
    ws = build_ws(tmp_path)
    app = _app(ws)
    ws.spine.open_app(app)
    M.STREAM.play("song", "Tone", str(TONE))
    face.n.update(at=60, len=200)
    M.STREAM.poll()
    _settle(ws, 1)
    app.do(M.now)
    drv = make_drv(ws)
    _settle(ws)
    drv.press("right")
    _frames(drv)
    assert face.seeks == [60 + M.SEEK_STEP]
    drv.press("left")
    _frames(drv)
    assert face.seeks == [60 + M.SEEK_STEP, 60]
    x, y, w, h, fs = M._DRAWN["head"]
    tx = h + 12 * fs
    drv.touch(x + tx + M._bar_w(w - tx, fs) - 2, y + 64 * fs)
    drv.frame(1 / 30)
    drv.touch_up()
    _frames(drv, 2)
    tapped = face.seeks[-1]
    assert len(face.seeks) == 3 and tapped >= 180 and M.STREAM.card["at"] == tapped
    M.STREAM.play("radio", GROOVE[0], GROOVE[2])    # a station has no place to seek
    _settle(ws)
    drv.press("right")
    _frames(drv)
    assert len(face.seeks) == 3


def test_a_station_that_blocks_browsers_says_so(tmp_path, face):
    """In the browser a station's bytes are the page's fetch, which a server
    without CORS headers refuses: the face fails it with EACCES."""
    ws = build_ws(tmp_path)
    ws.spine.open_app(_app(ws))
    M.STREAM.play("radio", "Secret Agent", "http://x/y")
    face.n["state"] = "failed"
    face.n["err"] = 13
    M.STREAM.poll()
    assert M.lines(M.STREAM.card) == ("Secret Agent", "Blocks browsers")


def test_the_folder_lists_the_songs_a_board_keeps_for_its_page(tmp_path, monkeypatch):
    """A board-served page keeps no song: the face's `held` names the board's,
    beside what the page's store has (a playlist rides the sync)."""
    folder = tmp_path / "music"

    class _Face:
        def held(self, f):
            return (("Board song.mp3", 4096),) if f == str(folder) else ()
    monkeypatch.setattr(M, "_media", lambda: _Face())
    assert M._scan(str(folder)) == ((("Board song", str(folder / "Board song.mp3"), ""),), ())
    folder.mkdir()
    (folder / "Mix.m3u").write_text("Board song.mp3\n")
    songs, lists = M._scan(str(folder))
    assert [s[0] for s in songs] == ["Board song"] and [x[0] for x in lists] == ["Mix"]


def test_a_stream_that_starts_during_the_desks_draw_waits_for_the_next_frame(tmp_path, face,
                                                                           monkeypatch):
    """The page shows the stream as its fill read it: a station whose card
    arrives while the desk window draws (the browser's pump runs the service
    inside the frame) shows on the next frame."""
    ws = build_desktop_ws(tmp_path)
    app = _app(ws)
    ws.home.open_desk()
    ws.spine.open_app(app)
    _settle(ws)
    assert M.STREAM.card is None and not app.state().playing
    fill = M.fill
    started = []

    def fill_that_starts_a_station(lay):
        fill(lay)
        if not started:
            started.append(1)
            M.play("r0")

    monkeypatch.setattr(M, "fill", fill_that_starts_a_station)
    app.gen = -1                                    # a fill owed
    _settle(ws, 1)
    assert started and M.STREAM.card is not None
    _settle(ws)
    assert app.state().playing and app.state().main_word == "Pause"


@pytest.mark.parametrize("desk", (False, True))
def test_the_keys_move_the_current_station(tmp_path, face, desk):
    ws = build_desktop_ws(tmp_path) if desk else build_ws(tmp_path)
    app = _app(ws)
    if desk:
        ws.home.open_desk()
    ws.spine.open_app(app)
    drv = make_drv(ws)
    _settle(ws)
    assert app.state().scur == M.ADD, "nothing plays: the list opens on Add a station"
    n = len(M.STREAM.stations)
    for _ in range(n):
        drv.press("down")
        _frames(drv, 12)                    # the glide's frames
    assert app.state().scur == "r%d" % (n - 1)
    for _ in range(n):
        drv.press("up")
        _frames(drv, 12)
    assert app.state().scur == M.ADD


@pytest.mark.parametrize("desk", (False, True))
def test_q_and_e_switch_the_tabs_through_the_toolkit(tmp_path, face, desk):
    """The list's tabs are `ui.tabs`, which takes Q and E itself: E steps
    to My music and stops there, Q back to Radio."""
    ws = build_desktop_ws(tmp_path) if desk else build_ws(tmp_path)
    app = _app(ws)
    if desk:
        ws.home.open_desk()
    ws.spine.open_app(app)
    drv = make_drv(ws)
    _settle(ws)
    for ch, tab in (("e", "files"), ("e", "files"), ("q", "radio")):
        drv.key_down(ord(ch))
        drv.frame(1 / 30)
        drv.key_up(ord(ch))
        for _ in range(3):
            drv.frame(1 / 30)
        assert app.state().tab == tab, ch


def test_music_follows_what_another_client_or_a_vm_stop_left_playing(tmp_path, face):
    """The card shows the service's stream whoever played it: Music's own
    after a VM stop (a fresh Stream, its label read back), another client's
    by its source, and a run that ended with nothing played as failed."""
    ws = build_ws(tmp_path)

    def nav_of():
        return ws.app_context(M.MusicAppLayer.id, ("nav",)).nav

    s = M.STREAM
    face.play(GROOVE[2], label=M.label_of("radio", GROOVE[0]))
    assert M.follow(nav_of) is True
    assert s.what == ("radio", GROOVE[0], GROOVE[2]) and s.card["station"] == GROOVE[0]
    it = ITEMS.at(0)
    assert it is not None and it.app == "Music" and it.state == ON
    face.n.update(src="/sd/files/Music/Song.mp3", label="", who="t.player", title="")
    s.stamp = None
    s.poll()
    assert s.what == ("song", "t.player", "/sd/files/Music/Song.mp3")
    face.n = None
    face.end = {"state": "failed", "err": 5, "pid": 9, "client": 7}
    s.poll()
    assert s.card["state"] == M.FAILED and ITEMS.at(0).state == ERROR
    face.end = None
    s._end()
    assert M.follow(nav_of) is False and ITEMS.at(0) is None


def test_now_playing_takes_its_own_keys_and_the_strip_opens_it(tmp_path, face):
    """A tap on the strip's head opens Now playing (#110's design, K18),
    whose keys are the page's: W and S (and up and down) the volume, A and
    D seek a file, M goes back to the list; a tap on the meter sets the
    volume at the step it lands on."""
    ws = build_ws(tmp_path)
    app = _app(ws)
    ws.spine.open_app(app)
    M.STREAM.play("song", "Tone", str(TONE))
    face.n.update(at=60, len=200, volume=50)
    M.STREAM.poll()
    drv = make_drv(ws)
    _settle(ws)
    x, y, w, h = app.engine._x.rect("strip")
    drv.touch(x + 20, y + h // 2)
    drv.frame(1 / 30)
    drv.touch_up()
    _settle(ws)
    assert app.state().view == "now"
    for ch, want in (("w", 60), ("s", 50)):
        drv.type_char(ord(ch))
        _frames(drv)
        assert face.n["volume"] == want
    drv.press("up")
    _frames(drv)
    assert face.n["volume"] == 60
    drv.type_char(ord("d"))
    _frames(drv)
    drv.type_char(ord("a"))
    _frames(drv)
    assert face.seeks == [60 + M.SEEK_STEP, 60]
    vx, vy, vw, vh = app.page_host().box("vol")
    drv.touch(vx + vw - 8, vy + vh // 2)
    drv.frame(1 / 30)
    drv.touch_up()
    _frames(drv, 2)
    assert face.n["volume"] == 100
    drv.type_char(ord("m"))
    _frames(drv)
    assert app.state().view == "radio"
