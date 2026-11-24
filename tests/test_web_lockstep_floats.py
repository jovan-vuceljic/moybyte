"""A Python cart simulates the same world in the browser as on a board.

Two consoles in a match run one simulation, so a page a Zero serves can play
a console's Python cart only where its VM computes floats as the boards'
does: REPR_C over 32-bit words with single-precision floats
(docs/netplay_v1.md section 5, FLOAT WIDTH IS PART OF THE LOCKSTEP CONTRACT).
Each two-player seed cart runs here frame by frame in dist/'s wasm under node
and in the host's board-model MicroPython (`make unix-micropython`'s R32
build), through the console's own cart namespace, on the same seed and the
same held buttons for both players (tests/cart_world_driver.py), and every
frame's world digest (`players.world_text`, the match's desync check) agrees.

The match around it is the kernel's C on every tier and is held by
tests/test_live_link.py and tests/test_web_live_e2e.py.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import unix_mp  # noqa: E402

ROOT = unix_mp.ROOT
DIST = ROOT / "firmware" / "web_runner" / "dist"
CARTS = ("moybyte.brick_siege.moy", "moybyte.harpoon_pop.moy")
FRAMES = 900                      # thirty seconds of a match at its 30 Hz
SINGLE = 'print("single", 16777217.0 == 16777216.0)\n'

# The paths ride the environment: micropython.mjs runs a script named on
# node's command line itself.
RUN_WASM = """
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const { MOY_DIST: dist, MOY_WORLD: script } = process.env;
const { loadMicroPython } = await import(pathToFileURL(dist + "/micropython.mjs").href);
const out = [];
const mp = await loadMicroPython({ heapsize: 16 << 20, stdout: (l) => out.push(l) });
mp.runPython(readFileSync(script, "utf-8"));
process.stdout.write(out.join("\\n") + "\\n");
"""

pytestmark = [
    pytest.mark.skipif(shutil.which("node") is None, reason="node not installed"),
    pytest.mark.skipif(not (DIST / "micropython.wasm").exists(),
                       reason="web_runner dist/ not built"),
]


def _program(cart):
    d = ROOT / "system_carts" / cart

    def text(name):
        p = d / name
        return p.read_text() if p.exists() else ""

    head = "SRC = %r\nMAP = %r\nCONFIG = %r\nSEED = 1105\nFRAMES = %d\n" % (
        text("main.py"), text("map.moymap"), json.loads(text("config.json") or "{}"), FRAMES)
    return SINGLE + head + (ROOT / "tests" / "cart_world_driver.py").read_text()


def _wasm(tmp_path, src):
    script = tmp_path / "wasm_world.py"
    script.write_text(src)
    env = dict(os.environ, MOY_DIST=str(DIST), MOY_WORLD=str(script))
    p = subprocess.run(["node", "--input-type=module", "-e", RUN_WASM],
                       capture_output=True, text=True, timeout=300, env=env)
    assert p.returncode == 0, p.stderr[-3000:]
    return p.stdout.splitlines()


def _board(exe, src):
    src = "import sys\nsys.path.insert(0, %r)\n" % unix_mp.runtime_tree() + src
    p = subprocess.run([exe, "-X", "heapsize=16M", "-c", src],
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-3000:]
    return p.stdout.splitlines()


@pytest.mark.parametrize("cart", CARTS)
def test_a_python_cart_simulates_the_same_world_in_the_browser_as_on_a_board(cart, tmp_path):
    exe = unix_mp.require_unix_mp(board_model=True, why="the boards' floats")
    src = _program(cart)
    page = _wasm(tmp_path, src)
    if page[:1] != ["single True"]:
        pytest.skip("dist/ predates the boards' floats -- rebuild it with "
                    "firmware/web_runner/build.sh")
    board = _board(str(exe), src)
    assert board[0] == "single True" and len(board) == FRAMES + 1, board[-5:]
    bad = [b for b, w in zip(board, page) if b != w]
    assert not bad and len(page) == len(board), \
        "first world that differs (frame, digest on a board): %r, page %r" % (
            bad[:1], page[board.index(bad[0])] if bad else page[-1:])
