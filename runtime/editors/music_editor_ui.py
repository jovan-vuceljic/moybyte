# Map (grep -n a name to jump there):
#   MusicLayout        the Music tab's content rect
#   MusicEditorUI      the music editor's UI: hosts the handheld page, the keys, the preview
#   MusicEditorUI.draw_row  a row of the steps table: its number, its step or slot, its meter
#   MusicEditorUI.act  a verb of the page on the core
"""The music/sound editor's UI layer (issue #50): the MusicEditor over the
cart's AudioBank -- SFX view (note/wave/vol steps) and SONG view (a phrase of
SFX-id slots) -- its keys, and the live preview (played on the same audio
session the running cart uses). On the handheld the Music tab is the
`uitree` page of `runtime/editors/editor_music.py`, which this hosts; a desk Editor's Sound pane is
`runtime/editors/editor_sound.py` over the same core, and its Sounds and Song panes
`runtime/editors/editor_parts.py`'s.

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
        self._host = _ui_draw.AppHost("editor_music")
        self._shown = None            # what `_sync` wrote last
        self._rows = ([], None)       # (the rows, what they were made from)
        sc = ws.sys_canvas
        self.layout = MusicLayout(sc.w, sc.h, getattr(sc, "font_scale", 1))

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
        """The pad's width: two 60 px buttons on a 320 px tab, more of a
        wider one's room (its words whole), at the font scale."""
        lay = self.layout
        fs = max(1, getattr(self.ws.sys_canvas, "font_scale", 1))
        return max(124 * fs, min(lay.cw * 3 // 8, 180 * fs))

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
