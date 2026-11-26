// Moybyte M5Stack CoreS3 SE (mainline MicroPython). Board facts, plus the
// MicroPython-level knobs sdkconfig cannot carry. The pins are board.toml's
// [hardware] rows (MOY_HW_*); everything tuned at the IDF level lives in
// sdkconfig.board beside this file. Where a knob is the T-Deck's for the T-Deck's
// reason (the other 320x240 S3 handheld), its verdict is in that board's
// mpconfigboard.h and is not repeated here.

#ifndef MICROPY_HW_BOARD_NAME
#define MICROPY_HW_BOARD_NAME               "Moybyte CoreS3 SE"
#endif
#define MICROPY_HW_MCU_NAME                 "ESP32S3"

// USB: the S3's USB-Serial/JTAG, not TinyUSB CDC, for the T-Deck's reason --
// with USBDEV on, the port drops the USB-Serial/JTAG ISR and the dev channel
// has no stdin.
#define MICROPY_HW_ENABLE_USBDEV            (0)
// UART0 (G43/G44) is the M-Bus's and the Grove port C's, not a REPL's.
#define MICROPY_HW_ENABLE_UART_REPL         (0)

// The card shares SPI2 with the panel and mounts through moy_sd's attach, never
// machine.SDCard (.claude/rules/boards.md).
#define MICROPY_HW_ENABLE_SDCARD            (0)
#define MICROPY_FATFS_EXFAT                 (1)
#define MICROPY_FATFS_REENTRANT             (1)
#define MICROPY_FATFS_ENABLE_LFN            (2)
#define MICROPY_FATFS_SYNC_T                uintptr_t

#define MICROPY_PY_MACHINE_I2S              (1)
// The Python heap's PSRAM reserve and growth step: the T-Deck's, over the same
// 8 MB (quad here, octal there).
#define MOYBYTE_GC_SPLIT_RESERVE            (3072 * 1024)
#define MOYBYTE_GC_GROW_MAX                 (512 * 1024)
#define MICROPY_PY_DEFLATE_COMPRESS         (1)
#define MICROPY_OPT_MAP_LOOKUP_CACHE_SIZE   (512)
#define MOY_WASM_STACK_BYTES                (16 * 1024)
#define MOY_WASM_STACK_PSRAM                (1)
#define MOY_SERIAL_RING_BYTES               (32768)

// The panel (native/moy_lcd): an ILI9342C on SPI2, landscape-native, its D/C
// on the bus's MISO pad (the spi2 row names no tft_dc), at M5GFX's 40 MHz
// write clock; the rails, its reset and its light are this board's own C
// (native/moy_cores3: the AXP2101 and the AW9523).
#define MOY_LCD_PANEL_ILI9342               (1)
#define MOY_LCD_PCLK_HZ                     (40 * 1000 * 1000)
#define MOY_LCD_BOARD_HOOKS                 (1)

// The kernel's recovery floor (native/moy_kernel): moy_lcd's entry points over
// the landscape 320x240 framebuffer in wire order.
#define MOY_KERNEL_PANEL(fn)                moy_lcd_k##fn
#define MOY_KERNEL_PANEL_W                  (320)
#define MOY_KERNEL_PANEL_H                  (240)
#define MOY_KERNEL_PANEL_ROT                (0)
#define MOY_KERNEL_PANEL_SWAP               (1)
#define MOY_VM_STOP                         (1)

// The kernel's I2C bus (native/moy_kernel/moy_bus.h): the board's internal bus
// (board.toml's i2c0 row), carrying the AXP2101 (0x34), the AW9523 (0x58), the
// FT6336U (0x38), the Faces Gamepad3 (0x08, through the Faces Bottom3's
// M-Bus), the AW88298 (0x36), the ES7210 (0x40) and the BM8563 (0x51).
#define MOY_BUS_I2C_PORT                    (0)
#define MOY_BUS_I2C_HZ                      (400000)

#define MOY_INPUT_BLE                       (1)
#define MICROPY_PY_BLUETOOTH                (0)
// Input's drivers (native/moy_input/moy_input_task.c), passed on the input
// task once a frame: the Gamepad3, gated by its IRQ (the i2c0 row's pad_int),
// and the FT6336U, which reports in the panel's own landscape coordinates. Its
// INT reaches the S3 only through the AW9523's INTN, so its reads are not gated.
#define MOY_INPUT_TASK                      (1)
#define MOY_INPUT_TASK_STACK                (2560)
#define MOY_INPUT_PAD3                      (1)
#define MOY_INPUT_TOUCH_KIND                (4)     // MOY_TOUCH_FT6X36
#define MOY_INPUT_TOUCH_SWAP                (0)
#define MOY_INPUT_TOUCH_FLIP_X              (0)
#define MOY_INPUT_TOUCH_FLIP_Y              (0)
#define MOY_INPUT_TOUCH_RAW_W               (320)
#define MOY_INPUT_TOUCH_RAW_H               (240)

// The speaker (native/moy_audio/moy_aud_out.c): the AW88298 amplifier on I2S1's
// pins (board.toml's speaker row: BCK 34, WS 33, DOUT 13, and MCLK 0, which the
// ES7210 microphone codec clocks from), set up over the bus; its rail is the
// AXP2101's ALDO1 and its enable the AW9523's P0.2 (native/moy_cores3).
#define MOY_AUDIO_CODEC_AW88298             (1)

#define MOY_GLASS_POOL_BYTES                (160 * 1024)
#define MOY_SHARES_BOARD                    "cores3"

// The Gamepad3 has A, B, a d-pad, Select and Start: Select is the shift for
// the tabs, a card's verbs and the more menu (native/moy_input/moy_pad3.c),
// and the hints say so.
#define MOY_UI_PAD_TABS                     "Select dpad_lr"
#define MOY_UI_PAD_MORE                     "Select B"
#define MOY_UI_PAD_OPTIONS                  "Select A"
#define MOY_GLASS_BANDED                    (1)
#define MICROPY_PY_ESPNOW                   (0)
#define MOY_NET_LINK                        (1)
#define MOY_NET_WIFI                        (1)
#define MOY_NET_MDNS                        (1)
#define MICROPY_ENABLE_VM_ABORT             (1)
