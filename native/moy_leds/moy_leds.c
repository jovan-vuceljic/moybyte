// moy_leds: moy_leds.h has the contract.

#include "moy_leds.h"

#include <errno.h>
#include <string.h>

#include "moy_lease.h"

#pragma weak moy_board_leds
#pragma weak moy_board_leds_show

static struct {
    uint32_t owner;
    uint32_t sim;                       // the host's bar, 0 for none
    uint8_t level;
    uint8_t rgb[MOY_LEDS_MAX * 3];
    uint8_t shown[MOY_LEDS_MAX * 3];    // GRB, as last handed to the board
} L = { .level = 255 };

static uint32_t count(void) {
    uint32_t n = moy_board_leds != NULL ? moy_board_leds() : L.sim;
    return n > MOY_LEDS_MAX ? MOY_LEDS_MAX : n;
}

static void show(void) {
    uint32_t n = count();
    for (uint32_t i = 0; i < n; i++) {
        const uint8_t *c = L.rgb + 3 * i;
        uint8_t *o = L.shown + 3 * i;
        o[0] = (uint8_t)(c[1] * L.level / 255u);
        o[1] = (uint8_t)(c[0] * L.level / 255u);
        o[2] = (uint8_t)(c[2] * L.level / 255u);
    }
    if (moy_board_leds_show != NULL) {
        moy_board_leds_show(L.shown, n);
    }
}

static void dark(void) {
    memset(L.rgb, 0, sizeof L.rgb);
    L.level = 255;
    show();
}

// The caller's right to the LEDs: 0 when it holds them (taking them when
// nobody does), else the refusal.
static int mine(uint32_t owner) {
    if (count() == 0) {
        return -ENODEV;
    }
    if (L.owner == 0) {
        L.owner = owner;
    }
    return L.owner == owner ? 0 : -EBUSY;
}

uint32_t moy_leds_count(void) {
    return count();
}

int moy_leds_open(uint32_t owner) {
    moy_lease_lock();
    int rc = mine(owner);
    moy_lease_unlock();
    return rc;
}

int moy_leds_close(uint32_t owner) {
    moy_lease_lock();
    int rc = -EPERM;
    if (owner != 0 && L.owner == owner) {
        L.owner = 0;
        dark();
        rc = 0;
    }
    moy_lease_unlock();
    return rc;
}

uint32_t moy_leds_sweep(uint32_t owner) {
    return moy_leds_close(owner) == 0 ? 1u : 0u;
}

uint32_t moy_leds_owner(void) {
    return L.owner;
}

int moy_leds_set(uint32_t owner, uint32_t i, uint32_t rgb) {
    moy_lease_lock();
    int rc = mine(owner);
    if (rc == 0 && i >= count()) {
        rc = -EINVAL;
    }
    if (rc == 0) {
        L.rgb[3 * i] = (uint8_t)(rgb >> 16);
        L.rgb[3 * i + 1] = (uint8_t)(rgb >> 8);
        L.rgb[3 * i + 2] = (uint8_t)rgb;
        show();
    }
    moy_lease_unlock();
    return rc;
}

int moy_leds_fill(uint32_t owner, uint32_t rgb) {
    moy_lease_lock();
    int rc = mine(owner);
    if (rc == 0) {
        for (uint32_t i = 0; i < count(); i++) {
            L.rgb[3 * i] = (uint8_t)(rgb >> 16);
            L.rgb[3 * i + 1] = (uint8_t)(rgb >> 8);
            L.rgb[3 * i + 2] = (uint8_t)rgb;
        }
        show();
    }
    moy_lease_unlock();
    return rc;
}

int moy_leds_bright(uint32_t owner, uint32_t level) {
    moy_lease_lock();
    int rc = mine(owner);
    if (rc == 0 && level > 255) {
        rc = -EINVAL;
    }
    if (rc == 0) {
        L.level = (uint8_t)level;
        show();
    }
    moy_lease_unlock();
    return rc;
}

int moy_leds_write(uint32_t owner, const uint8_t *rgb, uint32_t n) {
    moy_lease_lock();
    int rc = mine(owner);
    if (rc == 0) {
        uint32_t keep = count() * 3;
        keep = n < keep ? n : keep;
        memset(L.rgb, 0, sizeof L.rgb);
        memcpy(L.rgb, rgb, keep);
        show();
    }
    moy_lease_unlock();
    return rc;
}

int moy_leds_shown(uint8_t *out, uint32_t n) {
    uint32_t have = count() * 3;
    have = n < have ? n : have;
    memcpy(out, L.shown, have);
    return (int)have;
}

void moy_leds_sim(uint32_t n) {
    L.sim = n;
}

void moy_leds_reset(void) {
    L.owner = 0;
    memset(L.rgb, 0, sizeof L.rgb);
    memset(L.shown, 0xFF, sizeof L.shown);     // a test sees dark only once shown
    L.level = 255;
}
