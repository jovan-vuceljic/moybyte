"""The UI re-architecture's clean cut, kept: every shipped surface runs on the
UI tree engine (native/moy_uitree over native/moy_ui), and what the cut took
out stays out.

  * the `legacy` kind -- a surface on the immediate verbs hosted in one node
    of a tree -- is no kind of any front: not the Python API's, not the
    contract's, not the C engine's;
  * the shell draws on the engine, not the immediate toolkit: no runtime
    module but `shell/system_api.py` (a Python app cart's `ui`) imports
    runtime/toolkit/ui.py.
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
    contract = json.loads(_read("tests", "uitree_contract", "contract.json"))
    assert "legacy" not in contract["kinds"]
    for path in (("native", "moy_uitree", "moy_uitree.h"), ("native", "moy_uitree", "moy_uitree.c"),
                 ("native", "moy_uitree", "moy_uitree_walk.c"), ("native", "moy_uitree", "moy_uitree_int.h"),
                 ("native", "moy_uitree", "modmoy_uitree.c"), ("sdk", "include", "moybyte", "uitree_schema.h")):
        text = _read(*path)
        assert not re.search(r"UIT_LEGACY|UT_LEGACY|legacy_hints|\"legacy\"", text), path


def test_no_shell_module_draws_with_the_immediate_toolkit():
    found = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, "runtime")):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, ROOT)
            if rel in ("runtime/toolkit/ui.py", "runtime/shell/system_api.py"):
                continue
            with open(path) as f:
                for n, line in enumerate(f, 1):
                    if re.match(r"\s*(import ui\b(?!_)|from ui import)", line):
                        found.append("%s:%d" % (rel, n))
    assert not found, found


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
