"""A desk Editor pane's header as a placed `uitree` page, one page a shown
pane (docs/media/look_2026-10/EDITOR_LAYOUT.md): the pane's icon and name
over its dim status, or its tabs (short where they would not fit
labelled: the current one labelled, the others their icons); where the
name and the tools do not fit, the status gives way, then the icon, then
the words, the pane's icon naming it (`form`); the tools its
content carries and the more menu of those that did not fit; the Game's
Pause; the Code pane's file tabs, Find, Go to definition and its more
menu; the Sound pane's play, speed, loop, rename and, where no Sounds list
shows, its sounds menu; the Sounds list's new sound; and Grow.

The page stands on the whole pane, the header its top row and the body's
room left to the pane's own page under it (`below`), so a more menu hangs
over the pane. `editor_heads.HeadHost` is the host: it writes the
pane's state into the page's (`sync`) and does what its buttons ask
(`act`)."""
import uitree as ui
import uitree_app

s = ui.state(
    kind=ui.enum("title", "tabs", "short", "code", init="title"),
    form=ui.enum("named", "words", "icon", init="named"), icon="", title="", status="",
    tabs=ui.model(key="k", k="", label=""), tab=ui.row_of("tabs"),
    shorts=ui.model(key="k", k="", label="", icon="", cur=False),
    tools=ui.model(key="k", k="", icon="", label="", on=False),
    folded=ui.model(key="k", k="", icon="", label=""), folds=False,
    game=False, paused=False, playing=False,
    files=ui.model(key="k", k=""), file=ui.row_of("files"), finding=False,
    code_rows=ui.model(key="k", k="", icon="", label=""),
    sound=False, sounding=False, speed="", looping=False, sounds_menu=False, adds=False,
    pop=ui.enum("none", "more", "code", init="none"),
    cell=32, pad=2, lead=20, below=0, more_w=160, code_w=200,
)


def sync(vals):
    """The host's values where they moved: the header's kind, its words,
    its tabs and tools, the Game's, the Code pane's and the Sound pane's
    own, and the measures (`HeadHost._vals`)."""
    (kind, form, icon, title, status, tabs, tab, shorts, tools, folded, game, files, file, find,
     sound, new_sound, measures) = vals
    s.kind, s.form, s.icon, s.title, s.status = kind, form, icon, title, status
    s.tabs = [dict(k=str(i), label=t) for i, t in enumerate(tabs)]
    if s.tab != tab:
        s.tab = tab
    s.shorts = [dict(k=k, label=label, icon=ic, cur=cur) for k, label, ic, cur in shorts]
    s.tools = [dict(k=op, icon=ic, label=label, on=on) for ic, label, op, on in tools]
    s.folded = [dict(k=op, icon=ic, label=label) for ic, label, op in folded]
    s.folds = bool(folded)
    s.game, s.paused, s.playing = game
    s.files = [dict(k=f) for f in files]
    if s.file != file:
        s.file = file
    s.finding = find
    s.sound, s.sounding, s.speed, s.looping, s.sounds_menu = sound
    s.adds = new_sound
    s.cell, s.pad, s.lead, s.below, s.more_w, s.code_w, code_rows = measures
    s.code_rows = [dict(k=op, icon=ic, label=label) for ic, label, op in code_rows]


def open_pop(which):
    """The host's menu to open: "more" or "code"."""
    s.pop = which


def _act(verb, *args):
    uitree_app.env().act(verb, *args)


def close_pop():
    s.pop = "none"
    _act("closed")


def _more():
    s.pop = "more"
    _act("opened")


def _code_more():
    s.pop = "code"
    _act("opened")


def _fold(row):
    close_pop()
    _act("tool", row.k)


def _code_row(row):
    close_pop()
    _act("code", row.k)


def home():
    """The keys arrive at the header's first stop."""


ui.hook("home", home)
ui.hook("sync", sync, takes="arg")
ui.hook("open_pop", open_pop, takes="arg")
ui.hook("chose_tab", lambda: _act("tab", int(s.tab)))
ui.hook("chose_file", lambda: _act("file", s.file))
ui.action("grow", "Grow", lambda: _act("grow"))
ui.action("more", "More", _more)
ui.action("close_pop", "Close", close_pop)
ui.action("fold", "Use", _fold, takes="row")
ui.action("tool", "Use", lambda row: _act("tool", row.k), takes="row")
ui.action("short", "Show", lambda row: _act("tab", int(row.k)), takes="row")
ui.action("short_on", "Shown", lambda row: _act("tab", int(row.k)), takes="row")
ui.action("pause", "Pause", lambda: _act("pause"), when="playing", off="grey")
ui.action("find", "Find", lambda: _act("code", "find"))
ui.action("goto", "Go to definition", lambda: _act("code", "goto"))
ui.action("code_more", "More", _code_more)
ui.action("code_row", "Use", _code_row, takes="row")
ui.action("new_sound", "New sound", lambda: _act("new_sound"))
ui.action("sounds", "Sounds", lambda: _act("sound", "menu"))
ui.action("rename", "Rename", lambda: _act("sound", "rename"))
ui.action("loop", "Loop", lambda: _act("sound", "loop"))
ui.action("slower", "Slower", lambda: _act("sound", "slower"))
ui.action("faster", "Faster", lambda: _act("sound", "faster"))
ui.action("play", "Play", lambda: _act("sound", "play"))


def _nothing(cv, x, y, w, h):
    pass


def head_page():
    with ui.page(""):
        with ui.row("head", pad="{pad}", gap=0, grow=True):
            ui.canvas("lead", _nothing, w="{lead}", shown="kind=title")
            ui.label("{title}", icon="{icon}", size="text", shown="kind=title && form=named")
            ui.label("{title}", size="text", shown="kind=title && form=words")
            ui.label("", icon="{icon}", size="text", shown="kind=title && form=icon")
            ui.label("{status}", tone="dim", shown="kind=title")
            ui.tabs("tab", text="{.label}", on="chose_tab", shown="kind=tabs")
            with ui.rows("shorts", dir="row", shown="kind=short"):
                ui.button("short_on", label="{.label}", icon="{.icon}", kind="bar", marked=".cur",
                          shown=".cur")
                ui.button("short", icon="{.icon}", kind="bar", alone=True, w="{cell}", shown="!.cur")
            ui.label("", shown="kind=short")
            ui.tabs("file", text="{.k}", on="chose_file", shown="kind=code")
            ui.button("sounds", icon="down", kind="bar", alone=True, w="{cell}", shown="sound && sounds_menu")
            ui.button("rename", icon="pencil", kind="bar", alone=True, w="{cell}", shown="sound")
            ui.button("loop", icon="rotate", kind="bar", alone=True, w="{cell}", marked="looping", shown="sound")
            ui.button("slower", icon="back", kind="bar", alone=True, w="{cell}", shown="sound")
            ui.label("{speed}", size="text", shown="sound")
            ui.button("faster", icon="forward", kind="bar", alone=True, w="{cell}", shown="sound")
            ui.button("play", icon="run", kind="bar", alone=True, w="{cell}", marked="sounding", shown="sound")
            ui.button("new_sound", icon="new", kind="bar", alone=True, w="{cell}", shown="adds")
            with ui.rows("tools", dir="row"):
                ui.button("tool", label="{.label}", icon="{.icon}", kind="bar", alone=True, w="{cell}",
                          marked=".on")
            ui.button("find", icon="search", kind="bar", alone=True, w="{cell}", marked="finding",
                      shown="kind=code")
            ui.button("goto", icon="arrow_right", kind="bar", alone=True, w="{cell}", shown="kind=code")
            ui.button("code_more", icon="more", kind="bar", alone=True, w="{cell}", marked="pop=code",
                      shown="kind=code")
            ui.button("pause", icon="sleep", kind="bar", alone=True, w="{cell}", marked="paused", shown="game")
            ui.button("more", icon="more", kind="bar", alone=True, w="{cell}", marked="pop=more", shown="folds")
            ui.button("grow", icon="maximize", kind="bar", alone=True, w="{cell}")
        ui.canvas("below", _nothing, h="{below}")
        with ui.popover("more_pop", anchor="more", w="{more_w}", close="close_pop", shown="pop=more"):
            with ui.rows("folded"):
                ui.link("fold", label="{.label}", icon="{.icon}")
        with ui.popover("code_pop", anchor="code_more", w="{code_w}", close="close_pop", shown="pop=code"):
            with ui.rows("code_rows"):
                ui.link("code_row", label="{.label}", icon="{.icon}")
