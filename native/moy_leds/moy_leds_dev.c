// The `leds` device API by handle (native/moy_kernel/moy_dev.h's leds row):
// a board's RGB LEDs for a compiled program, over this module's driver
// (moy_leds.h), held by the process from its open to its close or its end,
// when they go dark.

#include "moy_dev.h"
#include "moy_dev_kinds.h"
#include "moy_leds.h"

static int32_t hex_rgb(const word_t *w, uint32_t *rgb) {
    uint8_t b[3];
    if (!moy_dev_hex(w->v, w->vn, b, 3)) {
        return MOY_DEV_EBAD;
    }
    *rgb = (uint32_t)b[0] << 16 | (uint32_t)b[1] << 8 | b[2];
    return 0;
}

static int32_t leds_open(uint32_t slot, uint32_t pid, uint32_t perms, const char *cfg,
                         size_t cn) {
    (void)slot, (void)perms;
    words_t it = { cfg, cfg + cn };
    word_t w;
    if (moy_dev_word(&it, &w) != 0) {
        return MOY_DEV_EBAD;                    // the LEDs take no cfg
    }
    return moy_dev_errno(moy_leds_open(pid));
}

static void leds_close(uint32_t slot, uint32_t pid) {
    (void)slot;
    moy_leds_close(pid);
}

static int32_t leds_write(uint32_t slot, uint32_t pid, const uint8_t *data, size_t n) {
    (void)slot;
    int rc = moy_leds_write(pid, data, (uint32_t)n);
    return rc < 0 ? moy_dev_errno(rc) : (int32_t)n;
}

// set: brightness=0..255, fill=RRGGBB, or led=<i> with rgb=RRGGBB; every word
// is checked before any applies.
static int32_t leds_set(uint32_t slot, uint32_t pid, const char *cfg, size_t n) {
    (void)slot;
    words_t it = { cfg, cfg + n };
    word_t w;
    int64_t level = -1, led = -1;
    uint32_t fill = 0, rgb = 0;
    bool has_fill = false, has_rgb = false;
    int r;
    while ((r = moy_dev_word(&it, &w)) == 1) {
        if (moy_dev_is(w.k, w.kn, "brightness")) {
            if (!moy_dev_in_range(&w, 0, 255, &level)) {
                return MOY_DEV_EBAD;
            }
        } else if (moy_dev_is(w.k, w.kn, "led")) {
            if (!moy_dev_in_range(&w, 0, (int64_t)moy_leds_count() - 1, &led)) {
                return MOY_DEV_EBAD;
            }
        } else if (moy_dev_is(w.k, w.kn, "fill")) {
            if (hex_rgb(&w, &fill) != 0) {
                return MOY_DEV_EBAD;
            }
            has_fill = true;
        } else if (moy_dev_is(w.k, w.kn, "rgb")) {
            if (hex_rgb(&w, &rgb) != 0) {
                return MOY_DEV_EBAD;
            }
            has_rgb = true;
        } else {
            return MOY_DEV_EBAD;
        }
    }
    if (r < 0 || (led >= 0) != has_rgb) {
        return MOY_DEV_EBAD;
    }
    int rc = 0;
    if (has_fill) {
        rc = moy_leds_fill(pid, fill);
    }
    if (rc == 0 && led >= 0) {
        rc = moy_leds_set(pid, (uint32_t)led, rgb);
    }
    if (rc == 0 && level >= 0) {
        rc = moy_leds_bright(pid, (uint32_t)level);
    }
    return rc < 0 ? moy_dev_errno(rc) : 0;
}

static int32_t leds_get(uint32_t slot, uint32_t pid, const char *what, size_t n) {
    (void)slot, (void)pid;
    if (moy_dev_is(what, n, "count")) {
        return (int32_t)moy_leds_count();
    }
    return MOY_DEV_EBAD;
}

const moy_dev_ops_t moy_dev_leds = {
    .open = leds_open, .close = leds_close, .write = leds_write, .set = leds_set,
    .get = leds_get,
};
