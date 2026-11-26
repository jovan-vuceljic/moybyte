"""The store's crash-safe write in C (native/moy_store, docs/history/kernel_store_2026-10.md
section 5), the one body every tier runs (runtime/carts/moy_fs.py names it).

  * the power-cut matrix: every scripted write sequence on oofatfs over a RAM
    card and littlefs2 over a RAM flash, cut at every block write, reads back
    as the version before or the version written, whole -- and the seeded
    random sequences with a random cut -- under ASan and UBSan;
  * the C store over POSIX through ctypes answers each case of the story and
    leaves no scratch behind;
  * the desktop MicroPython plays one session through moy_fs on a real folder.

tests/test_store_on_vfs.py runs the store on FAT and littlefs volumes under
the desktop MicroPython, where every write is the C store's.
"""

import ctypes
import os
import re
import subprocess

import pytest

from runtime import moy_fs
from runtime import native_parts
from tools import native_check
from unix_mp import require_unix_mp, runtime_tree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _no_toolchain(what):
    if os.environ.get("CI"):
        pytest.fail(what)
    pytest.skip(what)


def test_the_power_cut_matrix_holds_on_fat_and_littlefs():
    got = native_check.fuzz_matrix(native_parts.FS)
    if got is None:
        _no_toolchain("no sanitizer toolchain or no MicroPython tree "
                      "(make unix-micropython)")
    ok, secs, out = got
    assert ok, out[-4000:]
    assert "cuts, ok" in out, out
    # The FAT medium sits behind the card's read cache with every hit compared
    # with the card: the matrix is the cache's too, so it must have been hit.
    hits = re.search(r"card cache (\d+) hits checked", out)
    assert hits and int(hits.group(1)) > 0, out
    # ...and its zero runs (a new directory's cluster, cleared as one write):
    # every cut falls inside and between them too.
    runs = re.search(r"(\d+) zero runs", out)
    assert runs and int(runs.group(1)) > 0, out


def test_the_seeded_fuzz_runs_clean_under_the_sanitizers():
    if not os.path.isdir(os.path.join(native_parts.MPY, "lib", "oofatfs")):
        _no_toolchain("no MicroPython tree (make unix-micropython)")
    got = native_check.fuzz_seeded("c", seed=1, runs=300, comp=native_parts.FS)
    if got is None:
        _no_toolchain("no C compiler with AddressSanitizer here")
    ok, secs, out = got
    assert ok, out[-4000:]
    assert "300 programs" in out, out


# -- the C store over POSIX, through ctypes ----------------------------------------


class _Buf(ctypes.Structure):
    _fields_ = [("p", ctypes.c_void_p), ("n", ctypes.c_size_t)]


def _lib():
    san = os.environ.get("MOY_FS_SANITIZE") == "1"
    if san:
        path = native_parts.host_library("c", sanitize=True, comp=native_parts.FS)
    else:
        # The store's part alone, a library of this suite's own: its leak and
        # roots checks clear process-wide state the host's one library shares
        # with every other store user.
        from runtime import native_build
        path = native_build.build_parts("moy_fs_c", [native_parts.part(native_parts.FS)],
                                            native_parts.FS.cache)
    if path is None:
        _no_toolchain("no C compiler")
    lib = ctypes.CDLL(path)
    c, u32, sz = ctypes.c_char_p, ctypes.c_uint32, ctypes.c_size_t
    for name, args, res in (
            ("moy_fs_root", [c], ctypes.c_int),
            ("moy_fs_roots_clear", [], None),
            ("moy_fs_publish", [c, c, sz], ctypes.c_int),
            ("moy_fs_read", [c, c, ctypes.POINTER(_Buf)], ctypes.c_int),
            ("moy_fs_read_stamped", [c, ctypes.POINTER(_Buf)], ctypes.c_int),
            ("moy_fs_read_into", [c, ctypes.POINTER(_Sink)], ctypes.c_int),
            ("moy_fs_publish_from", [c, ctypes.POINTER(_Src)], ctypes.c_int),
            ("moy_fs_read_file", [c, sz, ctypes.POINTER(_Buf)], ctypes.c_int),
            ("moy_fs_write_bytes", [c, c, sz], ctypes.c_int),
            ("moy_fs_claim", [c, c, u32, u32], ctypes.c_int),
            ("moy_buf_free", [ctypes.POINTER(_Buf)], None),
            ("moy_store_host_live", [], ctypes.c_long)):
        fn = getattr(lib, name)
        fn.argtypes = args
        fn.restype = res
    return lib


class _CStore:
    """runtime/carts/moy_fs.py's calls over the C store."""

    def __init__(self, lib):
        self.lib = lib

    def _take(self, rc, b):
        if rc == -1:
            return None
        if rc:
            raise OSError(rc, os.strerror(rc))
        try:
            return ctypes.string_at(b.p, b.n).decode("utf-8")
        finally:
            self.lib.moy_buf_free(ctypes.byref(b))

    def set_publish_root(self, root):
        assert self.lib.moy_fs_root(root.encode()) == 0

    def publish(self, path, text):
        data = text.encode()
        rc = self.lib.moy_fs_publish(path.encode(), data, len(data))
        if rc:
            raise OSError(rc, os.strerror(rc))

    def read_recover(self, path):
        b = _Buf()
        return self._take(self.lib.moy_fs_read(path.encode(), None,
                                               ctypes.byref(b)), b)

    def read_stamped(self, path):
        b = _Buf()
        return self._take(self.lib.moy_fs_read_stamped(path.encode(),
                                                       ctypes.byref(b)), b)

    def claim(self, path, dest, stamp):
        return bool(self.lib.moy_fs_claim(path.encode(), dest.encode(), *stamp))


def _session(store, d):
    """One run of the store's cases in folder `d`: what each answered."""
    out = []
    root = os.path.join(d, "carts")
    cart = os.path.join(root, "a.moy")
    os.makedirs(os.path.join(cart, "journal"))
    store.set_publish_root(root)
    a = os.path.join(cart, "main.py")
    v1, v2 = "print('é')\n" * 40, "draw()\n" * 90
    store.publish(a, v1)
    out.append(("published", store.read_recover(a) == v1))
    store.publish(a, v2)
    with open(a, "w") as f:                 # the publish torn: a prefix
        f.write(v2[:100])
    out.append(("torn prefix", store.read_recover(a) == v2))
    with open(a) as f:
        out.append(("healed", f.read() == v2))
    with open(a, "w") as f:                 # someone else wrote it
        f.write("x" * len(v2))
    out.append(("foreign", store.read_recover(a) == "x" * len(v2),
                os.path.exists(moy_fs._native.bak_path(a))))
    store.publish(a, v1)
    dest = os.path.join(cart, "journal", "1")
    out.append(("claim", store.claim(a, dest, moy_fs._stamp_of(v1)),
                store.read_stamped(dest) == v1, os.path.exists(moy_fs._native.bak_path(a))))
    out.append(("claim wrong stamp", store.claim(a, dest + "x", (1, 2))))
    legacy = os.path.join(cart, "legacy")
    with open(legacy, "w") as f:
        f.write("old text\n")
    out.append(("legacy", store.read_stamped(legacy)))
    with open(legacy, "w"):
        pass
    out.append(("empty", store.read_stamped(legacy)))
    with open(legacy, "w") as f:
        f.write("#moyfs1 5 1\nhello")
    out.append(("torn bak", store.read_stamped(legacy)))
    gone = os.path.join(cart, "gone.py")
    store.publish(gone, v1)
    os.remove(gone)
    out.append(("missing", store.read_recover(gone) == v1, os.path.exists(gone)))
    try:
        store.read_recover(os.path.join(cart, "never.py"))
        out.append(("never", "read"))
    except OSError as e:
        out.append(("never", e.args[0]))
    return out


def test_the_c_store_answers_the_story_on_posix(tmp_path):
    lib = _lib()
    c = _session(_CStore(lib), str(tmp_path / "c"))
    lib.moy_fs_roots_clear()
    assert lib.moy_store_host_live() == 0
    assert c == [("published", True), ("torn prefix", True), ("healed", True),
                 ("foreign", True, False), ("claim", True, True, False),
                 ("claim wrong stamp", False), ("legacy", "old text\n"), ("empty", None),
                 ("torn bak", None), ("missing", True, True), ("never", 2)]


# -- the read into the caller's memory -----------------------------------------------


class _Sink(ctypes.Structure):
    pass


_BEGIN = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(_Sink), ctypes.c_size_t)
_ROOM = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.POINTER(_Sink), ctypes.POINTER(ctypes.c_size_t))
_TOOK = ctypes.CFUNCTYPE(None, ctypes.POINTER(_Sink), ctypes.c_size_t)
_Sink._fields_ = [("begin", _BEGIN), ("room", _ROOM), ("took", _TOOK)]


def _read_into(lib, path, piece=7, refuse_begin=0, room_for=None):
    """moy_fs_read_into with a sink that lends `piece` bytes at a time (a
    piece edge inside every line, a character, a stamp), refusing the begin
    with `refuse_begin` or room past `room_for` bytes: (rc, bytes), begins."""
    got, begins = bytearray(), []
    scratch = ctypes.create_string_buffer(piece)

    def begin(_k, n):
        begins.append(n)
        got.clear()
        return refuse_begin

    def room(_k, n):
        if room_for is not None and len(got) >= room_for:
            return None
        n[0] = piece
        return ctypes.addressof(scratch)

    def took(_k, n):
        got.extend(scratch.raw[:n])

    sink = _Sink(_BEGIN(begin), _ROOM(room), _TOOK(took))
    rc = lib.moy_fs_read_into(path.encode(), ctypes.byref(sink))
    return (rc, bytes(got) if rc == 0 else None), begins


def _read_whole(lib, path):
    b = _Buf()
    rc = lib.moy_fs_read(path.encode(), None, ctypes.byref(b))
    if rc:
        return rc, None
    try:
        return 0, ctypes.string_at(b.p, b.n)
    finally:
        lib.moy_buf_free(ctypes.byref(b))


V1, V2 = "print('é')\n" * 40, "draw()\n" * 90
BIG = "".join("line %d of a file longer than a piece\n" % i for i in range(160))
MULTI = "# café — über\nprint('✓')\n" * 30


def _put(path, data):
    with open(path, "wb") as f:
        f.write(data.encode() if isinstance(data, str) else data)


def _pub(lib, path, text):
    data = text.encode()
    assert lib.moy_fs_publish(path.encode(), data, len(data)) == 0


def _bak(text):
    return moy_fs._stamp_line(text) + text


# Each state a cut or a foreign write leaves, built in folder `d` for the file
# `p`: (whether `d` is a publish root, the build).
READ_STATES = {
    "published": (True, lambda lib, p: _pub(lib, p, V1)),
    "published, no root": (False, lambda lib, p: _pub(lib, p, V1)),
    "torn prefix": (True, lambda lib, p: (_pub(lib, p, V1), _pub(lib, p, V2), _put(p, V2[:100]))),
    "torn at a piece's edge": (True, lambda lib, p: (_pub(lib, p, V1), _pub(lib, p, BIG),
                                                    _put(p, BIG[:128]))),
    "torn past a piece's edge": (True, lambda lib, p: (_pub(lib, p, V1), _pub(lib, p, BIG),
                                                      _put(p, BIG[:2049]))),
    "torn to nothing": (True, lambda lib, p: (_pub(lib, p, V1), _pub(lib, p, V2), _put(p, ""))),
    "torn prefix, no root": (False, lambda lib, p: (_pub(lib, p, V2), _put(p, V2[:333]))),
    "torn inside a character": (True, lambda lib, p: (_pub(lib, p, MULTI),
                                                     _put(p, MULTI.encode()[:5]))),
    "foreign, same length": (True, lambda lib, p: (_pub(lib, p, V2), _put(p, "x" * len(V2)))),
    "foreign, longer": (False, lambda lib, p: (_pub(lib, p, V2), _put(p, V2 + "more\n"))),
    "foreign, a prefix and then not": (True, lambda lib, p: (_pub(lib, p, BIG),
                                                            _put(p, BIG[:300] + "Z"))),
    "torn backup": (True, lambda lib, p: (_pub(lib, p, V1), _pub(lib, p, V2), _put(p, V1),
                                          _put(moy_fs._native.bak_path(p), _bak(V2)[:-6]))),
    "crash between the writes": (False, lambda lib, p: (_pub(lib, p, V1),
                                                        _put(moy_fs._native.bak_path(p), _bak(V2)))),
    "missing": (True, lambda lib, p: (_pub(lib, p, V1), os.remove(p))),
    "missing, no root": (False, lambda lib, p: (_pub(lib, p, BIG), os.remove(p))),
    "missing, torn backup": (False, lambda lib, p: (_pub(lib, p, V1), os.remove(p),
                                                    _put(moy_fs._native.bak_path(p), _bak(V1)[:20]))),
    "missing, legacy backup": (False, lambda lib, p: _put(moy_fs._native.bak_path(p), "old text\n")),
    "missing, a line like a stamp": (False, lambda lib, p: _put(moy_fs._native.bak_path(p), "#moyfs1 nope\n" + V1)),
    "missing, empty backup": (False, lambda lib, p: _put(moy_fs._native.bak_path(p), "")),
    "never": (False, lambda lib, p: None),
    "legacy backup beside the file": (False, lambda lib, p: (_put(p, V2), _put(moy_fs._native.bak_path(p), V1))),
    "empty payload": (True, lambda lib, p: _pub(lib, p, "")),
    "empty payload, missing": (False, lambda lib, p: (_pub(lib, p, ""), os.remove(p))),
}


def _state(lib, d, name):
    rooted, build = READ_STATES[name]
    os.makedirs(d)
    lib.moy_fs_roots_clear()
    if rooted:
        lib.moy_fs_root(d.encode())
    p = os.path.join(d, "main.py")
    build(lib, p)
    lib.moy_fs_roots_clear()                # a boot: the marker read from the medium
    if rooted:
        lib.moy_fs_root(d.encode())
    return p


def _tree(d):
    out = {}
    for name in sorted(os.listdir(d)):
        with open(os.path.join(d, name), "rb") as f:
            out[name] = f.read().replace(d.encode(), b"@")
    return out


@pytest.mark.parametrize("name", sorted(READ_STATES))
def test_the_read_into_answers_as_the_whole_read_does(tmp_path, name):
    """moy_fs_read_into is moy_fs_read without the store's copy: on every
    state the story names it answers the same bytes or error, heals the same
    way and leaves the same files, and so does the read after it."""
    lib = _lib()
    seen = {}
    for kind in ("whole", "into"):
        p = _state(lib, str(tmp_path / kind), name)
        if kind == "whole":
            first, second = _read_whole(lib, p), _read_whole(lib, p)
        else:
            (first, begins), (second, _b) = _read_into(lib, p), _read_into(lib, p)
            assert len(begins) <= 2
        seen[kind] = (first, second, _tree(str(tmp_path / kind)))
    lib.moy_fs_roots_clear()
    assert lib.moy_store_host_live() == 0
    assert seen["into"] == seen["whole"]


def test_a_refusing_sink_is_answered_and_heals_nothing(tmp_path):
    lib = _lib()
    p = _state(lib, str(tmp_path / "d"), "torn prefix")
    (got, begins) = _read_into(lib, p, refuse_begin=27)
    assert got == (27, None) and begins == [len(V2[:100])]
    (got, _b) = _read_into(lib, p, room_for=10)
    assert got == (12, None)
    with open(p) as f:
        assert f.read() == V2[:100]         # neither read took the file for unreadable
    (got, begins) = _read_into(lib, p)
    assert got == (0, V2.encode()) and begins == [100, len(V2)]
    lib.moy_fs_roots_clear()
    assert lib.moy_store_host_live() == 0


# -- the publish from pieces ---------------------------------------------------------


class _Src(ctypes.Structure):
    pass


_NEXT = ctypes.CFUNCTYPE(ctypes.c_size_t, ctypes.POINTER(_Src), ctypes.POINTER(ctypes.c_void_p))
_REWIND = ctypes.CFUNCTYPE(None, ctypes.POINTER(_Src))
_Src._fields_ = [("next", _NEXT), ("rewind", _REWIND)]


def _publish_pieces(lib, path, text, piece):
    """moy_fs_publish_from over `text` in pieces of `piece` bytes: rc, rewinds."""
    data = text.encode()
    bufs = [ctypes.create_string_buffer(data[i:i + piece], len(data[i:i + piece]))
            for i in range(0, len(data), piece)]
    at, rewinds = [0], [0]

    def nxt(_s, p):
        if at[0] >= len(bufs):
            return 0
        b = bufs[at[0]]
        at[0] += 1
        p[0] = ctypes.addressof(b)
        return len(b)

    def rewind(_s):
        at[0] = 0
        rewinds[0] += 1

    src = _Src(_NEXT(nxt), _REWIND(rewind))
    return lib.moy_fs_publish_from(path.encode(), ctypes.byref(src)), rewinds[0]


@pytest.mark.parametrize("piece", (1, 7, 1000))
def test_a_publish_from_pieces_writes_what_the_whole_one_writes(tmp_path, piece):
    """The editor saves its blocks without a copy of them: the marker, the
    stamped backup and the file are byte for byte the one-buffer publish's,
    so every state a cut leaves is one the whole publish leaves too, and the
    power-cut matrix (whose publishes are this path over one piece) holds
    for it."""
    lib = _lib()
    trees = []
    for kind in ("whole", "pieces"):
        d = str(tmp_path / kind)
        os.makedirs(d)
        lib.moy_fs_roots_clear()
        lib.moy_fs_root(d.encode())
        p = os.path.join(d, "main.py")
        _pub(lib, p, V1)
        if kind == "whole":
            _pub(lib, p, MULTI)
        else:
            assert _publish_pieces(lib, p, MULTI, piece) == (0, 3)
        trees.append(_tree(d))
    lib.moy_fs_roots_clear()
    assert lib.moy_store_host_live() == 0
    assert trees[0] == trees[1]


def test_every_cut_of_a_publish_from_pieces_reads_back_whole(tmp_path):
    """The writes a publish makes, in order -- the marker, the stamped
    backup, the file -- cut at every byte, over a file published before:
    both readers give the version before or the one written, whole, and the
    one written wherever the cut fell in the file."""
    lib = _lib()
    ref = str(tmp_path / "ref")
    os.makedirs(ref)
    lib.moy_fs_roots_clear()
    lib.moy_fs_root(ref.encode())
    _pub(lib, os.path.join(ref, "main.py"), V1)
    before = _tree(ref)
    assert _publish_pieces(lib, os.path.join(ref, "main.py"), V2, 7) == (0, 3)
    after = _tree(ref)
    old, new = V1.encode(), V2.encode()
    cuts = ([("marker", k) for k in range(len(after[".publish"]) + 1)]
            + [("backup", k) for k in range(len(after[".main.py.moybak"]) + 1)]
            + [("file", k) for k in range(len(new) + 1)])
    for n, (where, k) in enumerate(cuts):
        for read in ("whole", "into"):
            d = str(tmp_path / ("%d%s" % (n, read)))
            os.makedirs(d)
            state = dict(before)
            if where == "marker":
                state[".publish"] = after[".publish"][:k]
            else:
                state[".publish"] = after[".publish"]
                state[".main.py.moybak"] = after[".main.py.moybak"][:k] if where == "backup" else after[".main.py.moybak"]
                if where == "file":
                    state["main.py"] = after["main.py"][:k]
            for name, data in state.items():
                _put(os.path.join(d, name), data.replace(b"@", d.encode()))
            lib.moy_fs_roots_clear()
            lib.moy_fs_root(d.encode())
            p = os.path.join(d, "main.py")
            rc, got = _read_whole(lib, p) if read == "whole" else _read_into(lib, p)[0]
            assert rc == 0 and got in (old, new), (where, k, read, got)
            if where == "file":
                assert got == new, (where, k, read)
    lib.moy_fs_roots_clear()
    assert lib.moy_store_host_live() == 0


# -- the desktop MicroPython over the native module ----------------------------------

VM_SESSION = r'''
import os, sys
sys.path.insert(0, @RUNTIME@)
import moy_fs
D = @DIR@
print("native", moy_fs._native.__name__)
root = D + "/carts"
cart = root + "/a.moy"
for p in (root, cart, cart + "/journal"):
    moy_fs._mkdir(p)
moy_fs.set_publish_root(root)
a = cart + "/main.py"
v1, v2 = "print('é')\n" * 40, "draw()\n" * 90
moy_fs._write_atomic(a, v1)
print("published", moy_fs._read_recover(a) == v1, moy_fs._bak_stamp(a))
moy_fs._write_atomic(a, v2)
with open(a, "w") as f:
    f.write(v2[:100])
print("torn", moy_fs._read_recover(a) == v2, moy_fs._read(a) == v2)
os.chdir(cart)
print("at", moy_fs._read_recover(a, "main.py") == v2)
os.chdir(D)
dest = cart + "/journal/1"
print("claim", moy_fs._claim_bak(a, dest, moy_fs._stamp_of(v2)),
      moy_fs._read_stamped(dest) == v2, moy_fs._exists(moy_fs._native.bak_path(a)))
b = cart + "/sprites.moygfx"
moy_fs._write_bytes(b, b"\x00\x01" * 300)
print("bytes", moy_fs._read_bytes(b, 600) == b"\x00\x01" * 300,
      moy_fs._read_bytes(b, 599))
moy_fs._remove(b)
print("removed", moy_fs._exists(b))
try:
    moy_fs._read(cart + "/never")
except OSError as e:
    print("never", e.args[0])
'''


def _vm_session(cmd, d):
    script = (VM_SESSION.replace("@RUNTIME@", repr(runtime_tree()))
              .replace("@DIR@", repr(str(d))))
    os.makedirs(str(d))
    out = subprocess.run(cmd + ["-c", script], capture_output=True, text=True,
                         timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout.splitlines()


def test_the_vm_store_is_the_native_one(tmp_path):
    exe = require_unix_mp(
        "moy_store",
        why="the store's file verbs on the VM a board runs, over the native "
            "module (docs/history/kernel_store_2026-10.md section 10, slice 2).")
    assert _vm_session([exe], tmp_path / "vm") == [
        "native moy_store", "published True (440, 2817393964)", "torn True True", "at True",
        "claim True True False", "bytes True None", "removed False", "never 2"]
