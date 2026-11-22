"""What the C engine refuses while a page runs, at the line of the call that
made the mistake: a handler's ui.focus naming a key two shown nodes have
(N08, `uit_want_focus`) and two shown rows lent to one site (L03, `uit_live`)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uitree_conf as C  # noqa: E402


class _Damage:
    def all(self):
        pass


def _module(tmp_path, name, src):
    app_py = tmp_path / name / "app.py"
    app_py.parent.mkdir()
    app_py.write_text(src)
    return C._module(str(app_py))


TWO_KEYED_ALIKE = '''import uitree as ui

s = ui.state(n=0)


def nothing():
    pass


def jump():
    ui.focus("go")


ui.action("go", "Go", nothing)
ui.action("jump", "Jump", jump)


def build():
    with ui.page("P"):
        ui.link("jump")
        with ui.group("A"):
            ui.link("go")
        with ui.group("B"):
            ui.link("go")
'''


def test_a_focus_on_a_key_two_shown_nodes_have_is_n08_at_the_focus(tmp_path):
    import uitree as S
    import uitree_app
    import uitree_c
    import uitree_parity as P
    mod = _module(tmp_path, "keyed", TWO_KEYED_ALIKE)
    cls = uitree_app.app_layer("keyed_c", "Keyed", mod.build, engine=uitree_c.CEngine)
    seen = {}

    def opened(ws):
        seen["app"] = P.host(ws, cls)
    with pytest.raises(S.UIError) as e:
        P.frames(C.CONFIGS[0], P.Surface(opened, probe=lambda ws: seen["app"].engine.focus_key), ["k:a", "f:2"])
    assert e.value.code == "N08" and e.value.where == ("app.py", 11), e.value.text()
    assert "two shown nodes are keyed go" in e.value.text()


TWO_LENDERS = '''import uitree as ui

s = ui.state(both=False)


def nothing():
    pass


ui.action("undo", "Undo", nothing)
ui.action("redo", "Redo", nothing)


def page():
    with ui.page("Lenders"):
        with ui.tools("one", lend="bar"):
            ui.button("undo", icon="undo")
        with ui.tools("two", lend="bar", shown="both"):
            ui.button("redo", icon="redo")
'''


def test_two_shown_rows_lent_to_one_site_are_l03_at_the_second(tmp_path):
    import ui_draw
    import uitree as S
    import uitree_c
    mod = _module(tmp_path, "lenders", TWO_LENDERS)
    page = uitree_c.CEditorPage(mod.page, ui_draw.AppHost(), _Damage())
    page.open(hook="none")
    page.fs = 1
    page.place((0, 0, 300, 200), desk=False)        # one shown: the bar's row is the first's
    assert [c[1] for c in page.lent("bar")] == ["undo"]
    page.run(setattr, mod.s, "both", True)
    with pytest.raises(S.UIError) as e:
        page.place((0, 0, 300, 200), desk=False)
    assert e.value.code == "L03" and e.value.where == ("app.py", 18), e.value.text()
    assert "lend to bar: one and two" in e.value.text()

