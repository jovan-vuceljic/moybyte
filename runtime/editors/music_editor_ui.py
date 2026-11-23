# Map (grep -n a name to jump there):
#   MusicLayout        the Music tab's content rect
#   MusicEditorUI      the music editor's UI: hosts the handheld page, the keys, the preview
#   MusicEditorUI.draw_row  a row of the steps table: its number, its step or slot, its meter
#   MusicEditorUI.act  a verb of the page on the core
#   SoundPane          the desk Editor's Sound pane: hosts its page, its header tools and keys
#   SoundPane.draw_graph  the pitch graph, each step's wave and the volume ladder
"""The music/sound editor's UI layer (issue #50): the MusicEditor over the
cart's AudioBank -- SFX view (note/wave/vol steps) and SONG view (a phrase of
SFX-id slots) -- its keys, and the live preview (played on the same audio
session the running cart uses). On the handheld the Music tab is the
`uitree` page of `runtime/editors/editor_music.py`, which this hosts; a desk Editor's Sound pane is
the page of `runtime/editors/editor_sound.py` over the same core, which `SoundPane` hosts,
and its Sounds and Song panes `runtime/editors/editor_parts.py`'s.

One instance lives on Workstation (`ws.music_ui`), with a back-reference to
it for the cart's audio session and `save_sounds`. Home.go_home() does
not reset musicedit/music_preview (blocks/map's go_home does reset their
active editor). Ctrl+Z/Ctrl+Y walk the editor's undo (`_music_input`)."""

from array import array

from editors_music import MusicEditor
from audio import MusicTrack, SFX
import ui as _ui
import ui_draw as _ui_draw
import layout_base as _layout_base
from layout_base import LayoutBase
import uitree_editor
import editor_music      # declared at import, never inside another page's handler
import editor_sound
from editor_sound import PAGE, SPAN, LEVELS

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
WAVES = ("SQR", "TRI", "SAW", "NOI", "PLS", "ORG", "TLT", "PHA")
ROW = 17                         # a step's row (the table's row=)
# A step's volume: seven bars, the lit ones first (`fill_rects(_METER, n)`).
_METER = array("h", [v for k in range(7) for v in (k * 9, 0, 7, ROW - 10, 0)])
_NUMS = tuple("%02d" % i for i in range(1, 257))
_DIGITS = tuple(str(i) for i in range(16))
_NOTE_NAMES = {}


def note_name(pitch):
    if pitch is None or pitch < 0:
        return "--"
    n = _NOTE_NAMES.get(pitch)
    if n is None:
        n = _NOTE_NAMES[pitch] = NOTE_NAMES[pitch % 12] + str(pitch // 12)
    return n


def sound_name(bank, n):
    """Sound `n` as the tab names it: its number and its name where it has
    one, else "Sound n"."""
    s = bank.sfx[n] if 0 <= n < len(bank.sfx) else None
    name = getattr(s, "name", None)
    return "%d %s" % (n, name) if name else "Sound %d" % n


def _slot_word(bank, row):
    if isinstance(row, list):
        sid = row[0] if row else -1
        extra = sum(1 for v in row[1:] if v >= 0)
    else:
        sid, extra = row, 0
    word = sound_name(bank, sid) if sid >= 0 else "--"
    return word + "  +%d" % extra if extra else word


class _Damage:
    def __init__(self, ws):
        self.ws = ws

    def all(self):
        self.ws.mark_dirty()


class _Surface:
    """What the page's host reads of the tab's surface: the console's
    pointer, whether it is held (a finger's drag scrolls the steps)."""

    def __init__(self, ws):
        self.ws = ws

    def pointer(self):
        return self.ws.pointer


class MusicLayout(LayoutBase):
    """The Music tab's geometry: the content rect, which the handheld page
    (`editor_music.music_page`) fills."""


class MusicEditorUI:
    """The music/sound editor's UI: the host of the handheld page, the keys
    and the preview. One instance lives on Workstation (`self.music_ui`),
    built once in Workstation.__init__; `ws.music_ui.build()` is called
    lazily from `set_menu_view("music")` the first time a cart's music
    editor is opened."""

    def __init__(self, ws, names):
        self.ws = ws
        # Injected instead of imported back from console.py -- see module docstring.
        self._NAMES = names
        # `musicedit` is built lazily on first open. `music_preview` tracks what
        # the cart's session is previewing so the frame loop ticks the mixer
        # and shows STOP; None when nothing is playing.
        self.musicedit = None         # MusicEditor while menu_view == "music"
        self.music_preview = None     # ("sfx", n) | ("song", track) | None (preview)
        self.page = None              # the handheld page's engine (editor_music.py), made at its first use
        self._host = _ui_draw.AppHost("editor_music", _Surface(ws))
        self._shown = None            # what `_sync` wrote last
        self._rows = ([], None)       # (the rows, what they were made from)
        self._sound = None            # the desk's Sound pane, made at its first use
        sc = ws.sys_canvas
        self.layout = MusicLayout(sc.w, sc.h, getattr(sc, "font_scale", 1))

    @property
    def sound(self):
        """The desk Editor's Sound pane (`SoundPane`)."""
        if self._sound is None:
            self._sound = SoundPane(self)
        return self._sound

    def _page(self):
        """The page's engine, made and opened at its first use."""
        if self.page is None:
            self.page = uitree_editor.page(editor_music.music_page, self._host,
                                           _Damage(self.ws))
            self.page.env = self            # what its handlers reach (`uitree_app.env()`)
            self.page.band = False          # the keys are the host's: no hints band
            self.page.open(hook="none")
        return self.page

    @property
    def s(self):
        """The page's state."""
        self._page()._bind()
        return editor_music.s

    def run(self, name, *args):
        """Run the page's action or hook `name` now."""
        pg = self._page()
        pg._bind()
        pg.run_action(pg.actions[name], args, "host")

    def popped(self):
        """Whether the speed popover is open."""
        return self.page is not None and self.s.pop

    def pointer(self, px, py, click):
        """A pointer sample on the tab (the layer's, after the bar's): the
        page's."""
        self._sync()
        self._page().point(px, py, click)

    def relayout(self, w, h, fs, cs=None):
        """Rebuild the responsive geometry (#39 step 3) -- called by ws.relayout on
        a font-scale change."""
        self.layout = MusicLayout(w, h, fs, chrome_scale=cs)

    def build(self):
        """Build the MusicEditor over the open cart's live AudioBank (#50): the
        SAME bank the running cart plays through, so an edit is heard immediately
        by the preview AND by the cart on resume. The bank is the run's audio
        session's (ws.run.audio.bank); SFX/MusicTrack are injected as
        factories so the editor core stays import-free. Called from
        Text.set_menu_view("music")."""
        ws = self.ws
        if self.musicedit is None and ws.run.audio is not None:
            bank = ws.run.audio.bank
            self.musicedit = MusicEditor(bank, sfx_factory=SFX,
                                         track_factory=MusicTrack)

    def reset(self):
        """Drop the active editor + preview flag -- called from Workstation.open()
        (switching carts). NOTE: unlike blocks/map, Home.go_home() does NOT
        call this (pre-existing asymmetry, preserved as-is)."""
        self.musicedit = None
        self.music_preview = None
        if self._sound is not None:
            self._sound.reset()

    # -- the page's state ------------------------------------------------------------

    def _steps(self, me, song):
        """The table's rows, made again only where a step (a slot) changed:
        each its index, its note, wave and volume (a slot: its word) and
        its meter's lit bars."""
        src = me.cur_track().pattern if song else me.cur_sfx().steps
        rows, made = self._rows
        key = (song, id(me.bank), [list(v) if isinstance(v, list) else v for v in src],
               [getattr(x, "name", None) for x in me.bank.sfx] if song else None)
        if key == made:
            return rows
        rows = []
        for i in range(len(src)):
            v = src[i]
            if song:
                rows.append(dict(k=str(i), a=_slot_word(me.bank, v), b="", c="", lit=0))
            else:
                rows.append(dict(k=str(i), a=note_name(v[0]) if v[0] >= 0 else "..",
                                 b=WAVES[v[1] & 7], c=_DIGITS[v[2] & 15],
                                 lit=max(0, min(7, v[2]))))
        self._rows = (rows, key)
        return rows

    def _sync(self):
        """The core's state the page shows, handed to its `sync` hook where
        it moved."""
        me = self.musicedit
        if me is None:
            vals = (True, False, "", 1, False, False, "", [], "", 0)
        else:
            song = me.view == me.SONG_VIEW
            obj = me.cur_track() if song else me.cur_sfx()
            n = me.slot_count() if song else me.step_count()
            name = "Song %d" % me.track_idx if song else sound_name(me.bank, me.sfx_idx)
            cur = me.slot if song else me.step
            vals = (False, song, name, int(obj.speed) if obj is not None else 1,
                    self.music_preview is not None, bool(obj is not None and obj.loop),
                    "%d %s" % (n, ("slot" if song else "step") + ("" if n == 1 else "s")),
                    self._steps(me, song), str(cur) if n else "", self._pad_w())
        if vals != self._shown:
            self._shown = vals
            self.run("sync", vals)

    def _pad_w(self):
        """The pad's width: two 61 px buttons on a 320 px tab, the widest
        words (Paste, Down) whole beside their icons, more of a wider one's
        room, at the font scale."""
        lay = self.layout
        fs = max(1, getattr(self.ws.sys_canvas, "font_scale", 1))
        return max(126 * fs, min(lay.cw * 3 // 8, 180 * fs))

    # -- the verbs (the page's handlers) -----------------------------------------------

    def set_view(self, song):
        me = self.musicedit
        if me is not None and (me.view == me.SONG_VIEW) != song:
            me.toggle_view()
            self._stop()
        self.ws.mark_dirty()

    def pick(self, key):
        me = self.musicedit
        if me is not None and key:
            me.select_cursor(int(key))
        self.ws.mark_dirty()

    def set_speed(self, v):
        me = self.musicedit
        if me is None:
            return
        obj = me.cur_track() if me.view == me.SONG_VIEW else me.cur_sfx()
        if obj is not None and v != obj.speed:
            me.nudge_speed(v - obj.speed)
        self.ws.mark_dirty()

    def _stop(self):
        if self.music_preview is not None:
            self._stop_music_preview()

    def act(self, verb):
        """A verb of the page: "prev", "next", "hear", "loop" or a pad's
        ("lower", "higher", "wave", "vol", "rest", "add", "dup", "del",
        "copy", "paste", "up", "down")."""
        me = self.musicedit
        if me is None:
            return
        song = me.view == me.SONG_VIEW
        if verb in ("prev", "next"):
            (me.select_track if song else me.select_sfx)(-1 if verb == "prev" else 1)
            self._stop()
        elif verb == "hear":
            if self.music_preview is not None:
                self._stop_music_preview()
            else:
                self._play_music_preview()
        elif verb == "loop":
            me.toggle_loop()
        elif verb in ("lower", "higher"):
            d = -1 if verb == "lower" else 1
            (me.nudge_slot if song else me.nudge_pitch)(d)
        elif verb == "wave":
            me.cycle_wave(1)
        elif verb == "vol":
            me.cycle_vol(1)
        elif verb == "rest":
            me.toggle_rest()
        elif verb == "add":
            me.add_slot() if song else me.add_step()
        elif verb == "del":
            me.del_slot() if song else me.del_step()
        elif verb == "dup":
            me.duplicate_track() if song else me.duplicate_sfx()
        elif verb == "copy":
            me.copy()
        elif verb == "paste":
            me.paste()
        elif verb in ("up", "down"):
            (me.move_slot if song else me.move_step)(-1 if verb == "up" else 1)
        self.ws.mark_dirty()

    # -- preview ---------------------------------------------------------------

    def _play_music_preview(self):
        """Preview what the cursor is on: in the SFX view play the current SFX, in
        the SONG view play the current phrase (looping). Plays on the cart's own
        session, focused so it is the one heard, on every tier. The frame loop
        ticks the mixer + redraws while a preview is up."""
        ws = self.ws
        me = self.musicedit
        au = ws.run.audio
        if me is None or au is None:
            return
        au.focus()
        au.sound_stop()                          # cut any prior preview first
        if me.view == MusicEditor.SONG_VIEW:
            au.music(me.track_idx, True)
            self.music_preview = ("song", me.track_idx)
        else:
            au.sfx(me.sfx_idx)
            self.music_preview = ("sfx", me.sfx_idx)
        ws.mark_dirty()

    def _stop_music_preview(self):
        """Stop any music-editor preview + clear the preview flag."""
        ws = self.ws
        if ws.run.audio is not None:
            ws.run.audio.sound_stop()
            ws.run.audio.music_stop()
        self.music_preview = None
        ws.mark_dirty()

    def _music_preview_active(self):
        """True while a music-editor preview is still producing sound (so the frame
        loop keeps ticking the mixer + redrawing the PLAY/STOP button). The
        session answers from the kernel, which holds the sequencers."""
        if self.music_preview is None:
            return False
        au = self.ws.run.audio
        return au is not None and au.is_active()

    # -- input -------------------------------------------------------------------

    def at_top(self):
        """The cursor on the first step or slot and no popover open: an up
        goes on to the bar (InputRouter._bar_keys)."""
        me = self.musicedit
        if me is None or self.popped():
            return False
        return (me.step if me.view == MusicEditor.SFX_VIEW else me.slot) <= 0

    def _music_input(self):
        """The page's popover takes the keys while it is open (B closes it);
        otherwise up/down move the step/slot cursor, left/right change the
        value under it (pitch / SFX-id), A plays/stops the preview, B leaves
        (#50). Called from the Music layer's handle_input."""
        ws = self.ws
        i = ws.input
        me = self.musicedit
        changed = False
        if self.popped():
            if i.pressed("b"):
                self.run("pop_close")
                ws.mark_dirty()
                return
            self._sync()
            self.page.keys(i)
            return
        if me is not None:
            if i.steps("up"):
                me.move_cursor(-1)
                changed = True
            if i.steps("down"):
                me.move_cursor(1)
                changed = True
            song = me.view == MusicEditor.SONG_VIEW
            if i.steps("left"):
                (me.nudge_slot if song else me.nudge_pitch)(-1)
                changed = True
            if i.steps("right"):
                (me.nudge_slot if song else me.nudge_pitch)(1)
                changed = True
            if i.pressed("a"):
                if self.music_preview is not None:
                    self._stop_music_preview()
                else:
                    self._play_music_preview()
        if i.pressed("b") or i.pressed("home"):
            changed = True
        ws.home.leave_or_home(ws.spine.exit)
        if changed:
            ws.mark_dirty()

    # -- drawing -------------------------------------------------------------------

    def _draw_music(self):
        """The Music tab: the handheld page in the content rect, no stop
        holding focus but the popover's."""
        ws = self.ws
        lay = self.layout
        r = (lay.cx, lay.cy, lay.cw, lay.ch)
        desk = _layout_base.metric_class() == _layout_base.DESK
        cv = ws.sys_canvas
        pg = self._page()
        self._sync()
        self._host.begin(cv, ws.theme_colors, r, desk, False, elsewhere=not self.s.pop)
        pg.paint(0, cv, ws.theme_colors, r, desk)
        _ui.end()
        if not self._host.still():
            ws.request_frame()

    def draw_row(self, cv, i, x, y, w, h):
        """Row `i` of the steps table in its part: its number (dim but on
        the cursor's row), a step's note, wave and volume and its meter, or
        a slot's sound, in the mono face."""
        me = self.musicedit
        rows = self._rows[0]
        if me is None or not 0 <= i < len(rows):
            return
        th = self.ws.theme_colors
        row = rows[i]
        song = me.view == me.SONG_VIEW
        cur = me.slot if song else me.step
        ink, dim = th["ink"], th["ink_dim"]
        fs = max(1, getattr(cv, "font_scale", 1))
        _ui.face("mono")
        lab = _ui_draw.label
        lab(cv, (x + 10 * fs, y, 20 * fs, h), _NUMS[i] if i < 256 else str(i + 1),
            ink if i == cur else dim)
        if song:
            lab(cv, (x + 34 * fs, y, max(0, w - 34 * fs), h), row["a"], ink)
        else:
            lab(cv, (x + 34 * fs, y, 30 * fs, h), row["a"], ink)
            lab(cv, (x + 66 * fs, y, 30 * fs, h), row["b"], dim)
            lab(cv, (x + 98 * fs, y, 12 * fs, h), row["c"], ink)
            lit = row["lit"]
            mx, my = x + 112 * fs, y + (h - (ROW - 10) * fs) // 2
            if lit < 7:
                cv.fill_rects(_METER, -1, mx, my, th["surface_alt"])
            if lit:
                cv.fill_rects(_METER, lit, mx, my, th["value"])
        _ui.face()


# -- the desk Editor's Sound pane ----------------------------------------------------

_LEFT, _RIGHT, _UP, _DOWN = 0x110, 0x111, 0x112, 0x113
_F2 = 0x101 + 1
_CTRL, _SHIFT, _ALT = 1, 2, 4


def _rungs(w, vh, u):
    """A step's ladder as LEVELS quads from its column's top left, the
    bottom rung first, so `fill_rects(q, n, ...)` draws the n lit ones."""
    key = (w & 0xFFF) | ((vh & 0xFFF) << 12) | ((u & 0xF) << 24)
    if _RUNGS[0] != key or _RUNGS[1] is None:
        q = []
        for k in range(LEVELS):
            q += (0, (LEVELS - 1 - k) * vh, w, vh - 2 * u, 0)
        _RUNGS[0] = key
        _RUNGS[1] = array("h", q)
    return _RUNGS[1]


_RUNGS = [0, None]           # (width, pitch, unit) packed -> the ladder's quads


def geometry(x, y, w, h, u, lw=None):
    """The graph canvas's parts in its rect: a dict of rects and sizes. The
    graph is 12 px a semitone where the canvas holds it, else 8 (800 x 480),
    6 at the least; a step 26 px where 16 fit, else narrower; the octaves'
    names left of it in a column `lw` wide (24 units, or more where the
    text scale is larger), each step's wave and the volume ladder under it."""
    pad = 12 * u
    fixed = 4 * u + 4 * u + 20 * u + 8 * LEVELS * u + 8 * u
    semi = 6 * u
    for sv in (12, 8):
        if fixed + SPAN * sv * u <= h:
            semi = sv * u
            break
    lw = max(24 * u, lw or 0)
    gx = x + pad + lw + 6 * u
    cw = max(10 * u, min(26 * u, (x + w - pad - gx) // PAGE))
    gy = y + 4 * u
    gh = SPAN * semi
    wy = gy + gh + 4 * u
    vh = 8 * u if semi >= 12 * u else 6 * u
    vy = wy + 20 * u
    return {"graph": (gx, gy, cw * PAGE, gh), "semi": semi, "cw": cw,
            "waves": (gx, wy, cw * PAGE, 16 * u), "ladder": (gx, vy, cw * PAGE, vh * LEVELS),
            "vh": vh, "lw": lw}


class SoundPane:
    """The desk Editor's Sound pane over the MusicEditor core: the host of
    its page (editor_sound.py), drawn in the pane's body through the desk's
    pane viewport, and the desk's half of it -- the pane's header tools,
    its keys and its title. One lives on the MusicEditorUI
    (`ws.music_ui.sound`), made at its first use."""

    def __init__(self, mu):
        self.mu = mu
        self.ws = mu.ws
        self._host = _ui_draw.AppHost("editor_sound", self)
        self.page = None
        self._shown = None
        self.brush = 1              # the wave brush: a wave id
        self.octs = {}              # a sound -> the graph's lowest C, as the pane left it
        self._u = 1
        self._lw = None             # the graph's names' column, 24 px at the text scale (`geometry`)

    def _page(self):
        if self.page is None:
            self.page = uitree_editor.page(editor_sound.sound_page, self._host,
                                           _Damage(self.ws))
            self.page.env = self
            self.page.band = False          # the pane's keys are the desk's
            self.page.bare = True           # the pane's card is its ground
            self.page.open(hook="none")
        return self.page

    @property
    def s(self):
        self._page()._bind()
        return editor_sound.s

    def run(self, name, *args):
        pg = self._page()
        pg._bind()
        pg.run_action(pg.actions[name], args, "host")
        self.ws.mark_dirty()

    def asking(self):
        """Whether a popover is up (the name, the sounds menu)."""
        return self.page is not None and self.s.asking != "none"

    def reset(self):
        """A fresh cart: the brush and the octaves as new, no popover."""
        self.brush = 1
        self.octs = {}
        self._shown = None
        if self.asking():
            self.run("close")

    def editor(self):
        """The MusicEditor over the open cart's bank, built where it is not."""
        mu = self.mu
        if mu.musicedit is None:
            mu.build()
        return mu.musicedit

    def _sfx(self):
        """The MusicEditor, its active object the sound: what the pane's
        edits act on (the Song pane beside it may have left it the song)."""
        me = self.editor()
        if me is not None and me.view != me.SFX_VIEW:
            me.toggle_view()
        return me

    def low(self, me):
        """The graph's lowest note, a C: as the pane left it for this sound, else
        the octave of the sound's lowest note, kept where the cursor's note shows."""
        s = me.cur_sfx()
        lo = self.octs.get(me.sfx_idx)
        if lo is None:
            heard = [t[0] for t in s.steps if t[0] >= 0 and t[2]] if s is not None else []
            lo = 12 * (min(heard) // 12) if heard else 48
        cur = me.cur_step()
        if cur is not None and cur[0] >= 0:
            if cur[0] < lo:
                lo = 12 * (cur[0] // 12)
            elif cur[0] >= lo + SPAN:
                lo = 12 * (cur[0] // 12) - 12
        lo = max(0, min(96 - SPAN, lo))
        self.octs[me.sfx_idx] = lo
        return lo

    def title(self):
        me = self.editor()
        if me is None:
            return "Sound"
        s = me.cur_sfx()
        name = getattr(s, "name", None) if s is not None else None
        return "Sound %d · %s" % (me.sfx_idx, name) if name else "Sound %d" % me.sfx_idx

    # -- the page ------------------------------------------------------------------------

    def _sync(self):
        me = self.mu.musicedit
        if me is None:
            vals = (True, [], "", "", "", "", False, False)
        else:
            cur = me.cur_step()
            if cur is not None:
                self.brush = cur[1]
            th = self.ws.theme_colors
            rgb = (editor_sound.WAVE_RGB_DAY if th.get("surface_light", False)
                   else editor_sound.WAVE_RGB_NIGHT)
            rows = [dict(k=str(w), rgb=rgb[w]) for w in editor_sound.WAVES]
            n = me.step_count()
            page = me.step // PAGE
            vals = (False, rows, str(self.brush), editor_sound.WAVE_WORDS[self.brush],
                    "Oct %d" % (self.low(me) // 12),
                    "%d–%d" % (page * PAGE + 1, min(n, page * PAGE + PAGE)), n > PAGE,
                    self._roomy())
        if vals != self._shown:
            self._shown = vals
            self.run("sync", vals)

    def _roomy(self):
        """Whether the ops row holds both steppers past its ops."""
        u = self._u
        ops = len(editor_sound.OPS)
        room = self.mu.layout.cw - 2 * 12 * u - ops * editor_sound.OP_W * u - ops * 4
        return room >= 2 * editor_sound.STEPPER_W * u

    def draw(self, dt):
        """The pane's body: the page in the pane's content rect (the desk
        lays the music tab's layout out at the pane's body)."""
        ws = self.ws
        if ws.audio_out is not None:
            ws.audio_out.tick(dt)
        mu = self.mu
        if mu.music_preview is not None and not mu._music_preview_active():
            mu.music_preview = None
            ws.mark_dirty()
        self.editor()
        lay = mu.layout
        r = (lay.cx, lay.cy, lay.cw, lay.ch)
        cv = ws.sys_canvas
        th = ws.theme_colors
        pg = self._page()
        self._u = max(1, _layout_base.chrome_size(ws.look.effective_font_scale())
                      // _layout_base.render_scale())
        pg.unit = self._u
        self._sync()
        self._host.begin(cv, th, r, True, False, elsewhere=not self.asking())
        pg.paint(dt, cv, th, r, True)
        _ui.end()
        if not self._host.still():
            ws.request_frame()

    def pointer(self):
        """The pointer, where the page's host reads whether it is held."""
        return self.ws.pointer

    def handle_pointer(self, px, py, click):
        """A pointer sample on the body, in its coordinates: the page's."""
        self._sync()
        self._page().point(px, py, click)
        return True

    def page_keys(self, i):
        """The keys while a popover is up: the page's."""
        self._sync()
        return self._page().keys(i)

    # -- the page's handlers --------------------------------------------------------------

    def act(self, op):
        """One of the pane's verbs on the core: an undo step each."""
        me = self._sfx()
        if me is None:
            return
        if op == "add":
            me.add_step()
        elif op == "del":
            me.del_step()
        elif op == "copy":
            me.copy()
        elif op == "paste":
            me.paste()
        elif op == "dup":
            me.duplicate_sfx()
        elif op == "earlier":
            me.move_step(-1)
        elif op == "later":
            me.move_step(1)
        elif op == "rest":
            me.toggle_rest(self.low(me) + 12)
        elif op == "loop":
            me.toggle_loop()
        elif op == "faster":
            me.nudge_speed(1)
        elif op == "slower":
            me.nudge_speed(-1)
        elif op in ("oct+", "oct-"):
            lo = self.low(me) + (12 if op == "oct+" else -12)
            self.octs[me.sfx_idx] = max(0, min(96 - SPAN, lo))
            cur = me.cur_step()
            if cur is not None and cur[0] >= 0:
                me.nudge_pitch(12 if op == "oct+" else -12)
        elif op in ("page+", "page-"):
            n = me.step_count()
            to = (me.step // PAGE + (1 if op == "page+" else -1)) * PAGE
            if 0 <= to < n:
                me.select_cursor(to)
        self.ws.mark_dirty()

    def set_wave(self, wv):
        me = self._sfx()
        st = me.cur_step() if me is not None else None
        if st is not None and st[1] != wv:
            me.cycle_wave((wv - st[1]) % 8)
            self.ws.mark_dirty()

    def set_brush(self, wv):
        """A swatch picked: the brush's wave, and the step's."""
        self.brush = wv
        self.set_wave(wv)

    def set_name(self, text):
        me = self._sfx()
        if me is not None:
            me.set_name(text)
        self.ws.mark_dirty()

    def pick_sound(self, k):
        """A row of the sounds menu: that sound, or a new one past the last."""
        me = self._sfx()
        if me is None:
            return
        if k >= len(me.bank.sfx):
            me.select_sfx(len(me.bank.sfx) - me.sfx_idx)
        else:
            me.sfx_idx = k
            me.step = 0
        self.ws.mark_dirty()

    def play(self):
        """Play the sound, or stop it."""
        mu = self.mu
        if self.editor() is None:
            return
        if mu.music_preview is not None:
            mu._stop_music_preview()
            return
        self._sfx()
        mu._play_music_preview()

    def graph_pointer(self, kind, x, y):
        """A press or drag on the graph canvas, in its coordinates: on the
        graph the step and its note, on the wave row the brush's wave (a
        press), on the ladder the step's volume."""
        me = self.editor()
        r = self._page().rect_of("graph")
        if me is None or r is None or kind == "up":
            return
        u = self._u
        g = geometry(0, 0, r[2], r[3], u, self._lw)
        hit = None
        for key in ("graph", "waves", "ladder"):
            gx, gy, gw, gh = g[key]
            if gx <= x < gx + gw and gy <= y < gy + gh:
                hit = key
                break
        if hit is None:
            return
        gx, gy, gw, gh = g[hit]
        n = (me.step // PAGE) * PAGE + (x - gx) // g["cw"]
        if n >= me.step_count():
            return
        self._sfx()
        if n != me.step:
            me.select_cursor(n)
        stp = me.cur_step()
        if hit == "graph":
            k = (gy + gh - 1 - y) // g["semi"]
            p = self.low(me) + max(0, min(SPAN - 1, k))
            if stp[0] != p:
                me.set_pitch(p)
                if stp[2] == 0:
                    me.nudge_vol(5)
        elif hit == "waves":
            if kind == "down":
                self.set_wave(self.brush)
        else:
            lv = max(0, min(LEVELS, LEVELS - (y - gy) // g["vh"]))
            if stp[2] != lv:
                me.nudge_vol(lv - stp[2])
        self.ws.mark_dirty()

    def draw_graph(self, cv, x, y, w, h):
        """Two octaves from `low`, a row a semitone (the sharps shaded, each C
        ruled and named), a column a step: its note as a capped bar in its
        wave's ink, the selected step's column on the value plate and its note
        named over it; each step's wave under it; the volume ladder."""
        me = self.mu.musicedit
        if me is None:
            return
        th = self.ws.theme_colors
        u = self._u
        self._lw = 24 * max(u, getattr(cv, "font_scale", 1))
        g = geometry(x, y, w, h, u, self._lw)
        s = me.cur_sfx()
        gx, gy, gw, gh = g["graph"]
        semi, cw, lw = g["semi"], g["cw"], g["lw"]
        lo = self.low(me)
        light = th.get("surface_light", False)
        dim, lab = th["ink_dim"], _ui_draw.label
        cv.rrect(gx, gy, gw, gh, 6 * u, th["surface"] if light else th["panel"], th["border"])
        outer = self.page.clip_to
        uitree_editor._clip_in(cv, gx + 1, gy + 1, gw - 2, gh - 2, outer)
        for k in range(SPAN):
            if (lo + k) % 12 in (1, 3, 6, 8, 10):
                cv.shadow(gx, gy + gh - (k + 1) * semi, gw, semi, 0, th["ink"], 10, 0)
        for k in range(1, SPAN):
            if (lo + k) % 12 == 0:
                cv.rect(gx, gy + gh - k * semi, gw, 1, th["border"])
        steps = s.steps if s is not None else []
        first = (me.step // PAGE) * PAGE
        sel = me.step - first
        if 0 <= sel < PAGE:
            cv.shadow(gx + sel * cw + 1, gy + 1, cw - 2, gh - 2, 4 * u, th["value"], 40, 0)
        named = None
        for i in range(PAGE):
            n = first + i
            if n >= len(steps):
                break
            p, wv, v = steps[n][0], steps[n][1], steps[n][2]
            if p < 0 or not v:
                continue
            k = max(0, min(SPAN - 1, p - lo))
            top = gy + gh - (k + 1) * semi
            cx = gx + i * cw
            ink = editor_sound.wave_ink(th, wv)
            body = gy + gh - top - semi - 1
            if body > 0:
                cv.rect(cx + 4 * u, top + semi, cw - 8 * u, body, ink)
                cv.shadow(cx + 4 * u, top + semi, cw - 8 * u, body, 0, th["surface"], 150, 0)
            cv.rrect(cx + 3 * u, top, cw - 6 * u, semi, 3 * u, ink)
            if i == sel:
                named = (cx, top, p)
        uitree_editor._clip_in(cv, x, y, w, h, outer)
        for k in range(0, SPAN, 12):
            lab(cv, (gx - lw - 2 * u, gy + gh - k * semi - 14 * u, lw, 14 * u), note_name(lo + k), dim)
        if named is not None:
            cx, top, p = named
            t = note_name(p)
            tw = _ui.text_size(t, getattr(cv, "font_scale", 1))[0] + 10 * u
            th_ = 18 * u
            nx = max(gx, min(gx + gw - tw, cx + (cw - tw) // 2))
            ny = max(gy + 2 * u, top - th_ - 2 * u)
            cv.rrect(nx, ny, tw, th_, 5 * u, th["surface"], th["value"])
            lab(cv, (nx, ny, tw, th_), t, th["value"], _ui_draw.ALIGN_CENTER)
        wx, wy, _ww, wh = g["waves"]
        lx, ly, _lw, _lh = g["ladder"]
        vh = g["vh"]
        rungs = _rungs(cw - 8 * u, vh, u)
        for i in range(PAGE):
            n = first + i
            cx = wx + i * cw
            if n >= len(steps):
                cv.rect(cx + cw // 2 - 1 * u, wy + 7 * u, 2 * u, 2 * u, th["border"])
                continue
            p, wv, v = steps[n][0], steps[n][1], steps[n][2]
            d = 8 * u
            cv.rrect(cx + (cw - d) // 2, wy + (wh - d) // 2, d, d, 2 * u,
                     editor_sound.wave_ink(th, wv) if p >= 0 else th["border"])
            lit = max(0, min(LEVELS, v)) if p >= 0 else 0
            if lit < LEVELS:
                cv.fill_rects(rungs, -1, cx + 4 * u, ly, th["border"])
            if lit:
                cv.fill_rects(rungs, lit, cx + 4 * u, ly, th["value"])
        lab(cv, (gx - lw - 2 * u, ly + (LEVELS * vh - 14 * u) // 2, lw, 14 * u), "Vol", dim)

    # -- the desk's half: the header, the keys, the popovers' doors -----------------------

    def head_vals(self, desk):
        """The pane header's Sound tools (editor_head.py): whether there is a
        sound, whether it plays, its speed, whether it loops, and whether
        the sounds menu stands in for a Sounds list the desk does not show."""
        me = self.editor()
        if me is None:
            return (False, False, "", False, False)
        mu = self.mu
        s = me.cur_sfx()
        return (True, mu.music_preview is not None and mu.music_preview[0] == "sfx",
                "%d" % int(s.speed) if s is not None else "", bool(s is not None and s.loop),
                not desk.shows("sounds"))

    def head_act(self, desk, op):
        """A header tool: play, faster, slower, loop, rename or the sounds
        menu."""
        if self.editor() is None:
            return
        if op == "play":
            self.play()
        elif op == "rename":
            self.open_rename(desk)
        elif op == "menu":
            self.open_menu(desk)
        else:
            self.act(op)

    def open_rename(self, desk):
        """The name popover, hung under the pane's header: a field whose
        Enter names the sound (empty: no name, the list shows its number)."""
        me = self.editor()
        box = desk.header_rect("music")
        if me is None or box is None:
            return
        u = self._u
        s = me.cur_sfx()
        w = min(box[2] - 16 * u, 300 * u)
        self.run("rename_open", ((getattr(s, "name", None) or "") if s is not None else "",
                                 "%d 0 %d 0" % (8 * u, w), w))

    def open_menu(self, desk):
        """Where no Sounds list shows (800 x 480): the bank as a menu from
        the pane's title."""
        me = self.editor()
        if me is None or desk.header_rect("music") is None:
            return
        u = self._u
        n = len(me.bank.sfx)
        rows = [dict(k=str(k), label=editor_sound.row_label(me, k), icon="music") for k in range(n)]
        rows.append(dict(k=str(n), label="New sound", icon="new"))
        self.run("menu_open", (rows, "%d 0 %d 0" % (8 * u, 220 * u), 220 * u))

    def keys(self, desk, i, ev):
        """The pane's keys while it is focused and no popover is up
        (EDITOR_LAYOUT.md: a pane keeps its own keys): left and right pick a
        step, up and down move its note (Shift an octave), held at the repeat
        rate, W the next wave, R a rest, [ and ] the speed, L loop, Space
        plays, + and - the volume, Del deletes, Ctrl+C/V/D copy, paste and
        duplicate, Alt+Left/Right move the step, F2 renames. `i` is the input
        (an arrow alone is the d-pad, no key event), `ev` this frame's new
        key event or 0. True where one acted."""
        me = self.editor()
        if me is None or self.asking():
            return False
        code, mods = ev & 0xFFFF, ev >> 16
        n = 1
        if not ev:
            # an arrow alone: its press and, held, its repeats at the rate
            mods = getattr(i, "mods", 0) or 0
            for name, c in (("left", _LEFT), ("right", _RIGHT), ("up", _UP), ("down", _DOWN)):
                n = i.steps(name)
                if n:
                    code = c
                    break
            if not code:
                return False
        ctrl, shift, alt = mods & _CTRL, mods & _SHIFT, mods & _ALT
        self._sfx()
        if code in (_LEFT, _RIGHT):
            d = -n if code == _LEFT else n
            if alt:
                self.act("earlier" if d < 0 else "later")
            else:
                me.move_cursor(d)
        elif code in (_UP, _DOWN) and not alt:
            cur = me.cur_step()
            if cur is not None and cur[0] < 0:
                me.toggle_rest(self.low(me) + 12)
            else:
                me.nudge_pitch((12 if shift else 1) * (n if code == _UP else -n))
        elif ctrl and code in (ord("c"), ord("C"), 3):
            self.act("copy")
        elif ctrl and code in (ord("v"), ord("V"), 22):
            self.act("paste")
        elif ctrl and code in (ord("d"), ord("D"), 4):
            self.act("dup")
        elif ctrl or alt:
            return False
        elif code in (ord("w"), ord("W")):
            cur = me.cur_step()
            brush = editor_sound.WAVES
            self.set_wave(brush[(brush.index(cur[1]) + (7 if shift else 1)) % 8]
                          if cur is not None else 0)
        elif code in (ord("r"), ord("R")):
            self.act("rest")
        elif code in (ord("l"), ord("L")):
            self.act("loop")
        elif code == ord("["):
            self.act("slower")
        elif code == ord("]"):
            self.act("faster")
        elif code == ord(" "):
            self.play()
        elif code in (ord("+"), ord("=")):
            me.nudge_vol(1)
        elif code in (ord("-"), ord("_")):
            me.nudge_vol(-1)
        elif code == 0x7F:
            self.act("del")
        elif code == _F2:
            self.open_rename(desk)
        else:
            return False
        self.ws.mark_dirty()
        return True
