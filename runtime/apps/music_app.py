# Map (grep -n a name to jump there):
#   Stream              what plays: the media face, the status item, the poll
#   card_of             the media card's answers from the face's
#   MusicSection        the status item's section (the desk menu, the control center)
#   _scan               the music folder's songs and playlists
#   build               the app's page: the library, Now playing, Add a station
#   MusicAppLayer       the app's Layer over the page
"""Music -- the console's radio and music player (#110), a SYSTEM APP
(docs/app_api_v1.md): a `uitree` page the C engine lays out and paints, over
the media service's face, `moybyte.media` (runtime/system/dev_media.py). Its
design is docs/media/music_2026-11/README.md.

  * Radio: the curated stations and the ones the person added (Add a
    station: an http:// address, or https:// where the console verifies
    it, and a name), kept in the app's prefs;
  * My music: the MP3s and the .m3u/.pls playlists in the music folder of
    the user files (`files/Music/` on the SD card);
  * what plays in a strip under either list, which opens Now playing: the
    title and its line, the transport, a file's place (a slider a tap or
    the arrows seek along, SEEK_STEP seconds a step) or LIVE for a station,
    and the volume; Q and E step to the previous or next.

What plays is the media service's stream, the system's (the app is one of
its clients): leaving the app keeps it playing, and Back on the desk
minimises the window. While the service runs the app's status item is in
the bar (`moybyte.status`); its section, rows of the title and the
transport, is where it is paused and stopped from anywhere (the desk's
menu, a handheld's control center). What another client plays, and what a
VM stop left playing, the card shows as well (`Stream.follow`, from the
label each play() names). A console with no media service (the Guition S3)
shows the no-audio page.
"""

import uitree as ui
import uitree_app
from moy_store_base import builtin_name, files_root
import moybyte as _moybyte
import devices as _devices
import status_items as _status

try:
    import moy_log as _L
except ImportError:  # pragma: no cover - an image without the kernel
    _L = None

# The curated stations: name, style, address (each answers 200 with
# audio/mpeg MP3 over plain http to the media client's request, and over
# https, every redirect https too, to a browser page's).
STATIONS = (
    ("Groove Salad", "Ambient beats", "http://ice1.somafm.com/groovesalad-128-mp3"),
    ("Drone Zone", "Ambient", "http://ice1.somafm.com/dronezone-128-mp3"),
    ("Deep Space One", "Space ambient", "http://ice1.somafm.com/deepspaceone-128-mp3"),
    ("Space Station Soma", "Electronica", "http://ice1.somafm.com/spacestation-128-mp3"),
    ("Mission Control", "Space", "http://ice1.somafm.com/missioncontrol-128-mp3"),
    ("Secret Agent", "Lounge", "http://ice1.somafm.com/secretagent-128-mp3"),
    ("Indie Pop Rocks!", "Indie pop", "http://ice1.somafm.com/indiepop-128-mp3"),
    ("Underground 80s", "Synthpop", "http://ice1.somafm.com/u80s-128-mp3"),
    ("Left Coast 70s", "70s rock", "http://ice1.somafm.com/seventies-128-mp3"),
    ("Sonic Universe", "Jazz", "http://ice1.somafm.com/sonicuniverse-128-mp3"),
    ("Folk Forward", "Folk", "http://ice1.somafm.com/folkfwd-128-mp3"),
    ("Thistle Radio", "Celtic", "http://ice1.somafm.com/thistle-128-mp3"),
    ("Radio Paradise", "Eclectic", "http://stream.radioparadise.com/mp3-128"),
    ("Radio Swiss Jazz", "Jazz", "http://stream.srg-ssr.ch/srgssr/rsj/mp3/128"),
)

MUSIC_DIR = "Music"
SONG_EXT = (".mp3",)
LIST_EXT = (".m3u", ".pls")
STATIONS_KEY = "stations"
STATIONS_MAX = 24
URL_MAX = 200
NAME_MAX = 32
POLL_MS = 250
SEEK_STEP = 10              # seconds a key seeks a file
ERR_ADDRESS = "This address won't play. Use one that starts with http://"
HELP_ADDRESS = "An MP3 stream or playlist"
FOLDER_MAX = 200

PLAYING, PAUSED_, OPENING, FAILED = "playing", "paused", "opening", "failed"
EACCES = 13                 # a station that does not let a browser's page read it


# -- what plays ----------------------------------------------------------------

def _media():
    return _devices.api("media")


def _is_url(src):
    return src[:7].lower() == "http://" or src[:8].lower() == "https://"


def _stem(path):
    name = path[path.rfind("/") + 1:]
    dot = name.rfind(".")
    return name[:dot] if dot > 0 else name


def _clock(sec):
    sec = max(0, int(sec))
    return "%d:%02d" % (sec // 60, sec % 60)


def _as_shell(verb):
    """`verb` made as the shell (pid 1), whatever process is current."""
    def shell_verb(*a, **k):
        if _L is None:
            return verb(*a, **k)
        was = _L.current()
        _L.current(_devices.SHELL)
        try:
            return verb(*a, **k)
        finally:
            _L.current(was)
    return shell_verb


class Stream:
    """What plays and what the person chose to play: the media face's
    answers read on a wake while a stream is open, the status item that
    shows it in the bar, and the verbs every surface acts with. One for the
    console (`STREAM`): the app's pages and its section read the same.

    Music is the shell's, so its verbs are the shell's client and its wake
    and status item the shell's (`_as_shell`), never the process a running
    game, or the Editor's run, makes current."""

    def __init__(self):
        self.face = None            # the media face, else moybyte.media's (a test's stand-in)
        self.what = None            # (kind, name, src): "radio", "song" or "list"
        self.card = None            # the media card's answers (`card_of`), None: nothing
        self.item = None
        self.section = None
        self.wake = None
        self.sig = None
        self.stamp = None           # the face's stamp the last full read saw
        self.tick = 0
        self.gen = 0                # moves with anything the card shows
        self.on_change = None       # fn() the app sets: a frame owed
        self.stations = STATIONS    # the radio's list, the app's own after
        self.songs = ()             # the music folder's songs, for a song's step
        self.run = 0                # the service's run the card shows

    def media(self):
        """The media face: a stand-in's where one is set (False: none, a
        console with no audio), else `moybyte.media`, None where absent."""
        f = self.face
        if f is False:
            return None
        return f if f is not None else _media()

    # -- verbs -----------------------------------------------------------------

    @_as_shell
    def play(self, kind, name, src):
        """Play `src` as `kind` named `name`: the stream starts connecting
        (a station) or playing; False with the card failed when the face
        refuses it."""
        self.stamp = None
        m = self.media()
        if m is None:
            return False
        self.what = (kind, name, src)
        try:
            m.play(src, label=label_of(kind, name))
        except OSError:
            self.card = card_of(None, self.what, FAILED)
            self._changed()
            self._start()
            return False
        self._start()
        self.poll()
        return True

    @_as_shell
    def toggle(self):
        """Pause or play; a stream that failed is tried again."""
        self.stamp = None
        m = self.media()
        c = self.card
        if m is None or c is None:
            return
        if c["state"] == FAILED:
            if self.what is not None:
                self.play(*self.what)
            return
        if c["paused"]:
            m.resume()
        else:
            m.pause()
        self.poll()

    @_as_shell
    def seek(self, sec):
        """The file played from `sec` seconds, held inside it; False for a
        stream with no length (a station) or a seek the face refuses."""
        self.stamp = None
        m = self.media()
        c = self.card
        if m is None or c is None or not c["len"]:
            return False
        try:
            ok = m.seek(max(0, min(c["len"] - 1, int(sec))))
        except OSError:
            ok = False
        self.poll()
        return bool(ok)

    @_as_shell
    def stop(self):
        m = self.media()
        if m is not None:
            try:
                m.stop()
            except OSError:
                pass
        self._end()

    @_as_shell
    def step(self, d):
        """The next (`d` 1) or previous station, song or list entry."""
        self.stamp = None
        w = self.what
        m = self.media()
        if w is None or m is None:
            return
        kind = w[0]
        if kind == "list":
            try:
                (m.next if d > 0 else m.prev)()
            except OSError:
                return
            self.poll()
            return
        pool = self.stations if kind == "radio" else self.songs
        names = [p[0] for p in pool]
        if not names:
            return
        i = names.index(w[1]) if w[1] in names else -1
        i = (i + d) % len(names)
        p = pool[i]
        self.play(kind, p[0], p[2] if kind == "radio" else p[1])

    @_as_shell
    def volume(self, v=None):
        self.stamp = None
        m = self.media()
        if m is None:
            return 0
        if v is not None:
            v = max(0, min(100, int(v)))
            try:
                m.volume(v)
            except OSError:
                pass
            self.poll()
        c = self.card
        return c["volume"] if c is not None else 0

    @_as_shell
    def follow(self):
        """The service's stream shown, whoever played it: Music's own after
        a VM stop, or another client's (its label says what, else its
        source). False where nothing plays."""
        m = self.media()
        n = m.now() if m is not None else None
        if n is None:
            return False
        self.what = what_of(n)
        self.stamp = None
        self._start()
        self.poll()
        return True

    # -- the wake ----------------------------------------------------------------

    def _start(self):
        if self.wake is None:
            self.wake = _moybyte.every(POLL_MS, self.poll)

    def _end(self):
        w = self.wake
        self.wake = None
        if w is not None:
            _moybyte.cancel(w)
        it = self.item
        self.item = None
        if it is not None:
            it.remove()
        self.card = None
        self.what = None
        self.sig = None
        self.stamp = None
        self._changed()

    def poll(self):
        """The face read: the card, the status item's state and a frame
        where what shows moved. A stream gone (stopped elsewhere, its list
        ended) takes the item out. While the face's stamp holds still
        (a station playing on under a game) it reads nothing else and
        allocates nothing."""
        m = self.media()
        if m is not None and self.sig is not None and self.sig[0] != OPENING:
            st = m.stamp() if hasattr(m, "stamp") else None
            if st is not None and st == self.stamp:
                return
            self.stamp = st
        n = None
        if m is not None:
            try:
                n = m.now()
            except OSError:
                n = None
        if n is None and self.what is not None and self._failed(m):
            return
        if n is None or self.what is None:
            self._end()
            return
        lab = n.get("label")
        if lab is not None and lab != label_of(*self.what[:2]):
            self.what = what_of(n)           # another client's play: what it named
        self.run = n.get("pid", 0)
        if n["state"] == "ended":
            self.stop()
            return
        c = card_of(n, self.what)
        self.card = c
        if c["state"] == OPENING:
            self.tick += 1
        sig = (c["state"], c["paused"], c["title"], c["station"], c["entry"],
               c["volume"], c["at"], c["len"], self.tick if c["state"] == OPENING else 0)
        if sig != self.sig:
            item_moved = self.sig is None or sig[:6] != self.sig[:6] or c["state"] == OPENING
            self.sig = sig
            self._item(c["state"] if not c["paused"] else PAUSED_, item_moved)
            self._changed()

    def _failed(self, m):
        """The card failed: the run it showed ended with nothing played (the
        service's own end), or a play the face refused. True while it shows
        that."""
        c = self.card
        if c is not None and c["state"] == FAILED:
            self._item(FAILED)
            return True
        e = m.last() if m is not None and self.run and hasattr(m, "last") else None
        if e is None or e["pid"] != self.run or e["state"] != "failed":
            return False
        self.run = 0
        self.card = card_of(None, self.what, FAILED)
        self._item(FAILED)
        self._changed()
        return True

    def _item(self, state, moved=True):
        it = self.item
        if it is None:
            sec = self.section
            if sec is None:
                return
            it = _moybyte.status("music", sec, 0)
            if it is None:
                return
            it.app = "Music"
            self.item = it
        it.show(_status.ERROR if state == FAILED else
                _status.PAUSED if state == PAUSED_ else _status.ON)
        if moved:
            it.changed()

    def _changed(self):
        self.gen = (self.gen + 1) & 0x3fffffff
        fn = self.on_change
        if fn is not None:
            fn()


STREAM = Stream()


def label_of(kind, name):
    """What Music names a play() it makes (the face's `label`)."""
    return "%s\t%s" % (kind, name)


def what_of(n):
    """(kind, name, src) of what the face's now() plays: Music's own label's,
    else the source's (a list, a station or a song) and its client's name."""
    kind, _, name = (n.get("label") or "").partition("\t")
    src = n.get("src") or ""
    if kind in ("radio", "song", "list") and name:
        return kind, name, src
    if (n.get("entries") or 1) > 1:
        kind = "list"
    else:
        kind = "radio" if _is_url(src) else "song"
    return kind, n.get("title") or n.get("who") or _stem(src), src


def follow(nav_of=None):
    """A run of the media service the face found (dev_media.listen: any
    client'st play that started one, or the run a VM stop left playing)
    shown in the bar, its section opening the app. `nav_of()` makes the nav
    role the section opens the app through, asked only when no app built
    the section."""
    st = STREAM
    if st.section is None and nav_of is not None:
        nav = None
        try:
            nav = nav_of()
        except Exception:  # noqa: BLE001 -- a section with no head still shows the card
            nav = None
        st.section = MusicSection(st, nav)
    return st.follow()


def card_of(n, what, state=None):
    """The media card's answers: state ("playing", "opening", "failed"),
    paused, the title, the station (or the list, or "My music"), the place
    in a list, the volume, the kind, and a file's place and length in
    seconds (0 where it has none)."""
    kind, name, _src = what
    st = state or (n["state"] if n else FAILED)
    if st not in (PLAYING, OPENING, FAILED):
        st = PLAYING if st == "idle" else st
    title = (n or {}).get("title") or ""
    if kind == "song":
        title = name
        station = "My music"
    elif kind == "list":
        title = title or name
        station = name
    else:
        station = name
    return {"state": st, "paused": bool(n and n.get("paused")), "title": title,
            "station": station, "entry": (n or {}).get("entry", 0) or 0,
            "entries": (n or {}).get("entries", 1) or 1,
            "volume": (n or {}).get("volume", 0) or 0, "kind": kind,
            "at": (n or {}).get("at", 0) or 0, "len": (n or {}).get("len", 0) or 0,
            "err": (n or {}).get("err", 0) or 0}


def _artist_title(text):
    """An ICY StreamTitle's "Artist - Title" as (title, artist)."""
    k = text.find(" - ")
    if k > 0:
        return text[k + 3:], text[:k]
    return text, ""


def lines(c):
    """The card's two lines, one order everywhere: the title, then the
    artist and the station (or the list and its place)."""
    if c["state"] == OPENING:
        return c["station"], "Connecting..."
    if c["state"] == FAILED:
        return c["station"], "Blocks browsers" if c.get("err") == EACCES else "Not answering"
    title, artist = _artist_title(c["title"])
    if c["kind"] == "list":
        return title, "%s · %d of %d" % (c["station"], c["entry"] + 1, c["entries"])
    if c["kind"] == "radio" and not title:
        return c["station"], "Live"
    if c["kind"] == "song":
        return title, c["station"]
    return title, (artist + " · " if artist else "") + c["station"]


# -- the status item's section ---------------------------------------------------

class MusicSection:
    """The status item's section (runtime/system/status_items.py): the
    title, which opens the app, the second line, the transport and the
    volume as rows."""

    def __init__(self, stream, nav=None):
        self.stream = stream
        self.nav = nav

    def panel(self):
        c = self.stream.card
        if c is None:
            return ""
        title, meta = lines(c)
        main = "Try again" if c["state"] == FAILED else "Play" if c["paused"] else "Pause"
        return ("button open %s\ntext %s\nbutton main %s\nbutton prev Previous\n"
                "button next Next\nbutton stop Stop\nslider volume Volume 0 10 %d"
                % (_one_line(title), _one_line(meta), main, (c["volume"] + 5) // 10))

    def press(self, rid, v):
        st = self.stream
        if rid == "open":
            if self.nav is not None:
                self.nav.open_app("jukebox")
        elif rid == "main":
            st.toggle()
        elif rid == "prev":
            st.step(-1)
        elif rid == "next":
            st.step(1)
        elif rid == "stop":
            st.stop()
        elif rid == "volume":
            st.volume(v * 10)


def _one_line(t):
    """`t` as a row's label: one line, never empty."""
    return " ".join(str(t).split()) or "-"


# -- the music folder -------------------------------------------------------------

def _list_count(path):
    """How many songs playlist `path` names."""
    try:
        with open(path, "rb") as f:
            text = f.read(8192)
    except OSError:
        return 0
    n = 0
    pls = path.lower().endswith(".pls")
    for ln in text.split(b"\n"):
        ln = ln.strip()
        if not ln:
            continue
        if pls:
            if ln[:4].lower() == b"file":
                n += 1
        elif ln[:1] != b"#":
            n += 1
    return n


def _scan(folder):
    """The music folder's songs and playlists, sorted by name: (songs,
    lists), each a tuple of (name, path, detail: a song's length, which the
    media face's `probe` reads in C, a list's count); None where the folder
    is not there. A song this console plays but does not keep (a
    board-served page's, which the board keeps: the media face's `held`) is
    listed too, with no length."""
    import os
    m = _media()
    held = getattr(m, "held", None)
    held = held(folder) if held is not None else ()
    probe = getattr(m, "probe", None)
    try:
        names = os.listdir(folder)
    except OSError:
        if not held:
            return None
        names = []
    names = set(names)
    names.update(nm for nm, _size in held)
    songs, lists = [], []
    for nm in sorted(names)[:FOLDER_MAX]:
        low = nm.lower()
        path = folder + "/" + nm
        if low.endswith(SONG_EXT):
            got = probe(path) if probe is not None else None
            sec = got[0] if got is not None else 0
            songs.append((_stem(nm), path, _clock(sec) if sec else ""))
        elif low.endswith(LIST_EXT):
            n = _list_count(path)
            lists.append((_stem(nm), path, "%d song%s" % (n, "" if n == 1 else "s")))
    return tuple(songs), tuple(lists)


# -- the app ------------------------------------------------------------------------
def _state(c, name, kind):
    """None, or how row `name` of `kind` stands against what plays."""
    if c is None or c["station"] != name and not (kind == "song" and c["title"] == name):
        return None
    if c["kind"] != kind:
        return None
    if c["state"] == OPENING:
        return OPENING
    if c["state"] == FAILED:
        return FAILED
    return PAUSED_ if c["paused"] else PLAYING


def _https():
    m = _media()
    return m is not None and bool(m.tls())


def _check(url, final):
    """The Address field's error: an address that names another scheme,
    and on Add one that is not http:// (or https:// where the media face
    verifies it) at all; None where it plays."""
    low = url.strip().lower()
    if not low:
        return ERR_ADDRESS if final else None
    if low.startswith("http://") and len(low) > 7:
        return None
    if low.startswith("https://") and len(low) > 8 and _https():
        return None
    if "://" in low or final or low.startswith("https"):
        return ERR_ADDRESS
    return None


def _host(url):
    rest = url[url.find("://") + 3:] if "://" in url else url
    k = rest.find("/")
    return (rest[:k] if k > 0 else rest)[:NAME_MAX]



# -- the page ---------------------------------------------------------------------

# What plays, as its glyph in the foot's button says it.
MARK = {PLAYING: "equalizer", PAUSED_: "pause", OPENING: "pulse", FAILED: "warn"}
# ...and the words its right column says in place of the row's own.
STATE_WORD = {PLAYING: "Playing", PAUSED_: "Paused", OPENING: "Connecting...", FAILED: "Not answering"}
MAIN = {FAILED: ("retry", "Try again"), PAUSED_: ("play", "Play"), PLAYING: ("pause", "Pause")}
ADD = "add"                 # the Radio list's first row, Add a station: no station's id

_ROW = dict(key="id", id="", name="", right="", on=False)
s = ui.state(
    audio=True,             # a media service to play through
    online=True,            # ...and a network for the radio
    view=ui.enum("radio", "files", "now", "add", "noaudio", init="radio"),   # the tabs' page, or another
    tab=ui.enum("radio", "files", init="radio"),
    folder=ui.enum("unread", "nosd", "empty", "some", init="unread"),
    stations=ui.model(**_ROW),
    scur=ui.row_of("stations"),
    songs=ui.model(**_ROW),
    fcur=ui.row_of("songs"),
    playing=False,          # what plays: the card's
    title="",
    meta="",
    failed=False,
    mark="music",
    main_icon="pause",
    main_word="Pause",
    vol=0,
    seekable=False,         # ...a file's place, SEEK_STEP seconds a step
    pos=0,
    steps=1,
    clock="",
    live=False,             # ...a station on air
    url="",                 # Add a station's fields
    name="",
    err="",
)
ui.derive("listing", cond="view=radio || view=files")
ui.derive("paged", cond="view=now || view=add")
ui.labels("TABS", {"radio": "Radio", "files": "My music"})
ui.app("Music", icon="music", back="back")


def _lay():
    return uitree_app.env()


def _row(id, name, right, st):
    return {"id": id, "name": name, "right": STATE_WORD.get(st, right), "on": st is not None}


def fill(lay):
    """The page's states from what plays, the stations and the folder;
    the lists written only where they moved."""
    st = STREAM
    c = st.card
    lay.gen = st.gen
    s.audio = st.media() is not None
    s.playing = c is not None
    if c is not None:
        title, meta = lines(c)
        state = FAILED if c["state"] == FAILED else PAUSED_ if c["paused"] else PLAYING
        s.title, s.meta = title, meta
        s.failed = state == FAILED
        s.mark = MARK[OPENING] if c["state"] == OPENING else MARK[state]
        s.main_icon, s.main_word = MAIN[state]
        s.vol = (c["volume"] + 5) // 10
        s.seekable = bool(c["len"]) and c["state"] == PLAYING
        s.steps = max(1, c["len"] // SEEK_STEP)
        s.pos = min(c["at"], c["len"]) // SEEK_STEP
        s.clock = "%s / %s" % (_clock(c["at"]), _clock(c["len"]))
        s.live = c["kind"] == "radio" and c["state"] == PLAYING and not c["paused"]
    elif s.view == "now":
        s.view = s.tab
    if not s.audio:
        s.view = "noaudio"
    rows = [_row(ADD, "Add a station", "", None)]
    for k, (name, style, _url) in enumerate(st.stations):
        rows.append(_row("r%d" % k, name, style, _state(c, name, "radio")))
    if rows != lay.rows[0]:
        lay.rows[0] = rows
        s.stations = rows
    f = lay.files
    s.folder = "unread" if f is None else "nosd" if f is False else "some" if f[0] or f[1] else "empty"
    rows = []
    if f:
        for k, (name, _path, detail) in enumerate(f[1]):
            rows.append(_row("l%d" % k, name, detail, _state(c, name, "list")))
        for k, (name, _path, detail) in enumerate(f[0]):
            rows.append(_row("s%d" % k, name, detail, _state(c, name, "song")))
    if rows != lay.rows[1]:
        lay.rows[1] = rows
        s.songs = rows


def _playing_row(rows):
    for r in rows:
        if r["on"]:
            return r["id"]
    return rows[1]["id"] if len(rows) > 1 and rows[0]["id"] == ADD else rows[0]["id"] if rows else ""


def _focus_list():
    ui.focus("songs" if s.tab == "files" else "stations")


def opened():
    lay = _lay()
    lay.folder_owed = True
    lay.wifi = lay.has_wifi()
    s.online = lay.wifi
    if s.view == "add":
        s.view = s.tab
    fill(lay)
    s.scur = _playing_row(lay.rows[0])
    s.fcur = _playing_row(lay.rows[1]) if lay.rows[1] else ""
    _focus_list()


def play(id):
    """Row `id` of either list played: Add a station opens its page, the
    row that plays is paused or played again (tried again where it failed)."""
    lay = _lay()
    if id == ADD:
        add_open()
        return
    rows = lay.rows[0] if id[0] == "r" else lay.rows[1]
    row = next((r for r in rows if r["id"] == id), None)
    if row is None:
        return
    if row["on"]:
        STREAM.toggle()
        return
    k = int(id[1:])
    if id[0] == "r":
        st = STREAM.stations[k]
        STREAM.play("radio", st[0], st[2])
    elif id[0] == "l":
        STREAM.play("list", lay.files[1][k][0], lay.files[1][k][1])
    else:
        STREAM.play("song", lay.files[0][k][0], lay.files[0][k][1])


def pick(row):
    play(row.id)


def tab_moved():
    s.view = s.tab
    if s.tab == "files" and _lay().files is None:
        _lay().folder_owed = True


def now():
    s.view = "now"
    ui.focus("pos" if s.seekable else "main")


def back():
    s.view = s.tab
    _focus_list()


def add_open():
    s.url, s.name, s.err = "", "", ""
    s.view = "add"
    ui.focus("url")


def url_moved():
    s.err = _check(s.url, False) or ""


def to_name():
    ui.focus("name")


def submit():
    url = s.url.strip()
    err = _check(url, True)
    if err:
        s.err = err
        ui.focus("url")
        return
    name = s.name.strip()[:NAME_MAX] or _host(url)
    lay = _lay()
    lay.add_station(name, url)
    fill(lay)
    s.scur = "r%d" % (len(STREAM.stations) - 1)
    back()
    STREAM.play("radio", name, url)


def main():
    STREAM.toggle()


def prev():
    STREAM.step(-1)


def next_():
    STREAM.step(1)


def stop():
    STREAM.stop()


def volume():
    STREAM.volume(s.vol * 10)


def seek():
    STREAM.seek(s.pos * SEEK_STEP)


def wifi():
    _lay().ctx.install.wifi()


def home():
    _lay().leave_asked = True


ui.hook("opened", opened)
ui.hook("tab_moved", tab_moved)
ui.hook("url_moved", url_moved)
ui.hook("to_name", to_name)
ui.hook("volume", volume)
ui.hook("seek", seek)
ui.action("pick", "Play", pick, takes="row")
ui.action("now", "Player", now, keys=("role:more",), when="playing && listing", off="hide")
ui.action("back", "Back", back, when="paged", off="hide")
ui.action("cancel", "Cancel", back)
ui.action("add", "Add", submit, when="!err", off="grey")
ui.action("main", "Play", main, when="playing", off="hide")
ui.action("prev", "Previous", prev, keys=("q",), when="playing && view=now", off="hide")
ui.action("next", "Next", next_, keys=("e",), when="playing && view=now", off="hide")
ui.action("stop", "Stop", stop, when="playing", off="hide")
ui.action("wifi", "Wi-Fi settings", wifi)
ui.action("home", "Back to home", home)


def _strip(wifi=False):
    """What plays, at the foot of either list's page; Wi-Fi's page where
    the radio has no network."""
    with ui.foot(look="share"):
        if wifi:
            ui.button("wifi", "primary", icon="wifi", shown="!online")
        ui.button("main", icon="{main_icon}", label="")
        ui.button("now", icon="{mark}", label="{title}")


def _radio():
    with ui.table("stations", cols=("Station", "Style"), cur="scur", on="pick", hint="Play", shown="online"):
        ui.col("{.name}")
        ui.col("{.right}")
    ui.empty("Radio needs Wi-Fi", icon="wifi_off", shown="!online",
             lines=["Turn on Wi-Fi to listen to stations.", "Your own music plays without it."])
    _strip(wifi=True)


def _files():
    with ui.table("songs", cols=("Name", "Length"), cur="fcur", on="pick", hint="Play", shown="folder=some"):
        ui.col("{.name}")
        ui.col("{.right}")
    ui.empty("No SD card", icon="folder", shown="folder=nosd",
             lines=["Put in an SD card with your songs on it.", "Radio plays without one."])
    ui.empty("No music yet", icon="music", shown="folder=empty",
             lines=["Put MP3 songs in the Music folder", "on the SD card."])
    _strip()


def _now():
    ui.label("{title}", face="title")
    ui.label("{meta}", tone="dim", shown="!failed")
    ui.label("{meta}", tone="danger", shown="failed")
    ui.label("LIVE", icon="equalizer", tone="value", shown="live")
    ui.slider("{clock}", "pos", 0, "{steps}", look="bar", on="seek", shown="seekable")
    ui.slider("Volume", "vol", 0, 10, look="steps", icon="volume", on="volume")
    ui.link("main", icon="{main_icon}", label="{main_word}")
    ui.link("prev", icon="prev")
    ui.link("next", icon="next")
    ui.link("stop", icon="stop")


def _add():
    ui.field("Address", "url", URL_MAX, hint="http://", on="to_name", changed="url_moved")
    ui.label("{err}", tone="danger", wrap="word", lines=2, shown="err")
    ui.label(HELP_ADDRESS, tone="dim", shown="!err")
    ui.field("Name", "name", NAME_MAX, hint="Optional", on="add")
    with ui.foot(look="share"):
        ui.button("cancel")
        ui.button("add", "primary")


def _no_audio():
    ui.empty("No sound on this console", icon="mute",
             lines=["This console has no speaker,", "so it can't play music or radio."])
    with ui.foot(look="share"):
        ui.button("home", "primary", icon="home")


def build():
    with ui.page(""):
        ui.tabs("tab", labels="TABS", on="tab_moved", shown="listing")
        ui.switch("view", {"radio": _radio, "files": _files, "now": _now, "add": _add,
                           "noaudio": _no_audio})


def is_app(cart):
    """The shipped Music identity cart: its title, its marker permission,
    its folder."""
    if (not cart or cart.get("title") != "Music"
            or "music" not in (cart.get("permissions") or ())):
        return False
    path = cart.get("path")
    if not path:
        return int(cart.get("version", 0)) >= 1
    return builtin_name(path) == "moybyte.music.moy"


TITLES = {"now": "Now playing", "add": "Add a station"}


class MusicAppLayer(uitree_app.app_layer("jukebox", "Music", build, is_app,
                                         needs=("prefs", "install", "nav"))):
    """The Music Layer: the page's engine handed this layer as what its
    handlers reach (`uitree_app.env()`), the stream's moves owing the page a
    fill, the music folder read off the draw (`idle_step`)."""

    PREFS_NS = "music"          # its prefs, the stations it added: portable
    MIN_W = 300
    MIN_H = 220
    # Back on its first page leaves the app; on the desk it minimises the
    # window. Either way the stream plays on.
    BACK_MINIMISES = True

    def __init__(self, ctx, names=None):
        super().__init__(ctx, names)
        self.engine.env = self
        self._prefs, self._install = ctx.prefs, ctx.install
        self.files = None           # (songs, lists), None: not read; False: no SD
        self.folder_owed = False    # the folder owes a read (an open, the tab)
        self.shown = False          # on screen: from a draw until close()
        self.rows = [None, None]    # each list's rows as last written
        self.gen = -1               # the stream's gen the page last showed
        self.wifi = True
        self.leave_asked = False
        st = STREAM
        st.on_change = self._moved
        if st.section is None:
            st.section = MusicSection(st)
        st.section.nav = ctx.nav    # the console's: the next one's takes its place
        self.stream = st
        self.load_stations()
        if st.what is None:
            st.follow()

    def do(self, fn, *args):
        """`fn(*args)` run as the page's handler, one commit."""
        self.engine.run(fn, *args, action="fill")
        ui.commit(self.engine)
        self._damage.all()

    def state(self):
        """The page's state, this engine's values."""
        self.engine._bind()
        return s

    def _moved(self):
        if self.shown:
            self._damage.all()

    def close(self):
        self.shown = False
        super().close()

    def draw(self, dt):
        self.shown = True
        if self.stream.gen != self.gen:
            self.do(fill, self)
        super().draw(dt)

    def page_title(self):
        return TITLES.get(self.state().view)

    def has_page(self):
        return self.state().view in TITLES or super().has_page()

    def cancel(self):
        """The T-Deck's Mic in a field: Add a station cancelled."""
        if self.state().view != "add":
            return False
        self.do(back)
        return True

    def has_wifi(self):
        """Whether the radio can reach a network: a transport, and on a
        board a saved network to dial."""
        net = self._install.net()
        if net is None:
            return True             # no transport to ask: the stream says
        w = getattr(net, "wifi", None)
        if w is None:
            return True
        try:
            if w.status()[0]:
                return True
            return bool(w.known())
        except Exception:  # noqa: BLE001 -- a radio that cannot say has none
            return False

    def load_stations(self):
        mine = self._prefs.get(STATIONS_KEY, None)
        rows = list(STATIONS)
        if isinstance(mine, list):
            for r in mine[:STATIONS_MAX]:
                if isinstance(r, list) and len(r) == 2 and _is_url(str(r[1])):
                    rows.append((str(r[0])[:NAME_MAX], "Added", str(r[1])[:URL_MAX]))
        self.stream.stations = tuple(rows)

    def add_station(self, name, url):
        mine = self._prefs.get(STATIONS_KEY, None)
        mine = list(mine) if isinstance(mine, list) else []
        mine.append([name, url])
        self._prefs.set(STATIONS_KEY, mine[-STATIONS_MAX:])
        self.load_stations()

    @property
    def idle_owed(self):
        return self.folder_owed or self.engine.idle_owed

    def idle_step(self):
        if not self.folder_owed:
            self.engine.idle_step()
            return
        self.folder_owed = False
        root = self._install.root()
        if root is None:
            self.files = False
        else:
            folder = files_root(root) + "/" + MUSIC_DIR
            got = self._install.op(lambda: _scan(folder))
            self.files = got if got is not None else ((), ())
            self.stream.songs = self.files[0]
        if self.shown:
            self.do(fill, self)
        else:
            self.gen = -1               # the next draw fills
