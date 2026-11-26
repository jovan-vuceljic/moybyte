"""The Zero suite's tools with no board (tests/zero_glass.py): the Improv
client against the board's own side of the protocol (device/zero_improv.py),
the raw REPL over a fake port, and the numbers' record."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zero_glass as Z  # noqa: E402
import zero_improv  # noqa: E402 -- on the path zero_glass puts device/ on
import perf_pass  # noqa: E402


class Port:
    """The board's console: frames it is fed answered by zero_improv's
    Improv, everything else echoed as console bytes."""

    def __init__(self, board):
        self.out = b""
        self.frames = Z.Frames()
        self.queue = []
        self.improv = zero_improv.Improv(self, board)

    # the board's end (zero_improv's port)
    def take(self):
        return self.queue.pop(0) if self.queue else None

    def send(self, kind, data):
        self.out += b"boot noise\r\n" + Z.frame(kind, data)

    # the host's end (a serial port)
    in_waiting = property(lambda self: len(self.out))

    def write(self, data):
        for kind, body, ok in self.frames.feed(data):
            self.queue.append((kind, body) if ok else (zero_improv.BAD, body))
        self.improv.poll()

    def flush(self):
        pass

    def read(self, n):
        got, self.out = self.out[:3], self.out[3:]       # cut anywhere
        return got


class Board:
    def __init__(self, ip="192.168.1.7", joins=True):
        self._ip, self.joins, self.saved = None, joins, None
        self.ip_after = ip

    def info(self):
        return "v1", "ESP32-C3"

    def name(self):
        return "moybyte-zero"

    def join(self, ssid, pw):
        return self.ip_after if self.joins else None

    def save(self, ssid, pw):
        self.saved = (ssid, pw)
        self._ip = self.ip_after

    def ip(self):
        return self._ip

    def address(self, fresh=False):
        return "ab" * 16, "c0ffee"


def test_a_frame_is_what_the_board_parses_and_a_split_read_still_parses():
    f = Z.wifi_rpc("Bench", "pw 1")
    frames = Z.Frames()
    got = []
    for i in range(len(f)):
        got += frames.feed(b"xx" + f[i:i + 1] if i == 0 else f[i:i + 1])
    assert len(got) == 1 and got[0][0] == zero_improv.RPC and got[0][2]
    assert zero_improv.parse_rpc(got[0][1]) == (zero_improv.WIFI, [b"Bench", b"pw 1"])
    assert frames.other == b"xx"


def test_a_bad_sum_is_a_frame_that_says_so():
    f = bytearray(Z.rpc(zero_improv.CURRENT))
    f[-2] ^= 1
    (kind, _data, ok), = Z.Frames().feed(bytes(f))
    assert kind == zero_improv.RPC and not ok


def test_console_bytes_around_frames_are_kept_in_order():
    frames = Z.Frames()
    got = frames.feed(b"ZERO serving\r\nIMPR")
    got += frames.feed(Z.frame(zero_improv.STATE, b"\x02")[4:] + b">>> ")
    assert [(k, d) for k, d, ok in got] == [(zero_improv.STATE, b"\x02")]
    assert frames.other == b"ZERO serving\r\n>>> "


def test_a_join_answers_provisioned_and_the_urls_the_board_serves_at():
    board = Board()
    st, urls, secs, err = Z.Improv(Port(board)).join("Bench", "secret pw")
    assert (st, err) == (zero_improv.PROVISIONED, None)
    assert urls == ["http://192.168.1.7/#id=%s&claim=c0ffee" % ("ab" * 16),
                    "http://moybyte-zero.local/#id=%s&claim=c0ffee" % ("ab" * 16)]
    assert board.saved == ("Bench", "secret pw")
    assert [Z.bare(u) for u in urls] == ["http://192.168.1.7/", "http://moybyte-zero.local/"]


def test_a_join_that_fails_answers_its_error_and_ready():
    st, urls, _secs, err = Z.Improv(Port(Board(joins=False))).join("Bench", "x", timeout=2)
    assert (st, urls, err) == (zero_improv.READY, [], zero_improv.UNABLE)


def test_a_claim_answers_the_url_with_a_fresh_claim():
    board = Board()
    board.save("Bench", "pw")
    urls, err = Z.Improv(Port(board)).claim()
    assert err is None and urls[0].startswith("http://192.168.1.7/#id=") \
        and urls[0].endswith("&claim=c0ffee"), urls


def test_a_board_in_setup_answers_ready():
    assert Z.Improv(Port(Board())).state() == (zero_improv.READY, [])


class Repl:
    """A raw REPL: answers each exec'd code from `answers` (code -> (out, err))."""

    def __init__(self, answer):
        self.answer, self.out, self.sent = answer, b"", []

    in_waiting = property(lambda self: len(self.out))

    def write(self, data):
        self.sent.append(data)
        if data == b"\r\x01":
            self.out += b"MicroPython\r\n" + Z.RAW_PROMPT
        elif data.endswith(b"\x04") and len(data) > 1:
            out, err = self.answer(data[:-1].decode())
            self.out += b"OK" + out + b"\x04" + err + b"\x04>"

    def flush(self):
        pass

    def reset_input_buffer(self):
        self.out = b""

    def read(self, n):
        got, self.out = self.out[:n], self.out[n:]
        return got


def test_the_raw_repl_runs_code_and_reads_its_output_and_errors():
    port = Repl(lambda code: (b"42\r\n", b"") if "6 * 7" in code else
                (b"", b"Traceback (most recent call last):\r\nOSError: 2\r\n"))
    r = Z.Repl(port)
    r.enter(timeout=2)
    assert r.eval("6 * 7", timeout=2) == 42
    with pytest.raises(Z.ReplError, match="OSError: 2"):
        r.run("open('/none')", timeout=2)
    r.leave()
    assert port.sent[-2:] == [b"\r\x02", b"\x04"]


def test_a_file_round_trips_as_hex_and_a_missing_one_is_none():
    store = {"/moy/wifi.json": b'{"networks": []}' * 100}

    def answer(code):
        import binascii
        import re
        m = re.search(r"open\('([^']+)','rb'\)", code)
        if m:
            data = store.get(m.group(1))
            if data is None:
                return b"-\r\n", b""
            lines = [binascii.hexlify(data[i:i + 512]) for i in range(0, len(data), 512)]
            return b"\r\n".join(lines) + b"\r\n.\r\n", b""
        m = re.search(r"open\('([^']+)','wb'\)", code)
        if m:
            store[m.group(1)] = b""
            return b"", b""
        m = re.search(r"open\('([^']+)','ab'\)\nf.write\(binascii.unhexlify\('([0-9a-f]*)'\)\)", code)
        if m:
            store[m.group(1)] += binascii.unhexlify(m.group(2))
            return b"", b""
        m = re.search(r"stat\('([^']+)'\)\[6\]", code)
        if m:
            return b"%d\r\n" % len(store[m.group(1)]), b""
        raise AssertionError(code)

    r = Z.Repl(Repl(answer))
    assert r.read("/moy/wifi.json") == store["/moy/wifi.json"]
    assert r.read("/moy/none") is None
    r.write("/moy/copy", store["/moy/wifi.json"])
    assert store["/moy/copy"] == store["/moy/wifi.json"]


def test_a_tree_is_read_from_the_lines_the_board_prints():
    r = Z.Repl(Repl(lambda code: (b"-1 /moy/carts\r\n120 /moy/carts/a.moy\r\n60 /moy/wifi.json\r\n",
                                  b"")))
    assert r.tree("/moy") == {"/moy/carts": -1, "/moy/carts/a.moy": 120, "/moy/wifi.json": 60}


def test_the_internal_heap_is_the_free_sum_and_the_largest_block():
    assert Z.internal_heap([(200, 100, 64, 10), (80, 40, 32, 5)]) == (140, 64)


def test_free_reads_the_internal_row():
    text = ("              total       used       free\n"
            "internal      262144     200000      62144\n"
            "python        131072      65536      65536\n")
    assert Z.free_internal(text) == (262144, 200000, 62144)
    assert Z.free_internal("free: no figures here\n") is None


def test_a_drift_is_the_fall_of_the_last_rounds_best_from_the_first():
    assert Z.drift([100], 10) == (0, False)
    assert Z.drift([100, 90, 98, 95], 10) == (2, False)    # one round caught mid-request
    assert Z.drift([100, 95, 90, 85, 80, 75], 10) == (15, True)
    assert Z.drift([100, 104, 110], 10) == (-10, False)


def test_an_ssh_client_takes_its_password_from_its_environment(tmp_path):
    s = Z.Ssh("192.0.2.7", "bench-pw", str(tmp_path / "home"))
    argv = s.argv("ls", tty=False)
    assert argv[0] == "ssh" and argv[-2:] == ["moy@192.0.2.7", "ls"]
    assert "bench-pw" not in " ".join(argv)
    assert s.env()["MOY_SSH_PW"] == "bench-pw" and s.env()["SSH_ASKPASS"] == s.askpass
    assert "-tt" in s.argv(tty=True)
    assert "bench-pw" not in open(s.askpass).read()


def test_percentiles_are_nearest_rank():
    xs = list(range(1, 11))
    assert Z.rtt(xs) == (5, 9)
    assert Z.percentile([], 50) is None


def test_the_record_holds_every_metric_and_says_why_one_is_absent():
    rec = Z.zero_record("c3_zero", {"zero live rtt median": (6.2, [5, 6, 7])},
                        {}, {"stamp": "c2d35a0c", "flashed": True}, secs=12.0)
    assert [n for n, _u, _b in Z.METRICS] == list(rec["metrics"])
    assert rec["metrics"]["zero live rtt median"]["value"] == 6.2
    assert rec["metrics"]["zero improv join"]["value"] is None
    assert "not taken" in rec["errors"]["zero improv join"]
    assert rec["commit"] == "c2d35a0c"
    assert perf_pass.protocol_key(rec["protocol"]) == (perf_pass.AFTER_SUITE, None)
