"""The Zero's terminal (device/zero_shell.py)
on the host: its door answers the shell's crossings it can (`passwd`, `df`,
`mem`, `ps`), says the other role commands and the installed ones are not
served on this board, hands every other back as a console with its VM
stopped does, and ssh_service serves on it without a WiFi lease."""

import sys
from pathlib import Path

import pytest

from runtime import net_binding, ssh_service

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "device"))

import zero_shell                                               # noqa: E402

DOOR = zero_shell.SH_DOOR


class IO:
    def __init__(self):
        self.out = {1: b"", 2: b""}

    def write(self, fd, b):
        self.out[fd] += b


class Server:
    def __init__(self):
        self.calls = []

    def parked(self):
        return True

    def start(self, path):
        self.calls.append(("start", path))

    def stop(self):
        self.calls.append(("stop",))

    def stats(self):
        return (0, 0, 0, 0, 0, 0, 0, bool(self.calls) and self.calls[-1][0] == "start")


@pytest.fixture
def zero(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "ssh_service", ssh_service)
    monkeypatch.setattr(ssh_service._docs, "system_store_path",
                        lambda root=None: str(tmp_path / "settings"))
    server = Server()
    monkeypatch.setattr(ssh_service, "_N", server)
    monkeypatch.setattr(ssh_service, "_state",
                        {"serving": False, "name": None, "default": None, "park": None})

    def no_radio(*a):
        raise AssertionError("the Zero's radio and name are the board's")
    monkeypatch.setitem(sys.modules, "moy_net", type("N", (), {
        "wifi_mdns": staticmethod(no_radio), "pw_hash": staticmethod(net_binding.pw_hash)}))
    ws = zero_shell.Console(str(tmp_path / "carts"), "Pocket Zero")
    io = IO()
    return zero_shell.Door(ws, io), io, server, tmp_path


def cross(door, *fields):
    return door(0, DOOR, b"\0".join(f.encode() for f in fields))


def test_passwd_crosses_the_door_and_serves_without_a_lease(zero):
    door, io, server, tmp = zero
    assert cross(door, "role", "j1", "passwd") == 0
    assert io.out[1].startswith(b"password not set\n")
    assert cross(door, "role", "j1", "passwd", "short") == 1
    assert cross(door, "role", "j1", "passwd", "s3cret-pw") == 0
    assert (tmp / "password").read_text().startswith("$moy2$")
    assert server.calls == [("start", str(tmp))]
    io.out[1] = b""
    assert cross(door, "role", "j1", "passwd") == 0
    assert io.out[1].startswith(b"password set\n"
                                b"ssh serving as pocket-zero.local, 0 session(s), 0 refused\n"
                                b"host key ")
    assert b"browser(s) paired" not in io.out[1]      # this Console has no webhost
    assert cross(door, "role", "j1", "passwd", "-l") == 1
    assert cross(door, "role", "j1", "passwd", "-x") == 2
    assert b"usage: passwd" in io.out[2]
    assert cross(door, "role", "j1", "passwd", "-d") == 0
    assert not (tmp / "password").exists() and server.calls[-1] == ("stop",)


def test_a_role_command_or_an_installed_one_is_not_served_here(zero):
    """ABSENT, which the shell says as "<cmd>: not served here" (an
    installed one's "not found"), the store's C serving `settings` and `pkg
    list` in its place (native/moy_sh/moy_sh_board.c, b_role): never
    NEEDS_VM, whose "needs the console" sends the user looking for one."""
    door, io, _, _ = zero
    for fields in (("role", "j1", "settings", "list"), ("role", "j1", "python"),
                   ("role", "j1", "cron", "list"), ("role", "j1", "pkg", "install", "x"),
                   ("role", "j1"), ("spawn", "0:j1", "hello"), ("spawn", "1", "hello")):
        assert cross(door, *fields) == zero_shell.ABSENT, fields
    assert io.out == {1: b"", 2: b""}


def test_what_only_a_console_answers_is_handed_back(zero):
    door, io, _, _ = zero
    for fields in (("lookup", "hello"), ("kill", "1", "15"), ("read", "/proc/kernel"),
                   ("list", "/dev"), ("status", "7"), ("step", "j1")):
        assert cross(door, *fields) == zero_shell.NEEDS_VM, fields
    assert door(0, 3, b"") == zero_shell.ABSENT


def test_proc_console_names_the_board_for_neofetch(zero, monkeypatch):
    """neofetch's title and its Board and Firmware rows: the mDNS name, the
    board's name by its OTA id and the image's label."""
    import moy_ota
    monkeypatch.setattr(moy_ota, "BOARD", "c3_zero")
    monkeypatch.setattr(moy_ota, "FIRMWARE_LABEL", "beta 2026-11-25 18:06")
    door, _, _, _ = zero
    assert cross(door, "read", "/proc/console") == (
        b"name: pocket-zero\nboard: ESP32-C3 Zero\nfirmware: beta 2026-11-25 18:06\n")


def test_the_board_s_own_figures(zero, tmp_path):
    door, _, _, _ = zero
    total, free = (int(x) for x in cross(door, "df", str(tmp_path)).split())
    assert total >= free > 0
    row = cross(door, "ps").split()
    assert row[:4] == ["1", "0", "shell", "running"] and row[5:] == ["-", "zero_host"]
    assert cross(door, "rescan", "moybyte.hop") == 0


def test_passwd_lists_and_forgets_the_browsers_its_webhost_paired(zero):
    door, io, _, _ = zero

    class Web:
        def __init__(self):
            self.kids = {"k1": (86400, 2 * 86400, "Laptop")}

        def browsers(self):
            return [(k,) + v for k, v in self.kids.items()]

        def forget(self, kid):
            return 1 if self.kids.pop(kid, None) else 0

    door.ws.webhost = Web()
    assert cross(door, "role", "j1", "passwd", "-l") == 0
    assert io.out[1].startswith(b"k1  paired 1970-01-0") and io.out[1].endswith(b"Laptop\n")
    assert cross(door, "role", "j1", "passwd", "-r", "k1") == 0
    assert cross(door, "role", "j1", "passwd", "-r", "k1") == 1


def test_df_says_absent_for_a_folder_no_volume_holds(zero, tmp_path):
    door, _, _, _ = zero
    assert cross(door, "df", str(tmp_path / "sd")) == zero_shell.ABSENT


# -- wifi: the page's Wi-Fi panel's backend, served to the shell --------------------


class Asks(IO):
    """A session that asks questions (moy_sh.h's moy_sh_ask): `answers`
    typed to the line's questions, in order, the line run again after each."""

    def __init__(self):
        super().__init__()
        self.asked, self.answers = [], []

    def ask(self, prompt, secret=False):
        self.asked.append(prompt)

    def answer(self):
        return self.answers.pop(0) if self.answers else None


@pytest.fixture
def board(tmp_path, monkeypatch):
    import json

    import zero_wifi
    from test_zero_wifi import HOME, RPT, Clock, Radio
    clock = Clock()
    monkeypatch.setattr(zero_wifi, "ticks_ms", clock)
    store = tmp_path / "wifi.json"
    store.write_text(json.dumps({"networks": [{"ssid": HOME, "password": "homepw"},
                                              {"ssid": "Work", "password": "workpw"}]}))
    radio = Radio(clock, {HOME: ("homepw", -50), RPT: ("rptpw", -70)}, on=HOME)
    w = zero_wifi.ZeroWifi(str(store), "pocket-zero", radio=radio, join_ms=4000,
                           back_ms=4000, leave_ms=500)
    ws = zero_shell.Console(str(tmp_path / "carts"), "Pocket Zero", type("Web", (), {"wifi": w}))
    io = Asks()
    return zero_shell.Door(ws, io), io, w, radio, clock


def wifi(door, w, clock, *argv):
    """`wifi ARGV` stepped as the session steps a role command, the webhost's
    poll stepping the backend between (zero_host's loop)."""
    r = cross(door, "role", "j1", "wifi", *argv)
    while r == zero_shell.RUNNING:
        clock.ms += 100
        if w.busy():
            w.step()
        r = cross(door, "step", "j1")
    return r


def settle(w, clock):
    while w.busy():
        clock.ms += 100
        w.step()


def said(io):
    out = (io.out[1].decode(), io.out[2].decode())
    io.out = {1: b"", 2: b""}
    return out


def test_wifi_shows_the_boards_station_its_scan_and_its_saved_networks(board):
    door, io, w, radio, clock = board
    assert wifi(door, w, clock) == 0 and said(io) == ("connected to Home (10.0.0.2)\n", "")
    assert wifi(door, w, clock, "list") == 0
    assert said(io) == ("in use  Home\n        Work\n", "")
    assert wifi(door, w, clock, "scan") == 0 and radio.scans == 1
    assert said(io) == ("100%  locked  in use  Home\n 60%  locked          Home_RPT\n", "")
    assert door.jobs == {}


def test_wifi_forget_keeps_the_network_in_use(board):
    """Forgetting never leaves the network (ZeroWifi's forget), but the one in
    use is refused: the board's next boot would not find it."""
    door, io, w, radio, clock = board
    assert wifi(door, w, clock, "forget", "Home") == 1
    assert said(io) == ("", "wifi: Home is the network in use: join another first\n")
    assert wifi(door, w, clock, "forget", "Nowhere") == 1
    assert said(io) == ("", "wifi: Nowhere: not saved\n")
    assert wifi(door, w, clock, "forget", "Work") == 0 and radio.forgot == ["Work"]
    assert [n["ssid"] for n in w.saved()] == ["Home"] and radio.up and radio.ssid == "Home"


def test_wifi_join_asks_first_and_moves_the_board_with_its_way_back(board):
    door, io, w, radio, clock = board
    assert wifi(door, w, clock, "join", "-y", "Home") == 0
    assert said(io) == ("already on Home\n", "")
    assert wifi(door, w, clock, "join", "Home_RPT", "rptpw") == zero_shell.NOT_RUN
    assert io.asked == ["Leave Home for Home_RPT? This session ends as the board moves. [y/N] "]
    io.answers = ["n"]
    assert wifi(door, w, clock, "join", "Home_RPT", "rptpw") == 1 and w.busy() is False
    io.answers = ["y"]
    assert wifi(door, w, clock, "join", "Home_RPT", "rptpw") == 0
    assert said(io)[0] == ("moving to Home_RPT: the board is pocket-zero.local there, "
                           "or back on Home if Home_RPT does not answer in 4 s\n")
    settle(w, clock)
    assert radio.ssid == "Home_RPT" and w.last["ok"] is True
    assert [n["ssid"] for n in w.saved()][0] == "Home_RPT"
    # a refused password: the switch's way back takes the board to where it was
    assert wifi(door, w, clock, "join", "-y", "Home", "wrong") == 0
    settle(w, clock)
    assert radio.ssid == "Home_RPT" and radio.up and w.last["ok"] is False


def test_wifi_join_on_a_face_that_asks_nothing_needs_its_yes(board):
    door, _io, w, _radio, clock = board
    door.io = IO()
    assert wifi(door, w, clock, "join", "Home_RPT") == 1 and w.busy() is False
    assert said(door.io) == ("", "wifi: it asks first: -y says yes\n")


def test_wifi_scan_ends_at_ctrl_c_and_a_job_it_does_not_hold_is_the_consoles(board):
    door, io, w, _radio, clock = board
    assert cross(door, "role", "j1", "wifi", "scan") == zero_shell.RUNNING
    assert cross(door, "stop", "j1") == zero_shell.INTERRUPTED and door.jobs == {}
    assert cross(door, "step", "j1") == zero_shell.NEEDS_VM
    assert cross(door, "stop", "j2") == zero_shell.NEEDS_VM
    for bad in (("bogus",), ("forget",), ("join",), ("scan", "-y"), ("list", "x"),
                ("join", "a", "b", "c")):
        assert wifi(door, w, clock, *bad) == 2, bad
        assert said(io)[1].startswith("usage: wifi ")


def test_wifi_says_a_board_without_its_panel_has_none(zero):
    door, io, _, _ = zero
    assert cross(door, "role", "j1", "wifi") == 1
    assert io.out[2] == b"wifi: this board has none\n"
