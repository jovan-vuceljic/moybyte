"""The C3 Zero's browser console through the loader, on the board
(docs/web_console_online_2026-11.md §11, phase 1's on-glass tests).

The C3's console is online (`[web] console = "online"`): its root serves the
loader, which boots the pack its image names from this origin's cache or a
mirror. An image built in a worktree names this machine's
`firmware/web_runner/serve.py` first (tools/gen_web_blob.py, THE MIRRORS), so
this suite serves the worktree's pack on that port, and headless Chrome
boots the board's console from it, signs in and syncs a cart.

    tools/board.py pass c3_zero            build, flash, then this suite
    MOYBYTE_C3_ZERO_PORT=$(tools/board.py c3_zero port) \\
        .venv/bin/python -m pytest tests/test_c3_zero_on_glass.py -s

The board's address comes from its boot line (`ZERO serving <ip>  (mDNS
<name>.local)`), read once the suite attaches after a flash or a reboot, or
from MOYBYTE_C3_ZERO_URL. Signing in takes the console's password,
MOYBYTE_C3_ZERO_PASSWORD; without it the sign-in and sync test skips.

The numbers it prints (the loader's and /sync's serving time, which is the
serving loop's stall a page load costs, and the boot's cost from the mirror
against the cache, over the IP and over `.local`) belong in #256's comments,
never in a doc.
"""

import contextlib
import gzip
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

import on_glass
from on_glass import ROOT

PORT, needs_board = on_glass.gate("MOYBYTE_C3_ZERO_PORT", "the C3 Zero")
BOARD_DIR = ROOT / "firmware" / "esp32c3_zero"
RUNNER = ROOT / "firmware" / "web_runner"
DIST_PACK = BOARD_DIR / "dist" / "c3_zero" / "moybyte_web.pack"
SERVING = re.compile(r"ZERO serving (\S+)\s+\(mDNS (\S+)\)")

sys.path.insert(0, str(ROOT / "tools"))
import gen_web_blob  # noqa: E402

pytestmark = [needs_board]


@pytest.fixture(scope="module")
def board():
    """{"url", "local"}: the board's address and its `.local` one."""
    url = os.environ.get("MOYBYTE_C3_ZERO_URL")
    if url:
        return {"url": url.rstrip("/"), "local": None}
    from p4_autotest import P4Board
    b = P4Board(PORT, board_dir=str(BOARD_DIR))
    try:
        line = b.wait_line("ZERO serving", timeout=90.0)
    finally:
        b.close()
    m = SERVING.search(line or "")
    if not m:
        pytest.fail("the C3 printed no `ZERO serving` line within 90 s of the "
                    "attach (reboot it, or set MOYBYTE_C3_ZERO_URL)")
    ip = m.group(1)
    return {"url": ip if ip.startswith("http") else "http://" + ip,
            "local": "http://" + m.group(2)}


def _get(url, timeout=30):
    t = time.monotonic()
    with urllib.request.urlopen(url, timeout=timeout) as r:
        body, head = r.read(), r.headers
    return body, head, (time.monotonic() - t) * 1000


def _pack():
    with open(DIST_PACK, "rb") as f:
        data = f.read()
    return data, hashlib.sha256(data[4096:]).hexdigest(), hashlib.sha256(data).hexdigest()


def test_sync_names_the_pack_the_image_names(board):
    """GET /sync carries both digests of the pack this build wrote beside
    the image, and `local` 0: the C3 keeps no copy."""
    _data, page, whole = _pack()
    doc = json.loads(_get(board["url"] + "/sync")[0])
    assert doc == {"sync": 1, "page": page, "pack": whole, "local": 0}


def test_the_root_is_the_loader_and_what_a_page_load_costs_the_board(board):
    """`/` is the loader, gzipped, naming this machine's serve.py first; the
    board serves it inside its loop, so its serving time is the stall a page
    load costs (#256)."""
    body, head, _ms = _get(board["url"] + "/")
    assert head.get("Content-Encoding") == "gzip" and "no-cache" in head.get("Cache-Control")
    page = gzip.decompress(body).decode()
    mirrors = json.loads(re.search(r"\}\)\((\[.*?\])\)\.catch", page, re.S).group(1))
    assert mirrors[-1] == gen_web_blob.SITE_MIRROR and len(mirrors) == 2, mirrors
    for path in ("/", "/sync"):
        ms = [_get(board["url"] + path)[2] for _ in range(10)]
        print("C3 %s: %d B, served in %.0f ms median, %.0f ms max over 10"
              % (path, len(body) if path == "/" else 0, statistics.median(ms), max(ms)))


@contextlib.contextmanager
def _mirror():
    """This worktree's serve.py on the port the image names, or the one
    already there when it serves this pack."""
    _data, page, _whole = _pack()
    url = "http://127.0.0.1:%d/console/%s.pack" % (gen_web_blob.DEV_PORT, page)
    server = None
    try:
        urllib.request.urlopen(url, timeout=2).read()
    except urllib.error.HTTPError:
        pytest.fail("port %d serves another tree's pack: stop that serve.py"
                    % gen_web_blob.DEV_PORT)
    except OSError:
        server = subprocess.Popen([sys.executable, "serve.py", str(gen_web_blob.DEV_PORT),
                                   "dist"], cwd=str(RUNNER),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        for _ in range(100):
            try:
                urllib.request.urlopen(url, timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        else:
            server.terminate()
            pytest.fail("serve.py did not serve this tree's pack (is dist/ the one "
                        "the image was built from?)")
    try:
        yield
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=10)


def _browsershot(base, steps, out, query="?handheld=1&dev=1"):
    scenario = out / "scenario.json"
    out.mkdir(parents=True, exist_ok=True)
    scenario.write_text(json.dumps({"query": query, "boot_ms": 120000, "steps": steps}))
    run = subprocess.run(["node", "browsershot.mjs", str(scenario), str(out)],
                         cwd=str(RUNNER), env=dict(os.environ, MOY_BASE=base),
                         capture_output=True, text=True, timeout=600)
    print(run.stdout[-4000:])
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-500:]
    return run.stdout


BOOTED = [
    {"js": "JSON.stringify(window.moyBoot)"},
    {"js": "location.reload(), 1"},
    {"waitFor": "window.moyBoot && window.moyBoot.from == 'cache' && JSON.stringify(window.moyBoot)",
     "timeout": 120000},
]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_chrome_boots_the_console_from_the_worktree_mirror(board, tmp_path):
    """The loader takes the pack from this machine's serve.py, checked, and a
    reload from this origin's cache: the boot's cost both ways, over the IP
    and over `.local` (§11)."""
    with _mirror():
        for name, base in (("ip", board["url"]), ("local", board["local"])):
            if base is None:
                continue
            out = _browsershot(base, BOOTED, tmp_path / name)
            assert '\\"from\\":\\"http://' in out, "the first boot took no mirror"
            assert '\\"from\\":\\"cache\\"' in out


@pytest.mark.skipif(not os.environ.get("MOYBYTE_C3_ZERO_PASSWORD"),
                    reason="MOYBYTE_C3_ZERO_PASSWORD not set (the console's password)")
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_console_signs_in_and_syncs_a_cart(board, tmp_path):
    """Booted through the loader, the console pairs with the password, makes
    a cart through the real UI, and after a reload (the cache, then the
    board's pull) the shelf it pulled holds it."""
    pw = json.dumps(os.environ["MOYBYTE_C3_ZERO_PASSWORD"])
    steps = [
        {"waitFor": "document.getElementById('pin') && "
                    "document.getElementById('pin').style.display == 'flex'", "timeout": 60000},
        {"js": "document.getElementById('pinf').value = %s; "
               "document.getElementById('pinb').click(), 1" % pw},
        {"waitFor": "document.getElementById('s').textContent == 'live' && window.moyBoot "
                    "&& window.moyBoot.from == 'cache'", "timeout": 120000},
        {"wait": 1500}, {"click": [117, 9]}, {"wait": 1500},
        {"click": [160, 100]}, {"wait": 8000},
        {"js": "location.reload(), 1"},
        {"waitFor": "document.getElementById('s').textContent == 'live'", "timeout": 120000},
        {"js": "pzAsk(), 1"}, {"wait": 1000},
        {"js": "Array.from(pzC.options).map(function (o) { return o.value; }).join(',')"},
    ]
    with _mirror():
        out = _browsershot(board["url"], steps, tmp_path / "sync")
    assert "local.new_cart.moy" in out.rsplit("js ->", 1)[-1], out[-2000:]
