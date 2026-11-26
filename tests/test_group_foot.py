"""A button that is a group's last row (native/moy_ui/moy_ui_api.c,
`mua_group_close`): the card's foot rounds its corners under it, and the
button is drawn again over them, so its edge and its focus ring stay whole
and no row's focus mark (moy's bar) lands in them: the button draws as it
does with a row after it, focused or not, in every seed theme."""

import pytest

from test_app_field_typing import _open

DT = 1 / 30

APP = """
s = ui.state(n=0)
ui.app("Group App", icon="calc")


def go():
    s.n += 1


ui.action("go", "Go on", go)
ui.action("other", "Other", go)
ui.action("more", "More", go)


def build():
    with ui.page("Group"):
        with ui.group("Things"):
            ui.link("other")
            ui.button("go")
"""

# The same button with a row after it: no foot under it.
APP_MID = APP.replace('            ui.button("go")\n', '            ui.button("go")\n            ui.link("more")\n', 1)


def _button(tmp_path, src, theme, variant, focus):
    """The pixels of the "go" button's box, focused or not."""
    ws, d = _open(tmp_path, "group_app", src, "python")
    ws.look.set_theme(theme, persist=False, variant=variant)
    host = ws.run.player.tree.engine._ui
    host.focus(focus)
    for _ in range(3):
        d.frame(DT)
    ws.mark_dirty()
    d.frame(DT)
    x, y, w, h = host.box("go")
    cv = ws.sys_canvas
    buf, W = bytes(cv.to_rgb888()), cv.w
    return (x, y, w, h), [buf[3 * (r * W + x):3 * (r * W + x + w)] for r in range(y, y + h)]


@pytest.mark.parametrize("focus", ["go", "other"])
@pytest.mark.parametrize("theme,variant", [("moy", "light"), ("moy", "dark"), ("blocks", "light"),
                                           ("contrast", "dark")])
def test_a_groups_last_button_draws_as_one_with_a_row_after_it(tmp_path, theme, variant, focus):
    box, last = _button(tmp_path / "last", APP, theme, variant, focus)
    box2, mid = _button(tmp_path / "mid", APP_MID, theme, variant, focus)
    assert box == box2
    x, y, w, h = box
    bad = [(x + j // 3, y + i, tuple(a[j:j + 3]), tuple(b[j:j + 3]))
           for i, (a, b) in enumerate(zip(last, mid))
           for j in range(0, len(a), 3) if _inside(j // 3, i, w, h) and a[j:j + 3] != b[j:j + 3]]
    assert not bad, "the group's foot drew over its last button at %s" % bad[:8]


def _inside(i, j, w, h):
    """Whether (i, j) of a w x h button lies inside a pill of that box, a
    pixel and a half in: inside any button's rounded edge, where the card's
    foot, rounded or not, has nothing to show."""
    r = h / 2
    cx = min(max(i + 0.5, r), w - r)
    return ((i + 0.5 - cx) ** 2 + (j + 0.5 - r) ** 2) ** 0.5 <= r - 1.5
