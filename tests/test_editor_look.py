"""The Editor's tabs and the desk apps as the glass shows them, under every
seed theme and mode, on the shell the goldens build (`tests/test_shell_goldens.py`'s
configs and pinning): the measurements a design review takes off a render,
taken here off the same frame."""

import pytest

import test_shell_goldens as g

THEMES = [("moy", "dark"), ("moy", "light"), ("blocks", "light"),
          ("contrast", "dark"), ("contrast", "light")]
HANDHELD = "tdeck_320x240_fs1_dark"
DESK = "p4_1024x600_cs2_fs1_windowed"
# The Code tab's caret, the targets' (tools/look_shots.py's `_code`): line 42,
# column 13, line 34 the first shown.
CODE_TOP, CODE_ROW, CODE_COL = 33, 41, 12


@pytest.fixture(autouse=True)
def _uninstall():
    yield
    import moy_ui
    from runtime import iconsets, ui_draw
    moy_ui.theme_uninstall()
    iconsets.reset()
    ui_draw.input_kind("keys")


def _ws(tmp_path, config, theme, mode):
    import moy_ui
    moy_ui.theme_uninstall()
    cfg = dict(g.CONFIGS[config], variant=mode)
    if "layout" not in cfg:
        cfg["theme"] = theme
    return g._build(cfg, tmp_path / "carts")


def _frame(ws, n=4):
    for _ in range(n):
        g._quiesce(ws)
        ws.mark_dirty()
        ws.frame(g._DT)


def _px(ws):
    """The glass as rows of (r, g, b)."""
    cv = ws.glass_canvas
    buf = cv._buf
    out = []
    for y in range(cv.h):
        row = []
        for x in range(cv.w):
            i = (y * cv.w + x) * 2
            v = (buf[i] << 8) | buf[i + 1]
            row.append(((v >> 11) & 31, (v >> 5) & 63, v & 31))
        out.append(row)
    return out


def _rgb(cv, colour):
    """Colour index (or role value) `colour` as `_px` reads it: the canvas
    word is the glass's big-endian RGB565 read as a native one."""
    w = cv._col(colour)
    v = ((w & 0xFF) << 8) | (w >> 8)
    return ((v >> 11) & 31, (v >> 5) & 63, v & 31)


def _ink_left(px, x0, x1, y0, y1, ground=None):
    """The first column in [x0, x1) where a row of [y0, y1) leaves its ground
    (the row's pixel at x0, or `ground`), or None."""
    for x in range(x0, x1):
        for y in range(y0, y1):
            if px[y][x] != (px[y][x0] if ground is None else ground):
                return x
    return None


def _editor(ws, tab):
    """The handheld Editor on Star Catcher's `tab`: its CodeLayout and the
    glass origin of its content (0, 0)."""
    ws.open_in_editor(g._cart_by_title(ws, "Star Catcher"))
    ws.text.set_menu_view(tab)
    if tab == "code":
        ed = ws.editor
        ed.row, ed.col, ed.top = CODE_ROW, CODE_COL, CODE_TOP
    _frame(ws)
    return ws.code_layout, 0, 0


@pytest.mark.parametrize("theme,mode", THEMES)
def test_the_code_tab_keeps_one_left_inset(tmp_path, theme, mode):
    """The code, the status line and the symbol keys start on one column
    at least 8 px in from the content's left edge, and the current line's mark stands inside that inset, clear of
    the frame (design review R3-10)."""
    from runtime import ui_draw
    ws = _ws(tmp_path, HANDHELD, theme, mode)
    ui_draw.input_kind("touch")              # the symbol keys show after touch (D-17)
    lay, ox, oy = _editor(ws, "code")
    ed = ws.editor
    fs = lay.fs
    cl = ws.code_layer
    rect, top, cell, lh, tx0 = cl.view()
    x0 = lay.cx + 8 * fs                     # the page's text column
    assert lay.symbols and cl.s.touch
    px = _px(ws)
    # An unindented line that is not the current one: its line number
    # ends a cell before the code, which starts on the text column, each
    # glyph's bearing at most fs in; the widest number starts on x0.
    other = next(i for i in range(rect[3] // lh) if ed.top + i != ed.row
                 and ed.lines[ed.top + i][:1].isalpha())
    y = oy + rect[1] + other * lh
    gc = (tx0 - x0) // cell
    assert gc and tx0 == x0 + gc * cell
    num = _ink_left(px, ox + lay.cx + 1, ox + lay.cx + lay.cw, y, y + lh)
    digits = len(str(ed.top + other + 1))
    at = x0 + (gc - 1 - digits) * cell
    assert at <= num - ox <= at + fs, ("number", num - ox, at)
    code = _ink_left(px, ox + tx0 - cell // 2, ox + lay.cx + lay.cw, y, y + lh)
    assert tx0 <= code - ox <= tx0 + fs, ("code", code - ox, tx0)
    sx, sy, _sw, sh = cl.page.rect_of("status_row")
    status = _ink_left(px, ox + sx + 1, ox + sx + 200, oy + sy + 1, oy + sy + sh)
    assert x0 <= status - ox <= x0 + fs, ("status", status - ox, x0)
    # The symbol keys: the first key's edge on x0, the last one's on the
    # inset from the right; a tap anywhere on a key is that key.
    kx, ky0, kw, kh = cl.page.rect_of("symbols")
    n = len(cl._symbols())
    ins = x0 - lay.cx - fs
    span = kw - 2 * ins
    for i in range(n):
        assert cl.symbol_at(ins + i * span // n) == i
        assert cl.symbol_at(ins + (i + 1) * span // n - 1) == i
    ky = oy + ky0 + kh // 2
    # (the strip is a canvas part, its ground a card whose edge a light
    # look draws: the probe starts inside it)
    key = _ink_left(px, ox + lay.cx + 3 * fs, ox + lay.cx + lay.cw, ky, ky + 1)
    assert key - ox == x0, ("keys", key - ox, x0)
    # The current line's mark: inside the inset, 3 px or more off the frame.
    assert lay.cx + 3 * fs <= lay.mark_x and lay.mark_x + 2 * fs < x0
    cy = oy + lay.y0 + (ed.row - ed.top) * lay.lh + lay.lh // 2
    mark = _ink_left(px, ox + lay.cx, ox + x0, cy, cy + 1)
    assert mark - ox == lay.mark_x, ("mark", mark - ox, lay.mark_x)


@pytest.mark.parametrize("theme,mode", THEMES)
def test_the_caret_stands_a_column_off_the_next_stem(tmp_path, theme, mode):
    """The caret before "b" (the targets' caret, line 42 column 13) is one
    column wide and a ground column stands between it and the stem, so the
    stem does not read as bold (design review R3-24)."""
    ws = _ws(tmp_path, HANDHELD, theme, mode)
    lay, ox, oy = _editor(ws, "code")
    ed = ws.editor
    assert ed.lines[ed.row][ed.col] == "b"
    fs = lay.fs
    cv = ws.glass_canvas
    px = _px(ws)
    caret = _rgb(cv, ws.theme_colors["ink_accent"])     # the text view's caret
    rect, _top, cell, lh, tx0 = ws.code_layer.view()
    y = oy + rect[1] + (ed.row - ed.top) * lh
    x = tx0 + (ed.col - ed.left) * cell
    cols = [c for c in range(x - lay.cell, x + lay.cell)
            if all(px[yy][c] == caret for yy in range(y + fs, y + lay.text_h - fs))]
    assert len(cols) == fs, cols
    ground = px[y + lay.text_h // 2][cols[-1] + 1]
    stem = next(c for c in range(cols[-1] + 1, x + lay.cell)
                if any(px[yy][c] != ground for yy in range(y + fs, y + lay.text_h - fs)))
    assert stem - cols[-1] >= 2, (cols, stem)


@pytest.mark.parametrize("theme,mode", THEMES)
def test_play_carries_as_much_full_ink_as_a_tab_icon(tmp_path, theme, mode):
    """The narrow bar's Play, drawn in one ink beside the tab icons, has at
    least as many pixels of that full ink as the lightest tab icon: its 16 px
    mask's diagonals no longer antialias it to a grey the tabs do not wear,
    which Contrast reads as disabled (design review R3-26)."""
    from runtime.bar_layer import SET_KIND as _SET_KIND
    from runtime.editor_app import ZONE_ITEMS
    ws = _ws(tmp_path, HANDHELD, theme, mode)
    _editor(ws, "code")
    cv, th = ws.sys_canvas, ws.theme_colors
    ink = th["chrome_ink"]
    word = cv._col(ink)

    def full(draw):
        cv.rect(0, 0, 32, 32, th["surface"])
        draw((8, 8, 16, 16))
        n = 0
        for y in range(32):
            for x in range(32):
                i = (y * cv._stride + x) * 2
                n += (cv._buf[i] | (cv._buf[i + 1] << 8)) == word
        return n

    tabs = [full(lambda r, k=k: ws.draw_icon(_SET_KIND.get(k, k), r, ink, cv))
            for t, k in ZONE_ITEMS if isinstance(t, str) and not t.startswith("\x00")]
    play = full(lambda r: ws.editor_app.bar_zone.look._draw_play(cv, r, ink))
    assert play >= min(tabs), (play, tabs)
    bare = full(lambda r: ws.draw_icon("play", r, ink, cv))
    assert bare < min(tabs), ("the set's 16 px play carries full ink of its own now: "
                              "ZoneLook._draw_play's second pass can go", bare, tabs)


def _sprites(ws):
    """The handheld Sprites tab, as the targets show it (tools/look_shots.py's
    `_sprites`): its PaintLayout."""
    ws.open_in_editor(g._cart_by_title(ws, "Star Catcher"))
    ws.text.set_menu_view("paint")
    _frame(ws)
    return ws.paint_layer.layout


@pytest.mark.parametrize("theme,mode", THEMES)
def test_every_enabled_sprite_tool_wears_the_chrome_ink(tmp_path, theme, mode):
    """The sprite tools' icons take one ink role, the chrome's: no tool in
    the dim ink and no trash in the danger ink, louder than its row (design
    review R3-11). The tool in use wears the current mark; copy and paste,
    with nothing to copy or paste, the disabled ink."""
    from runtime import paint_layer, ui_draw
    ws = _ws(tmp_path, HANDHELD, theme, mode)
    lay = _sprites(ws)
    th = ws.theme_colors
    cv = ws.glass_canvas
    px = _px(ws)
    ink = _rgb(cv, th["chrome_ink"])
    others = {_rgb(cv, th[r]) for r in ("ink_dim", "chrome_ink_dim")}
    others.add(_rgb(cv, ui_draw.button_ink(th, "danger")))
    others.discard(ink)
    pe = ws.paint
    for tid, (x, y, w, h) in zip(paint_layer._TOOLS, lay.tool_btns):
        if tid == "stamp" or ws.paint_layer._tool_on(pe, tid):
            continue
        seen = {px[yy][xx] for yy in range(y, y + h) for xx in range(x, x + w)}
        assert ink in seen, tid
        assert not (seen & others), (tid, seen & others)


@pytest.mark.parametrize("theme,mode", THEMES)
def test_the_sprite_tool_row_keeps_the_mockups_spacing(tmp_path, theme, mode):
    """The one tool row (owner, 2026-10-19) stands at the mockup's pitch,
    24 px on the handheld, from the grid's left edge under the grid or
    from the column's at its head."""
    from runtime import paint_layer
    ws = _ws(tmp_path, HANDHELD, theme, mode)
    lay = _sprites(ws)
    row = lay.tool_btns
    assert len(row) == len(paint_layer._TOOL_ROW)
    assert {b[0] - a[0] for a, b in zip(row, row[1:])} == {24 * lay.fs}
    assert row[0][0] in (lay.pg_x0, lay.spr_prev[0])


@pytest.mark.parametrize("app_id", ("appearance", "calc"))
@pytest.mark.parametrize("theme,mode", THEMES)
def test_under_touch_a_handheld_app_keeps_no_hint_band(tmp_path, app_id, theme, mode):
    """Touch draws no keycaps, so Appearance and Calc on the handheld keep no
    empty band for them: the content's last 20 rows hold the page (design
    review R3-07); a key input brings the hints back."""
    ws = _ws(tmp_path, HANDHELD, theme, mode)
    ws.use_inputs([("local", "touch")])
    ws.spine.open_app(ws.app(app_id))
    _frame(ws)
    lay = ws.layout
    px = _px(ws)
    band = {px[y][x] for y in range(lay.cy + lay.ch - 20, lay.cy + lay.ch)
            for x in range(lay.cx, lay.cx + lay.cw)}
    assert len(band) > 1, "an empty band under touch"
    ws.use_inputs([("local", "keys")])
    _frame(ws)
    px = _px(ws)
    band = {px[y][x] for y in range(lay.cy + lay.ch - 20, lay.cy + lay.ch)
            for x in range(lay.cx, lay.cx + lay.cw)}
    assert len(band) > 1, "no hints under keys"
