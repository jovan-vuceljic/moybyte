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
    assert isinstance(host.call(pid, "moybyte.clock", [0]), (int, float))
    with pytest.raises(ValueError):
        host.call(pid, "moybyte.notify", ["x"])


def test_the_page_starts_no_service_of_an_app_its_board_runs():
    S.on_board(("moymesh",))
    try:
        cart = {"id": "moymesh", "title": "Moy Mesh", "type": "service", "runtime": "lua",
                "src": "", "permissions": [], "required": []}
        assert S.SCHED.start(cart) is None
    finally:
        S.on_board(())
