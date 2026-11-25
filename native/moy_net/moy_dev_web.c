// moy_dev_web: the page's half of the live socket's device channel
// (moy_live.c's header is the wire; native/moy_kernel/moy_dev_kinds.h's THE
// RELAY what a board relays). In the browser console a handle of a kind the
// page's board relays is a REMOTE ROW of the kernel's handle table
// (moy_dev.h): the page's consent and grant gate its open as any handle's,
// and its verbs are the ones below, which never wait on the socket, as the
// frame never does:
//
//   open    answers at once; the board's answer follows, and a refusal is
//           what every later call of the row answers
//   write   one in flight a row: BUSY until the board answered the last one
//           (it holds a write its device was busy for until it goes), and
//           BUSY while the socket is closed; a write the board refused is
//           answered to the next write
//   set     sent; a refusal is answered to the next set or write
//   read    the next record the board pushed, cut to `cap` (lora's read);
//           0 with none
//   get     a packet get from the record read last, a state get from the
//           board's last 'G'; BAD for a key the kind's list has not
//   xfer    BAD: its answer cannot come back inside the call
//
// The board's events for a kind are posted to each process that holds a
// row of it (moy_evq_post from the system, as a driver posts), after the
// records and the state they announce. A socket that (re)opens opens every
// row again, its last set after it: a board that restarted holds none.
//
// The kinds come from the /live probe's "kinds" (moy_dev_web_kinds). The
// worker moves the bytes between frames (moy_link_web.c's queue).

#if defined(MOY_NET_LIVE_PAGE) && MOY_NET_LIVE_PAGE

#include <string.h>
#include <time.h>

#include "moy_dev.h"
#include "moy_dev_kinds.h"
#include "moy_evq.h"
#include "moy_link.h"

#define KINDS_MAX 4
#define GETS 6
#define GET_MAX 10
#define NAME_MAX 12
#define CFG_MAX 256
#define RECS 8192                       // the records waiting, every row's

typedef struct {
    char name[NAME_MAX];
    uint8_t np, ns;                     // its packet gets, its state gets
    char gp[GETS][GET_MAX], gs[GETS][GET_MAX];
} kind_t;

enum { FREE, OPENING, OPEN, FAILED };

typedef struct {
    uint32_t pid;
    uint8_t kind;                       // its index in K
    uint8_t state;
    uint8_t writing;                    // a write awaits the board's answer
    int32_t err;                        // FAILED's code; else a refusal kept for the next call
    int32_t pv[GETS], sv[GETS];
    uint64_t asked;                     // when the call its next answer answers was queued, 0: none
    uint16_t cn, sn;
    char cfg[CFG_MAX], set[CFG_MAX];    // the open's cfg and the last set, said again at a reopen
} row_t;

static struct {
    kind_t k[KINDS_MAX];
    int nk;
    int open;                           // the socket is open
    row_t r[MOY_DEV_HANDLES];
    uint8_t rec[RECS];                  // id(1) len(2) vals(4 x np) data, oldest first
    size_t rec_n;
    moy_dev_web_info_t info;
} W;

static uint64_t now_us(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000u + (uint64_t)t.tv_nsec / 1000u;
}

static int kind_of(const char *name, size_t n) {
    for (int i = 0; i < W.nk; i++) {
        if (strlen(W.k[i].name) == n && memcmp(W.k[i].name, name, n) == 0) {
            return i;
        }
    }
    return -1;
}

// Words split by ',' from p up to ':' or `end`, into `out`: how many.
static uint8_t words(const char **p, const char *end, char out[GETS][GET_MAX]) {
    uint8_t n = 0;
    const char *s = *p;
    while (s < end && *s != ':' && *s != ';') {
        const char *e = s;
        while (e < end && *e != ',' && *e != ':' && *e != ';') {
            e++;
        }
        if (e > s && n < GETS && (size_t)(e - s) < GET_MAX) {
            memcpy(out[n], s, (size_t)(e - s));
            out[n][e - s] = 0;
            n++;
        }
        s = e < end && *e == ',' ? e + 1 : e;
    }
    *p = s;
    return n;
}

void moy_dev_web_kinds(const char *spec, size_t n) {
    const char *p = spec, *end = spec + n;
    W.nk = 0;
    while (p < end && W.nk < KINDS_MAX) {
        const char *c = p;
        while (c < end && *c != ':' && *c != ';') {
            c++;
        }
        kind_t *k = &W.k[W.nk];
        memset(k, 0, sizeof *k);
        if (c > p && (size_t)(c - p) < NAME_MAX) {
            memcpy(k->name, p, (size_t)(c - p));
            W.nk++;
        }
        p = c < end && *c == ':' ? c + 1 : c;
        k->np = words(&p, end, k->gp);
        p = p < end && *p == ':' ? p + 1 : p;
        k->ns = words(&p, end, k->gs);
        while (p < end && *p != ';') {
            p++;
        }
        p += p < end;
    }
}

bool moy_dev_web_has(const char *name) {
    return kind_of(name, strlen(name)) >= 0;
}

// A plaintext of the device channel queued: 'd', verb, row, then `n`
// bytes of `a` and `m` of `b`.
static void say(char verb, uint32_t slot, const void *a, size_t n, const void *b, size_t m) {
    uint8_t *p = moy_link_web_queue(3 + n + m);
    if (p == NULL) {
        W.info.dropped++;
        return;
    }
    p[0] = 'd';
    p[1] = (uint8_t)verb;
    p[2] = (uint8_t)slot;
    if (verb != 'C' && W.r[slot].asked == 0) {
        W.r[slot].asked = now_us();
    }
    if (n) {
        memcpy(p + 3, a, n);
    }
    if (m) {
        memcpy(p + 3 + n, b, m);
    }
    W.info.up++;
}

static void say_open(uint32_t slot) {
    row_t *r = &W.r[slot];
    const char *name = W.k[r->kind].name;
    uint8_t h[1 + NAME_MAX];
    h[0] = (uint8_t)strlen(name);
    memcpy(h + 1, name, h[0]);
    say('O', slot, h, 1u + h[0], r->cfg, r->cn);
    if (r->sn) {
        say('S', slot, r->set, r->sn, NULL, 0);
    }
}

// Row `slot`'s records dropped.
static void drop_recs(uint32_t slot) {
    size_t at = 0;
    while (at + 3 <= W.rec_n) {
        size_t len = 3 + ((size_t)W.rec[at + 1] | (size_t)W.rec[at + 2] << 8);
        if (W.rec[at] == slot) {
            memmove(W.rec + at, W.rec + at + len, W.rec_n - at - len);
            W.rec_n -= len;
        } else {
            at += len;
        }
    }
}

int32_t moy_dev_web_open(uint32_t slot, const char *name, uint32_t pid, const char *cfg,
                         size_t cn) {
    int k = kind_of(name, strlen(name));
    if (k < 0) {
        return MOY_DEV_EABSENT;
    }
    if (cn > CFG_MAX) {
        return MOY_DEV_EBAD;
    }
    row_t *r = &W.r[slot];
    memset(r, 0, sizeof *r);
    r->pid = pid;
    r->kind = (uint8_t)k;
    r->state = OPENING;
    memcpy(r->cfg, cfg, cn);
    r->cn = (uint16_t)cn;
    drop_recs(slot);
    if (W.open) {
        say_open(slot);
    }
    W.info.opens++;
    return 0;
}

static void web_close(uint32_t slot, uint32_t pid) {
    (void)pid;
    if (W.open) {
        say('C', slot, NULL, 0, NULL, 0);
    }
    drop_recs(slot);
    W.r[slot].state = FREE;
}

// A FAILED row's code, else the refusal kept for the next call (given once).
static int32_t kept(row_t *r) {
    if (r->state == FAILED) {
        return r->err;
    }
    int32_t e = r->err;
    r->err = 0;
    return e;
}

static int32_t web_write(uint32_t slot, uint32_t pid, const uint8_t *data, size_t n) {
    (void)pid;
    row_t *r = &W.r[slot];
    int32_t e = kept(r);
    if (e < 0) {
        return e;
    }
    if (!W.open || r->writing) {
        return MOY_DEV_EBUSY;
    }
    if (n > 1400) {
        return MOY_DEV_EBAD;
    }
    say('W', slot, data, n, NULL, 0);
    r->writing = 1;
    return (int32_t)n;
}

static int32_t web_set(uint32_t slot, uint32_t pid, const char *cfg, size_t n) {
    (void)pid;
    row_t *r = &W.r[slot];
    int32_t e = kept(r);
    if (e < 0) {
        return e;
    }
    if (n > CFG_MAX) {
        return MOY_DEV_EBAD;
    }
    memcpy(r->set, cfg, n);
    r->sn = (uint16_t)n;
    if (W.open) {
        say('S', slot, cfg, n, NULL, 0);
    }
    return 0;
}

static int32_t web_read(uint32_t slot, uint32_t pid, uint8_t *out, size_t cap) {
    (void)pid;
    row_t *r = &W.r[slot];
    if (r->state == FAILED) {
        return r->err;
    }
    const kind_t *k = &W.k[r->kind];
    size_t at = 0;
    while (at + 3 <= W.rec_n) {
        size_t len = (size_t)W.rec[at + 1] | (size_t)W.rec[at + 2] << 8;
        if (W.rec[at] == slot) {
            const uint8_t *v = W.rec + at + 3;
            for (int i = 0; i < k->np; i++) {
                r->pv[i] = (int32_t)((uint32_t)v[4 * i] | (uint32_t)v[4 * i + 1] << 8
                                     | (uint32_t)v[4 * i + 2] << 16 | (uint32_t)v[4 * i + 3] << 24);
            }
            size_t dn = len - 4u * k->np;
            size_t m = dn < cap ? dn : cap;
            memcpy(out, v + 4u * k->np, m);
            memmove(W.rec + at, W.rec + at + 3 + len, W.rec_n - at - 3 - len);
            W.rec_n -= 3 + len;
            return (int32_t)m;
        }
        at += 3 + len;
    }
    return 0;
}

static int32_t web_get(uint32_t slot, uint32_t pid, const char *what, size_t n) {
    (void)pid;
    row_t *r = &W.r[slot];
    if (r->state == FAILED) {
        return r->err;
    }
    const kind_t *k = &W.k[r->kind];
    for (int i = 0; i < k->np; i++) {
        if (moy_dev_is(what, n, k->gp[i])) {
            return r->pv[i];
        }
    }
    for (int i = 0; i < k->ns; i++) {
        if (moy_dev_is(what, n, k->gs[i])) {
            return r->sv[i];
        }
    }
    return MOY_DEV_EBAD;
}

const moy_dev_ops_t moy_dev_web = {
    .close = web_close, .read = web_read, .write = web_write, .set = web_set, .get = web_get,
};

static int32_t i32(const uint8_t *p) {
    return (int32_t)((uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16
                     | (uint32_t)p[3] << 24);
}

static void event(const uint8_t *p, size_t n) {
    if (n < 1 || (size_t)p[0] + 1 > n || p[0] >= MOY_EVQ_NAME) {
        return;
    }
    char name[MOY_EVQ_NAME];
    memcpy(name, p + 1, p[0]);
    name[p[0]] = 0;
    const char *args = (const char *)p + 1 + p[0];
    size_t an = n - 1 - p[0];
    int k = kind_of(name, p[0]);
    uint32_t told[MOY_DEV_HANDLES];
    int nt = 0;
    for (uint32_t s = 0; k >= 0 && s < MOY_DEV_HANDLES; s++) {
        const row_t *r = &W.r[s];
        if (r->state == FREE || r->kind != k) {
            continue;
        }
        int seen = 0;
        for (int i = 0; i < nt; i++) {
            seen |= told[i] == r->pid;
        }
        if (!seen) {
            told[nt++] = r->pid;
            moy_evq_post(r->pid, 0u, name, an ? args : "[]", an ? an : 2);
            W.info.events++;
        }
    }
}

void moy_dev_web_give(const uint8_t *p, size_t n) {
    if (n < 3 || p[0] != 'd') {
        return;
    }
    W.info.down++;
    if (p[1] == 'E') {
        event(p + 2, n - 2);
        return;
    }
    uint32_t slot = p[2];
    if (slot >= MOY_DEV_HANDLES || W.r[slot].state == FREE) {
        return;
    }
    row_t *r = &W.r[slot];
    const kind_t *k = &W.k[r->kind];
    if (p[1] == 'A' && n >= 8) {
        int32_t rc = i32(p + 4);
        if (r->asked != 0) {
            uint32_t us = (uint32_t)(now_us() - r->asked);
            r->asked = 0;
            W.info.rtt_min = W.info.timed == 0 || us < W.info.rtt_min ? us : W.info.rtt_min;
            W.info.rtt_max = us > W.info.rtt_max ? us : W.info.rtt_max;
            W.info.rtt_sum += us;
            W.info.rtt_last = us;
            W.info.timed++;
        }
        if (p[3] == 'O') {
            r->state = rc < 0 ? FAILED : OPEN;
            r->err = rc < 0 ? rc : 0;
        } else if (rc < 0 && r->state != FAILED) {
            r->err = rc;
        }
        if (p[3] == 'W') {
            r->writing = 0;
        }
    } else if (p[1] == 'G' && n >= 3u + 4u * k->ns) {
        for (int i = 0; i < k->ns; i++) {
            r->sv[i] = i32(p + 3 + 4 * i);
        }
    } else if (p[1] == 'R' && n >= 3u + 4u * k->np) {
        size_t len = n - 3;
        if (W.rec_n + 3 + len > RECS) {
            W.info.dropped++;
            return;
        }
        uint8_t *q = W.rec + W.rec_n;
        q[0] = (uint8_t)slot;
        q[1] = (uint8_t)len;
        q[2] = (uint8_t)(len >> 8);
        memcpy(q + 3, p + 3, len);
        W.rec_n += 3 + len;
        W.info.records++;
    }
}

void moy_dev_web_socket(int on) {
    W.open = on;
    for (uint32_t s = 0; s < MOY_DEV_HANDLES; s++) {
        row_t *r = &W.r[s];
        if (r->state == FREE) {
            continue;
        }
        r->writing = 0;
        r->asked = 0;
        if (on) {
            r->state = OPENING;
            r->err = 0;
            say_open(s);
        }
    }
}

void moy_dev_web_info(moy_dev_web_info_t *out) {
    *out = W.info;
    out->kinds = (uint32_t)W.nk;
    out->rows = 0;
    for (uint32_t s = 0; s < MOY_DEV_HANDLES; s++) {
        out->rows += W.r[s].state != FREE;
    }
}

#endif
