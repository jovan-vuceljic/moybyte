# Map (grep -n a name to jump there):
#   ThemeDoc              the theme package open in the Editor: its theme.json
#   ThemeDoc.save         Config's text, written through the look
#   ThemeDoc.step         undo and redo, the session's alone
#   ConfigLayout          the Config tab's geometry: the code view, its status line, the hints
#   ConfigLayer           the Config tab: theme.json in the Code tab's view, json mode
"""The Editor's theme mode (docs/history/look_2026-10.md step 33, GAPS 56): a theme
package's theme.json opened in the console's Editor, one tab and nothing a
cart has -- no Code, Blocks, Map, Music and no Play: an edit applies live,
so there is nothing to run. Appearance's Edit theme… opens it
(`Appearance.edit_file`, which makes `custom` from a seed first),
`Text.edit_theme` hands it to the Editor (`EditorApp.open_theme`), and Done
(‹, K, Esc) brings the Editor back to where it was opened from.

**Config** is the package's theme.json, opened indented, in the Code tab's
view (`ConfigLayer` is a `CodeLayer` whose language is JSON): the gutter,
the current line, long lines fading at the edge. Its saves are the look's
(`Appearance.file_check` gates, `file_write` writes, `file_saved` installs at
the next frame), never a project's: a theme package is flat data with no
`journal/`, so undo lives in the session and a save keeps no history.

The console edits no icon: a package that wants its own ships its tiles
(`icons.moygfx`, named in its look's `icons.pixel_slots`;
runtime/toolkit/iconsets.py says where they draw).

Keys: the Code tab's, where letters type and the trackball is the caret's
arrows; Esc (B on a pad) is Done, and on the T-Deck Mic opens the menu on
its Home row, which leaves saving as Done does. The desk shows the tab as
the `theme` workspace's one pane (runtime/editors/editor_desk.py).
"""

import ui_font as _ui_font
import ui_draw as _ui_draw
import text_modes as _modes
import layout_base as _lb
from code_layer import CodeLayer
from chrome import CodeLayout
from editors_code import CodeEditor

TAB_CONFIG = "theme_config"
INVALID = "INVALID"              # a refused save's badge (editor_handle's)
THEME_BYTES = 16384              # style.json's theme.bytes: the cap the status line names


def _dot():
    return " · " if _ui_font.print_symbols() else " - "


# -- the package ------------------------------------------------------------------


class ThemeDoc:
    """`custom` open in the Editor: its theme.json as Config's buffer and
    whether it is written. `made` is the theme it was copied from just now,
    which Config's status line names once."""

    def __init__(self, ws, made=None):
        self.ws = ws
        look = ws.look
        self.name = look.theme_name
        self.note = None
        if made is not None:
            how = "is built in" if made in _builtin_names() else "stays as it is"
            self.note = "%s %s: this is your copy, %s" % (
                made[:1].upper() + made[1:], how, self.name)
        self.max_chars = look.max_chars
        text = look.file_text() or ""
        self.ed = CodeEditor(_modes.pretty(_modes.JSON, text)[:self.max_chars], 32, 12,
                             clip=getattr(ws, "clipboard", None))
        self.badge = ""
        self.saved = True              # Config's text is the file's
        self._wgen = look.file_gen

    # -- undo -------------------------------------------------------------------

    def step(self, router, redo):
        """Undo (or redo) one step of Config's typing: True where one was taken."""
        router.close_code_burst()
        hist = router.code_op_history()
        if hist is None:
            return False
        can = hist.can_redo() if redo else hist.can_undo()
        if not can or (hist.redo() if redo else hist.undo()) is None:
            return False
        self.ed.dirty = True
        self.saved = False
        self.ws.mark_dirty()
        self.ws.bar_layer.invalidate()
        return True

    def can(self, router, redo):
        hist = router.code_op_history()
        if hist is None:
            return False
        if redo:
            return hist.can_redo()
        return hist.can_undo() or router._code_burst_pending()

    # -- the saves --------------------------------------------------------------

    def clean(self):
        return not self.ed.dirty and self.saved

    def save_config(self, soft=False):
        """Write Config's text: (ok, badge). `soft` (the idle save) refuses a
        text the loader would not take and badges it; every other caller is
        an exit and writes it anyway, keeping the badge (a kid's text is
        theirs; the loader refuses it the next time the theme loads)."""
        look = self.ws.look
        self.ws.history.close_code_burst()
        body = self.ed.text()[:self.max_chars]
        good, why = _modes.check(_modes.JSON, body)
        out = body
        if good:
            good, why, out = look.file_check(body)
            if not good:
                out = body
        self.badge = why if good else (INVALID + " " + why).rstrip()
        if not good and soft:
            return (False, self.badge)
        err = look.file_write(out)
        if err is not None:
            return (False, str(err))
        self.ed.dirty = False
        self.saved = True
        self.note = None
        self._wgen = look.file_gen
        if good:
            look.file_saved(out)
        self.ws.mark_dirty()
        return (True, self.badge)

    def save(self, soft=False):
        """Config's save where it holds an edit (`soft`: the idle one, which
        refuses a text the loader would not take). True when it wrote."""
        if self.clean():
            return False
        return self.save_config(soft)[0]

    def commit(self):
        """Every exit's hard commit: Config's text where it is unwritten."""
        if not self.clean():
            self.save_config()

    def follow(self):
        """A write made elsewhere (the Appearance rows): Config with no edits
        reads the file again."""
        ws = self.ws
        look = ws.look
        if look.file_gen != self._wgen and self.clean():
            self._wgen = look.file_gen
            text = look.file_text()
            if text is not None:
                self.ed.set_text(_modes.pretty(_modes.JSON, text)[:self.max_chars])
                ws.history.drop_code_history()

    def status(self):
        """Config's status line: the copy's note once, else the file, its
        size against the cap and whether it is saved (or the badge)."""
        if self.note is not None:
            return self.note
        n = len(self.ed.text())
        kb = THEME_BYTES
        size = "%d.%d of %d KB" % (n // 1024, (n % 1024) * 10 // 1024, kb // 1024)
        tail = self.badge or ("Saved" if self.clean() else "Edited")
        return "theme.json" + _dot() + size + _dot() + tail


def _builtin_names():
    from chrome import THEME_NAMES
    return THEME_NAMES


# -- the hint strips ----------------------------------------------------------------


def _hints_for():
    """Config's keys for the hint input (`ui_draw.hint_kind`): the T-Deck's
    are its own (moy_ui_parts.c's ACT_KEYS), a keyboard's and a pad's
    Done, none under touch alone."""
    inp = _ui_draw.hint_kind()
    if inp == "touch":
        return ()
    if inp == "tdeck":
        return ("menu", "Home")     # the menu opens on its Home row
    return ("back", "Done")


# -- Config -------------------------------------------------------------------------


class ConfigLayout(CodeLayout):
    """The Code tab's geometry for Config: no symbol keys, the status line
    over the hint strip where the input has keys."""

    def __init__(self, w, h, font_scale=1, chrome_scale=None, keys=True):
        CodeLayout.__init__(self, w, h, font_scale, chrome_scale, symbols=False)
        fs = self.fs
        desk = _lb.metric_class() == _lb.DESK
        self.keys = keys
        hint_h = (max(34 // _lb.render_scale(), 18 * fs) if desk else 22 * fs) \
            if keys and not desk else 0
        self.hints = (self.cx, self.cy + self.ch - hint_h, self.cw, hint_h) if hint_h else None
        band = self.status_band[3]
        y = self.cy + self.ch - hint_h - band
        self.status_band = (self.cx, y, self.cw, band)
        self.status_text = (self.status_text[0], y, self.status_text[2], band)
        self.rows = max(4, (y - self.y0) // self.lh)


class ConfigLayer(CodeLayer):
    """The Config tab: the package's theme.json in the Code tab's view, its
    language JSON, the theme's status line under it. The buffer is the open
    ThemeDoc's (`ws.editor` while the theme mode is open), its keys the Code
    tab's less what JSON has no use for (completion, Go to, the scripts)."""
    # Esc closes theme mode back to Appearance (its handle_input), not
    # the Editor's leave.
    ESC_LEAVES = False

    id = TAB_CONFIG
    PAGE = "config_page"

    def __init__(self, ws, names):
        CodeLayer.__init__(self, ws, names)
        self.layout = None
        self._args = None

    def relayout(self, w, h, fs, cs=None):
        self._args = (w, h, fs, cs)
        self.layout = ConfigLayout(w, h, fs, cs, keys=_ui_draw.hint_kind() != "touch")

    def _sync(self):
        """Lay the tab out where nothing has (a desk pane lays it out at the
        pane's size, `EditorDesk._in_pane`), and again on a handheld where the
        input moved between touch and keys (the hint strip)."""
        ws = self.ws
        if self.layout is None:
            sc = ws.sys_canvas
            self.relayout(sc.w, sc.h, ws.look.effective_font_scale(),
                          ws.look.effective_chrome_scale())
        elif (self._args is not None and ws.editor_app._desk() is None
              and self.layout.keys != (_ui_draw.hint_kind() != "touch")):
            self.relayout(*self._args)

    def _doc(self):
        return self.ws.editor_app.theme

    def _lang(self):
        return "json"

    def wants_symbols(self):
        return False

    def wants_tools(self):
        return False

    def _recheck_err(self):
        self.ws.crash_popup = None

    def open_scripts(self):
        pass

    def _with(self, fn, *args):
        """Run `fn` with the Code tab's layout handle on Config's and the
        buffer the open theme's: what every CodeLayer verb reads."""
        ws = self.ws
        doc = self._doc()
        if doc is None:
            return None
        self._sync()
        lay = self.layout
        ed = doc.ed
        if (ed.COLS, ed.ROWS) != (lay.cols, lay.rows):
            ed.set_view_size(lay.cols, lay.rows)
        old_lay, old_ed = ws.code_layout, ws.editor
        ws.code_layout, ws.editor = lay, ed
        try:
            return fn(*args)
        finally:
            ws.code_layout = old_lay
            if ws.editor is ed:
                ws.editor = old_ed

    def draw(self, dt):
        doc = self._doc()
        if doc is not None:
            doc.follow()
        self._with(CodeLayer.draw, self, dt)

    def _frame_keys(self):
        return _hints_for()

    def _note(self):
        """The theme's status line."""
        doc = self._doc()
        if doc is None:
            return ("", False)
        return (doc.status(), doc.note is not None)

    def handle_input(self, i):
        doc = self._doc()
        if doc is None:
            return True
        k = i.typed
        app = self.ws.editor_app
        if k:
            if k == 27 and not (self._find_open or self._cmp_open or self._jump_open):
                self.ws.defer(app.close_theme)
                return True
        if _ui_draw.input_kind() == "pad" and i.pressed("b"):
            self.ws.defer(app.close_theme)          # a gamepad types nothing here
            return True
        got = self._with(CodeLayer.handle_input, self, i)
        if k and doc.ed.dirty:
            doc.saved = False
            doc.note = None
        return got if got is not None else True

    def handle_pointer(self, px, py, click):
        return self._with(CodeLayer.handle_pointer, self, px, py, click)

    def nav(self, dx, dy, select=None):
        doc = self._doc()
        if doc is not None:
            doc.ed.move(dy, dx, select)
