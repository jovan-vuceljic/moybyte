"""G9's engine half on the host layer: an `image` value found, decoded,
cached under a byte budget and drawn, the app running no code for it.

A drawing stands whole in its tile, letterboxed at its own aspect (a
cover PNG and a picture the app draws fill it). A card or picture asks
`peek(pic, w, h)` while it draws: a decoded picture,
or None, and then the pair is owed. Each console frame, before it paints,
calls the layer's `idle_step` while it owes one (`view_owed`), which
decodes one owed picture and damages the page: the page is not quiet until
it shows every picture it holds. A picture that does not decode is failed for the session, traced
once. The cache keeps decoded pixels under `budget` bytes, the least
recently drawn let go first ("redraw on exposure": it is owed again the
next time a card shows it).

A cart's cover (`image.cart(path)`) is the shell's cover cache's
(`covers`, runtime/shell/cover_cache.py's CoverPictures): the engine neither decodes nor
copies it, and counts none of it in its budget. It holds the cache's
picture and draws its pixels while the cache keeps them; one the cache let
go (its pixels None) is asked for again, and a build still in flight stays
owed, a slice of it each idle step.

What this host layer cannot show: a decode off the frame's thread (here it
is the frame's own time), a cache shared across apps, and a budget the
engine sets per board.
"""
import collections

import ui_draw as _ui_draw
import uitree as S

def budget_for(w, h):
    """The app's picture budget: two glasses of RGB565. A drawing's picture
    keeps its indices and its RGB565 bake, three bytes a pixel, and a view
    counts its cards cut at its edges whole: a view of drawings' cards
    (My Art's, twelve on a T-Deck) fits it where one glass did not."""
    return w * h * 4


def _tr(app, text):
    was, S._NOW.app = S._NOW.app, app
    try:
        S._trace("image", "", text)
    finally:
        S._NOW.app = was


def _let_go(got):
    """A picture the cache let go: a layer an app's drawer made goes back."""
    if got[0] in ("layer", "clear"):
        got[1].release()


class PicEngine:
    def __init__(self, app, files, swapped, budget, covers=None):
        self.app, self.files, self.swapped, self.budget = app, files, swapped, budget
        self.covers = covers                       # the cover cache's pictures, for image.cart
        self.carts = {}                            # (pic, w, h) -> ("cart", the cache's picture, 0)
        self.cart_none = {}                        # a cart pic -> the cache's gen when it had no cover
        self.cart_gen = {}                         # a cart pic -> the pictures taken for it
        self.cache = collections.OrderedDict()     # (pic, w, h) -> (draw kind, pixels, bytes)
        self.used = 0
        self.failed = {}                           # (pic, gen) -> why
        self.owed = []
        self.seen = set()                          # (pic, w, h) the frame drew
        self.stats = dict.fromkeys(("decoded", "failed", "refused", "evicted"), 0)

    # -- the frame's side ------------------------------------------------------------

    def begin_frame(self):
        self.owed.clear()
        self.seen.clear()

    def peek(self, pic, w, h):
        k = (pic, w, h)
        self.seen.add(k)
        if pic.kind == "cart":
            got = self.carts.get(k)
            if got is not None and got[1].pix is not None:
                return got
            if self.cart_none.get(pic) != self._covers_gen() and k not in self.owed:
                self.owed.append(k)
            return None
        got = self.cache.get(k)
        if got is not None:
            self.cache[k] = self.cache.pop(k)       # the most recent last
            return got
        if (pic, self.gen_of(pic)) not in self.failed and k not in self.owed:
            self.owed.append(k)
        return None

    def state(self, pic, w, h):
        """none, loading, failed or shown: what the card shows."""
        if pic is None:
            return "none"
        if pic.kind == "cart":
            got = self.carts.get((pic, w, h))
            if got is not None and got[1].pix is not None:
                return "shown"
            return "failed" if self.cart_none.get(pic) == self._covers_gen() else "loading"
        if (pic, w, h) in self.cache:
            return "shown"
        if (pic, self.gen_of(pic)) in self.failed:
            return "failed"
        return "loading"

    def forget_store(self, path):
        """Store picture `path`'s file changed: its pictures and its
        failure go. Answers whether any were held."""
        held = False
        for k in [k for k in self.cache if k[0].kind == "store" and k[0].key == path]:
            self.used -= self.cache.pop(k)[2]
            held = True
        for f in [f for f in self.failed if f[0].kind == "store" and f[0].key == path]:
            del self.failed[f]
        return held

    def draw(self, cv, got, x, y, w, h, r=0):
        """A picture held (`peek`'s) over (x, y, w, h); a cover's corners
        rounded to `r` (the theme's stepped corners where it steps them)."""
        kind, pix, _n = got
        if kind == "cart":
            if pix.pix is not None:
                cv.cover(pix.pix, pix.w, 0, 0, pix.w, pix.h, x, y, w, h, r,
                         bool(r) and bool(_ui_draw.depth()[4]))
        elif kind == "cover":
            side = pix[0]
            cv.cover(pix[1], side, 0, 0, side, side, x, y, w, h, r,
                     bool(r) and bool(_ui_draw.depth()[4]))
        elif kind == "layer":
            cv.blit565_resize(pix._buf, pix.w, pix.h, x, y, w, h)
        elif kind == "clear":   # its corner's colour left out: the tile under it shows there
            b = pix._buf
            cv.blit565(b, pix.w, pix.h, x + (w - pix.w) // 2, y + (h - pix.h) // 2, 1, b[0] | b[1] << 8)
        else:                   # a drawing: centred in its tile at its own aspect
            cv.picture(pix, x + (w - pix.w) // 2, y + (h - pix.h) // 2, pix.w, pix.h)

    # -- the idle side -----------------------------------------------------------------

    @property
    def idle_owed(self):
        # a loop, not any() over a generator: one naming self makes self a cell
        # on every call, and the console asks every idle frame
        refused = getattr(self, "refused", ())
        for k in self.owed:
            if k not in refused:
                return True
        return False

    def idle_step(self):
        view = frozenset(self.seen)
        if view != getattr(self, "_refused_view", None):
            self.refused, self._refused_view = set(), view     # the view moved: ask again
        owed = [k for k in self.owed if k not in self.refused]
        if not owed:
            return False
        pic, w, h = k = owed[0]
        self.owed.remove(k)
        if pic.kind == "cart":
            return self._cart_step(k)
        try:
            got = self._decode(pic, w, h)
        except MemoryError:
            got = None
        if isinstance(got, str):
            self.failed[(pic, self.gen_of(pic))] = got
            self.stats["failed"] += 1
            _tr(self.app, "%r %dx%d failed: %s" % (pic, w, h, got))
            return True
        if not self._room(got[2]):
            self.refused = getattr(self, "refused", set())
            if k not in self.refused:
                self.refused.add(k)
                self.stats["refused"] += 1
                _tr(self.app, "%r %dx%d not kept: the pictures in view fill the budget (%d of %d bytes)" % (
                    pic, w, h, self.used, self.budget))
            return False
        self.cache[k] = got
        self.used += got[2]
        self.stats["decoded"] += 1
        _tr(self.app, "%r %dx%d decoded, %d bytes (cache %d, %d of %d bytes)" % (
            pic, w, h, got[2], len(self.cache), self.used, self.budget))
        return True

    def _room(self, n):
        """Room for n bytes: the least recently drawn picture out of view let
        go first; a picture in view is never let go, so a budget the view
        overfills keeps the rest veiled (loading) rather than thrash."""
        seen = self.seen
        while self.used + n > self.budget:
            k = next((k for k in self.cache if k not in seen), None)
            if k is None:
                return False
            old = self.cache.pop(k)
            self.used -= old[2]
            _let_go(old)
            self.stats["evicted"] += 1
            _tr(self.app, "%r %dx%d evicted (least recently drawn, out of view), %d bytes back" % (
                k[0], k[1], k[2], old[2]))
        return True

    def forget_own(self, key):
        """The app put own picture `key` again: its decoded pixels let go.
        Answers whether any were held (a card showing them changes)."""
        held = False
        for k in [k for k in self.cache if k[0].kind == "own" and k[0].key == key]:
            old = self.cache.pop(k)
            self.used -= old[2]
            _let_go(old)
            held = True
        return held

    def _covers_gen(self):
        return self.covers.gen() if self.covers is not None else 0

    def _cart_step(self, k):
        """A slice of cart cover `k`'s build in the cover cache: True once
        it holds the picture, which the page draws again to show; a build
        still in flight stays owed, and a cart with none is not asked again
        until the cache changes."""
        pic, w, h = k
        img = self.covers.picture(pic.key, max(w, h)) if self.covers is not None else None
        if img:
            self.carts[k] = ("cart", img, 0)
            self.cart_gen[pic] = self.cart_gen.get(pic, 0) + 1
            return True
        if img is None:
            self.cart_none[pic] = self._covers_gen()     # asked again once the cache changes
            self.stats["failed"] += 1
            _tr(self.app, "%r has no cover" % (pic,))
            return False                                # its card shows its icon as it did
        self.owed.append(k)
        return False

    def gen_of(self, pic):
        """What moves with the picture's pixels: an app's own picture's puts,
        a store file's changes, a cart cover's pictures taken from the cache."""
        if pic.kind == "cart":
            return self.cart_gen.get(pic, 0)
        if pic.kind == "own":
            return S.pictures.gen_of(self.app, pic.key)
        return S.pictures.store_gen.get(pic.key, 0)

    # -- decoders ----------------------------------------------------------------------

    def _bytes(self, pic):
        if pic.kind == "store":
            kind, name = pic.key.split("/")
            blob, err = self.files.load(kind, name)
            if err is not None or not blob:
                return None, "no file %s" % pic.key
            return blob, None
        src = S.pictures.source(self.app, pic.key)
        if src is None:
            return None, "no picture %r put" % pic.key
        if src[0] == "idx":
            import moy_carts
            return moy_carts.encode_moyimg(src[1], src[2], src[3]), None
        return src[1], None

    def _decode(self, pic, w, h):
        src = S.pictures.source(self.app, pic.key) if pic.kind == "own" else None
        if src is not None and src[0] == "render":
            lay = src[1](w, h)
            if lay is None or lay.w != w or lay.h != h:
                return "not drawn at %dx%d" % (w, h)
            return ("clear" if src[2] else "layer", lay, w * h * 2)
        blob, why = self._bytes(pic)
        if blob is None:
            return why
        raw = blob.encode() if isinstance(blob, str) else bytes(blob)
        if raw[:8] == b"\x89PNG\r\n\x1a\n":
            import cover_png as _cp
            side = _cp.SIDE
            while side // 2 >= max(w, h) and _cp.SIDE // (side // 2) in (1, 2, 4, 8):
                side //= 2
            pix = _cp.decode(raw, _cp.SIDE // side, _cp.RGB565_SW if self.swapped else _cp.RGB565, None, None)
            if pix is None:
                return "not a cover PNG"
            return ("cover", (side, pix), side * side * 2)
        from artwork import picture_size, read_cover
        from file_widgets import Bitmap
        # a drawing stands whole in its tile, letterboxed: its edges are the drawer's
        size = picture_size(raw)
        if size is not None:
            fw, fh = w, size[1] * w // size[0]
            if fh > h:
                fw, fh = size[0] * h // size[1], h
            w, h = max(1, fw), max(1, fh)
        pix = bytearray(w * h)
        if read_cover(raw, pix, w, h) is None:
            return "not a picture"
        return ("bmp", Bitmap(w, h, pix), w * h * 3)        # indices, and the RGB565 bake the canvas keeps
