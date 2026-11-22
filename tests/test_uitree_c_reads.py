"""A canvas's reads=: the states its draw reads, which keep its page's gen."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))

import uitree_parity as P  # noqa: E402

CONFIG = "tdeck_320x240_fs1_dark"


def _gens(build):
    import uitree_c
    import uitree_canvas_reads as F
    seen = {}

    def opened(ws):
        seen["app"] = P.host(ws, F.layer(uitree_c.CEngine, build))
    P.frames(CONFIG, P.Surface(opened), ["idle:4"])
    return seen["app"].engine.gens(), F


def test_a_canvas_that_names_its_states_keeps_the_pages_gen():
    """A canvas draws what no state says, so the frame after one drew carries
    no gen; one whose reads= names what it draws does."""
    import uitree_canvas_reads as F
    named, _ = _gens(F.build_reads)
    assert named is not None, "a page whose canvas names its states carried no gen"
    unnamed, _ = _gens(F.build_none)
    assert unnamed is None, "a page whose canvas names nothing carried a gen"


def test_a_draw_that_reads_a_state_its_reads_does_not_name_is_r01():
    import uitree as S
    import uitree_canvas_reads as F
    with pytest.raises(S.UIError) as e:
        _gens(F.build_wrong)
    assert e.value.code == "R01", e.value
