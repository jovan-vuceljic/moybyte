// moy_cores3: the M5Stack CoreS3 SE's own chips, which no other board has --
// the AXP2101 power manager (0x34), the AW9523 IO expander (0x58) that holds
// the panel's reset and the amplifier's enable, the BM8563 clock (0x51) and the
// Faces Bottom3's SK6812 bar -- all on the kernel's I2C bus
// (native/moy_kernel/moy_bus.h) but the bar, which is one GPIO.
//
// What the shared modules ask of it:
//   moy_lcd_board_up      native/moy_lcd's bring-up (MOY_LCD_BOARD_HOOKS): the
//                         rails, the expander's outputs and the panel's reset,
//                         before the bus exists; the light stays off
//   moy_lcd_board_light   the backlight, which is the AXP2101's DLDO1 voltage
//   moy_board_rtc_set     every NTP answer, kept by the BM8563
//                         (native/moy_net/moy_net.h)
//
// The sequences are M5Stack's, MIT: M5Unified's Power_Class::begin for the
// CoreS3 (the AXP2101's rails, its power key, charge voltage and TS pin) and
// M5GFX's board_detect pmic_ops (the expander's outputs and modes) and
// Light_M5StackCoreS3 (the DLDO1 light); the register maps are the parts'
// datasheets. README.md beside this tree lists each step with its source.
//
// The module `moy_cores3` is the console's reach to the rest: the battery and
// charger (pmic), the clock chip (rtc, rtc_set, clock_restore), the bar
// (leds), and a register read for the on-glass suite (reg).

#include <string.h>
#include <time.h>

#include "py/runtime.h"
#include "py/mphal.h"
#include "extmod/modmachine.h"

#include "driver/gpio.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "moy_bus.h"
#include "moy_light.h"
#include "moy_net.h"

#define AXP_ADDR 0x34
#define AW_ADDR 0x58
#define RTC_ADDR 0x51
#define BUS_MS 50

// The Faces Bottom3's bar: ten SK6812s, five a side, whose data line the
// base's LED IO switch (S1, its schematic A168) puts on one of two M-Bus
// pins: pin 8, G5 on the CoreS3, or pin 23, G13 -- the speaker's I2S data, so
// in that position every sound the console plays is a frame to the bar.
// `leds` drives G5, the position the README asks for; the bring-up writes the
// bar dark on both before the speaker takes G13.
#define BAR_PIN 5
#define BAR_PIN_ALT MOY_HW_SPEAKER_DOUT
#define BAR_LEDS 10

// The AW9523's ports: P0 output 0x02, P1 output 0x03, P0/P1 direction 0x04/0x05
// (1 an input), the global control 0x11 (bit 4: P0 push-pull) and the LED-mode
// switches 0x12/0x13 (1 a GPIO).
//   P0: 0 touch reset, 1 BUS_OUT_EN (the M-Bus 5 V out), 2 the amplifier's
//       enable, 3 and 4 inputs
//   P1: 0 the camera's reset (the SE has none), 1 the panel's reset, 2 the
//       touch INT and 3 the amplifier's INT as inputs, 7 the SY7088 boost
#define AW_P0 0x02
#define AW_P1 0x03
#define AW_P0_BUS_OUT 0x02
#define AW_P0_AMP 0x04
#define AW_P1_LCD_RST 0x02
#define AW_P1_BOOST 0x80

static uint8_t s_axp = 0xff, s_aw = 0xff, s_rtc = 0xff;
static uint8_t s_ldo;               // AXP2101 0x90, as last written
static int s_step;                  // the light's code, 0 off

static int dev(uint8_t addr, uint8_t *d) {
    if (*d == 0xff && moy_bus_add(addr, BUS_MS, d) != MOY_BUS_OK) {
        return -1;
    }
    return 0;
}

static int wr(uint8_t addr, uint8_t *d, uint8_t reg, uint8_t v) {
    uint8_t b[2] = {reg, v};
    return dev(addr, d) == 0 && moy_bus_write(*d, b, 2) == MOY_BUS_OK ? 0 : -1;
}

static int rd(uint8_t addr, uint8_t *d, uint8_t reg, uint8_t *out, size_t n) {
    return dev(addr, d) == 0 && moy_bus_write_read(*d, &reg, 1, out, n) == MOY_BUS_OK ? 0 : -1;
}

static int bits(uint8_t addr, uint8_t *d, uint8_t reg, uint8_t set, uint8_t clear) {
    uint8_t v;
    if (rd(addr, d, reg, &v, 1) != 0) {
        return -1;
    }
    return wr(addr, d, reg, (uint8_t)((v | set) & ~clear));
}

#define AXP(reg, v) wr(AXP_ADDR, &s_axp, (reg), (v))
#define AW(reg, v) wr(AW_ADDR, &s_aw, (reg), (v))

// The bar's ten pixels, GRB, sent once on `pin`.
static void bar_show(int pin, uint8_t px[BAR_LEDS * 3]) {
    gpio_set_direction(pin, GPIO_MODE_OUTPUT);
    gpio_set_level(pin, 0);
    uint32_t timing_ns[4] = {400, 850, 800, 450};   // T0H T0L T1H T1L
    machine_bitstream_high_low(pin, timing_ns, px, BAR_LEDS * 3);
}

// The rails and the expander, then the panel's reset pulse. The light (DLDO1)
// stays off: it powers up at 3.3 V, full, so it is left to the first frame.
esp_err_t moy_lcd_board_up(void) {
    int e = 0;
    // A DCDC dip below 85% (inrush on a weak USB supply) latches the AXP2101
    // off until its key; let the S3 brown out and restart instead.
    e |= bits(AXP_ADDR, &s_axp, 0x23, 0, 0x1F);
    // The expander: outputs written before the directions, so every pin
    // switched to an output comes up at its level.
    // BUS_OUT_EN puts 5 V on the M-Bus: without it a base's parts (the
    // Bottom3's LED bar) have no supply on USB power.
    e |= bits(AW_ADDR, &s_aw, AW_P0, 0x01 | AW_P0_BUS_OUT | AW_P0_AMP, 0);
    e |= bits(AW_ADDR, &s_aw, AW_P1, 0x01 | AW_P1_LCD_RST | AW_P1_BOOST, 0);
    e |= AW(0x04, 0x18);
    e |= AW(0x05, 0x0C);
    e |= AW(0x11, 0x10);
    e |= AW(0x12, 0xFF);
    e |= AW(0x13, 0xFF);
    // The LDOs: ALDO1 1.8 V (the AW88298), ALDO2 3.3 V (the ES7210), ALDO3
    // 3.3 V (the camera's, on no SE), ALDO4 3.3 V (the TF slot), BLDO1 and 2;
    // DLDO1, the light, off.
    s_ldo = 0x3F;
    e |= AXP(0x92, 18 - 5);
    e |= AXP(0x93, 33 - 5);
    e |= AXP(0x94, 33 - 5);
    e |= AXP(0x95, 33 - 5);
    e |= AXP(0x90, s_ldo);
    e |= AXP(0x27, 0x00);           // the power key: hold 1 s on, 4 s off
    e |= AXP(0x69, 0x11);           // the charge LED
    e |= AXP(0x10, 0x30);           // off-discharge on
    e |= AXP(0x30, 0x0F);           // the ADCs: battery, VBUS, VSYS, TS
    // The cell is a 4.2 V one, and a unit's power-on charge voltage can be a
    // reserved code; set before TS stops reading as a cold cell.
    e |= bits(AXP_ADDR, &s_axp, 0x64, 0x03, 0x04);
    e |= bits(AXP_ADDR, &s_axp, 0x50, 0x10, 0);    // TS: an input, not the charger's
    // The panel's reset, through the expander.
    e |= bits(AW_ADDR, &s_aw, AW_P1, 0, AW_P1_LCD_RST);
    vTaskDelay(pdMS_TO_TICKS(10));
    e |= bits(AW_ADDR, &s_aw, AW_P1, AW_P1_LCD_RST, 0);
    vTaskDelay(pdMS_TO_TICKS(120));
    // The bar is powered from the boost just switched on and can come up lit:
    // dark on either of its pins, before the speaker's I2S takes G13.
    uint8_t dark[BAR_LEDS * 3] = {0};
    bar_show(BAR_PIN, dark);
    bar_show(BAR_PIN_ALT, dark);
    s_step = 0;
    return e == 0 ? ESP_OK : ESP_FAIL;
}

// DLDO1's voltage is the light: 0.5 V + 0.1 V a code, lit from code 20 (2.5 V)
// to 28 (3.3 V), M5GFX's (level + 641) >> 5 over its 0..255 brightness, which
// is MOY_LIGHT_FULL's scale. Answers the step, 1..9, or 0 off.
int moy_lcd_board_light(int level) {
    int code = level <= 0 ? 0 : (level + 641) >> 5;
    if (code == s_step) {
        return code ? code - 19 : 0;
    }
    if (code) {
        AXP(0x99, (uint8_t)code);
        if (!(s_ldo & 0x80)) {
            s_ldo |= 0x80;
            AXP(0x90, s_ldo);
        }
    } else if (s_ldo & 0x80) {
        s_ldo &= (uint8_t)~0x80;
        AXP(0x90, s_ldo);
    }
    s_step = code;
    return code ? code - 19 : 0;
}

// -- the clock chip ----------------------------------------------------------

static int bcd(uint8_t v) {
    return (v >> 4) * 10 + (v & 0x0F);
}

static uint8_t tobcd(int v) {
    return (uint8_t)(((v / 10) << 4) | (v % 10));
}

// The BM8563's time as Unix seconds (it keeps UTC), or -1 when it cannot be
// read or its VL bit says the time was lost.
static int64_t rtc_read(void) {
    uint8_t r[7];
    if (rd(RTC_ADDR, &s_rtc, 0x02, r, 7) != 0 || (r[0] & 0x80)) {
        return -1;
    }
    struct tm t = {0};
    t.tm_sec = bcd(r[0] & 0x7F);
    t.tm_min = bcd(r[1] & 0x7F);
    t.tm_hour = bcd(r[2] & 0x3F);
    t.tm_mday = bcd(r[3] & 0x3F);
    t.tm_mon = bcd(r[5] & 0x1F) - 1;
    t.tm_year = bcd(r[6]) + ((r[5] & 0x80) ? 0 : 100);     // C: 19xx, else 20xx
    if (t.tm_year < 120) {
        return -1;          // before 2020: never set
    }
    // UTC: the board's TZ is never set, so mktime is timegm here, and newlib's
    // calendar counts from 1970 whatever the system clock's epoch.
    return (int64_t)mktime(&t);
}

void moy_board_rtc_set(int64_t unix_s) {
    time_t s = (time_t)unix_s;         // the calendar's 1970, not the clock's 2000
    struct tm t;
    gmtime_r(&s, &t);
    int year = t.tm_year + 1900;
    uint8_t b[8] = {
        0x02, tobcd(t.tm_sec), tobcd(t.tm_min), tobcd(t.tm_hour), tobcd(t.tm_mday),
        (uint8_t)t.tm_wday, (uint8_t)(tobcd(t.tm_mon + 1) | (year < 2000 ? 0x80 : 0)),
        tobcd(year % 100),
    };
    if (dev(RTC_ADDR, &s_rtc) == 0) {
        moy_bus_write(s_rtc, b, sizeof(b));
    }
}

// -- the module ----------------------------------------------------------------

// pmic() -> (level, charging, vbus, mv): the fuel gauge's percent (None with
// no cell), whether the charger is charging the cell, whether USB powers the
// board, and the cell's voltage in mV (None with no cell). None when the
// AXP2101 does not answer.
static mp_obj_t cores3_pmic(void) {
    uint8_t st[2], pct, v[2];
    if (rd(AXP_ADDR, &s_axp, 0x00, st, 2) != 0 || rd(AXP_ADDR, &s_axp, 0xA4, &pct, 1) != 0
        || rd(AXP_ADDR, &s_axp, 0x34, v, 2) != 0) {
        return mp_const_none;
    }
    // The SE has no cell of its own; one reads through the M-Bus where a base
    // carries it. A present bit over a voltage no cell rests at is no cell.
    int mv = ((v[0] & 0x3F) << 8) | v[1];
    bool cell = (st[0] & 0x08) && mv >= 2500;
    mp_obj_t out[4] = {
        cell ? MP_OBJ_NEW_SMALL_INT(pct > 100 ? 100 : pct) : mp_const_none,
        mp_obj_new_bool(cell && ((st[1] >> 5) & 3) == 1),
        mp_obj_new_bool(st[0] & 0x20),
        cell ? MP_OBJ_NEW_SMALL_INT(mv) : mp_const_none,
    };
    return mp_obj_new_tuple(4, out);
}
static MP_DEFINE_CONST_FUN_OBJ_0(cores3_pmic_obj, cores3_pmic);

// rtc() -> the clock chip's Unix seconds, or None (unreadable, or never set).
static mp_obj_t cores3_rtc(void) {
    int64_t t = rtc_read();
    return t < 0 ? mp_const_none : mp_obj_new_int_from_ll(t);
}
static MP_DEFINE_CONST_FUN_OBJ_0(cores3_rtc_obj, cores3_rtc);

// rtc_set(unix_s) -> None: what every NTP answer does.
static mp_obj_t cores3_rtc_set(mp_obj_t t) {
    moy_board_rtc_set(mp_obj_get_ll(t));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(cores3_rtc_set_obj, cores3_rtc_set);

// clock_restore() -> bool: the system clock set from the chip at boot (the
// clock then reads synced), False where the chip has no time.
static mp_obj_t cores3_clock_restore(void) {
    int64_t t = rtc_read();
    if (t < 0) {
        return mp_const_false;
    }
    moy_clock_restore(t);
    return mp_const_true;
}
static MP_DEFINE_CONST_FUN_OBJ_0(cores3_clock_restore_obj, cores3_clock_restore);

// leds(grb) -> None: the bar's ten SK6812s, on G5, three bytes each in the order
// green, red, blue, the first the chain's nearest; short data leaves the rest
// dark. leds(b"") is the bar off.
static mp_obj_t cores3_leds(mp_obj_t buf_in) {
    mp_buffer_info_t b;
    mp_get_buffer_raise(buf_in, &b, MP_BUFFER_READ);
    uint8_t px[BAR_LEDS * 3] = {0};
    memcpy(px, b.buf, b.len < sizeof(px) ? b.len : sizeof(px));
    bar_show(BAR_PIN, px);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(cores3_leds_obj, cores3_leds);

// reg(addr, reg, n=1) -> bytes: n registers of a chip on the bus, or None.
// reg(addr, reg, data) -> bool: `data` (bytes, at most 15) written from `reg`.
static mp_obj_t cores3_reg(size_t n_args, const mp_obj_t *a) {
    uint8_t addr = (uint8_t)mp_obj_get_int(a[0]);
    uint8_t reg = (uint8_t)mp_obj_get_int(a[1]);
    uint8_t out[16], d;
    if (n_args > 2 && !mp_obj_is_int(a[2])) {
        mp_buffer_info_t bi;
        mp_get_buffer_raise(a[2], &bi, MP_BUFFER_READ);
        if (bi.len == 0 || bi.len >= sizeof(out) || moy_bus_add(addr, BUS_MS, &d) != MOY_BUS_OK) {
            return mp_const_false;
        }
        out[0] = reg;
        memcpy(out + 1, bi.buf, bi.len);
        return mp_obj_new_bool(moy_bus_write(d, out, bi.len + 1) == MOY_BUS_OK);
    }
    size_t n = n_args > 2 ? (size_t)mp_obj_get_int(a[2]) : 1;
    if (n == 0 || n > sizeof(out) || moy_bus_add(addr, BUS_MS, &d) != MOY_BUS_OK
        || moy_bus_write_read(d, &reg, 1, out, n) != MOY_BUS_OK) {
        return mp_const_none;
    }
    return mp_obj_new_bytes(out, n);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(cores3_reg_obj, 2, 3, cores3_reg);

// light() -> the light's DLDO1 code now, 0 off.
static mp_obj_t cores3_light(void) {
    return MP_OBJ_NEW_SMALL_INT(s_step);
}
static MP_DEFINE_CONST_FUN_OBJ_0(cores3_light_obj, cores3_light);

static const mp_rom_map_elem_t cores3_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_moy_cores3) },
    { MP_ROM_QSTR(MP_QSTR_pmic), MP_ROM_PTR(&cores3_pmic_obj) },
    { MP_ROM_QSTR(MP_QSTR_rtc), MP_ROM_PTR(&cores3_rtc_obj) },
    { MP_ROM_QSTR(MP_QSTR_rtc_set), MP_ROM_PTR(&cores3_rtc_set_obj) },
    { MP_ROM_QSTR(MP_QSTR_clock_restore), MP_ROM_PTR(&cores3_clock_restore_obj) },
    { MP_ROM_QSTR(MP_QSTR_leds), MP_ROM_PTR(&cores3_leds_obj) },
    { MP_ROM_QSTR(MP_QSTR_reg), MP_ROM_PTR(&cores3_reg_obj) },
    { MP_ROM_QSTR(MP_QSTR_light), MP_ROM_PTR(&cores3_light_obj) },
    { MP_ROM_QSTR(MP_QSTR_BAR_LEDS), MP_ROM_INT(BAR_LEDS) },
};
static MP_DEFINE_CONST_DICT(cores3_globals, cores3_globals_table);

const mp_obj_module_t moy_cores3_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&cores3_globals,
};

MP_REGISTER_MODULE(MP_QSTR_moy_cores3, moy_cores3_module);
