"""The Sprites tab as the glass shows it, under every seed theme and mode, on
the shell the goldens build: the marks a design review reads off a render
(the selection, the sprite map's current sprite, the grid's cursor), taken
here off the same frame (`tests/test_editor_look.py`'s fixtures)."""

import pytest
from ws_helpers import paint_grid_at  # noqa: E402

import test_editor_look as el
from test_editor_look import DESK, HANDHELD, THEMES

_uninstall = el._uninstall            # the theme and input put back after each


def _rgb8(p):
    """A `_px` pixel (5/6/5 bits) as 8-bit RGB."""
    return (p[0] * 255 // 31, p[1] * 255 // 63, p[2] * 255 // 31)


def _contrast(a, b):
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def lum(c):
        return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])
    hi, lo = sorted((lum(_rgb8(a)), lum(_rgb8(b))), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _open(tmp_path, config, theme, mode):
    """The Sprites tab: the handheld's, or the desk Editor's Sprite pane in
    the Art workspace. (ws, its PaintLayer, the glass origin of its
    surface)."""
    ws = el._ws(tmp_path, config, theme, mode)
    if config == HANDHELD:
        return ws, el._sprites(ws), 0, 0
    ws.home.open_desk()
    ws.open_in_editor(el.g._cart_by_title(ws, "Star Catcher"))
    ws.text.set_menu_view("paint")
    el._frame(ws)
    d = ws.editor_desk
    pane, r, _p = next(p for p in d.panes() if "paint" in p[0])
    body = d._body(r, d._unit(), pane)
    ox, oy = d._origin()
    return ws, ws.paint_layer, ox + body[0], oy + body[1]


@pytest.mark.parametrize("theme,mode", THEMES)
def test_the_selection_reads_against_the_grid_lines(tmp_path, theme, mode):
    """The selection is a two-toned ring, `ink` on and outside its grid
    lines and `surface` within: one of the two stands at 3:1 or more off
    the grid's lines in every theme-mode (design review R4-02; Contrast
    Night's lines are its ink, Moy Day's and Blocks' a hair from white)."""
    ws, pl, ox, oy = _open(tmp_path, HANDHELD, theme, mode)
    ws.paint.set_selection(1, 1, 4, 4)
    el._frame(ws)
    px = el._px(ws)
    cv = ws.glass_canvas
    border = el._rgb(cv, ws.theme_colors["border"])
    gx, gy = paint_grid_at(pl)
    cell = pl.layout.span // ws.paint.dim
    x0 = ox + gx + cell                 # the selection's first column
    ys = range(oy + gy + 2 * cell, oy + gy + 4 * cell)
    outer = {px[y][x0 - 1] for y in ys}
    inner = {px[y][x0] for y in ys}
    assert outer == {el._rgb(cv, ws.theme_colors["ink"])}, outer
    assert inner == {el._rgb(cv, ws.theme_colors["surface"])}, inner
    best = max(_contrast(c, border) for c in outer | inner)
    assert best >= 3, (theme, mode, best)


@pytest.mark.parametrize("theme,mode", THEMES)
def test_the_maps_mark_leaves_the_sprite_whole(tmp_path, theme, mode):
    """The sprite map's mark lies outside the sprite -- `surface` around
    it, then `ink` -- so every pixel of the sprite shows as the sheet holds
    it (design review R4-03: the inner line used to cover its edge)."""
    ws, pl, ox, oy = _open(tmp_path, HANDHELD, theme, mode)
    pe = ws.paint
    sheet = pe.sheet
    mx, my, mw, mh = pl.rect_of("map")
    o = pl._map_ring()
    k, first, rows = pl._map_geom(pe, sheet, mw, mh)
    tile = sheet.TILE * k
    sx = ox + mx + 2 * o + (pe.n % sheet.cols) * tile
    sy = oy + my + 2 * o + (pe.n // sheet.cols - first) * tile
    px = el._px(ws)
    cv = ws.glass_canvas
    tx, ty = sheet.tile_origin(pe.n)
    inked = 0
    for y in range(sheet.TILE):
        for x in range(sheet.TILE):
            v = sheet.pget(tx + x, ty + y)
            if not v:
                continue
            inked += 1
            want = el._rgb(cv, v)
            for yy in range(k):
                for xx in range(k):
                    assert px[sy + y * k + yy][sx + x * k + xx] == want, (x, y)
    assert inked
    mid = sy + tile // 2
    th = ws.theme_colors
    assert px[mid][sx - 1] == el._rgb(cv, th["surface"])
    assert px[mid][sx - o - 1] == el._rgb(cv, th["ink"])
    assert px[mid][sx + tile + o] == el._rgb(cv, th["ink"])


def test_the_map_stands_beside_the_palette(tmp_path):
    """The map takes the room right of the palette, from the grid's top
    to its foot."""
    ws, pl, _ox, _oy = _open(tmp_path, HANDHELD, "moy", "light")
    m, p, g = pl.rect_of("map"), pl.rect_of("color"), pl.rect_of("grid")
    assert m[0] >= p[0] + p[2] and m[1] == g[1] and m[3] == g[3]


def test_the_tool_row_and_the_file_buttons_share_the_foot(tmp_path):
    """Under the grid (the handheld), the tool row and the file buttons
    share one line (design review R4-17), centred on it."""
    ws, pl, _ox, _oy = _open(tmp_path, HANDHELD, "moy", "light")
    mids = {r[1] + r[3] // 2 for r in (pl.rect_of(k) for k in ("pen", "more", "load", "files"))}
    assert max(mids) - min(mids) <= 1, mids


@pytest.mark.parametrize("theme,mode", THEMES)
def test_the_head_names_the_sprite_and_its_size(tmp_path, theme, mode):
    """"Sprite N" heads the tab and ‹ n › and "Size" stand at its end
    (D-10's "‹ value ›", design review R4-18), the number in the ink."""
    ws, pl, ox, oy = _open(tmp_path, HANDHELD, theme, mode)
    hx, hy, hw, hh = pl.rect_of("head")
    sx = pl.rect_of("pickers")[0]
    assert sx > hx + hw // 2
    px = el._px(ws)
    ink = el._rgb(ws.glass_canvas, ws.theme_colors["ink"])
    seen = {px[oy + y][ox + x] for y in range(hy, hy + hh) for x in range(hx + hw // 2, sx)}
    assert ink in seen


def test_the_grid_cursor_is_drawn_for_keys_and_not_for_touch(tmp_path):
    """The grid's cursor is a key's: under touch it is gone (design review
    R4-19), and a key's move brings it back."""
    from runtime import ui_draw
    ws, pl, ox, oy = _open(tmp_path, HANDHELD, "moy", "light")
    cv = ws.glass_canvas
    keyline = el._rgb(cv, ws.look.live.fixed[2])
    border = el._rgb(cv, ws.theme_colors["border"])
    pl._cur[:] = [0, 0]
    # the cursor cell's left line, the grid's own left edge: where it stands
    # in either layout (touch has no band, and so another grid margin)
    el._frame(ws)
    gx, gy = paint_grid_at(pl)
    assert el._px(ws)[oy + gy + 3][ox + gx - 1] == keyline
    ui_draw.input_kind("touch")
    el._frame(ws)
    el._frame(ws)
    gx, gy = paint_grid_at(pl)
    assert el._px(ws)[oy + gy + 3][ox + gx - 1] == border


def test_while_a_popover_is_open_the_band_shows_only_its_close(tmp_path):
    """The band shows the operations' keys, and while the more menu is open
    only what Enter picks and the key that closes it (design review R4-13),
    never keys the menu has taken."""
    ws, pl, _ox, _oy = _open(tmp_path, HANDHELD, "moy", "light")
    band = pl.page.hints()
    assert "Flip" in band and "Close" not in band
    pl._open_more()
    el._frame(ws)
    band = pl.page.hints()
    assert band[-2:] == ("back", "Close") and "Flip" not in band, band


def _key_ink_h(px, box, ox, oy, w):
    """The ink height of what a menu row draws in its key column, the last
    `w` pixels of its box: rows holding a pixel 3:1 off the column's ground."""
    x, y, bw, bh = box
    cols = range(ox + x + bw - w, ox + x + bw)
    hist = {}
    for yy in range(oy + y, oy + y + bh):
        for xx in cols:
            hist[px[yy][xx]] = hist.get(px[yy][xx], 0) + 1
    ground = max(hist, key=hist.get)
    rows = [yy for yy in range(oy + y, oy + y + bh)
            if any(_contrast(px[yy][xx], ground) >= 3 for xx in cols)]
    return rows[-1] - rows[0] + 1 if rows else 0


@pytest.mark.parametrize("theme,mode", THEMES)
def test_the_more_menus_arrow_keys_stand_as_tall_as_its_letters(tmp_path, theme, mode):
    """The desk Sprite pane's more menu's key column draws the shifts' arrows as tall as
    the letters beside them, "F" (design review R5-09), not as specks half
    their height."""
    from runtime import paint_layer, editor_sprite, ui_draw
    ws, pl, ox, oy = _open(tmp_path, DESK, theme, mode)
    ui_draw.input_kind("keys")
    ws.paint.set_selection(1, 1, 4, 4)
    pl._open_more()
    el._frame(ws)
    el._frame(ws)
    px = el._px(ws)
    keys = paint_layer._OP_KEYS["keys"]
    rows = {a: word + "\t" + keys[a] for a, word, _i in editor_sprite.OPS if a in keys}
    host = pl._host
    w = 24
    letter = _key_ink_h(px, host.box(rows["fliph"]), ox, oy, w)
    assert letter > 0
    # a row the menu's cut peeks under its fade is the fade's measure
    # (tests/test_system_menu.py), not its key's
    card = host.box("more_pop")
    fade = card[1] + card[3] - ui_draw.metrics("value_row")[29] - 10 * ws.layout.fs
    shown = [op for op in ("sleft", "sright", "sup", "sdown")
             if host.box(rows[op])[1] + host.box(rows[op])[3] <= fade]
    assert len(shown) >= 3, shown
    for op in shown:
        got = _key_ink_h(px, host.box(rows[op]), ox, oy, w)
        assert got >= 0.8 * letter, "%s %s: %s's arrow %d px against F's %d" % (
            theme, mode, op, got, letter)
