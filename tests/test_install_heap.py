"""A Zero's install fits a C3's Python heap: run on the boards' model of
MicroPython (32-bit words, REPR_C), the board's whole install of one cart
from a release-sized index (web_addon.OfficialCarts: the entry read as the
index streams, its signature checked over the digest, the asset read by
range, the buffers sized to the heap) lands with INSTALL_BOUND bytes of
heap free when it starts, while reading that index whole (cart_index.Fetch
and parse_index, what the install did before) does not. Its cart's entry is
as large as Jet Teapot's in moybyte-org/carts' index, and that entry's read
alone fits ENTRY_BOUND, the heap a C3 has beside a page's session.

The bound is a C3's: its Python heap is 47 KB in all and the board's own
check measured about 44 KB free at rest on glass (#41). The heap a run
leaves free is set by a ballast of small blocks, so what the install has is
the heap a board's has after its own allocations: free, but in pieces."""

import json
import os
import subprocess

import pytest

from cart_store_fixtures import Repo
from test_ota_signing import TEST_KEYS
from test_pkg import _sign

INSTALL_BOUND = 32 * 1024
# The entry's read alone, Jet Teapot's: a C3 has 24.4 KB of Python heap free
# beside a page's session (#276), where the whole entry, parsed, ran it out.
ENTRY_BOUND = 24 * 1024
INDEX_BYTES = 46 * 1024            # the C3 release's own index, carts-c3_zero.json
TEAPOT_ENTRY = 6152                # Jet Teapot's entry as moybyte-org/carts' index serves it
BASE = "https://heap.example/carts"

_SCRIPT = r'''
import sys, os, json, gc
sys.path.insert(0, %(runtime)r)
import cart_index as ci, cart_unpack, web_addon, moy_carts, rsa_check, app_imports
import hashlib, binascii

KEYS = %(keys)r
files = json.load(open(%(map)r))


class V:
    @staticmethod
    def ota_verify_digest(digest, sig, keys=None):
        return rsa_check.verify_digest(digest, sig, keys or KEYS)


ci._native = lambda: V


class R:
    def __init__(s, path, span=None):
        s.f = open(path, "rb")
        s.left = os.stat(path)[6]
        s.status = 200
        if span is not None:
            s.f.seek(span[0])
            s.left = span[1]
            s.status = 206
        s.length = s.left

    def readinto(s, mv):
        if not s.left:
            return 0
        n = s.f.readinto(memoryview(mv)[:min(len(mv), s.left)])
        s.left -= n
        return n

    def close(s):
        s.f.close()


class Net:
    ranges = True

    def ready(s):
        return True

    def open(s, url, span=None):
        return R(files[url], span)


class Inst:
    def net(s): return NET
    def root(s): return ROOT
    def op(s, fn): return fn()
    def chip(s): return "esp32s3", "2"
    def hold(s): return True
    def release(s): pass
    def rescan(s, folder=None): pass


NET = Net()
ROOT = %(root)r
URL = %(index_url)r
FOLDER = %(folder)r


def install():
    oc = web_addon.OfficialCarts(Inst(), URL, sources=lambda root, own: [URL])
    ok, why = oc.request("install", FOLDER, {"index": URL})
    assert ok, why
    while oc.step(1000):
        pass
    if oc.state == "installing":
        oc._agree()
        while oc.step(1000):
            pass
    return oc.error


def whole():
    f = ci.index_fetch(NET, URL)
    while f.step():
        pass
    got = [c for c in ci.parse_index(f.data, URL) if c["folder"] == FOLDER]
    return None if got else "not found"


def stream():
    e = ci.EntryRead(NET, URL, FOLDER)
    while e.step():
        pass
    return None if e.carts else "none"


def tidy():
    if FOLDER in os.listdir(ROOT):
        ci.remove(ROOT, FOLDER)


def attempt(fn, k):
    tidy()
    gc.collect()
    ballast = None
    try:
        while gc.mem_free() > k + 256:
            ballast = (bytearray(200), ballast)     # a chain: no list to grow
        try:
            err = fn()
        except MemoryError:
            err = "MemoryError"
    finally:
        ballast = None
        gc.collect()
    return err


def least(fn, lo, hi, step):
    """The least free heap, to `step`, `fn` succeeds with."""
    while hi - lo > step:
        mid = (lo + hi) // 2
        if attempt(fn, mid) is None:
            hi = mid
        else:
            lo = mid
    return hi


assert install() is None
assert whole() is None
print("BOUND", attempt(install, %(bound)d), attempt(whole, %(bound)d),
      attempt(stream, %(entry_bound)d))
if %(measure)r:
    print("LEAST", least(install, 2048, 200000, 512), least(whole, 2048, 400000, 512))
    print("PARTS", least(stream, 1024, 200000, 256))
'''


def _teapot_sized(entry):
    """`entry` grown to Jet Teapot's in moybyte-org/carts' index, where its
    build record (each chip's module key and the pins it was built at), its
    source bundle and its links are most of it, and an install reads none."""
    entry["source_asset"] = {"name": "target-v1-source.tar.gz", "size": 255162,
                             "url": BASE + "/releases/download/target-v1/target-v1-source.tar.gz",
                             "sha256": "0" * 64}
    key = "format 2\ntarget riscv32\ncpu generic-rv32\nabi ilp32f\nfeatures +m,+a,+f,+c\n" \
          "opt 3\nsize 3\nbounds 1\nstack-bounds 1\nxip 0\n"
    build = {"commit": "0" * 40, "keys": {"esp32p4": key, "esp32s3": key},
             "modules": dict((chip, {"name": "main.%s.f2.aot" % chip, "unsigned_size": 269377,
                                     "unsigned_sha256": "0" * 64})
                             for chip in ("esp32p4", "esp32s3")),
             "pins": {}}
    entry["build"] = build
    while len(json.dumps({"carts": [entry]}, indent=2)) < TEAPOT_ENTRY:
        build["pins"]["pin%d" % len(build["pins"])] = {
            "commit": "0" * 40, "url": "https://github.com/moybyte-org/x/tree/" + "0" * 40,
            "note": "the runtime the modules are keyed for; a board built for another refuses them"}


def _repo(base=BASE):
    """A release-sized index as moybyte-org/carts writes it (indented): the
    cart installed, a compiled one with two chips' modules and a 40 KB file
    whose entry is as large as Jet Teapot's, among enough others to make the
    index as large as the C3's release index."""
    repo = Repo(base)
    repo.add("target", name="Target", extra={"level.bin": os.urandom(40000)})
    _teapot_sized(repo.carts[-1])
    n = 0
    while len(_indented(repo)) < INDEX_BYTES:
        n += 1
        repo.add("filler_%02d" % n, extra=dict(("f%d.bin" % i, b"x" * 64) for i in range(20)))
    repo.files["index.json"] = _sign(_indented(repo))
    return repo


def _indented(repo):
    return json.dumps(json.loads(repo.index()), indent=2).encode() + b"\n"


def _run(tmp_path, measure=False, bound=INSTALL_BOUND):
    from unix_mp import require_unix_mp, runtime_tree
    exe = require_unix_mp(board_model=True, why="a board's heap is the boards' model's")
    repo = _repo()
    data = tmp_path / "data"
    data.mkdir()
    url_map = {}
    for i, (url, blob) in enumerate(repo.routes().items()):
        p = data / ("f%d" % i)
        p.write_bytes(blob)
        url_map[url] = str(p)
    (tmp_path / "map.json").write_text(json.dumps(url_map))
    root = tmp_path / "moy" / "carts"
    root.mkdir(parents=True)
    script = tmp_path / "run.py"
    script.write_text(_SCRIPT % {
        "runtime": runtime_tree(), "map": str(tmp_path / "map.json"), "keys": TEST_KEYS,
        "index_url": repo.url("index.json"), "root": str(root),
        "folder": "target.moy", "bound": bound, "entry_bound": ENTRY_BOUND,
        "measure": measure})
    out = subprocess.run([exe, "-X", "heapsize=2M", str(script)], capture_output=True,
                         text=True, timeout=600)
    assert out.returncode == 0, out.stdout + out.stderr
    return dict((ln.split()[0], ln.split()[1:]) for ln in out.stdout.splitlines()
                if ln.startswith(("BOUND", "LEAST", "PARTS")))


def test_an_install_fits_the_heap_a_c3_has_and_reading_the_index_whole_does_not(tmp_path):
    got = _run(tmp_path)
    assert got["BOUND"][0] == "None", got
    assert got["BOUND"][1] != "None", "the whole index fits the bound: it proves nothing"
    assert got["BOUND"][2] == "None", got


@pytest.mark.skipif(not os.environ.get("MOYBYTE_HEAP_MEASURE"),
                    reason="a measurement: MOYBYTE_HEAP_MEASURE=1 prints the least heap each needs")
def test_measure_the_least_heap_an_install_needs(tmp_path):
    got = _run(tmp_path, measure=True)
    print("least free heap: install %s, the index read whole %s" % tuple(got["LEAST"]))
    print("least free heap: the entry read alone %s" % tuple(got["PARTS"]))
