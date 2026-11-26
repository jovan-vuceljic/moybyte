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
//
// THE PINS (moy_dev_kinds.h's MOY_DEV_PINS; moy_live.c's header is the wire):
// a board that serves its pins to its page (/gpio, moy_gpio.c) relays them
// here too, as the kind "pins", one row a page, which the page's pin verbs
// hold (firmware/web_runner/gpio_link.py) while its socket is open. A write
// is driven as it arrives and a refusal answered; the pins the page watches
// are read after each of its messages and each pass, and pushed when one
// changed. The ops are moy_gpio_op's, so the allowlist, the process that
// holds the pins ("web") and their leases are /gpio's, and the socket's end
// leaves them driven, as a page gone from /gpio does.

#include "moy_link.h"            // the board's MOY_NET_LIVE and MOY_NET_LINK
#include "moy_live.h"
#include "moy_dev_kinds.h"       // MOY_DEV_RELAYS, MOY_DEV_PINS

#if defined(MOY_NET_LIVE) && MOY_NET_LIVE && defined(MOY_NET_LINK) && MOY_NET_LINK \
    && ((defined(MOY_DEV_RELAYS) && MOY_DEV_RELAYS) || (defined(MOY_DEV_PINS) && MOY_DEV_PINS))

#include <string.h>

#include "moy_dev.h"
#include "moy_net.h"

#if defined(MOY_DEV_RELAYS) && MOY_DEV_RELAYS
#define RELAYS 1
#else
#define RELAYS 0
#endif
#if defined(MOY_DEV_PINS) && MOY_DEV_PINS
#define PINS 1
#pragma weak moy_gpio_pins
#else
#define PINS 0
#endif

static struct {
    uint32_t calls, writes, pushes;     // every session's
} N;

static void put32(uint8_t *p, int32_t v) {
    uint32_t u = (uint32_t)v;
    p[0] = (uint8_t)u;
    p[1] = (uint8_t)(u >> 8);
    p[2] = (uint8_t)(u >> 16);
    p[3] = (uint8_t)(u >> 24);
}

// An 'A': the answer to row `id`'s `verb`.
static int say_answer(uint8_t id, char verb, int32_t rc) {
    size_t cap;
    uint8_t *o = moy_live_out(&cap);
    o[0] = 'd';
    o[1] = 'A';
    o[2] = id;
    o[3] = (uint8_t)verb;
    put32(o + 4, rc);
    return moy_live_say(8);
}

#if PINS

#define WATCH_MAX 16            // the pins a page watches at once

static struct {
    uint8_t open, id;           // the page's pins row
    uint8_t n;                  // pins watched
    uint8_t w[WATCH_MAX];
    int32_t last[WATCH_MAX];    // ...and the levels last pushed
    uint8_t stale;              // push them whatever they read
} P;

static int32_t pins_code(int rc) {
    return rc == MOY_GPIO_EPIN ? MOY_DEV_EBAD : rc == MOY_GPIO_EBUSY ? MOY_DEV_EBUSY
           : rc < 0 ? MOY_DEV_EIO : rc;
}

// The watched pins read, and pushed ('G') where one changed: 0, -1 when the
// socket failed.
static int pins_push(void) {
    if (!P.open || P.n == 0) {
        return 0;
    }
    size_t cap;
    uint8_t *o = moy_live_out(&cap);
    int changed = P.stale;
    for (int i = 0; i < P.n; i++) {
        int32_t v = pins_code(moy_gpio_op(P.w[i], 0, 0));
        changed |= v != P.last[i];
        P.last[i] = v;
        put32(o + 3 + 4 * i, v);
    }
    if (!changed) {
        return 0;
    }
    P.stale = 0;
    o[0] = 'd';
    o[1] = 'G';
    o[2] = P.id;
    N.pushes++;
    return moy_live_say(3 + 4 * (size_t)P.n);
}

// A message of the pins row (`p` its plaintext, n bytes).
static int pins_message(const uint8_t *p, size_t n) {
    switch (p[1]) {
        case 'C':
            P.open = 0;
            return 0;
        case 'W':
            for (size_t i = 3; i + 1 < n; i += 2) {
                int rc = moy_gpio_op(p[i], 1, p[i + 1]);
                N.writes += rc >= 0;
                if (rc < 0) {
                    size_t cap;
                    uint8_t *o = moy_live_out(&cap);
                    o[0] = 'd';
                    o[1] = 'A';
                    o[2] = P.id;
                    o[3] = 'W';
                    put32(o + 4, pins_code(rc));
                    o[8] = p[i];
                    if (moy_live_say(9) < 0) {
                        return -1;
                    }
                }
            }
            return pins_push();
        case 'S':
            P.n = 0;
            for (size_t i = 3; i < n && P.n < WATCH_MAX; i++) {
                P.w[P.n++] = p[i];
            }
            P.stale = 1;
            return P.n > 0 ? pins_push() : 0;
        default:
            return 0;
    }
}

static int pins_open(uint8_t id) {
    const uint8_t *pins = NULL;
    if (moy_gpio_pins == NULL || moy_gpio_pins(&pins) <= 0) {
        return say_answer(id, 'O', MOY_DEV_EABSENT);
    }
    P.open = 1;
    P.id = id;
    P.n = 0;
    return say_answer(id, 'O', 0);
}

#endif

#if RELAYS

#include "moy_evq.h"
#include "moy_lease.h"
#include "moy_log.h"

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
} relay_row_t;

typedef struct {
    moy_evq_ev_t ev;
    char args[ARGS];
} event_t;

typedef struct {
    relay_row_t d[DEVS];
    event_t evs[EVENTS];
} devs_t;

static struct {
    uint32_t pid;               // the session's process, 0 before its first open
    devs_t *t;
} D;

// The gets of list `l` (comma-separated, up to its ':' or end) of handle `d`,
// each 4 bytes into `out`: how many bytes.
static size_t read_gets(const relay_row_t *d, const char *l, uint8_t *out) {
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

static const char *state_list(const relay_row_t *d) {
    const char *s = strchr(d->relay, ':');
    return s != NULL ? s + 1 : "";
}

static int answer(const relay_row_t *d, uint8_t id, char verb, int32_t rc) {
    if (say_answer(id, verb, rc) < 0) {
        return -1;
    }
    if (d == NULL || d->h <= 0) {
        return 0;
    }
    size_t cap;
    uint8_t *o = moy_live_out(&cap);
    o[0] = 'd';
    o[1] = 'G';
    o[2] = id;
    return moy_live_say(3 + read_gets(d, state_list(d), o + 3));
}

static relay_row_t *row(uint8_t id) {
    for (int i = 0; D.t != NULL && i < DEVS; i++) {
        if (D.t->d[i].h > 0 && D.t->d[i].id == id) {
            return &D.t->d[i];
        }
    }
    return NULL;
}

static void close_dev(relay_row_t *d) {
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
    relay_row_t *d = row(id);
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

static int write_dev(relay_row_t *d, const uint8_t *p, size_t n) {
    if (d->wn) {
        return answer(d, d->id, 'W', MOY_DEV_EBUSY);
    }
    int32_t r = moy_dev_write(D.pid, d->h, p, n);
    N.writes += r >= 0;
    if (r == MOY_DEV_EBUSY && n > 0 && n <= WAIT_MAX) {
        memcpy(d->w, p, n);
        d->wn = (uint16_t)n;
        d->since = moy_net_ms();
        return 0;
    }
    return answer(d, d->id, 'W', r);
}

static int kinds_message(const uint8_t *p, size_t n) {
    uint8_t id = p[2];
    if (p[1] == 'O') {
        return open_dev(id, p + 3, n - 3);
    }
    relay_row_t *d = row(id);
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
static int reads(relay_row_t *d) {
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
        read_gets(d, d->relay, o + 3);
        if (moy_live_say(at + (size_t)r) < 0) {
            return -1;
        }
        N.pushes++;
    }
    return 0;
}

static int kinds_pump(void) {
    if (D.t == NULL) {
        return 0;
    }
    int open = 0;
    for (int i = 0; i < DEVS; i++) {
        relay_row_t *d = &D.t->d[i];
        if (d->h <= 0 || !d->wn) {
            continue;
        }
        int32_t r = moy_dev_write(D.pid, d->h, d->w, d->wn);
        N.writes += r >= 0;
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
        relay_row_t *d = &D.t->d[i];
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
            relay_row_t *d = &D.t->d[i];
            if (d->h > 0 && strcmp(d->kind, ev->ev.name) == 0) {
                o[0] = 'd';
                o[1] = 'G';
                o[2] = d->id;
                if (moy_live_say(3 + read_gets(d, state_list(d), o + 3)) < 0) {
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
        N.pushes++;
    }
    return open;
}

static void kinds_end(void) {
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

static uint32_t kinds_open(void) {
    uint32_t k = 0;
    for (int i = 0; D.t != NULL && i < DEVS; i++) {
        k += D.t->d[i].h > 0;
    }
    return k;
}
#endif

int moy_live_dev_message(const uint8_t *p, size_t n) {
    if (n < 3) {
        return 0;
    }
    N.calls++;
#if PINS
    if (p[1] == 'O' && n >= 8 && p[3] == 4 && memcmp(p + 4, "pins", 4) == 0) {
        return pins_open(p[2]);
    }
    if (P.open && p[2] == P.id && p[1] != 'O') {
        return pins_message(p, n);
    }
#endif
#if RELAYS
    return kinds_message(p, n);
#else
    return p[1] == 'C' ? 0 : say_answer(p[2], (char)p[1], MOY_DEV_EABSENT);
#endif
}

int moy_live_dev_pump(void) {
    int open = 0;
#if PINS
    if (pins_push() < 0) {
        return -1;
    }
    open += P.open;
#endif
#if RELAYS
    int k = kinds_pump();
    if (k < 0) {
        return -1;
    }
    open += k;
#endif
    return open;
}

void moy_live_dev_end(void) {
#if PINS
    P.open = 0;
#endif
#if RELAYS
    kinds_end();
#endif
}

void moy_live_dev_stats(moy_live_stats_t *out) {
    out->devs = 0;
#if PINS
    out->devs += P.open;
#endif
#if RELAYS
    out->devs += kinds_open();
#endif
    out->dev_calls = N.calls;
    out->dev_writes = N.writes;
    out->dev_pushes = N.pushes;
}

size_t moy_web_live_kinds(char *out, size_t cap) {
    size_t n = 0;
#if RELAYS
    n = moy_dev_relayed(out, cap);
#endif
#if PINS
    const uint8_t *pins = NULL;
    if (moy_gpio_pins != NULL && moy_gpio_pins(&pins) > 0 && n + 6 < cap) {
        if (n > 0) {
            out[n++] = ';';
        }
        memcpy(out + n, "pins", 5);
        n += 4;
    }
#endif
    if (cap > 0) {
        out[n] = 0;
    }
    return n;
}

#endif
