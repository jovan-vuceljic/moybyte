// A fake `lora` kind for the board twin (tests/test_live_dev.py): the
// handle table's lora verbs over a radio that hears itself. A write is BUSY
// while the last one "transmits"; the next read finishes it as a driver's
// task would: the packet comes back as a received one, queued, then the
// events posted (TX_DONE, then RX), as moy_lora.c queues before it posts.
// A set naming fail=1 is BAD, so a refusal crosses the relay too.

#include <string.h>

#include "moy_dev.h"
#include "moy_dev_kinds.h"
#include "moy_evq.h"

static struct {
    uint32_t owner;
    int busy;
    uint8_t tx[256];
    size_t tn;
    uint8_t rx[4][256];
    size_t rn[4];
    int rh, rc;
    uint32_t sent, sets;
} F;

static void post(const char *args) {
    if (moy_evq_hears(F.owner, "lora")) {
        moy_evq_post(F.owner, 0u, "lora", args, strlen(args));
    }
}

static int32_t f_open(uint32_t slot, uint32_t pid, uint32_t perms, const char *cfg, size_t cn) {
    (void)slot; (void)perms; (void)cfg; (void)cn;
    if (F.owner != 0 && F.owner != pid) {
        return MOY_DEV_EBUSY;
    }
    memset(&F, 0, sizeof F);
    F.owner = pid;
    return 0;
}

static void f_close(uint32_t slot, uint32_t pid) {
    (void)slot; (void)pid;
    F.owner = 0;
}

static int32_t f_write(uint32_t slot, uint32_t pid, const uint8_t *d, size_t n) {
    (void)slot; (void)pid;
    if (F.busy) {
        return MOY_DEV_EBUSY;
    }
    if (n > sizeof F.tx) {
        return MOY_DEV_EBAD;
    }
    memcpy(F.tx, d, n);
    F.tn = n;
    F.busy = 1;
    F.sent++;
    return (int32_t)n;
}

static int32_t f_read(uint32_t slot, uint32_t pid, uint8_t *out, size_t cap) {
    (void)slot; (void)pid;
    if (F.busy) {
        F.busy = 0;
        if (F.rc < 4) {
            int at = (F.rh + F.rc) % 4;
            memcpy(F.rx[at], F.tx, F.tn);
            F.rn[at] = F.tn;
            F.rc++;
        }
        post("[2,0]");
        post("[1,1]");
        return 0;
    }
    if (F.rc == 0) {
        return 0;
    }
    size_t n = F.rn[F.rh] < cap ? F.rn[F.rh] : cap;
    memcpy(out, F.rx[F.rh], n);
    F.rh = (F.rh + 1) % 4;
    F.rc--;
    return (int32_t)n;
}

static int32_t f_set(uint32_t slot, uint32_t pid, const char *cfg, size_t n) {
    (void)slot; (void)pid;
    if (n >= 6 && memcmp(cfg, "fail=1", 6) == 0) {
        return MOY_DEV_EBAD;
    }
    F.sets++;
    return 0;
}

static int32_t f_get(uint32_t slot, uint32_t pid, const char *what, size_t n) {
    (void)slot; (void)pid;
    if (moy_dev_is(what, n, "rssi")) {
        return -57;
    }
    if (moy_dev_is(what, n, "snr")) {
        return 26;
    }
    if (moy_dev_is(what, n, "port") || moy_dev_is(what, n, "joined")) {
        return 0;
    }
    if (moy_dev_is(what, n, "fcnt")) {
        return (int32_t)F.sent;
    }
    if (moy_dev_is(what, n, "busy")) {
        return F.busy;
    }
    return MOY_DEV_EBAD;
}

static int f_present(void) {
    return 1;
}

const moy_dev_ops_t moy_dev_lora = {
    .open = f_open, .close = f_close, .read = f_read, .write = f_write, .set = f_set,
    .get = f_get, .present = f_present,
};

// What the twin's radio holds, for the test's eyes: its owner and the
// packets written.
uint32_t fake_lora_owner(void) {
    return F.owner;
}
