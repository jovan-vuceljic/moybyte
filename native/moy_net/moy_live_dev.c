// moy_live_dev: the live socket's device channel, the board's half
// (moy_live.h; moy_live.c's header is the wire, native/moy_kernel/
// moy_dev_kinds.h's THE RELAY what a board relays).
//
// The page runs the cart; its handles of a relayed kind are remote rows
// (native/moy_net/moy_dev_web.c), and their calls arrive here in order. The
// board serves them from the kernel's handle table (moy_dev.h) as a process
// of the page's session: a pid of its own, made at the session's first open,
// with an event queue listening on each kind it opened, so the drivers post
// to it as they do to any holder (lora's "lora"). The session's end (a close,
// a takeover, a drop, an idle page) ends that process: its handles closed,
// its leases swept, its queue gone, so the radio's lease rules hold across
// pages as across programs.
//
// Each pass of the bridge pushes, per open handle, in this order: the events
// its queue took, then the records the handle's read gives (each with the
// kind's packet gets read after it), then for each event the kind's state
// gets and the event. A driver queues a record before it posts its event, so
// the page has a packet before the event that says it came. A write the
// device answers BUSY (a transmission running) waits here, in order, until it
// goes or WAIT_MS passed, and its answer is sent then: the page holds one
// write in flight a handle, so a cart sees BUSY until the board has written.

#include "moy_live.h"

#if defined(MOY_NET_LIVE) && MOY_NET_LIVE && defined(MOY_NET_LINK) && MOY_NET_LINK

#include <string.h>

#include "moy_dev.h"
#include "moy_dev_kinds.h"
#include "moy_evq.h"
#include "moy_lease.h"
#include "moy_log.h"
#include "moy_net.h"

#define DEVS 4                  // handles a page holds on its board at once
#define WAIT_MAX 256            // a write the device was busy for, kept to try again
#define WAIT_MS 5000            // ...this long at most
#define EVENTS 4                // events one pass forwards, at most
#define ARGS 96                 // an event's arguments, at most
#define READS 8                 // records one pass reads a handle, at most
#define KIND_MAX 12

typedef struct {
    int32_t h;                  // the board's handle, 0: the row is free
    uint8_t id;                 // the page's row
    char kind[KIND_MAX];
    const char *relay;          // the kind's relay list
    uint16_t wn;                // a write waiting (bytes), 0: none
    uint32_t since;
    uint8_t w[WAIT_MAX];
} dev_t;

typedef struct {
    moy_evq_ev_t ev;
    char args[ARGS];
} event_t;

typedef struct {
    dev_t d[DEVS];
    event_t evs[EVENTS];
} devs_t;

static struct {
    uint32_t pid;               // the session's process, 0 before its first open
    devs_t *t;
    uint32_t calls, writes, pushes;     // every session's
} D;

static void put32(uint8_t *p, int32_t v) {
    uint32_t u = (uint32_t)v;
    p[0] = (uint8_t)u;
    p[1] = (uint8_t)(u >> 8);
    p[2] = (uint8_t)(u >> 16);
    p[3] = (uint8_t)(u >> 24);
}

// The gets of list `l` (comma-separated, up to its ':' or end) of handle `d`,
// each 4 bytes into `out`: how many bytes.
static size_t gets(const dev_t *d, const char *l, uint8_t *out) {
    size_t n = 0;
    while (*l && *l != ':') {
        const char *e = l;
        while (*e && *e != ',' && *e != ':') {
            e++;
        }
        put32(out + n, moy_dev_get(D.pid, d->h, l, (size_t)(e - l)));
        n += 4;
        l = *e == ',' ? e + 1 : e;
    }
    return n;
}

static const char *state_list(const dev_t *d) {
    const char *s = strchr(d->relay, ':');
    return s != NULL ? s + 1 : "";
}

static int answer(const dev_t *d, uint8_t id, char verb, int32_t rc) {
    size_t cap;
    uint8_t *o = moy_live_out(&cap);
    o[0] = 'd';
    o[1] = 'A';
    o[2] = id;
    o[3] = (uint8_t)verb;
    put32(o + 4, rc);
    if (moy_live_say(8) < 0) {
        return -1;
    }
    if (d == NULL || d->h <= 0) {
        return 0;
    }
    o[1] = 'G';
    return moy_live_say(3 + gets(d, state_list(d), o + 3));
}

static dev_t *row(uint8_t id) {
    for (int i = 0; D.t != NULL && i < DEVS; i++) {
        if (D.t->d[i].h > 0 && D.t->d[i].id == id) {
            return &D.t->d[i];
        }
    }
    return NULL;
}

static void close_dev(dev_t *d) {
    moy_dev_close(D.pid, d->h);
    moy_evq_listen(D.pid, d->kind, false);
    d->h = 0;
    d->wn = 0;
}

// The session's process, made at its first open: 0, or -1 with no memory.
static int session(void) {
    if (D.pid != 0) {
        return 0;
    }
    D.t = moy_net_alloc(sizeof *D.t);
    if (D.t == NULL) {
        return -1;
    }
    memset(D.t, 0, sizeof *D.t);
    D.pid = moy_log_spawn("page");
    if (moy_evq_open(D.pid, "page", NULL, 0) != MOY_EVQ_OK) {
        moy_net_free(D.t);
        D.t = NULL;
        D.pid = 0;
        return -1;
    }
    return 0;
}

static int open_dev(uint8_t id, const uint8_t *p, size_t n) {
    if (n < 1 || (size_t)p[0] + 1 > n || p[0] == 0 || p[0] >= KIND_MAX) {
        return answer(NULL, id, 'O', MOY_DEV_EBAD);
    }
    const char *kind = (const char *)p + 1;
    size_t kn = p[0];
    const char *relay = moy_dev_relay_of(kind, kn);
    if (relay == NULL) {
        return answer(NULL, id, 'O', MOY_DEV_EABSENT);
    }
    if (session() < 0) {
        return answer(NULL, id, 'O', MOY_DEV_ENOMEM);
    }
    dev_t *d = row(id);
    if (d != NULL) {
        close_dev(d);
    }
    for (int i = 0; i < DEVS && d == NULL; i++) {
        d = D.t->d[i].h <= 0 ? &D.t->d[i] : NULL;
    }
    if (d == NULL) {
        return answer(NULL, id, 'O', MOY_DEV_EFULL);
    }
    memcpy(d->kind, kind, kn);
    d->kind[kn] = 0;
    // listening first: an event the open itself causes is the page's too
    moy_evq_listen(D.pid, d->kind, true);
    int32_t h = moy_dev_open(D.pid, moy_dev_perm_bit(kind, kn), kind, kn,
                             (const char *)p + 1 + kn, n - 1 - kn);
    if (h <= 0) {
        moy_evq_listen(D.pid, d->kind, false);
        return answer(NULL, id, 'O', h == 0 ? MOY_DEV_EIO : h);
    }
    d->h = h;
    d->id = id;
    d->relay = relay;
    d->wn = 0;
    return answer(d, id, 'O', 0);
}

static int write_dev(dev_t *d, const uint8_t *p, size_t n) {
    if (d->wn) {
        return answer(d, d->id, 'W', MOY_DEV_EBUSY);
    }
    int32_t r = moy_dev_write(D.pid, d->h, p, n);
    D.writes += r >= 0;
    if (r == MOY_DEV_EBUSY && n > 0 && n <= WAIT_MAX) {
        memcpy(d->w, p, n);
        d->wn = (uint16_t)n;
        d->since = moy_net_ms();
        return 0;
    }
    return answer(d, d->id, 'W', r);
}

int moy_live_dev_message(const uint8_t *p, size_t n) {
    if (n < 3) {
        return 0;
    }
    D.calls++;
    uint8_t id = p[2];
    if (p[1] == 'O') {
        return open_dev(id, p + 3, n - 3);
    }
    dev_t *d = row(id);
    switch (p[1]) {
        case 'C':
            if (d != NULL) {
                close_dev(d);
            }
            return 0;
        case 'W':
            return d == NULL ? answer(NULL, id, 'W', MOY_DEV_EABSENT) : write_dev(d, p + 3, n - 3);
        case 'S':
            return d == NULL ? answer(NULL, id, 'S', MOY_DEV_EABSENT)
                   : answer(d, id, 'S', moy_dev_set(D.pid, d->h, (const char *)p + 3, n - 3));
        default:
            return 0;
    }
}

// Handle `d`'s records, to the page.
static int reads(dev_t *d) {
    size_t cap;
    uint8_t *o = moy_live_out(&cap);
    size_t np = d->relay[0] != ':' && d->relay[0] != 0;     // the packet gets
    for (const char *l = d->relay; *l && *l != ':'; l++) {
        np += *l == ',';
    }
    size_t at = 3 + 4 * np;
    for (int i = 0; i < READS; i++) {
        int32_t r = moy_dev_read(D.pid, d->h, o + at, cap - at);
        if (r <= 0) {
            break;
        }
        o[0] = 'd';
        o[1] = 'R';
        o[2] = d->id;
        gets(d, d->relay, o + 3);
        if (moy_live_say(at + (size_t)r) < 0) {
            return -1;
        }
        D.pushes++;
    }
    return 0;
}

int moy_live_dev_pump(void) {
    if (D.t == NULL) {
        return 0;
    }
    int open = 0;
    for (int i = 0; i < DEVS; i++) {
        dev_t *d = &D.t->d[i];
        if (d->h <= 0 || !d->wn) {
            continue;
        }
        int32_t r = moy_dev_write(D.pid, d->h, d->w, d->wn);
        D.writes += r >= 0;
        if (r != MOY_DEV_EBUSY || moy_net_ms() - d->since > WAIT_MS) {
            d->wn = 0;
            if (answer(d, d->id, 'W', r) < 0) {
                return -1;
            }
        }
    }
    int ne = 0;
    moy_evq_step(D.pid);
    while (ne < EVENTS
           && moy_evq_take(D.pid, &D.t->evs[ne].ev, D.t->evs[ne].args, ARGS) == MOY_EVQ_OK) {
        ne++;
    }
    for (int i = 0; i < DEVS; i++) {
        dev_t *d = &D.t->d[i];
        if (d->h > 0) {
            open++;
            if (reads(d) < 0) {
                return -1;
            }
        }
    }
    for (int e = 0; e < ne; e++) {
        const event_t *ev = &D.t->evs[e];
        size_t cap;
        uint8_t *o = moy_live_out(&cap);
        for (int i = 0; i < DEVS; i++) {
            dev_t *d = &D.t->d[i];
            if (d->h > 0 && strcmp(d->kind, ev->ev.name) == 0) {
                o[0] = 'd';
                o[1] = 'G';
                o[2] = d->id;
                if (moy_live_say(3 + gets(d, state_list(d), o + 3)) < 0) {
                    return -1;
                }
            }
        }
        size_t nn = strlen(ev->ev.name);
        size_t an = ev->ev.n < ARGS ? ev->ev.n : 0;
        if (4 + nn + an > cap) {
            continue;
        }
        o[0] = 'd';
        o[1] = 'E';
        o[2] = (uint8_t)nn;
        memcpy(o + 3, ev->ev.name, nn);
        memcpy(o + 3 + nn, ev->args, an);
        if (moy_live_say(3 + nn + an) < 0) {
            return -1;
        }
        D.pushes++;
    }
    return open;
}

void moy_live_dev_end(void) {
    if (D.pid == 0) {
        return;
    }
    moy_dev_sweep(D.pid);
    moy_lease_sweep(D.pid);
    moy_evq_close(D.pid);
    moy_net_free(D.t);
    D.t = NULL;
    D.pid = 0;
}

void moy_live_dev_stats(moy_live_stats_t *out) {
    out->devs = 0;
    for (int i = 0; D.t != NULL && i < DEVS; i++) {
        out->devs += D.t->d[i].h > 0;
    }
    out->dev_calls = D.calls;
    out->dev_writes = D.writes;
    out->dev_pushes = D.pushes;
}

size_t moy_web_live_kinds(char *out, size_t cap) {
    return moy_dev_relayed(out, cap);
}

#endif
