"""The UI re-architecture's clean cut, kept: every shipped surface runs on the
UI tree engine (native/moy_uitree over native/moy_ui), and what the cut took
out stays out.

  * the `legacy` kind -- a surface on the immediate verbs hosted in one node
    of a tree -- is no kind of any front: not the Python API's, not the
    contract's, not the C engine's;
  * the immediate `ui` surface is gone from every tier, and a test here
    fails the day any part of it returns: the os_calls `ui` rows and role,
    the RUN form (face.json's `run` keys and its generated rows), the Python
    toolkit (runtime/toolkit/ui.py and any import of it), the Lua and wasm
    verbs (moycore_ui, moy_ui_wasm), the SDK's ui.h and the toolkit a
    native module links, the WASI and ELF rows a linked toolkit pulled its
    theme and told its answers through, and the `moybyte.ui` extension;
  * the theme's shared-state machinery a linked copy pulled through goes with
    it: no theme write bracket or its generation, no per-file record tables;
  * no tool or board script imports the `ui` module, its code run on a board
    (a bench's snippet) included.
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts)) as f:
        return f.read()


def test_the_legacy_kind_is_no_kind_of_any_front():
    from runtime import uitree, uitree_c
    assert not hasattr(uitree, "legacy") and "legacy" not in uitree.NODE_CALLS
    assert "legacy" not in uitree.SCHEMA
    assert "legacy" not in uitree_c._KINDS
    contract = json.loads(_read("native", "moy_uitree", "contract.json"))
    assert "legacy" not in contract["kinds"]
    for path in (("native", "moy_uitree", "moy_uitree.h"), ("native", "moy_uitree", "moy_uitree.c"),
                 ("native", "moy_uitree", "moy_uitree_walk.c"), ("native", "moy_uitree", "moy_uitree_int.h"),
                 ("native", "moy_uitree", "modmoy_uitree.c"), ("sdk", "include", "moybyte", "uitree_schema.h")):
        text = _read(*path)
        assert not re.search(r"UIT_LEGACY|UT_LEGACY|legacy_hints|\"legacy\"", text), path


def test_no_runtime_module_imports_an_immediate_toolkit():
    import glob
    assert not glob.glob(os.path.join(ROOT, "runtime", "**", "ui.py"), recursive=True)
    found = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, "runtime")):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            with open(path) as f:
                for n, line in enumerate(f, 1):
                    if re.match(r"\s*(import ui\b(?!_)|from ui import|from runtime import (.*, )?ui\b(?!_))",
                                line):
                        found.append("%s:%d" % (os.path.relpath(path, ROOT), n))
    assert not found, found


def test_the_os_calls_carry_no_ui_rows_and_no_ui_role():
    calls = json.loads(_read("native", "os_calls.json"))
    assert "ui" not in [r["role"] for r in calls["roles"]]
    assert not [r["name"] for r in calls["rows"] if r["name"].startswith("ui.")]
    for name in ("moy_ui_pull", "moy_ui_font_pull", "moy_ui_tell"):
        row = next(r for r in calls["rows"] if r["name"] == name)
        assert row.get("retired") and not row.get("wasi"), row
    from runtime import app_imports
    assert "ui" not in app_imports.PUBLIC


def test_the_run_form_is_no_face_of_the_toolkit():
    face = json.loads(_read("native", "moy_ui", "face.json"))["moy_ui"]
    for row in face["api"]:
        assert not set(row) & {"run", "run_ret", "run_fix"}, row
    for gone in ("moy_ui_run_rows.h", "moy_ui_run_face.h"):
        assert not os.path.exists(os.path.join(ROOT, "native", "moy_ui", gone)), gone


def test_no_lua_wasm_wasi_or_native_tier_has_ui_verbs():
    gone = [("native", "moycore", "moycore_ui.h"), ("native", "moycore", "moycore_ui_rows.h"),
            ("native", "moy_ui", "moy_ui_wasm.c"), ("native", "moy_ui", "moy_ui_wasm.h"),
            ("native", "moy_ui", "moy_ui_wasm_face.h"), ("native", "moy_ui", "moy_ui_wasm_rows.h"),
            ("sdk", "include", "moybyte", "ui.h"), ("sdk", "src", "moyui_link.c")]
    assert not [p for p in gone if os.path.exists(os.path.join(ROOT, *p))]
    found = []
    for top in ("native", "runtime", "device", "sdk", "tools"):
        for base, dirs, files in os.walk(os.path.join(ROOT, top)):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "wamr", "lua")]
            for name in files:
                if not name.endswith((".c", ".h", ".py", ".lua")):
                    continue
                path = os.path.join(base, name)
                with open(path, errors="replace") as f:
                    text = f.read()
                if re.search(r"MOYCORE_UI_VERBS|moycore_ui_rows|moy_ui_wasm|import_module\(\"moybyte\.ui\"\)"
                             r"|moy_ui_link_frame|moy_screen_slot_tell", text):
                    found.append(os.path.relpath(path, ROOT))
    assert not found, found
    rows = _read("native", "moy_wasm", "moy_wasi_os_rows.h")
    assert not re.search(r"X\(ui_(tell|pull|font_pull)\b", rows)


def test_no_toolkit_copy_pulls_the_theme():
    """The theme block a toolkit linked into a program pulled across the OS's
    door goes with the linked toolkit: no pull, install or font fetch, no
    instance that syncs one, and no binding row for them."""
    found = []
    for top in ("native", "runtime", "device", "sdk", "tools"):
        for base, dirs, files in os.walk(os.path.join(ROOT, top)):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "wamr", "lua")]
            for name in files:
                if not name.endswith((".c", ".h", ".py", ".lua")):
                    continue
                path = os.path.join(base, name)
                with open(path, errors="replace") as f:
                    text = f.read()
                if re.search(r"moy_ui_theme_(pull|put|font|font_ids|size|gen)\b|moy_ui_inst_(pull|sync)\b"
                             r"|MOY_UI_THEME_(MAGIC|FONTS)\b|\bfont_pull\b|\btheme_puts\b", text):
                    found.append(os.path.relpath(path, ROOT))
    assert not found, found


def test_the_moybyte_ui_extension_is_not_supported():
    from runtime import player
    assert "moybyte.ui" not in player.SUPPORTED_EXTENSIONS
    assert "moybyte.uitree" in player.SUPPORTED_EXTENSIONS


def test_every_front_numbers_the_kinds_as_the_engine_does():
    """A kind cut from the engine's enum renumbers the ones after it: the
    Python front's table and the Lua front's number each as the enum does."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("gen_uitree_schema",
                                                  os.path.join(ROOT, "tools", "gen_uitree_schema.py"))
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    engine = {k: i + 1 for i, k in enumerate(gen.engine_kinds(_read("native", "moy_uitree", "moy_uitree.h")))}
    from runtime import uitree_c
    assert uitree_c._KINDS == engine
    lua = _read("runtime", "run", "uitree_engine.lua")
    table = re.search(r"local KINDS = \{(.*?)\}", lua, re.S).group(1)
    got = {k: int(v) for k, v in re.findall(r"(\w+) = (\d+)", table)}
    assert got and all(engine[k] == v for k, v in got.items()), got


def _sources(tops, ends):
    for top in tops:
        for base, dirs, files in os.walk(os.path.join(ROOT, top)):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "wamr", "lua", ".build")]
            for name in files:
                if name.endswith(ends):
                    path = os.path.join(base, name)
                    with open(path, errors="replace") as f:
                        yield os.path.relpath(path, ROOT), f.read()


def test_no_theme_write_bracket_or_record_tables():
    found = [path for path, text in _sources(("native", "runtime", "device", "sdk", "tools"), (".c", ".h", ".py"))
             if re.search(r"moy_ui_theme_write\b|moy_ui_recs_\w+|\bmoy_ui_rec_t\b", text)]
    assert not found, found


def test_no_tool_or_board_script_imports_the_ui_module():
    """A line of a tool, a board's script or the device tier, or of a snippet
    a tool runs on a board, that imports `ui` (`import ui`, `import time, ui`,
    `from ui import`): a board has no such module."""
    pattern = re.compile(r"^\s*(import (\w+, )*ui(, \w+)*\s*$|from ui import)", re.M)
    found = ["%s:%d" % (path, text.count("\n", 0, m.start()) + 1)
             for path, text in _sources(("tools", "firmware", "device"), (".py", ".sh"))
             for m in pattern.finditer(text)]
    assert not found, found

