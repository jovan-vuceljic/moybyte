# Map (grep -n a name to jump there):
#   PaintDraw                     Paint's draw half: the first base of paint_app.PaintAppLayer
#   PaintDraw._draw_view          the view canvas's draw: the drawing, a viewed one, or Show
#   PaintDraw._stroke_frame       a frame only a mark changed: the view's changed part alone
#   PaintDraw._look               a desk's drawing viewed on a handheld
"""Paint's draw half (paint_app.PaintAppLayer): what the page's canvases
draw -- the drawing in its view with the ring cursor, a desk's drawing
viewed on a handheld, Show -- the stroke frame that repaints only what a
mark changed, what the bar is lent, the band's words, and the pages a
drawing goes to (a game, a story). Everything else the page draws
(paint_app's `build`).

`PaintDraw` is PaintAppLayer's FIRST base: the layer's `draw` (and the WM's
`retained`/`changed`) stay on the class, and every method here they reach
each frame is found at the first base, the frame-path rule's limit. It
takes paint_app's constants at its FOOT: paint_app imports this module after
binding them, so either may load first. MicroPython-safe; a frame allocates
nothing here that it did not before.
"""

import ui_draw as _ui_draw
import ui_font as _ui_font
from artwork import colour_name
try:
    import moy_loop as _loop
except ImportError:
    _loop = None
from drawing_pages import shown, dot as _dot


class PaintDraw:
    """Paint's draw half, PaintAppLayer's first base (see above)."""

    def _name_bar(self):
        """The bar's title after its back chevron (the page's row after it,
        `build`'s `tools lend="bar"`): the drawing's on a desk and viewed,
        the page a drawing is sent from, else "Paint"."""
        if self.page in ("game", "story"):
            self.bar_title = "Put in a game" if self.page == "game" else "Put in a story"
        elif self.page != "show" and (self.viewer is not None or self.layout.desk):
            self.bar_title = self.doc_title()
        else:
            self.bar_title = "Paint"

    def _lead(self):
        """The band's words before its keys: the tool (Pick's with the
        colour under the cursor), "View only", the desk's status line."""
        if self.page == "show" or self.pop is not None:
            return ""
        if self.viewer is not None:
            return "View only"
        if self.layout.desk:
            return self._status()
        if self.tool == PICK:
            return "Pick" + _dot() + colour_name(self._drip_colour(), _dot()) + _dot().rstrip()
        return TOOLS[self.tool][2] + _dot().rstrip()

    def _pop_at(self):
        """Where the open popover hangs, "X Y W H" on the glass: a viewed
        drawing's More under the bar's end, the rest from the drawing's
        foot at its right; "" on the desk's More, its button's."""
        lay = self.layout
        pop = self.pop
        u = lay.fs
        if pop is None:
            return ""
        if pop == "more" and lay.desk:
            # under the row's More, at the window's right
            return "%d %d 36 36" % (lay.cx + lay.cw - 52, lay.cy + 8)
        if self.viewer is not None:
            w = 194 * u
            return "%d %d %d 1" % (lay.cx + lay.cw - 6 * u - w, lay.cy - 4 * u, w)
        w = (190 if lay.desk else 260 * u if lay.touch else 176 * u) if pop == "colours" else (
            194 * u if pop == "brush" else 182 * u)
        vx, vy, vw, vh = lay.view
        if lay.touch and pop == "colours":
            return "%d %d %d 1" % (vx, vy + vh + 4 * u, vw)
        return "%d %d %d 1" % (vx + vw - 2 * u - w, vy + vh + 4 * u, w)

    def _look_h(self):
        """The viewed drawing's canvas height, and its caption under it (at
        Fit), or Show's."""
        lay = self.layout
        u = lay.fs
        hint_h = 0 if lay.touch or lay.desk else 20 * u
        if self.page == "show":
            return lay.ch, ""
        v = self.viewer
        if v is None:
            return 0, ""
        if v.zoom == FIT:
            bmp = v.fit_bitmap()
            q = v.quarters()
            cap = ("%d \u00d7 %d, made on a desk%sshown at %s" % (v.W, v.H, _dot(), _zoom_word(q))
                   if _ui_font.print_symbols() else
                   "%dx%d, made on a desk - shown at %s" % (v.W, v.H, _zoom_word(q)))
            return (bmp.h if bmp is not None else lay.ch // 2) + 6 * u, cap
        return lay.ch - hint_h, ""

    def _draw_view(self, cv, x, y, w, h):
        """The view canvas's draw at (x, y, w, h): Show, a viewed drawing,
        else the drawing with its cursor."""
        th = self._theme.colors()
        if self.page == "show":
            self._show(cv, th, x, y, w, h)
            return
        if self.viewer is not None:
            self._look(cv, th, x, y, w, h)
            return
        lay = self.layout
        v = lay.view
        if v[0] != x or v[1] != y or v[2] != w or v[3] != h:
            lay.view = (x, y, w, h)
        self._drawing(cv, th)

    def _drip_colour(self):
        """The colour under the cursor; while a stroke is drawn, the one it
        was under when the stroke began."""
        if self._down or self._drawing_key:
            return self._drip_c
        d = self.doc
        c = self._drip_c = d.get(min(d.W - 1, self.cur[0]), min(d.H - 1, self.cur[1]))
        return c

    def _drawing(self, cv, th):
        lay = self.layout
        d = self.doc
        vx, vy, vw, vh = lay.view
        dirty = d.take_dirty()
        if dirty is not None:
            cv.rebake(d.image, *dirty)
        spec = self._spec()
        self._view(cv, th, spec)
        g = self._cursor_at()
        if g is not None:
            cv.clip(vx, vy, vw, vh)
            _ui_draw.cursor(cv, (g[0], g[1], g[2], g[2]))
            cv.clip()

    def _cursor_at(self):
        """(x, y, side) of the ring cursor's rect on the glass, or None where
        it is not drawn."""
        if not self._cursor_shown():
            return None
        s = self.size()
        gx, gy = self._to_glass((self.cur[0] - s // 2, self.cur[1] - s // 2))
        vx, vy, vw, vh = self.layout.view
        if not (vx <= gx < vx + vw and vy <= gy < vy + vh):
            return None
        return (gx, gy, max(2, s * self._quarters() // 4))

    def _cursor_shown(self):
        """The ring cursor: the keys', so not under touch, under a popover,
        or while the pointer draws (the pointer is where it draws)."""
        return not self.layout.touch and self.pop is None and not self._down

    def _view(self, cv, th, spec):
        """The view: the drawing on its ground, its frame and thumbs, and a
        shape's outline while it is dragged."""
        lay = self.layout
        d = self.doc
        vx, vy, vw, vh = lay.view
        x, y, w, h, sx, sy, sw, sh, q = spec
        r = lay.radius
        src = self._src
        src[0] = sx
        src[1] = sy
        src[2] = sw
        src[3] = sh
        full = w == vw and h == vh
        if lay.desk:
            cv.rrect(vx, vy, vw, vh, 10, th["panel"])
            hole = self._hole
            hole[0] = x
            hole[1] = y
            hole[2] = w
            hole[3] = h
            cv.shadow(x, y, w, h, 2, 0, 60, 6, 0, 2, hole)
            cv.picture(d.image, x, y, w, h, 0, src)
            cv.rrect(x - 1, y - 1, w + 2, h + 2, 0, None, th["border"])
        else:
            if w < vw or h < vh:
                cv.rrect(vx, vy, vw, vh, r, th["surface_alt"], th["border"])
            cv.picture(d.image, x, y, w, h, r if full else 0, src)
            if full:
                cv.rrect(vx, vy, vw, vh, r, None, th["border"])
            self._thumbs(cv, th, x, y, w, h, sx, sy, sw, sh)
        self._preview(cv)

    # -- the stroke frame ----------------------------------------------------------
    #
    # A frame whose only change is a mark's -- the doc's pixels, a shape's
    # outline, the ring cursor the keys move, the pointer's sprite over them
    # -- repaints the part of the view
    # those changed and nothing else: the page around it, the toolkit's pass
    # included, is the pixels already there. That holds when the canvas keeps
    # them: the last RETAINED_FRAMES frames all painted this page, the same
    # page (`_epoch`, moved by any change but a mark's and by anything the page
    # reads), into this canvas. The view is then painted again inside the
    # union of what those frames and this one changed, by the same calls a
    # whole frame makes, so the pixels are a whole frame's. A recording canvas
    # keeps nothing, and the loop's drawn-frame count is what says the frames
    # were consecutive. In a desk window the WM says instead what the target
    # holds (`retained`, docs/surface_model_v1.md §14.3), and is told what
    # each frame changed (`changed`).

    def _stroke_frame(self, cv, th):
        """Paint this frame as a stroke frame where it may: True when it did
        (the frame is done), False when the whole page must be painted. Either
        way the doc's marks are baked and this frame's change is recorded."""
        self._sf_ran = True
        d = self.doc
        spec = self._spec()
        c = self._chg
        c[0] = c[1] = 1 << 29
        c[2] = c[3] = -(1 << 29)
        dirty = d.take_dirty()
        if dirty is not None:
            cv.rebake(d.image, dirty[0], dirty[1], dirty[2], dirty[3])
            x, y, w, h, sx, sy, sw, sh, q = spec
            dx, dy, dw, dh = dirty
            _grow(c, x + (dx - sx) * q // 4 - 1, y + (dy - sy) * q // 4 - 1,
                  x + ((dx + dw - sx) * q + 3) // 4 + 1, y + ((dy + dh - sy) * q + 3) // 4 + 1)
        pv = self._pv
        _grow(c, pv[0], pv[1], pv[2], pv[3])
        a, b = self._shape0, self._shape1
        if a is not None and b is not None:
            ga = self._to_glass(a)
            gb = self._to_glass(b)
            pv[0] = min(ga[0], gb[0]) - 2
            pv[1] = min(ga[1], gb[1]) - 2
            pv[2] = max(ga[0], gb[0]) + 3
            pv[3] = max(ga[1], gb[1]) + 3
            _grow(c, pv[0], pv[1], pv[2], pv[3])
        else:
            pv[2] = pv[0]
        cu = self._cu
        _grow(c, cu[0], cu[1], cu[2], cu[3])
        g = self._cursor_at()
        if g is not None:
            # the ring reaches five pixels past the rect it is round
            cu[0] = g[0] - 6
            cu[1] = g[1] - 6
            cu[2] = g[0] + g[2] + 6
            cu[3] = g[1] + g[2] + 6
            _grow(c, cu[0], cu[1], cu[2], cu[3])
        else:
            cu[2] = cu[0]
        # The pointer's sprite, drawn over the page after it: where it was
        # and where it is, when it moved. One that reaches past the view is
        # a whole frame. Its family, shape and size are the console's
        # (runtime/toolkit/pointers.py): at chrome scale cs it is at most
        # 32 px a step (Large), its shadow a pixel per 16 more, and its
        # hotspot anywhere inside it, so the rect round the hotspot is that
        # far each way.
        sp = self._sp
        x0, y0, x1, y1 = sp[0], sp[1], sp[2], sp[3]
        p = self._surf.pointer()
        if p is not None and p[4]:
            u = 34 * self.layout.cs
            sp[0] = p[0] - u
            sp[1] = p[1] - u
            sp[2] = p[0] + u
            sp[3] = p[1] + u
        else:
            sp[2] = sp[0]
        if sp[0] != x0 or sp[1] != y0 or sp[2] != x1 or sp[3] != y1:
            _grow(c, x0, y0, x1, y1)
            _grow(c, sp[0], sp[1], sp[2], sp[3])
            self._sp_out = (not self._in_view(x0, y0, x1, y1)
                            or not self._in_view(sp[0], sp[1], sp[2], sp[3]))
        else:
            self._sp_out = False
        epoch = self._page_epoch(cv, th, d, spec)
        f = _loop.drawn() if _loop is not None else -1
        ok = self._region(cv, f, epoch, self._said)
        if f >= 0:
            e = self._ring[f % (_RING + 1)]
            e[0] = f
            e[1] = epoch
            e[2] = self._own[0]
            e[3] = self._own[1]
            e[4] = self._own[2]
            e[5] = self._own[3]
            self._ring_cv = cv
        if not ok:
            # A whole frame: until the canvas's every buffer holds this page,
            # the frames after it are asked for now, while nothing is drawn,
            # so the next press is a stroke frame from its first.
            if f >= 0 and self._may(cv) and not self._kept(f + 1, epoch, None):
                self._damage.settle()
            return False
        if c[2] > c[0] and c[3] > c[1]:
            self._clip_r = c
            cv.clip(c[0], c[1], c[2] - c[0], c[3] - c[1])
            self._view(cv, th, spec)
            if g is not None:
                # the toolkit's verbs on this page's context, its frame not
                # begun again: the ring is drawn as a whole frame draws it
                self._ui.resume(cv, th)
                _ui_draw.cursor(cv, (g[0], g[1], g[2], g[2]))
            cv.clip()
            self._clip_r = None
        return True

    def _region(self, cv, f, epoch, held=False):
        """Whether this frame may be a stroke frame; when it may, `_chg`
        becomes the part of the view it repaints: this frame's change and
        those of the frames since the canvas's buffer was last painted -- or,
        where the window said what the target holds (`held`), the part it
        said lags. The frame's own change stays in `_own`, which the ring
        records."""
        o = self._own
        c = self._chg
        o[0] = c[0]
        o[1] = c[1]
        o[2] = c[2]
        o[3] = c[3]
        if f < 0 or self._sp_out or not self._may(cv):
            return False
        if held:
            if self._moved:
                return False
            h = self._word
            _grow(c, h[1], h[2], h[3], h[4])
        elif cv is not self._ring_cv or not self._kept(f, epoch, c):
            return False
        lay = self.layout
        vx, vy, vw, vh = lay.view
        if c[0] < vx:
            c[0] = vx
        if c[1] < vy:
            c[1] = vy
        if c[2] > vx + vw:
            c[2] = vx + vw
        if c[3] > vy + vh:
            c[3] = vy + vh
        # The view's rounded corners blend into what is under them, so a
        # second paint there would not be the first's.
        k = 10 if lay.desk else lay.radius
        if k > 0 and c[2] > c[0] and c[3] > c[1]:
            if ((c[0] < vx + k or c[2] > vx + vw - k)
                    and (c[1] < vy + k or c[3] > vy + vh - k)):
                return False
        return True

    def _in_view(self, x0, y0, x1, y1):
        """Whether rect [x0, y0, x1, y1) is empty or inside the view."""
        if x1 <= x0 or y1 <= y0:
            return True
        vx, vy, vw, vh = self.layout.view
        return vx <= x0 and vy <= y0 and x1 <= vx + vw and y1 <= vy + vh

    def _may(self, cv):
        """Whether the page and the canvas are ones a stroke frame paints."""
        if (self.page is not None or self.pop is not None or self.viewer is not None
                or self.toast is not None or self._touch is None
                or getattr(cv, "covered", False)):
            return False
        n = getattr(cv, "RETAINED_FRAMES", 0)
        return 1 <= n <= _RING

    def _kept(self, f, epoch, c):
        """Whether the RETAINED_FRAMES frames before frame `f` all painted
        page `epoch`, so the buffer `f` draws into holds it; `c`, when given,
        grows over what those frames changed since that buffer was painted."""
        n = self._ring_cv.RETAINED_FRAMES
        ring = self._ring
        for i in range(1, n + 1):
            e = ring[(f - i) % (_RING + 1)]
            if e[0] != f - i or e[1] != epoch:
                return False
            if c is not None and i < n:
                _grow(c, e[2], e[3], e[4], e[5])
        return True

    def _page_epoch(self, cv, th, d, spec):
        """The page's epoch: moved by any change a mark is not (the damage's
        own count) and by anything the page outside the view reads."""
        g = self._damage.gen
        moved = g != self._gen
        self._gen = g
        cvm = self._sig_is(0, cv)
        moved = self._sig_is(1, self.layout) | moved
        moved = self._sig_is(2, th) | moved
        moved = self._sig_is(3, d) | moved
        moved = self._sig_is(4, self.page) | moved
        moved = self._sig_is(5, self.pop) | moved
        moved = self._sig_is(6, self.viewer) | moved
        moved = self._sig_is(7, self.toast) | moved
        h = (self.tool | self.shape << 4 | (1 if self.shape_fill else 0) << 6
             | self.size_i << 7 | self.color << 10 | (1 if self._unsaved else 0) << 16
             | (1 if d.history else 0) << 17 | (1 if d.future else 0) << 18
             | (1 if self._touch else 0) << 20
             | (1 if self._art.editable() else 0) << 21)
        moved = self._sig_eq(8, h) | moved
        moved = self._sig_eq(9, self.zoom) | moved
        for i in range(9):
            moved = self._sig_eq(10 + i, spec[i]) | moved
        moved = self._sig_eq(19, self._drip_colour()) | moved
        # The page moved; a new canvas is a new epoch too, but where the
        # window said what the target holds, it is only a new target.
        self._moved = moved
        if moved or cvm:
            self._epoch += 1
        return self._epoch

    def _sig_is(self, i, v):
        if self._sig[i] is v:
            return False
        self._sig[i] = v
        return True

    def _sig_eq(self, i, v):
        if self._sig[i] == v:
            return False
        self._sig[i] = v
        return True

    def _thumbs(self, cv, th, x, y, w, h, sx, sy, sw, sh):
        """A panned view's thumbs: where the view stands in the drawing."""
        d = self.doc
        u = self.layout.fs
        ink = th["ink_dim"]
        if sw < d.W:
            tw = w - 18 * u
            cv.rrect(x + 6 * u + sx * tw // d.W, y + h - 6 * u, max(6, sw * tw // d.W), 3 * u,
                     1 * u, ink)
        if sh < d.H:
            tw = h - 18 * u
            cv.rrect(x + w - 6 * u, y + 6 * u + sy * tw // d.H, 3 * u, max(6, sh * tw // d.H),
                     1 * u, ink)

    def _preview(self, cv):
        a, b = self._shape0, self._shape1
        if a is None or b is None:
            return
        ga = self._to_glass(a)
        gb = self._to_glass(b)
        vx, vy, vw, vh = self.layout.view
        k = self._clip_r
        if k is not None:
            x0, y0 = max(vx, k[0]), max(vy, k[1])
            cv.clip(x0, y0, min(vx + vw, k[2]) - x0, min(vy + vh, k[3]) - y0)
        else:
            cv.clip(vx, vy, vw, vh)
        c = self.color
        if self.shape == 0:
            cv.line(ga[0], ga[1], gb[0], gb[1], c)
        else:
            x, y = min(ga[0], gb[0]), min(ga[1], gb[1])
            w, h = abs(ga[0] - gb[0]) + 1, abs(ga[1] - gb[1]) + 1
            if self.shape == 1:
                (cv.rect if self.shape_fill else cv.rectb)(x, y, w, h, c)
            else:
                (cv.oval if self.shape_fill else cv.ovalb)(x, y, w, h, c)
        if k is not None:
            cv.clip(k[0], k[1], k[2] - k[0], k[3] - k[1])
        else:
            cv.clip()

    def _status(self):
        """The desk foot's sentence: the tool, its size, the zoom, the save."""
        dot = _dot()
        q = self._quarters()
        z = ("Fit, " + _zoom_word(q)) if self.zoom == FIT else _zoom_word(q)
        state = "saved" if not self._unsaved else "changed"
        if not self._art.editable():
            state = "only to look at"
        return TOOLS[self.tool][2] + dot + "size %d" % self.size() + dot + z + dot + state

    # -- popovers ---------------------------------------------------------------------

    # -- the pages ----------------------------------------------------------------------

    def _send_page(self, cv, th, dt):
        """Put in a game or Put in a story over the drawing, its answer a
        toast over the canvas."""
        lay = self.layout
        game = self.page == "game"
        send = self._sent()
        got = send.draw(cv, th, lay.page, lay.desk, dt)
        if got is None:
            return
        name = send.name
        self._close_sent()
        self.page = None
        self._ui.reset()
        self.fill_owed = True
        if game:
            if got:
                self._say(shown(name) + " is the background of " + got)
            else:
                self._say(self._art.copies.last_error or "Can't put it there", "warn", True)
            return
        title, slide, undo = got
        if slide:
            self._say("Added as slide %d of %s%sUndo" % (slide, title, _dot()), undo=undo)
        else:
            self._say("Can't add it to " + title, "warn", True)

    def _look(self, cv, th, x, y, w, h):
        """A desk's drawing viewed on a handheld, in the look canvas's rect:
        at Fit the quarter-size picture on its shadow (its caption is the
        page's), else the window on it and a sixteenth of the whole showing
        where it is."""
        lay = self.layout
        v = self.viewer
        u = lay.fs
        if v.zoom == FIT:
            bmp = v.fit_bitmap()
            if bmp is not None:
                bx = x + (w - bmp.w) // 2
                by = y + 6 * u
                cv.shadow(bx, by, bmp.w, bmp.h, 2, 0, 60, 6, 0, 2, (bx, by, bmp.w, bmp.h, 0))
                cv.picture(bmp, bx, by, bmp.w, bmp.h)
                cv.rrect(bx - 1, by - 1, bmp.w + 2, bmp.h + 2, 0, None, th["border"])
            return
        v.view = (x, y, w, h)
        bmp, k = v.window()
        if bmp is not None:
            cv.picture(bmp, x, y, bmp.w * k, bmp.h * k)
        mini = v.mini()
        if mini is not None:
            mx = x + w - 10 * u - mini.w
            my = y + 6 * u
            cv.rect(mx - 2 * u, my - 2 * u, mini.w + 4 * u, mini.h + 4 * u, th["surface"])
            cv.picture(mini, mx, my, mini.w, mini.h)
            fx, fy, fw, fh = v.frame()
            cv.rectb(mx + fx // 16, my + fy // 16, max(2, fw // 16), max(2, fh // 16),
                     th["accent"])
            cv.rectb(mx - 2 * u, my - 2 * u, mini.w + 4 * u, mini.h + 4 * u, th["border"])

    def _show(self, cv, th, x, y, w, h):
        """Show: the drawing alone on the show canvas, black around it; any
        key or tap returns."""
        cv.rect(x, y, w, h, self.names["black"])
        v = self.viewer
        if v is not None:
            sw = w
            sh = v.H * w // v.W
            if sh > h:
                sh = h
                sw = v.W * h // v.H
            bmp = v.show_bitmap(sw, sh)
            if bmp is not None:
                cv.picture(bmp, x + (w - sw) // 2, y + (h - sh) // 2, sw, sh)
            return
        d = self.doc
        dirty = d.take_dirty()
        if dirty is not None:
            cv.rebake(d.image, *dirty)
        sw = w
        sh = d.H * w // d.W
        if sh > h:
            sh = h
            sw = d.W * h // d.H
        cv.picture(d.image, x + (w - sw) // 2, y + (h - sh) // 2, sw, sh)


# paint_app's tools, zooms and helpers, imported last (see above).
from paint_app import FIT, PICK, TOOLS, _RING, _grow, _zoom_word
