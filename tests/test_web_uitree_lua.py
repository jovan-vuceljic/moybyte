"""A Lua app on the UI tree runs in the browser console: Tree Form
(tests/fixtures/uitree_lua/form.moy) through the headless harness
(firmware/web_runner/harness.mjs) over the built dist/, the layer the wasm
freezes (uitree_lua.py, tools/uitree_lua_freeze.py) ahead of its scripts.

Needs a built dist/ (firmware/web_runner/build.sh), as test_web_cart_engine.py.
"""

import base64
import json
import os
import shutil
import subprocess

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_RUNNER = os.path.abspath(os.path.join(_HERE, os.pardir, "firmware", "web_runner"))
_DIST = os.path.join(_RUNNER, "dist")
_FORM = os.path.join(_HERE, "fixtures", "uitree_lua", "form.moy")


def _have_dist():
    return all(os.path.isfile(os.path.join(_DIST, n))
               for n in ("micropython.mjs", "micropython.wasm", "carts.json"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.skipif(not _have_dist(), reason="web_runner dist/ not built")
def test_a_lua_tree_app_runs_in_the_browser_console(tmp_path):
    for name in os.listdir(_DIST):
        if name != "carts.json":
            os.symlink(os.path.join(_DIST, name), tmp_path / name)
    with open(os.path.join(_DIST, "carts.json")) as f:
        carts = json.load(f)
    for name in os.listdir(_FORM):
        with open(os.path.join(_FORM, name), "rb") as f:
            raw = f.read()
        try:
            carts["tree_form.moy/" + name] = raw.decode("utf-8")
        except UnicodeDecodeError:
            carts["tree_form.moy/" + name] = {"b": base64.b64encode(raw).decode()}
    (tmp_path / "carts.json").write_text(json.dumps(carts))
    p = subprocess.run(["node", "harness.mjs", "tree_form.moy"], cwd=_RUNNER,
                       env=dict(os.environ, MOY_DIST=str(tmp_path)),
                       capture_output=True, text=True, timeout=180)
    assert p.returncode == 0 and "harness: ALL OK" in p.stdout, \
        "Tree Form in the browser console:\n%s\n%s" % (p.stdout[-3000:], p.stderr[-3000:])
