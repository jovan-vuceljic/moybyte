"""The UI engine's wasm rows (native/moy_uitree/moy_uitree_wasm.h): the
`uitree` rows a compiled app imports, called here as the natives they are,
with no module (a run's own pages are tests/test_uitree_conformance.py's
compiled halves).

  * the numbers sdk/include/moybyte/uitree.h (and its generated
    uitree_schema.h) give an app are the engine's;
  * a refusal is latched for the run, and its line names its code, its row
    and where on the page;
  * a prop is held to the contract's table at the row that names it, with
    the contract's code, though the module carries no check of its own;
  * a read answers the whole length, whatever the buffer held;
  * a model's write is traced as the Python and Lua layers trace a set.
"""

import ctypes as c
import os
import re

import face_ctypes
from runtime.host import moy_log

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_P, _I, _U, _B = c.c_void_p, c.c_int32, c.c_uint32, c.c_char_p

_SIGS = (
    ("moy_uitree_wasm_end", [], None),
    ("moy_uitree_wasm_state", [_P, _B, _U, _I, _B, _U], _I),
    ("moy_uitree_wasm_model", [_P, _I, _B, _U, _B, _U, _I], _I),
    ("moy_uitree_wasm_build", [_P, _B, _U], _I),
    ("moy_uitree_wasm_node", [_P, _I, _B, _U, _I], _I),
    ("moy_uitree_wasm_prop", [_P, _I, _B, _U, _B, _U], _I),
    ("moy_uitree_wasm_open", [_P], _I),
    ("moy_uitree_wasm_frame", [_P, _I], _I),
    ("moy_uitree_wasm_set_text", [_P, _I, _B, _U], _I),
    ("moy_uitree_wasm_get_text", [_P, _I, _P, _U], _I),
    ("moy_uitree_wasm_set_model", [_P, _I, _I, _B, _U], _I),
    ("moy_uitree_wasm_error", [_P, _P, _U], _I),
)
NUM, TEXT, MODEL = 3, 4, 7
PAGE, GROUP, LABEL = 1, 2, 3
E_KIND, E_ARG, E_CHECK = -3, -5, -6


class Rows:
    """The rows, each text a Python str, on a run of their own."""

    def __init__(self):
        self.d = face_ctypes.lib(_SIGS)
        self.d.moy_uitree_wasm_end()

    def __getattr__(self, verb):
        fn = getattr(self.d, "moy_uitree_wasm_" + verb)

        def call(*args):
            out = [None]
            for a in args:
                if isinstance(a, str):
                    b = a.encode()
                    out += [b, len(b)]
                elif isinstance(a, bytes):
                    out += [a, len(a)]
                else:
                    out.append(a)
            return fn(*out)
        return call

    def read(self, verb, *args, cap=64):
        buf = c.create_string_buffer(cap)
        n = getattr(self, verb)(*args, c.cast(buf, c.c_void_p), cap)
        return n, buf.raw[:min(max(n, 0), cap)].decode()

    def close(self):
        self.d.moy_uitree_wasm_end()


def _enums(path, prefix):
    """Each enum of the header at `path` as {name without `prefix`: value}."""
    with open(os.path.join(ROOT, path)) as f:
        text = f.read()
    out = []
    for body in re.findall(r"enum\s*\{(.*?)\}", text, re.S):
        body = re.sub(r"//[^\n]*", "", body)
        n, got = 0, {}
        for item in (x.strip() for x in body.split(",")):
            m = re.match(r"(%s\w+)(?:\s*=\s*(-?\d+))?$" % prefix, item)
            if m:
                n = int(m.group(2)) if m.group(2) is not None else n
                got[m.group(1)[len(prefix):]] = n
                n += 1
        if got:
            out.append(got)
    return out


def test_the_sdk_headers_numbers_are_the_engines():
    """Each of the SDK's enums is one of the engine's, whole: the types, every
    kind, the action flags and the refusals (the off values are uit_action's)."""
    engine = _enums("native/moy_uitree/moy_uitree.h", "UIT_")
    for sdk in _enums("sdk/include/moybyte/uitree.h", "UT_") + _enums("sdk/include/moybyte/uitree_schema.h", "UT_"):
        if "OFF_NONE" in sdk:
            assert sdk == {"OFF_NONE": 0, "OFF_HIDE": 1, "OFF_GREY": 2}
            continue
        mine = next((e for e in engine if next(iter(sdk)) in e), None)
        assert mine is not None, sdk
        assert {k: v for k, v in mine.items() if k != "KINDS"} == sdk


def test_a_refusal_is_latched_and_names_its_row_and_place():
    r = Rows()
    try:
        assert r.state("note", TEXT, b"") == 0
        r.build("1 page")
        page = r.node(PAGE, "page", -1)
        group = r.node(GROUP, "group#0", page)
        assert r.node(99, "odd", group) == E_KIND
        n, line = r.read("error", cap=200)
        assert line.startswith("KIND uitree_node(page/group#0/odd): "), line
        assert n == len(line.encode())
        # every later row answers it again, a read included
        assert r.state("other", TEXT, b"") == E_KIND
        assert r.read("get_text", 0)[0] == E_KIND
    finally:
        r.close()
    r = Rows()
    try:
        assert r.state("note", TEXT, b"") == 0        # a new run starts clean
        assert r.read("error")[0] == 0
    finally:
        r.close()


def test_a_prop_is_held_to_the_contract_with_its_code_page_path_and_name():
    for name, src, line in (
            ("nope", "1", "N01 uitree_prop(page/group#0/label#0 nope=): ui.label has no prop 'nope'; fix: drop it"),
            ("tones", "x", "N01 uitree_prop(page/group#0/label#0 tones=): ui.label has no prop 'tones'; "
                           "fix: did you mean 'tone' or 'lines'?"),
            ("ink", "x", "N04 uitree_prop(page/group#0/label#0 ink=): ui.label ink= is retired; fix: tone="),
            ("wrap", "x", "N01 uitree_prop(page/group#0/label#0 wrap=): ui.label wrap='x'; fix: wrap='cut' "
                          "(expected cut, word, char)")):
        r = Rows()
        try:
            r.build("1 page")
            page = r.node(PAGE, "page", -1)
            group = r.node(GROUP, "group#0", page)
            label = r.node(LABEL, "label#0", group)
            assert r.prop(label, "text", "hi") >= 0
            assert r.prop(label, name, src) == E_CHECK
            assert r.read("error", cap=400)[1].startswith(line), (name, r.read("error", cap=400)[1])
        finally:
            r.close()


def test_a_frame_is_refused_before_a_page_and_with_a_flag():
    for flags, words in ((0, "no page is built"), (4, "flags is 0")):
        r = Rows()
        try:
            r.state("note", TEXT, b"")
            assert r.frame(flags) == E_ARG
            assert words in r.read("error", cap=200)[1]
        finally:
            r.close()


def test_a_read_answers_the_whole_length():
    r = Rows()
    try:
        s = r.state("note", TEXT, b"")
        r.set_text(s, "a longer text than the buffer")
        assert r.read("get_text", s, cap=6) == (29, "a long")
    finally:
        r.close()


def test_a_number_crosses_as_its_digits():
    """A number state is set and read as text, spelled as the trace spells
    it; text that is no number is refused."""
    r = Rows()
    try:
        n = r.state("level", NUM, b"")
        assert r.set_text(n, "2.5") == 0
        assert r.read("get_text", n) == (3, "2.5")
        r.set_text(n, "-1e3")
        assert r.read("get_text", n) == (5, "-1000")
        assert r.set_text(n, "2.5kg") == E_ARG
        assert r.read("error", cap=200)[1].startswith("ARG uitree_set_text(level): a number state takes")
    finally:
        r.close()


def test_a_model_write_is_traced_as_the_layers_trace_a_set():
    r = Rows()
    try:
        m = r.state("items", MODEL, b"")
        r.model(m, b"id\0name", bytes([TEXT, TEXT]), 0)
        seq = moy_log.next()
        r.set_model(m, 1, b"z\0Zero\0")               # before the visit: the app's start
        r.open()
        r.set_model(m, 3, b"a\0Apples\0b\0Bread\0c\0Cheese\0")
        r.set_model(m, 3, b"a\0Apples\0b\0Buns\0c\0Cheese\0")
        r.set_model(m, 3, b"c\0Cheese\0a\0Apples\0b\0Buns\0")
        r.set_model(m, 3, b"c\0Cheese\0a\0Apples\0b\0Buns\0")   # nothing moved: no line
        lines = [re.sub(r"\s+", " ", t.split("[trace] ", 1)[1][13:]).strip()
                 for t in (x[4] for x in moy_log.read(seq, 100)) if "[trace] " in t]
        assert lines == [
            "state items [3 rows] +3 -1 ~0 moved 0 (in the app)",
            'state items "b": name "Bread" -> "Buns" (in the app)',
            "state items [3 rows] +0 -0 ~0 moved 3 (in the app)",
        ]
    finally:
        r.close()


def test_a_canvas_is_drawn_by_the_app_and_hands_its_pointer_to_an_action():
    """A canvas's draw is the module's own, called inside the frame; a press
    on it, its drag and its release reach the pointer= action as down, drag
    and up in the canvas's coordinates, the press holding the canvas."""
    import uitree_conf as C
    cart = os.path.join(ROOT, "tests", "fixtures", "uitree_canvas_wasm.moy")
    trace, frames = C.run_wasm(None, C.CONFIGS[0], ["swipe:20"], cart=cart)
    acts = [l for l in trace if l.startswith("action poke")]
    assert acts[0] == "action poke from pointer down on canvas 'pad'"
    assert acts[-1] == "action poke from pointer up on canvas 'pad'"
    assert "action poke from pointer drag on canvas 'pad'" in acts
    down = next(re.search(r"-> 'down (\d+),(\d+) drawn' \(in poke\)$", l) for l in trace if "-> 'down " in l)
    up = next(re.search(r"-> 'up (\d+),(\d+) drawn' \(in poke\)$", l) for l in trace if "-> 'up " in l)
    assert up.group(1) == down.group(1) and int(up.group(2)) - int(down.group(2)) == 20



def test_a_tables_canvas_hands_the_press_on_a_row_with_that_row():
    """A table's canvas child draws each row; a press on one, its drag and
    its release reach the pointer= action with the row pressed, in that
    row's coordinates, as a Python or Lua app's handler is handed ev.row."""
    import uitree_conf as C
    cart = os.path.join(ROOT, "tests", "fixtures", "uitree_table_wasm.moy")
    trace, _ = C.run_wasm(None, C.CONFIGS[0], ["f:2", "swipe:5"], cart=cart)
    got = [re.search(r"-> '(\w+) (-?\d+),(-?\d+)' \(in poke\)$", l) for l in trace if "(in poke)" in l]
    got = [(m.group(1), int(m.group(2)), int(m.group(3))) for m in got if m]
    assert got and got[0][0] == "down" and got[-1][0] == "up", trace
    assert len({row for _k, row, _y in got}) == 1 and got[0][1] >= 0 and 0 <= got[0][2] < 30, got


def test_a_canvas_under_an_open_dialog_takes_no_press():
    """While a dialog is up a canvas outside it takes no press (only one in
    it would), as uitree_c.py's point() routes a Python app's."""
    import uitree_conf as C
    cart = os.path.join(ROOT, "tests", "fixtures", "uitree_modal_wasm.moy")
    trace, _ = C.run_wasm(None, C.CONFIGS[0], ["f:2", "swipe:20"], cart=cart)
    assert not [l for l in trace if l.startswith("action poke")], trace


def test_a_page_takes_a_row_and_the_app_moves_the_focus():
    """ut_focus puts the focus on a row's part; that row's action pushes a
    page that takes the row (its cursor set first), and Back puts the focus
    back on it."""
    import uitree_conf as C
    cart = os.path.join(ROOT, "tests", "fixtures", "uitree_rowpage_wasm.moy")
    trace, _ = C.run_wasm(None, C.CONFIGS[0], ["f:2", "k:a", "back"], cart=cart)
    assert trace[trace.index("action open from link 'b/open' on 'Shelf'"):] == [
        "action open from link 'b/open' on 'Shelf'",
        "state sel '' -> 'b' (in open)",
        "page push page 2, opened from 'b/open'",
        "page back page 1, focus back to 'b/open'"]


def test_a_page_pushed_over_itself_with_another_row_gives_the_first_its_row_back():
    """ut_push_row's page keeps the row it was pushed with: the details of
    Bread pushed over by the details of Apples, Back sets the cursor to
    Bread again as it builds the page under."""
    import uitree_conf as C
    cart = os.path.join(ROOT, "tests", "fixtures", "uitree_rowpage_wasm.moy")
    trace, _ = C.run_wasm(None, C.CONFIGS[0], ["f:2", "k:a", "k:a", "back", "back"], cart=cart)
    assert trace[trace.index("action open from link 'b/open' on 'Shelf'"):] == [
        "action open from link 'b/open' on 'Shelf'",
        "state sel '' -> 'b' (in open)",
        "page push page 2, opened from 'b/open'",
        "action other from link 'other' on 'Details'",
        "state sel 'b' -> 'a' (in other)",
        "page push page 3, opened from 'other'",
        "state sel 'a' -> 'b' (in the app)",
        "page back page 2, focus back to 'other'",
        "page back page 1, focus back to 'b/open'"]


def test_more_role_runs_on_the_m_key():
    """The more role's key (m) runs the page's action where no field is
    focused and the focused row's action where it hangs from a row; a field
    that holds focus takes the letter."""
    import uitree_conf as C
    fx = os.path.join(ROOT, "tests", "fixtures")
    trace, _ = C.run_wasm(None, C.CONFIGS[0], ["f:2", "t:m", "f:1", "k:down", "t:m"],
                          cart=os.path.join(fx, "uitree_more_wasm.moy"))
    assert [l for l in trace if l.startswith("action more")] == [
        "action more from key more on 'tools' on 'Tools'"]
    trace, _ = C.run_wasm(None, C.CONFIGS[0], ["f:2", "t:m"], cart=os.path.join(fx, "uitree_morerow_wasm.moy"))
    assert [l for l in trace if l.startswith("action open from")] == [
        "action open from key more on 'b/open' on 'Shelf'"]


def test_a_buttons_arg_and_a_typed_char_reach_their_handlers():
    """A button's arg= reaches its action's handler (ut_arg), each button of
    one action keyed by its arg; a typed key an action's chars= holds owes
    that action, the key its arg, and a key no action holds owes none."""
    import uitree_conf as C
    cart = os.path.join(ROOT, "tests", "fixtures", "uitree_arg_wasm.moy")
    trace, _ = C.run_wasm(None, C.CONFIGS[0], ["f:2", "k:a", "k:down", "k:a", "t:5", "t:x"], cart=cart)
    assert [l for l in trace if l.startswith(("action", "state"))] == [
        "action key from button 'key/7' on 'Keypad'",
        "state said '' -> '7' (in key)",
        "action key from button 'key/+' on 'Keypad'",
        "state said '7' -> '+' (in key)",
        "action typed from key '5'",
        "state said '+' -> '5' (in typed)"]


def test_build_refuses_an_app_the_engine_refused_in_init(tmp_path):
    """tools/wasm_cart.build runs a UI tree app's `_init` on the host's WAMR and
    fails with the engine's refusal, naming its code; a good app builds."""
    import pytest
    from runtime import wasm_host
    from tools import wasm_cart
    if not wasm_host.available():
        pytest.skip("no host wasm binding")
    fx = os.path.join(ROOT, "tests", "fixtures")
    wasm_cart.build(os.path.join(fx, "uitree_more_wasm.moy"), str(tmp_path / "good.moy"))
    with pytest.raises(ValueError, match=r"T02 .*no state nothing"):
        wasm_cart.build(os.path.join(fx, "uitree_bad_wasm.moy"), str(tmp_path / "bad.moy"))


def test_a_carousel_is_a_cards_look_the_rows_take_and_another_look_is_refused():
    """A compiled app's carousel (`ut_carousel_`, sdk/include/moybyte/uitree.h):
    cards look="carousel" lowers and draws; another word is refused at the
    row that names it, by the contract's table."""
    cards = _enums("sdk/include/moybyte/uitree_schema.h", "UT_")
    cards = next(e for e in cards if "CARDS" in e)["CARDS"]
    for look, ok in (("carousel", True), ("grid", False)):
        r = Rows()
        try:
            m = r.state("items", MODEL, b"")
            r.model(m, b"id\0name", bytes([TEXT, TEXT]), 0)
            assert r.state("at", 6, b"items") >= 0
            r.build("1 page")
            page = r.node(PAGE, "page", -1)
            node = r.node(cards, "items", page)
            assert r.prop(node, "bind", "items") >= 0 and r.prop(node, "cur", "at") >= 0
            got = r.prop(node, "look", look)
            if ok:
                assert got >= 0, r.read("error", cap=400)[1]
            else:
                assert got == E_CHECK
                assert "cards look='grid'" in r.read("error", cap=400)[1], r.read("error", cap=400)[1]
        finally:
            r.close()
