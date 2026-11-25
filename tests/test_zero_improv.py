"""Improv over the cable, the Zero's end (device/zero_improv.py): a client's
frames through the kernel's real parser (native/moy_kernel/moy_improv.c,
compiled for the host as in test_improv.py), answered by the store host's
module, the answer framed by the same C and read back as a client reads it.
And the setup access point's loop handing a join over the cable to the
serving board without a reset (zero_setup.run)."""

import ctypes
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "device"))

import zero_improv as zi  # noqa: E402
import zero_setup  # noqa: E402
from test_improv import Port, frame, lib, rpc, wifi  # noqa: E402,F401

BOARD_ID, CLAIM = "ab" * 16, "cd" * 16


class Cable:
    """The board's end of the cable: client bytes through the C parser in,
    frames out through the C encoder, read back into (type, data)."""

    def __init__(self, lib):
        self.lib, self.rx, self.out = lib, Port(lib), b""

    def write(self, data):
        self.rx.feed(data)

    def take(self):
        return self.rx.frames.pop(0) if self.rx.frames else None

    def send(self, kind, data):
        self.out += frame(self.lib, kind, bytes(data))

    def read(self):
        """The frames the board sent, as a client parses them."""
        got, out = [], self.out
        self.out = b""
        while out:
            at = out.index(b"IMPROV")
            n = out[at + 8]
            body = out[at:at + 9 + n]
            assert out[at + 9 + n] == sum(body) & 0xFF and out[at + 10 + n] == 10
            got.append((out[at + 7], out[at + 9:at + 9 + n]))
            out = out[at + 11 + n:]
        return got


def strings(data):
    """An RPC result's (command, [strings])."""
    out, body, at = [], data[2:], 0
    assert data[1] == len(body)
    while at < len(body):
        n = body[at]
        out.append(body[at + 1:at + 1 + n].decode())
        at += 1 + n
    return data[0], out


class Board:
    def __init__(self, ip=None, joins=True, claim=CLAIM):
        self._ip, self.joins, self.claim = ip, joins, claim
        self.saved, self.named, self.minted = [], "moybyte-zero", 0

    def info(self):
        return "v0.16-beta.3", "ESP32-S3"

    def name(self):
        return self.named

    def rename(self, raw):
        name = zero_setup.clean_name(raw)
        if name:
            self.named = name
        return name or None

    def scan(self):
        return [("home", -60, True), ("cafe", -70, False), ("home", -40, True), ("", -30, False)]

    def join(self, ssid, pw):
        if self.joins:
            self._ip = "192.168.1.57"
        return self._ip if self.joins else None

    def save(self, ssid, pw):
        self.saved.append((ssid, pw))

    def ip(self):
        return self._ip

    def address(self, fresh=False):
        if fresh:
            self.minted += 1
            return BOARD_ID, "%032x" % self.minted
        return BOARD_ID, self.claim


def ask(lib, imp, cable, cmd, data=b""):
    cable.write(rpc(lib, cmd, data))
    assert imp.poll() == 1
    return cable.read()


def test_a_fresh_board_on_its_access_point_is_ready_and_says_who_it_is(lib):
    cable, board = Cable(lib), Board()
    imp = zi.Improv(cable, board, serving=False)
    assert ask(lib, imp, cable, zi.CURRENT) == [(zi.ERROR, b"\x00"), (zi.STATE, b"\x02")]
    got = ask(lib, imp, cable, zi.INFO)
    assert strings(got[1][1]) == (zi.INFO, ["Moybyte", "v0.16-beta.3", "ESP32-S3",
                                            "moybyte-zero"])


def test_the_scan_is_each_network_once_strongest_first_then_an_empty_result(lib):
    cable = Cable(lib)
    imp = zi.Improv(cable, Board(), serving=False)
    got = ask(lib, imp, cable, zi.SCAN)
    assert [strings(d) for k, d in got if k == zi.RESULT] == [
        (zi.SCAN, ["home", "-40", "YES"]), (zi.SCAN, ["cafe", "-70", "NO"]), (zi.SCAN, [])]


def test_a_join_while_serving_answers_both_addresses_with_the_id_and_the_claim(lib):
    cable, board = Cable(lib), Board()
    imp = zi.Improv(cable, board, serving=True)
    board.rename("Kitchen")
    got = ask(lib, imp, cable, zi.WIFI, wifi(b"home", b"its password"))
    assert got[:3] == [(zi.ERROR, b"\x00"), (zi.STATE, b"\x03"), (zi.STATE, b"\x04")]
    tail = "#id=%s&claim=%s" % (BOARD_ID, CLAIM)
    assert strings(got[3][1]) == (zi.WIFI, ["http://192.168.1.57/" + tail,
                                            "http://kitchen.local/" + tail])
    assert board.saved == [("home", "its password")]
    again = ask(lib, imp, cable, zi.CURRENT)
    assert again[1] == (zi.STATE, b"\x04")
    assert strings(again[2][1])[1][0] == "http://192.168.1.57/" + tail
    net = ask(lib, imp, cable, zi.NETWORK)
    assert strings(net[1][1])[1][0] == "3"


def test_a_board_with_a_password_answers_its_id_and_no_claim(lib):
    cable = Cable(lib)
    imp = zi.Improv(cable, Board(ip="10.0.0.9", claim=""), serving=True)
    got = ask(lib, imp, cable, zi.CURRENT)
    assert strings(got[2][1])[1] == ["http://10.0.0.9/#id=" + BOARD_ID,
                                     "http://moybyte-zero.local/#id=" + BOARD_ID]


def test_the_cable_s_claim_is_fresh_each_time_and_comes_with_a_password_too(lib):
    """0xF0 (My consoles' "Manage by cable"): the address with a new claim,
    which may replace the password, while the board serves; none before."""
    cable = Cable(lib)
    board = Board(ip="10.0.0.9", claim="")
    imp = zi.Improv(cable, board, serving=True)
    got = ask(lib, imp, cable, zi.CLAIM)
    assert got[0] == (zi.ERROR, b"\x00")
    assert strings(got[1][1]) == (zi.CLAIM, ["http://10.0.0.9/#id=%s&claim=%032x" % (BOARD_ID, 1),
                                             "http://moybyte-zero.local/#id=%s&claim=%032x"
                                             % (BOARD_ID, 1)])
    assert strings(ask(lib, imp, cable, zi.CLAIM)[1][1])[1][0].endswith("claim=%032x" % 2)
    assert "claim" not in strings(ask(lib, imp, cable, zi.CURRENT)[2][1])[1][0]
    early = zi.Improv(cable, Board(), serving=False)
    assert ask(lib, early, cable, zi.CLAIM) == [(zi.ERROR, b"\x00"), (zi.RESULT, bytes([zi.CLAIM, 0]))]


def test_a_board_on_a_network_joins_another_and_answers_its_new_address(lib):
    cable = Cable(lib)
    board = Board(ip="10.0.0.9", claim="")
    imp = zi.Improv(cable, board, serving=True)
    got = ask(lib, imp, cable, zi.WIFI, wifi(b"office", b"other password"))
    assert got[:3] == [(zi.ERROR, b"\x00"), (zi.STATE, b"\x03"), (zi.STATE, b"\x04")]
    assert strings(got[3][1])[1][0] == "http://192.168.1.57/#id=" + BOARD_ID
    assert board.saved == [("office", "other password")]


def test_a_join_from_the_access_point_is_answered_once_the_board_serves(lib):
    cable = Cable(lib)
    imp = zi.Improv(cable, Board(), serving=False)
    got = ask(lib, imp, cable, zi.WIFI, wifi(b"home", b""))
    assert got == [(zi.ERROR, b"\x00"), (zi.STATE, b"\x03")]
    assert imp.joined == ("192.168.1.57", zi.WIFI)
    imp.serving = True
    imp.finish()
    got = cable.read()
    assert got[0] == (zi.STATE, b"\x04")
    assert strings(got[1][1])[1][0].startswith("http://192.168.1.57/#id=")
    assert imp.joined is None


def test_a_network_that_does_not_answer_is_unable_to_connect(lib):
    cable, board = Cable(lib), Board(joins=False)
    imp = zi.Improv(cable, board, serving=False)
    got = ask(lib, imp, cable, zi.WIFI, wifi(b"home", b"wrong one"))
    assert got == [(zi.ERROR, b"\x00"), (zi.STATE, b"\x03"), (zi.ERROR, b"\x03"),
                   (zi.STATE, b"\x02")]
    assert board.saved == [] and imp.joined is None


def test_the_name_and_the_hostname_are_one_label(lib):
    cable, board = Cable(lib), Board()
    imp = zi.Improv(cable, board, serving=False)
    got = ask(lib, imp, cable, zi.NAME, b"\x0aMy Kitchen")
    assert strings(got[1][1]) == (zi.NAME, ["mykitchen"])
    got = ask(lib, imp, cable, zi.HOSTNAME, b"\x0aMy Kitchen")
    assert got[1] == (zi.ERROR, b"\x05"), "a hostname is RFC 1123 or refused"
    got = ask(lib, imp, cable, zi.HOSTNAME, b"\x07attic-2")
    assert strings(got[1][1]) == (zi.HOSTNAME, ["attic-2"])
    assert strings(ask(lib, imp, cable, zi.NAME)[1][1]) == (zi.NAME, ["attic-2"])


def test_bad_frames_and_unknown_commands_are_told_so(lib):
    cable = Cable(lib)
    imp = zi.Improv(cable, Board(), serving=False)
    f = bytearray(rpc(lib, zi.CURRENT))
    f[-2] ^= 1
    cable.write(bytes(f))
    imp.poll()
    assert cable.read() == [(zi.ERROR, b"\x01")]
    assert ask(lib, imp, cable, 0x42) == [(zi.ERROR, b"\x00"), (zi.ERROR, b"\x02")]
    cable.write(frame(lib, zi.RPC, b"\x01\x05\x02ab"))      # lengths that do not add up
    imp.poll()
    assert cable.read() == [(zi.ERROR, b"\x01")]


def test_the_setup_loop_hands_a_join_over_the_cable_to_the_serving_board(monkeypatch, tmp_path):
    """The claim lives in RAM, so a join over the cable never resets the
    board: the loop ends the access point and its servers and returns the IP
    for zero_host.serve to go on serving from."""
    log = []

    class Srv:
        def __init__(self, *a, **kw):
            pass

        def start(self, ip=None):
            return True

        def poll(self):
            pass

        def due(self):
            return False

        def stop(self):
            log.append("server stop")

    class Dns:
        def __init__(self, ip):
            pass

        def start(self):
            return True

        def poll(self):
            pass

        def stop(self):
            log.append("dns stop")

    class Imp:
        joined = None

        def poll(self):
            Imp.joined = ("192.168.1.57", zi.WIFI)

    net = zero_setup.moy_net
    monkeypatch.setattr(net, "wifi_ap_mac", lambda: b"\x24\x6f\x28\xaa\x97\x3d", raising=False)
    monkeypatch.setattr(net, "wifi_ap", lambda ssid: log.append("ap %r" % ssid) or "192.168.4.1",
                        raising=False)
    monkeypatch.setattr(zero_setup, "SetupServer", Srv)
    monkeypatch.setattr(zero_setup, "DnsRedirect", Dns)
    monkeypatch.setitem(sys.modules, "machine", object())
    ip = zero_setup.run(str(tmp_path / "w"), str(tmp_path / "z"), str(tmp_path / "s"),
                        sleep_ms=0, improv=Imp())
    assert ip == "192.168.1.57"
    assert log == ["ap 'moybyte-zero-973d'", "server stop", "dns stop", "ap ''"]


@pytest.mark.parametrize("data", [b"", b"\x01", b"\x01\x04\x02ab", b"\x01\x03\x05ab"])
def test_parse_rpc_refuses_lengths_that_do_not_add_up(data):
    assert zi.parse_rpc(data) is None


def test_a_result_never_outgrows_a_frame():
    data = zi.rpc_result(zi.SCAN, ["x" * 200, "y" * 200])
    assert len(data) <= 255 and zi.parse_rpc(data) is not None
