"""The Editor's Blocks tab as a placed `uitree` page, the handheld's and a
desk Editor's Blocks pane alike (docs/media/look_2026-10/EDITOR_LAYOUT.md's
`blocks` pictures): the objects as tabs (the Stage, then each sprite with
scripts or on the stage, as many as the row holds) and the last edit's word
at the head's end, or "You levelled up to code!" on a cart that graduated;
the outline of the picked object's scripts as a table whose canvas draws
each row -- a hat in its category's colour, a statement on a plate with its
category's bar, indented by depth, the cursor's slot underlined and its
insert point as "add block"; a rule and the foot's tools (add, delete, up,
down, more, marked while a block moves) and See code, the door to the Code
tab. The insert menu, the block actions and the pickers are a popover's
menu; a number, a text or a name is typed into a dialog's field, with Use a
block where the slot takes one.

`BlockEditorUI` (block_editor_ui.py) is the host, which the handlers and the
rows' draw reach through `uitree_app.env()`: it writes the core's state into
the page's (`sync`), draws the outline's rows (`draw_row`), filters what is
typed (`typed`) and does what the handlers ask over the core
(`BlockEditor`). The keys are the host's (up and down the cursor, right the
slot, left a number's nudge, A acts) but while the menu or a dialog is up."""
import uitree as ui
import uitree_app

s = ui.state(
    none=False, graduated=False, status="", moving=False, row_h=22,
    objs=ui.model(key="k", k="", name=""),
    obj=ui.row_of("objs"),
    lines=ui.model(key="k", k="", sig="", on=0),
    at=ui.row_of("lines"),
    menu=False, menu_title="",
    items=ui.model(key="k", k="", label=""),
    asking=False, ask_title="", ask_rule=False, ask_cap="", ask_hint="", to_block=False,
    entry="",
)

# The foot's tools: (action, its word, icon).
TOOLS = (("add", "Add", "new"), ("delete", "Delete", "del"), ("up", "Up", "arrow_up"),
         ("down", "Down", "arrow_down"), ("more", "More", "more"))


def sync(vals):
    """The host's values: (no program, graduated, the status word, the
    objects' tabs, the picked one's key, the outline's rows, the cursor's
    row, a block moving, the menu up, its title, its items, the one it
    opens on, a row's height in pixels); a model None where it is as the
    host wrote it last."""
    (s.none, s.graduated, s.status, objs, obj, lines, at, s.moving, menu, s.menu_title,
     items, sel, s.row_h) = vals
    if objs is not None:
        s.objs = objs
    if s.obj != obj:
        s.obj = obj
    if lines is not None:
        s.lines = lines
    if s.at != at:
        s.at = at
    s.menu = menu
    if items is not None:
        s.items = items
        if menu and items:
            ui.focus(items[sel]["label"])       # a menu opens on its host's row (its id its text)


def marked(vals):
    """The host's cursor moved: (the row it left, the row it is on, its
    slot + 1): each row's `on`, so the two draw again."""
    was, now, on = vals
    if was and was != now and s.lines.get(was) is not None:
        s.lines.update(was, on=0)
    if now:
        s.lines.update(now, on=on)
    if s.at != now:
        s.at = now


def ask(vals):
    """A dialog up: (its title, the name rule shown, the field's caption,
    its placeholder, Use a block offered)."""
    s.ask_title, s.ask_rule, s.ask_cap, s.ask_hint, s.to_block = vals
    s.entry = ""
    s.asking = True
    ui.focus("entry")


def asked():
    """The dialog let go by its host."""
    s.asking = False


def typed():
    got = uitree_app.env().typed(s.entry)
    if got != s.entry:
        s.entry = got


def picked(row):
    uitree_app.env().pick_row(int(row.k))


def opened(row):
    uitree_app.env().open_row(int(row.k))


def chose():
    uitree_app.env().pick_object(s.obj)


def pick(row):
    uitree_app.env().menu_pick(int(row.k))


def menu_back():
    uitree_app.env().menu_back()


def _done(how):
    s.asking = False
    uitree_app.env().ask_done(how, s.entry)


def ok():
    _done("ok")


def cancel():
    _done("cancel")


def use_block():
    _done("block")


def _do(verb):
    uitree_app.env().act(verb)


ui.hook("sync", sync, takes="arg")
ui.hook("marked", marked, takes="arg")
ui.hook("ask", ask, takes="arg")
ui.hook("asked", asked)
ui.hook("typed", typed)
ui.hook("picked", picked, takes="row")
ui.hook("opened", opened, takes="row")
ui.hook("chose", chose)
ui.action("pick", "Pick", pick, takes="row")
ui.action("menu_back", "Back", menu_back)
ui.action("ok", "OK", ok)
ui.action("cancel", "Cancel", cancel)
ui.action("use_block", "Use a block", use_block)
for _a, _w, _i in TOOLS:
    ui.action(_a, _w, (lambda v: lambda: _do(v))(_a), when="!graduated", off="grey")
ui.action("code", "See code", lambda: _do("code"))


def _draw_row(cv, x, y, w, h, row):
    uitree_app.env().draw_row(cv, int(row.k), x, y, w, h)


def blocks_page():
    with ui.page(""):
        ui.empty("No blocks", icon="blocks", lines=["This cart has no program to show"], shown="none")
        with ui.row("head", pad=4, gap=8, shown="!none"):
            ui.tabs("obj", text="{.name}", on="chose", shown="!graduated")
            ui.label("You levelled up to code!", tone="value", shown="graduated")
            ui.label("{status}", tone="dim", align="end", shown="status && !graduated")
        with ui.row("body", grow=True, shown="!none"):
            with ui.table("lines", cur="at", row="{row_h}", changed="picked", on="opened"):
                ui.canvas("line", _draw_row)
        ui.rule(shown="!none")
        with ui.row("foot", pad=4, gap=2, shown="!none"):
            for a, _w, icon in TOOLS:
                if a == "more":
                    ui.button(a, icon=icon, kind="bar", alone=True, w="{@desk?36:24}", marked="moving")
                else:
                    ui.button(a, icon=icon, kind="bar", alone=True, w="{@desk?36:24}")
            ui.label("")
            ui.button("code", icon="code")
        with ui.popover("menu_pop", anchor="lines", w=220, close="menu_back", shown="menu"):
            with ui.menu("{menu_title}"):
                with ui.rows("items"):
                    ui.item("pick", label="{.label}")
        with ui.dialog("{ask_title}", ["cancel", "ok"], kind="primary", look="keys", shown="asking"):
            ui.label("Use letters, numbers and underscores.", tone="dim", wrap="word", lines=2,
                     shown="ask_rule")
            ui.field("{ask_cap}", "entry", max=24, on="ok", changed="typed", hint="{ask_hint}")
            ui.button("use_block", icon="blocks", shown="to_block")
