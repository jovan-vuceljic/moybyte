"""The text view (native/moy_ui/moy_ui_text.h;
docs/history/scroll_and_text_2026-10.md §5): the Code tab's and theme Config's rows
and the desk's made code, drawn in C through the verb, and only the rows
that changed.

Each Code session runs on two consoles fed the same input: one as it ships,
and one whose Code tab draws every frame whole (its host never shifts) -- on
one, two and three buffers presented in turn as a board's are. Every
presented picture of the first is held to the second's bytes, so every rows
and shift frame is a whole repaint's; the share of floor frames is held
above a floor, so the mechanism cannot silently stop. The C's colour runs
are held to the Python highlighter's (`tests/text_twin.py`), and the Code
tab's pixels at rest to the goldens (tests/test_shell_goldens.py)."""

import re
from pathlib import Path

import pytest

import text_twin
from runtime import appearance, code_layer, host_app, moy_input, ui_draw
from ws_helpers import no_unlock_banner, quiesce

_C = ui_draw._C
ROOT = Path(__file__).resolve().parent.parent


def test_the_options_are_the_headers():
    """The text view's options and the host binding's defaults are
    moy_ui_api.h's MOY_UI_TXO_*."""
    src = (ROOT / "native" / "moy_ui" / "moy_ui_api.h").read_text()
    body = src[src.index("MOY_UI_TXO_ROWS = 0"):src.index("MOY_UI_TXO_LEN")]
    names = re.findall(r"MOY_UI_TXO_([A-Z0-9_]+)", body)
    from runtime import moy_ui_binding
    assert len(names) == moy_ui_binding._TXO_LEN
    words = re.search(r"#define MOY_UI_TXO_DEFAULTS \{([^}]*)\}", src).group(1).split(",")
    want = tuple(ui_draw.SYN_SGR if w.strip() == "MOY_UI_SYN_SGR" else int(w) for w in words)
    assert want == moy_ui_binding._TXO_DEFAULTS


def test_the_syntaxes_are_named_alike_in_every_face():
    """A syntax's name is its MOY_UI_SYN_* number in ui_draw's table."""
    head = (ROOT / "native" / "moy_ui" / "moy_ui_text.h").read_text()
    body = head[head.index("MOY_UI_SYN_NONE = 0"):head.index("MOY_UI_SYN_N\n")]
    syns = re.findall(r"MOY_UI_SYN_([A-Z]+)", body)
    assert len(ui_draw.SYNTAX) == len(syns) - 1
    for name, i in ui_draw.SYNTAX.items():
        assert syns[i] == name.upper()


# -- the runs ------------------------------------------------------------------------

def _c_runs(line, syn):
    """The C's runs as (first column, column after, class)."""
    w = _C.text_runs(line, syn)
    b = line.encode()
    out = []
    for k in range(0, len(w), 4):
        a, e, col, tone = w[k:k + 4]
        out.append((col, col + len(b[a:e].decode()), code_layer._HL_CLASSES[tone]))
    return out


def _py_runs(runs):
    return [(runs[k], runs[k + 1], runs[k + 2]) for k in range(0, len(runs), 4)]


def _seed_lines():
    lines = ['s = "a\\"b" + \'c\'', 'x = "open', "n = 0x1F + 1.5e3 - .5",
             "a--b # c", "-- lua comment", "#len", "x1y2 = _z_9", "é = 'ü' # ö",
             "", " ", "print(\"\\\\\") -- end", "x = '\\", "a-b-c--d", "def end local and",
             "x = 'é\\é' + \"\\"]
    for p in sorted((ROOT / "system_carts").glob("*.moy/main.*")):
        lines += p.read_text(encoding="utf-8").splitlines()
    return lines


def test_the_runs_are_the_pythons_per_character_scan():
    """Every line of every seed cart's code, in its own language and the
    other, and the edges (escapes, an unclosed string, numbers, either
    comment marker, a name with digits, characters past ASCII): the C's
    runs are the Python highlighter's colours grouped."""
    lines = _seed_lines()
    assert len(lines) > 1000
    for lua in (False, True):
        syn = ui_draw.SYN_LUA if lua else ui_draw.SYN_PYTHON
        for line in lines:
            assert _c_runs(line, syn) == _py_runs(text_twin._highlight_runs(line, lua)), line


def test_the_json_runs_are_the_theme_modes():
    lines = ['{"name": "Moy", "n": -1.5e3, "on": true, "off": false, "x": null}',
             '  "a\\"b" : "c\\\\"', '"open', "[1, 2, -x, nullx, truth]", "", "  ",
             '{"é": "ü"}']
    for p in sorted((ROOT / "native" / "moy_ui" / "themes").glob("*.json")):
        lines += p.read_text(encoding="utf-8").splitlines()
    for line in lines:
        want = text_twin._runs_of(line, text_twin._highlight_json(line))
        assert _c_runs(line, ui_draw.SYN_JSON) == _py_runs(want), line


def test_sgr_escapes_take_no_column():
    w = _C.text_runs("a\x1b[31mred\x1b[0m b\x1b[92mg", ui_draw.SYN_SGR)
    runs = [tuple(w[k:k + 4]) for k in range(0, len(w), 4)]
    # (bytes, column, tone): text, danger, text, string
    assert [(r[2], r[3]) for r in runs] == [(0, 0), (1, 7), (4, 0), (6, 2)]


def test_reverse_video_is_a_bit_of_its_runs_tone():
    """SGR 7 sets a run's reverse bit (moy_ui_text.h's MOY_UI_TONE_REV, bit
    24) over the ink and ground it reverses; 27 and a reset clear it."""
    w = _C.text_runs("a\x1b[7mb\x1b[31mc\x1b[27md\x1b[7;48;5;3me\x1b[0mf", ui_draw.SYN_SGR)
    rev, danger, ground = 1 << 24, 7, 4 << 16
    assert [w[k + 3] for k in range(0, len(w), 4)] == [
        0, rev, rev | danger, danger, rev | danger | ground, 0]


def _md_runs(line):
    """The C's Markdown runs as (text, tone name)."""
    w = _C.text_runs(line, ui_draw.SYN_MARKDOWN)
    b = line.encode()
    names = ("text", "keyword", "string", "number", "comment", "builtin")
    return [(b[w[k]:w[k + 1]].decode(), names[w[k + 3]]) for k in range(0, len(w), 4)]


def test_the_markdown_runs_colour_a_notes_marks():
    """A note's source, coloured as Code colours a program: its marks dim
    (the comment's tone), a heading's words in the number's, a task's open
    box in the keyword's (the seed themes' accent) and a ticked one in the
    string's with its words dim, a link's name in the builtin's (their
    blue). Each run is the line's own, read with nothing past it."""
    want = {
        "## Plan [[x]]": [("##", "comment"), (" Plan [[x]]", "number")],
        "#": [("#", "comment")],
        "#hashtag": [("#hashtag", "text")],
        "####### seven": [("####### seven", "text")],
        "- [ ] buy [[Milk]]": [("- ", "comment"), ("[ ]", "keyword"), (" buy ", "text"),
                               ("[[", "comment"), ("Milk", "builtin"), ("]]", "comment")],
        "  * [x] done **now**": [("  ", "text"), ("* ", "comment"), ("[x]", "string"),
                                 (" done **now**", "comment")],
        "- [X]": [("- ", "comment"), ("[X]", "string")],
        "- [y] odd": [("- ", "comment"), ("[y] odd", "text")],
        "12. step `x = 1` **b**": [("12. ", "comment"), ("step ", "text"), ("`", "comment"),
                                   ("x = 1", "text"), ("`", "comment"), (" ", "text"),
                                   ("**", "comment"), ("b", "text"), ("**", "comment")],
        "> quote - no": [("> ", "comment"), ("quote - no", "text")],
        "---": [("---", "comment")],
        "* * *": [("* * *", "comment")],
        "see [[open": [("see ", "text"), ("[[", "comment"), ("open", "builtin")],
        "a `b": [("a ", "text"), ("`", "comment"), ("b", "text")],
        "é [[ü]]": [("é ", "text"), ("[[", "comment"), ("ü", "builtin"), ("]]", "comment")],
        "-x and 1.5": [("-x and 1.5", "text")],
        "": [],
    }
    for line, runs in want.items():
        assert _md_runs(line) == runs, line
    # a wrapped row's runs are its line's up to the row's end
    line = "- [ ] call [[Ana]] today"
    whole = _md_runs(line)
    for end in range(len(line) + 1):
        part = _md_runs(line[:end])
        got = "".join(t for t, _ in part)
        assert got == line[:end]
        for (t, tone), (wt, wtone) in zip(part[:-1], whole):
            assert (t, tone) == (wt, wtone), line[:end]


def test_a_note_draws_at_15_px_on_the_desk_alone(tmp_path):
    """The note's face (`Appearance.note_font`, a text view's `font`): the
    mono family's 15 px regular on the desk, the mono role's own (0) on the
    handheld; the desk's Code keeps the mono role."""
    desk = _console(tmp_path / "desk", True)
    fid = desk.look.note_font()
    assert fid and fid != ui_draw.font("mono")[0]
    assert ui_draw.font_info(fid)[0] > ui_draw.font("mono")[1]
    names = {v: k[1] for k, v in appearance._FONTS.items()}
    assert names[fid] == "jbmono-15-400-4.fnt"
    assert names[ui_draw.font("mono")[0]] == "jbmono-11-400-2.fnt"
    hand = _console(tmp_path / "hand", False)
    assert hand.look.note_font() == 0


# -- two consoles, one drawing the Python's whole ------------------------------------

def _console(tmp_path, windowed):
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    if windowed:
        ws = host_app.build_workstation(carts, sys_size=(1024, 600), font_scale=1,
                                        windowed=True, panel_diagonal_in=7.0)
    else:
        ws = host_app.build_workstation(carts)
    ws.bar_layer.clock_text = lambda: "10:30"
    no_unlock_banner(ws)
    quiesce(ws)
    ws.pointer.visible = False
    return ws


def _whole(host):
    """`host`'s frames draw whole: it never plans a shift or rows frame."""
    def shift(_cv, _th):
        host.shifting = False
    host._shift = shift


class Pair:
    """The session on both consoles, frame by frame: `a` as it ships, `b`
    drawing the Code tab's rows whole; `a`'s buffers presented in turn."""

    def __init__(self, tmp_path, bufs, windowed):
        self.a = _console(tmp_path / "ships", windowed)
        self.b = _console(tmp_path / "whole", windowed)
        _whole(self.b.code_layer._host)
        _whole(self.b.theme_config_layer._host)
        self.da = host_app.ConsoleDriver(self.a)
        self.db = host_app.ConsoleDriver(self.b)
        self.bufs = bufs
        self.windowed = windowed
        root = self.root(self.a)
        root.RETAINED_FRAMES = bufs
        self.held = [bytes(root._buf)]
        self.kinds = []
        self.n = 0

    @staticmethod
    def root(ws):
        return ws.wm.root_canvas if hasattr(ws.wm, "root_canvas") else ws.sys_canvas

    def frame(self, n=1, force=None):
        # on the desk a board's buffers keep the WM asking for frames the
        # one-buffer twin does not: every frame is painted there
        force = self.windowed if force is None else force
        for _ in range(n):
            for ws, drv in ((self.a, self.da), (self.b, self.db)):
                if force:
                    ws.mark_dirty()
                ws.pointer.visible = False
                k = ws.frame_state.frames_drawn
                ws.code_layer._host.shifting = ws.theme_config_layer._host.shifting = False
                drv.frame(1 / 30)
                ws.painted = ws.frame_state.frames_drawn != k
            a, b = self.a, self.b
            assert a.painted == b.painted, "the two consoles' gates parted"
            if not a.painted:
                continue
            self.n += 1
            self.kinds.append(a.code_layer._host.shifting or a.theme_config_layer._host.shifting)
            ra = self.root(a)
            shot, want = bytes(ra._buf), bytes(self.root(b)._buf)
            if shot != want:
                w = ra.w
                at = next(i for i in range(0, len(shot), 2) if shot[i:i + 2] != want[i:i + 2]) // 2
                raise AssertionError("frame %d (%s, %d buffers) differs from a whole draw at "
                                     "(%d, %d)" % (self.n, self.kinds[-1], self.bufs,
                                                   at % w, at // w))
            self.held.append(shot)
            if self.bufs > 1:
                ra._comp.last = shot
                ra._buf[:] = self.held[-self.bufs] if len(self.held) > self.bufs else self.held[0]
            del self.held[:-self.bufs]

    def both(self, verb, *args):
        getattr(self.da, verb)(*args)
        getattr(self.db, verb)(*args)

    def run(self, code):
        for ws in (self.a, self.b):
            exec(code, {"ws": ws})
            ws.mark_dirty()

    def type(self, text, frames=2):
        for ch in text:
            self.key(ord(ch), frames)

    def key(self, code, frames=2, mods=0):
        self.both("key_down", code, mods)
        self.frame()
        self.both("key_up", code, mods)
        self.frame(frames - 1)

    def held_key(self, code, frames=24, mods=0):
        self.both("key_down", code, mods)
        self.frame(frames)
        self.both("key_up", code, mods)
        self.frame(2)

    def floors(self):
        return sum(1 for k in self.kinds if k)


_BS = 8
_ENTER = 13
_ESC = 27


def _code(p, title="Star Catcher"):
    p.run("ws.open_in_editor([c for c in ws.carts.all if c.get('title') == %r][0])\n"
          "ws.editor_app.set_tab('code')\n"
          "_d = ws.editor_desk\n"
          "if _d is not None and _d.active():\n"
          "    [_d.focus_pane(n) for n, (pane, _r, _p) in enumerate(_d.panes()) if 'code' in pane]"
          % title)
    p.frame(6, force=True)


def _fling(p):
    """A finger dragged up the code and let go: the view follows it by
    pixels and coasts on after the release; a key brings the caret back."""
    a = p.a.editor
    lay = p.a.code_layout
    x, y = lay.x0 + 60, lay.y0 + 8 * lay.lh
    top = a.top
    p.both("touch", x, y)
    p.frame()
    for k in range(1, 7):
        p.both("touch_drag", x, y - k * lay.lh)
        p.frame()
    p.both("touch_up")
    p.frame()
    let_go = a.top
    assert let_go > top, "the drag did not scroll the code"
    p.frame(4)
    assert a.top > let_go, "the release did not coast"
    p.frame(40)
    p.key(moy_input.KEY_DOWN)                   # the caret, out of view, brings it back


def _session(p):
    """Typing, caret moves, a held key, a selection and a paste, a long
    line scrolled across, find past the view, completion and the crash
    popover, a gutter growing past 99 and 999 lines, a theme change."""
    _code(p)
    a, b = p.a.editor, p.b.editor
    p.type("x = 1")
    p.key(_ENTER)
    p.type("# a comment")
    p.key(moy_input.KEY_UP)
    p.key(moy_input.KEY_LEFT)
    p.held_key(moy_input.KEY_DOWN, 30)          # a held key: the view scrolls
    p.held_key(moy_input.KEY_UP, 12)
    if not p.windowed:
        _fling(p)                               # a drag scrolls, its release coasts
    p.held_key(_BS, 10)                         # Backspace held
    p.key(moy_input.KEY_DOWN, mods=moy_input.SHIFT)     # a selection
    p.key(moy_input.KEY_DOWN, mods=moy_input.SHIFT)
    p.key(0x03)                                 # copy
    p.key(moy_input.KEY_RIGHT)
    p.key(0x16)                                 # paste
    p.type("long = '" + "abcdefghij" * 8 + "'")     # past the view: it scrolls across
    p.held_key(moy_input.KEY_LEFT, 40)
    p.key(_ENTER)
    p.key(0x06)                                 # find
    p.type("coin")
    for _ in range(6):
        p.key(_ENTER)                           # next, past the view
    p.key(_ESC)
    p.type("pr")
    p.key(0x05)                                 # completion over the rows
    p.key(moy_input.KEY_DOWN)
    p.type("i")                                 # (the completion closes as it types)
    p.run("ws.code_err_row = ws.editor.row; ws.code_err = 'NameError: x'\n"
          "ws.crash_popup = 'NameError: x is not defined'")
    p.frame(3)
    p.key(_ESC)
    p.run("ws.code_err_row = None; ws.code_err = None")
    p.frame(2)
    p.run("ws.look.set_theme('moy', persist=False, variant='light')")
    p.frame(3)
    p.type("y")
    assert a.lines == b.lines and (a.row, a.col, a.top, a.left) == (b.row, b.col, b.top, b.left)


def _gutter_session(p):
    """The gutter grows past 99 and 999 lines: the frames it widens draw
    whole, the rows between them as rows."""
    _code(p)
    p.run("ws.editor.set_text('\\n'.join('v%d = %d' % (i, i) for i in range(96)))\n"
          "ws.editor.row = 95")
    p.frame(3)
    for _ in range(6):
        p.key(_ENTER)
    p.run("ws.editor.set_text('\\n'.join('v%d = %d' % (i, i) for i in range(996)))\n"
          "ws.editor.row = 995; ws.editor._scroll()")
    p.frame(3)
    for _ in range(6):
        p.key(_ENTER)
    assert p.a.editor.lines == p.b.editor.lines


@pytest.mark.parametrize("bufs", (1, 2, 3))
@pytest.mark.parametrize("windowed", (False, True))
def test_the_code_tab_draws_the_pythons_pixels(tmp_path, bufs, windowed):
    p = Pair(tmp_path, bufs, windowed)
    _session(p)
    assert p.floors() >= 0.6 * len(p.kinds), p.kinds


@pytest.mark.parametrize("windowed", (False, True))
def test_a_key_step_past_the_foot_lands_as_one_shift(tmp_path, windowed):
    """The editor's top, moved by a key past the view's foot, lands in the
    key's own frame as a shift (`ui_draw.text_aim` before the
    frame begins): no glide frames follow it, and it draws the Python's
    pixels."""
    p = Pair(tmp_path, 2, windowed)
    _code(p)
    a = p.a.editor
    p.run("ws.editor.row = ws.editor.top + ws.editor.ROWS - 1; ws.mark_dirty()")
    p.frame(4)
    top = a.top
    p.both("key_down", moy_input.KEY_DOWN, 0)
    p.frame()
    landed = a.top
    assert landed > top, "the key's frame did not show the caret's line"
    assert p.kinds[-1], "the key's frame drew whole"
    assert p.a.code_layer._host.still(), "the view glides on after the key"
    p.both("key_up", moy_input.KEY_DOWN, 0)
    p.frame(2)
    assert a.top == landed


def test_a_held_keys_steps_draw_each_row_once(tmp_path):
    """A held key's steps past the foot: each frame's floor is the row the
    move uncovered and the rows the caret left and entered, in touching
    pieces. The view grounds them under one fill and lays out a row that
    crosses from one piece into the next once (it was a row twice and a
    page ground under the view's own: 16 fills and up to 21 texts a frame).
    A dearer step needs a reason before this budget moves."""
    p = Pair(tmp_path, 1, False)
    _code(p)
    p.run("ws.editor.row = ws.editor.top + ws.editor.ROWS - 1; ws.mark_dirty()")
    p.frame(4)
    cv = p.root(p.a)
    got = []
    for _ in range(10):
        cv.gate_counts_reset()
        p.both("key_down", moy_input.KEY_DOWN, 0)
        p.frame()
        assert p.kinds[-1], "the step's frame drew whole"
        got.append(tuple(cv.gate_counts()[:2]))
        p.both("key_up", moy_input.KEY_DOWN, 0)
        p.frame()
    budget = [(9, 10), (9, 14), (9, 14), (9, 16), (9, 16), (9, 14), (9, 12), (9, 10), (9, 10),
              (9, 9)]
    over = [(i, g, b) for i, (g, b) in enumerate(zip(got, budget)) if g[0] > b[0] or g[1] > b[1]]
    assert not over, "steps drew more (fills, texts) than their budget: %r" % (over,)


@pytest.mark.parametrize("bufs", (2, 3))
def test_a_whole_frame_mid_drag_leaves_each_buffer_one_catch_up(tmp_path, bufs):
    """On the desk, a frame that draws the Editor whole mid-drag (here the
    pane's own key moved) leaves the buffers behind it lagging the whole
    desk. Each catches up in a whole frame that changed the pane alone, and
    the pane's frames are its own again: one whole frame never becomes a
    gesture of them. The code moves its rows on every frame after the one
    whose key moved, the catch-ups too."""
    p = Pair(tmp_path, bufs, True)
    _code(p)
    d = p.a.editor_desk
    whole = []
    draw = d._draw

    def counted(dt):
        whole.append(p.n)
        draw(dt)
    d._draw = counted
    cx, cy, cw, ch = p.a.wm.windows["menu"].content_rect()
    x, y = cx + cw // 5, cy + 3 * ch // 5
    p.both("touch", x, y)
    p.frame()
    p.both("touch_drag", x, y - 20)
    p.frame()
    del whole[:]
    d._surround = p.b.editor_desk._surround = None
    n = len(p.kinds)
    for k in range(2, 14):
        p.both("touch_drag", x, y - 20 * k)
        p.frame()
    assert whole == list(range(n, n + bufs)), whole
    assert not p.kinds[n] and all(p.kinds[n + 1:]), p.kinds[n:]


@pytest.mark.parametrize("bufs", (1, 2, 3))
def test_the_gutter_widening_draws_whole(tmp_path, bufs):
    p = Pair(tmp_path, bufs, False)
    _gutter_session(p)
    assert p.floors() >= 8, p.kinds


def _config_session(p):
    """theme Config: typing, the caret moving through the JSON, a held key
    scrolling it, Backspace held."""
    p.run("ws.spine.open_app(ws.app('appearance'))")
    p.frame(3)
    p.run("assert ws.look.edit_file()")
    p.frame(4)
    assert p.a.menu_view == "theme_config"
    p.held_key(moy_input.KEY_DOWN, 30)
    p.type('"x": 1,')
    p.key(_ENTER)
    p.held_key(moy_input.KEY_UP, 10)
    p.held_key(_BS, 6)
    p.type("ab")
    assert p.a.editor.lines == p.b.editor.lines


@pytest.mark.parametrize("bufs", (1, 2, 3))
@pytest.mark.parametrize("windowed", (False, True))
def test_theme_config_draws_the_pythons_pixels(tmp_path, bufs, windowed):
    p = Pair(tmp_path, bufs, windowed)
    _config_session(p)
    assert p.floors() >= 0.6 * len(p.kinds), p.kinds
