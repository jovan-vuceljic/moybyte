"""A Python cart simulates the same world in the browser as on a board.

Two consoles in a match run one simulation, so a page a Zero serves can play
a console's Python cart only where its VM computes floats as the boards'
does: REPR_C over 32-bit words with single-precision floats
(docs/netplay_v1.md section 5, FLOAT WIDTH IS PART OF THE LOCKSTEP CONTRACT).
Each two-player seed cart runs here frame by frame in dist/'s wasm under node
and in the host's board-model MicroPython (`make unix-micropython`'s R32
build), through the console's own cart namespace, on the same seed and the
same held buttons for both players (tests/cart_world_driver.py), and every
frame's world digest (`players.world_text`, the match's desync check) agrees,
and so does every float function of the math module, which every tier
computes with the kernel's one libm (native/moy_kernel/README.md).

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


# Every function of the math module that the C library computes, over its
# domain, and the pairs that once parted the T-Deck and the wasm. A cart's
# math is the kernel's one libm on every tier (native/moy_kernel/README.md,
# THE FLOAT FUNCTIONS), so both sides of a match answer each with one float.
LIBM = """
import math, struct
ONE = {"sin": (-60, 60), "cos": (-60, 60), "tan": (-6, 6), "asin": (-1, 1), "acos": (-1, 1),
       "atan": (-40, 40), "exp": (-20, 20), "log": (0.001, 5000), "sqrt": (0, 5000),
       "floor": (-50, 50), "sinh": (-9, 9), "cosh": (-9, 9), "tanh": (-5, 5),
       "log10": (0.001, 5000), "log2": (0.001, 5000), "expm1": (-5, 5), "asinh": (-50, 50),
       "acosh": (1, 50), "atanh": (-0.99, 0.99), "erf": (-3, 3), "erfc": (-3, 3),
       "gamma": (0.1, 20), "lgamma": (0.1, 30)}
TWO = {"atan2": ((-10, 10), (-10, 10)), "pow": ((0.01, 10), (-6, 6)),
       "fmod": ((-100, 100), (0.1, 9))}
PAIRS = [(1.0, 2.5), (-1.0, 2.5), (1.5, -2.0), (0.0, -1.0), (-0.0, -1.0), (1.0, 0.0)]
N = 400

def at(lo, hi, i):
    return lo + (hi - lo) * ((i * 0.6180339887) % 1.0)

def word(f, *a):
    try:
        return struct.unpack("<I", struct.pack("<f", getattr(math, f)(*a)))[0]
    except (ValueError, OverflowError):
        return -1

for f, (lo, hi) in sorted(ONE.items()):
    print(f, [word(f, at(lo, hi, i)) for i in range(N)])
for f, ((a, b), (c, d)) in sorted(TWO.items()):
    print(f, [word(f, at(a, b, i), at(c, d, 7 * i + 3)) for i in range(N)])
print("atan2-pairs", [word("atan2", y, x) for y, x in PAIRS])
print("atan-of-quotient", [word("atan", y / x) for y, x in PAIRS[:2]])
"""


def test_a_cart_s_math_is_one_libm_in_the_browser_and_on_a_board(tmp_path):
    exe = unix_mp.require_unix_mp(board_model=True, why="the boards' floats")
    src = SINGLE + LIBM
    page = _wasm(tmp_path, src)
    if page[:1] != ["single True"]:
        pytest.skip("dist/ predates the boards' floats -- rebuild it with "
                    "firmware/web_runner/build.sh")
    board = _board(str(exe), src)
    assert len(board) == len(page) == 29, (board[-3:], page[-3:])
    apart = [b.split()[0] for b, w in zip(board, page) if b != w]
    assert not apart, "the R32 build and the wasm part on %s" % apart
    # The kernel's atan2f takes the atan of the rounded quotient, as glibc's
    # does not: atan2(1.0, 2.5) is the C library's on neither side.
    rows = dict(line.split(" ", 1) for line in board[1:])
    assert eval(rows["atan2-pairs"])[:2] == eval(rows["atan-of-quotient"])
