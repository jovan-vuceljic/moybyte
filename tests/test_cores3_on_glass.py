"""On-glass CoreS3 SE console tests: drive the REAL board over serial.

Gated: they run only when MOYBYTE_CORES3_PORT is set (e.g.
`MOYBYTE_CORES3_PORT=/dev/ttyACM3 .venv/bin/python -m pytest
tests/test_cores3_on_glass.py -v`, or `tools/board.py pass cores3`), so the
normal host suite never needs hardware.

The board's USB is the SoC's USB-Serial/JTAG, like the T-Deck's, so the suite
ATTACHES to the running console (`[serial] attach_only`) and leaves it on the
launcher. Tests share the session in file order. The bodies every
fullscreen-tier board shares live in tests/on_glass.py; what is here is this
board's own hardware: the AXP2101's rails, light and battery, the Faces
Gamepad3, the FT6336U, the AW88298 amplifier, the ES7210 microphone, the
BM8563 clock and the Faces Bottom3's LED bar (firmware/m5stack_cores3_se/README.md).
"""

import os
import sys
import time

import pytest

import on_glass
from on_glass import ROOT

PORT, pytestmark = on_glass.gate("MOYBYTE_CORES3_PORT", "the CoreS3 SE")
BOARD_DIR = ROOT / "firmware" / "m5stack_cores3_se"
C3 = "__import__('moy_cores3')"


@pytest.fixture(scope="module")
def board():
    with on_glass.session(PORT, board_dir=BOARD_DIR) as b:
        yield b


# -- this board's hardware -------------------------------------------------------


def test_the_panel_is_the_landscape_glass(board):
    assert list(board.pyval("(ws.sys_canvas.w, ws.sys_canvas.h)", strict=True)) == [320, 240]


def test_brightness_steps_the_axp2101s_light(board):
    """Settings' Brightness is DLDO1's voltage: codes 20..28, the lowest
    still lit, the highest full; the stored level is put back."""
    was = board.pyval("ws.settings_layer.level('brightness')", strict=True)
    try:
        lo, hi = was[1], was[2]
        board.pyval("ws.settings_layer.set_level('brightness', %d) or 1" % lo, strict=True)
        low = board.pyval(C3 + ".light()", strict=True)
        board.pyval("ws.settings_layer.set_level('brightness', %d) or 1" % hi, strict=True)
        high = board.pyval(C3 + ".light()", strict=True)
        assert 20 <= low < high == 28, (low, high)
    finally:
        board.pyval("ws.settings_layer.set_level('brightness', %d) or 1" % was[0], strict=True)


def test_the_gamepad_answers_on_its_irq_line(board):
    """The Faces Gamepad3 is the kernel's pad source: found by its model,
    read only while its IRQ line is low, and holding nothing at rest."""
    g = board.pyval("(lambda g: (g.available, g.gate, g.raw, g.errors))"
                    "(__import__('moy_input').gamepad())", strict=True)
    assert g[0] is True and g[1] is True, g
    assert g[2] == 0xFF, "a button reads held at rest: 0x%02x" % g[2]
    assert g[3] == 0, g
    assert board.pyval(C3 + ".reg(8, 0xD0, 1)", strict=True) is not None
    held = board.pyval("[n for n in ('start', 'select', 'a', 'b', 'x', 'y', 'up', 'down', "
                       "'left', 'right') if ws.input.held(n)]", strict=True)
    assert held == [], held


# A person at the pad: MOYBYTE_CORES3_HUMAN=1 asks for each press on this
# terminal and waits PRESS_S for it. The buttons as the pad's byte names them
# (bit, active low) and the console's buttons each press or chord holds.
HUMAN = os.environ.get("MOYBYTE_CORES3_HUMAN") == "1"
PRESS_S = 20.0
PRESSES = (("UP", (0,), ("up",)), ("DOWN", (1,), ("down",)), ("LEFT", (2,), ("left",)),
           ("RIGHT", (3,), ("right",)), ("A", (4,), ("a",)), ("B", (5,), ("b",)),
           ("SELECT + A", (6, 4), ("select", "x")), ("SELECT + B", (6, 5), ("select", "y")))


def _ask(text):
    sys.__stdout__.write("\n>>> %s\n" % text)
    sys.__stdout__.flush()


@pytest.mark.skipif(not HUMAN, reason="a person presses the pad: MOYBYTE_CORES3_HUMAN=1")
@pytest.mark.parametrize("label,bits,held", PRESSES, ids=[p[0] for p in PRESSES])
def test_a_press_on_the_pad_reaches_the_console(board, label, bits, held):
    """Each button, held, is in the Gamepad3's byte (active low) and in the
    console's held set the frame reads; Select is the shift for x and y. Start
    is left out: held, it opens the task manager."""
    _ask("press and hold %s on the gamepad" % label)
    probe = ("(lambda g: (g.raw, [n for n in %r if ws.input.held(n)]))"
             "(__import__('moy_input').gamepad())" % (held,))
    end = time.time() + PRESS_S
    got = None
    while time.time() < end:
        raw, names = board.pyval(probe, strict=True)
        if all(not raw & (1 << b) for b in bits):
            got = (raw, names)
            if sorted(names) == sorted(held):
                break
        time.sleep(0.05)
    _ask("let go")
    assert got is not None, "no %s press in %.0f s" % (label, PRESS_S)
    assert sorted(got[1]) == sorted(held), (label, "0x%02x" % got[0], got[1])
    end = time.time() + PRESS_S
    while time.time() < end and board.pyval("__import__('moy_input').gamepad().raw",
                                            strict=True) != 0xFF:
        time.sleep(0.05)


def test_the_led_bar_is_a_processs_and_dark_when_it_ends(board):
    """The bar through the `leds` device API (native/moy_leds over the
    board's hooks): ten LEDs, a process holds them and lights them, another is
    refused, and its end -- the sweep every process end runs -- turns them
    dark and lets them go."""
    import errno
    got = board.pyval(
        "(lambda N, L, M: (lambda a, b: (N.count(), N.fill(a, 0x000010), N.owner() == a,"
        " N.open(b), (M.end(a), N.owner())[1], (lambda buf: (N.shown(buf), bytes(buf))[1])"
        "(bytearray(30))))(L.spawn('t.leds.a'), L.spawn('t.leds.b')))"
        "(__import__('moy_leds'), __import__('moy_log'), __import__('moybyte'))",
        timeout=20, strict=True)
    count, filled, held, other, after, shown = got
    assert count == 10 and filled == 0 and held is True, got
    assert other == -errno.EBUSY, got
    assert after == 0 and shown == bytes(30), got


def test_the_hints_show_the_pads_keys(board):
    """The pad is the input from boot, so the hints draw its keys (Select the
    shift for the tabs and the more menu, moy_pad3.c and mpconfigboard.h)."""
    assert board.pyval("__import__('ui_draw').hint_kind()", strict=True) == "pad"


def test_the_touch_controller_answers(board):
    """The FT6336U at 0x38, the console's pointer."""
    assert board.pyval(C3 + ".reg(0x38, 0xA8, 1)", strict=True) is not None


def test_the_battery_reads_the_axp2101(board):
    """pmic() is (level, charging, vbus, mv): no cell reads None for both the
    level and the voltage, never 0; the bar's battery follows it."""
    lvl, charging, vbus, mv = board.pyval(C3 + ".pmic()", strict=True)
    assert vbus is True, "the board is on its USB cable"
    if lvl is None:
        assert mv is None and charging is False
    else:
        assert 0 <= lvl <= 100 and 2500 <= mv <= 4400, (lvl, mv)
    # The bar's reading is cached for battery.REFRESH_MS: a charging cell can
    # step once between the two reads.
    bar = board.pyval("ws.battery.level()", strict=True)
    assert (bar is None) == (lvl is None) and (lvl is None or abs(bar - lvl) <= 1), (bar, lvl)


def test_an_ntp_answer_reaches_the_clock_chip(board):
    """With the network up the clock is synced, and the answer went to the
    BM8563 (moy_board_rtc_set), so the next boot starts on it."""
    if board.pyval("__import__('moy_net').clock_state()", strict=True) != 1:
        pytest.skip("no NTP answer this power-on (no network saved?)")
    chip = board.pyval(C3 + ".rtc()", strict=True)
    assert chip is not None and abs(chip - time.time()) < 120, (chip, time.time())


def test_the_clock_chip_keeps_the_time(board):
    """The BM8563 takes what NTP answers (moy_board_rtc_set) and the boot
    reads it back (clock_restore); set here to the host's UTC, as an NTP
    answer would."""
    now = int(time.time())
    board.pyval(C3 + ".rtc_set(%d) or 1" % now, strict=True)
    got = board.pyval(C3 + ".rtc()", strict=True)
    assert got is not None and abs(got - now) <= 3, (got, now)


def test_the_amplifier_is_up_and_named(board):
    """The AW88298 on the bus (its ID 0x1852) with its I2S running at the
    console's rate once audio has started."""
    ident = board.pyval(C3 + ".reg(0x36, 0x00, 2)", strict=True)
    assert ident == b"\x18\x52" or list(ident) == [0x18, 0x52], ident


def test_the_microphone_reads_samples(board):
    """The ES7210 through the kernel's mic driver (duplex on the speaker's
    I2S), read over its lease by the shell's `mic read`: a quarter second of
    PCM16 at its rate."""
    st, out = on_glass._sh(board, "mic")
    assert st == 0 and out and out[0].startswith("rate "), (st, out)
    rate = int(out[0].split()[1])
    assert rate > 0, out
    st, out = on_glass._sh(board, "mic read 250 | wc -c", timeout=20)
    assert st == 0, (st, out)
    assert int(out[-1].split()[0]) >= rate // 4 * 2 * 9 // 10, (rate, out)


def test_the_led_bar_takes_a_frame_and_goes_dark(board):
    """The Faces Bottom3's ten SK6812s take a frame and the dark one the boot
    writes; nothing reads them back, so this pins the call, not the light."""
    assert board.pyval(C3 + ".BAR_LEDS", strict=True) == 10
    board.pyval(C3 + ".leds(bytes(30)) or 1", strict=True)
    board.pyval(C3 + ".leds(b'') or 1", strict=True)


# -- the bodies every fullscreen board shares ------------------------------------


def test_state_snapshot_has_the_fullscreen_tier_shape(board):
    on_glass.fullscreen_tier_state(board)


def test_wifi_status_is_readable(board):
    on_glass.wifi_status_is_readable(board)


def test_the_kernel_verifies_a_signed_manifest(board):
    on_glass.the_kernel_verifies_a_signed_manifest(board)


def test_the_internal_volume_is_the_kernels(board):
    on_glass.the_internal_volume_is_the_kernels(board)


def test_wifi_is_off_at_rest(board):
    on_glass.wifi_is_off_at_rest(board)


def test_every_system_app_claims_exactly_one_cart(board):
    on_glass.every_app_claims_one_cart(board)


def test_py_probe_reaches_the_live_console(board):
    on_glass.py_probe_reaches_the_console(board)


def test_the_log_word_reads_the_ring(board):
    on_glass.the_log_word_reads_the_ring(board)


def test_the_shell_answers_over_serial(board):
    on_glass.the_shell_answers_over_serial(board)


def test_the_clock_syncs_when_the_network_comes_up(board):
    on_glass.the_clock_syncs_when_the_network_comes_up(board)


def test_pkg_installs_a_cart_from_the_carts_repo(board):
    on_glass.pkg_installs_a_cart_from_the_carts_repo(board)


def test_ota_verification_is_fast_enough(board):
    on_glass.ota_verification_is_fast_enough(board)


def test_the_ota_updater_is_live_on_this_board(board):
    # Staged on the card when the card is the store (moy_ota.UPDATE_DIR), else in flash.
    on_card = board.pyval("ws.carts_root").startswith("/sd/")
    on_glass.ota_updater_is_live(board, "cores3", saw_boot=False,
                                 update_dir="/sd/update" if on_card else "/moy/update")


def test_rollback_confirm_comes_from_the_frame_loop(board):
    on_glass.rollback_confirm_comes_from_the_frame_loop(board)


def test_the_web_console_add_on_fits_this_image(board):
    on_glass.web_console_add_on_fits_the_image(board)


def test_the_board_serves_its_web_console(board):
    """`web` serves the browser console from this board over the network it
    joined: the page answers a GET from this machine, then the service goes
    off again as the console was found."""
    import urllib.request
    if board.pyval("__import__('moy_net').page_state()", strict=True) != 3:   # MOY_PAGE_READY
        pytest.skip("no browser console add-on that fits this image on the board")
    line = board.cmd("web", wait_for="WEB ", timeout=60)
    assert line is not None and "http" in line, line
    url = line.split()[1]
    base = url.split("#")[0].split("?")[0]
    try:
        with urllib.request.urlopen(base, timeout=20) as r:
            body = r.read(4096)
            assert r.status == 200, r.status
        assert b"<" in body, body[:80]
    finally:
        board.pyval("ws.webhost.serving and ws.web.toggle() or 1", timeout=20)


def test_a_leaked_session_leaves_the_panel_flushing(board):
    on_glass.a_leaked_session_leaves_the_panel_flushing(board)


def test_diag_toggle_roundtrips(board):
    on_glass.diag_toggle_roundtrips(board)


def test_a_cart_runs_and_exits(board):
    on_glass.cart_runs_and_exits(board, "star", "Star Catcher")


def test_draw_gates_are_installed(board):
    on_glass.draw_gates_are_installed(board)


def test_idle_screen_blank_and_wake(board):
    on_glass.idle_blank_and_wake(board)
    on_glass.idle_timeout_restored(board)


def test_a_card_transfer_takes_no_memory_of_its_own(board):
    on_glass.sd_card_io_allocates_nothing(board, on_glass.SD_INTERNAL_DMA)


def test_mem_reports_the_heap(board):
    on_glass.mem_reports_the_heap(board)


def test_the_frame_is_the_kernels(board):
    on_glass.the_frame_is_the_kernels(board)


def test_perf_line_is_the_one_format(board):
    """A fullscreen S3 runs no window manager and no PPA: those fields read
    `-`, absence, never 0."""
    got = on_glass.perf_line_is_the_one_format(board)
    for name in ("wmr", "wmw", "wms", "ppa", "fence_ms", "gfence_ms"):
        assert got[name] is None, (name, got[name])


def test_the_kernel_lit_the_logo_before_any_vm(board):
    on_glass.the_kernel_lit_the_logo(board)


def test_loop_is_the_kernels_line_with_every_stage(board):
    on_glass.loop_line_is_the_kernels(board)
