"""The pointer families' art: a pointer of each shape in each family, drawn as a
few layers of coverage that tools/make_icons.py packs into one font file a
family and size (`ptr-<family>-<size>.fnt`).

A family draws its shapes in its icon set's style: PIXEL 1-bit art with a
black outline; MOY a black body in a cream band ringed in black, the
Windows look; COAST short, wide and round in a navy line; LUNA the Windows
XP look, long and narrow, a lavender body in a broad cream rim; BLOCKS a
vinyl toy, a sunny body in a navy keyline, a cream glove on a rolled cuff.
Busy is an hourglass in every family. Every shape has the three layers of
LAYERS, drawn in that order, each in its family's colour for it
(runtime/toolkit/pointers.py): the outline (the silhouette, under the rest),
the fill and the accent. A layer a shape lacks is empty.

At 16 px every family is 1-bit pixel art (`ART16`): `O` cells the outline,
`F` the fill, `A` the accent, a whole pixel each; `auto` art is fill cells
whose outline is every clear cell beside one, across or down. PIXEL keeps
its 16 px art at every size, each cell grown whole. The shapes a family does
not draw its own share one art, recoloured per family (`art16`): LUNA's
lavender in black, COAST's sand cyan, MOY's arrow, hand and busy ringed in
black.

At 32 and 48 px the smooth families are SVG on a 32-unit cell (a unit a
pixel at 32 px), rasterised by resvg. A shape's parts are its BODY (the
innermost layer); the family's band (`rim`, MOY's and LUNA's cream) and
outline (`ow`) are the parts grown outward, a polygon's corners mitred
(capped, `MITER`) and then rounded by the family's `round` grown with them,
but for its tip, which stays sharp. `cut` lines part a body (fingers),
`accent` parts are drawn in the accent (shrunk by `accent_d`), `hole` parts
are kept out of it, `marks` are drawn with the outline alone and `rimmed`
parts take the band where the body does not; a shape may set its own `rim`,
`ow` and `round`, and `top`, a thinner keyline over a hand's hotspot.

Each shape's hotspot is exact at every size: an arrow's is the pixel at its
outline's apex, a hand's the top of its index finger (a pixel or two
into a thick keyline), each placed
on a whole pixel (the art is shifted by the fraction of a pixel that takes),
the fill starting within 2 px below it (3 at 48 px): an arrow's outline reaches its
family's `tip` past the body's, tapering to it; a centred shape's is its
middle.

  render(family, shape, size) -> (hx, hy, w, h, {layer: alpha bytes})
  bpp(family, size) -> the bits a coverage takes in the font file
"""

import math

FAMILIES = ("pixel", "moy", "coast", "luna", "blocks")
SHAPES = ("arrow", "hand", "text", "ew", "ns", "nwse", "nesw", "move", "busy")
LAYERS = ("line", "fill", "accent")
CELL = 32                   # the smooth families' units a cell
PAD = 8                     # units around the cell a raster keeps for the outline
MITER = 4                   # a corner's miter, in widths, before it is bevelled
TIP = 1.6                   # a tip's reach past its body, in widths: its outline thins

# How each smooth family draws its parts, in units: the outline outside the
# band (`ow`), the band between outline and body (`rim`; the body then wears
# the accent), the body's corner rounding (`round`), and how far an arrow's
# apex reaches past its body's tip (`tip`, and at least `tip_px` pixels), the
# keyline tapering to it.
STYLES = {
    "moy": {"ow": 1, "rim": 2, "round": 0.25, "tip": 1},
    "coast": {"ow": 1.5, "rim": 0, "round": 0.5, "tip": 1},
    "luna": {"ow": 2, "rim": 2, "round": 0, "tip": 1.25},
    "blocks": {"ow": 3, "rim": 0, "round": 1.5, "tip": 1, "tip_px": 2},
}


def bpp(family, size):
    return 1 if family == "pixel" or size == 16 else 4


# -- geometry ----------------------------------------------------------------------
# A part is a tuple: ("poly", points, tip) with `tip` the index of the vertex
# kept sharp (or None), ("rect", x, y, w, h, r[, (deg, cx, cy)]), ("circle", cx,
# cy, r), ("cap", x0, y0, x1, y1, w) a stroke with round ends, ("curve", x0, y0,
# cx, cy, x1, y1, w) a quadratic stroke. Grown by d, each keeps its outline d
# units out.

def _f(v):
    return ("%.3f" % v).rstrip("0").rstrip(".")


def _area(pts):
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts))) / 2


def _offset(pts, d, tip, rnd, reach=None):
    """[(x, y, r)]: polygon `pts` grown by d (shrunk where d < 0), a corner
    whose miter passes MITER widths bevelled, each corner's rounding grown
    with it (a convex corner's by d, a concave one's less d); the tip's
    corner stays sharp, reaching at most TIP widths past the body's, so a
    narrow tip's outline thins toward its point instead of growing a spike.
    Given `reach`, the tip instead lies on the edge that leaves it, grown,
    `reach` units past the body's tip: an arrow's vertical edge runs straight
    up to its apex, which stays `reach` from the fill whatever the outline."""
    n = len(pts)
    s = 1 if _area(pts) > 0 else -1
    normals = []
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        ln = math.hypot(x1 - x0, y1 - y0)
        normals.append((s * (y1 - y0) / ln, -s * (x1 - x0) / ln))
    out = []
    late = None
    for i in range(n):
        px, py = pts[i]
        a, b = normals[i - 1], normals[i]
        ex0, ey0 = px - pts[i - 1][0], py - pts[i - 1][1]
        ex1, ey1 = pts[(i + 1) % n][0] - px, pts[(i + 1) % n][1] - py
        convex = (ex0 * ey1 - ey0 * ex1) * s > 0
        r = 0 if i == tip else max(0.0, rnd + d if convex else rnd - d)
        dot = a[0] * b[0] + a[1] * b[1]
        m = d / (1 + dot) if dot > -0.999 else 1e9
        mx, my = px + m * (a[0] + b[0]), py + m * (a[1] + b[1])
        far = math.hypot(mx - px, my - py)
        if i == tip and reach is not None and d > 0:
            nx, ny = pts[(i + 1) % n]
            ln = math.hypot(px - nx, py - ny)
            ay = py + d * b[1] + (py - ny) / ln * reach
            out.append((px + d * b[0] + (px - nx) / ln * reach, ay, r))
            # The other edge's outline runs whole up to half its width below
            # the apex, and only then tapers to it.
            qx, qy = pts[i - 1]
            lq = math.hypot(qx - px, qy - py)
            ux, uy = (qx - px) / lq, (qy - py) / lq
            fx, fy = px + d * a[0], py + d * a[1]
            t = (ay + d / 2 - fy) / uy if uy > 0 else -1
            if 0 < t < lq / 2:
                late = (fx + ux * t, fy + uy * t, 0)
        elif i == tip and far > TIP * abs(d):
            out.append((px + (mx - px) * TIP * abs(d) / far,
                        py + (my - py) * TIP * abs(d) / far, r))
        elif i != tip and d and far > MITER * abs(d):
            out.append((px + d * a[0], py + d * a[1], r))
            out.append((px + d * b[0], py + d * b[1], r))
        else:
            out.append((mx, my, r))
    if late is not None:
        out.append(late)
    return out


def _rounded(vs):
    """An SVG path through vertices (x, y, r), each corner rounded by r."""
    n = len(vs)
    cuts = []
    for i in range(n):
        x, y, r = vs[i]
        if r <= 0:
            cuts.append(None)
            continue
        (ax, ay, _), (bx, by, _) = vs[i - 1], vs[(i + 1) % n]
        l0, l1 = math.hypot(x - ax, y - ay), math.hypot(bx - x, by - y)
        if not l0 or not l1:
            cuts.append(None)
            continue
        u0 = ((x - ax) / l0, (y - ay) / l0)
        u1 = ((bx - x) / l1, (by - y) / l1)
        turn = math.acos(max(-1.0, min(1.0, u0[0] * u1[0] + u0[1] * u1[1])))
        t = min(r * math.tan(turn / 2), l0 / 2, l1 / 2)
        cuts.append(((x - u0[0] * t, y - u0[1] * t), (x + u1[0] * t, y + u1[1] * t)))
    d = []
    for i in range(n):
        x, y, _ = vs[i]
        c = cuts[i]
        if c is None:
            d.append(("L" if d else "M") + "%s %s" % (_f(x), _f(y)))
        else:
            d.append(("L" if d else "M") + "%s %s" % (_f(c[0][0]), _f(c[0][1])))
            d.append("Q%s %s %s %s" % (_f(x), _f(y), _f(c[1][0]), _f(c[1][1])))
    return '<path d="%s Z"/>' % " ".join(d)


def _part(p, d, rnd, reach=None):
    """The SVG of part `p` grown by d (a polygon's tip `reach` past its
    body's where it is an arrow's, `_offset`)."""
    k = p[0]
    if k == "poly":
        return _rounded(_offset(p[1], d, p[2], rnd, reach if len(p) > 3 else None))
    if k == "rect":
        x, y, w, h, r = p[1:6]
        rot = p[6] if len(p) > 6 else None
        t = ' transform="rotate(%s %s %s)"' % tuple(_f(v) for v in rot) if rot else ""
        return '<rect x="%s" y="%s" width="%s" height="%s" rx="%s"%s/>' % (
            _f(x - d), _f(y - d), _f(w + 2 * d), _f(h + 2 * d), _f(max(0, r + d)), t)
    if k == "circle":
        return '<circle cx="%s" cy="%s" r="%s"/>' % (_f(p[1]), _f(p[2]), _f(p[3] + d))
    if k == "cap":
        return ('<path d="M%s %s L%s %s" fill="none" stroke="#000" stroke-width="%s" '
                'stroke-linecap="round"/>' % (_f(p[1]), _f(p[2]), _f(p[3]), _f(p[4]),
                                              _f(p[5] + 2 * d)))
    if k == "curve":
        return ('<path d="M%s %s Q%s %s %s %s" fill="none" stroke="#000" stroke-width="%s" '
                'stroke-linecap="round"/>' % tuple(_f(v) for v in p[1:7] + (p[7] + 2 * d,)))
    raise ValueError(k)


def _apex(p, d, rnd, reach):
    """The point of part `p` grown by d that the hotspot sits on: a polygon's
    tip, a rect's top middle."""
    if p[0] == "poly":
        x, y, _r = _offset(p[1], d, p[2], rnd, reach)[p[2]]
        return x, y
    return p[1] + p[3] / 2, p[2] - d


def _turned(parts, deg, cx=16, cy=16):
    """Parts rotated by deg about (cx, cy): polygons by their points, the
    rest by the rect's transform (strokes by their ends)."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))

    def rot(x, y):
        return cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c
    out = []
    for p in parts:
        if p[0] == "poly":
            out.append(("poly", [rot(x, y) for x, y in p[1]], p[2]))
        elif p[0] == "rect":
            out.append(p[:6] + ((deg, cx, cy),))
        elif p[0] == "cap":
            out.append(("cap",) + rot(p[1], p[2]) + rot(p[3], p[4]) + (p[5],))
        else:
            out.append(p)
    return out


# -- the smooth shapes, by family -------------------------------------------------
# Each answers {"body": parts, "apex": index of the body part the hotspot is on
# (absent: the cell's middle), "cut", "accent", "hole", "marks": parts, "core":
# False where a band family's body is not its accent, "ow": its own outline,
# "flat": the apex a pixel wide}.

ARROWS = {
    "moy": [(6, 4), (6, 22.5), (10, 18.8), (12.8, 25.4), (16.4, 23.9), (13.6, 17.4),
                (18.8, 17.4)],
    "coast": [(6, 4), (6, 22.6), (10.4, 18.8), (12.6, 23.8), (16.8, 22), (14.6, 17.2),
              (22, 17.2)],
    "luna": [(6, 4), (6, 23.6), (9, 20.6), (12.4, 28.4), (15.4, 27.1), (12.2, 19.6),
             (16.6, 19.6)],
    "blocks": [(6, 4), (6, 23.5), (10.4, 19.6), (13.4, 27.6), (18.2, 25.6), (15.2, 18.4),
                (21.4, 18.4)],
}


def _arrow(fam):
    got = {"body": [("poly", ARROWS[fam], 0, "arrow")], "apex": 0, "flat": True}
    if fam == "blocks":            # a gloss stroke down the left edge
        got["accent"] = [("curve", 8.6, 8.4, 8.2, 12.6, 8.9, 16.2, 1.6)]
    return got


def _hand(fam):
    if fam == "blocks":             # a puffy glove on a rolled cuff, a vinyl rim round it
        index = ("rect", 9, 5, 6, 12, 2)
        knuckles = [("circle", 17.5, 12.6, 2.6), ("circle", 22.3, 12.6, 2.6),
                    ("circle", 26.8, 13, 2.6)]
        palm = ("rect", 9, 13.6, 20.4, 12.4, 4.4)
        thumb = ("rect", 3, 15.5, 9, 5.6, 2.8, (-30, 7.5, 18.3))
        cuff = ("rect", 8.6, 25, 21.2, 6, 3)
        glove = [index, palm, thumb] + knuckles
        cut = [("cap", 17.5, 15.4, 17.5, 19.4, 2), ("cap", 22.3, 15.4, 22.3, 19.4, 2),
               ("cap", 26.8, 15.8, 26.8, 19.4, 2), ("cap", 15, 12.6, 15, 17.6, 2),
               ("cap", 19.9, 11, 19.9, 13.6, 1.6), ("cap", 24.6, 11.2, 24.6, 13.8, 1.6),
               ("cap", 9.6, 20.4, 12, 19, 2), ("cap", 10.4, 25, 28, 25, 2)]
        return {"body": [index] + knuckles + [palm, thumb, cuff], "apex": 0, "cut": cut,
                "accent": glove, "accent_d": -1.5, "hole": [cuff], "top": 2}
    if fam == "coast":              # round and friendly
        index = ("rect", 9.4, 5, 4.4, 12, 2.2)
        fingers = [("rect", 14.6, 11.2, 4.2, 8, 2.1), ("rect", 19.4, 12, 4, 8, 2),
                   ("rect", 24, 13.4, 3.8, 7, 1.9)]
        palm = ("rect", 9.4, 15, 18.4, 10.6, 4.6)
        thumb = ("rect", 4.4, 17.4, 8.4, 4.4, 2.2, (-35, 8.6, 19.6))
        wrist = ("rect", 11.4, 23, 14, 5, 2.4)
        cut = [("cap", 14.2, 13, 14.2, 17.6, 1.2), ("cap", 19, 14, 19, 18.6, 1.2),
               ("cap", 23.6, 15.4, 23.6, 19.6, 1.2)]
        return {"body": [index] + fingers + [palm, thumb, wrist], "apex": 0, "cut": cut}
    # MOY and LUNA: the fingers parted by cream lines, LUNA's index jointed
    parts = [("cap", 14.2, 14, 14.2, 18.6, 1), ("cap", 18.8, 14.8, 18.8, 19.2, 1),
             ("cap", 23.4, 16, 23.4, 19.6, 1)]
    if fam == "luna":
        index = ("rect", 9.6, 6, 3.6, 13, 1)
        fingers = [("rect", 14.6, 12.4, 3.4, 8, 1), ("rect", 19.2, 13.2, 3.4, 8, 1),
                   ("rect", 23.8, 14.6, 3, 7, 1)]
        palm = ("rect", 9.6, 18.4, 17.2, 8, 2)
        thumb = ("rect", 4.4, 19.4, 7.4, 3.4, 1, (-38, 8, 21))
        return {"body": [index] + fingers + [palm, thumb], "apex": 0,
                "cut": parts + [("cap", 9.6, 12.4, 13.2, 12.4, 1)]}
    index = ("rect", 9.8, 6, 3.6, 12, 1.8)
    fingers = [("rect", 14.6, 12, 3.4, 8, 1.7), ("rect", 19.2, 12.8, 3.4, 8, 1.7),
               ("rect", 23.8, 14, 3, 7, 1.5)]
    palm = ("rect", 9.8, 16.6, 17, 8.4, 2.6)
    thumb = ("rect", 4.6, 18, 7.6, 3.4, 1.7, (-36, 8.4, 19.7))
    return {"body": [index] + fingers + [palm, thumb], "apex": 0, "cut": parts}


def _beam(fam):
    if fam == "blocks":             # a fat I: a round stem, round caps
        return {"body": [("cap", 16, 6, 16, 26, 2), ("cap", 12, 6, 20, 6, 2),
                         ("cap", 12, 26, 20, 26, 2)], "ow": 2}
    if fam == "coast":
        return {"body": [("rect", 14.8, 6, 2.4, 20, 0), ("rect", 12, 5, 8, 2.2, 1.2),
                         ("rect", 12, 24.8, 8, 2.2, 1.2)]}
    return {"body": [("rect", 15, 6, 2, 20, 0), ("rect", 12, 5, 8, 2, 0),       # MOY, LUNA
                     ("rect", 12, 25, 8, 2, 0)], "rim": 1, "ow": 1}


# The across resize: (shaft width, head width, head depth, length).
DOUBLE = {"moy": (3.4, 10, 5.6, 24), "coast": (3.2, 11, 6, 22),
          "luna": (2, 7, 5, 25), "blocks": (6, 14, 7, 30)}


def _double(fam):
    t, hw, hd, ln = DOUBLE[fam]
    a, b = 16 - ln / 2, 16 + ln / 2
    rnd = {"coast": 1.4, "blocks": 1.6}.get(fam)
    tip = None if rnd else 0
    shaft = ("rect", a + hd - 0.5, 16 - t / 2, ln - 2 * hd + 1, t, 0)
    heads = [("poly", [(a, 16), (a + hd, 16 - hw / 2), (a + hd, 16 + hw / 2)], tip),
             ("poly", [(b, 16), (b - hd, 16 + hw / 2), (b - hd, 16 - hw / 2)], tip)]
    return [shaft] + heads, rnd


# Move: (arm width, head width, head depth, reach from the middle).
MOVE = {"moy": (3, 8, 4.5, 14.4), "coast": (3, 9, 5, 13.8), "luna": (2, 6.5, 4.5, 15),
        "blocks": (5, 10, 5.5, 16.5)}


def _move(fam):
    t, hw, hd, reach = MOVE[fam]
    rnd = 1.6 if fam == "blocks" else (1.2 if fam == "coast" else None)
    parts = [("rect", 16 - reach + hd - 0.5, 16 - t / 2, 2 * (reach - hd) + 1, t, 0),
             ("rect", 16 - t / 2, 16 - reach + hd - 0.5, t, 2 * (reach - hd) + 1, 0)]
    for deg in (0, 90, 180, 270):
        head = ("poly", [(16 - reach, 16), (16 - reach + hd, 16 - hw / 2),
                         (16 - reach + hd, 16 + hw / 2)], None if rnd else 0)
        parts += _turned([head], deg)
    return parts, rnd


def _busy(fam):
    """An hourglass: caps above and below, the glass, sand in its bulbs and a
    stream down its neck."""
    if fam == "blocks":             # navy caps, a cream glass, yellow sand
        glass = ("poly", [(10, 7), (22, 7), (22, 9), (17.6, 16), (22, 23), (22, 25), (10, 25),
                          (10, 23), (14.4, 16), (10, 9)], None)
        sand = [("poly", [(16, 17.4), (21.4, 23), (21.4, 24.4), (10.6, 24.4), (10.6, 23)], None),
                ("poly", [(11.6, 10.4), (20.4, 10.4), (16.8, 15), (15.2, 15)], None),
                ("cap", 16, 14.6, 16, 18, 2.4)]
        caps = [("rect", 8, 3.4, 16, 4, 2), ("rect", 8, 24.6, 16, 4, 2)]
        return {"body": [glass], "marks": caps, "accent": [glass], "hole": sand,
                "core": False, "round": 1.2}
    w = {"moy": 6, "coast": 6.4, "luna": 5.6}[fam]
    sand = [("poly", [(16, 18.8), (16 + w - 1.4, 23.8), (16 - w + 1.4, 23.8)], None),
            ("cap", 16, 14, 16, 19, 1.2)]
    if fam == "coast":
        glass = ("poly", [(16 - w, 7.6), (16 + w, 7.6), (16 + w, 9), (17, 16), (16 + w, 23),
                          (16 + w, 24.4), (16 - w, 24.4), (16 - w, 23), (15, 16), (16 - w, 9)],
                 None)
        caps = [("rect", 16 - w - 2.4, 4, 2 * w + 4.8, 3.2, 1.4),
                ("rect", 16 - w - 2.4, 24.8, 2 * w + 4.8, 3.2, 1.4)]
        return {"body": [glass], "marks": caps, "accent": sand, "round": 1}
    # MOY and LUNA: slim caps in the body's colour inside a 1u band, the glass
    # cream in the outline alone
    glass = ("poly", [(16 - w, 6.5), (16 + w, 6.5), (16 + w, 9), (17, 16), (16 + w, 23),
                      (16 + w, 25.5), (16 - w, 25.5), (16 - w, 23), (15, 16), (16 - w, 9)], None)
    caps = [("rect", 16 - w - 1.2, 5, 2 * w + 2.4, 1.5, 0.4),
            ("rect", 16 - w - 1.2, 25.5, 2 * w + 2.4, 1.5, 0.4)]
    return {"body": [glass], "rimmed": caps, "rimmed_rim": 1, "accent": sand + caps,
            "core": False, "round": 0.2}


def smooth_shape(fam, shape):
    if shape == "arrow":
        return _arrow(fam)
    if shape == "hand":
        return _hand(fam)
    if shape == "text":
        return _beam(fam)
    if shape == "busy":
        return _busy(fam)
    if shape == "move":
        body, rnd = _move(fam)
    else:
        body, rnd = _double(fam)
        body = _turned(body, {"ew": 0, "ns": 90, "nwse": 45, "nesw": -45}[shape])
    got = {"body": body}
    if rnd is not None:
        got["round"] = rnd
    return got


# -- 16 px and the pixel family -----------------------------------------------------
# Each is (hotspot, rows). `auto` art lists fill cells alone.

def _auto(rows):
    """Fill rows with their outline: every clear cell beside a fill cell,
    across or down (never corner to corner, which closes the notches)."""
    w, h = max(len(r) for r in rows), len(rows)
    g = [[r[x] if x < len(r) else "." for x in range(w)] for r in rows]
    out = [row[:] for row in g]
    for y in range(h):
        for x in range(w):
            if g[y][x] == "." and any(0 <= x + i < w and 0 <= y + j < h and g[y + j][x + i] != "."
                                      for i, j in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                out[y][x] = "O"
    return tuple("".join(r) for r in out)


_EW = (
    "...............",
    "...F.......F...",
    "..FF.......FF..",
    ".FFFFFFFFFFFFF.",
    "..FF.......FF..",
    "...F.......F...",
    "...............")
_NWSE = (
    "...............",
    ".FFFF..........",
    ".FFF...........",
    ".FFF...........",
    ".F..F..........",
    ".....F.........",
    "......F........",
    ".......F.......",
    "........F......",
    ".........F.....",
    "..........F..F.",
    "...........FFF.",
    "...........FFF.",
    "..........FFFF.",
    "...............")
_MOVE = (
    ".................",
    "........F........",
    ".......FFF.......",
    "......FFFFF......",
    "........F........",
    "........F........",
    "...F....F....F...",
    "..FF....F....FF..",
    ".FFFFFFFFFFFFFFF.",
    "..FF....F....FF..",
    "...F....F....F...",
    "........F........",
    "........F........",
    "......FFFFF......",
    ".......FFF.......",
    "........F........",
    ".................")


def _flip(rows):
    return tuple(r[::-1] for r in rows)


def _swap(rows):
    return tuple("".join(r[y] for r in rows) for y in range(len(rows[0])))


SHARED16 = {
    "text": ((3, 7), (
        "OOO.OOO", "OFFOFFO", "OOOFOOO", "..OFO..", "..OFO..", "..OFO..", "..OFO..",
        "..OFO..", "..OFO..", "..OFO..", "..OFO..", "..OFO..", "OOOFOOO", "OFFOFFO",
        "OOO.OOO")),
    "ew": ((7, 3), _auto(_EW)),
    "ns": ((3, 7), _auto(_swap(_EW))),
    "nwse": ((7, 7), _auto(_NWSE)),
    "nesw": ((7, 7), _auto(_flip(_NWSE))),
    "move": ((8, 8), _auto(_MOVE)),
    "busy": ((5, 7), (
        "OOOOOOOOOOO",
        "OFFFFFFFFFO",
        "OOOOOOOOOOO",
        ".OFFFFFFFO.",
        ".OFFFFFFFO.",
        "..OFFFFFO..",
        "...OFFFO...",
        "....OFO....",
        "....OSO....",
        "...OFSFO...",
        "..OFFSFFO..",
        ".OFFSSSFFO.",
        ".OSSSSSSSO.",
        "OOOOOOOOOOO",
        "OFFFFFFFFFO",
        "OOOOOOOOOOO")),
}

_CLASSIC_ARROW = ((0, 0), (
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
    "......OO........"))
_CLASSIC_HAND = ((5, 0), (
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
    ".....OOOOOOOOO.."))

ART16 = {
    "pixel": {"arrow": _CLASSIC_ARROW, "hand": _CLASSIC_HAND},
    "moy": {                        # 14 and 13 rows: its ring makes them 16 and 15
        "arrow": ((0, 0), (
            "O.........",
            "OO........",
            "OFO.......",
            "OFFO......",
            "OFFFO.....",
            "OFFFFO....",
            "OFFFFFO...",
            "OFFFFFFO..",
            "OFFFFOOO..",
            "OFFOFFO...",
            "OFO.OFFO..",
            "OO..OFFO..",
            "O....OFFO.",
            ".....OOO..")),
        "hand": ((5, 0), (
            ".....OO.........",
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
            "....OOOOOOOOOO.."))},
    "coast": {
        "arrow": ((0, 0), (
            "O..........",
            "OO.........",
            "OFOO.......",
            "OFFFO......",
            "OFFFFOO....",
            "OFFFFFFO...",
            "OFFFFFFFOO.",
            "OFFFFFFFFFO",
            "OFFFFFOOOO.",
            "OFFOOFFO...",
            ".OO..OFFO..",
            "......OO...")),
        "hand": ((5, 0), (
            ".....OO.........",
            "....OFFO........",
            "....OFFO........",
            "....OFFOOO......",
            "....OFFOFFOOO...",
            "....OFFOFFOFFOO.",
            "..O.OFFOFFOFFOFO",
            ".OFOOFFOFFOFFOFO",
            "OFFFOFFFFFFFFFFO",
            "OFFFFFFFFFFFFFFO",
            ".OFFFFFFFFFFFFFO",
            "..OFFFFFFFFFFFO.",
            "...OFFFFFFFFFO..",
            "....OOOOOOOOO..."))},
    "luna": {
        "arrow": ((0, 0), (
            "O........",
            "OO.......",
            "OFO......",
            "OFFO.....",
            "OFFO.....",
            "OFFFO....",
            "OFFFFO...",
            "OFFFFO...",
            "OFFFFFO..",
            "OFFFFFFO.",
            "OFFFOOOO.",
            "OFFOFFO..",
            "OFO.OFFO.",
            "OO..OFFO.",
            "O....OFFO",
            ".....OOO.")),
        "hand": _CLASSIC_HAND},
    "blocks": {
        "arrow": ((0, 0), (
            "O...........",
            "OO..........",
            "OFO.........",
            "OFFO........",
            "OFFFO.......",
            "OFFFFO......",
            "OFFFFFO.....",
            "OFFFFFFO....",
            "OFFFFFFFO...",
            "OFFFFFFFFO..",
            "OFFFFFFFFFO.",
            "OFFFOFFFOOO.",
            "OFFO.OFFFO..",
            "OOO..OFFFO..",
            "......OFFFO.",
            "......OOOO..")),
        "hand": ((5, 0), (
            "....OOO.........",
            "...OFFFO........",
            "...OAAFO........",
            "...OAAFOOO......",
            "...OAAFOFFOOO...",
            ".OOOAAFOAFOFFOO.",
            "OFFOAAFOAFOAFOFO",
            "OAAAOAAAAAAAAAFO",
            ".OAAAAAAAAAAAAFO",
            "..OAAAAAAAAAAAFO",
            "...OAAAAAAAAAFO.",
            "..OOOOOOOOOOOOO.",
            "..OFFFFFFFFFFFFO",
            "..OFFFFFFFFFFFFO",
            "...OOOOOOOOOOOO."))},
}

# What each cell draws at 16 px: (line, fill, accent) cells; `S` is sand,
# the outline's unless a family's art says otherwise. MOY's body is its
# accent in a cream outline, its arrow, hand and busy ringed in black (`R`,
# `_ring`).
_CELLS = {"moy": ("ROFA", "OFA", "F")}
_PLAIN = ("OFA", "FA", "A")


def _ring(rows):
    """Rows with a black ring (`R`) round every cell, across or down, the
    art moved a cell right and down."""
    w = max(len(r) for r in rows) + 2
    g = ["." * w] + ["." + r.ljust(w - 2, ".") + "." for r in rows] + ["." * w]
    out = [list(r) for r in g]
    for y in range(len(g)):
        for x in range(w):
            if g[y][x] == "." and any(0 <= x + i < w and 0 <= y + j < len(g) and
                                      g[y + j][x + i] != "."
                                      for i, j in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                out[y][x] = "R"
    return tuple("".join(r) for r in out)


def _recolour(rows, f):
    return tuple("".join(f(x, c) for x, c in enumerate(r)) for r in rows)


def art16(family, shape):
    """(hotspot, rows) of `shape` at 16 px in `family`'s cells."""
    (hx, hy), rows = ART16[family].get(shape) or SHARED16[shape]
    sand = "O"
    if family == "luna":            # lavender in black, the arrow's left column the rim
        rows = _recolour(rows, lambda x, c: "A" if c == "F" and (shape != "arrow" or x >= 2)
                         else c)
    elif family == "coast":         # cyan sand
        sand = "A"
    rows = _recolour(rows, lambda x, c: sand if c == "S" else c)
    if family == "moy" and shape == "busy":     # a cream glass in black walls, black sand
        rows = rows[:3] + tuple(r.translate(str.maketrans("OF", "FO")) for r in rows[3:12]) \
            + rows[12:]
    if family == "moy" and shape in ("arrow", "hand", "busy"):
        rows = _ring(rows)          # (a ring would close the notches, fatten the beam)
        hx, hy = hx + 1, (hy if shape in ("arrow", "hand") else hy + 1)
    return (hx, hy), rows


def _pixel(family, shape, size):
    k = size // 16
    (hx, hy), rows = art16(family, shape)
    w, h = max(len(r) for r in rows) * k, len(rows) * k
    layers = {}
    for layer, on in zip(LAYERS, _CELLS.get(family, _PLAIN)):
        a = bytearray(w * h)
        for y in range(h):
            r = rows[y // k]
            for x in range(w):
                if x // k < len(r) and r[x // k] in on:
                    a[y * w + x] = 255
        layers[layer] = bytes(a)
    if shape == "hand":             # the fingertip's middle, two cells across
        return hx * k + k - 1, hy * k, w, h, layers
    return hx * k, hy * k, w, h, layers


# -- the rasteriser ------------------------------------------------------------------

def _svg(parts, size, shift=(0, 0)):
    n = (CELL + 2 * PAD) * size // CELL
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="%d %d %d %d"><g transform="translate(%s %s)" fill="#000">%s</g></svg>'
            % (n, n, -PAD, -PAD, CELL + 2 * PAD, CELL + 2 * PAD, _f(shift[0]), _f(shift[1]),
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


def _max(a, b):
    return bytes(max(x, y) for x, y in zip(a, b))


def render(family, shape, size):
    """(hx, hy, w, h, {layer: w*h alpha bytes}) of `shape` in `family` at
    `size` px: the hotspot in the raster's pixels."""
    if family == "pixel" or size == 16:
        return _pixel(family, shape, size)
    st = STYLES[family]
    sh = smooth_shape(family, shape)
    body = sh["body"]
    rnd = sh.get("round", st["round"])
    core = sh.get("core", True) and st["rim"] > 0
    brim = sh.get("rim", st["rim"])
    rim = brim if core else 0
    ow = sh.get("ow", st["ow"])
    edge = rim + ow
    n = (CELL + 2 * PAD) * size // CELL
    k = size / CELL

    tip = max(st["tip"], st.get("tip_px", 0) / k)

    def reach(d):                   # an arrow tip's reach past its body at d
        return tip * d / edge if edge else 0

    # The hotspot: an arrow's apex on a whole pixel's corner, its vertical
    # edge on a pixel's edge; a hand's at the middle of a pixel across, as
    # far into a thick keyline as puts its fill 2 px below (set once the fill
    # is drawn); else the cell's middle.
    if "apex" in sh:
        ap = body[sh["apex"]]
        ax, ay = _apex(ap, edge, rnd, reach(edge))
        if "top" in sh:             # a thick keyline thinner over the hotspot
            ay += edge - rim - sh["top"]
        px, py = (ax + PAD) * k, (ay + PAD) * k
        tx = math.floor(px) + 0.5 if ap[0] == "rect" else round(px)
        ty = math.ceil(py - 1e-6)
        shift = ((tx - px) / k, (ty - py) / k)
        hx, hy = int(math.floor(tx)), ty
    else:
        shift = (0, 0)
        hx = hy = int(round((16 + PAD) * k))

    def ras(parts, d=0.0, flat=False):
        if not parts:
            return bytes(n * n)
        svg = []
        for i, p in enumerate(parts):
            if flat and i == sh.get("apex") and "top" in sh:
                lift = edge - rim - sh["top"]
                svg.append(_part(p[:2] + (p[2] + lift, p[3], p[4] - lift) + p[5:], d, rnd))
            elif flat and i == sh.get("apex") and p[0] == "poly":
                vs = _offset(p[1], d, p[2], rnd, reach(d))
                x, y, _ = vs[p[2]]
                vs.insert(p[2], (x + 1 / k, y, 0))
                svg.append(_rounded(vs))
            else:
                svg.append(_part(p, d, rnd, reach(d)))
        return _alpha(_svg(svg, size, shift))

    rimmed = sh.get("rimmed")       # parts that keep the band where the body does not
    rrim = sh.get("rimmed_rim", brim)
    line = _max(_max(ras(body, edge, sh.get("flat") or "top" in sh), ras(rimmed, rrim + ow)),
                ras(sh.get("marks")))
    cut = ras(sh.get("cut"))
    if core:                        # the band in the fill, the body in the accent
        fill = ras(body, rim)
        accent = _minus(ras(body), cut)
    else:
        fill = _max(_minus(ras(body), cut), ras(rimmed, rrim))
        accent = _minus(_mul(ras(sh.get("accent"), sh.get("accent_d", 0)), fill),
                        ras(sh.get("hole")))
    if "apex" in sh and body[sh["apex"]][0] == "rect":
        hy = max(hy, next(y for y in range(n) if fill[y * n + hx] >= 128) - 2)
    return hx, hy, n, n, {"line": line, "fill": fill, "accent": accent}
