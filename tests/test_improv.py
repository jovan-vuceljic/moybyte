"""Improv's frame parser, the C a Zero's console runs every byte through
(native/moy_kernel/moy_improv.c), compiled for the host and driven by
ctypes: every command a client sends, a frame split across reads, the
REPL's bytes passed on untouched and in order, and the frames the board
answers with."""

import ctypes
import os

import pytest

from runtime.host import native_build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KERNEL = os.path.join(ROOT, "native", "moy_kernel")
HOLD_MS, FRAME_MS, HOLD = 30, 1000, 8


class Rx(ctypes.Structure):
    _fields_ = [("at", ctypes.c_uint8), ("type", ctypes.c_uint8), ("len", ctypes.c_uint8),
                ("sum", ctypes.c_uint8), ("nl", ctypes.c_uint8), ("last", ctypes.c_uint32),
                ("data", ctypes.c_uint8 * 255)]


FRAME_FN = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int,
                            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t)


@pytest.fixture(scope="module")
def lib():
    part = native_build.Part("moy_improv", ["moy_improv.h", "moy_improv.c"], KERNEL)
    path = native_build.build_parts("moy_improv", [part],
                                    os.path.join(ROOT, ".build", "moy_improv_c"))
    if path is None:
        pytest.skip(native_build.explain_no_cc())
    return native_build.load_cdll(path, (
        ("moy_improv_feed", [ctypes.POINTER(Rx), ctypes.c_char_p, ctypes.c_size_t,
                             ctypes.c_uint32, ctypes.c_char_p, FRAME_FN, ctypes.c_void_p],
         ctypes.c_size_t),
        ("moy_improv_tick", [ctypes.POINTER(Rx), ctypes.c_uint32, ctypes.c_char_p],
         ctypes.c_size_t),
        ("moy_improv_busy", [ctypes.POINTER(Rx)], ctypes.c_int),
        ("moy_improv_frame", [ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t,
                              ctypes.c_char_p], ctypes.c_size_t),
    ))


class Port:
    """One console's parser: bytes in, the REPL's bytes and the frames out."""

    def __init__(self, lib):
        self.lib, self.rx, self.frames, self.repl = lib, Rx(), [], b""
        self._fn = FRAME_FN(lambda _c, t, d, n: self.frames.append((t, bytes(d[:n]))))

    def feed(self, data, now=0):
        out = ctypes.create_string_buffer(len(data) + HOLD)
        n = self.lib.moy_improv_feed(ctypes.byref(self.rx), data, len(data), now, out,
                                     self._fn, None)
        self.repl += out.raw[:n]

    def tick(self, now):
        out = ctypes.create_string_buffer(HOLD)
        n = self.lib.moy_improv_tick(ctypes.byref(self.rx), now, out)
        self.repl += out.raw[:n]


def frame(lib, kind, data):
    out = ctypes.create_string_buffer(len(data) + 11)
    n = lib.moy_improv_frame(kind, data, len(data), out)
    return out.raw[:n]


def rpc(lib, cmd, data=b""):
    return frame(lib, 0x03, bytes([cmd, len(data)]) + data)


def wifi(ssid, pw):
    return bytes([len(ssid)]) + ssid + bytes([len(pw)]) + pw


def test_a_frame_is_improvs_layout(lib):
    """The layout the SDKs read: header, version 1, type, length, data, the
    low byte of the sum of everything before it, and a newline."""
    f = frame(lib, 0x01, b"\x02")
    body = b"IMPROV\x01\x01\x01\x02"
    assert f == body + bytes([sum(body) & 0xFF]) + b"\n"
    assert lib.moy_improv_frame(4, b"x" * 256, 256, ctypes.create_string_buffer(300)) == 0


@pytest.mark.parametrize("cmd,data", [
    (0x01, wifi(b"home", b"secret123")),
    (0x02, b""), (0x03, b""), (0x04, b""),
    (0x05, b"\x07kitchen"), (0x06, b"\x07kitchen"), (0x07, b""),
])
def test_every_command_arrives_whole_and_none_reaches_the_repl(lib, cmd, data):
    p = Port(lib)
    p.feed(rpc(lib, cmd, data))
    assert p.frames == [(0x03, bytes([cmd, len(data)]) + data)]
    assert p.repl == b""
    assert not lib.moy_improv_busy(ctypes.byref(p.rx))


def test_a_frame_split_across_reads_byte_by_byte(lib):
    p = Port(lib)
    f = rpc(lib, 0x01, wifi(b"a network", b"its password"))
    for i, b in enumerate(f):
        p.feed(bytes([b]), now=i)
    assert p.frames == [(0x03, f[9:-2])]
    assert p.repl == b""


def test_a_frame_split_at_every_point(lib):
    f = rpc(lib, 0x03)
    for cut in range(1, len(f)):
        p = Port(lib)
        p.feed(f[:cut])
        p.feed(f[cut:])
        assert p.frames == [(0x03, b"\x03\x00")], cut
        assert p.repl == b"", cut


def test_repl_bytes_pass_untouched_around_frames(lib):
    """Typing, a Ctrl-C and text that starts like the header all reach the
    REPL in order; the frames between them do not."""
    p = Port(lib)
    p.feed(b"print('IMP')\r\x03")
    p.feed(rpc(lib, 0x02) + b"IMPORT\r" + rpc(lib, 0x03) + b"IIMPRO")
    assert p.repl == b"print('IMP')\r\x03IMPORT\rI"
    assert [f[1][0] for f in p.frames] == [0x02, 0x03]
    p.feed(b"VED")                   # "IMPROV" then 'E': not version 1
    assert p.repl == b"print('IMP')\r\x03IMPORT\rIIMPROVED"


def test_a_held_header_goes_to_the_repl_once_it_is_stale(lib):
    """A person typing 'IM' at the REPL sees it after HOLD_MS, not never."""
    p = Port(lib)
    p.feed(b"IM", now=100)
    assert p.repl == b""
    p.tick(100 + HOLD_MS - 1)
    assert p.repl == b""
    p.tick(100 + HOLD_MS)
    assert p.repl == b"IM"
    assert not lib.moy_improv_busy(ctypes.byref(p.rx))


def test_the_rpc_type_never_reaches_the_repl_and_a_cut_frame_is_dropped(lib):
    """0x03 is Ctrl-C to the REPL: a frame cut short is dropped whole after
    FRAME_MS of quiet, its bytes the REPL's never."""
    p = Port(lib)
    p.feed(rpc(lib, 0x03)[:9], now=0)
    p.tick(FRAME_MS - 1)
    assert lib.moy_improv_busy(ctypes.byref(p.rx))
    p.tick(FRAME_MS)
    assert not lib.moy_improv_busy(ctypes.byref(p.rx))
    assert p.repl == b"" and p.frames == []
    p.feed(rpc(lib, 0x02), now=FRAME_MS + 1)
    assert p.frames == [(0x03, b"\x02\x00")]


def test_a_bad_checksum_is_handed_on_as_bad(lib):
    p = Port(lib)
    f = bytearray(rpc(lib, 0x02))
    f[-2] ^= 0xFF
    p.feed(bytes(f))
    assert p.frames == [(-1, b"\x02\x00")]
    assert p.repl == b""


def test_two_frames_in_one_read_and_their_newlines(lib):
    p = Port(lib)
    p.feed(rpc(lib, 0x02) + rpc(lib, 0x03) + b"\n")
    assert [f[1][0] for f in p.frames] == [0x02, 0x03]
    assert p.repl == b"\n"           # only the newline right after a frame is its own
