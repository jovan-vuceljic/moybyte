"""The hosted console's pointer in a real browser: the page's CSS cursor is
the console's pointer family, drawn from its own pixels (web_boot's
`_cursor_images`, page_core.html's `curCss`), with the shape's keyword
behind it.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_pointer_e2e.py

One Chrome boot.
"""

import os
import subprocess
import sys
import time
import urllib.request

import pytest

import web_e2e
from web_e2e import RUNNER

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")


@pytest.fixture
def base():
    web_e2e.require()
    port = web_e2e.free_port()
    p = subprocess.Popen([sys.executable, "serve.py", str(port), "dist"], cwd=RUNNER,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = "http://127.0.0.1:%d" % port
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(url + "/index.html", timeout=1).read(64)
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("serve.py never answered")
        yield url
    finally:
        p.terminate()
        p.wait(timeout=10)


_CURSOR = "'CURSOR ' + document.getElementById('cv').style.cursor"


def test_the_page_cursor_is_the_familys_own_picture(tmp_path, base):
    steps = [
        {"note": "the console up", "wait": 5000},
        {"move": [400, 300]}, {"wait": 800},
        {"move": [420, 310]}, {"wait": 800},
        {"js": _CURSOR},
    ]
    out, js = web_e2e.run(tmp_path, "pointer", "?desktop=1&dev=1", steps, base,
                          tmp_path / "chrome_pointer", boot_ms=30000)
    got = [j for j in js if isinstance(j, str) and j.startswith("CURSOR ")]
    assert got, out[-3000:]
    css = got[-1][len("CURSOR "):]
    assert "url(\"data:image/png;base64," in css, out[-3000:]
    assert css.rstrip().endswith(("default", "pointer", "text")), css[-80:]
