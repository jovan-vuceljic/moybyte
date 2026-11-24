# Map (grep -n a name to jump there):
#   Stream              what plays: the media face, the status item, the poll
#   card_of             the media card's answers from the face's
#   MusicSection        the status item's section, a page (music_card: the desk menu, the control center)
#   _scan               the music folder's songs and playlists
#   draw_now            what plays as the canvases draw it: art, equalizer, pulse, bar
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
  * Now playing: the media card at its full density (the art, the title,
    the artist and the station, LIVE or a file's bar a tap seeks along, the
    transport, the volume meter between - and +), its keys the page's own
    (Enter the focused button, Q E step, W S the volume, A D seek a file
    SEEK_STEP seconds, M the list); on a handheld the strip over either
    list's foot opens it;
  * on the desk one window: the Library's two places beside the table, the
    media card in one row across its foot.

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
import ui_draw as _D
import layout_base as _lb
from moy_store_base import files_root
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
VOLUME_STEP = 10
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
    """The status item's section (runtime/system/status_items.py): a page,
    the compact card (`music_card`), on the desk with the volume under it.
    Its head opens the app."""

    def __init__(self, stream, nav=None):
        self.stream = stream
        self.nav = nav

    @property
    def page(self):
        return music_card.page

    def height(self, desk):
        return music_card.H_DESK if desk else music_card.H

    def open(self):
        if self.nav is not None:
            self.nav.open_app("jukebox")


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



# -- the drawn pieces: what plays, as the canvases draw it -------------------------

# A station's (or list's) art: a colour field, two MOY64 colours top to
# bottom. One the table does not name takes a pair by its name.
ART = {"Groove Salad": (58, 40), "Drone Zone": (60, 22), "Deep Space One": (61, 43),
       "Space Station Soma": (59, 42), "Mission Control": (54, 12),
       "Secret Agent": (56, 36)}
ART_PAIRS = ((58, 40), (60, 22), (61, 43), (59, 42), (54, 12), (56, 36), (57, 37),
             (52, 20), (46, 28))
_EQ = (6, 10, 4, 8)
_DIAMOND = (0, 1, 2, 3, 2, 1, 0)


def _art_of(name):
    pair = ART.get(name)
    if pair is None:
        h = 0
        for ch in name:
            h = (h * 31 + ord(ch)) & 0xffff
        pair = ART_PAIRS[h % len(ART_PAIRS)]
    return pair


def paused_ink(th):
    """The paused state's ink: the theme's `paused` content role, the dim
    ink where the theme names none."""
    v = th.get("paused")
    return v if v is not None else th["chrome_ink_dim"]


def eq(cv, x, y, w, h, c, fs, lively=True, size=12):
    """The equalizer, the state of what plays: four bars on one baseline,
    lively while it plays, 2 px and still while paused."""
    sz = size * fs
    bw = max(2 * fs, sz // 4)
    gap = max(fs, sz // 8)
    x0 = x + (w - 4 * bw - 3 * gap) // 2
    base = y + h // 2 + sz // 2
    for k in range(4):
        bh = (sz * _EQ[k] // 10) if lively else 2 * fs
        cv.rect(x0 + k * (bw + gap), base - bh, bw, bh, c)


def pulse(cv, x, y, w, h, on, off, fs, lit=1):
    """Connecting: three 2 px dots centred on the line, one lit, stepping."""
    d = 2 * fs
    x0 = x + (w - 5 * d) // 2
    cy = y + (h - d) // 2
    for k in range(3):
        cv.rect(x0 + 2 * k * d, cy, d, d, on if k == lit else off)


def chevron(cv, x, y, h, c, fs, desk=False):
    """The toolkit's one chevron (a value row's), right pointing, its
    column at x, centred on a line at y `h` tall; its width."""
    w = _D.metrics("value_row")[3 if desk else 2] * fs
    half = w // fs - 1
    rows = 2 * half + 1
    y0 = y + (h - rows * fs) // 2
    for i in range(rows):
        o = i if i <= half else rows - 1 - i
        cv.rect(x + o * fs, y0 + i * fs, fs, fs, c)
    return w


def art(cv, x, y, w, h, name, fs, r=8):
    """What plays, as art: its colour field. It carries no state."""
    a, b = _art_of(name)
    cv.rrect(x, y, w, h, r * fs, (0, 0, ((0, a), (1000, b))))
    cv.circ(x + w * 3 // 4, y + h // 3, max(3 * fs, w // 7), b)


_R = [0, 0, 0, 0]               # a text's box: one list, so a draw allocates nothing
_DRAWN = {"head": [0, 0, 0, 0, 1]}  # a canvas's last rect and scale


def _drawn(key, x, y, w, h, fs):
    d = _DRAWN[key]
    d[0], d[1], d[2], d[3], d[4] = x, y, w, h, fs


def _text(cv, x, y, w, h, t, ink, role="ui"):
    """`t` in the theme's `role` face in (x, y, w, h), cut to fit, centred
    on its line."""
    r = _R
    r[0], r[1], r[2], r[3] = x, y, max(1, w), h
    if role == "ui":
        _D.label(cv, r, t, ink)
        return
    was = _D.font("ui")[0]              # a label is the UI face's: the role's for this one
    _D.use_font("ui", _D.font(role)[0])
    _D.label(cv, r, t, ink)
    _D.use_font("ui", was)


def _line_h(fs, role="ui"):
    return _D.font(role)[2] * fs + 2 * fs


def _fit(meta, w, c, fs):
    """A line too wide for `w` drops a part at its separator, never cut
    inside one: a station keeps its name, a list its own."""
    if " · " not in meta or _D.text_width(meta, fs, "ui") <= w:
        return meta
    k = meta.find(" · ")
    return meta[k + 3:] if c["kind"] == "radio" else meta[:k]


def state_line(cv, th, c, x, y, w, fs, size=8, meta=None):
    """The state glyph (the equalizer, or the pulse while connecting) and
    the second line, cut at its separator where it does not fit."""
    if meta is None:
        meta = lines(c)[1]
    lh = _line_h(fs)
    tx = x
    gw = size * 2 * fs
    if c["state"] == PLAYING:
        eq(cv, x, y, gw, lh, th["value"] if not c["paused"] else paused_ink(th), fs,
           not c["paused"], size)
        tx = x + gw + 2 * fs
    elif c["state"] == OPENING:
        pulse(cv, x, y, gw, lh, th["value"], paused_ink(th), fs, STREAM.tick % 3)
        tx = x + gw + 2 * fs
    meta = _fit(meta, x + w - tx, c, fs)
    _text(cv, tx, y, x + w - tx, lh, meta, th["danger"] if c["state"] == FAILED else th["chrome_ink_dim"])


def head(cv, th, c, x, y, w, a, fs, role="ui", chev=True, desk=False):
    """The card's head: the art, the title, the state line, the chevron."""
    art(cv, x, y, a, a, c["station"], fs, 6 if a < 48 * fs else 8)
    tx = x + a + 8 * fs
    cw = 6 * fs if chev else 0
    tw = x + w - tx - cw - (6 * fs if chev else 0)
    lh = _line_h(fs)
    ty = y + (a - 2 * lh) // 2
    _text(cv, tx, ty, tw, lh, lines(c)[0], th["chrome_ink"], role)
    state_line(cv, th, c, tx, ty + lh, tw, fs)
    if chev:
        chevron(cv, x + w - cw, y, a, th["chrome_ink_dim"], fs, desk)


def _fs(cv):
    return max(1, int(getattr(cv, "font_scale", 1)))


def draw_strip(cv, x, y, w, h):
    """The strip over a list's foot: a band, the head (a stop that opens
    Now playing); the main button is the page's."""
    c = STREAM.card
    if c is None:
        return
    th, fs = ui.colors(), _fs(cv)
    cv.rect(x, y, w, fs, th["border"])
    a = h - 10 * fs
    hx = x + 8 * fs
    art(cv, hx, y + 5 * fs, a, a, c["station"], fs, 4)
    tx = hx + a + 8 * fs
    cw = 6 * fs
    lh = _D.font("ui")[2] * fs + fs
    ty = y + (h - 2 * lh) // 2
    tw = x + w - tx - cw - 6 * fs
    _text(cv, tx, ty, tw, lh, lines(c)[0], th["chrome_ink"])
    state_line(cv, th, c, tx, ty + lh, tw, fs, 7)
    chevron(cv, x + w - cw - 2 * fs, y, h, th["chrome_ink_dim"], fs)


def draw_wide(cv, x, y, w, h):
    """The desk window's foot: the head at its title face, no chevron."""
    c = STREAM.card
    if c is None:
        return
    head(cv, ui.colors(), c, x, y, w, h, _fs(cv), "title", False)


def draw_now(cv, x, y, w, h):
    """Now playing's head: the art, the title, the artist then the station
    (the list, then the place), LIVE or the file's bar."""
    c = STREAM.card
    if c is None:
        return
    th, fs = ui.colors(), _fs(cv)
    _drawn("head", x, y, w, h, fs)
    art(cv, x, y, h, h, c["station"], fs)
    tx = x + h + 12 * fs
    tw = x + w - tx
    title, meta = lines(c)
    k = meta.find(" · ")
    first, second = (meta[:k], meta[k + 3:]) if k >= 0 else (meta, "")
    _text(cv, tx, y, tw, 20 * fs, title, th["chrome_ink"], "title")
    state_line(cv, th, c, tx, y + 20 * fs, tw, fs, meta=first)
    if second:
        _text(cv, tx, y + 37 * fs, tw, 18 * fs, second, th["chrome_ink_dim"])
    sy = y + 56 * fs
    if c["state"] != PLAYING:
        return
    if c["kind"] == "radio":
        live = not c["paused"]
        ink = th["value"] if live else paused_ink(th)
        cy = sy + 8 * fs
        for i in range(7):
            half = _DIAMOND[i]
            cv.rect(tx + (3 - half) * fs, cy - 3 * fs + i * fs, (2 * half + 1) * fs, fs, ink)
        _text(cv, tx + 11 * fs, sy, 60 * fs, 18 * fs, "LIVE", ink if live else th["chrome_ink_dim"])
        return
    if not c["len"]:
        return
    t = s.clock
    bw = _bar_w(tw, fs)
    cv.rrect(tx, sy + 8 * fs, bw, 4 * fs, 2 * fs, th["border"])
    done = bw * min(c["at"], c["len"]) // c["len"]
    if done > 0:
        cv.rrect(tx, sy + 8 * fs, done, 4 * fs, 2 * fs, th["value"])
    _text(cv, tx + bw + 8 * fs, sy, tw - bw - 8 * fs, 18 * fs, t, th["chrome_ink_dim"])


def _bar_w(tw, fs):
    """A file's bar's width in Now playing's head, its time after it."""
    return tw - _D.text_width(s.clock, fs, "ui") - 10 * fs


def level(c):
    """The volume as the meter's ten steps."""
    return (c["volume"] + 5) // 10 if c is not None else 0


def set_level(v):
    """The meter moved (a tap, a drag, its keys): the volume at its step."""
    STREAM.volume(10 * max(0, min(10, v)))


# -- the page ---------------------------------------------------------------------

# What plays, as its glyph in a row says it.
LEAD = {PLAYING: "equalizer", PAUSED_: "pause", OPENING: "pulse", FAILED: "warn"}
MAIN = {FAILED: ("retry", "Try again"), PAUSED_: ("play", "Play"), PLAYING: ("pause", "Pause")}
VERB = {PLAYING: "Pause", PAUSED_: "Play", FAILED: "Play", OPENING: "Play", "lead": "Open"}
ADD = "add"                 # the Radio list's first row, Add a station: no station's id

_ROW = dict(key="id", id="", name="", right="", sort="", st="", icon="", tone="")
s = ui.state(
    audio=True,             # a media service to play through
    online=True,            # ...and a network for the radio
    view=ui.enum("radio", "files", "now", "add", "noaudio", init="radio"),   # the tabs' page, or another
    tab=ui.enum("radio", "files", init="radio"),
    folder=ui.enum("unread", "nosd", "empty", "some", init="unread"),
    places=ui.model(key="id", id="", name="", icon=""),
    here="",                # the Library place the tab shows
    stations=ui.model(**_ROW),
    scur=ui.row_of("stations"),
    songs=ui.model(**_ROW),
    fcur=ui.row_of("songs"),
    verb="Play",            # what Enter does to the focused row
    playing=False,          # what plays: the card's
    main_icon="pause",
    main_word="Pause",
    seekable=False,         # ...a file's place
    radio=False,            # ...a station's, whose step is Station
    clock="",
    vol=0,                  # the volume's meter, ten steps
    url="",                 # Add a station's fields
    name="",
    err="",
)
ui.derive("listing", cond="view=radio || view=files")
ui.derive("paged", cond="view=now || view=add")
ui.labels("TABS", {"radio": "Radio", "files": "My music"})
ui.app("Music", icon="music", back="back", min=(300, 220))


def _lay():
    return uitree_app.env()


def _row(id, name, right, st, icon="music", sort=""):
    return {"id": id, "name": name, "right": right, "sort": sort, "st": st or "",
            "icon": LEAD.get(st, icon), "tone": "value" if st else ""}


def fill(lay):
    """The page's states from what plays, the stations and the folder;
    the lists written only where they moved."""
    st = STREAM
    c = st.card
    lay.gen = st.gen
    s.audio = st.media() is not None
    s.playing = c is not None
    if c is not None:
        state = FAILED if c["state"] == FAILED else PAUSED_ if c["paused"] else PLAYING
        s.main_icon, s.main_word = MAIN[state]
        s.seekable = bool(c["len"]) and c["state"] == PLAYING
        s.radio = c["kind"] == "radio"
        s.clock = "%s / %s" % (_clock(c["at"]), _clock(c["len"]))
        s.vol = level(c)
    elif s.view == "now":
        s.view = s.tab
    if not s.audio:
        s.view = "noaudio"
    if not s.places:
        s.places = [{"id": "radio", "name": "Radio", "icon": "volume"},
                    {"id": "files", "name": "My music", "icon": "music"}]
        s.here = s.tab
    rows = [_row(ADD, "Add a station", "", None, "plus")]
    rows[0]["tone"] = "value"
    for k, (name, style, _url) in enumerate(st.stations):
        rows.append(_row("r%d" % k, name, style, _state(c, name, "radio")))
    if rows != lay.rows[0]:
        lay.rows[0] = rows
        s.stations = rows
    f = lay.files
    s.folder = "unread" if f is None else "nosd" if f is False else "some" if f[0] or f[1] else "empty"
    rows = []
    desk = _lb.metric_class() == _lb.DESK      # the desk's table names each row's kind
    if f:
        for k, (name, _path, detail) in enumerate(f[1]):
            rows.append(_row("l%d" % k, name, detail, _state(c, name, "list"), "playlist",
                             "Playlist" if desk else ""))
        for k, (name, _path, detail) in enumerate(f[0]):
            rows.append(_row("s%d" % k, name, detail, _state(c, name, "song"), "music",
                             "Song" if desk else ""))
    if rows != lay.rows[1]:
        lay.rows[1] = rows
        s.songs = rows
    _verb()


def _verb():
    """The confirm hint's word: what Enter does to the focused row."""
    cur = s.fcur if s.tab == "files" else s.scur
    rows = _lay().rows[1 if s.tab == "files" else 0] or ()
    st = "lead" if cur == ADD else next((r["st"] for r in rows if r["id"] == cur), "")
    s.verb = VERB.get(st, "Play")


def row_moved(row):
    _verb()


def _playing_row(rows):
    for r in rows:
        if r["st"]:
            return r["id"]
    return rows[0]["id"] if rows else ""


def _focus_list():
    cur = s.fcur if s.tab == "files" else s.scur
    if cur:
        ui.focus(cur + "/pick")


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
    _verb()
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
    if row["st"]:
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


def place(row):
    s.tab = row.id
    tab_moved()


def tab_moved():
    s.view = s.tab
    s.here = s.tab
    if s.tab == "files" and _lay().files is None:
        _lay().folder_owed = True
    _verb()


def now():
    s.view = "now"
    ui.focus("toggle")


def player():
    """M: Now playing from either list, the list from Now playing."""
    if s.view == "now":
        back()
    else:
        now()


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


def louder():
    STREAM.volume(STREAM.volume() + VOLUME_STEP)


def quieter():
    STREAM.volume(STREAM.volume() - VOLUME_STEP)


def back_seek():
    STREAM.seek(STREAM.card["at"] - SEEK_STEP)


def ahead():
    STREAM.seek(STREAM.card["at"] + SEEK_STEP)


def strip_at(ev):
    """A press on the strip's head: Now playing."""
    if ev.kind == "down":
        now()


def seek_at(ev):
    """A tap on a file's bar in Now playing's head: the second it names."""
    c = STREAM.card
    if c is None or not c["len"] or ev.kind != "down":
        return
    d = _DRAWN["head"]
    fs = d[4]
    tx = d[3] + 12 * fs
    bw = _bar_w(d[2] - tx, fs)
    if ev.y >= 56 * fs and tx <= ev.x < tx + bw:
        STREAM.seek(c["len"] * (ev.x - tx) // max(1, bw))


def wifi():
    _lay().ctx.install.wifi()


def home():
    _lay().leave_asked = True


ui.hook("opened", opened)
ui.hook("tab_moved", tab_moved)
ui.hook("row_moved", row_moved, takes="row")
ui.hook("url_moved", url_moved)
ui.hook("strip_at", strip_at, takes="pointer")
ui.hook("vol_set", lambda: set_level(s.vol))
ui.hook("seek_at", seek_at, takes="pointer")
ui.action("pick", "Play", pick, takes="row", hint="{verb}")
ui.action("place", "Open", place, takes="row")
ui.action("back", "{view=add?Cancel:Back}", back, when="paged", off="hide")
ui.action("cancel", "Cancel", back)
ui.action("to_name", "Next", to_name)
ui.action("add", "Add", submit, when="!err", off="grey")
ui.action("main", "{main_word}", main, when="playing", off="hide")
ui.action("toggle", "{main_word}", main, when="playing", off="hide")     # Now playing's, focused
ui.action("stop", "Stop", stop, when="playing", off="hide")
ui.action("rewind", "Seek", back_seek, keys=("role:left", "a"), when="seekable && view=now",
          off="hide")
ui.action("ahead", "Seek", ahead, keys=("role:right", "d"), when="seekable && view=now",
          off="hide")
ui.action("louder", "Volume", louder, keys=("role:up", "w"), when="playing && view=now", off="hide")
ui.action("quieter", "Volume", quieter, keys=("role:down", "s"), when="playing && view=now",
          off="hide")
ui.action("player", "{view=now?List:Player}", player, keys=("m",), when="playing",
          off="hide")
ui.action("prev", "Previous", prev, keys=("q",), when="playing && view=now", off="hide",
          hint="{radio?Station:Song}")
ui.action("next", "Next", next_, keys=("e",), when="playing && view=now", off="hide",
          hint="{radio?Station:Song}")
ui.action("back_one", "Previous", prev, when="playing", off="hide")    # the desk card's, keyless
ui.action("on_one", "Next", next_, when="playing", off="hide")
ui.action("softer", "Quieter", quieter, when="playing", off="hide")
ui.action("harder", "Louder", louder, when="playing", off="hide")
ui.action("wifi", "Wi-Fi settings", wifi, hint="Open")
ui.action("home", "Back to home", home)


def _list(model, cur, shown):
    with ui.scroll(model + "_view", shown=shown):
        with ui.rows(model, cur=cur, changed="row_moved"):
            ui.link("pick", "{.right}", label="{.name}", icon="{.icon}", tone="{.tone}", tag="{.sort}")


def _radio():
    _list("stations", "scur", "online")
    with ui.empty("Radio needs Wi-Fi", icon="wifi_off", shown="!online",
                  lines=["Turn on Wi-Fi to listen to stations.", "Your own music plays without it."]):
        ui.button("wifi", "primary", icon="wifi", w=150, focus=True)


def _files():
    _list("songs", "fcur", "folder=some")
    ui.empty("No SD card", icon="folder", shown="folder=nosd",
             lines=["Put in an SD card with your songs on it.", "Radio plays without one."])
    ui.empty("No music yet", icon="music", shown="folder=empty",
             lines=["Put MP3 songs in the Music folder", "on the SD card."])


def _listing():
    """Either list: on a handheld under the tabs, the strip at its foot; on
    the desk the Library's two places beside it, the card across its foot."""
    ui.switch("tab", {"radio": _radio, "files": _files}, shown="!@desk")
    with ui.split("row", sizes=(168, "1*"), shown="@desk"):
        with ui.group(""):
            ui.label("Library", tone="dim")
            with ui.rows("places", current="here"):
                ui.link("place", label="{.name}", icon="{.icon}")
        with ui.group(""):
            ui.info("{tab=files?Name:Station}", "{tab=files?Length:Style}")
            ui.switch("tab", {"radio": _radio, "files": _files})
    with ui.foot(shown="playing && @desk"):
        with ui.row("card", gap=8):
            ui.canvas("wide", draw_wide, grow=True, h=64)
            ui.button("back_one", icon="prev", label="", w=40)
            ui.button("main", "primary", icon="{main_icon}", label="", w=80)
            ui.button("on_one", icon="next", label="", w=40)
            ui.button("stop", icon="stop", label="", w=40)
            ui.button("softer", icon="minus", label="", w=32)
            ui.label("", icon="volume")
            ui.slider("", "vol", 0, 10, look="blocks", on="vol_set")
            ui.button("harder", icon="plus", label="", w=32)


def _now():
    """Now playing on a 12 px grid, its block centred: the head, the
    transport on a 1:2:1 + 1 grid, the volume. Its keys are the page's own:
    Enter plays, pauses or tries again, Q E step, W S the volume, A D seek
    a file, M goes to the list."""
    with ui.split("col", sizes=(72, 36, 28, "1*"), gap=8, pad=8):
        ui.canvas("head", draw_now, pointer="seek_at")
        with ui.grid(5, 1, gap=8):
            ui.button("prev", icon="prev", label="")
            ui.button("toggle", "primary", icon="{main_icon}", label="", span=2, focus=True)
            ui.button("next", icon="next", label="")
            ui.button("stop", icon="stop", label="")
        with ui.split("row", sizes=(32, 38, "1*", 12, 32), gap=0, pad=0):
            ui.button("quieter", icon="minus", label="")
            ui.label("", icon="volume")
            ui.slider("", "vol", 0, 10, look="blocks", on="vol_set")
            ui.label("")
            ui.button("louder", icon="plus", label="")
        with ui.group(""):
            pass


def _add():
    """Add a station on the 12 px gutter: each field's label over it, its
    line under it, Cancel and Add at the foot."""
    with ui.split("col", sizes=("1*", 28), gap=8, pad=8):
        with ui.group(""):
            ui.label("Address", face="caption", tone="dim")
            ui.field("", "url", URL_MAX, hint="http://", on="to_name", changed="url_moved", edit="open")
            ui.label("{err}", tone="danger", wrap="word", lines=2, shown="err")
            ui.label(HELP_ADDRESS, tone="dim", shown="!err")
            ui.label("Name", face="caption", tone="dim")
            ui.field("", "name", NAME_MAX, hint="Optional", on="add", edit="open")
        with ui.split("row", sizes=("1*", 88, 8, 88), gap=0, pad=0):
            ui.label("")
            ui.button("cancel")
            ui.label("")
            ui.button("add", "primary")


def _no_audio():
    ui.empty("No sound on this console", icon="mute",
             lines=["This console has no speaker,", "so it can't play music or radio."])
    with ui.foot(look="share"):
        ui.button("home", "primary", icon="home")


def build():
    with ui.page(""):
        ui.tabs("tab", labels="TABS", on="tab_moved", shown="listing && !@desk",
                hint="{tab=radio?My music:Radio}")
        ui.switch("view", {"radio": _listing, "files": _listing, "now": _now, "add": _add,
                           "noaudio": _no_audio})
        with ui.foot(look="band", shown="playing && listing && !@desk"):
            with ui.row("strip", gap=0):
                ui.canvas("strip", draw_strip, grow=True, h=34, pointer="strip_at")
                ui.button("main", "tonal", icon="{main_icon}", label="", w=42)


TITLES = {"now": "Now playing", "add": "Add a station"}


class MusicAppLayer(uitree_app.app_layer("jukebox", "Music", build)):
    """The Music Layer: the page's engine handed this layer as what its
    handlers reach (`uitree_app.env()`), the stream's moves owing the page a
    fill, the music folder read off the draw (`idle_step`)."""

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


import music_card  # noqa: E402 -- the section's page, which reads this module: declared at import, as every page
