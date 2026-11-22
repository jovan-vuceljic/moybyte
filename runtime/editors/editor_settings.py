"""The Editor's Config tab ("Make it mine", #3/#15) as `uitree` pages, the
handheld's tab and the desk Editor's Settings pane alike.

The cards page: a note where the cart's run reads none of some tabs' files
(`EditorApp._offers`), the cart's `edit` cards as one group on a card (an
`int` a slider stepping by the card's step, a two-way `choice` a toggle, a
`sprite-tiles` or `bg-thumbs` choice and a `choice-icons` one of more than
two a row of its pictures, the current one on the selection plate, left and
right or Enter stepping it and a tap taking a picture, any other choice a
cycle), then This project: Cart info and Files. A cart whose
manifest did not parse (`moy_carts.load` keeps it with its reason in
`cart["broken"]`) shows the reason and Files instead. Files is a page pushed
over it: the project's own files, each the tab it opens in. Cart info and
New script are dialogs.

`CardsLayer` (cards_layer.py) is the host: it writes the cart's values into
the state (`sync`), and the handlers reach it through `uitree_app.env()`
for what touches the cart (a card's value, the file routing, the commits)."""
import uitree as ui
import uitree_app

s = ui.state(
    cards=ui.model(key="id", id="", shape=ui.enum("int", "two", "cycle", "pics", init="int"), label="",
                   v=0, lo=0, hi=100, on=False, k=0, names=""),
    pick_h=0,
    missing="", broken="", broken_title="", fixable=False, title="", nfiles="",
    file_rows=ui.model(key="name", name="", label="", word="", icon=""),
    files_msg="",
    asking=ui.enum("none", "meta", "newf", init="none"),
    f_title="", f_author="", f_name="", new_sub="", ask_msg="",
)


def card_label(f):
    """A card's label: its `card` text before `{value}`, else its `label`,
    in sentence case and without a closing "is" ("RUN AT {value}" -> "Run
    at", "HERO IS {value}" -> "Hero")."""
    text = f.get("card") or f.get("label") or f.get("key") or ""
    cut = text.find("{")
    if cut >= 0:
        text = text[:cut]
    text = text.strip().rstrip(":=").strip()
    if text.lower().endswith(" is"):
        text = text[:-3]
    if not text:
        text = str(f.get("label") or f.get("key") or "")
    return text[:1].upper() + text[1:].lower()


def sync(vals):
    """The host's values: (the cards' rows, the missing tabs' note, why
    the page shows no cards and its title, whether Files fixes that, the
    cart's title, its files' count, a picker row's height)."""
    rows, s.missing, s.broken, s.broken_title, s.fixable, s.title, s.nfiles, s.pick_h = vals
    if s.cards != rows:
        s.cards = rows


def opened():
    """A visit: the cards page with no dialog up."""
    s.asking = "none"


def set_int(row):
    uitree_app.env().set_int(row.id, row.v)


def set_two(row):
    uitree_app.env().set_choice(row.id, 1 if row.on else 0)


def set_k(row):
    uitree_app.env().set_choice(row.id, row.k)


def draw_pick(cv, x, y, w, h, row):
    """A picker's row: its label, then each choice's picture in a tile at
    the row's right, the current one on the selection plate."""
    _WH[0], _WH[1] = w, h
    uitree_app.env().draw_picker(cv, ui.colors(), x, y, w, h, row.id, row.label, row.k)


_WH = [0, 0]        # a picker's row as the last frame drew it: every picker's is one size


def pick_keys(i, row):
    """Left and right step a picker, Enter takes the next; the other keys
    move focus off it."""
    d = i.steps("right") - i.steps("left") + (1 if i.pressed("a") or i.pressed("run") else 0)
    if not d:
        return False
    host = uitree_app.env()
    f = host.field(row.id)
    if f is not None:
        host.set_choice(row.id, (row.k + d) % len(f["choices"]))
    return True


def pick_at(ev):
    """A press on a picker's tile takes it."""
    if ev.kind != "down" or ev.row is None:
        return
    host = uitree_app.env()
    f = host.field(ev.row.id)
    if f is None:
        return
    for k, t in enumerate(host.tiles(len(f["choices"]), _WH[0], _WH[1])):
        if t[0] <= ev.x < t[0] + t[2] and t[1] <= ev.y < t[1] + t[2]:
            host.set_choice(ev.row.id, k)


def files():
    s.file_rows, s.files_msg = uitree_app.env().listing()
    ui.push(files_page)
    if s.file_rows:
        ui.focus("%s/open_file" % s.file_rows[0].name)      # the list opens on its first file


def open_file(row):
    uitree_app.env().open_file(row.name)


def open_name(name):
    """A project file opened by its name (New script's, a host's)."""
    uitree_app.env().open_file(name)


def cart_info():
    host = uitree_app.env()
    s.f_title, s.f_author = host.meta()
    s.ask_msg = ""
    s.asking = "meta"
    ui.focus("f_title")


def new_script():
    s.new_sub = uitree_app.env().new_sub()
    s.f_name, s.ask_msg = "", ""
    s.asking = "newf"
    ui.focus("f_name")


def save():
    s.ask_msg = uitree_app.env().commit_meta(s.f_title, s.f_author)
    if not s.ask_msg:
        s.asking = "none"


def add():
    s.ask_msg = uitree_app.env().commit_newf(s.f_name)
    if not s.ask_msg:
        s.asking = "none"


def cancel():
    s.asking = "none"


def typed():
    s.ask_msg = ""


def say(why):
    """Why a file did not open, under the list."""
    s.files_msg = why


ui.hook("opened", opened)
ui.hook("sync", sync, takes="arg")
ui.hook("set_int", set_int, takes="row")
ui.hook("set_two", set_two, takes="row")
ui.hook("set_k", set_k, takes="row")
ui.hook("pick_at", pick_at, takes="pointer")
ui.hook("typed", typed)
ui.hook("open_name", open_name, takes="arg")
ui.hook("say", say, takes="arg")
ui.action("files", "Files", files)
ui.action("open_file", "Open", open_file, takes="row")
ui.action("cart_info", "Cart info", cart_info)
ui.action("new_script", "New script", new_script)
ui.action("save", "Save", save)
ui.action("add", "Add", add)
ui.action("cancel", "Cancel", cancel)


def _meta():
    with ui.dialog("Cart info", ["cancel", "save"], shown="asking=meta", look="keys"):
        ui.field("Title", "f_title", max=24, on="save", changed="typed")
        ui.field("Made by", "f_author", max=24, on="save", changed="typed",
                 hint="Your name (you can leave it)")
        ui.label("{ask_msg}", tone="danger", wrap="word", lines=2, shown="ask_msg")


def _newf():
    with ui.dialog("New script", ["cancel", "add"], shown="asking=newf", look="keys"):
        ui.label("{new_sub}", tone="dim", wrap="word", lines=2)
        ui.field("Name", "f_name", max=24, on="add", changed="typed", hint="helpers")
        ui.label("{ask_msg}", tone="danger", wrap="word", lines=2, shown="ask_msg")


def cards_page():
    with ui.page(""):
        ui.empty("{broken_title}", icon="warn", lines=["{broken}"], shown="broken")
        ui.button("files", kind="primary", shown="fixable")
        ui.note(["{missing}"], icon="info", shown="missing && !broken")
        with ui.group("", look="card", shown="cards && !broken"):
            ui.rows("cards", by="shape", cases={
                "int": lambda: ui.slider("{.label}", ".v", "{.lo}", "{.hi}", on="set_int"),
                "two": lambda: ui.toggle("{.label}", ".on", on="set_two"),
                "cycle": lambda: ui.seg("{.label}", ".k", text="{.names}", look="cycle", on="set_k"),
                "pics": lambda: ui.canvas("pick", draw_pick, h="{pick_h}", keys=pick_keys,
                                          pointer="pick_at", hint="Change")})
        with ui.group("This project", shown="!broken"):
            ui.link("cart_info", "{title}")
            ui.link("files", "{nfiles}")
        _meta()
        _newf()


def files_page():
    with ui.page("Files"):
        ui.empty("No files", icon="doc", lines=["{files_msg}"], shown="!file_rows")
        ui.label("{files_msg}", tone="danger", shown="files_msg && file_rows")
        with ui.rows("file_rows"):
            ui.link("open_file", "{.word}", label="{.label}", icon="{.icon}")
        _newf()
