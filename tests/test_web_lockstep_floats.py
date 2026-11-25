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
import struct
import subprocess
import sys
from decimal import Decimal, getcontext
from fractions import Fraction

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import unix_mp  # noqa: E402

getcontext().prec = 200

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


# A Lua cart's numerals, and `tonumber`, as the Lua VM reads them: its
# one correctly rounded parser on every tier (native/moy_lua/
# moy_strtof.c), where newlib's strtof rounds through a double and parted a
# T-Deck from the wasm on literals near a float's halfway point. HARD are such
# literals: each lies just past the halfway point above a float, on the side a
# second rounding gets wrong, by far less than a double's half ulp.
def _f32(bits):
    return Fraction(struct.unpack("<f", struct.pack("<I", bits))[0])


def _hard(bits):
    lo, hi = _f32(bits), _f32(bits + 1)
    x = (lo + hi) / 2 + (hi - lo) / 2 ** 40 * (1 if bits % 2 == 0 else -1)
    return format(Decimal(x.numerator) / Decimal(x.denominator), ".29e")


def _numerals():
    out = ["1.00000005960464477550", "7.038531e-26", "1.4e-45", "3.4028235e38", "0.1",
           "16777217.0", "0x1.00000100000001p0", "0x1ff09030p-155", "1e-46", "0x.8p1"]
    seed = 12345
    for _ in range(48):
        seed = (seed * 1103515245 + 12345) & 0x7fffffff
        out.append(_hard(((100 + (seed >> 8) % 60) << 23) | (seed & 0x7fffff)))
    out += [_hard(b) for b in (0x3f800000, 0x4b7fffff, 0x00000004, 0x00400001, 0x7f7ffffe)]
    return out


def _exact(text):
    """The float nearest `text`'s value, ties to even: its bits."""
    if text.lower().startswith("0x"):
        m, _, e = text[2:].lower().partition("p")
        a, _, b = m.partition(".")
        x = Fraction(int(a + b, 16)) * Fraction(2) ** (int(e or 0) - 4 * len(b))
    else:
        x = Fraction(Decimal(text))
    near = struct.unpack("<I", struct.pack("<f", float(x)))[0] if x < 2 ** 128 else 0x7f800000
    best = min((c for c in (near - 1, near, near + 1) if 0 <= c < 0x7f800000),
               key=lambda c: (abs(x - _f32(c)), c & 1))
    return "%08x" % best


NUMERALS = _numerals()
LUA_NUMERALS = """
import moycore
from array import array
fb = bytearray(8 * 8 * 2)
snap = array("i", bytearray(4 * moycore.SNAP_LEN))
aq = array("i", bytearray(4 * (1 + moycore.AQ_SLOTS * moycore.AQ_MAX)))
pm = array("i", bytearray(4 * 256))
moycore.run_begin(fb, 8, 8, None, None, None, 0, 0, snap, aq, pm, None, None, True, None)
print("exec", moycore.exec(%r, "=numerals"))
moycore.pmem_image(pm)
moycore.close()
print("literal", " ".join("%%08x" %% (v & 0xffffffff) for v in pm[:%d]))
print("tonumber", " ".join("%%08x" %% (v & 0xffffffff) for v in pm[128:128 + %d]))
""" % ("local L = {%s}\nlocal T = {%s}\n" % (", ".join(NUMERALS),
                                            ", ".join('"%s"' % n for n in NUMERALS))
       + "for i = 1, #L do\n"
         "  pmem(i - 1, (string.unpack('<i4', string.pack('<f', L[i]))))\n"
         "  pmem(127 + i, (string.unpack('<i4', string.pack('<f', tonumber(T[i])))))\n"
         "end\n", len(NUMERALS), len(NUMERALS))


def test_a_lua_cart_s_numerals_are_one_float_in_the_browser_and_on_a_board(tmp_path):
    exe = unix_mp.require_unix_mp("moycore", board_model=True, why="the boards' floats")
    page = _wasm(tmp_path, LUA_NUMERALS)
    board = _board(str(exe), LUA_NUMERALS)
    assert board == page, "the R32 build and the wasm read a numeral apart:\n%s\n%s" % (
        board, page)
    rows = dict(line.split(" ", 1) for line in board)
    assert rows["exec"] == "None", rows["exec"]
    want = [_exact(n) for n in NUMERALS]
    # The numerals are hard: a double's rounding first parts most of them.
    twice = ["%08x" % struct.unpack("<I", struct.pack("<f", float(Decimal(n))))[0]
             for n in NUMERALS if not n.lower().startswith("0x")]
    assert sum(t != w for t, w in zip(twice, [_exact(n) for n in NUMERALS
                                              if not n.lower().startswith("0x")])) >= 50
    for kind in ("literal", "tonumber"):
        got = rows[kind].split()
        apart = [(n, g, w) for n, g, w in zip(NUMERALS, got, want) if g != w]
        assert len(got) == len(want) and not apart, (kind, apart)
