"""The project site's embedded console, in a REAL browser (site/build.py).

One console and no tiers to pick: it lays itself out from the room its frame
gives it (page_core.html, THE GLASS). A phone's frame is the handheld's 4:3
with the pads under it, a wider page's the desk's; Full screen is a compact
button beside the hint line, a thumb's height on a phone.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_site_embed_e2e.py
"""

import importlib.util
import os
import pathlib
import sys

import pytest

import web_e2e
from test_web_term_e2e import _tagged

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")

ROOT = pathlib.Path(__file__).resolve().parent.parent
PHONE = {"width": 390, "height": 844, "dpr": 3, "mobile": True}
DESKTOP = {"width": 1366, "height": 900, "dpr": 1, "mobile": False}

_MEASURE = (
    "(function () { var f = document.querySelector('#stage iframe'), w = f.contentWindow,"
    " e = document.getElementById('expand').getBoundingClientRect(),"
    " s = document.getElementById('stage').getBoundingClientRect();"
    " return w.__moyState().then(function (st) { return 'EMBED ' + JSON.stringify({"
    " tabs: document.querySelectorAll('.tab').length, src: f.getAttribute('src'),"
    " exp: [e.width, e.height], label: document.getElementById('expand').innerText.trim(),"
    " stage: [s.width, s.height], room: [w.innerWidth, w.innerHeight],"
    " phl: w.document.documentElement.classList.contains('phl'),"
    " cls: st.glass.cls, desk: st.desk}); }); })()")


def _build(tmp_path, monkeypatch):
    """The site over this tree's site player (dist_site/), stills faked."""
    spec = importlib.util.spec_from_file_location("_moy_site_build_embed",
                                                  ROOT / "site" / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)

    def stills(player, media):
        os.makedirs(media, exist_ok=True)
        for name, _scheme in build.STILLS:
            open(os.path.join(media, "console-%s.png" % name), "wb").close()
    monkeypatch.setattr(build, "capture_stills", stills)
    out = tmp_path / "_site"
    monkeypatch.setattr(sys, "argv", ["build.py", "--out", str(out), "--firmware",
                                      str(tmp_path / "none")])
    build.main()
    return out


@pytest.mark.parametrize("device", [PHONE, DESKTOP], ids=["phone", "desktop"])
def test_the_site_embeds_one_console_that_fits_itself(tmp_path, monkeypatch, device):
    web_e2e.require("site_shell")
    out = _build(tmp_path, monkeypatch)
    p, base = web_e2e.serve(out, web_e2e.free_port())
    try:
        steps = [{"wait": 500}, {"js": "document.getElementById('go').click(), 'go'"},
                 {"waitFor": "document.getElementById('stage').classList.contains('live')",
                  "timeout": 40000},
                 {"waitFor": "document.querySelector('#stage iframe').contentWindow.__moyState",
                  "timeout": 20000},
                 {"wait": 2500}, {"js": _MEASURE}, {"page": "embed"}]
        _out, js = web_e2e.run(tmp_path, "embed", "", steps, base, tmp_path / "chrome",
                               device=device, boot_ms=1000)
        e = _tagged(js, "EMBED")
        assert e, js
        assert e["tabs"] == 0 and "handheld=1" not in e["src"] and "desktop=1" not in e["src"], e
        w, h = e["stage"]
        if device is PHONE:
            # A thumb's height; the 4:3 console across the frame's width with
            # the pads under it, the handheld's layout.
            assert e["exp"][1] >= 40 and "Full screen" in e["label"], e
            assert h > w * 3 / 4 and not e["phl"] and e["cls"] == "handheld", e
        else:
            assert "Full screen" in e["label"] and e["exp"][1] <= 40, e
            assert abs(h - w * 600 / 1024) < 40, ("the desk's aspect", e)
            room_desk = e["room"][0] >= 1024 and e["room"][1] >= 600
            assert e["cls"] == ("desk" if room_desk else "handheld"), e
    finally:
        p.terminate()
