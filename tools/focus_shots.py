#!/usr/bin/env python3
# Map (grep -n a name to jump there):
#   sheet               the state sheet: one surface a UI tree page
#   _sheet_setup        a sheet frame's setup (SURFACES lists each page's frames)
#   _cc                 the control center opened (SHELL lists the shell's screens)
#   checks              the legibility checks on the declared marks
#   shoot               one run's renders
#   sheets              the contact sheets
#   findings            the README's numbered crops (FINDINGS)
#   main                the command
"""The focus and selection audit (docs/media/focus_2026-11/README.md): every
surface that wears a focus or a selected mark, in every state, in every
theme-mode the shell holds, drawn by the real toolkit on the goldens'
workstation (`tests/test_shell_goldens.py`, through `tools/look_shots.py`'s
`render`), written as PNGs.

usage: .venv/bin/python tools/focus_shots.py OUT [FILTER ...] [--work DIR]
                                             [--runs today|proposal|findings|checks]

Two kinds of render:

- the STATE SHEET: a UI tree app showing one surface a page (a group
  card, a plain list, a table, a menu, buttons, a dialog, tabs and
  segments, cards and bar buttons, fields), drawn once per state -- the
  focus elsewhere, a stop focused, a selected stop focused, a press held,
  the same under touch --
  on the T-Deck (320x240) and in a window on the desk (1024x600);
- the SHELL: the real screens (Settings, the home and its bar, the system
  menu, the control center, Files, Calc, the desk's PROJECTS window, the
  delete's question), each with a stop focused.

A run draws the checkout it runs in, under its name: the README's `today`
is dev before the marks landed (02bc69e20), `proposal` the declared marks
as the toolkit draws them. `checks` prints the legibility checks on the
checkout's declared marks, as the README's table states them; the loader
holds L1-L4 (moy_theme_marks) and tests/test_focus_marks.py the rendered
sheets. Each run writes OUT/RUN/
surface_SURFACE_{tdeck,desk,shell}.png (one surface across the
theme-modes) and theme_THEME-MODE_{tdeck,shell}.png (one theme-mode's
surfaces), every cell captioned with its theme-mode, surface and state;
`findings` crops FINDINGS' panels from both runs' --work into
OUT/findings/. The single frames and whole renders stay in --work (a
temporary directory by default).
"""

import argparse
import fnmatch
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import look_shots as L  # noqa: E402  -- the review kit's renderer
sys.path.insert(0, ROOT)
import runtime  # noqa: E402,F401  -- the runtime's modules by their bare names (uitree)
import uitree as ui  # noqa: E402  -- the sheet's pages

MODES = L.KIT_MODES

# --------------------------------------------------------------------------
# the state sheet
# --------------------------------------------------------------------------

FILES = ("Beach trip", "Road trip mix", "Birthday song", "Dragon theme", "Sleepy time")
ROWS = (("Beach trip", "3 KB"), ("Road trip mix", "12 KB"), ("Birthday song", "2 KB"),
        ("Dragon theme", "4 KB"))

s = ui.state(on=True, live=False, toggle=True, level=3,
             files=ui.model(key="k", k="", name=""), pick=ui.row_of("files"),
             table=ui.model(key="k", k="", name="", size=""), trow=ui.row_of("table"),
             tab=ui.enum("games", "make", "art", init="make"), mode=ui.enum("day", "night", init="day"),
             cells=ui.model(key="k", k="", label="", icon="", locked=False, on=False),
             field="", named="Star Catcher", bad="http", up=True,
             choices=ui.model(key="k", k="", label="", value=""), chosen=ui.row_of("choices"),
             cell=ui.row_of("cells"))
ui.labels("tabs", {"games": "Games", "make": "Make", "art": "Art"})
ui.labels("modes", {"day": "Day", "night": "Night"})


def _nothing():
    pass


def _row(row):
    pass


def _opened():
    s.files = [dict(k="f%d" % i, name=n) for i, n in enumerate(FILES)]
    s.pick = "f1"
    s.table = [dict(k="t%d" % i, name=n, size=z) for i, (n, z) in enumerate(ROWS)]
    s.trow = "t1"
    s.choices = [dict(k="rest", label="Rest", value="Home"), dict(k="selected", label="Selected", value="Night")]
    s.chosen = "selected"
    s.cell = "selected"
    s.cells = [dict(k="rest", label="Rest", icon="play", locked=False, on=False),
               dict(k="selected", label="Selected", icon="paint", locked=False, on=True),
               dict(k="locked", label="Locked", icon="calc", locked=True, on=False)]


def _focus(key):
    ui.focus(key)


ui.hook("opened", _opened)
ui.hook("focus", _focus, takes="arg")
for _name, _label in (("other", "Other"),
                      ("normal", "Normal"), ("primary", "Primary"), ("danger", "Danger"),
                      ("tonal", "Tonal"), ("toggle_on", "Toggle on"), ("wide", "Wide button"),
                      ("resume", "Resume"), ("restart", "Restart"), ("settings", "Settings"),
                      ("delete_cart", "Delete cart"), ("cancel", "Cancel"), ("delete", "Delete"),
                      ("undo", "Undo"), ("pen", "Pen")):
    ui.action(_name, _label, _nothing)
ui.action("disabled", "Disabled", _nothing, when="live", off="grey")
ui.action("redo", "Redo", _nothing, when="live", off="grey")
ui.action("open", "Open", _row, takes="row")
ui.action("choose", "Choose", _row, takes="row")


def _other():
    ui.button("other")


def group_page():
    with ui.page(""):
        with ui.group("Group card"):
            with ui.rows("choices", current="chosen"):
                ui.link("choose", label="{.label}", value="{.value}")
            ui.link("disabled", "Off")
            ui.toggle("Toggle", "toggle")
            ui.slider("Slider", "level", 0, 7, look="steps")
        _other()


def list_page():
    with ui.page(""):
        with ui.rows("files", current="pick"):
            ui.link("open", label="{.name}")
        _other()


def table_page():
    with ui.page(""):
        with ui.table("table", cols=["Name", "Size"], cur="trow"):
            ui.col("{.name}")
            ui.col("{.size}")
        _other()


def menu_page():
    with ui.page(""):
        with ui.menu(""):
            ui.item("resume", icon="play")
            ui.item("restart", icon="undo")
            ui.item("settings", icon="gear")
            ui.item("delete_cart", icon="trash", mkind="danger")


def buttons_page():
    with ui.page(""):
        with ui.group("Buttons"):
            ui.button("normal")
            ui.button("primary", kind="primary")
            ui.button("disabled")
            ui.button("tonal", kind="tonal")
            ui.button("toggle_on", marked="on")
            ui.button("wide")
            ui.button("danger", kind="danger")
        _other()


def dialog_page():
    with ui.page(""):
        ui.label("The page under the dialog")
        with ui.dialog("Delete Star Catcher?", ["cancel", "delete"], kind="danger", shown="up"):
            ui.label("This can't be undone.", wrap="word")


def tabs_page():
    with ui.page(""):
        ui.tabs("tab", labels="tabs")
        with ui.group("Segments"):
            ui.seg("Mode", "mode", labels="modes")
        _other()


def cells_page():
    with ui.page(""):
        with ui.cards("cells", w=56, h=40, current="cell"):
            ui.card("open", label="{.label}")
        with ui.row("tools", gap=4):
            ui.button("undo", kind="bar", icon="undo", alone=True)
            ui.button("pen", kind="bar", icon="pencil", alone=True, marked="on")
            ui.button("redo", kind="bar", icon="redo", alone=True)
        _other()


def fields_page():
    with ui.page(""):
        with ui.group("Fields"):
            ui.field("Name", "field", 16, hint="Your name")
            ui.field("Title", "named", 16)
            ui.field("Address", "bad", 32)
        _other()


PAGES = {"group": group_page, "list": list_page, "table": table_page, "menu": menu_page,
         "buttons": buttons_page, "dialog": dialog_page, "tabs": tabs_page,
         "cells": cells_page, "fields": fields_page}


def sheet(ws, page):
    """The sheet app showing `page`, registered and opened as the console
    registers a system app: a UI tree App whose engine draws through its
    AppHost, whose context answers its stops' boxes (`api_box`)."""
    import uitree_app
    from runtime.ui_draw import AppHost
    cls = uitree_app.app_layer("focus_sheet", "Focus", PAGES[page])
    ctx = ws.app_context(cls.id, cls.NEEDS)
    ctx.ui = AppHost(cls.id, ctx.surface)
    ws._app_hosts[cls.id] = ctx.ui
    app = cls(ctx)
    ws.spine.register_app(app)
    app.open()
    return app


def box_of(app, stop):
    """Stop `stop`'s box on the app's canvas, else None."""
    from runtime import ui_draw
    return ui_draw._C.api_box(app.page_host().ctx, stop)


# where the desk's sheet window stands, in glass pixels
DESK_WIN = (112, 52, 560, 270)


# surface -> [(state, focus stop or None, press stop, input)]
# A state's name says what the frame shows; an item's label says its own.
SURFACES = {
    "group": [("rest", "other", None, None), ("focus-rest", "rest/choose", None, None),
              ("focus-selected", "selected/choose", None, None),
              ("focus-toggle", "toggle", None, None),
              ("focus-slider", "level", None, None),
              ("pressed", None, "rest/choose", "touch"),
              ("touch-focus", "rest/choose", None, "touch")],
    "list": [("rest", "other", None, None), ("focus-selected", "f1/open", None, None),
             ("focus-rest", "f2/open", None, None),
             ("touch-focus", "f2/open", None, "touch")],
    "table": [("rest", "other", None, None), ("focus-selected", "table", None, None)],
    "menu": [("focus-first", "Resume", None, None),
             ("focus-danger", "Delete cart", None, None),
             ("touch", "Resume", None, "touch")],
    "buttons": [("rest", "other", None, None), ("focus-normal", "normal", None, None),
                ("focus-primary", "primary", None, None),
                ("focus-danger", "danger", None, None),
                ("focus-toggle-on", "toggle_on", None, None),
                ("focus-wide", "wide", None, None),
                ("pressed", None, "normal", "touch")],
    "dialog": [("focus-cancel", "Cancel", None, None),
               ("focus-verb", "Delete", None, None)],
    "tabs": [("rest", "other", None, None), ("focus-tabs", "tab", None, None),
             ("focus-seg", "mode", None, None)],
    "cells": [("rest", "other", None, None), ("focus-rest", "rest/open", None, None),
              ("focus-selected", "selected/open", None, None),
              ("focus-tool", "undo", None, None),
              ("focus-tool-selected", "pen", None, None)],
    "fields": [("rest", "other", None, None), ("focus-empty", "field", None, None),
               ("focus-filled", "named", None, None),
               ("focus-error", "bad", None, None)],
}

SHEET_CONFIGS = (("tdeck", L.HANDHELD), ("desk", L.DESK))


def _sheet_setup(page, focus, press, apps=None):
    """A sheet frame's setup: the page open, `focus` focused (the app's
    own ui.focus) and `press` held under a touch; `apps` (a list) gets
    (the workstation, the sheet app)."""
    def setup(g, ws):
        app = sheet(ws, page)
        if apps is not None:
            apps.append((ws, app))
        ws.wm.goto(app.id)
        L._settle(g, ws, 2)
        if app.id in getattr(ws.wm, "windows", {}):
            L._place(ws, app.id, *DESK_WIN)
            L._settle(g, ws, 2)
        if focus is not None:
            app.engine.run_action(app.engine.actions["focus"], (focus,), "host")
            ws.mark_dirty()
            L._settle(g, ws, 2)
        if press is not None:
            from runtime import host_app
            box = box_of(app, press)
            win = getattr(ws.wm, "windows", {}).get(app.id)
            ox, oy = win.content_rect()[:2] if win is not None else (0, 0)
            host_app.ConsoleDriver(ws).touch(ox + box[0] + box[2] // 2, oy + box[1] + box[3] // 2)
            L._settle(g, ws, 3)
    return setup


# --------------------------------------------------------------------------
# the real shell's screens
# --------------------------------------------------------------------------

def _open(app_id, then=None):
    def setup(g, ws):
        ws.spine.open_app(ws.app(app_id))
        L._settle(g, ws, 2)
        if then is not None:
            then(g, ws)
    return setup


def _cc(focus=None):
    """The handheld's control center, opened from the bar's cluster, `focus`
    its stop focused (None: where it opens)."""
    def setup(g, ws):
        L._home(g, ws)
        L._settle(g, ws, 2)
        ws._golden_popover = True
        ws.widget_tap("battery")
        L._settle(g, ws, 2)
        if focus is not None:
            ws.sysmenu.comp.host.focus(focus)
    return setup


def _bar_focus(name):
    """The home with the bar's stop `name` focused (the cluster, a tab)."""
    def setup(g, ws):
        L._home(g, ws)
        L._settle(g, ws, 2)
        items = ws.bar_layer.focus_items("home")
        names = [i[2] for i in items]
        k = names.index(name) if name in names else 0
        ws.bar_layer.focus_enter("home", k=k)
    return setup


def _desk_power(g, ws):
    ws.home.open_desk()
    L._settle(g, ws, 2)
    ws._golden_popover = True
    ws.widget_tap("battery")


# surface -> [(state, config, setup)]
SHELL = {
    "group": [("settings-volume", L.HANDHELD, L._settings_at("volume")),
              ("settings-toggle", L.HANDHELD, L._settings_at("steady")),
              ("desk-appearance-seg", L.DESK, L._desk_appearance_at("Mode"))],
    "control-center": [("open", L.HANDHELD, _cc()),
                       ("focus-brightness", L.HANDHELD, _cc("Brightness")),
                       ("focus-wifi", L.HANDHELD, _cc("Wi-Fi"))],
    "list": [("files", L.HANDHELD, _open("files")),
             ("desk-files-calc", L.DESK, L._desk)],
    "menu": [("sysmenu", L.HANDHELD, L._sysmenu_home),
             ("pause", L.HANDHELD, L._pause),
             ("desk-sysmenu", L.DESK, L._sysmenu_desk),
             ("desk-power", L.DESK, _desk_power)],
    "dialog": [("delete", L.HANDHELD, L._delete_asks(L._make_own)),
               ("desk-delete", L.DESK, L._delete_asks(L._projects_own(), True))],
    "bar": [("focus-cluster", L.HANDHELD, _bar_focus("cluster")),
            ("focus-menu-button", L.HANDHELD, _bar_focus("menu"))],
    "cells": [("home-tiles", L.HANDHELD, L._home),
              ("calc", L.HANDHELD, _open("calc", L._key_calc)),
              ("desk-projects", L.DESK, L._projects())],
    "fields": [("settings-name", L.HANDHELD, L._settings_at("name"))],
}


# --------------------------------------------------------------------------
# rendering, cropping, the sheets
# --------------------------------------------------------------------------

def _ground(img, box):
    """The commonest colour in `box` of `img`: the page's ground."""
    crop = img.crop(box)
    return max(crop.getcolors(1 << 20), key=lambda c: c[0])[1]


def _bbox(imgs, box, pad):
    """The union of what differs from the ground in `box` over `imgs`."""
    from PIL import ImageChops, Image
    x0, y0, x1, y1 = box
    out = None
    for im in imgs:
        crop = im.crop(box)
        g = Image.new("RGB", crop.size, _ground(im, box))
        bb = ImageChops.difference(crop, g).convert("L").point(lambda v: 255 if v > 6 else 0) \
            .getbbox()
        if bb is None:
            continue
        out = bb if out is None else (min(out[0], bb[0]), min(out[1], bb[1]),
                                      max(out[2], bb[2]), max(out[3], bb[3]))
    if out is None:
        return box
    return (max(x0, x0 + out[0] - pad), max(y0, y0 + out[1] - pad),
            min(x1, x0 + out[2] + pad), min(y1, y0 + out[3] + pad))


def _content(ws_size, config):
    w, h = ws_size
    if config == L.HANDHELD:
        return (0, 22, w, h - 24)
    x, y, ww, hh = DESK_WIN
    return (x - 8, y - 8, x + ww + 8, y + hh + 8)


# every render whole, in glass pixels (the findings crop from these)
FULL = {}

# The findings (README): id, title, panels (run, (theme-mode, config tag,
# surface, state), crop in glass pixels or None, scale).
_TMS = ["%s-%s" % m for m in MODES]
_CARD = (0, 32, 320, 162)
_CC = (80, 22, 320, 150)


def _across(run, tag, surface, state, crop, scale, tms=None):
    return [(run, (tm, tag, surface, state), crop, scale) for tm in (tms or _TMS)]


FINDINGS = [
    ("01_focus-is-a-fill-in-two-themes",
     "1. One focused row, three marks: Moy draws a bar, Blocks and Contrast fill the row",
     _across("today", "tdeck", "group", "focus-rest", _CARD, 2)),
    ("02_focus-and-selection-swap-meaning",
     "2. A fill means SELECTED in Moy and FOCUSED in Blocks/Contrast; a table row, "
     "focused and selected",
     _across("today", "tdeck", "list", "focus-rest", (0, 40, 320, 140), 2)),
    ("03_selected-group-row-draws-nothing",
     "3. A group row given `current` draws no mark in any theme ('Selected' == 'Rest')",
     _across("today", "tdeck", "group", "rest", _CARD, 2,
             ["moy-dark", "blocks-light", "contrast-dark"])
     + _across("proposal", "tdeck", "group", "rest", _CARD, 2,
               ["moy-dark", "blocks-light", "contrast-dark"])),
    ("04_rules-vanish-beside-the-bar",
     "4. The rules above and below a focused row vanish (the old plate's leftover); "
     "the bar sits on the card's frame",
     [("today", ("moy-dark", "shell-tdeck", "control-center", "focus-brightness"), _CC, 3),
      ("proposal", ("moy-dark", "shell-tdeck", "control-center", "focus-brightness"), _CC, 3),
      ("today", ("moy-light", "tdeck", "group", "focus-selected"), (0, 52, 170, 112), 4),
      ("proposal", ("moy-light", "tdeck", "group", "focus-selected"), (0, 52, 170, 112), 4)]),
    ("05_control-center-flush-top",
     "5. The control center's card sits flush on the panel's top, with an empty foot",
     [("today", ("moy-dark", "shell-tdeck", "control-center", "open"), _CC, 2),
      ("proposal", ("moy-dark", "shell-tdeck", "control-center", "open"), _CC, 2),
      ("today", ("moy-light", "shell-tdeck", "control-center", "open"), _CC, 2),
      ("proposal", ("moy-light", "shell-tdeck", "control-center", "open"), _CC, 2)]),
    ("06_the-shape-decides-the-mark",
     "6. The mark follows the box's shape, not the part: a focused tab strip wears a row's "
     "bar (Moy) or a filled strip",
     _across("today", "tdeck", "tabs", "focus-tabs", (0, 22, 320, 70), 2)),
    ("07_focus-hides-the-part",
     "7. A focus that fills hides what the part is: the danger verb loses its red, a "
     "selected tool its mark",
     _across("today", "tdeck", "dialog", "focus-verb", (0, 70, 320, 180), 2,
             ["moy-dark", "blocks-light", "contrast-dark", "contrast-light"])),
    ("08_a-field-wears-two-marks",
     "8. A focused field wears two marks: the row's bar and an accent box",
     [("today", ("moy-dark", "tdeck", "fields", "focus-filled"), (0, 42, 320, 120), 3),
      ("proposal", ("moy-dark", "tdeck", "fields", "focus-filled"), (0, 42, 320, 120), 3)]),
    ("09_pressed-looks-like-primary-or-focus",
     "9. Pressed fills a button with the accent: it reads as Primary (Moy, Blocks) or as "
     "focus (Contrast)",
     _across("today", "tdeck", "buttons", "pressed", (0, 22, 320, 80), 2,
             ["moy-dark", "blocks-light", "contrast-dark"])),
    ("10_cards-lift-in-moy-ring-elsewhere",
     "10. A focused card lifts in Moy and rings in Blocks and Contrast; every other cell "
     "rings in Moy",
     _across("today", "tdeck", "cells", "focus-rest", (0, 22, 320, 130), 2,
             ["moy-dark", "blocks-light", "contrast-dark"])),
    ("11_the-proposal-in-every-theme",
     "11. The proposal's rows, each theme's declared marks: focus on 'Rest' (left), "
     "focus on the selected row (right); rules kept",
     [p for tm in _TMS for p in _across("proposal", "tdeck", "group", "focus-rest", _CARD, 2,
                                         [tm])
      + _across("proposal", "tdeck", "group", "focus-selected", _CARD, 2, [tm])], 2),
    ("12_the-proposal-on-cells",
     "12. The proposal on cells: the ring outside, the part's own fill and ink kept; a "
     "tab strip rings its current tab",
     _across("proposal", "tdeck", "dialog", "focus-verb", (0, 70, 320, 180), 2,
             ["moy-dark", "blocks-light", "contrast-dark", "contrast-light"])
     + _across("proposal", "tdeck", "tabs", "focus-tabs", (0, 22, 320, 70), 2,
               ["moy-light", "blocks-light", "contrast-dark", "contrast-light"]), 2),
    ("13_control-center-in-every-theme",
     "13. The control center on the T-Deck, proposed: the card inset on all four sides, "
     "the rules kept beside the focused row",
     _across("proposal", "shell-tdeck", "control-center", "focus-brightness", _CC, 2)),
    ("14_danger-keeps-its-ink",
     "14. A focused danger row keeps its red: where a fill focus would hide it (Contrast "
     "Night), the focus is an inset line",
     _across("proposal", "tdeck", "menu", "focus-danger", (0, 20, 200, 80), 3,
             ["moy-dark", "blocks-light", "contrast-dark", "contrast-light"]), 2),
    ("15_list-and-table-selection",
     "15. A list's selection stays where it was chosen (left); a table's follows its "
     "cursor (right)",
     [p for tm in ("moy-dark", "blocks-light", "contrast-light")
      for p in _across("proposal", "tdeck", "list", "focus-rest", (0, 20, 320, 150), 2, [tm])
      + _across("proposal", "tdeck", "table", "focus-down", (0, 20, 320, 150), 2, [tm])], 2),
]


def findings(work, out):
    """Each FINDINGS entry as one captioned image: its panels cropped from
    the whole renders of `work`'s runs, each labelled."""
    from PIL import Image, ImageDraw
    os.makedirs(out, exist_ok=True)
    for fid, title, panels, *cols in FINDINGS:
        cells = []
        for run, key, crop, scale in panels:
            path = os.path.join(work, run, "full", "%s_%s_%s_%s.png" % key)
            if not os.path.exists(path):
                continue
            im = Image.open(path).convert("RGB")
            if crop is not None:
                im = im.crop(crop)
            im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
            cells.append(("%s: %s, %s, %s" % (run.upper(), key[0], key[2], key[3]), im))
        if not cells:
            continue
        f, hf = _font(14), _font(18)
        gap = 12
        cols = cols[0] if cols else min(len(cells), 3 if cells[0][1].width < 700 else 2)
        rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
        W = max(sum(im.width + gap for _c, im in r) for r in rows) + gap
        H = 44 + sum(max(im.height for _c, im in r) + 24 + gap for r in rows)
        sheet = Image.new("RGB", (max(W, 700), H), (236, 236, 236))
        d = ImageDraw.Draw(sheet)
        d.text((gap, 10), title, fill=(0, 0, 0), font=hf)
        y = 44
        for r in rows:
            x = gap
            for cap, im in r:
                d.text((x, y), cap, fill=(0, 0, 0), font=f)
                sheet.paste(im, (x, y + 20))
                x += im.width + gap
            y += max(im.height for _c, im in r) + 24 + gap
        _save(sheet, os.path.join(out, fid + ".png"))


def shoot(out, filters=(), proposal=False, shell=True, sheets=True):
    g = L._goldens()
    frames = {}         # (tm, config tag, surface, state) -> PIL image (cropped)
    FULL.clear()
    for theme, mode in MODES:
        tm = "%s-%s" % (theme, mode)
        if sheets:
            for surface, states in SURFACES.items():
                if filters and not any(fnmatch.fnmatch("%s_%s" % (tm, surface), f)
                                       or f in "%s_%s" % (tm, surface) for f in filters):
                    continue
                for tag, config in SHEET_CONFIGS:
                    got = []
                    for state, focus, press, inputs in states:
                        img, _ok, _r = L.render(g, config, theme, mode,
                                                _sheet_setup(surface, focus, press),
                                                False, inputs)
                        got.append((state, img))
                    box = _content(got[0][1].size, config)
                    if surface != "dialog" and config == L.HANDHELD:
                        box = _bbox([i for _s, i in got], box, 6)
                    for state, img in got:
                        frames[(tm, tag, surface, state)] = img.crop(box)
                        FULL[(tm, tag, surface, state)] = img
        if shell:
            for surface, scenes in SHELL.items():
                for state, config, setup in scenes:
                    key = "%s_%s_%s" % (tm, surface, state)
                    if filters and not any(fnmatch.fnmatch(key, f) or f in key
                                           for f in filters):
                        continue
                    img, _ok, _r = L.render(g, config, theme, mode, setup, False)
                    tag = "tdeck" if config == L.HANDHELD else "desk"
                    frames[(tm, "shell-" + tag, surface, state)] = img
                    FULL[(tm, "shell-" + tag, surface, state)] = img
    _write(out, frames)
    return frames


def _scale(tag):
    return 3 if tag == "tdeck" else 2 if tag == "shell-tdeck" else 1


def _write(out, frames):
    """Each frame as THEME-MODE_[shell-]CONFIG_SURFACE_STATE.png, the T-Deck's
    scaled up nearest."""
    from PIL import Image
    fdir = os.path.join(out, "frames")
    os.makedirs(fdir, exist_ok=True)
    full = os.path.join(out, "full")
    os.makedirs(full, exist_ok=True)
    for (tm, tag, surface, state), img in frames.items():
        s = _scale(tag)
        im = img.resize((img.width * s, img.height * s), Image.NEAREST) if s > 1 else img
        name = "%s_%s_%s_%s.png" % (tm, tag, surface, state)
        im.save(os.path.join(fdir, name))
        FULL[(tm, tag, surface, state)].save(os.path.join(full, name))


def _save(img, path):
    """A sheet as a 256-colour PNG (flat chrome and its type's ramps hold in
    256; the sheets stay reviewable at a quarter of the bytes)."""
    from PIL import Image
    img.convert("RGB").quantize(colors=256, method=Image.Quantize.FASTOCTREE,
                                dither=Image.Dither.NONE).save(path, optimize=True)


def _font(size):
    from PIL import ImageFont
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/TTF/DejaVuSans.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _grid(cells, cols, title, scale, gap=10):
    """A captioned grid: `cells` [(caption, image)], `cols` a row; None
    caption-only cells start a new row with their caption as a heading."""
    from PIL import Image, ImageDraw
    f, hf = _font(13), _font(20)
    rows, row = [], []
    for c in cells:
        if c[1] is None:
            if row:
                rows.append(row)
            rows.append(c[0])
            row = []
            continue
        row.append(c)
        if len(row) == cols:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    ims = [[(cap, im.resize((im.width * scale, im.height * scale), Image.NEAREST))
            for cap, im in r] if not isinstance(r, str) else r for r in rows]
    W = max([sum(i.width + gap for _c, i in r) for r in ims if not isinstance(r, str)] + [600])
    H = 40 + sum(30 if isinstance(r, str) else max(i.height for _c, i in r) + 22 + gap
                 for r in ims)
    sheet = Image.new("RGB", (W + gap, H), (236, 236, 236))
    d = ImageDraw.Draw(sheet)
    d.text((gap, 8), title, fill=(0, 0, 0), font=hf)
    y = 40
    for r in ims:
        if isinstance(r, str):
            d.text((gap, y + 6), r, fill=(30, 30, 160), font=_font(16))
            y += 30
            continue
        x = gap
        for cap, im in r:
            d.text((x, y), cap, fill=(0, 0, 0), font=f)
            sheet.paste(im, (x, y + 18))
            x += im.width + gap
        y += max(i.height for _c, i in r) + 22 + gap
    return sheet


def sheets(out, frames, label):
    """A sheet per theme-mode (its T-Deck state sheet, its shell screens) and
    one per surface across the theme-modes (the T-Deck's and the desk's state
    sheets, the shell's screens)."""
    sdir = out
    os.makedirs(sdir, exist_ok=True)
    tms = ["%s-%s" % m for m in MODES]
    surfaces = list(SURFACES) + [s for s in SHELL if s not in SURFACES]
    for tm in tms:
        for tag, scale in (("tdeck", 2),):
            cells = []
            for surface in SURFACES:
                st = [(s, im) for (t, c, su, s), im in frames.items()
                      if t == tm and c == tag and su == surface]
                if st:
                    cells.append(("%s -- %s" % (surface, tag), None))
                    cells += [("%s %s %s" % (tm, surface, s), im) for s, im in st]
            if cells:
                _save(_grid(cells, 7, "%s: %s, the state sheet on the %s" % (label, tm, tag),
                            scale), os.path.join(sdir, "theme_%s_%s.png" % (tm, tag)))
        cells = []
        for surface in SHELL:
            st = [(s, c, im) for (t, c, su, s), im in frames.items()
                  if t == tm and c.startswith("shell") and su == surface]
            if st:
                cells.append(("%s -- the shell" % surface, None))
                cells += [("%s %s %s" % (tm, surface, s), im) for s, c, im in st]
        if cells:
            _save(_grid(cells, 4, "%s: %s, the shell's screens (1x)" % (label, tm), 1),
                  os.path.join(sdir, "theme_%s_shell.png" % tm))
    for surface in surfaces:
        for tag, scale in (("tdeck", 2), ("desk", 2), ("shell", 1)):
            cells = []
            for tm in tms:
                st = [(s, im) for (t, c, su, s), im in frames.items()
                      if t == tm and su == surface and (c == tag or (tag == "shell"
                                                                     and c.startswith("shell")))]
                if st:
                    cells.append((tm, None))
                    cells += [("%s %s %s" % (tm, surface, s), im) for s, im in st]
            if cells:
                _save(_grid(cells, 7 if tag != "shell" else 4,
                            "%s: %s on the %s, every theme-mode" % (label, surface, tag), scale),
                      os.path.join(sdir, "surface_%s_%s.png" % (surface, tag)))


# --------------------------------------------------------------------------
# the legibility checks on the declarations, as the README tabulates them
# --------------------------------------------------------------------------

def _rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _lum(c):
    v = [x / 255 for x in c]
    v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]


def _cr(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _deep(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = _deep(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _declared(theme, mode):
    """(colours, marks): a seed's role colours and its `marks`, its mode's
    over its own."""
    with open(os.path.join(ROOT, "native", "moy_ui", "themes", theme + ".json")) as f:
        d = json.load(f)
    look = d.get("look", {})
    look = _deep(look, look.get(mode, {}))
    cols = dict(d["colors"][mode])
    # the roles a seed leaves to the derivation: value is the accent; the
    # danger ink is the look's menu or button danger ink, else the palette's red
    cols.setdefault("value", cols["accent"])
    cols.setdefault("danger", look.get("danger_ink")
                    or look.get("buttons", {}).get("danger", {}).get("ink") or "#ff004d")
    return cols, look.get("marks", {})


def _ink_over(c):
    return max((_cr(c, k), k) for k in ((0, 0, 0), (255, 255, 255)))[1]


def checks():
    """The L-checks (README, "The legibility checks") on each theme-mode's
    declared marks, as a markdown table: each cell the ratio and its verdict."""
    head = ("theme-mode", "L1 row focus on card / page", "L1 ink on a focus fill",
            "L1 cell ring on panel", "L3 selected against rest", "L4 the both cue",
            "L5 danger ink on focus")
    rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for theme, mode in MODES:
        cols, marks = _declared(theme, mode)
        if not marks:
            continue

        def col(v, under=None):
            if v is None:
                return _ink_over(under) if under is not None else _rgb(cols["accent"])
            return _rgb(v if v.startswith("#") else cols[v])
        card, panel = _rgb(cols["surface"]), _rgb(cols["panel"])
        rf, ro = marks["row"]["focus"], marks["row"].get("on", {})
        rb = marks["row"].get("both")
        cf = marks["cell"]["focus"]
        cells = []

        def verdict(r, need):
            return "%.2f %s" % (r, "pass" if r >= need else "FAIL")

        def keyed(mark, c, ground):
            key = mark.get("key")
            r = _cr(c, ground)
            if r < 3 and key:
                kc = col(key[1])
                return "%s (keyline %s)" % ("%.2f" % r, verdict(min(_cr(kc, ground), _cr(kc, c)),
                                                                    3))
            return verdict(r, 3)
        fc = col(rf.get("c"))
        cells.append(" / ".join(keyed(rf, fc, g) for g in (card, panel)))
        cells.append(verdict(_cr(_ink_over(fc), fc), 4.5) if rf["mark"] == "fill" else "-")
        cells.append(keyed(cf, col(cf.get("c")), panel))
        oc = col(ro.get("c", "value"))
        if ro.get("mark") == "tint":
            oc = _mix(card, oc, ro.get("alpha", 1))
        cells.append(verdict(_cr(oc, card), 1.3))
        if rf["mark"] == "fill":
            bc = col(rb.get("c"), fc) if rb else oc
            cells.append(verdict(_cr(bc, fc), 3))
        else:
            under = oc if ro.get("mark") in ("fill", "tint") else card
            bc = col(rb.get("c"), under) if rb else fc
            cells.append(verdict(_cr(bc, under), 3))
        cells.append(verdict(_cr(_rgb(cols["danger"]), fc), 4.5) if rf["mark"] == "fill"
                     else verdict(_cr(_rgb(cols["danger"]), card), 4.5))
        rows.append("| %s-%s | " % (theme, mode) + " | ".join(cells) + " |")
    return "\n".join(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out")
    ap.add_argument("filters", nargs="*")
    ap.add_argument("--work", help="where the frames and whole renders go (default: a "
                    "temporary directory)")
    ap.add_argument("--runs", default="today")
    a = ap.parse_args(argv)
    work = a.work or tempfile.mkdtemp(prefix="focus_shots_")
    runs = a.runs.split(",")
    for run in ("today", "proposal"):
        if run in runs:
            frames = shoot(os.path.join(work, run), a.filters, run == "proposal")
            os.makedirs(os.path.join(a.out, run), exist_ok=True)
            sheets(os.path.join(a.out, run), frames, run.upper())
    if "checks" in runs:
        print(checks())
    if "findings" in runs:
        findings(work, os.path.join(a.out, "findings"))
    print("frames and whole renders in", work)
    return 0


if __name__ == "__main__":
    sys.exit(main())
