"""A Python app cart on the UI tree API (runtime/run/player_tree.py): a cart
that declares the extension `moybyte.uitree` gets `uitree` as its `ui`, and
its pages run on the console's engine in the run's app host. The pixels and
the trace are held to the Lua half's by tests/test_uitree_conformance.py
(the counter's Python cart); this file holds the seam: what a cart without
the declarations meets, the host's back into its pages, and a cart without
the extension keeping the toolkit."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]

import uitree_lua_parity as parity  # noqa: E402

PAGES = '''s = ui.state(n=0)
ui.app("Two Pages", icon="calc")


def more():
    ui.push(second)


ui.action("more", "More", more)


def build():
    with ui.page("First"):
        ui.link("more")


def second():
    with ui.page("Second"):
        ui.label("the second page")
'''


NOTE = """s = ui.state(note=ui.doc("", "markdown"), said="")
ui.app("Tree Note", icon="notes")
ed = [None]


def opened():
    files.save_text("probe", "- [ ] milk\\nsee [[other]]\\n")
    ed[0] = open_editor("probe")
    s.note.adopt(ed[0])


def follow():
    s.said = repr(ed[0].follow())


ui.hook("opened", opened)
ui.action("follow", "Open link", follow, keys=("ctrl+o",))


def build():
    with ui.page("Note"):
        ui.text_editor("note", focus=True)
        ui.label("{said}")
"""


def _cart(root, title, main, ext=("moybyte.uitree",), perms=()):
    d = os.path.join(root, title.replace(" ", "_").lower() + ".moy")
    os.makedirs(d)
    with open(os.path.join(d, "main.py"), "w") as f:
        f.write(main)
    with open(os.path.join(d, "manifest.json"), "w") as f:
        json.dump({"format": "moy-1", "title": title, "runtime": "python", "main": "main.py",
                   "extensions": list(ext), "moybyte": {"type": "app", "permissions": list(perms)}}, f)


def _run(tmp_path, title, main, ext=("moybyte.uitree",), perms=()):
    from runtime import app_perms, host_app
    from ws_helpers import open_cart, quiesce
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, title, main, ext, perms)
    ws = host_app.build_workstation(carts, **parity.SIZES["320"])
    drv = host_app.ConsoleDriver(ws)
    cart = next(c for c in ws.carts.all if c["title"] == title)
    ws.consent.record(app_perms.app_id(cart), list(perms))
    open_cart(ws, title)

    def frame():
        quiesce(ws)
        ws.mark_dirty()
        drv.frame(parity.DT)
    for _ in range(3):
        frame()
    return ws, drv, frame


def test_a_cart_with_no_app_declaration_stops_at_the_error_panel(tmp_path):
    ws, _, _ = _run(tmp_path, "No App", 's = ui.state(n=0)\n\n\ndef build():\n    with ui.page("x"):\n'
                    '        ui.label("x")\n')
    err = ws.run.player.cart_error or ""
    assert "D04" in err and "ui.app" in err, err


def test_a_cart_with_no_root_page_stops_at_the_error_panel(tmp_path):
    ws, _, _ = _run(tmp_path, "No Page", 's = ui.state(n=0)\nui.app("No Page", icon="calc")\n')
    err = ws.run.player.cart_error or ""
    assert "P01" in err and "build" in err, err


def test_the_hosts_back_steps_the_carts_pages_then_leaves(tmp_path):
    ws, drv, frame = _run(tmp_path, "Two Pages", PAGES)
    pl = ws.run.player
    assert pl.cart_error is None, pl.cart_error
    eng = pl.tree.engine
    assert eng.has_page() is False
    drv.press("a")              # the focused link: More
    frame()
    frame()
    assert len(eng.pages) == 2
    assert pl.face.has_page() is True
    assert pl.face.back() is True
    frame()
    assert len(eng.pages) == 1 and pl.face.has_page() is False
    assert pl.face.back() is False, "the first page's back is the host's: it leaves the app"


def test_a_cart_without_the_extension_keeps_the_toolkit(tmp_path):
    ws, _, _ = _run(tmp_path, "Old Ui", "def _draw():\n    ui.page('Old')\n    ui.label('hi')\n    ui.end()\n",
                    ext=())
    pl = ws.run.player
    assert pl.cart_error is None, pl.cart_error
    assert pl.tree is None and pl.ns["ui"].__name__.rpartition(".")[2] == "ui"


def test_a_text_editor_that_adopts_an_editor_handle_edits_its_document(tmp_path):
    """`s.note.adopt(ed)`: the text editor types into the handle's buffer,
    its undo is the handle's, a tap places its caret, the run takes typed
    bytes while it holds the keys, and the handle's idle save writes it."""
    from runtime import editor_handle
    ws, drv, frame = _run(tmp_path, "Tree Note", NOTE, perms=("files:documents",))
    pl = ws.run.player
    assert pl.cart_error is None, pl.cart_error
    ed = pl.editors[0]
    assert pl.face.typing() is True
    for ch in b"oat ":
        drv.type_char(ch)
        frame()
    assert ed.text().startswith("oat - [ ] milk"), ed.text()
    assert ed.dirty() and ed.can_undo()
    ed.undo()
    frame()
    assert ed.text().startswith("- [ ] milk"), ed.text()
    # a press on the second line puts the caret there
    eng = pl.tree.engine
    r = eng.views["note"][0]
    lh = eng.views["note"][3]
    drv.touch(r[0] + r[2] // 2, r[1] + lh + lh // 2)
    frame()
    drv.touch_up()
    frame()
    assert ed.caret()[0] == 1, ed.caret()
    assert ed.follow() == ("link", "other")
    ed.ed.row = 0
    assert ed.follow() == ("check", 0) and ed.text().startswith("- [x] milk")
    ed._edit_ms -= editor_handle.AUTOSAVE_MS + 1
    frame()
    assert not ed.dirty(), "the idle save never came"
