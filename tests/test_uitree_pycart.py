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


def _cart(root, title, main, ext=("moybyte.uitree",)):
    d = os.path.join(root, title.replace(" ", "_").lower() + ".moy")
    os.makedirs(d)
    with open(os.path.join(d, "main.py"), "w") as f:
        f.write(main)
    with open(os.path.join(d, "manifest.json"), "w") as f:
        json.dump({"format": "moy-1", "title": title, "runtime": "python", "main": "main.py",
                   "extensions": list(ext), "moybyte": {"type": "app", "permissions": []}}, f)


def _run(tmp_path, title, main, ext=("moybyte.uitree",)):
    from runtime import app_perms, host_app
    from ws_helpers import open_cart, quiesce
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, title, main, ext)
    ws = host_app.build_workstation(carts, **parity.SIZES["320"])
    drv = host_app.ConsoleDriver(ws)
    cart = next(c for c in ws.carts.all if c["title"] == title)
    ws.consent.record(app_perms.app_id(cart), [])
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
