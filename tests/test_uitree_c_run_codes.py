"""What the C engine refuses while a page runs, at the line of the call that
made the mistake: a handler's ui.focus naming a key two shown nodes have
(N08, `uit_want_focus`)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uitree_conf as C  # noqa: E402


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

