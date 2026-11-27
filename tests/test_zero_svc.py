"""The Zero's on-board services (device/zero_svc.py, #256): an installed
app's Lua service, started by the board's service host as the console
starts one, under its grant and the board's budget for services.

The host runs the same host as the board over the host's twins (moycore's
services stepped at each turn, moy_app's state over the kernel's settings
rows), with Moy Mesh (tests/fixtures/apps/moymesh.moy) as the app: the
service the board is for. The host has no radio, so its service runs with
none; what it holds is the start, its chunks' order, the grant's prefs and
keys, the budget's refusal and the page's hook (scheduler.on_board)."""

import json
import os
import shutil
import sys
import time

import pytest

import runtime  # noqa: F401 -- registers the twins' module names
from runtime import moy_evq, moycore, scheduler as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "device"))
import zero_svc  # noqa: E402

MESH = os.path.join(ROOT, "tests", "fixtures", "apps", "moymesh.moy")


def _install(root, autostart=True, kib=None):
    dst = os.path.join(root, "moymesh.moy")
    shutil.copytree(MESH, dst)
    with open(os.path.join(dst, "manifest.json")) as f:
        m = json.load(f)
    if autostart:
        m["moybyte"]["permissions"].append("autostart")
    if kib is not None:
        m["moybyte"]["service_kib"] = kib
    with open(os.path.join(dst, "manifest.json"), "w") as f:
        json.dump(m, f)
    return dst


@pytest.fixture
def carts(tmp_path):
    root = tmp_path / "carts"
    root.mkdir()
    yield str(root)
    moycore.svc_reset()
    moy_evq.reset()


def test_moy_mesh_s_service_starts_at_boot_with_its_shared_script_first(carts):
    _install(carts)
    host = zero_svc.Services(carts)
    m = json.load(open(os.path.join(carts, "moymesh.moy", "manifest.json")))
    got = zero_svc.chunks(os.path.join(carts, "moymesh.moy"), m, zero_svc.entry_of(m))
    assert [n for _s, n in got] == ["@mesh.lua", None], "mesh.lua ahead of service.lua"
    assert host.boot() == ["moymesh"]
    for _ in range(20):
        host.turn()
    (app_id, _pid, state, heap, why), = host.info()
    assert app_id == "moymesh" and state != zero_svc.SVC_EXITED, why
    assert heap > 50 << 10, "its state's bytes, counted"
    print("Moy Mesh's service on the host: %d B" % heap)


def test_a_service_that_does_not_ask_for_autostart_waits(carts):
    _install(carts, autostart=False)
    host = zero_svc.Services(carts)
    assert host.boot() == []
    assert host.running == {}


def test_a_service_the_budget_cannot_hold_is_refused_with_the_reason(carts, monkeypatch):
    _install(carts, kib=4096)
    host = zero_svc.Services(carts)
    monkeypatch.setattr(host.svc, "svc_budget", lambda: (1024 << 10, 0))
    assert host.boot() == []
    m = json.load(open(os.path.join(carts, "moymesh.moy", "manifest.json")))
    assert host.room(zero_svc.need(m)) == ("it needs 4096 KB and this board gives its "
                                           "services 1024 KB, 1024 KB of it free")


def test_its_console_calls_are_the_board_s(carts):
    _install(carts)
    host = zero_svc.Services(carts)
    host.boot()
    pid = host.running["moymesh"].pid
    pub = host.call(pid, "moybyte.key_make", ["node"])
    assert len(pub) == 64 and host.call(pid, "moybyte.key_public", ["node"]) == pub
    assert abs(host.call(pid, "moybyte.clock", [0]) - time.time()) <= 2
    with pytest.raises(ValueError):
        host.call(pid, "moybyte.notify", ["x"])


def test_its_clock_is_unix_seconds_where_time_counts_from_2000():
    """A board's `time.time()` counts from 2000; the service's
    `moybyte.clock()` is Unix seconds, as a console's, so a record a service
    stamps reads on the page's clock."""
    class Board:
        @staticmethod
        def time():
            return 849078670

        @staticmethod
        def gmtime(t):
            return (2000, 1, 1, 0, 0, 0, 5, 1)
    assert zero_svc.unix_now(Board) == 849078670 + 946684800
    assert abs(zero_svc.unix_now() - time.time()) <= 2


def test_the_page_starts_no_service_of_an_app_its_board_runs():
    S.on_board(("moymesh",))
    try:
        cart = {"id": "moymesh", "title": "Moy Mesh", "type": "service", "runtime": "lua",
                "src": "", "permissions": [], "required": []}
        assert S.SCHED.start(cart) is None
    finally:
        S.on_board(())


def test_the_restart_rule_is_the_console_s():
    assert (zero_svc.RESTART_BACKOFF_MS, zero_svc.RESTART_HEAL_MS, zero_svc.RESTART_CAP,
            zero_svc.RESTART_KEY, zero_svc.POLICIES) == (
        S.MOY_RESTART_BACKOFF_MS, S.MOY_RESTART_HEAL_MS, S.RESTART_CAP, S.RESTART_KEY,
        S.POLICIES)


def _crash(host, app_id="moymesh"):
    """The running service ended as a crash would leave it, then reaped."""
    s = host.running[app_id]
    host.svc.svc_stop(s.h)
    for _ in range(50):
        host.turn()
        if app_id not in host.running:
            return
    raise AssertionError("the service did not end")


def test_an_unasked_end_restarts_by_its_policy_backs_off_and_gives_up(carts, monkeypatch):
    _install(carts)
    host = zero_svc.Services(carts)
    now = [0]
    monkeypatch.setattr(zero_svc, "_ticks", lambda: now[0])
    host.boot()
    _crash(host)
    assert host.pending == {}, "never (the default) leaves it down"
    host.set_policy("moymesh", zero_svc.ALWAYS)
    assert host.policy("moymesh") == zero_svc.ALWAYS
    host.start_by_hand("moymesh")
    for n in range(1, zero_svc.RESTART_CAP):
        _crash(host)
        due = host.pending["moymesh"][0]
        assert due == now[0] + (zero_svc.RESTART_BACKOFF_MS << (n - 1)), "the back-off doubles"
        host.turn()
        assert "moymesh" not in host.running, "it waits its back-off"
        now[0] = due
        host.turn()
        assert "moymesh" in host.running, "then it starts again"
    _crash(host)
    assert host.pending == {}, "the cap's end leaves it down"
    assert host.start_by_hand("moymesh") is not None and host.down == {}, \
        "a start by hand forgets the ends in a row"


def test_an_asked_stop_does_not_restart(carts):
    _install(carts)
    host = zero_svc.Services(carts)
    host.set_policy("moymesh", zero_svc.ALWAYS)
    host.boot()
    host.stop("moymesh")
    for _ in range(50):
        host.turn()
    assert "moymesh" not in host.running and host.pending == {}


def test_the_page_says_where_a_service_too_big_for_its_board_runs():
    m = {"moybyte": {"entries": {"service": "service.lua"}, "service_kib": 160}}
    assert S.service_need(m) == 160
    assert S.service_need({"moybyte": {"entries": {"service": "s.lua"}}}) == 40
    assert S.service_need({"moybyte": {}}) is None
    assert S.board_reason(m, (1024, 900)) is None
    assert S.board_reason(m, (128, 128)) == (
        "Its service runs in the page on this board: it needs 160 KB and this board "
        "gives its services 128 KB.")
    assert S.board_reason(m, (1024, 100)).endswith("gives its services 1024 KB, 100 KB of it free.")
    assert S.board_reason(m, None) is None
