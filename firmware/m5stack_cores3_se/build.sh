#!/usr/bin/env bash
# Moybyte M5Stack CoreS3 SE on MAINLINE MicroPython: the T-Deck's build with
# this board's facts. The shared half is tools/esp32_build_lib.sh; what is here
# is the board's patch ladder -- the T-Deck's, since the panel is the same
# esp_lcd SPI path (native/moy_lcd), each patcher's why in its function -- and
# its sdkconfig facts.
#
#   ./build.sh
#   tools/board_flash.py flash firmware/m5stack_cores3_se --port /dev/ttyACM0
#
# The flash drives the board into the ROM loader itself (board.toml's [flash]
# `before = "usb_reset"`); holding the reset button about 3 s until the green
# LED lights is the manual way (README.md).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BUILD_DIR="${SCRIPT_DIR}/.build"
MPY_DIR="${BUILD_DIR}/micropython"
BOARD="MOYBYTE_CORES3"
BOARD_DIR="${SCRIPT_DIR}/boards/${BOARD}"
DIST_DIR="${REPO_ROOT}/dist/cores3"
PATCH_DIR="${REPO_ROOT}/patches"
MODULES_DIR="${SCRIPT_DIR}/modules"
MANIFEST="${BUILD_DIR}/moybyte_cores3_manifest.py"

source "${REPO_ROOT}/tools/esp32_build_lib.sh"
moybyte_resolve_build_python

mkdir -p "${BUILD_DIR}" "${DIST_DIR}"

moybyte_clone_micropython
moybyte_setup_idf esp32s3 \
  "${REPO_ROOT}/firmware/esp32_p4_wifi6_touch_lcd_7b/.build/esp-idf"

# moy_lcd needs esp_lcd in the main component's REQUIRES (native/moy_lcd's
# micropython.cmake has why a usermod cannot ask for it).
moybyte_idf_component esp_lcd

moybyte_patch_repr_c
moybyte_patch_map_cache_for_repr_c
moybyte_patch_gc_run_hints
moybyte_patch_gc_meters
moybyte_patch_slice_store
moybyte_patch_fatfs_lfn
moybyte_patch_import_cache
moybyte_patch_map_load
moybyte_patch_gc_split_reserve
moybyte_patch_gc_grow_step

# The esp_lcd tx_color no-acquire patch (#66), the T-Deck's: the feeder's bands
# queue without re-acquiring the bus per band.
ESP_LCD_SPI_C="${IDF_DIR}/components/esp_lcd/spi/esp_lcd_panel_io_spi.c"
if [ -f "${ESP_LCD_SPI_C}" ] && ! grep -q "Moybyte #66" "${ESP_LCD_SPI_C}"; then
  echo "== applying esp_lcd tx_color no-acquire patch (#66)"
  patch -d "${IDF_DIR}" -p1 < "${PATCH_DIR}/esp_lcd_tx_color_noacquire.patch"
fi

moybyte_patch_native_code_free
moybyte_patch_usj_rx_init
moybyte_patch_pwm_ledc_book
moybyte_patch_mdns_psram

# The T-Deck's declines, for the T-Deck's reasons (the same chip and the same
# panel and card arrangement):
# DECLINED moybyte_patch_thread_state_tls -- the VM's thread state as a
# `__thread` variable. Measured on the P4s (RISC-V), where the TLS slot's
# lookup was ~5% of an Editor frame; on this Xtensa board it is unmeasured,
# and a board takes it when a profile here shows the same path.

# DECLINED moybyte_patch_usj_improv -- Improv's frames off the console: a
# console with a screen sets its Wi-Fi on glass
# (docs/web_console_online_2026-11.md §7).

# DECLINED moybyte_patch_tinyusb_msc_psram -- this board's MSC endpoint buffer
# is one 64-byte full-speed packet (native/moy_usbdisk/moy_tusb_config.h); its
# sector is already gathered in PSRAM.

# DECLINED moybyte_patch_p4_dsi_underrun -- an ESP32-P4 silicon patch (#106):
# the MIPI-DSI bridge-underrun ISR. This board has no DSI peripheral.

# DECLINED moybyte_patch_p4_ppa_srm_mb_order -- an ESP32-P4 silicon patch: the
# PPA SRM engine's macro-block-order bypass. This board has no PPA.

# DECLINED moybyte_patch_p4_coredump_dram -- an ESP32-P4 linker patch: the
# rev < v3 P4's high-SRAM data section. The S3's linker script has none.

# DECLINED moybyte_patch_p4_heap_low_sram -- an ESP32-P4 heap patch: the
# rev < v3 P4's low-SRAM heap priority. The S3 has no such region.

# DECLINED moybyte_patch_p4_ppa_trans_context -- an ESP32-P4 driver patch: the
# PPA's transaction elements. This board has no PPA.

# DECLINED moybyte_patch_p4_clk_switch -- an ESP32-P4 startup patch: the
# P4's CPU clock switch. This board is an ESP32-S3.

# DECLINED moybyte_patch_esp_hosted_bump -- the ESP-Hosted 2.12.12 bump. That
# component is the P4's radio: a C6 slave over SDIO. This board's WiFi and BLE
# are on-die, and nothing in its build pulls esp_hosted in at all.

# DECLINED moybyte_patch_lfs_sizes -- LittleFS sized for a flash store. The
# store is the SD card; the internal VFS it falls back to without one keeps the
# stock sizes, unmeasured here.

# DECLINED moybyte_patch_sdcard_runs -- machine.SDCard in multi-block runs.
# This board's card is not machine.SDCard, which hangs it by re-initialising the
# panel's SPI host: it is native/moy_sd, which moves its runs itself.

# DECLINED moybyte_patch_stdin_ring -- the 4 KB stdin ring for a UART console.
# This board's serial is the SoC's USB-Serial/JTAG, whose ISR takes only what
# the ring has room for while the USB host waits with the rest, so a heap
# collection costs it throughput and never a byte; the internal SRAM stays.

# DECLINED moybyte_patch_psram_retune -- the #169 temperature retune of the
# 120 MHz MSPI profile; this board's quad PSRAM runs at 80 MHz
# (sdkconfig.board), which needs none.

moybyte_stage_native
"${BUILD_PYTHON}" "${REPO_ROOT}/tools/board_config.py" stage "${SCRIPT_DIR}"
moybyte_stage_uitree_pages
moybyte_stage_uitree_lua
"${BUILD_PYTHON}" "${REPO_ROOT}/tools/gen_device_carts.py" --packed "${MODULES_DIR}/carts_data.py"
"${BUILD_PYTHON}" "${REPO_ROOT}/tools/make_font.py" module "${SCRIPT_DIR}" "${MODULES_DIR}/fonts_data.py"
moybyte_ota_identity cores3 "${REPO_ROOT}/device/moy_ota.py"
moybyte_frozen_manifest "${MANIFEST}"

moybyte_sdkconfig_guard "${BOARD_DIR}" \
  "${MPY_DIR}/ports/esp32/build-${BOARD}/sdkconfig"

moybyte_build_and_collect "${BOARD_PARTITION_CSV}" \
  moybyte_cores3 "full image, cable flash at 0x0"
