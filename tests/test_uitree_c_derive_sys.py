"""A derive over a system value on the C engine: `ui.derive(name,
cond="@desk || ...")` as a node's shown= reads the size class the frame
draws under, as the same condition written in place does."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))

import uitree_parity as P  # noqa: E402


@pytest.mark.parametrize("config, desk", (("tdeck_320x240_fs1_dark", False),
                                          ("p4_1024x600_cs2_fs1_windowed", True)))
def test_a_derive_naming_desk_shows_where_the_inline_condition_does(config, desk):
    import uitree_c
    import uitree_derive_sys as F

    def opened(ws):
        P.host(ws, F.layer(uitree_c.CEngine))

    def probe(ws):
        e = ws.app("derive_sys").engine
        kinds = e.stop_kinds()
        return "%s %s" % ("go" in kinds, "inline" in kinds)
    frames = P.frames(config, P.Surface(opened, probe=probe), ["k:a"])
    want = "True True" if desk else "False False"
    assert frames[0].state == want, [f.state for f in frames]
    assert frames[-1].state == "True True", [f.state for f in frames]      # Turn: Files is the view
