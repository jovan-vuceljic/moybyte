"""The pointer families' art: a pointer of each shape in each family, drawn as a
few layers of coverage that tools/make_icons.py packs into one font file a
family and size (`ptr-<family>-<size>.fnt`).

A family draws its shapes in its icon set's style: PIXEL 1-bit art with an
outline, DEFAULT a slim modern arrow and a clean hand, COAST rounded, LUNA
its fill colour as an accent inside a white rim, PLAYFUL chunky and round
with a thick dark outline, a cartoon glove and a star for busy. Every shape
has the three layers of LAYERS, drawn in that order, each in its family's
colour for it (runtime/toolkit/pointers.py): the outline (the silhouette,
under the rest), the fill and the accent. A layer a shape lacks is empty. A
smooth family's soft shadow is its outline again, drawn translucent a pixel
down and right of it.

The smooth families are SVG on a 32-unit cell (one unit a pixel at 32 px,
the 2x size), rasterised by resvg at each size: the body's parts, grown by
the family's outline for the silhouette and by its rounding for the body
itself; `cut` lines that part the fill (a hand's fingers), `accent` parts
inside the body, `marks` drawn with the outline alone. PIXEL is 16x16 art
whose `F` cells are the fill, `A` the accent, `O` the outline, and every
clear cell beside a filled one outline too; its larger sizes are its cells
grown whole.

Each shape's hotspot is exact at every size: a smooth family's is in even
units, so it falls on a whole pixel at 16, 32 and 48.

  render(family, shape, size) -> (hx, hy, w, h, {layer: alpha bytes})
"""

FAMILIES = ("pixel", "default", "coast", "luna", "playful")
SHAPES = ("arrow", "hand", "text", "ew", "ns", "nwse", "nesw", "move", "busy")
LAYERS = ("line", "fill", "accent")
CELL = 32                   # the smooth families' units a cell
PAD = 8                     # units around the cell a raster keeps for the outline

# How each smooth family draws its parts, in units: the outline outside the
# body (`ow`), the body's corner rounding (`round`), the joins, and the
# white rim between outline and an accent body (`rim`, LUNA's).
STYLES = {
    "default": {"ow": 2, "round": 0, "join": "miter"},
    "coast": {"ow": 2, "round": 1.5, "join": "round"},
    "luna": {"ow": 2, "round": 0, "join": "round", "rim": 2},
    "playful": {"ow": 4, "round": 2, "join": "round"},
}


def _f(v):
    return ("%.3f" % v).rstrip("0").rstrip(".")


def _poly(pts):
    return '<path d="M%s Z"/>' % " L".join("%s %s" % (_f(x), _f(y)) for x, y in pts)


def _rect(x, y, w, h, r=0, rot=None):
    t = ' transform="rotate(%s %s %s)"' % (_f(rot[0]), _f(rot[1]), _f(rot[2])) if rot else ""
    return '<rect x="%s" y="%s" width="%s" height="%s" rx="%s"%s/>' % (
        _f(x), _f(y), _f(w), _f(h), _f(r), t)


def _circle(cx, cy, r):
    return '<circle cx="%s" cy="%s" r="%s"/>' % (_f(cx), _f(cy), _f(r))


def _line(x0, y0, x1, y1, w):
    return ('<path d="M%s %s L%s %s" fill="none" stroke-width="%s" stroke-linecap="round"/>'
            % (_f(x0), _f(y0), _f(x1), _f(y1), _f(w)))


def _ring(cx, cy, r0, r1):
    """An annulus, as one path of two circles (even-odd)."""
    def circ(r):
        return "M%s %s a%s %s 0 1 0 %s 0 a%s %s 0 1 0 %s 0" % (
            _f(cx - r), _f(cy), _f(r), _f(r), _f(2 * r), _f(r), _f(r), _f(-2 * r))
    return '<path fill-rule="evenodd" d="%s %s"/>' % (circ(r1), circ(r0))


def _arc(cx, cy, r, a0, a1, w):
    """An arc's stroke from angle a0 to a1 (degrees, clockwise from east)."""
    import math
    x0, y0 = cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0))
    x1, y1 = cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1))
    big = 1 if (a1 - a0) % 360 > 180 else 0
    return ('<path d="M%s %s A%s %s 0 %d 1 %s %s" fill="none" stroke-width="%s" '
            'stroke-linecap="round"/>' % (_f(x0), _f(y0), _f(r), _f(r), big, _f(x1), _f(y1),
                                          _f(w)))


def _wedge(cx, cy, r0, r1, a0, a1):
    """A ring's sector from a0 to a1 (degrees, clockwise from east)."""
    import math
    def at(r, a):
        return cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))
    (ax, ay), (bx, by) = at(r1, a0), at(r1, a1)
    (cx1, cy1), (dx, dy) = at(r0, a1), at(r0, a0)
    big = 1 if (a1 - a0) % 360 > 180 else 0
    return ('<path d="M%s %s A%s %s 0 %d 1 %s %s L%s %s A%s %s 0 %d 0 %s %s Z"/>'
            % (_f(ax), _f(ay), _f(r1), _f(r1), big, _f(bx), _f(by), _f(cx1), _f(cy1),
               _f(r0), _f(r0), big, _f(dx), _f(dy)))


def _star(cx, cy, r0, r1, turn=-90):
    import math
    pts = []
    for i in range(10):
        r = r1 if i % 2 == 0 else r0
        a = math.radians(turn + i * 36)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return _poly(pts)


# -- the shapes, by family ---------------------------------------------------------
# Each answers {"hot": (x, y) in even units, "body": [svg], "cut": [svg],
# "accent": [svg], "marks": [svg], "turn": degrees about the cell's centre}.

def _arrow(fam):
    if fam == "playful":            # chunky, the tip rounded by the body's rounding
        pts = [(6, 4), (6, 25), (11, 20.6), (14.2, 27.6), (18.8, 25.6), (15.6, 18.8),
               (22.4, 18.8)]
        shine = [_rect(7.6, 9.2, 2.2, 7.5, 1.1)]
        return {"hot": (6, 4), "body": [_poly(pts)], "accent": shine}
    if fam == "luna":               # Luna's: a broad head, a long tail
        pts = [(6, 4), (6, 26), (11, 21.4), (14.6, 29.2), (18.2, 27.6), (14.8, 20.2),
               (21.6, 20.2)]
        return {"hot": (6, 4), "body": [_poly(pts)]}
    if fam == "coast":
        pts = [(6, 4), (6, 25.4), (10.8, 21), (14, 28.2), (17.6, 26.6), (14.6, 19.6),
               (21, 19.6)]
        return {"hot": (6, 4), "body": [_poly(pts)]}
    pts = [(6, 4), (6, 25), (10.6, 20.8), (13.6, 27.8), (16.9, 26.4), (14, 19.6), (20.4, 19.6)]
    return {"hot": (6, 4), "body": [_poly(pts)]}


def _hand(fam):
    if fam == "playful":            # the cartoon glove over its cuff
        fingers = [_rect(9, 2, 6, 17, 3), _rect(15, 11, 5.4, 10, 2.7),
                   _rect(20.4, 12, 5, 10, 2.5), _rect(25.4, 13.6, 4.2, 9, 2.1)]
        palm = [_rect(9, 15, 20.6, 12.6, 5.5)]
        thumb = [_rect(3, 16.6, 10, 5.6, 2.8, rot=(38, 8, 19.4))]
        cuff = [_rect(10.4, 25.8, 18, 5.6, 2.4)]
        cut = [_line(15, 12.5, 15, 18.4, 1.6), _line(20.4, 13.5, 20.4, 19.4, 1.6),
               _line(25.4, 15, 25.4, 20, 1.6), _line(12.6, 25.6, 27, 25.6, 1.6)]
        glove = fingers + palm + thumb
        return {"hot": (12, 2), "body": glove + cuff, "cut": cut, "accent": glove}
    w = 5 if fam != "luna" else 5.4
    fingers = [_rect(9.6, 2, w - 0.2, 16, (w - 0.2) / 2), _rect(14.4, 11, 4.6, 9, 2.3),
               _rect(19, 12, 4.4, 9, 2.2), _rect(23.4, 13.6, 3.8, 8, 1.9)]
    palm = [_rect(9.6, 15, 17.6, 12.4, 4.6 if fam == "coast" else 3.6)]
    thumb = [_rect(3.6, 17, 9, 4.6, 2.3, rot=(36, 8, 19.3))]
    wrist = [_rect(11, 24, 14.6, 6, 1.2 if fam != "coast" else 2.4)]
    cut = [_line(14.4, 12.2, 14.4, 18.4, 1.4), _line(19, 13.2, 19, 19, 1.4),
           _line(23.4, 14.8, 23.4, 19.6, 1.4)]
    return {"hot": (12, 2), "body": fingers + palm + thumb + wrist, "cut": cut}


def _beam(fam):
    if fam == "playful":
        return {"hot": (16, 16), "body": [_rect(14, 4, 4, 24, 1), _rect(9.6, 2.4, 12.8, 4, 2),
                                          _rect(9.6, 25.6, 12.8, 4, 2)]}
    r = 0.6 if fam == "coast" else 0
    return {"hot": (16, 16), "body": [_rect(15, 4, 2, 24), _rect(11, 3, 10, 2, r),
                                      _rect(11, 27, 10, 2, r)]}


def _double(fam):
    """The across resize: a shaft with a head at each end."""
    if fam == "playful":
        return [_rect(8, 14, 16, 4, 0.5), _poly([(3, 16), (11, 8), (11, 24)]),
                _poly([(29, 16), (21, 8), (21, 24)])]
    if fam == "luna":
        return [_rect(8, 14.5, 16, 3), _poly([(3.4, 16), (10.4, 9), (10.4, 23)]),
                _poly([(28.6, 16), (21.6, 9), (21.6, 23)])]
    return [_rect(8, 15, 16, 2), _poly([(3, 16), (9.4, 9.6), (9.4, 22.4)]),
            _poly([(29, 16), (22.6, 9.6), (22.6, 22.4)])]


def _move(fam):
    t, a, b, c = {"playful": (4, 2.6, 9, 5.6), "luna": (3, 3, 8.6, 5)}.get(fam, (2, 3, 8, 4.4))
    lo, hi = 16 - t / 2, 16 + t / 2
    shaft = [_rect(6, lo, 20, t), _rect(lo, 6, t, 20)]
    heads = [_poly([(a, 16), (b, 16 - c), (b, 16 + c)]),
             _poly([(32 - a, 16), (32 - b, 16 - c), (32 - b, 16 + c)]),
             _poly([(16, a), (16 - c, b), (16 + c, b)]),
             _poly([(16, 32 - a), (16 - c, 32 - b), (16 + c, 32 - b)])]
    return {"hot": (16, 16), "body": shaft + heads, "round": 0.5 if fam == "playful" else None}


def _busy(fam):
    if fam == "playful":            # a spinning star, its sweep behind it
        star = _star(16, 16, 5.4, 11.4)
        return {"hot": (16, 16), "body": [star], "accent": [_circle(12.6, 11.6, 2)],
                "marks": [_arc(16, 16, 14.2, 20, 70, 2.2), _arc(16, 16, 14.2, 200, 250, 2.2)]}
    return {"hot": (16, 16), "body": [_ring(16, 16, 5.4, 10)],
            "accent": [_wedge(16, 16, 5, 10.5, -90, 0)]}


def smooth_shape(fam, shape):
    """The shape's parts. A centred shape of a family whose lines are a pixel
    at 16 px is drawn a unit off the cell's centre (`at`), so its one-pixel
    stems and shafts lie on whole pixels; its hotspot is the pixel they
    cover."""
    if shape == "arrow":
        return _arrow(fam)
    if shape == "hand":
        return _hand(fam)
    if shape == "text":
        got = _beam(fam)
    elif shape in ("ew", "ns", "nwse", "nesw"):
        turn = {"ew": 0, "ns": 90, "nwse": 45, "nesw": -45}[shape]
        got = {"hot": (16, 16), "body": _double(fam), "turn": turn,
               "round": 0.5 if fam == "playful" else None}
    elif shape == "move":
        got = _move(fam)
    else:
        got = _busy(fam)
    if fam != "playful":
        got["at"] = 1
    return got


# -- the pixel family --------------------------------------------------------------

PIXEL_ART = {
    "arrow": ((0, 0), (
        "O...............",
        "OO..............",
        "OFO.............",
        "OFFO............",
        "OFFFO...........",
        "OFFFFO..........",
        "OFFFFFO.........",
        "OFFFFFFO........",
        "OFFFFFFFO.......",
        "OFFFFFOOOO......",
        "OFFOFFO.........",
        "OFO.OFFO........",
        "OO..OFFO........",
        "O....OFFO.......",
        ".....OFFO.......",
        "......OO........")),
    "hand": ((5, 0), (
        ".....OO.........",
        "....OFFO........",
        "....OFFO........",
        "....OFFO........",
        "....OFFOOO......",
        "....OFFOFFOOO...",
        "....OFFOFFOFFOO.",
        ".OO.OFFOFFOFFOFO",
        "OFFOOFFOFFOFFOFO",
        "OFFFOFFFFFFFFFFO",
        ".OFFFFFFFFFFFFFO",
        "..OFFFFFFFFFFFFO",
        "...OFFFFFFFFFFO.",
        "....OFFFFFFFFO..",
        ".....OFFFFFFFO..",
        ".....OOOOOOOOO..")),
    "text": ((3, 7), (
        "OOO.OOO", "OFFOFFO", "OOOFOOO", "..OFO..", "..OFO..", "..OFO..", "..OFO..",
        "..OFO..", "..OFO..", "..OFO..", "..OFO..", "..OFO..", "OOOFOOO", "OFFOFFO",
        "OOO.OOO")),
    "busy": ((5, 7), (
        "OOOOOOOOOOO",
        "OFFFFFFFFFO",
        "OOOOOOOOOOO",
        ".OFFFFFFFO.",
        ".OFAAAAAFO.",
        "..OFAAAFO..",
        "...OFAFO...",
        "....OFO....",
        "....OFO....",
        "...OFFFO...",
        "..OFFAFFO..",
        ".OFFAAAFFO.",
        ".OFAAAAAFO.",
        "OOOOOOOOOOO",
        "OFFFFFFFFFO",
        "OOOOOOOOOOO")),
}


def _pixel_arrows():
    """The resize and move arrows' fill cells on a 15-cell grid (the outline
    comes from `_pixel_rows`), hotspot at the centre."""
    n, m = 15, 7
    e = n - 2
    ew = {(x, m) for x in range(1, n - 1)}
    for d in range(4):
        for j in range(-d, d + 1):
            ew |= {(1 + d, m + j), (e - d, m + j)}
    ns = {(y, x) for x, y in ew}
    diag = {(i, i) for i in range(1, n - 1)}
    for x in range(1, n - 1):
        for y in range(1, n - 1):
            if x + y <= 6 or x + y >= 2 * e - 4:
                diag.add((x, y))
    anti = {(n - 1 - x, y) for x, y in diag}
    mv = {(x, m) for x in range(1, n - 1)} | {(m, y) for y in range(1, n - 1)}
    for d in range(3):
        for j in range(-d, d + 1):
            mv |= {(1 + d, m + j), (e - d, m + j), (m + j, 1 + d), (m + j, e - d)}
    out = {}
    for k, cells in (("ew", ew), ("ns", ns), ("nwse", diag), ("nesw", anti), ("move", mv)):
        out[k] = ((m, m), tuple("".join("F" if (x, y) in cells else "." for x in range(n))
                                for y in range(n)))
    return out


def _pixel_rows(shape):
    """(hotspot, rows of 'O', 'F', 'A', '.'): the art as drawn, or a generated
    arrow's fill with the outline added round it."""
    if shape in PIXEL_ART:
        return PIXEL_ART[shape]
    hot, rows = _pixel_arrows()[shape]
    w, h = max(len(r) for r in rows), len(rows)
    grid = [[r[x] if x < len(r) else "." for x in range(w)] for r in rows]
    out = [row[:] for row in grid]
    for y in range(h):
        for x in range(w):
            if grid[y][x] != ".":
                continue
            if any(0 <= x + i < w and 0 <= y + j < h and grid[y + j][x + i] in "FA"
                   for i in (-1, 0, 1) for j in (-1, 0, 1)):
                out[y][x] = "O"
    return hot, ["".join(r) for r in out]


def _pixel(shape, size):
    k = size // 16
    (hx, hy), rows = _pixel_rows(shape)
    w, h = len(rows[0]) * k, len(rows) * k
    layers = {}
    for layer, on in (("line", "OFA"), ("fill", "FA"), ("accent", "A")):
        a = bytearray(w * h)
        for y in range(h):
            r = rows[y // k]
            for x in range(w):
                if r[x // k] in on:
                    a[y * w + x] = 255
        layers[layer] = bytes(a)
    return hx * k, hy * k, w, h, layers


# -- the rasteriser ------------------------------------------------------------------

def _svg(parts, size, grow=0.0, join="miter", turn=0, at=0):
    n = (CELL + 2 * PAD) * size // CELL
    stroke = ' stroke="#000" stroke-width="%s"' % _f(2 * grow) if grow else ' stroke="none"'
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="%d %d %d %d"><g transform="translate(%d %d) rotate(%s 16 16)" '
            'fill="#000"%s stroke-linejoin="%s" stroke-miterlimit="12">%s</g></svg>'
            % (n, n, -PAD, -PAD, CELL + 2 * PAD, CELL + 2 * PAD, at, at, _f(turn), stroke, join,
               "".join(parts)))


def _alpha(svg):
    import io
    import resvg_py
    from PIL import Image
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg))
    return Image.open(io.BytesIO(png)).convert("RGBA").getchannel("A").tobytes()


def _mul(a, b):
    return bytes((x * y + 127) // 255 for x, y in zip(a, b))


def _minus(a, b):
    return bytes((x * (255 - y) + 127) // 255 for x, y in zip(a, b))


def render(family, shape, size):
    """(hx, hy, w, h, {layer: w*h alpha bytes}) of `shape` in `family` at
    `size` px: the hotspot in the raster's pixels."""
    if family == "pixel":
        return _pixel(shape, size)
    st = STYLES[family]
    sh = smooth_shape(family, shape)
    body = sh["body"]
    rnd = st["round"] if sh.get("round") is None else sh["round"]
    join = st["join"]
    marks = ['<g stroke="#000">%s</g>' % m for m in sh.get("marks", ())]
    n = (CELL + 2 * PAD) * size // CELL

    def alpha(parts, grow=0.0, how=join):
        if not parts:
            return bytes(n * n)
        return _alpha(_svg(parts, size, grow, how, sh.get("turn", 0), sh.get("at", 0)))

    edge = rnd + st.get("rim", 0) + st["ow"]    # the silhouette's reach past the body
    line = bytes(max(x, y) for x, y in zip(alpha(body, edge), alpha(marks)))
    solid = alpha(body, rnd, "round" if rnd else join)
    cut = alpha(['<g stroke="#000">%s</g>' % c for c in sh.get("cut", ())])
    if st.get("rim"):               # LUNA: the body in the accent, a white rim round it
        fill = _minus(alpha(body, rnd + st["rim"]), cut)
        accent = _minus(solid, cut)
    else:
        fill = _minus(solid, cut)
        accent = _mul(alpha(sh.get("accent")), fill)
    hx, hy = sh["hot"]
    k = size / CELL
    return (int(round((hx + PAD) * k)), int(round((hy + PAD) * k)), n, n,
            {"line": line, "fill": fill, "accent": accent})
