"""On-glass Elecrow CrowPanel Advance 10.1" P4 console tests: drive the real board.

Gated: they run only when MOYBYTE_ELECROW_P4_PORT is set (e.g.
`MOYBYTE_ELECROW_P4_PORT=/dev/ttyUSB0 .venv/bin/python -m pytest
tests/test_elecrow_p4_on_glass.py -v`) -- the port checklist's stage-6 exit
criterion (docs/board_ports_2026-08.md) for the third ESP32-P4 board.

The board is the Waveshare 7B's tier on a bigger glass: the same 1024x600
windowed desk over the PPA composite, the same GT911, and the same UART
console through a CH340K with no flow control, so its `[serial]` block does
not declare `attach_only` and the suite RESETS the board at open and leaves it
freshly booted on the desk (a reset survives on an external bridge). What is
shared with every board lives in tests/on_glass.py, and the idle-SRAM
baseline is the Waveshare's (same silicon, same kernel, same patch ladder),
which `test_p4_on_glass` derives; what is here is this board's -- its board
dir, its OTA id and its floors.
"""

import pytest

import on_glass
from on_glass import ROOT

PORT, pytestmark = on_glass.gate("MOYBYTE_ELECROW_P4_PORT", "the Elecrow P4")

BOARD_DIR = ROOT / "firmware" / "elecrow_crowpanel_p4_10_1"
BOARD_ID = "elecrow_p4"


@pytest.fixture(scope="module")
def board():
    with on_glass.session(
            PORT,
            board_dir=ROOT / "firmware" / "elecrow_crowpanel_p4_10_1") as b:
        b.cmd("diag 1")            # this suite asserts PERF lines flow
        yield b
        # Leave the board freshly booted on the desk for a human: its bridge
        # is external, so a reset keeps the port.
        b.ser.write(b"\r\x03")
        b.drain(0.5)
        b.ser.write(b"\x04")
        b.drain(1.0)


# The engine's idle cost (docs/history/wasm_tier_plan_2026-09.md, guard 1),
# FIRST in the file on purpose: the comparison is against a fresh boot, and
# the wasm block at the end brings the radios up.
WASM_BOARD_DIR = BOARD_DIR

# (free, largest block) of internal SRAM on this board's idle desk, read on a
# fresh boot with no radio up (three boots, identical): the add-on step holds
# the radio only where there is something to fetch, so a card in the slot or an
# add-on already in the store leaves the guard below to compare, where it
# skips a desk whose WiFi came up. It bounds this image's growth.
WASM_IDLE_BASELINE = (276283, 188416)

# This board's store is the 2.7 MB tail of a 16 MB flash and the seeds take 1.4
# MB of it, so the compiled-cart fixtures cannot all stay: before a test, a
# store with less than STORE_ROOM_BLOCKS free (4 KiB each: the showcase's 150
# is the biggest fixture) is given back, and the fixtures below are scoped to
# the test, which pushes what it needs again (files already there are skipped).
STORE_ROOM_BLOCKS = 160


@pytest.fixture(autouse=True)
def store_room(board):
    on_glass.store_room(board, STORE_ROOM_BLOCKS)


def test_the_wasm_engine_costs_the_idle_desk_at_most_a_constant(board):
    on_glass.wasm_idle_cost_is_bounded(board, WASM_IDLE_BASELINE,
                                       ble_at_boot=True)

@pytest.fixture
def wasm(board):
    return on_glass.wasm_push(board, WASM_BOARD_DIR)


# The rest of the engine's checks that bring no radio up, while the desk is
# still fresh: the Lua guard in particular needs an internal heap the radios
# have not spent, or its control run falls back to PSRAM by itself.


def test_the_hello_module_runs_and_foreign_modules_are_refused(board, wasm):
    on_glass.wasm_hello_runs_and_foreign_modules_are_refused(
        board, WASM_BOARD_DIR, wasm)


def test_consent_lets_only_a_missing_signature_through(board, wasm):
    on_glass.wasm_consent_lets_only_a_missing_signature_through(
        board, wasm)


def test_a_misaligned_load_or_store_of_any_width_is_exact(board, wasm):
    on_glass.wasm_misaligned_access_is_exact(board, wasm)


def test_a_saturating_float_to_int_conversion_is_exact(board, wasm):
    on_glass.wasm_saturating_conversions_are_exact(board, wasm)


def test_the_run_stack_works_in_psram_and_internal_sram(board, wasm):
    on_glass.wasm_run_stack_placements(board, wasm)


def test_terminate_reaches_a_runaway_only_at_its_end(board, wasm):
    on_glass.wasm_runaway_runs_to_its_end(board, wasm)


def test_a_lua_cart_after_a_wasm_run_keeps_its_sram(board, wasm):
    on_glass.wasm_lua_after_wasm_keeps_its_sram(board, wasm)


# -- the Player path (docs/history/wasm_tier_plan_2026-09.md, phase 3) ---------------
# Compiled carts from the launcher, WiFi off -- the state a cart plays in, so
# before the radio guards. The floors are this board's median drawn fps
# measured on 2026-09-25, less a margin; the measurements are the owner's to
# post, and native/moy_wasm/README.md states the per-board ceiling.
WASM_HELLO_FPS_FLOOR = 27
WASM_BLIT_FPS_FLOOR = 50


@pytest.fixture
def wasm_carts(board):
    return on_glass.wasm_carts_push(board, WASM_BOARD_DIR)


def test_a_compiled_app_reaches_its_roles_through_imports(board):
    root = on_glass.wasm_app_push(board, WASM_BOARD_DIR)
    try:
        on_glass.wasm_app_reaches_its_roles(board, root)
    finally:
        on_glass.remove_carts(board, on_glass.WASM_APPS)


def test_a_compiled_app_draws_the_toolkits_widgets(board):
    root = on_glass.wasm_app_push(board, WASM_BOARD_DIR)
    try:
        on_glass.wasm_app_draws_the_toolkit(board, root)
    finally:
        on_glass.remove_carts(board, on_glass.WASM_APPS)


def test_the_hello_wasm_cart_holds_its_floor(board, wasm_carts):
    on_glass.wasm_cart_holds_its_floor(board, wasm_carts["hello"],
                                       WASM_HELLO_FPS_FLOOR,
                                       check=on_glass.hello_read_its_greeting)


def test_a_full_frame_blit_cart_holds_its_floor(board, wasm_carts):
    on_glass.wasm_cart_holds_its_floor(board, wasm_carts["blit"],
                                       WASM_BLIT_FPS_FLOOR)


# par (moy-spec SPEC.md §16.10): a compiled cart's items on this board's
# second core leave exactly what running them in order leaves, each on its
# own stack, and the board's one lane runs some of them.
def test_par_items_across_the_cores_match_them_in_order(board, wasm_carts):
    on_glass.wasm_par_matches_items_in_order(board, lanes=1)


# A palette frame stays the blit's on a P4 (ESP-IDF disables the PPA's
# palette mode); a direct-colour one goes to the glass from the cart's memory
# (the Jet section below), and the board says it lacks the frame fold by
# absence.
def test_a_compiled_carts_palette_frames_are_written_into_the_canvas(board, wasm_carts):
    on_glass.p4_palette_frames_keep_the_blit(board, wasm_carts["blit"])


def test_a_compiled_cart_with_no_module_runs_on_the_interpreter(board, wasm_carts):
    on_glass.wasm_no_module_at_all_runs_on_the_interpreter(board, WASM_BOARD_DIR)


def test_a_module_for_another_chip_runs_on_the_interpreter(board, wasm_carts):
    on_glass.wasm_a_module_for_another_chip_runs_on_the_interpreter(board, WASM_BOARD_DIR)


def test_a_stale_format_module_runs_on_the_interpreter(board, wasm_carts):
    on_glass.wasm_stale_format_module_runs_on_the_interpreter(board, WASM_BOARD_DIR)


def test_a_compiled_cart_whose_module_was_tampered_with_is_refused(board, wasm_carts):
    on_glass.wasm_tampered_module_is_refused(board, WASM_BOARD_DIR)


def test_an_unsigned_cart_runs_natively_only_with_native_granted(board, wasm_carts):
    on_glass.wasm_unsigned_cart_follows_its_consent(board, WASM_BOARD_DIR)


def test_a_compiled_cart_too_big_for_the_board_opens_the_notice(board, wasm_carts):
    on_glass.wasm_too_big_cart_opens_the_notice(board, WASM_BOARD_DIR)


def test_a_compiled_cart_for_a_newer_console_opens_the_notice(board, wasm_carts):
    on_glass.wasm_newer_cart_opens_the_notice(board, WASM_BOARD_DIR)


def test_a_trap_in_init_is_the_carts_own_error(board, wasm_carts):
    on_glass.wasm_init_trap_is_the_carts_own_error(board, WASM_BOARD_DIR)


def test_a_compiled_cart_out_of_native_stack_traps_with_its_numbers(board, wasm_carts):
    on_glass.wasm_deep_recursion_traps_with_its_numbers(board, WASM_BOARD_DIR)


def test_a_folder_in_the_cart_reads_as_a_missing_file(board, wasm_carts):
    on_glass.wasm_read_of_a_folder_reads_nothing(board, WASM_BOARD_DIR)


def test_a_compiled_carts_written_files_outlive_its_session(board, wasm_carts):
    on_glass.wasm_written_files_outlive_the_session(board, WASM_BOARD_DIR)


# The compiled tier's showcase, Jet Teapot (ports/jet/README.md), from the
# launcher: uncapped with WiFi off, in Phong -- the costliest of its three
# shadings and the steadiest to measure -- at half and at full width. The
# floors sit about a fifth under what this board drew, its raster on both
# cores, when they were set (2026-10-01); the figures are #158's. The cart stays installed as it ships.
JET_HALF_FPS_FLOOR = 27
JET_FULL_FPS_FLOOR = 22


def test_the_jet_showcase_holds_its_floor_at_half_width(board):
    on_glass.jet_holds_its_floor(board, WASM_BOARD_DIR, JET_HALF_FPS_FLOOR,
                                 width="half", shading="phong")


def test_the_jet_showcase_holds_its_floor_at_full_width(board):
    on_glass.jet_holds_its_floor(board, WASM_BOARD_DIR, JET_FULL_FPS_FLOOR,
                                 shading="phong")


# Its blit565 frames go to the glass from the cart's memory: the PPA scales
# them from there and the GDMA snapshots each into the run's scratch, and
# nothing writes them into the game canvas (device/p4_canvas.py).
def test_the_showcases_frames_go_to_the_glass_from_the_cart(board):
    on_glass.jet_push(board, WASM_BOARD_DIR)
    on_glass.p4_compiled_frames_go_to_the_glass_from_the_cart(
        board, on_glass.JET_TITLE, glass=True)


# A fullscreen compiled play runs in the kernel's front with the VM up: the
# same scale and snapshot, in C (moy_glass.front's frame op), and the glass
# holds the scale of the copy the front kept, byte for byte.
def test_a_compiled_run_shows_its_frames_in_front(board):
    on_glass.jet_push(board, WASM_BOARD_DIR)
    on_glass.a_compiled_run_shows_its_frames_in_front(board, on_glass.JET_TITLE, "dsi")


# Doom, built by the recipe (experiments/wasm_aot/doom/): its frames are the
# host's, and the run's median drawn fps holds a floor about a fifth under
# what this board drew when it was set (2026-09-28, the figures are #158's).
# Skips until the developer has built the cart, which is never in the
# repository or CI.
DOOM_FPS_FLOOR = 32


def test_doom_frames_match_the_host(board):
    on_glass.doom_frames_match_the_host(board, WASM_BOARD_DIR,
                                        floor=DOOM_FPS_FLOOR)


# No doom1.wad-sized push (the Waveshare's regression for the raw upload on its
# UART): this board's internal store is the 2.7 MB tail of a 16 MB flash, so
# a 4 MB file cannot fit and the refusal leaves a partial file behind.


def test_boots_to_the_desk(board):
    st = board.state()
    assert st.get("desk") is True
    assert not st.get("order")


def test_wifi_status_is_readable(board):
    on_glass.wifi_status_is_readable(board)


def test_the_kernel_verifies_a_signed_manifest(board):
    on_glass.the_kernel_verifies_a_signed_manifest(board)


def test_the_internal_volume_is_the_kernels(board):
    on_glass.the_internal_volume_is_the_kernels(board)


def test_wifi_is_off_at_rest(board):
    on_glass.wifi_is_off_at_rest(board)


def test_the_bar_wifi_widget_opens_the_wifi_panel(board):
    on_glass.the_bar_wifi_widget_opens_the_wifi_panel(board)


def test_appearance_cart_is_claimed(board):
    on_glass.appearance_cart_is_claimed(board)


def test_every_system_app_claims_exactly_one_cart(board):
    """The same identity check for every registered app, not just Appearance."""
    on_glass.every_app_claims_one_cart(board)


def test_leaving_paint_saves_a_stroke(board):
    """A stroke on a blank page, then home: saved, read back, no reset."""
    on_glass.paint_saves_a_stroke_on_leaving(board)


def test_open_settings_window(board):
    board.open("settings")
    board.drain(0.5)
    st = board.state()
    assert "settings" in st.get("order", ())


def test_settings_rows_scroll_on_swipe(board):
    on_glass.settings_rows_scroll_on_swipe(board)


def test_scroll_survives_release(board):
    on_glass.scroll_survives_release(board)


def test_appearance_opens(board):
    line = board.open("appearance")
    board.drain(0.5)
    st = board.state()
    assert "appearance" in st.get("order", ()), (line, st.get("order"))


def test_projects_opens(board):
    board.open("projects")
    board.drain(6.0)              # first-open cover pop-in settles
    st = board.state()
    assert "projects" in st.get("order", ())


def test_play_parks_the_windows_and_the_back_brings_them_back(board):
    on_glass.play_parks_the_windows_and_the_back_brings_them_back(board)


def test_window_buffers_are_single_retained_surfaces(board):
    on_glass.window_buffers_are_single_retained_surfaces(board)


def test_draw_gates_are_installed(board):
    on_glass.draw_gates_are_installed(board, windowed=True)


def test_draw_gates_take_the_traffic(board):
    on_glass.draw_gates_take_the_traffic(board, windowed=True)


def test_py_probe_reaches_the_live_console(board):
    on_glass.py_probe_reaches_the_console(board)


def test_the_log_word_reads_the_ring(board):
    on_glass.the_log_word_reads_the_ring(board)


def test_the_shell_answers_over_serial(board):
    on_glass.the_shell_answers_over_serial(board)


def test_wasi_commands_run_in_the_shell(board):
    on_glass.wasi_commands_run(board, WASM_BOARD_DIR)


def test_elf_commands_run_in_the_shell(board):
    on_glass.elf_commands_run(board, WASM_BOARD_DIR)


def test_elf_modules_run_isolated_in_u_mode(board):
    on_glass.elf_umode_isolates(board, WASM_BOARD_DIR)


def test_pkg_installs_a_cart_from_the_carts_repo(board):
    on_glass.pkg_installs_a_cart_from_the_carts_repo(board)


def test_the_clock_syncs_when_the_network_comes_up(board):
    on_glass.the_clock_syncs_when_the_network_comes_up(board)


def test_an_alarm_wakes_the_screen_and_at_logs(board):
    on_glass.an_alarm_wakes_the_screen_and_at_logs(board)


def test_the_event_rings_keep_their_records(board):
    on_glass.the_event_rings_keep_their_records(board)


def test_a_gpio_lease_loses_no_tap(board):
    on_glass.a_gpio_lease_loses_no_tap(board, BOARD_DIR.name)


def test_a_lease_runs_a_driver_and_a_crash_leaves_it_safe(board):
    on_glass.a_lease_runs_a_driver_and_a_crash_leaves_it_safe(board, BOARD_DIR.name)


def test_the_scheduler_stops_a_runaway_service(board):
    on_glass.the_scheduler_stops_a_runaway_service(board)


def test_a_lua_service_runs_on_a_task_of_its_own(board):
    on_glass.a_lua_service_runs_on_a_task_of_its_own(board)


def test_a_lua_app_s_every_runs_beside_a_python_app_s(board):
    on_glass.a_lua_app_s_every_runs_beside_a_python_app_s(board)


def test_an_asyncio_service_runs_beside_the_desk(board):
    on_glass.an_asyncio_service_runs_beside_the_desk(board)


def test_an_on_crash_service_restarts_after_a_forced_crash(board):
    on_glass.an_on_crash_service_restarts_after_a_forced_crash(board)


def test_the_painter_matches_the_host(board):
    on_glass.painter_matches_host(board)


def test_the_sprites_match_the_host(board):
    on_glass.sprites_match_host(board)


def test_the_picker_kernel_matches_sspr(board):
    on_glass.picker_kernel_matches_sspr(board)


def test_shift_last_and_copy_last_into_match_the_reference(board):
    on_glass.shift_last_matches_the_reference(board, p4=True)


def test_a_fuzzed_font_corpus_loads_as_on_the_host(board):
    on_glass.fonts_match_host(board)


def test_a_fuzzed_layout_corpus_reads_as_on_the_host(board):
    on_glass.layouts_match_host(board)


def test_custom_themes_derive_as_on_the_host(board):
    on_glass.theme_custom_matches_host(board)


def test_the_theme_font_is_installed(board):
    on_glass.the_theme_font_is_installed(board)


def test_the_font_set_is_the_tiers(board):
    on_glass.the_font_set_is_the_tiers(board, BOARD_DIR.name)


def test_the_glyph_lane_draws_the_hosts_bytes(board):
    on_glass.glyph_lane_matches_host(board, 'desktop')


def test_a_stale_handle_is_refused_loudly(board):
    on_glass.stale_handle_is_refused_loudly(board)


def test_diag_toggle_roundtrips(board):
    on_glass.diag_toggle_roundtrips(board)


def test_mem_reports_the_heap(board):
    on_glass.mem_reports_the_heap(board)


def test_a_quiet_console_collects_its_garbage(board):
    on_glass.a_quiet_console_collects_its_garbage(board)


def test_a_quiet_console_leaves_a_live_heap_alone(board):
    on_glass.a_quiet_console_leaves_a_live_heap_alone(board)


def test_the_saver_comes_and_its_wake_repaints(board):
    on_glass.idle_saver_and_wake(board)


def test_internal_flash_commits_under_a_running_cart(board):
    ms = on_glass.internal_flash_commits_under_a_cart(board)
    print("\nlongest internal-flash commit under a cart: %d ms" % ms)


def test_the_frame_is_the_kernels(board):
    on_glass.the_frame_is_the_kernels(board)


def test_no_display_underruns(board):
    on_glass.display_underruns_are_zero(board)


def test_window_chrome_freezes_during_a_content_scroll(board):
    on_glass.window_chrome_freezes_during_a_content_scroll(board)


def test_perf_lines_flow(board):
    """One format on every board (#206 item 2), plus the column only this one
    can fill: the async-PPA overlap counters.

    The windowed WM's pass split (wmr/wmw/wms) moved to its own test below. It
    was asserted here as "not None" against whatever line an IDLE desk happened
    to emit, and since `c95bf89` those meters are TAKEN -- so a sample in which
    the WM drew nothing reads `-`, which is the honest answer and was being read
    as a regression."""
    got = on_glass.perf_line_is_the_one_format(board)
    assert isinstance(got["ppa"], tuple) and len(got["ppa"]) == 5, got
    assert got["ppa"][4] == 0, "PPA timeouts must stay 0: %r" % (got["ppa"],)


def test_the_wm_meters_answer_for_the_frame_they_measured(board):
    on_glass.wm_meters_answer_for_the_frame_they_measured(board)


def test_a_drag_touches_no_storage_and_rebuilds_no_cache(board):
    on_glass.a_drag_touches_no_storage_and_rebuilds_no_cache(board)


def test_idle_screen_blank_and_wake(board):
    """The #58 power save: the panel blanks after an idle timeout and any input
    wakes it, while the loop, the cart and this very serial channel stay live.

    The shared body is the blank/wake/`power off` trio every board runs; what
    is this board's is the tail -- 0 disables the timer outright, which the S3
    suites do not pin."""
    on_glass.idle_blank_and_wake(board)

    # 0 disables it outright: no blank, however long the silence.
    board.cmd("power 0", wait_for="REMOTE power")
    board.drain(6.0)
    line = board.cmd("power", wait_for="REMOTE power")
    assert "asleep=False" in line, "a disabled timer still blanked: %r" % line
    board.cmd("power 300", wait_for="REMOTE power")     # restore the default


# -- the OTA manifest verifier, in the kernel (#53, #224) ----------------------
#
# The verifier is native/moy_net/moy_ota.c's: the canonical text, SHA-256 and
# the RSA-2048 modexp in C. The host suite runs the same C over net_binding;
# every console's suite runs the image's own build of it
# (on_glass.the_kernel_verifies_a_signed_manifest), and this one times it.

def test_verification_is_fast_enough_to_not_think_about(board):
    on_glass.ota_verification_is_fast_enough(board)


def test_the_ota_updater_is_live_on_this_board(board):
    on_glass.ota_updater_is_live(board, BOARD_ID)


def test_the_rollback_confirm_comes_from_the_frame_loop(board):
    on_glass.rollback_confirm_comes_from_the_frame_loop(board)


def test_a_pending_marker_becomes_a_verdict_on_this_board(board):
    on_glass.pending_marker_becomes_a_verdict(board)


# -- the browser console baked into the image (moy_web) -----------------------


def test_the_cart_store_is_the_card_when_one_mounted(board):
    on_glass.cart_store_follows_the_card(board)


def test_a_card_transfer_takes_no_memory_of_its_own(board):
    on_glass.sd_card_io_allocates_nothing(board, on_glass.SD_PSRAM, saves=False)


def test_the_web_console_add_on_fits_this_image(board):
    on_glass.web_console_add_on_fits_the_image(board)


def test_a_lua_cart_runs_and_exits(board):
    """The Lua tier reaches every board by default; pin it with a real run."""
    on_glass.cart_runs_and_exits(board, "sakura lua", title="Sakura Lua",
                                 door="shell", clear=3)


def test_a_cart_runs_and_exits(board):
    """The desk tier's door: ws.spine.exit() out, not the cart-quit flag. A `run`
    from the tour's projects arrangement opens the cart under it, where the
    first draft's cart-quit exit did not pop -- so this board pins the launch
    and the shell's own close, while the fullscreen tiers pin the kid-facing
    flag."""
    on_glass.cart_runs_and_exits(board, "star", door="shell", clear=3)


@pytest.mark.parametrize("spec,title", on_glass.VM_FREE_SEEDS)
def test_a_vm_free_frame_makes_no_crossing(board, spec, title):
    on_glass.a_vm_free_frame_makes_no_crossing(board, spec, title, door="shell",
                                               clear=3)


@pytest.mark.parametrize("spec,title", on_glass.VM_FREE_SEEDS)
def test_a_front_run_makes_no_crossing(board, spec, title):
    on_glass.a_front_run_makes_no_crossing(board, spec, title, clear=3)


# The compiled half of the same check: the blit fixture's frames run in the
# kernel's Player on the engine's thread, and neither its frames nor its run's
# books since launch hold an APP, SERVICE or REFUSED crossing; the hello
# fixture reads its greeting from its own folder at _init, in C.
@pytest.mark.parametrize("which", ("blit", "hello"))
def test_a_compiled_frame_makes_no_crossing(board, wasm_carts, which):
    title = wasm_carts[which]
    on_glass.a_vm_free_frame_makes_no_crossing(board, title.lower(), title,
                                               door="shell", clear=3, runtime="wasm")


# The runaway watch (native/moy_play/moy_play.h): a frame that never comes
# back is ended, Lua on its line and a compiled cart at its next import call.
@pytest.fixture
def stuck_carts(board):
    on_glass.stuck_carts_push(board, WASM_BOARD_DIR)


@pytest.mark.parametrize("runtime", ("lua", "wasm"))
def test_a_frame_that_never_ends_is_ended(board, stuck_carts, runtime):
    on_glass.a_stuck_run_is_ended(board, runtime)


# A Lua app on the UI tree: the image's frozen layer over the C engine.
@pytest.fixture
def tree_form(board):
    on_glass.tree_form_push(board, WASM_BOARD_DIR)


def test_a_lua_tree_app_runs_on_the_engine(board, tree_form):
    on_glass.a_lua_tree_app_runs_on_the_engine(board)


# The timed lanes (native/moy_wasm/moy_wasm_session.h): moy_audio and moy_timer
# run on their own core, AOT and interpreted, and a lane that spins is struck
# at its deadline, the ring muted, the cart running on.
@pytest.fixture
def lanes_carts(board):
    on_glass.lanes_carts_push(board, WASM_BOARD_DIR)


@pytest.mark.parametrize("runaway", (False, True))
@pytest.mark.parametrize("tier", ("aot", "interp"))
def test_a_cart_s_timed_lanes_run_and_a_runaway_is_struck(board, lanes_carts, tier, runaway):
    on_glass.timed_lanes_run(board, tier, runaway)


# -- the engine's radio guards (docs/history/wasm_tier_plan_2026-09.md, phase 1) ------
# LAST in the file: both bring WiFi up (released again) and the second starts
# BLE, and the WiFi driver keeps its internal RAM for the rest of the boot.


def test_load_unload_loop_under_a_live_cart_and_wifi(board, wasm):
    on_glass.wasm_load_unload_under_flush_and_wifi(board, wasm)


def test_a_run_with_wifi_and_ble_up_costs_at_most_a_constant(board, wasm):
    on_glass.wasm_low_water_with_radios_up(board, wasm)


def test_the_kernel_lit_the_logo_before_any_vm(board):
    on_glass.the_kernel_lit_the_logo(board)


def test_heapcaps_mem_and_hush_are_the_kernels_words(board):
    on_glass.board_words_are_the_kernels(board)


def test_loop_is_the_kernels_line_with_every_stage(board):
    on_glass.loop_line_is_the_kernels(board)


def test_a_ctrl_c_ends_a_run_in_front_and_reaches_the_repl(board):
    on_glass.a_ctrl_c_ends_a_front_run(board, clear=3)


def test_bluetooth_stops_and_starts_again(board):
    on_glass.ble_stops_and_starts_again(board)


# LAST in the file: twenty soft resets end on a freshly started VM.
def test_twenty_soft_resets_leave_psram_flat(board):
    on_glass.soft_resets_leave_psram_flat(board, n=20)
