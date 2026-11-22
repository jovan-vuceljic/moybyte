# Map (grep -n a name to jump there):
#   shown_name                      a cart folder as a row shows it
#   files_page                      the page: places, files, foot, dialogs
#   FilesAppLayer.open_place        a place's rows, listed once
#   FilesAppLayer.door              the router's rules, as a pure function
#   FilesAppLayer._act              the verbs on the current row
"""Files -- the kid file manager system app (#108), a `uitree` page the C
engine lays out and paints.

Places down the side (Projects, the shared folders Documents, Pictures,
Music and Downloads as they are named on disk, Themes once there are any,
and the Trash), and the place's files as rows: each file's icon (by what it
is), its name (a project's title) and its kind. No paths, and no extensions
outside Downloads, whose files keep the whole names they arrived under (a
beam from a console nearby lands there, runtime/run/link_beam.py) and show
their type as their kind: one opens in the app that takes its type, as any
file does, and nothing there runs. The handheld shows the places, then a
place's files, one page at a time; the desk shows both. A file's verbs ride
the page's foot, the one Enter does last: OPEN in the owning app (Enter, or
a tap on the row, does the same), OPEN WITH (the "open with" menu of the apps
whose manifest opens the file's type, runtime/system/intents.py, the one
picked becoming the choice), RENAME in a dialog (Paint's open picture follows
it, `artwork.follow`), DUPLICATE, WALLPAPER / USE IN GAME / USED IN for a
drawing (`picture_copies.PictureCopies`), SEND to a console nearby where the
console's radio link can come up (`intents.Intents.send`,
runtime/run/link_beam.py), and DELETE, which moves it to the restorable
Trash and never destroys -- the Trash restores, and emptying it is the one
verb that asks first.

A `.moy` cartridge identity on the launcher (`moybyte.files.moy`) backed by
a SYSTEM process. Projects is a place beside the file kinds but never a store
kind, because a project is a thing you edit and not a directory you browse;
Themes are the store's theme packages, whose rows open the Appearance app.
"""

import uitree as ui
import uitree_app
from moy_store_base import builtin_name
from picture_copies import PictureCopies
from app_shell import ListShellApp
import text_modes as _modes
import intents as _intents


# The carts root, as a place beside the user-files kinds. NOT a
# `moy_carts.FILE_KINDS` name and never passed to the files store: its items
# are `.moy` FOLDERS, each shown as ONE item and opened as a project.
PROJECTS = "projects"
# The store's theme packages: a theme is data the Appearance app picks,
# never a project the Editor opens (docs/history/theming_2026-09.md §9 phase 6).
THEMES = "themes"
DOCUMENTS = "documents"
PICTURES = "pictures"
MUSIC = "music"
DOWNLOADS = "downloads"
TRASH = "trash"

# The places, in the side's order: key, label, icon, and the store kinds a
# place lists. The shared folders are named as on disk
# (moy_store_base.SHARED_FOLDERS); THEMES shows once there are any; the rest
# always do.
PLACES = (
    (PROJECTS, "Projects", "projects", ()),
    (DOCUMENTS, "Documents", "notes", ("docs",)),
    (PICTURES, "Pictures", "paint", ("drawings", "sprites")),
    (MUSIC, "Music", "music", ("music", "recordings")),
    (DOWNLOADS, "Downloads", "arrow_down", ("downloads",)),
    (THEMES, "Themes", "wallpaper", ()),
    (TRASH, "Trash", "trash", ()),
)

# What a store kind's file is called as its kind, and its icon.
KIND_OF = {
    "docs": ("Note", "notes"),
    "drawings": ("Drawing", "art"),
    "sprites": ("Sprites", "sprite"),
    "music": ("Song", "music"),
    "recordings": ("Recording", "music"),
    "downloads": ("File", "doc"),
}
# A download's, by its extension: our formats and the vault's by name, any
# other by its extension in capitals (KIND_OF's "File" where it has none).
DOWNLOAD_KIND = {
    ".md": ("Note", "notes"),
    ".txt": ("Text", "doc"),
    ".json": ("Data", "doc"),
    ".py": ("Script", "cart_py"),
    ".lua": ("Script", "cart_lua"),
    ".moyimg": ("Drawing", "art"),
    ".moygfx": ("Sprites", "sprite"),
    ".moysong": ("Song", "music"),
    ".png": ("Image", "art"),
}
# A project's, by its cart type.
CART_KIND = {
    "game": ("Game", "game"),
    "app": ("App", "app"),
    "tool": ("Tool", "app"),
    "wallpaper": ("Wallpaper", "wallpaper"),
    "theme": ("Theme", "wallpaper"),
}

# A verb's row field (the current row offers it where true) and the action
# that does it, in the foot's order: Enter's verb last.
VERBS = (("WITH", "v_with"), ("NAME", "v_name"), ("COPY", "v_copy"), ("WALL", "v_wall"),
         ("GAME", "v_game"), ("USE", "v_use"), ("SEND", "v_send"), ("DEL", "v_del"),
         ("PLAY", "v_play"), ("RUN", "v_run"), ("RESTORE", "v_restore"), ("OPEN", "v_open"))


def _cap(word):
    """`word` with its first letter in capitals: MicroPython's str has no
    `capitalize`."""
    return word[:1].upper() + word[1:]


def kind_of(kind, name):
    """What a `kind` file named `name` is called as its kind, and its icon:
    a download's by its extension."""
    if kind == DOWNLOADS:
        ext = _modes.ext_of(name)
        got = DOWNLOAD_KIND.get(ext)
        if got is not None:
            return got
        if ext:
            return ext[1:].upper()[:6], "doc"
    return KIND_OF.get(kind, (_cap(kind), "doc"))


def _folder_of(cart):
    """A cart's `.moy` FOLDER name. The folder and not the title: the title
    is what a kid renamed the game to, the folder is the thing on the card."""
    path = (cart or {}).get("path") or ""
    cut = max(path.rfind("/"), path.rfind("\\"))
    return path[cut + 1:] if cut >= 0 else (path or (cart or {}).get("title") or "")


def shown_name(folder):
    """A cart folder as a row shows it: no author and no extension."""
    name = folder[:-4] if folder.endswith(".moy") else folder
    dot = name.find(".")
    return name[dot + 1:] if dot >= 0 else name


def row_id(i):
    """Row i's key in the files model: an index, so a name of any spelling
    makes a stop id."""
    return "r%d" % i


# -- the page's state and actions ---------------------------------------------------

s = ui.state(
    places=ui.model(key="id", id="", label="", icon="", count=""),
    place=ui.row_of("places"),
    files=ui.model(key="id", id="", name="", kind="", icon="", v_with=False, v_name=False,
                   v_copy=False, v_wall=False, v_game=False, v_use=False, v_send=False, v_del=False,
                   v_play=False, v_run=False, v_restore=False, v_open=False),
    cur=ui.row_of("files"),
    any=False,                      # the place lists a file
    trashed=False,                  # the Trash holds something: Empty
    in_trash=False,                 # the place is the Trash
    caption="",                     # the place's name over a handheld's list
    none_line="",                   # what an empty place says
    view=ui.enum("places", "files", init="places"),     # what a handheld shows (the desk: both, "files")
    status="",                      # what the last verb did, at the foot's start
    asking=ui.enum("none", "rename", "empty", "game", "used", init="none"),
    typed="",                       # the rename dialog's name
    empty_line="",                  # the Trash's count, as emptying it says it
    targets=ui.model(key="id", id="", title=""),        # Use in game's projects
    target=ui.row_of("targets"),
    uses=ui.model(key="id", id="", label="", note=""),  # Used in's copies
    use=ui.row_of("uses"),
)
ui.app("Files", icon="folder_open", back="back")


def _f():
    return uitree_app.env()


def opened():
    _f()._opened()


def pick_place(row):
    _f().open_place(row.id, pick=True)


def open_place(row):
    _f().open_place(row.id, show=True)


def back():
    s.view = "places"
    ui.focus(s.place + "/open_place")


def open_row(row):
    f = _f()
    f._open_row(f.index(row.id))


def _verb(verb):
    def act(row):
        f = _f()
        f.cur = f.index(row.id)
        f._act(verb)
    return act


def empty_trash():
    _f()._act("EMPTY")


def del_key(c):
    _f()._act("DEL")


def rename_it():
    _f()._rename_commit()


def empty_it():
    _f()._empty_trash()


def add(row):
    f = _f()
    f._game_pick(int(row.id))


def resend(row):
    _f()._resend(int(row.id))


def cancel():
    _f()._close_dialog()


ui.hook("opened", opened)
ui.action("back", "Back", back, when="!@desk && view=files", off="hide")
ui.action("pick_place", "Show", pick_place, takes="row", hint="")
ui.action("open_place", "Open", open_place, takes="row")
ui.action("open", "Open", open_row, takes="row")
_LABELS = {"WITH": "Open with…", "NAME": "Rename", "COPY": "Duplicate", "WALL": "Wallpaper",
           "GAME": "Use in game", "USE": "Used in", "SEND": "Send", "DEL": "Delete", "PLAY": "Play",
           "RUN": "Run", "RESTORE": "Restore", "OPEN": "Open"}
for _v, _field in VERBS:
    ui.action(_field, _LABELS[_v], _verb(_v), takes="row", row="cur", when="cur." + _field, off="hide")
ui.action("empty", "Empty", empty_trash, when="in_trash && trashed", off="hide")
ui.action("del_key", "Delete", del_key, takes="char", chars="\b\x7f",
          when="view=files && cur.v_del && asking=none", off="hide")
ui.action("cancel", "Cancel", cancel)
ui.action("rename_it", "Rename", rename_it)
ui.action("empty_it", "Empty", empty_it)
ui.action("add", "Add", add, takes="row", row="target", off="hide")
ui.action("close_used", "Close", cancel)
ui.action("resend", "Send again", resend, takes="row", row="use", off="hide")

# Each verb's icon at the foot, and its button's kind.
_ICONS = {"WITH": "app", "NAME": "pencil", "COPY": "dup", "WALL": "wallpaper", "GAME": "game",
          "USE": "search", "SEND": "export", "DEL": "del", "PLAY": "play", "RUN": "run",
          "RESTORE": "back", "OPEN": "folder_open"}
_KINDS = {"DEL": "danger", "RESTORE": "primary", "OPEN": "primary"}


def _places():
    with ui.scroll("side"):
        with ui.rows("places", cur="place", changed="pick_place"):
            ui.link("open_place", "{.count}", icon="{.icon}", label="{.label}")


def _list():
    with ui.scroll("list"):
        with ui.rows("files", cur="cur"):
            ui.link("open", "{.kind}", icon="{.icon}", label="{.name}")
    ui.label("{none_line}", tone="dim", shown="!any")


def _hand_list():
    ui.label("{caption}", tone="dim", face="caption")
    _list()


def files_page():
    with ui.page(""):
        with ui.split("row", sizes=(160, "1*"), shown="@desk"):
            with ui.group(""):
                _places()
            with ui.group(""):
                _list()
        ui.switch("view", {"places": _places, "files": _hand_list}, shown="!@desk")
        with ui.foot(look="share", shown="view=files"):
            ui.label("{status}", tone="dim")
            for v, field in VERBS:
                if v == "OPEN":
                    ui.button("empty", "danger", icon="trash")
                ui.button(field, _KINDS.get(v, "normal"), icon=_ICONS[v])
        with ui.dialog("Rename", ["cancel", "rename_it"], shown="asking=rename"):
            ui.field("Name", "typed", ListShellApp.RENAME_MAX, on="rename_it")
        with ui.dialog("Empty the Trash?", ["cancel", "empty_it"], kind="danger", shown="asking=empty"):
            ui.label("{empty_line}", wrap="word")
        with ui.dialog("Use in a game", ["cancel", "add"], shown="asking=game"):
            with ui.rows("targets", cur="target"):
                ui.link("add", icon="game", label="{.title}")
        with ui.dialog("Used in", ["close_used", "resend"], shown="asking=used"):
            with ui.rows("uses", cur="use", empty="Not used yet."):
                ui.link("resend", "{.note}", icon="game", label="{.label}")


def is_app(cart):
    """True only for the shipped Files identity, not a renamed or copied
    cart."""
    if (not cart or cart.get("title") != "Files"
            or "files" not in (cart.get("permissions") or ())):
        return False
    path = cart.get("path")
    if not path:                 # embedded fallback cart (no writable store)
        return int(cart.get("version", 0)) >= 1
    return builtin_name(path) == "moybyte.files.moy"


def _inside(fn):
    """A method that writes the page's state: run in a handler's run, or in
    one of its own when the console asks (a test, the router)."""
    def run(self, *args, **kw):
        return self._in(lambda: fn(self, *args, **kw))
    return run


# The shell roles this app uses (runtime/shell/app_context.py). `nav` carries
# the app-to-app jumps the router takes (a drawing opens in Paint, a note on
# the text page, a project in the Editor). WALL, GAME and USE copy a drawing
# into the backdrop and into a project (`carts`, `wallpaper`:
# runtime/apps/picture_copies.py), and `artwork` follows a renamed drawing
# Paint has open.
NEEDS = ("files", "nav", "artwork", "carts", "wallpaper")


class FilesAppLayer(uitree_app.app_layer("files", "Files", files_page, is_app, needs=NEEDS),
                    ListShellApp):
    """The Files app: the page's engine, and what its handlers ask of the
    console (the store, the router, the verbs)."""

    PICTURE_ACTIONS = ("OPEN", "WITH", "NAME", "COPY", "WALL", "GAME", "USE", "DEL")
    DOC_ACTIONS = ("OPEN", "WITH", "NAME", "COPY", "DEL")   # the kinds the router opens
    # A vault SCRIPT is a PROGRAM, so RUN leads (docs/history/text_editing_2026-09.md
    # step 6). OPEN stays beside it: a script is still text, and editing it is
    # the other thing you do with one.
    SCRIPT_ACTIONS = ("RUN", "OPEN", "WITH", "NAME", "COPY", "DEL")
    PLAIN_ACTIONS = ("WITH", "NAME", "COPY", "DEL")     # kinds the shell opens no door to
    # An arrival is opened (the door its type takes, through "open with";
    # never RUN, whatever it is), sent on, or deleted to the Trash.
    DOWNLOAD_ACTIONS = ("OPEN", "WITH", "DEL")
    PROJECT_ACTIONS = ("OPEN", "PLAY")
    THEME_ACTIONS = ("OPEN",)
    TRASH_ACTIONS = ("RESTORE",)
    # The kinds a row's SEND offers to a console nearby where this console
    # can beam (runtime/run/link_beam.py): a project as its cart, a file as
    # it is; recordings and stories are folders, which a beam does not carry.
    SEND_KINDS = (PROJECTS, "docs", "drawings", "sprites", "music", "downloads")

    def __init__(self, ctx, names=None):
        super().__init__(ctx, names)
        self.engine.env = self
        self._store = ctx.files       # ListShellApp's storage role
        self._nav = ctx.nav
        self._art = ctx.artwork
        self._carts = ctx.carts
        self._copies = PictureCopies(ctx)
        self.names = names
        self.rows = ()                # (name, kind, kind label, icon, cart) per row
        self.counts = {}
        self.trash = ()
        self._save_failed = False
        self.project_names = ()       # Use in game's targets
        self.used_rows = ()           # provenance "used in:" rows (#108 phase 2)
        self.used_name = None

    # -- the page's state, read and written from the console's side -------------

    def _in(self, fn, *args):
        """`fn` run where the page's state may be written: a handler's run,
        or one of its own when the console asks (a test, the router)."""
        e = self.engine
        if ui._NOW.app is e:
            return fn(*args)
        got = e.run(fn, *args, action="console")
        ui.commit(e)
        self._damage.all()
        return got

    def _get(self, name):
        self.engine._bind()
        return self.engine.s._v[name]

    def _put(self, name, value):
        self._in(setattr, s, name, value)

    @property
    def place(self):
        return self._get("place") or PROJECTS

    @property
    def level(self):
        """The handheld's page: places | files."""
        return self._get("view")

    @level.setter
    def level(self, v):
        self._put("view", v)

    @property
    def cur(self):
        r = self._get("cur")
        return int(r[1:]) if r else -1

    @cur.setter
    def cur(self, i):
        self._put("cur", row_id(i) if 0 <= i < len(self.rows) else "")

    @property
    def dialog(self):
        """None | rename | empty | game | used: the dialog that is up."""
        d = self._get("asking")
        return None if d == "none" else d

    @dialog.setter
    def dialog(self, d):
        self._put("asking", d or "none")

    @property
    def status(self):
        return self._get("status")

    @status.setter
    def status(self, v):
        self._put("status", v)

    @property
    def rename_text(self):
        return self._get("typed")

    @rename_text.setter
    def rename_text(self, v):
        self._put("typed", v)

    def index(self, rid):
        return int(rid[1:]) if rid else -1

    # -- store ----------------------------------------------------------------

    def _refresh_counts(self):
        """Every kind's count and the trash listing: one store op each."""
        counts = {}
        for _key, _label, _icon, kinds in PLACES:
            for kind in kinds:
                n, err = self._store.count(kind)
                counts[kind] = n if err is None else 0
        trash, err = self._store.trash_list()
        self.trash = tuple(trash) if err is None else ()
        counts[PROJECTS] = len(self._nav.projects())
        counts[THEMES] = len(self._themes())
        counts[TRASH] = len(self.trash)
        self.counts = counts
        self._show_places()

    @_inside
    def _show_places(self):
        s.places = [{"id": p[0], "label": p[1], "icon": p[2], "count": str(self._count(p[0]))}
                    for p in self.shown_places()]
        s.trashed = bool(self.trash)

    def _themes(self):
        """The store's theme packages, by folder."""
        return tuple(_folder_of(c) for c in self._carts.all()
                     if c.get("type") == "theme")

    def _count(self, key):
        for k, _label, _icon, kinds in PLACES:
            if k == key:
                if kinds:
                    return sum([self.counts.get(kind, 0) for kind in kinds])
                return self.counts.get(key, 0)
        return 0

    def shown_places(self):
        """The places the side shows: THEMES once there are any."""
        return tuple(p for p in PLACES if p[0] != THEMES or self.counts.get(THEMES))

    def _list(self, key):
        """The rows of place `key`, newest first within each kind."""
        out = []
        if key == PROJECTS:
            for cart in self._nav.projects():
                label, icon = CART_KIND.get(cart.get("type") or "game",
                                            (_cap(cart.get("type") or "cart"), "game"))
                # its title, as the home names it
                name = cart.get("title") or shown_name(_folder_of(cart))
                out.append((name, PROJECTS, label, icon, cart))
        elif key == THEMES:
            for folder in self._themes():
                out.append((shown_name(folder), THEMES, "Theme", "wallpaper", folder))
        elif key == TRASH:
            for kind, name in self.trash:
                label, icon = kind_of(kind, name)
                out.append((name, kind, label, icon, None))
        else:
            for k, _label, _icon, kinds in PLACES:
                if k != key:
                    continue
                for kind in kinds:
                    names, err = self._store.list(kind)
                    if err is not None:
                        continue
                    for name in names or ():
                        label, icon = kind_of(kind, name)
                        if kind == "docs" and _modes.is_script(name):
                            label = "Script"
                            icon = "cart_lua" if name.endswith(".lua") else "cart_py"
                        out.append((name, kind, label, icon, None))
        return tuple(out)

    def open(self):
        self.engine.open()
        self._damage.all()

    def _opened(self):
        s.asking = "none"
        s.view = "files" if metric_desk() else "places"
        s.status = ""
        self._refresh_counts()
        self.open_place(self.place)
        if self.rows and metric_desk():
            ui.focus(row_id(0) + "/open")
        else:
            ui.focus(self.place + "/open_place")

    # -- the place and its rows ---------------------------------------------------

    @_inside
    def open_place(self, key, keep=None, show=False, pick=False):
        """Show place `key`: its rows listed once (never per frame), the row
        named `keep` current, else the first; `show` (a place opened) turns a
        handheld to its files, `pick` (the focus moved onto it) leaves the
        focus where it is."""
        self.rows = self._list(key)
        s.place = key
        send = _intents.INTENTS.can_send()
        s.files = [self._model_row(i, r, key, send) for i, r in enumerate(self.rows)]
        s.any = bool(self.rows)
        s.in_trash = key == TRASH
        s.none_line = "The Trash is empty" if key == TRASH else "Nothing here yet"
        for p in PLACES:
            if p[0] == key:
                s.caption = p[1]
        first = row_id(0) if self.rows else ""
        if not pick and s.cur != first:     # a write moves the focus onto the row
            s.cur = first
        elif pick and self.index(s.cur) >= len(self.rows):
            s.cur = ""                      # a place picked on the desk keeps the focus on the places
        if keep is not None:
            self.select(keep)
        if show:
            s.view = "files"
            if self.rows:
                ui.focus(s.cur + "/open")

    def _model_row(self, i, r, place, send):
        labels = self._labels(place, r[1], r[0], send)
        row = {"id": row_id(i), "name": r[0], "kind": r[2], "icon": r[3]}
        for v, field in VERBS:
            row[field] = v in labels
        return row

    def _refresh(self, keep=None):
        self._refresh_counts()
        self.open_place(self.place, keep)

    def names_shown(self):
        """The names the place lists, in its order."""
        return [r[0] for r in self.rows]

    def select(self, name):
        """Make the row named `name` current (None: none)."""
        i = -1
        for j, r in enumerate(self.rows):
            if r[0] == name:
                i = j
                break
        self.cur = i

    def _row(self):
        cur = self.cur
        return self.rows[cur] if 0 <= cur < len(self.rows) else None

    def sel_name(self):
        r = self._row()
        return r[0] if r is not None else None

    def sel_kind(self):
        r = self._row()
        return r[1] if r is not None else None

    def _action_labels(self):
        """The verbs the current row takes, SEND before DELETE where the row
        can be sent."""
        r = self._row()
        if r is None:
            return ()
        return self._labels(self.place, r[1], r[0], _intents.INTENTS.can_send())

    def _labels(self, place, kind, name, send):
        labels = self._row_labels(place, kind, name)
        if send and kind in self.SEND_KINDS:
            if labels[-1:] == ("DEL",):
                return labels[:-1] + ("SEND", "DEL")
            return labels + ("SEND",)
        return labels

    def _row_labels(self, place, kind, name):
        if place == PROJECTS:
            return self.PROJECT_ACTIONS
        if place == THEMES:
            return self.THEME_ACTIONS
        if place == TRASH:
            return self.TRASH_ACTIONS
        if kind == DOWNLOADS:
            return self.DOWNLOAD_ACTIONS
        if kind == "drawings":
            return self.PICTURE_ACTIONS
        if kind == "docs":
            if _modes.is_script(name or ""):
                return self.SCRIPT_ACTIONS
            return self.DOC_ACTIONS
        return self.PLAIN_ACTIONS

    # -- the router -----------------------------------------------------------

    def route(self, name, kind=None, cart=None):
        """Open `name` by WHAT IT IS, in the order
        docs/theme_and_shell_2026-11.md §10 fixes:

            a `.moy` folder      the project Editor, never a listing
            a cart's main file   that cart's Editor, on the Code tab
            an image             Paint
            any other text file  the shell's text page, in its mode

        `kind` is the user-files kind an item came from (its extension is the
        kind's, asked of the mode table); `cart` is the project a project file
        came from. Returns the door taken -- "editor" / "code" / "paint" /
        a mode name -- or None when nothing here can open it, which is what
        the status line reports.

        A user file (a drawing, a note) goes to the app that opens its type,
        by the intents' route "Open with" takes; a project and its own files
        go through ctx.nav by REGISTERED ID. Files holds no reference to
        another app's class, and a build without one degrades to the status
        line instead of an AttributeError."""
        door, subject = self.door(name, kind, cart)
        if door == "editor":
            return self._to_editor(subject)
        if door == "appearance":
            if not self._nav.open_app("appearance"):
                self.status = "No Appearance app"
                return None
            return door
        if door == "code" and cart is not None:
            # The cart-main door, NOT the `code` MODE a standalone `.py` edits
            # in -- `text_modes.CODE` is the same string, and only a project
            # file reaches the Editor.
            return self._to_editor(subject, tab="code")
        if door == "paint":
            if cart is None:
                return self._to_app(subject, kind, door)
            return self._to_paint(subject, cart)
        return self._to_text(name, kind, door, cart)

    def door(self, name, kind=None, cart=None):
        """WHICH door `name` takes, as `(door, subject)` -- the router's rules
        as a pure function, so the order above is one readable ladder and a
        test can ask what a file IS without opening anything. `door` is
        "editor" / "code" / "paint" or a `text_modes` mode name; `subject` is
        what that door opens."""
        if kind == PROJECTS:
            return "editor", (cart or self._project(name))
        if kind == THEMES:
            return "appearance", name
        fname = name if cart is not None else _modes.file_name(kind, name)
        if cart is not None and fname == cart.get("main", "main.py"):
            return "code", cart
        if _modes.is_image(fname):
            # A cart's own image (`images/*.moyimg`, its `cover.png`) is a
            # PICTURE like any other, so it takes the picture door -- Paint
            # opens it on the project kind and writes it back into the cart's
            # folder.
            return "paint", name
        return _modes.mode_for(fname), name

    def _project(self, name):
        """The cart a PROJECTS row names (its folder, or the folder as a row
        shows it), against the live roster rather than a stale dict."""
        for cart in self._nav.projects():
            folder = _folder_of(cart)
            if name in (folder, shown_name(folder), cart.get("title")):
                return cart
        return None

    def _to_editor(self, cart, tab=None):
        if cart is None or not self._nav.edit(cart, tab):
            self.status = "Can't open"
            return None
        return "code" if tab else "editor"

    def _to_paint(self, name, cart):
        """Open a cart's OWN image in Paint, which reads and writes it on that
        project's kind: the same file, in place, so an edited cover is the
        cover."""
        if not self._nav.open_image(name, None, cart):
            self.status = "No Paint app"
            return None
        return "paint"

    def _to_app(self, name, kind, door):
        """A user file to the app that opens its type: the intents' route,
        the one "Open with" takes (runtime/system/intents.py), asked as the
        shell, as Files is."""
        item = _intents.item_of(kind, name)
        if item is None or not _intents.INTENTS.open_with(_intents.SHELL, item, False):
            self.status = "No app opens it"
            return None
        return door

    def _to_text(self, name, kind, mode, cart=None):
        if kind is None:
            # A project's own text file. It opens through that project's
            # EDITOR (`nav.edit_file`), never straight into the handle: the
            # Config tab's Files is the same door, and going through it
            # is what keeps the loader in the loop -- the return re-reads the
            # folder, so a manifest JSON mode was allowed to write invalid is
            # re-validated where the kid can see it.
            if not self._nav.edit_file(cart, name, mode):
                self.status = "Can't open"
                return None
            return mode
        return self._to_app(name, kind, mode)

    def _open_row(self, i):
        """The open gesture on row i: its door, or the Trash's restore."""
        if not 0 <= i < len(self.rows):
            return
        self.cur = i
        name, kind, _label, _icon, cart = self.rows[i]
        if self.place == TRASH:
            self._restore(i)
        elif kind == PROJECTS:
            self.route(name, PROJECTS, cart)
        elif kind == THEMES:
            self.route(cart, THEMES)
        else:
            self.route(name, kind=kind)

    # -- the verbs --------------------------------------------------------------

    @_inside
    def _act(self, verb, name=None):
        """Verb `verb` on the current row (`name`, where given, made current)."""
        if name is not None:
            self.select(name)
        row = self._row()
        art = self._copies
        if verb == "EMPTY":
            if self.trash:
                s.empty_line = "%d %s deleted for good." % (
                    len(self.trash), "item is" if len(self.trash) == 1 else "items are")
                s.asking = "empty"
            return
        if row is None:
            return
        name, kind = row[0], row[1]
        if verb == "RUN":
            ok, why = self._nav.run_script(kind, name)
            if not ok:
                self.status = why
        elif verb == "OPEN":
            self._open_row(self.cur)
        elif verb == "WITH":
            # The apps whose manifest opens its type, asked always
            # (runtime/system/intents.py): the one picked becomes the choice.
            # Files is the shell's, so it asks as the shell.
            item = _intents.item_of(kind, name)
            if item is None or not _intents.INTENTS.open_with(_intents.SHELL, item, True):
                self.status = "No app opens it"
        elif verb == "PLAY":
            self._nav.play(row[4])
        elif verb == "SEND":
            item = row[4] if kind == PROJECTS else _intents.item_of(kind, name)
            if item is None or not _intents.INTENTS.send(_intents.SHELL, item):
                self.status = "Can't send"
        elif verb == "RESTORE":
            self._restore(self.cur)
        elif verb == "NAME":
            s.typed = name[:self.RENAME_MAX]
            s.asking = "rename"
            ui.focus("typed")
        elif verb == "COPY":
            res = self._store.duplicate(kind, name)
            if self._persist(res):
                self.status = "Duplicated"
                self._refresh(keep=res[0] or name)
        elif verb == "WALL":
            self.status = "Wallpaper set" if art.set_wallpaper(name) else \
                (art.last_error or "Can't set")
        elif verb == "GAME":
            self.project_names = art.targets()
            s.targets = [{"id": str(i), "title": n} for i, n in enumerate(self.project_names)]
            s.target = "0" if self.project_names else ""
            s.asking = "game"
        elif verb == "USE":
            # Provenance "used in:" list (#108 phase 2): the wallpaper and
            # every project background copied from this drawing, stale copies
            # flagged.
            self.used_name = name
            self._uses()
            s.use = "0" if self.used_rows else ""
            s.asking = "used"
        elif verb == "DEL":
            if self._persist(self._store.delete(kind, name)):
                self.status = "Moved to the Trash"
                cur = self.cur
                self._refresh()
                self.cur = min(cur, len(self.rows) - 1)

    def _uses(self):
        self.used_rows = tuple(self._copies.usage(self.used_name))
        s.uses = [{"id": str(i), "label": r["label"], "note": "Changed" if r.get("stale") else ""}
                  for i, r in enumerate(self.used_rows)]

    @_inside
    def _rename_commit(self):
        row = self._row()
        text = s.typed
        s.asking = "none"
        if row is not None and text.strip():
            name, kind = row[0], row[1]
            res = self._store.rename(kind, name, text)
            if self._persist(res):
                new = res[0] or name
                # A renamed open drawing keeps Paint pointed at it.
                self._art.follow(kind, name, new)
                self.status = "Renamed"
                self._refresh(keep=new)
        self._focus_cur()

    @_inside
    def _restore(self, index):
        try:
            name, kind = self.rows[index][0], self.rows[index][1]
        except IndexError:
            return
        if self._persist(self._store.restore(kind, name)):
            self.status = "Restored " + name
            self._refresh()

    @_inside
    def _empty_trash(self):
        s.asking = "none"
        if self._persist(self._store.empty_trash()):
            self.status = "The Trash is empty"
        self._refresh()
        self._focus_cur()

    @_inside
    def _resend(self, i):
        """Re-copy the drawing to one usage row -- the one-tap UPDATE / send-
        again (#108 phase 2). Stays in the list, re-scanned so the mark clears."""
        art = self._copies
        if 0 <= i < len(self.used_rows) and self.used_name:
            row = self.used_rows[i]
            if art.resend(row, self.used_name):
                self.status = "Sent to " + row["label"]
            else:
                self.status = art.last_error or "Can't send"
            self._uses()

    @_inside
    def _game_pick(self, i):
        art = self._copies
        name = self.sel_name()
        s.asking = "none"
        if 0 <= i < len(self.project_names) and name:
            title = art.attach(i, name)
            self.status = ("Added to " + title) if title else \
                (art.last_error or "Can't add")
        self._focus_cur()

    @_inside
    def _close_dialog(self):
        s.asking = "none"
        self._focus_cur()

    def _focus_cur(self):
        ui.focus(s.cur + "/open" if s.cur else s.place + "/open_place")


def metric_desk():
    from layout_base import metric_class, DESK
    return metric_class() == DESK
