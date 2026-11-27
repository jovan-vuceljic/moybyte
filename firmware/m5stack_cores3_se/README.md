# M5Stack CoreS3 SE with the Faces Bottom3 and Faces Gamepad3 (`cores3`)

The T-Deck's tier (320x240, one canvas, fullscreen) on M5Stack's CoreS3 SE,
the first console board whose keys are a gamepad. The panel is the shared
SPI driver (`native/moy_lcd`, `MOY_LCD_PANEL_ILI9342` with this board's
hooks), the card shares the panel's SPI2 as the T-Deck's does
(`device/bus_store.py`), and the Gamepad3 and the FT6336U are the kernel's
input drivers. What is this board's own is `board.toml`,
`boards/MOYBYTE_CORES3/`, `modules/` and `native/moy_cores3/` (the AXP2101,
the AW9523, the BM8563 and the LED bar).

Build: `make firmware-build-cores3` (`dist/cores3/`). Flash:
`tools/board.py cores3 flash` or `make firmware-flash-cores3 PORT=...`.

## The hardware and where each fact comes from

The sources are M5Stack's own libraries (MIT; THIRD_PARTY.md §2.4a):
[M5GFX](https://github.com/m5stack/M5GFX) (the panel, the board's power
operations, the light), [M5Unified](https://github.com/m5stack/M5Unified)
(the power manager, the amplifier, the clock) and
[M5Faces](https://github.com/m5stack/M5Faces) (the Faces and their bar).

| part | wiring | source |
|---|---|---|
| ESP32-S3 (QFN56), 16 MB flash, 8 MB quad PSRAM | GPIO 26–32 flash/PSRAM, 19/20 USB | the chip's report; `sdkconfig.board` |
| ILI9342C panel, 320x240 | SPI2: SCK 36, MOSI 37, MISO 35 is also D/C, CS 3; 40 MHz; MADCTL 0x08 (BGR), inverted | M5GFX `Panel_ILI9342`, board detection |
| panel reset | AW9523 P1 bit 1, pulsed low 10 ms at bring-up | M5GFX `pmic_ops` |
| backlight | AXP2101 DLDO1: reg 0x90 bit 7 on, reg 0x99 the voltage, codes 20..28 | M5GFX `Light_M5StackCoreS3` |
| microSD | SPI2, CS 4; its MISO is the panel's D/C pad, turned to the card's input for a card session (`native/moy_lcd`, M5GFX's `Panel_M5StackCoreS3::cs_control`) | M5Unified, M5GFX |
| internal I2C | SDA 12, SCL 11, 400 kHz: AXP2101 0x34, AW9523 0x58, FT6336U 0x38, AW88298 0x36, ES7210 0x40, BM8563 0x51, the Gamepad3 0x08 | M5Unified, M5Faces |
| touch | FT6336U at 0x38, read every pass (its INT reaches GPIO 21 only through the AW9523) | M5Unified |
| speaker | AW88298 over I2S: BCK 34, WS 33, DOUT 13, MCLK 0; AW9523 P0 bit 2 its enable | M5Unified `Speaker_Class` |
| microphone | ES7210 over the speaker's I2S, DIN 14 | M5Unified `Mic_Class` |
| clock | BM8563 at 0x51, UTC, its VL bit the "lost" flag | M5Unified `RTC8563_Class` |
| Faces Gamepad3 | 0x08; IRQ on G10; keys at reg 0x00, active low (bit 0 up, 1 down, 2 left, 3 right, 4 A, 5 B, 6 Select, 7 Start); model 0x03 at 0xD0 | M5Faces `M5Faces_Gamepad3` |
| Faces Bottom3 LED bar | ten SK6812, five a side; the base's LED IO switch puts their data on M-Bus pin 8 (G5) or pin 23 (G13, the speaker's I2S data) | the Bottom3's schematic (A168), the CoreS3's M-Bus map |

The power-on sequence (`moy_lcd_board_up`, before the panel's bus): the
AXP2101's ADC and DCDC settings (0x23, 0x27, 0x69, 0x10, 0x30, the 4.2 V
charge voltage, the TS pin off), its ALDO rails (0x92 1.8 V, 0x93..0x95 3.3 V)
with DLDO1 off; the AW9523's outputs (P0 0x07, with BUS_OUT_EN 0x02: the M-Bus's 5 V, the LED bar's supply; P1 0x03 with the boost's bit
0x80), directions (0x04 0x18, 0x05 0x0C), P0 push-pull (0x11 0x10) and every
pin a GPIO (0x12/0x13 0xFF); then the panel's reset pulse and 120 ms. Each
value is M5Unified's `Power_Class::begin` for the CoreS3 and M5GFX's
`pmic_ops`. The AW88298's (`native/moy_audio/moy_codec_aw88298.c`) is
M5Unified's: 0x61 0x0673, 0x04 0x4040, 0x05 0x0008, 0x06 0x14C0 with the
rate's code, 0x0C 0x0064. Its PLL locks on BCK, and the I2S driver's fractional
MCLK divider jitters BCK enough that the lock never holds (SYSST 0x01 shows
PLLS clear, no sound), so the board takes `MOY_AUDIO_MCLK_WHOLE`
(`native/moy_audio/moy_aud_out.c`): a whole divider, 160 MHz / 28, and the
output and the mix at the rates it gives (2026-11-27). `moy_cores3.reg(0x36,
0x01, 2)` reads SYSST; 0x0311 is locked.

## Input

| on the pad | the console's button | |
|---|---|---|
| d-pad | up down left right | |
| A, B | `a`, `b` | confirm, back |
| Start | `start` | the console's key: a tap the system menu or the pause card, held the task manager |
| Select | `select` | and the shift: |
| Select + A, Select + B | `x`, `y` | B's is the more menu (`Y` on a full gamepad) |
| Select + left/right | types Q / E | the tabs (the browser pad's shoulders); in a game the directions stay |
| Select + Start | | the Editor's Play |

The hints draw these chords (`MOY_UI_PAD_TABS`, `MOY_UI_PAD_MORE` in
`boards/MOYBYTE_CORES3/mpconfigboard.h`). Touch works beside the pad, and a
paired BLE keyboard is a desk keyboard.

The card is the store's when its volume mounts (FAT or exFAT, on an MBR
partition table or none); a card partitioned GPT mounts nothing, so the
console runs on its internal store, as with no card.

## Power

The AXP2101's power key is the board's switch, in hardware: a press powers
on, a hold of about 4 s powers off. Sleep is the shared idle ladder's (the
system menu's Sleep and Settings' screen-off rung). The status bar's battery
reads the AXP2101's gauge (`battery.PmicBattery` over `moy_cores3.pmic`): the
SE carries no cell of its own, so without a battery base the bar shows none.

## LED bar

The Faces Bottom3's LED IO switch belongs in the G5 position (M-Bus pin 8).
In the other, G13, the bar's data line is the speaker's I2S data: every sound
is a frame of garbage to the bar, which lights it up to full white and
warm. The bar keeps the last frame it was sent, so it is written dark by
`boot.py` (G5) and by the panel's bring-up on both pins before the speaker
takes G13 (`moy_lcd_board_up`). The console has no status light.

## On glass

`tests/test_cores3_on_glass.py` (gated on `MOYBYTE_CORES3_PORT`) over the
shared `tests/on_glass.py`; `tools/board.py pass cores3` builds, flashes and
runs it with the perf stage. The USB is the SoC's USB-Serial/JTAG, so the
suite attaches (`[serial] attach_only`) and the flash enters the ROM loader
over USB on its own (`[flash] before = "usb_reset"`).

Download mode by hand: hold the reset button (the small one beside the USB
port) for about 3 s until the green LED lights, then flash.
