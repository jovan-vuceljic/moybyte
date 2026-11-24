# A Python cart's lockstep simulation, the same on every VM that runs it:
# the console's own cart namespace (cart_api.make_api) over a canvas that
# draws nothing, two players' held buttons from an integer stream, a fixed
# tick, and the world digest a match compares (players.world_text), printed
# every frame as `frame crc32`. tests/test_web_lockstep_floats.py prepends
# the cart (SRC, MAP, CONFIG, SEED, FRAMES) and runs it in the browser's VM
# and the host's board-model one. Imports are bare, as a board freezes them.
import binascii
import random

from cart_api import make_api
from editors_sheet import TileMap
from players import world_text

BUTTONS = ("left", "right", "up", "down", "a", "b")


class _Canvas:
    w, h = 320, 240

    def __getattr__(self, name):
        return _nothing


def _nothing(*a, **k):
    return 0


class _Input:
    """Both players' held buttons this frame, and the last frame's."""

    def __init__(self):
        self.now = [(), ()]
        self.was = [(), ()]
        self.players = self

    def held(self, name, p=0):
        return name in self.now[p]

    def pressed(self, name, p=0):
        return name in self.now[p] and name not in self.was[p]

    def count(self):
        return 2


def run(src, map_text, config, seed, frames, dt):
    inp = _Input()
    tm = TileMap.from_hex(map_text) if map_text else TileMap()
    ns = make_api(_Canvas(), inp, config, tilemap=tm)
    for name in ("award", "progress"):
        ns.setdefault(name, _nothing)
    random.seed(seed)
    exec(compile(src, "<cart>", "exec"), ns)
    ns["_init"]()
    kid = seed & 0x7FFFFFFF
    for f in range(frames):
        inp.was = inp.now
        held = []
        for p in (0, 1):
            kid = (kid * 1103515245 + 12345) & 0x7FFFFFFF
            held.append(tuple(b for i, b in enumerate(BUTTONS) if (kid >> (8 + i)) & 1))
        inp.now = held
        ns["_update"](dt)
        ns["_draw"]()
        print(f, binascii.crc32(world_text(ns).encode()))


run(SRC, MAP, CONFIG, SEED, FRAMES, 1 / 30)  # noqa: F821 -- prepended
