# Map (grep -n a name to jump there):
#   CardsLayout              the Config tab's content rect under the bar
#   CardsLayer               the Config tab: hosts its pages (editor_settings.py)
#   CardsLayer._rows         the cards' rows, from the cart's `edit` fields
#   CardsLayer.open_file     a project file routed to what opens it
"""The Editor's Config tab ("Make it mine", #3/#15) as its own Layer: the
host of its `uitree` pages (editor_settings.py) in the content rect under
the bar, the handheld's tab and, through the desk's pane viewport, its
Settings pane.

CART STATE lives on the open Project: the tab reads `ws.run.project.config`
/ `ws.run.project.cart`, sets a card's value in the config in place
(`Project.record_config` keeps the undo), and PLAY in the bar re-runs the
cart. A field that fails `_validate_field` stays off the page (#94), so a
bad hand-edited manifest costs one card, never the tab.

Files ROUTES each project file: any of the cart's SCRIPTS to the Code tab
(#89: its whole load order, not just main), an asset to its own tab, a
picture to Paint, a text file through `ws.open_project_file`, which opens it
in the editor handle and returns HERE. Cart info edits the manifest's
title and author through `Project.commit_manifest`; New script, offered
only where a second script would run (`moy_carts.multi_script`), is the ONE
door that adds a file to a cart (the Code tab's scripts menu opens it too).
"""

import ui_draw as _ui_draw
import uitree as _tree
import uitree_app
import editor_settings      # declared at import, never inside another page's handler
from layers import Layer
import layout_base as _layout_base
import text_modes as _modes
import chrome_ops as _ch_ops
from layout_base import LayoutBase

# The project's files (step 5 of docs/theme_and_shell_2026-11.md §10) are reached from
# the Config tab rather than the Files app because the loader has to stay in the
# loop -- what it opens is reached through the Editor, which re-reads the folder
# on the way back (Workstation.open_project_file).
#
# A project file that is an ASSET is opened by the TAB that owns it, never as
# text -- the list is a router, not a viewer. `images/` is deliberately absent: a
# cart's image assets are copies the WALL/GAME flow made from a drawing and no
# tab edits one in place, so a picture takes the picture door instead.
_ASSET_TABS = {
    "sprites.moygfx": "paint",
    "map.moymap": "map",
    "sounds.json": "music",
    "blocks.json": "blocks",
}
_ASSET_SUBDIR_TABS = {"scenes": "scene"}

# The last code row of that list on a cart whose runtime runs more than one
# script: the ONE door that adds a file to a cart (#89). A sentinel rather than a
# real name, because the list's rows come from the store and a real file could be
# called anything -- including this.
_NEW_ROW = "New script"

# The Files page's words for what a file is and the tab it opens in.
_FILE_WORDS = {"sprites.moygfx": "Sprites", "map.moymap": "Map", "sounds.json": "Sounds",
               "blocks.json": "Blocks"}
_TAB_WORDS = {"code": "Code", "paint": "Art", "map": "World", "music": "Sound",
              "blocks": "Blocks", "scene": "World"}
_TAB_ICONS = {"code": "code", "paint": "sprite", "map": "map", "music": "music",
              "blocks": "blocks", "scene": "scene"}


class _Damage:
    def __init__(self, ws):
        self.ws = ws

    def all(self):
        self.ws.mark_dirty()


def _picker(f):
    """Whether choice card `f` is a picker of its pictures: its sprites, its
    backgrounds, or more than two icons."""
    disp = f.get("display")
    return disp in ("sprite-tiles", "bg-thumbs") or (
        disp == "choice-icons" and (len(f["choices"]) != 2 or bool(f.get("names"))))


class CardsLayout(LayoutBase):
    """The Config tab's geometry: the content rect under the bar (`cx`,
    `cy`, `cw`, `ch`) its pages draw in, from the SYSTEM canvas size and
    font scale, the T-Deck's 320x240 by the same formulas as every canvas."""


class CardsLayer(Layer):
    """The Config tab's content Layer (SYSTEM domain): its pages fill the
    content rect under the bar on the reflowed system canvas."""

    id = "cards"
    domain = "system"

    # A card field MAY carry an optional `display` hint -- "gauge" | "count" |
    # "choice-icons" | "sprite-tiles" | "bg-thumbs" (a choice-icons choice of
    # two is a toggle and of more a picker of its icons, a sprite-tiles or
    # bg-thumbs one a picker of its sprites or backgrounds).
    _DISPLAYS = ("gauge", "count", "choice-icons", "sprite-tiles", "bg-thumbs")
    _CELL_DISPLAYS = ("choice-icons", "sprite-tiles", "bg-thumbs")

    def __init__(self, ws, names, err_text):
        self.ws = ws
        self._NAMES = names
        self._err_text = err_text
        self._ui_mod = editor_settings
        self._host = _ui_draw.AppHost()
        self.page = None              # the pages' engine, made at the tab's first open
        self._opened = False
        self._shown = None            # what `_sync` wrote last
        self._count = (None, 0)       # (the cart's path, its files)
        self._pics = (None, ())       # (what the pickers' pictures were drawn from, their puts)
        self._band = None             # what the page's band adds: F6, a desk pane's
        sc = ws.sys_canvas
        self.layout = CardsLayout(sc.w, sc.h, getattr(sc, "font_scale", 1))

    def relayout(self, w, h, fs, cs=None):
        """Rebuild the geometry (#39 step 3) -- called by ws.relayout on a
        font-scale change."""
        self.layout = CardsLayout(w, h, fs, chrome_scale=cs)

    def reset(self):
        """Back to the cards page with no dialog (called by ws.open on a
        fresh cart)."""
        if self._opened:
            self.page.close()
            self._opened = False
        self._count = (None, 0)

    # -- the page's state ---------------------------------------------------------

    @property
    def s(self):
        """The pages' state, this tab's values in it."""
        if not self._opened:
            self._open()
        self.page._bind()
        return self._ui_mod.s

    def run(self, name, *args):
        """Run the page's action or hook `name` now, the page open."""
        if not self._opened:
            self._open()
        self.page._bind()
        self.page.run_action(self.page.actions[name], args, "host")
        self.ws.mark_dirty()

    def _fields(self):
        ws = self.ws
        if not ws.editor_app._offers("mine"):
            return []               # its run reads no config.json
        return [f for f in (ws.cart.get("edit") or []) if not self._validate_field(f)]

    def _get(self, f):
        return self.ws.run.project.config.get(f["key"], f.get("default"))

    def _set(self, f, v):
        ws = self.ws
        old = self._get(f)
        if v == old:
            return
        ws.run.project.config[f["key"]] = v
        ws.run.project.record_config(f["key"], old, v)
        ws.mark_dirty()

    def field(self, key):
        for f in self._fields():
            if f["key"] == key:
                return f
        return None

    def _rows(self):
        """The cards' rows: an `int` a slider, a two-way choice a toggle, a
        picture choice a picker of its pictures (`cfg:KEY:K`, `_pictures`),
        any other choice a cycle through its names, one a line."""
        label = self._ui_mod.card_label
        rows = []
        for f in self._fields():
            cur = self._get(f)
            row = {"id": f["key"], "label": label(f), "shape": "int", "v": 0, "lo": 0, "hi": 0,
                   "on": False, "k": 0, "names": "", "pics": ""}
            if f["type"] == "int":
                lo, hi = f.get("min", 0), f.get("max", 100)
                try:
                    v = int(cur)
                except (TypeError, ValueError):
                    v = lo
                row.update(shape="int", v=v, lo=lo, hi=hi)
            else:
                ch = f["choices"]
                idx = ch.index(cur) if cur in ch else 0
                two = len(ch) == 2 and not f.get("names")
                if _picker(f):
                    row.update(shape="pics", k=idx, pics="\n".join(
                        ["own:cfg:%s:%d" % (f["key"], k) for k in range(len(ch))]))
                elif two:
                    row.update(shape="two", on=idx == 1)
                else:
                    names = f.get("names") or ch
                    row.update(shape="cycle", k=idx, names="\n".join(
                        [str(names[i] if i < len(names) else c) for i, c in enumerate(ch)]))
            rows.append(row)
        return rows

    def _sync(self):
        """The cart's values the page shows, handed to its `sync` hook where
        they moved; a card that fails to build leaves the reason, exact."""
        ws = self.ws
        cart = ws.cart or {}
        why = (cart.get("broken") or "") if ws.run.project.cart else ""
        try:
            rows = () if why else self._rows()
            vals = (rows, "" if why else (ws.editor_app.missing_note() or ""), why,
                    "The manifest didn't read" if why else "", bool(why),
                    str(cart.get("title") or ""), str(self._file_count()), self._pictures())
        except Exception as exc:  # noqa: BLE001 -- a card the checks missed must not take the frame
            ws.cart_error = self._err_text(exc)
            print("Moybyte cards error:", exc)
            vals = ((), "", ws.cart_error, "This page didn't draw", False, "", "", ())
        if vals != self._shown:
            self._shown = vals
            self.run("sync", vals)

    def _file_count(self):
        """The project's files, counted once a cart (the list reads the
        store) and again each time Files lists them."""
        ws = self.ws
        path = ws.cart.get("path")
        if self._count[0] != path:
            n = 0
            try:
                kind = ws.carts_store.project_kind(path)
                n = len(ws.with_sd(lambda: ws.carts_store.list_files(kind, ws.carts_root)))
            except Exception:  # noqa: BLE001 -- an unreadable folder counts none
                pass
            self._count = (path, n)
        return self._count[1]

    # -- what the page's handlers ask ---------------------------------------------

    def set_int(self, key, v):
        """A slider moved: a key's or a nudge's step is the card's step, a
        drag lands on the nearest step."""
        f = self.field(key)
        if f is None:
            return
        lo, hi = f.get("min", 0), f.get("max", 100)
        try:
            was = int(self._get(f))
        except (TypeError, ValueError):
            was = lo
        step = max(1, int(f.get("step", 1)))
        d = v - was
        if d and abs(d) < step:
            v = was + (step if d > 0 else -step)
        else:
            v = lo + ((v - lo + step // 2) // step) * step
        self._set(f, max(lo, min(hi, v)))

    def set_choice(self, key, k):
        f = self.field(key)
        if f is not None:
            self._set(f, f["choices"][k])

    # -- a picker's pictures ----------------------------------------------------------

    def _pictures(self):
        """The pickers' pictures to put, `(key, render)` each: drawn again
        where what they show moved (the cards, the sheet's tiles, the look,
        the text size), the same tuple otherwise."""
        ws = self.ws
        fields = [f for f in self._fields() if f["type"] != "int" and _picker(f)]
        sheet = ws.run.project.sheet
        src = (repr(fields), id(sheet), getattr(sheet, "gen", 0), ws.look.look_gen, self.layout.fs)
        if src != self._pics[0]:
            self._pics = (src, tuple(("cfg:%s:%d" % (f["key"], k), self._render(f, k))
                                     for f in fields for k in range(len(f["choices"]))))
        return self._pics[1]

    def _render(self, f, k):
        """Choice `k` of picker card `f` drawn at the size its tile asks, on
        a ground of the colour key, which `clear=True` leaves out."""
        def render(w, h):
            lay = self.ws.sys_canvas.new_layer(w, h)
            lay.fill565(0, 0, w, h, 0xF81F)      # magenta: no colour a choice draws in
            self.draw_choice(lay, f, k, (0, 0, w, h))
            return lay
        return render

    def _resolve_tiles(self, f):
        """For a `sprite-tiles` field, the list of sprite tile ids its choices map
        to. `choices` may be ints (tile ids directly) or names paired with a
        parallel `tiles` list. Returns ints; non-resolvable entries become 0."""
        out = []
        for c in f.get("tiles") or f.get("choices", []):
            try:                               # a non-numeric entry must not escape the draw (#15)
                out.append(int(c))
            except (TypeError, ValueError):
                out.append(0)
        return out

    def draw_choice(self, cv, f, k, rect):
        """Choice `k`'s picture of a picker card `f` in `rect` on `cv`: its
        sprite at the largest whole zoom the rect holds, its glyph, or its
        background's preview."""
        x, y, w, h = rect
        disp = f.get("display")
        if disp == "sprite-tiles":
            tiles = self._resolve_tiles(f)
            sheet = self.ws.run.project.sheet
            if sheet is None:
                return
            img = sheet.tile_image(tiles[k] if k < len(tiles) else 0, 0)
            z = max(1, min(w, h) * 3 // 4 // 8)
            cv.spr(img, x + (w - 8 * z) // 2, y + (h - 8 * z) // 2, z)
        elif disp == "bg-thumbs":
            ch = f.get("choices") or []
            m = max(2, min(w, h) // 8)
            self._draw_bg_thumb(cv, str(ch[k]) if k < len(ch) else "", (x + m, y + m, w - 2 * m, h - 2 * m))
        else:
            icons = f.get("icons") or []
            side = max(12, min(w, h) // 2)
            _ch_ops.glyph(cv, icons[k] if k < len(icons) else "dot",
                          (x + (w - side) // 2, y + (h - side) // 2, side, side), self.ws.theme_colors["ink"])

    # Each bg-thumbs choice is drawn as a tiny "what the screen will look like"
    # preview. A cart reads the chosen name in cfg("bg") and paints to match.
    # "night"/"stripes" get a patterned thumbnail; any other name renders as a
    # solid swatch via NAMES.get, so arbitrary palette colors (e.g. "indigo")
    # just work -- no preset list to keep in sync.

    def _draw_bg_thumb(self, cv, name, rect):
        """Paint a small preview of background preset `name` inside `rect`."""
        NAMES = self._NAMES
        fs = self.layout.fs
        x, y, w, h = rect
        if name == "night":                              # starfield
            cv.rect(x, y, w, h, NAMES["black"])
            for sx, sy in ((4, 4), (14, 9), (24, 5), (30, 15), (9, 17), (20, 12)):
                cv.rect(x + sx * fs, y + sy * fs, fs, fs, NAMES["white"])
        elif name == "stripes":
            for i in range(0, w, 6 * fs):
                cv.rect(x + i, y, min(3 * fs, w - i), h, NAMES["indigo"])
                if i + 3 * fs < w:
                    cv.rect(x + i + 3 * fs, y, min(3 * fs, w - i - 3 * fs), h, NAMES["dark_blue"])
        else:                                            # a solid color swatch
            cv.rect(x, y, w, h, NAMES.get(name, NAMES["black"]))

    def meta(self):
        cart = self.ws.run.project.cart or {}
        return str(cart.get("title") or "")[:24], str(cart.get("author") or "")[:24]

    def new_sub(self):
        main = (self.ws.run.project.cart or {}).get("main", "main.py")
        return "A %s file beside %s" % ("Lua" if main.endswith(".lua") else "Python", main)

    def commit_meta(self, title, author):
        """Cart info's Save: "" where it saved, else why it stays open."""
        title = title.strip()
        if not title:
            return "Give it a title."     # never persist a blank title
        if not self.ws.run.project.commit_manifest(title=title, author=author.strip()):
            return "It didn't save. Try again."
        return ""

    def commit_newf(self, typed):
        """New script's Add: "" where the file was made and the Code tab
        opened on it, else why it stays open."""
        ws = self.ws
        cart = ws.run.project.cart
        name = self._newf_filename(typed)
        if name is None:
            return "Start its name with a letter."
        made = ws.with_sd(lambda: ws.carts_store.add_source(cart, name, "-- " + name + "\n"))
        if made is None:
            return "There's a file with that name."
        self._leave_files()
        ws.editor_app.set_tab("code")
        ws.text.open_code_file(made)
        return ""

    def new_script(self):
        """New script from the Code tab's scripts menu: the cards page and its dialog."""
        self.run("new_script")

    # -- the page -------------------------------------------------------------------

    def _open(self):
        if self.page is None:
            self.page = uitree_app.hosted_page(editor_settings.cards_page, self._host,
                                               _Damage(self.ws), gen=True, env=self)
        if not self._opened:
            self._opened = True
            self._shown = None
            self.page.open()
        self._sync()

    def page_host(self):
        return self._host

    @property
    def view_owed(self):
        """A picker's picture in view waits for its first draw (uitree_pics):
        the console steps it before the frame paints."""
        return self._opened and self.page.view_owed

    def idle_step(self):
        self.page.idle_step()

    def draw(self, dt):
        ws = self.ws
        ws.reset_canvas_state()          # game-canvas hygiene (degradation shares it)
        self._open()
        lay = self.layout
        r = (lay.cx, lay.cy, lay.cw, lay.ch)
        desk = _layout_base.metric_class() == _layout_base.DESK
        # a desk pane's band names the key to the next pane, where the input in use has it
        band = ("F6", "Next pane") if desk and _ui_draw.hint_kind() == "keys" else ()
        if band != self._band:
            self._band = band
            self.page.band_extra(band)
        cv = ws.sys_canvas
        self._host.begin(cv, ws.theme_colors, r, desk)
        self.page.paint(dt, cv, ws.theme_colors, r, desk)
        self._host.end()
        if not self._host.still():
            ws.request_frame()

    def _on_link(self):
        """Whether the focus is on a stop A takes (a door, a cycle, a picker:
        the page's one seg)."""
        kind = self.page.stop_kinds().get(self.page.focus_key)
        return kind in ("link", "button", "field", "cycle", "seg")

    def handle_input(self, i):
        ws = self.ws
        self._open()
        s = self.s
        if (s.asking == "none" and not self.page.has_page() and not self._on_link()
                and (i.pressed("run") or i.pressed("a"))):
            if s.fixable:
                self.run("files")              # a broken manifest's one door, never PLAY
            elif not s.broken:
                ws.defer(ws.text.leave_menu)   # Enter PLAYs (a device's Enter is "a")
            return True
        if (i.pressed("b") or i.pressed("stop")) and self.page.back():
            return True
        self.page.keys(i)
        if not self.page.has_page():
            ws.home.leave_or_home(ws.spine.exit)
        return True

    def handle_pointer(self, px, py, click):
        if click and self.ws.bar_layer.handle_bar_tap("menu", px, py):
            return True
        self._open()
        self.page.point(px, py, click)
        return True

    def has_page(self):
        return bool(self._opened and self.page.has_page())

    def back(self):
        """A dialog closes, else Files goes back to the cards."""
        return bool(self._opened and self.page.back())

    def cancel(self):
        """Mic in a dialog: it closes, as its Cancel does."""
        if self._opened and self.s.asking != "none":
            self.run("cancel")
            return True
        return Layer.cancel(self)

    # -- the checks ------------------------------------------------------------------

    def _validate_field(self, f):
        """Sanity-check ONE `edit` field definition: returns a short human
        reason it can't be drawn/stepped, or None when it's fine. The Settings
        page (`SettingsPage._fields`) leaves a field that fails it off the
        page, so a bad hand-edited manifest.json/config.json costs one card,
        never the Config tab -- draw()'s try/except stays the net for a
        genuinely UNFORESEEN crash; this catches the KNOWN-bad shapes (missing
        key/type, min>max, a zero step, empty/missing choices, an unknown or
        type-mismatched `display`)."""
        if not isinstance(f, dict):
            return "not a card"
        key = f.get("key")
        if not key or not isinstance(key, str):
            return "missing key"
        t = f.get("type")
        if t not in ("int", "choice"):
            return "bad type %r" % (t,)
        if t == "int":
            lo, hi = f.get("min"), f.get("max")
            if lo is not None and hi is not None:
                try:
                    if float(lo) > float(hi):
                        return "min > max"
                except (TypeError, ValueError):
                    return "bad min/max"
            step = f.get("step", 1)
            try:
                if float(step) == 0:
                    return "step is 0"
            except (TypeError, ValueError):
                return "bad step"
        else:                                             # "choice"
            ch = f.get("choices")
            if not isinstance(ch, list) or not ch:
                return "no choices"
        disp = f.get("display")
        if disp is not None and disp not in self._DISPLAYS:
            return "bad display %r" % (disp,)
        if disp in ("gauge", "count") and t != "int":
            return "display needs type int"
        if disp in self._CELL_DISPLAYS and t != "choice":
            return "display needs type choice"
        return None

    # -- Files: the project's own files (step 5) -----------------------------
    #
    # A ROUTER over one project folder, not a viewer: a text-shaped file (by
    # `text_modes`) opens in the shell's editor handle through the SAME request
    # door Notes uses, the cart's scripts open the Code tab, and an asset
    # opens the tab that owns it. Everything it lists comes from the store's
    # `list_files` on the project KIND (moy_carts.PROJECT_KIND), so the page
    # never spells a cart's layout itself.

    def listing(self):
        """(the Files page's rows, the line saying why it lists none): the
        cart's scripts first, New script last among them, then the rest,
        each its icon, its word and the tab it opens in."""
        ws = self.ws
        cart = ws.run.project.cart
        path = (cart or {}).get("path")
        rows, msg = (), ""
        try:
            kind = ws.carts_store.project_kind(path)
            rows = tuple(ws.with_sd(lambda: ws.carts_store.list_files(kind, ws.carts_root)))
        except Exception as exc:  # noqa: BLE001 -- an unreadable folder lists none
            msg = self._err_text(exc)
        self._count = (path, len(rows))
        self._shown = None
        sources = ws.carts_store.cart_sources(cart) if cart and ws.carts_store else ()
        code = [r for r in rows if r in sources]
        if self._can_add_source(cart):
            code.append(_NEW_ROW)
        out = []
        for n in code + [r for r in rows if r not in code]:
            icon, label, word = self._file_cells(n, n in code)
            out.append({"name": n, "label": label, "word": word, "icon": icon})
        return out, msg

    def _file_cells(self, name, code):
        """A file's row: its icon, its name, and the tab it opens in."""
        if name == _NEW_ROW:
            return ("new", _NEW_ROW, "")
        tab = "code" if code else self._asset_tab(name)
        if tab is not None:
            return (_TAB_ICONS.get(tab, "doc"), _FILE_WORDS.get(name, name),
                    _TAB_WORDS.get(tab, ""))
        if _modes.is_image(name):
            return ("art", name, "Paint")
        return ("doc", name, "Text")

    def _asset_tab(self, name):
        """The tab that owns asset `name`, or None."""
        tab = _ASSET_TABS.get(name)
        if tab is None and "/" in name:
            tab = _ASSET_SUBDIR_TABS.get(name.split("/")[0])
        return tab

    def _can_add_source(self, cart):
        """Whether this folder may gain another SCRIPT: a writable cart whose
        runtime actually loads more than main (moy_carts.multi_script). The
        gate is the store's, not a runtime string spelled here."""
        store = self.ws.carts_store
        return bool(cart and self.ws.can_manage and store is not None
                    and store.multi_script(cart))

    def _leave_files(self):
        """Back to the cards page, where Files is open."""
        if len(self.page.pages) > 1:
            _tree.pop()

    def open_file(self, name):
        """Route one project file. A script is the Code tab (that is where
        PLAY, the journal and crash-to-code live); an asset is its own tab; a
        text file goes through the request door and comes BACK here."""
        ws = self.ws
        cart = ws.run.project.cart
        if cart is None:
            return
        if name == _NEW_ROW:
            self._ui_mod.new_script()
            return
        if name in ws.carts_store.cart_sources(cart):
            self._leave_files()
            ws.editor_app.set_tab("code")
            ws.text.open_code_file(name)
            return
        tab = self._asset_tab(name)
        if tab is not None:
            self._leave_files()
            ws.editor_app.set_tab(tab)
            return
        if "/" in name and not _modes.is_image(name):
            self.s.files_msg = "Nothing on this console opens that file."
            return
        # a picture and a text file open another app: at the frame's tail,
        # never inside the page's handler
        ws.defer(lambda: self._open_doc(cart, name))

    def _open_doc(self, cart, name):
        """A cart's OWN image is a picture: the picture door Files takes,
        opened in Paint on this project's kind and written back in place; a
        text file opens in the editor handle and comes back here."""
        ws = self.ws
        if _modes.is_image(name):
            ok, why = ws.open_image(name, cart=cart), "There's no Paint app to open it in."
        else:
            ok, why = ws.open_project_file(cart, name, _modes.mode_for(name)), "That file didn't open."
        if ok:
            if self.page.has_page():
                self.page.back()
        else:
            self.run("say", why)

    def _newf_filename(self, typed):
        """The file a typed name lands on: slugged to letters, digits and
        underscore, under the cart's own runtime extension. `free_file_name`'s
        rule for a project file is "keep it verbatim" (a FORMAT chose the name),
        which is right for manifest.json and wrong for something a person is
        typing now, so the slug is here."""
        cart = self.ws.run.project.cart or {}
        mainf = cart.get("main", "main.py")
        cut = mainf.rfind(".")
        ext = mainf[cut:] if cut > 0 else ".lua"
        stem = typed.strip()
        if stem.lower().endswith(ext):
            stem = stem[:-len(ext)]
        out = ""
        last = "_"
        for ch in stem.lower():
            if ch == "_" or ch.isalpha() or ch.isdigit():
                out += ch
            elif last != "_":
                out += "_"
            last = out[-1:] or "_"
        out = out.strip("_")[:24]
        if not out or not out[0].isalpha():
            return None
        return out + ext
