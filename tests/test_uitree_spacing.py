"""A UI spacing (gap=, pad=) is an int at 1x, which the engine multiplies by the
chrome scale in force (layout_base.scale): a caller never hands it a value it
multiplied by a scale itself. The check reads every Python page and host under
runtime/ and system_carts/ and refuses

  * a gap= or pad= on a ui call that is not an int, a template or a name;
  * a spacing state (`s.NAME`, `ui.state(NAME=)` or `_put("NAME", ...)`, where a gap= or pad=
    names {NAME}) given a product with a scale (fs, cs, u, unit, sp, du, a
    scale() or unit() call);
  * a PAD or GAP constant multiplied by a scale as an item of a tuple, the
    shape of the values a host hands its page.

And each front takes a 1x int, scaled by the engine, and refuses a word."""

import ast
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
SPACING = ("gap", "pad")
SCALES = {"fs", "cs", "u", "unit", "sp", "du", "scale", "font_scale", "chrome_scale"}


def _sources():
    for top in ("runtime", "system_carts"):
        for d, _, fs in os.walk(os.path.join(ROOT, top)):
            for f in fs:
                if f.endswith(".py"):
                    p = os.path.join(d, f)
                    yield os.path.relpath(p, ROOT), ast.parse(open(p).read(), p)


def _is_scale(n):
    if isinstance(n, ast.Name):
        return n.id in SCALES
    if isinstance(n, ast.Attribute):
        return n.attr in SCALES
    if isinstance(n, ast.Call):
        return _is_scale(n.func)
    return False


def _scaled(n):
    """Whether expression `n` multiplies by a scale anywhere in it."""
    return any(isinstance(b, ast.BinOp) and isinstance(b.op, ast.Mult) and (_is_scale(b.left) or _is_scale(b.right))
               for b in ast.walk(n))


def _spacing_const(n):
    name = n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else ""
    return "PAD" in name or "GAP" in name


def _state_names(t):
    """The state fields target `t` writes: `s.NAME`, in a tuple or alone."""
    if isinstance(t, (ast.Tuple, ast.List)):
        for e in t.elts:
            yield from _state_names(e)
    elif isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "s":
        yield t.attr
    else:
        yield None


def test_no_spacing_is_handed_over_already_scaled():
    trees = list(_sources())
    bound, bad = set(), []
    for path, tree in trees:
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "ui"):
                continue
            for kw in n.keywords:
                if kw.arg not in SPACING:
                    continue
                v = kw.value
                if isinstance(v, ast.Constant) and type(v.value) is str and v.value.startswith("{"):
                    bound.add(v.value.strip("{}"))
                elif not (isinstance(v, ast.Constant) and type(v.value) is int or isinstance(v, (ast.Name, ast.Attribute))):
                    bad.append("%s:%d ui.%s %s= is not an int at 1x" % (path, n.lineno, n.func.attr, kw.arg))
    for path, tree in trees:
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    tn, vs = list(_state_names(t)), n.value.elts if isinstance(n.value, ast.Tuple) else [n.value]
                    pairs = zip(tn, vs) if isinstance(t, ast.Tuple) and len(tn) == len(vs) else ((x, n.value) for x in tn)
                    for name, v in pairs:
                        if name in bound and _scaled(v):
                            bad.append("%s:%d %s, a spacing at 1x, is multiplied by a scale" % (path, n.lineno, name))
            elif isinstance(n, ast.Call) and len(n.args) >= 2 and isinstance(n.args[0], ast.Constant) \
                    and n.args[0].value in bound and _scaled(n.args[1]) \
                    and getattr(n.func, "id", getattr(n.func, "attr", "")).endswith("put"):
                bad.append("%s:%d %s is put multiplied by a scale" % (path, n.lineno, n.args[0].value))
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "state":
                for kw in n.keywords:
                    if kw.arg in bound and _scaled(kw.value):
                        bad.append("%s:%d state %s is multiplied by a scale" % (path, n.lineno, kw.arg))
            if isinstance(n, ast.Tuple):
                for b in n.elts:
                    if isinstance(b, ast.BinOp) and isinstance(b.op, ast.Mult) and (
                            _spacing_const(b.left) and _is_scale(b.right) or _spacing_const(b.right) and _is_scale(b.left)):
                        bad.append("%s:%d a PAD or GAP constant multiplied by a scale" % (path, b.lineno))
    assert not bad, "\n".join(bad)


PAGE = ("import uitree as ui\n"
        "s = ui.state(n=0)\n"
        "def build():\n"
        "    with ui.page(\"P\"):\n"
        "        with ui.split(\"row\", sizes=(1, 1), %s):\n"
        "            ui.label(\"a\")\n"
        "            ui.label(\"b\")\n")


@pytest.mark.parametrize("prop, ok", [("gap=6, pad=0", True), ("gap=\"s\"", False), ("pad=\"m\"", False)])
def test_python_a_split_takes_an_int_at_1x_and_refuses_a_word(prop, ok, tmp_path):
    import uitree_check
    (tmp_path / "sp.py").write_text(PAGE % prop)
    got = [e.code for e in uitree_check.check(str(tmp_path / "sp.py")).errors]
    assert got == ([] if ok else ["N01"]), got


def test_the_scale_is_the_chrome_scale_in_force():
    import layout_base as lb
    was = lb.metric_class()
    try:
        lb.place_class(lb.DESK)
        assert lb.scale(1) == 2                     # the desk's unit at chrome size 1
        lb.place_class(lb.DESK, render=2)
        assert lb.scale(1) == 1                     # a doubled surface halves it
        lb.place_class(lb.HANDHELD)
        assert lb.scale(1) == 1 and lb.scale(3) == 3
        lb.set_scale(2)                             # a tap floor over the font scale
        assert lb.scale(1) == 2
    finally:
        lb.place_class(was)


def test_compiled_a_split_s_gap_is_scaled_and_a_word_refused():
    """A compiled app's split takes its gap as an int at 1x and is refused a word."""
    from test_uitree_wasm import Rows, PAGE as PG, E_CHECK
    import uitree_c
    r = Rows()
    try:
        r.build("1 page")
        page = r.node(PG, "page", -1)
        sp = r.node(uitree_c._KINDS["split"], "sp", page)
        assert r.prop(sp, "gap", "6") >= 0
        assert r.prop(sp, "pad", "s") == E_CHECK
        assert "T03" in r.read("error", cap=400)[1]
    finally:
        r.close()
