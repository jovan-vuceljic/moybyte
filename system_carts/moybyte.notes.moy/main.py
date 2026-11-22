# Notes -- the console's one text app, and it is nothing but a cartridge (#181).
#
# Everything below is ordinary cart code you can open in the Editor and change.
# What makes it an APP rather than a game is its manifest.json:
#
#     "type": "app"                 -> the shell runs it WITH the exitable bar,
#                                      so it can never trap you
#     "permissions": [...]          -> the shell hands it exactly these, and
#                                      nothing else. A permission it does not
#                                      ask for has no NAME here at all: writing
#                                      `carts` in this file is a NameError, not
#                                      a locked door. That is the whole sandbox.
#     "extensions": ["moybyte.uitree"] -> its `ui` is the UI tree API: the page
#                                      is declared once (state, actions, the
#                                      build below) and the console's engine
#                                      draws it and moves focus, keys and taps
#
# The one that matters here is `files:documents`, which brings BOTH the storage verbs
# (`files.list()`, `files.new_name()`, `files.rename()`, `files.duplicate()`,
# `files.delete()`, `files.badge()`) and `open_editor(name)` -- a handle onto
# one note, over the console's own editor. The editor is not in this file:
# the text, the caret, wrap, undo, the clipboard, saving and running a program
# (`ed.run()` on a `.py` or `.lua`, and back here when it ends) all live in the
# shell. The page's text editor adopts the handle (`s.note.adopt(ed)`), so it
# types into the note and draws it; Open link asks the handle what the caret's
# line holds (`ed.follow()`: a `[ ]` box ticks, a `[[link]]` opens its note).

NAME_MAX = 24          # characters a name takes
ICON = {"MD": "notes", "TXT": "doc", "JSON": "doc", "PY": "code", "LUA": "code"}
MODES = {"md": "Markdown", "code": "Program", "json": "Data", "text": "Text"}
NEW = "+new"           # the list's first row, New note: no note's name

s = ui.state(
    notes=ui.model(key="name", name="", shown="", icon=""),   # New note, then the vault
    cur=ui.row_of("notes"),
    store=True,                     # a card to keep notes on
    editing=False,                  # a note is open
    routed=False,                   # ...the console asked for it (Files): Back goes back there
    title="Notes",                  # ...its name and its kind (the page's title)
    status="",                      # ...why its last save was refused
    note=ui.doc("", "markdown"),    # ...its text, the handle's (adopt)
    md=False,                       # ...it is Markdown: Open link
    can_run=False,                  # ...it is a program: Run
    selecting=False,                # ...Select is on
    view=ui.enum("nostore", "empty", "list", "note", init="list"),   # what a handheld shows
    side=ui.opt(0),                 # the desk's vault column, as its divider left it
    asking=ui.enum("none", "new", "rename", init="none"),
    typed="",                       # the name the dialog holds
)
ui.derive("listed", cond="@desk || !editing")     # the vault shows: its verbs are on offer
ui.app("Notes", icon="notes", back="close")

ed = None              # the open note's editor handle (None: none open)
names = []             # the vault, newest first


def shown(name):
    """A name as the list shows it: a note's bare and in words, any other
    file's with its extension."""
    if "." in name:
        return name
    words = name.replace("_", " ")
    return words[:1].upper() + words[1:]


def _refresh(keep=None):
    global names
    got, err = files.list()
    s.store = err is None
    names = list(got) if err is None else []
    s.notes = [{"name": NEW, "shown": "New note", "icon": "new"}] + [
        {"name": n, "shown": shown(n), "icon": ICON.get(files.badge(n), "doc")} for n in names]
    s.view = "nostore" if err is not None else "note" if s.editing else "list" if names else "empty"
    if keep is not None and keep in names:
        s.cur = keep
    elif s.cur not in names:
        s.cur = names[0] if names else NEW


def _find(target):
    """The note a `[[link]]` names: by its name, or as the list shows it."""
    t = target.strip().lower()
    for n in names:
        if n.lower() == t or shown(n).lower() == t:
            return n
    return target


def _show(handle, routed=False):
    global ed
    _shut()
    ed = handle
    s.note.adopt(ed)
    s.editing = True
    s.routed = routed
    s.md = ed.mode() == "md"
    s.can_run = ed.can_run()
    s.selecting = False
    _status()
    prefs.set("last", ed.name())
    _refresh(ed.name())


def _shut():
    """The open note saved and let go (no Save button: leaving saves)."""
    global ed
    if ed is not None:
        name = ed.name()
        ed.close()
        ed = None
        s.editing = False
        s.title = "Notes"
        _refresh(name)


def _open_name(name):
    got = open_editor(name)
    if got is not None:
        _show(got)


def _status():
    s.title = "%s · %s" % (shown(ed.name()), MODES.get(ed.mode(), ed.mode()))
    s.status = ed.badge()


# -- the actions ---------------------------------------------------------------


def opened():
    """A note the console was asked to open (Files routed a `.md`, a `.json`
    or a `.txt` here) is shown; else the last one opened, where it is kept."""
    _refresh()
    asked = open_editor()
    if asked is not None:
        _show(asked, True)
        return
    last = prefs.get("last")
    if last in names:
        _open_name(last)


def open_row(row):
    if row.name == NEW:
        new()
    else:
        _open_name(row.name)


def close():
    _shut()
    ui.focus(s.cur + "/open")       # the list again, on the note's row


def new():
    s.typed = ""
    s.asking = "new"
    ui.focus("typed")


def rename(row):
    if row.name == NEW:
        return
    s.cur = row.name
    s.typed = shown(row.name)[:NAME_MAX]
    s.asking = "rename"
    ui.focus("typed")


def duplicate(row):
    if row.name == NEW:
        return
    got, err = files.duplicate(row.name)
    _refresh(got if err is None else row.name)


def trash(row):
    if row.name == NEW:
        return
    if ed is not None and ed.name() == row.name:
        _shut()
    files.delete(row.name)          # to the Trash, which restores: nothing to ask
    _refresh()


def make():
    """The dialog's verb: make the new note and open it, or rename the
    row's."""
    what, name = s.asking, s.typed.strip()
    s.asking = "none"
    if what == "new":
        got, err = files.new_name(name or None)
        if err is None:
            got, err = files.save_text(got, "")
        if err is None:
            _refresh(got)
            _open_name(got)
    elif name and s.cur:
        was = s.cur
        if ed is not None and ed.name() == was:
            _shut()
        got, err = files.rename(was, name)
        _refresh(got if err is None else was)


def cancel():
    s.asking = "none"


def undo():
    s.note.undo()


def redo():
    s.note.redo()


def select():
    ed.select_mode()
    s.selecting = ed.selecting()


def copy():
    s.note.copy()


def cut():
    s.note.cut()


def paste():
    s.note.paste()


def run():
    if ed.run():
        ui.after(0, "restatus")     # a run the console could not start badges the note
    else:
        _status()


def restatus():
    if ed is not None:
        _status()


def follow():
    got = ed.follow()
    if got is not None and got[0] == "link":
        _open_name(_find(got[1]))
    elif got is not None:
        s.note.go(got[1] + 1, ed.caret()[1] + 1)    # the tick moves the version


ui.hook("opened", opened)
ui.hook("open_name", _open_name, takes="arg")
ui.hook("restatus", restatus)
ui.action("open", "Open", open_row, takes="row", hint="")
ui.action("close", "Close", close, when="editing && !routed", off="hide")
ui.action("new", "New note", new, keys=("n",), when="store && listed", off="hide")
ui.action("rename", "Rename", rename, takes="row", row="cur", keys=("m",), when="listed", off="hide")
ui.action("duplicate", "Duplicate", duplicate, takes="row", row="cur", keys=("ctrl+d",), when="listed",
          off="hide")
ui.action("trash", "Move to Trash", trash, takes="row", row="cur", keys=("t",), when="listed", off="hide")
ui.action("make", "Make", make)
ui.action("rename_it", "Rename", make)
ui.action("cancel", "Cancel", cancel)
ui.action("undo", "Undo", undo, hint="")
ui.action("redo", "Redo", redo, hint="")
ui.action("select", "Select", select, hint="")
ui.action("copy", "Copy", copy, keys=("ctrl+c",), hint="")
ui.action("cut", "Cut", cut, keys=("ctrl+x",), hint="")
ui.action("paste", "Paste", paste, keys=("ctrl+v",), hint="")
ui.action("run", "Run", run, when="can_run", off="hide", hint="")
ui.action("follow", "Open link", follow, keys=("ctrl+o",), when="md", off="hide", hint="")


# -- the page ------------------------------------------------------------------


def _vault():
    with ui.scroll("vault"):
        with ui.rows("notes", cur="cur"):
            ui.link("open", icon="{.icon}", label="{.shown}")


def _note():
    ui.text_editor("note", focus=True)
    with ui.row("tools"):
        ui.button("undo", icon="undo", alone=True)
        ui.button("redo", icon="redo", alone=True)
        ui.button("select", icon="select", alone=True, marked="selecting")
        ui.button("copy", icon="copy", alone=True)
        ui.button("cut", icon="cut", alone=True)
        ui.button("paste", icon="paste", alone=True)
        ui.button("follow", icon="forward", alone=True)
        ui.button("run", icon="run", alone=True)
        ui.status("{status}", shown="status")


def _no_store():
    ui.empty("No storage", icon="notes", lines=["Notes keep to a card;", "put one in to start."])


def _no_notes():
    ui.link("new", icon="new")
    ui.empty("No notes yet", icon="notes", lines=["A note can be a list, a story,", "a plan or a little program."])


def _pick():
    ui.empty("Pick a note", icon="notes", lines=["Or make a new one."])


def build():
    with ui.page("{title}"):
        # the desk: the vault beside the note
        with ui.panes("row", "desk", shown="@desk"):
            with ui.pane("vault", size="side", start=280, head=False):
                ui.switch("view", {"nostore": _no_store, "empty": _no_notes, "_": _vault})
            with ui.pane("doc", grow=True, head=False):
                ui.switch("editing", {True: _note, False: _pick})
        # a handheld: one at a time
        ui.switch("view", {"nostore": _no_store, "empty": _no_notes, "list": _vault, "note": _note},
                  shown="!@desk")
        with ui.dialog("New note", ["cancel", "make"], shown="asking=new"):
            ui.field("", "typed", NAME_MAX, on="make", hint="my note")
            ui.label("End the name with .py or .lua to make a program you can Run.", wrap="word",
                     tone="dim")
        with ui.dialog("Rename", ["cancel", "rename_it"], shown="asking=rename"):
            ui.field("", "typed", NAME_MAX, on="rename_it", hint="my note")
