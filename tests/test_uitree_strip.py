"""An image carries a compiled page's blob and not the function it was
compiled from (tools/uitree_compile.py's `strip`): the engine loads a blob
for an engine's first page (`uitree_c.CEngine._load`), so a device builds
from its function only a page pushed over another and the pages of a
module that pushes one (`built_on_device`). The host keeps every function:
the blobs are compiled from them.

The guard: the console driven through its surfaces with the blobs loaded,
as a board loads them, and every function an image leaves out raising if
it is called."""

import ast
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uitree_compile as U  # noqa: E402

from ws_helpers import build_ws, build_desktop_ws, device_frames  # noqa: E402
from tools.board_config import runtime_file  # noqa: E402


@pytest.fixture(scope="module")
def compiled():
    if U.UNABLE:
        pytest.skip(U.UNABLE)
    c = U.compile_modules(sorted(U.SYSTEM))
    trees = {}
    for p in sorted((ROOT / "runtime").rglob("*.py")):
        trees[p.stem] = ast.parse(p.read_text(encoding="utf-8"), str(p))
    keep = U.built_on_device(c.pages, trees)
    return c.pages, set(c.pages) - keep


def test_most_compiled_pages_leave_their_function_to_the_host(compiled):
    pages, cut = compiled
    assert len(cut) >= len(pages) - 8, sorted(set(pages) - cut)


def test_strip_stubs_exactly_the_pages_no_device_builds(compiled, tmp_path):
    """A staged copy of the modules, stripped: each page left out is one
    line, and every other function is as the source has it."""
    pages, cut = compiled
    mods = sorted(set(k.rpartition(".")[0] for k in pages))
    trees = {}
    for m in mods:
        src = runtime_file(m + ".py").read_text(encoding="utf-8")
        (tmp_path / (m + ".py")).write_text(src, encoding="utf-8")
        trees[m] = ast.parse(src)
    assert set(U.strip(str(tmp_path), pages, trees)) == cut
    for m in mods:
        got = ast.parse((tmp_path / (m + ".py")).read_text(encoding="utf-8"))
        for f in got.body:
            if isinstance(f, ast.FunctionDef) and "%s.%s" % (m, f.name) in cut:
                assert ast.unparse(f.body[0]) == U.STUB and len(f.body) == 1


_STUB = compile(
    "def stub(*a, **k):\n"
    "    import builtins\n"
    "    builtins._moy_built.append(__name__)\n"
    "    raise RuntimeError('a page an image leaves to the host was built in ' + __name__)\n",
    "<stub>", "exec")


def _as_a_board(monkeypatch, pages, cut):
    """The blobs loaded as an image loads them, and each function an image
    leaves out recording its module and raising when it is called (its code
    swapped, so every reference to it -- an app class's BUILD -- calls the
    stub)."""
    import builtins
    import uitree_aot
    monkeypatch.setattr(uitree_aot, "BLOBS", dict((k, uitree_aot.entry(b, False)) for k, b in pages.items()))
    called = []
    monkeypatch.setattr(builtins, "_moy_built", called, raising=False)
    ns = {}
    exec(_STUB, ns)
    loaded = []
    load = uitree_aot.load

    def counted(eng, x, blob):
        loaded.append(uitree_aot.key(eng.pages[0]))
        return load(eng, x, blob)
    monkeypatch.setattr(uitree_aot, "load", counted)
    for k in cut:
        mod, _, name = k.rpartition(".")
        m = sys.modules.get(mod) or sys.modules["runtime." + mod]
        monkeypatch.setattr(getattr(m, name), "__code__", ns["stub"].__code__)
    return called, loaded


def _tour(ws):
    device_frames(ws, 3)
    for p in ("tz", "log", "permissions", "licences", "achievements", "wifi"):
        ws.open_settings()
        device_frames(ws, 2)
        ws.settings_layer.open_page(p)
        device_frames(ws, 3)
        ws.home.go_home()
    ws.open_tasks()
    device_frames(ws, 3)
    ws.home.go_home()
    for slot in list(ws.app_layers):
        if ws.spine.open_app(slot):
            device_frames(ws, 4)
        ws.home.go_home()
        device_frames(ws, 2)
    ws.open_in_editor()
    for tab in ("cards", "blocks", "code", "paint", "map", "scene", "music"):
        ws.text.set_menu_view(tab)
        device_frames(ws, 3)
    ws.spine.exit()
    device_frames(ws, 3)


@pytest.mark.parametrize("desk", [False, True], ids=["tdeck", "desk"])
def test_no_surface_builds_a_page_an_image_leaves_to_the_host(compiled, monkeypatch, tmp_path, desk):
    pages, cut = compiled
    called, loaded = _as_a_board(monkeypatch, pages, cut)
    ws = build_desktop_ws(tmp_path) if desk else build_ws(tmp_path, sys_size=(320, 240))
    _tour(ws)
    assert not called, called
    assert len(set(loaded) & cut) >= 25, sorted(set(loaded))
