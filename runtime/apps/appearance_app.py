# Map (grep -n a name to jump there):
#   build                            the rows' page: the theme cards over the rows, NAME
#   walls                            the wallpapers' page: tabs over cards
#   fill                             the pages' states from the layer and the choices
#   AppearanceAppLayer               the app: the choices, the changes, NAME, the pictures put
#   AppearanceAppLayer._preview      a theme's card picture: its colours
#   AppearanceAppLayer._draw_wall    a wallpaper's card picture
"""The Appearance page (docs/history/look_2026-10.md step 20), a `uitree`
page the C engine lays out and paints.

The themes are cards (`ui.cards`), each picture the theme's own ground,
bar, surface and accent, drawn when the engine asks (`ui.pictures.put`),
the theme in use wearing the current mark; under them the rows: MODE (a
seg, where the theme has two modes: Day by the sun, Night by the moon), ACCENT (eight swatches: the theme's
own and `OFFERED`), TINT, WALLPAPER (a link to the wallpapers' page),
WINDOW STYLE (where windows are), FONT, CODE FONT (where the image draws
more than one), CHROME SIZE (where the panel takes more than one), POINTER
and its SIZE (where the console has a pointer: the theme's own family or
one of runtime/toolkit/pointers.py's, Normal or Large), NAME on `custom`,
and the door to the Editor's theme mode. On the desk the band
under them leads with the theme's status.

WALLPAPER pushes a page of the wallpapers as cards under two tabs
(`ui.tabs`): Pictures (the theme's backdrop, its picture, Paint's) and
Carts (the wallpaper carts). A card puts that wallpaper on and comes back;
Back comes back with nothing changed.

Every row but the cards, MODE, CHROME SIZE, POINTER, NAME and the door is a change
to the theme (`ctx.theme.change`), which lands in `custom`. The rows read
`ctx.theme.choices()` once per token generation.

NAME (on `custom` only) is a dialog holding a field, the keyboard in text
mode while it has focus: Keep renames `custom` to the name typed
(`ctx.theme.name_custom`), a theme of its own among the cards; a name an
installed theme has turns Keep into Replace, which replaces it; Cancel or
Back backs out.
"""
import moy_ui as _C
import uitree as ui
import uitree_app

from moy_store_base import BUILTIN_NS
from pointers import FAMILIES as POINTERS, NAMES as POINTER_NAMES
from chrome import (THEME_NAMES, theme_accents, theme_colors, theme_look, theme_modes,
                    theme_names, theme_presets, theme_tints, RGB, PAINT, LOOK_NONE,
                    rgb565_of, nearest_of)

# The theme's picture's wallpaper id (`Appearance.PICTURE`), and the change
# value that puts the source theme's own wallpaper back (`Appearance.change`).
PICTURE = BUILTIN_NS + ".wallpaper"
THEIRS = ""

# The WINDOW STYLE and FONT presets in their stepping order (the look's
# FRAMES and FONTS), and their names.
FRAMES = ("classic", "tab", "platinum", "win9x", "flat")
FONTS = ("tiny5", "petme128")
FRAME_NAMES = ("Classic", "Tabs", "Platinum", "Win9x", "Flat")
FONT_NAMES = ("Tiny5", "PetMe128")
# The CODE FONT presets (`Appearance.CODE_FONTS`) by name.
CODE_FONT_NAMES = {"petme128": "PetMe128", "jbmono": "JetBrains Mono"}
OWN = "Default"     # a cycler's word for the theme's own choice
POINTER_OWN = "%s (theme)"      # POINTER's words for the theme's own family
POINTER_SIZES = ("normal", "large")
POINTER_SIZE_NAMES = ("Normal", "Large")
# ACCENT's seven swatches after the theme's own, by name, in hue order: a
# preset (style.json's `presets`, an accent in each mode's value) or one of
# the sixteen accents. Each reads in Moy's Day and Night, its focus colour on
# the current plate included (tests/test_theme_derive.py); `indigo`, the
# twin of Moy's own, and the rest stay in the data, not offered.
OFFERED = ("coral", "red", "berry", "magenta", "azure", "forest", "slate")
# NAME's refusals (`ctx.theme.name_check`), in words.
NAME_WHY = {"grammar": "a-z 0-9 _ - only, a letter or digit first",
            "seed": "A built-in theme has that name",
            "custom": "Custom is the one being changed",
            "cart": "A cart has that name",
            "folder": "A folder has that name",
            "store": "Can't save here",
            "none": "Only custom is named"}
NAME_HINT = "a-z 0-9 _ -, up to 24"
# The line the Code font row's sample draws in the font it picked.
CODE_SAMPLE = "for i=1,10 do print(i) end"
NAME_MAX = 24
EDIT_THEME = "Edit theme…"
DOT = " · "
# The type roles a card's "Aa" tries, largest first (`_aa`).
_AA_FACES = ("result", "key", "title")
# The rows by the words a caller names them with (`show_row`): their ids.
ROWS = {"Mode": "mode", "Accent": "accent", "Tint": "tint", "Wallpaper": "wallpaper",
        "Window style": "frame", "Font": "font", "Code font": "code", "Chrome size": "chrome",
        "Pointer": "pointer", "Pointer size": "psize",
        "Name": "name_ask", EDIT_THEME: "edit"}


# -- the pages ------------------------------------------------------------------------

_PICKS = dict(key="v", v="", word="", icon="")
# The Mode row's icons, light's and dark's: Day the sun, Night the moon.
MODE_ICONS = ("sun", "moon")
s = ui.state(
    status="",                  # the desk band's lead: the theme, its mode, where it comes from
    themes=ui.model(key="id", id="", title="", sub="", pic=ui.IMAGE),
    theme=ui.row_of("themes"),  # the theme in use: the current mark
    card=ui.row_of("themes"),   # the card focus is on
    modes=ui.model(**_PICKS),
    mode=ui.row_of("modes"),
    two_modes=False,
    accents=ui.model(key="v", v="", rgb=""),
    accent=ui.row_of("accents"),
    has_accents=False,
    tints=ui.model(**_PICKS),
    tint=ui.row_of("tints"),
    wall_title="",
    frames=ui.model(**_PICKS),
    frame=ui.row_of("frames"),
    fonts=ui.model(**_PICKS),
    font=ui.row_of("fonts"),
    codes=ui.model(**_PICKS),
    code=ui.row_of("codes"),
    has_codes=False,
    chromes=ui.model(**_PICKS),
    chrome=ui.row_of("chromes"),
    has_chromes=False,
    pointers=ui.model(**_PICKS),
    pointer=ui.row_of("pointers"),
    psizes=ui.model(**_PICKS),
    psize=ui.row_of("psizes"),
    has_pointer=False,          # the console has a pointer: POINTER and its size show
    custom=False,               # the theme in use is custom: NAME shows
    edit_word="",               # the door's value
    wtab=ui.enum("pictures", "carts", init="pictures"),
    pics=ui.model(key="id", id="", title="", pic=ui.IMAGE),
    carts=ui.model(key="id", id="", title="", pic=ui.IMAGE),
    wall_on=ui.row_of("pics"),  # the wallpaper in force: its card's key, on either tab
    no_carts=False,
    naming=False,               # NAME's dialog
    armed=False,                # ...its Keep is Replace
    name="",
    name_note="",
)
ui.app("Appearance", icon="palette", min=(310, 230))
ui.labels("WTABS", {"pictures": "Pictures", "carts": "Carts"})


def _lay():
    """The app's Layer, which a handler's run owes a fill."""
    lay = uitree_app.env()
    lay.fill_owed = True
    return lay


def use_theme(row):
    lay = _lay()
    if row.id != lay.choices()["theme"]:
        lay._theme.set(row.id)
        lay.acted()


def mode_set():
    lay = _lay()
    lay._theme.set_variant(s.mode)
    lay.acted()


def accent_set():
    lay = _lay()
    v = s.accent
    lay.change("accent", None if v == "own" else lay.accent_value(v))


def tint_set():
    _lay().change("tint", s.tint or None)


def _preset(kind, name):
    def changed():
        lay = _lay()
        lay.change(kind, getattr(s, name) or None)      # "": the source's own
    return changed


def chrome_set():
    lay = _lay()
    lay._theme.set_chrome_scale(int(s.chrome))
    lay.acted()


def pointer_set():
    lay = _lay()
    lay._theme.set_pointer(s.pointer, s.psize == "large")
    lay.acted()


def wallpaper():
    lay = _lay()
    tab, key = lay.wall_now()
    s.wtab = tab
    ui.push(walls)
    ui.focus(key + "/use_wall")


def use_wall(row):
    lay = _lay()
    item = lay.walls[row.id]
    if row.id != s.wall_on:
        lay.change("wallpaper", item[0])
    ui.pop()


def name_ask():
    _lay().open_name()


def name_typed():
    lay = _lay()
    lay.armed = None
    lay.why = None


def keep():
    _lay().name_commit()


def cancel():
    _lay().close_name()


def edit():
    lay = _lay()
    lay._theme.edit_file()
    lay.acted()


ui.action("use", "Use", use_theme, takes="row")
ui.hook("mode_set", mode_set)
ui.hook("accent_set", accent_set)
ui.hook("tint_set", tint_set)
ui.hook("frame_set", _preset("frame", "frame"))
ui.hook("font_set", _preset("font", "font"))
ui.hook("code_set", _preset("code_font", "code"))
ui.hook("chrome_set", chrome_set)
ui.hook("pointer_set", pointer_set)
ui.action("wallpaper", "Wallpaper", wallpaper, hint="Open")
ui.action("use_wall", "Use", use_wall, takes="row")
ui.action("name_ask", "Name", name_ask, hint="Open")
ui.action("edit", EDIT_THEME, edit, hint="Open")
ui.hook("name_typed", name_typed)
ui.action("keep", "Keep", keep)
ui.action("cancel", "Cancel", cancel)


def build():
    with ui.page("", status="{status}"):
        with ui.group("Theme"):
            with ui.cards("themes", cur="card", current="theme", w="{@desk?192:66}",
                          h="{@desk?112:50}", flow=True):
                ui.card("use", label="{.title}", sub="{.sub}", image=".pic")
            ui.seg("Mode", "mode", text="{.word}", icons="{.icon}", on="mode_set", shown="two_modes")
            ui.seg("Accent", "accent", text="{.rgb}", look="swatches", on="accent_set",
                   shown="has_accents")
            ui.seg("Tint", "tint", text="{.word}", look="cycle", on="tint_set")
            ui.link("wallpaper", "{wall_title}")
            ui.seg("Window style", "frame", text="{.word}", look="cycle", on="frame_set",
                   shown="@desk")
            ui.seg("Font", "font", text="{.word}", look="cycle", on="font_set")
            ui.seg("Code font", "code", text="{.word}", look="cycle", on="code_set",
                   shown="has_codes")
            ui.label(CODE_SAMPLE, face="mono", tone="dim", shown="has_codes")
            ui.seg("Chrome size", "chrome", text="{.word}", look="cycle", on="chrome_set",
                   shown="has_chromes")
            ui.seg("Pointer", "pointer", text="{.word}", look="cycle", on="pointer_set",
                   shown="has_pointer")
            ui.seg("Pointer size", "psize", text="{.word}", on="pointer_set",
                   shown="has_pointer")
            ui.link("name_ask", "Keep as a theme", shown="custom")
            ui.link("edit", "{edit_word}")
        with ui.dialog("Name your theme", ["cancel", "keep"], labels=["Cancel", "{armed?Replace:Keep}"],
                       shown="naming"):
            ui.field("Name", "name", NAME_MAX, on="keep", changed="name_typed", edit="open",
                     keys="name")
            ui.label("{name_note}")


def walls():
    with ui.page("", status="{status}"):
        ui.tabs("wtab", labels="WTABS")
        with ui.cards("pics", current="wall_on", w="{@desk?192:66}", h="{@desk?112:50}",
                      shown="wtab=pictures"):
            ui.card("use_wall", label="{.title}", image=".pic")
        with ui.cards("carts", current="wall_on", w="{@desk?192:66}", h="{@desk?112:50}",
                      shown="wtab=carts && !no_carts"):
            ui.card("use_wall", label="{.title}", image=".pic")
        ui.label("No wallpaper carts yet", shown="wtab=carts && no_carts")


# -- the states -----------------------------------------------------------------------

def _set(lay, name, value):
    """State `name` written only where it moved."""
    if lay.shown.get(name) != value:
        lay.shown[name] = value
        setattr(s, name, value)


def _picks(lay, name, keys, words, cur, icons=()):
    """A cycle's rows (`name` + "s") and its value, `cur` (a key of `keys`);
    `icons` each row's icon, where its seg shows one."""
    _set(lay, name + "s", [{"v": k, "word": w, "icon": icons[i] if i < len(icons) else ""}
                           for i, (k, w) in enumerate(zip(keys, words))])
    _set(lay, name, cur)


def _own_or(keys, words, cur, own):
    """A preset row's keys, words and value: the presets, the theme's own
    ("", `OWN`) before them where it uses none of them -- `own`, the
    source's, so a pick on custom keeps the way back to it."""
    if cur in keys and own in keys:
        return keys, words, cur
    return ("",) + tuple(keys), (OWN,) + tuple(words), cur if cur in keys else ""


def fill(lay):
    """The pages' states from the choices: the cards and their pictures, the
    rows, the wallpapers' cards, the band's status and NAME's dialog."""
    ch = lay.choices()
    name = ch["theme"]
    variant = ch["variant"]
    rows = []
    for n in lay.themes():
        rows.append({"id": n, "title": _title(n), "sub": DOT.join(lay.modes_of(n)),
                     "pic": lay.theme_pic(n, variant)})
    _set(lay, "themes", rows)
    _set(lay, "theme", name)
    modes = lay.modes_of(name if name != "custom" else (ch["from"] or name))
    _set(lay, "two_modes", len(modes) > 1)
    if len(modes) > 1:
        _picks(lay, "mode", ("light", "dark"), modes, variant, MODE_ICONS)
    offered = lay.accents_offered(ch)
    _set(lay, "has_accents", offered)
    if offered:
        own = ch["accent"] is None
        first = _rgb(lay._theme.colors()["accent"] if own else lay.own_accent(ch))
        side = 3 if variant == "light" else 2
        _set(lay, "accents", [{"v": "own", "rgb": "0x%06x" % first}]
             + [{"v": a[0], "rgb": "0x%06x" % _rgb(a[side])} for a in lay.accents])
        cur = "own" if own else ""
        for a in lay.accents:
            if a[1] == ch["accent"]:
                cur = a[0]
        _set(lay, "accent", cur)
    tints = [t[0] for t in lay.tints]
    _picks(lay, "tint", [""] + tints, ["None"] + [_title(t) for t in tints],
           ch["tint"] if ch["tint"] in tints else "")
    pics, carts = lay.wall_rows(ch)        # (the titles wall_title reads)
    tab, key = lay.wall_now()
    _set(lay, "wall_title", lay.walls[key][1] if key in lay.walls else "")
    _picks(lay, "frame", *_own_or(FRAMES, FRAME_NAMES, ch["frame"], ch["own_frame"]))
    _picks(lay, "font", *_own_or(FONTS, FONT_NAMES, ch["font"], ch["own_font"]))
    codes = ch["code_fonts"]
    _set(lay, "has_codes", len(codes) > 1)
    if len(codes) > 1:
        _picks(lay, "code", *_own_or(codes, [CODE_FONT_NAMES[k] for k in codes], ch["code_font"],
                                     ch["own_code_font"]))
    chromes = ch["chromes"]
    _set(lay, "has_chromes", len(chromes) > 1)
    if len(chromes) > 1:
        cur = ch["chrome"] if ch["chrome"] in chromes else chromes[0]
        _picks(lay, "chrome", [str(c) for c in chromes], ["%d×" % c for c in chromes], str(cur))
    _set(lay, "has_pointer", ch["has_pointer"])
    own = POINTER_NAMES[POINTERS.index(ch["own_pointer"])]
    _picks(lay, "pointer", ("",) + POINTERS, (POINTER_OWN % own,) + POINTER_NAMES,
           ch["pointer"])
    _picks(lay, "psize", POINTER_SIZES, POINTER_SIZE_NAMES,
           POINTER_SIZES[1 if ch["pointer_large"] else 0])
    _set(lay, "custom", name == "custom")
    _set(lay, "edit_word", "" if name == "custom" else "Makes a copy")
    _set(lay, "pics", pics)
    _set(lay, "carts", carts)
    _set(lay, "no_carts", not carts)
    _set(lay, "wall_on", key)
    _set(lay, "status", lay.status(ch) if lay.desk else "")
    _set(lay, "naming", lay.naming)
    _set(lay, "armed", lay.armed is not None and lay.armed == s.name)
    why = lay.why
    _set(lay, "name_note", ("Replace " + s.name + "?") if s.armed else
         NAME_WHY.get(why, str(why)) if why is not None else NAME_HINT)
    if lay.name_text_to is not None:
        s.name = lay.name_text_to
        lay.name_text_to = None
    if lay.focus_to is not None:
        ui.focus(lay.focus_to)
        lay.focus_to = None


# -- the app --------------------------------------------------------------------------

class AppearanceAppLayer(uitree_app.app_layer("appearance", "Appearance", build)):
    """The Appearance app: the page's engine handed this layer as what its
    handlers reach (`uitree_app.env()`), the choices read once per token
    generation, the changes, NAME, and the cards' pictures."""

    TITLE = "Appearance"
    # The shell roles this app uses (runtime/shell/app_context.py). `wallpaper` is a
    # CAPABILITY, not a core role: this app and the two that copy a drawing
    # into it (Paint, Files) are its only consumers. A pick is a change to
    # the theme (docs/theme_and_shell_2026-11.md D6), so it lands in `custom`.

    def __init__(self, ctx, names=None):
        super().__init__(ctx, names)
        self.engine.env = self
        self._wall = ctx.wallpaper
        self.names = names
        self.shown = {}             # each state as last written (`_set`)
        self.fill_owed = True
        self.naming = False         # NAME's dialog is open
        self.armed = None           # the name Replace is armed for
        self.why = None             # the refusal shown
        self.note = None            # the status once a name is kept
        self.focus_to = None        # the stop focus moves to at the next fill
        self.name_text_to = None    # the name NAME's field is set to at the next fill
        self.walls = {}             # a wallpaper card's key -> (value, title, kind)
        self._pics = {}             # a picture's key -> what it was drawn from
        self._ch = None
        self._gen = None
        # (name, the change's value, its swatch in dark, in light): a
        # preset is picked by its dark value and shows each mode's.
        by = dict((p[0], (p[0], p[1], p[1], p[2])) for p in theme_presets())
        for a in theme_accents():
            by.setdefault(a[0], (a[0], a[1], a[1], a[1]))
        self.accents = tuple(by[n] for n in OFFERED)
        self.tints = tuple(theme_tints())

    # -- the app protocol (docs/app_api_v1.md) ----------------------------------

    def open(self):
        self.naming = False
        self.armed = self.why = self.note = None
        self._ch = None
        self.fill_owed = True
        self.focus_to = self.choices()["theme"] + "/use"
        super().open()

    def relayout(self, w, h, fs, cs=None):
        super().relayout(w, h, fs, cs)
        self.fill_owed = True

    def show_row(self, label):
        """Focus row `label` ("Tint") from the next frame on, on the rows' page."""
        self.engine.pages = self.engine.pages[:1]
        self.engine.root = None
        self.focus_to = ROWS.get(label, label)
        self.fill_owed = True
        self._damage.all()

    def open_walls(self):
        """The wallpapers' page, as WALLPAPER opens it."""
        self.engine.run(wallpaper, action="console")
        ui.commit(self.engine)
        self._damage.all()

    def handle_input(self, inp):
        self._refresh()
        if inp.pressed("b"):
            self.back()
            return True
        return self.engine.keys(inp)

    def draw(self, dt):
        self._refresh()
        if self.fill_owed:
            self.fill_owed = False
            self.engine.run(fill, self, action="fill")
            ui.commit(self.engine)
        super().draw(dt)

    # -- what the rows show ----------------------------------------------------

    def choices(self):
        """What the rows show (`ctx.theme.choices()`), as `_refresh` last
        read it."""
        if self._ch is None:
            self._ch = self._theme.choices()
            self._gen = self._theme.gen()
        return self._ch

    def _refresh(self):
        """Read `ctx.theme.choices()` again when the token generation moved
        (a change lands at the next frame's tick, and moves it)."""
        g = self._theme.gen()
        if self._ch is None or g != self._gen:
            self._ch = self._theme.choices()
            self._gen = g
            self.fill_owed = True
            if self.naming and self._ch["theme"] != "custom":
                self.close_name(acted=False)

    def themes(self):
        """The cards' names: `custom` first, then the store's packages (a
        named theme among them), then the seeds (`chrome.theme_names`)."""
        names = list(theme_names())
        mine = [n for n in names if n not in THEME_NAMES]
        if "custom" in mine:
            mine.remove("custom")
            mine.insert(0, "custom")
        return mine + [n for n in names if n in THEME_NAMES]

    def modes_of(self, name):
        """A theme's modes, light first, as its Mode row names them: one for
        a single-mode theme, which shows no Mode row."""
        modes = theme_modes(name)
        if len(modes) == 1:
            return ("Day",) if modes == ("light",) else ("Night",)
        return ("Day", "Night")

    def status(self, ch):
        """The desk's band: the theme, its mode and where it comes from."""
        if self.note:
            return self.note
        name = ch["theme"]
        if name == "custom":
            return "Custom" + DOT + "saved as you go"
        modes = self.modes_of(name)
        mode = modes[0 if ch["variant"] == "light" else len(modes) - 1]
        return _title(name) + " " + mode + DOT + ("store" if ch["store"] else "built in")

    def accents_offered(self, ch):
        """Whether the theme in use (a custom one's source) offers accent
        picks: its look's `accents`, true where it is silent."""
        name = ch["theme"]
        src = (ch["from"] or name) if name == "custom" else name
        return theme_look(src, ch["variant"]).get("accents") != 0

    def own_accent(self, ch):
        """The source's own accent while the theme sets another."""
        src = ch["from"] or ch["theme"]
        return theme_colors(src, ch["variant"])["accent"]

    def accent_value(self, name):
        for a in self.accents:
            if a[0] == name:
                return a[1]
        return None

    # -- the wallpapers --------------------------------------------------------

    def wall_rows(self, ch):
        """The wallpapers' cards, (Pictures, Carts): the theme's backdrop,
        the source theme's own picture where it has one, Paint's picture,
        then the wallpaper carts; `walls` keeps each card's (value, title,
        kind), kind "backdrop", "theirs", "art" or "cart"."""
        walls = self.walls = {"backdrop": (None, "Backdrop", "backdrop")}
        pics = ["backdrop"]
        if ch["picture"] == "theme":
            walls["theirs"] = (THEIRS, "Theme's picture", "theirs")
            pics.append("theirs")
        carts = []
        for c in self._wall.carts():
            wid = self._wall.id_for(c)
            title = str(c.get("title", "Wallpaper"))
            if title == "Wallpaper":
                walls["art"] = (wid, "Wallpaper", "art")
                pics.append("art")
            else:
                key = "cart:" + str(wid)
                walls[key] = (wid, title, "cart")
                carts.append(key)
        on = self.wall_now()[1]
        return ([{"id": k, "title": walls[k][1], "pic": self.wall_pic(k, k == on, ch)} for k in pics],
                [{"id": k, "title": walls[k][1], "pic": self.wall_pic(k, k == on, ch)} for k in carts])

    def wall_now(self):
        """(tab, card key) of the wallpaper in force."""
        ch = self.choices()
        wp = ch["wallpaper"]
        if wp is None:
            return "pictures", "backdrop"
        if wp == PICTURE:
            return "pictures", "art" if ch["picture"] == "mine" else "theirs"
        return "carts", "cart:" + str(wp)

    # -- NAME ------------------------------------------------------------------

    @property
    def name_text(self):
        """NAME's field, as typed."""
        self.engine._bind()
        return self.engine.s._v["name"]

    @name_text.setter
    def name_text(self, v):
        self.name_text_to = v
        self.fill_owed = True
        self._damage.all()

    def open_name(self):
        self.naming = True
        self.armed = self.why = None
        self.name_text_to = ""
        self.focus_to = "name"
        self.fill_owed = True
        self._damage.all()

    def close_name(self, acted=True):
        self.naming = False
        self.armed = self.why = None
        self.focus_to = "name_ask"
        self.fill_owed = True
        if acted:
            self.acted()

    def name_commit(self):
        """Keep in NAME: rename `custom` to the name typed; a name an
        installed theme has arms Replace, and a second Keep replaces it."""
        name = self.name_text
        why = self._theme.name_check(name)
        replace = why == "taken" and self.armed == name
        if why == "taken" and not replace:
            self.armed = name
            self.why = None
            return
        if why is None or replace:
            why = self._theme.name_custom(name, replace)
        if why is not None:
            self.armed = None
            self.why = why
            return
        self.close_name()
        self.focus_to = name + "/use"
        self.note = name + ".moy is a theme now"
        self._ch = None

    # -- acting ----------------------------------------------------------------

    def acted(self):
        self.note = None
        self.fill_owed = True
        self._damage.all()

    def change(self, kind, value):
        """A change to the theme (`ctx.theme.change`), which lands in `custom`."""
        self._theme.change(kind, value)
        self.acted()

    # -- the pictures ----------------------------------------------------------

    def _put(self, key, made, render):
        """Picture `key` put again where what it is drawn from moved."""
        if self._pics.get(key) != made:
            self._pics[key] = made
            ui.pictures.put(key, render=render)
        return ui.image.own(key)

    def _layer(self, w, h):
        return self._surf.canvas().new_layer(w, h)

    def theme_pic(self, name, variant):
        p = self._pic(name, variant)
        face = _C.font("title")[0]

        def render(w, h):
            cv = self._layer(w, h)
            self._preview(cv, w, h, p)
            return cv
        return self._put("theme:" + name, (p, face, self._surf.font_scale()), render)

    def wall_pic(self, key, on, ch):
        item = self.walls[key]

        def render(w, h):
            cv = self._layer(w, h)
            if on:
                self._wall.preview(cv, (0, 0, w, h), 0)    # the backdrop's own still
            else:
                self._draw_wall(cv, w, h, item)
            return cv
        made = (item, on, ch["wallpaper"], ch["picture"], self._theme.colors()["desktop"],
                self._surf.font_scale())
        return self._put("wall:" + key, made, render)

    @staticmethod
    def _pic(name, variant):
        """Theme `name`'s card picture's colours and widths in `variant`:
        (ground, bar, bar line width, bar line, frame width, card radius,
        frame, surface, ink index, accent, value), the look's leaves where
        it sets them, else the tokens'."""
        tok = theme_colors(name, variant)
        lk = theme_look(name, variant)
        return (_look_colour(lk, "home_bg", tok["desktop"]),
                _look_colour(lk, "bar.fill", tok["bar"]),
                lk.get("bar.line.w", LOOK_NONE),
                _look_colour(lk, "bar.line.c", tok["border"]),
                lk.get("win.frame.w", LOOK_NONE),
                lk.get("card_r", 0),
                _look_colour(lk, "win.frame.c", tok["border"]),
                tok["surface"], _index(tok["ink"]), tok["accent"], tok["value"])

    def _preview(self, cv, w, h, p):
        """A theme's card picture (`_pic`), as its home shows it: its ground
        (the look's home ground, else `desktop`), its bar with the bar's
        line, a panel in its window frame (else a `border` hairline) at its
        card radius holding "Aa" in the live theme's title face and its ink,
        and its accent (and its value, where that is another colour) as
        dots."""
        desk = self.desk
        k = 1 if desk else max(1, self._surf.font_scale())
        _fill(cv, 0, 0, w, h, p[0])
        bh = (14 if desk else 8) * k
        _fill(cv, 0, 0, w, bh, p[1])
        lw = _look_px(p[2], k)
        if lw:
            _fill(cv, 0, bh - lw, w, lw, p[3])
        m = (14 if desk else 6) * k
        py = bh + (10 if desk else 5) * k
        pw = w - 2 * m
        ph = h - py - (10 if desk else 5) * k
        fw = _look_px(p[4], k) or k
        rad = p[5]
        rad = min(max(0, rad) * k // 2, ph // 3) if rad != LOOK_NONE else 2 * k
        _shape(cv, m, py, pw, ph, rad, p[6])
        _shape(cv, m + fw, py + fw, pw - 2 * fw, ph - 2 * fw, max(0, rad - fw), p[7])
        _aa(cv, 2 * m, py, ph, p[8])
        d = (16 if desk else 8) * k
        xr = pw - d
        acc = p[9]
        val = p[10]
        if val != acc:
            _shape(cv, xr, py + ph // 2 - d - k, d, d, d // 2, acc)
            _shape(cv, xr, py + ph // 2 + k, d, d, d // 2, val)
        else:
            _shape(cv, xr, py + (ph - d) // 2, d, d, d // 2, acc)

    def _draw_wall(self, cv, w, h, item):
        kind = item[2]
        if kind == "backdrop":
            cv.rect(0, 0, w, h, self._theme.colors()["desktop"])
        elif kind == "art":
            pic = self._wall.thumbnail(w, h)
            if pic is not None:
                cv.spr(pic, 0, 0)
            else:
                self._picture(cv, w, h)
        elif kind == "theirs":
            self._picture(cv, w, h)
        else:
            self._cart_scene(cv, w, h, item[1])

    def _picture(self, cv, w, h):
        n = self.names
        cv.rect(0, 0, w, h, n["light_grey"])
        cv.circ(w * 3 // 4, h // 3, max(2, min(w, h) // 8), n["yellow"])

    def _cart_scene(self, cv, w, h, title):
        # Distinct miniature visual identities of the wallpaper carts.
        fs = max(1, self._surf.font_scale())
        n = self.names
        if "Ocean" in title:
            cv.rect(0, 0, w, h, n["blue"])
            for row in range(3):
                cv.line(0, h // 2 + row * 5 * fs, w - 1, h // 2 + row * 5 * fs, 21 + row)
            cv.circ(w * 3 // 4, h // 3, max(2, h // 10), 7)
        elif "Sakura" in title:
            cv.rect(0, 0, w, h, 22)
            cv.line(w // 3, h, w // 2, h // 4, 28)
            cv.circ(w // 2, h // 3, max(3, h // 4), n["pink"])
            cv.circ(w * 2 // 3, h // 3, max(2, h // 6), n["peach"])
        elif "Machine" in title:
            cv.rect(0, 0, w, h, n["black"])
            step = max(4 * fs, min(w, h) // 6)
            for gy in range(step // 2, h, step):
                for gx in range(step // 2, w, step):
                    cv.rect(gx, gy, fs, fs, n["dark_blue"])
            cv.line(w * 2 // 3, 0, w - 1, h // 3, n["indigo"])
            cv.line(w - 1, h // 3, w * 2 // 3, h - 1, n["indigo"])
        elif "Space" in title or "Night" in title:
            cv.rect(0, 0, w, h, 60)
            for i in range(12):
                cv.rect((i * 37) % max(1, w), (i * 19) % max(1, h), fs, fs, 7 if i % 3 else 10)
            cv.circ(w * 3 // 4, h // 3, max(3, h // 6), 10)
        else:
            cv.rect(0, 0, w, h, 12)
            cv.rect(0, h * 2 // 3, w, h - h * 2 // 3, n["dark_green"])
            cv.circ(w * 3 // 4, h // 3, max(2, h // 8), n["yellow"])


# -- drawing in another theme's colours ----------------------------------------------

def _rgb(v):
    """Colour value `v` as 0xRRGGBB: RGB's own, an index's (the palette's or
    the block's) from its RGB565 word, which it comes back to exactly."""
    if v >= RGB:
        return v & 0xffffff
    w = rgb565_of(v)
    return (((w >> 11) * 255 // 31) << 16) | ((((w >> 5) & 63) * 255 // 63) << 8) \
        | ((w & 31) * 255 // 31)


_WORDS = {}          # an RGB colour value -> its RGB565 word, two bytes in a canvas's order
_TAKES_RGB = {}      # a canvas class -> whether it draws RGB565 words (`cover`)


def _takes_rgb(cv):
    t = type(cv)
    ok = _TAKES_RGB.get(t)
    if ok is None:
        ok = _TAKES_RGB[t] = getattr(cv, "cover", None) is not None
    return ok


def _word(cv, v):
    """RGB value `v`'s RGB565 word as the picture of one pixel in `cv`'s
    byte order (`swapped565`), made once a value."""
    sw = getattr(cv, "swapped565", False)
    key = -v if sw else v
    b = _WORDS.get(key)
    if b is None:
        w = rgb565_of(v)
        if sw:
            w = ((w & 0xFF) << 8) | (w >> 8)
        b = _WORDS[key] = bytes((w & 0xFF, w >> 8))
    return b


def _fill(cv, x, y, w, h, v):
    """A rect in colour value `v`: a palette index (the live theme's block
    included) through the canvas, an RGB value as its RGB565 word, which
    takes no slot: how a card shows another theme's colours."""
    if w <= 0 or h <= 0:
        return
    if v < RGB:
        cv.rect(x, y, w, h, v)
        return
    if not _takes_rgb(cv):              # a canvas that takes indices only
        cv.rect(x, y, w, h, nearest_of(v))
        return
    cv.blit565_resize(_word(cv, v), 1, 1, x, y, w, h)


def _shape(cv, x, y, w, h, r, v):
    """A rect with anti-aliased corners of radius `r` (a circle at w // 2)
    in colour value `v`: an index through the canvas's `rrect`, an RGB value
    exactly, as a one-word picture `cover` scales into the shape."""
    if w <= 0 or h <= 0:
        return
    if v < RGB:
        cv.rrect(x, y, w, h, r, v)
        return
    if not _takes_rgb(cv):              # a canvas that takes indices only
        cv.rrect(x, y, w, h, r, nearest_of(v))
        return
    cv.cover(_word(cv, v), 1, 0, 0, 1, 1, x, y, w, h, r)


def _look_colour(lk, leaf, default):
    """Look leaf `leaf`'s colour, else `default` (unset, or a paint)."""
    v = lk.get(leaf, LOOK_NONE)
    return default if v == LOOK_NONE or v < 0 or v >= PAINT else v


def _look_px(v, k):
    """A look width `v` (hundredths) in pixels at scale `k`, 0 unset."""
    return 0 if v == LOOK_NONE or v <= 0 else max(1, (v * k + 50) // 100)


def _index(v):
    """Colour value `v` as an index a canvas draws: its nearest for RGB."""
    return v if v < RGB else nearest_of(v)


def _title(name):
    """A theme's name as its card says it."""
    return name[:1].upper() + name[1:]


def _aa(cv, x, y, h, c):
    """"Aa" centred down a panel of height `h` at `x`: the live theme's
    largest face whose line is at most half the panel, at its own size
    (its anti-aliasing unscaled), else the print font at the whole scale
    that fits."""
    for role in _AA_FACES:
        f = _C.font(role)[0]
        if f and _C.text_covers("Aa", f):
            lh = _C.font_info(f)[2]
            if 2 * lh <= h:
                was = _C.print_font(f)
                cv.print("Aa", x, y + (h - lh) // 2, c)
                _C.print_font(was)
                return
    info = _C.font_info(_C.print_font())
    lh = info[2] if info else 8
    big = max(1, h // (2 * lh))
    cv.print_scaled(b"Aa", x, y + (h - lh * big) // 2, c, big)
