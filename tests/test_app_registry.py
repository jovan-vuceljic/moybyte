"""The system-app registry is DATA -- the ratchet for
docs/history/ui_refactor_2026-08.md §3 Phase 5.

Adding a system app used to cost EIGHT files, five of which held the app's name
in a hand-maintained list:

  * `runtime/shell/console.py`     -- import ladder + construction + register_app(...)
  * `tools/gen_device_carts.py` -- CART_ORDER, the device launcher order
  * `tests/test_device_seed_parity.py` -- TITLE_TO_FOLDER
  * `firmware/web_runner/build.sh`  -- the browser bundle's roster
  * (`runtime/host/host_app.py` -- the bare-name alias, which only Calc ever had)

FOUR of those five failed SILENTLY, and on device only. Forget CART_ORDER and
the identity cart never seeds, so `is_app` never claims it, so the app is simply
unreachable on hardware -- while working perfectly on the host, which is where
anyone would test it.

They are all derived now, from an `"app"` block in the identity cart's own
manifest -- the same move #161 made for board staging when `board.toml` replaced
hand-edited module lists in a build script.

These tests exist so the hand-written lists cannot grow back. They are
deliberately a MIX of behavioural and structural assertions: a structural one
alone would pass against a file that still constructs apps by hand somewhere
else, and a behavioural one alone would pass against a hand-written list that
happens to agree with the manifests today.
"""

import ast
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import gen_device_carts as gdc  # noqa: E402

from runtime import app_decls  # noqa: E402
from ws_helpers import build_ws  # noqa: E402


def _read(rel):
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


# -- the declaration is the source of truth ---------------------------------

def test_app_decls_matches_the_manifests():
    """`runtime/shell/app_decls.py` is generated. If a manifest's `app` block changes
    and nobody regenerates, the frozen tiers ship a stale registry -- so the
    generated text must equal the committed file, byte for byte."""
    fresh = gdc.render_app_decls(gdc.app_decls())
    on_disk = _read("runtime/shell/app_decls.py")
    assert fresh == on_disk, (
        "runtime/shell/app_decls.py is STALE -- regenerate it:\n"
        "    python tools/gen_device_carts.py --app-decls")


def test_every_declaration_names_a_real_identity_cart():
    for d in app_decls.APPS:
        man = os.path.join(ROOT, "system_carts", d["folder"] + ".moy", "manifest.json")
        assert os.path.exists(man), "%s declares folder %r, which does not exist" % (
            d["id"], d["folder"])
        with open(man, "r", encoding="utf-8") as f:
            assert json.load(f)["title"] == d["title"]


def test_declaration_ids_and_order_are_unique():
    ids = [d["id"] for d in app_decls.APPS]
    orders = [d["order"] for d in app_decls.APPS]
    assert len(set(ids)) == len(ids), "duplicate app id in APPS"
    assert len(set(orders)) == len(orders), "duplicate app order in APPS"
    assert orders == sorted(orders), "APPS must be emitted in registration order"


# -- behavioural: the shell registers exactly what is declared ---------------

def test_the_shell_registers_exactly_the_declared_apps(tmp_path):
    """The load-bearing one. A structural check cannot see a shell that builds
    an app somewhere else; this can."""
    ws = build_ws(tmp_path)
    registered = [a.id for a in ws.app_layers]
    assert registered == [d["id"] for d in app_decls.APPS]
    for i, d in enumerate(app_decls.APPS):
        # `ws.app(id)`, how the shell and the tools address an app, builds
        # it where its slot stood; no `<id>_app` attribute stands beside it
        app = ws.app(d["id"])
        assert ws.app_layers[i] is app and app.id == d["id"]
        assert not hasattr(ws, d["id"] + "_app")


# -- structural: the hand-written lists cannot grow back --------------------

def test_console_has_no_per_app_registration_line():
    """`register_app` may appear exactly twice in the Workstation's spine half
    (runtime/shell/console_spine.py, where the declaration loop lives): its own
    definition and the ONE call inside that loop, over the declared apps and
    the shell's own two (`_declared_apps`)."""
    src = _read("runtime/shell/console_spine.py")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr == "register_app"]
    assert len(calls) == 1, (
        "console_spine.py makes %d register_app calls; the declaration loop should "
        "make exactly one. Apps are declared in their manifest, not here." % len(calls))
    defs = [n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "register_app"]
    assert len(defs) == 1


@pytest.mark.parametrize("app_id", [d["id"] for d in app_decls.APPS])
def test_no_app_is_constructed_by_name_in_console(app_id):
    """The seven `self.<id>_app = SomeAppLayer(...)` lines are gone. The class
    IMPORTS stay -- console.py's barrel is deliberately frozen, not migrated
    (docs/history/shell_decoupling_2026-08.md row 3) -- but nothing may assign one."""
    tree = ast.parse(_read("runtime/shell/console.py"))
    attr = app_id + "_app"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if (isinstance(tgt, ast.Attribute) and tgt.attr == attr
                    and isinstance(node.value, ast.Call)):
                raise AssertionError(
                    "console.py constructs self.%s by hand at line %d -- it "
                    "should come from the declaration loop" % (attr, node.lineno))


def test_gen_device_carts_holds_no_hand_written_app_list():
    """CART_ORDER is gone. Its name survives only in prose explaining why."""
    tree = ast.parse(_read("tools/gen_device_carts.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "CART_ORDER":
                    raise AssertionError(
                        "CART_ORDER is back at line %d -- the seed order is "
                        "derived from the manifests' `order`" % node.lineno)


def test_the_web_roster_is_derived_not_pasted():
    """The browser bundle's cart list comes from --roster, so a new cart marked
    for the web reaches it without anyone editing a shell script."""
    sh = _read("firmware/web_runner/build.sh")
    assert "--roster web" in sh, "the web build no longer derives its roster"
    line = [ln for ln in sh.splitlines() if ln.startswith("ROSTER=")]
    assert len(line) == 1
    assert ".moy " not in line[0], (
        "the web roster has been pasted back into build.sh: %s" % line[0])


def test_the_device_and_web_orders_agree():
    """One `order` field drives both, so the browser shelf and the device shelf
    cannot silently disagree the way the two hand-written lists did."""
    web = gdc.roster("web")
    dev = gdc.roster("device")
    assert [c for c in dev if c in set(web)] == web


def test_the_browser_shelf_is_the_boards():
    """Every seed cart a board ships, the browser ships (owner, 2026-10-20:
    the browser and the boards do not diverge). A `targets` line that leaves
    one out takes Notes from the browser's Files (its text app) or My Art
    from its Appearance (Paint's wallpaper) with nothing failing; a cart that
    cannot run in a browser is a decision argued here, not a manifest line."""
    assert gdc.roster("web") == gdc.roster("device")


# -- a boot builds no app: the declaration carries what it asks -------------

def test_a_boot_builds_no_app_and_an_open_builds_the_one(tmp_path):
    """Every declared app registers as its slot; the console's start builds
    none, nor going home (which leaves every surface), Settings or the task
    manager; opening one builds that one alone."""
    from runtime.app_slot import AppSlot
    from ws_helpers import device_frames
    ws = build_ws(tmp_path)
    device_frames(ws, 3)
    for opener in (ws.open_settings, ws.open_tasks):
        opener()
        device_frames(ws, 3)
        ws.home.go_home()
        device_frames(ws, 2)
    assert all(isinstance(a, AppSlot) for a in ws.app_layers)
    ws.spine.open_app(ws.app_layers[[d["id"] for d in app_decls.APPS].index("calc")])
    built = [a.id for a in ws.app_layers if not isinstance(a, AppSlot)]
    assert built == ["calc"]


def test_the_declaration_says_what_the_built_app_says(tmp_path):
    """What boot reads off the declaration -- the title, the resize floor --
    is what the app's class would give, so a declaration cannot drift from
    its app."""
    ws = build_ws(tmp_path)
    for d in app_decls.APPS:
        app = ws.app(d["id"])
        assert app.TITLE == (d.get("name") or d["title"]), d["id"]
        floor = getattr(app, "MIN", None)
        if floor is None:
            lay = getattr(app, "layout", None)
            if getattr(lay, "MIN_W", None) is not None:
                floor = (int(lay.MIN_W), int(lay.MIN_H))
        if floor is not None:           # (else the declaration's is the only one: Calc's)
            assert d.get("min_size") == tuple(floor), d["id"]


def test_each_app_claims_its_own_seed_cart_alone(tmp_path):
    ws = build_ws(tmp_path)
    for d in app_decls.APPS:
        app = ws.app_layers[[e["id"] for e in app_decls.APPS].index(d["id"])]
        mine = [c for c in ws.carts.all if app.is_app(c)]
        assert [c["title"] for c in mine] == [d["title"]], d["id"]
        copy = dict(mine[0], path="/carts/local.copy.moy")
        assert not app.is_app(copy)


def test_a_boot_imports_no_app_module(tmp_path):
    """The console's start on the host, in a process of its own: no app's
    module is imported until the app first runs."""
    import subprocess
    mods = sorted(d["entry"].partition(":")[0] for d in app_decls.APPS)
    code = (
        "import sys, pathlib\n"
        "sys.path[:0] = [%r, %r]\n"
        "import conftest\n"
        "from ws_helpers import build_ws, device_frames\n"
        "ws = build_ws(pathlib.Path(%r), sys_size=(320, 240))\n"
        "device_frames(ws, 5)\n"
        "print(sorted(m.rpartition('.')[2] for m in sys.modules))\n"
        % (os.path.join(ROOT, "tests"), ROOT, str(tmp_path)))
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                         text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-3000:]
    loaded = set(eval(out.stdout.strip().splitlines()[-1]))
    assert loaded.isdisjoint(mods), sorted(loaded & set(mods))
