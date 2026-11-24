"""The station's transmit-power walk (moy_net.h, the station's transmit power):
full power first, a lower power only after a garbled handshake, remembered per
network, and a remembered power that fails walks back up to full."""

import ctypes

import pytest

from runtime import net_binding as moy_net

FULL, MID, FLOOR = 80, 60, 34
AUTH_EXPIRE, HANDSHAKE_4WAY, BEACON, NO_AP, HANDSHAKE, CONN_FAIL = 2, 15, 200, 201, 204, 205
AUTH_FAIL, ASSOC_LEAVE = 202, 8


@pytest.fixture(scope="module")
def lib():
    try:
        return moy_net._lib()
    except ImportError as e:
        pytest.skip(str(e))


def _table(lib):
    return ctypes.create_string_buffer(lib.moy_net_host_txp_table_size())


def _learn(lib, t, ssid, txp):
    return lib.moy_net_host_txp_learn(t, ssid.encode(), txp)


def _recall(lib, t, ssid):
    return lib.moy_net_host_txp_recall(t, ssid.encode())


GARBLED = (AUTH_EXPIRE, HANDSHAKE_4WAY, HANDSHAKE, CONN_FAIL)


def _walk(lib, start, reasons):
    """The powers a join's attempts ask for, each refused with the next
    reason, the way moy_wifi.c carries its flags: a join from a remembered
    power is searching and its first refusal is at a known power, and a
    garbled refusal starts a search."""
    cur, seen = start, [start]
    first = search = int(start != FULL)
    for r in reasons:
        search |= int(r in GARBLED)
        cur = lib.moy_net_host_txp_next(r, cur, first, search)
        first = 0
        seen.append(cur)
    return seen


def test_full_power_is_the_first_try_with_nothing_remembered(lib):
    t = _table(lib)
    assert _recall(lib, t, "home") == 0
    assert lib.moy_net_host_txp_start(_recall(lib, t, "home")) == FULL


def test_a_garbled_handshake_steps_down_to_the_floor_and_round_to_full(lib):
    for r in GARBLED:
        assert _walk(lib, FULL, [r] * 4) == [FULL, MID, FLOOR, FULL, MID]


def test_a_board_that_never_needed_less_stays_at_full(lib):
    for r in (NO_AP, BEACON, AUTH_FAIL, ASSOC_LEAVE, 0):
        assert _walk(lib, FULL, [r] * 3) == [FULL] * 4


def test_a_search_steps_past_a_network_lost_at_full(lib):
    # the SuperMini at full power: the handshake garbled, then the probe
    # answers lost (201), walked round twice
    assert _walk(lib, FULL, [AUTH_EXPIRE, NO_AP, BEACON, NO_AP, NO_AP, NO_AP]) == [
        FULL, MID, FLOOR, FULL, MID, FLOOR, FULL]
    assert lib.moy_net_host_txp_next(AUTH_FAIL, MID, 0, 1) == MID


def test_the_remembered_power_is_per_network(lib):
    t = _table(lib)
    assert _learn(lib, t, "home", FLOOR)
    assert _recall(lib, t, "home") == FLOOR
    assert _recall(lib, t, "office") == 0
    assert lib.moy_net_host_txp_start(_recall(lib, t, "office")) == FULL
    assert _learn(lib, t, "office", MID)
    assert (_recall(lib, t, "home"), _recall(lib, t, "office")) == (FLOOR, MID)
    assert not _learn(lib, t, "office", MID)        # nothing new, nothing written
    assert not _learn(lib, t, "cafe", FULL)         # full power takes no slot
    for i in range(4):
        _learn(lib, t, "n%d" % i, FLOOR)
    assert _recall(lib, t, "home") == 0             # the oldest goes
    assert _recall(lib, t, "n3") == FLOOR


def test_a_remembered_power_that_fails_walks_back_up_and_is_replaced(lib):
    t = _table(lib)
    _learn(lib, t, "home", FLOOR)
    start = lib.moy_net_host_txp_start(_recall(lib, t, "home"))
    assert start == FLOOR
    for r in (AUTH_EXPIRE, NO_AP, BEACON, HANDSHAKE):
        assert _walk(lib, start, [r]) == [FLOOR, FULL]
    # from full the walk goes on down, past the remembered power and round,
    # whatever the refusals: a network that needed less is a search
    assert _walk(lib, MID, [NO_AP, NO_AP, NO_AP, BEACON, NO_AP]) == [
        MID, FULL, MID, FLOOR, FULL, MID]
    assert _learn(lib, t, "home", FULL)             # full worked: forgotten
    assert _recall(lib, t, "home") == 0
    _learn(lib, t, "home", FLOOR)
    assert _learn(lib, t, "home", MID)
    assert _recall(lib, t, "home") == MID
