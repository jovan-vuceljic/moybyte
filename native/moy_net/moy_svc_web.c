// moy_svc_web: the live socket's apps' messages, the page's half
// (moy_live.c's header is the wire, its channel 'm'; moy_live_svc.c the
// board's half and the design).
//
// For each app whose service runs on the page's board (the board's 'H'),
// the page keeps a STAND-IN: a process of that app whose queue hears every
// message sent to it (native/moy_kernel/moy_evq.h's MOY_EVQ_ANY), so a
// window's `moybyte.send(app, name, ...)` reaches it as it would reach the
// service on one device; what it takes goes up the socket ('M'), and an 'M'
// the board sends is sent again from it to the app's processes here, the
// window's `moybyte.on(name, fn)` among them, the sender the app's own.
//
// A dropped socket is never silent: its stand-ins end with it, so a send
// to the app meanwhile reaches none (`send` answers 0), and the OS message
// "board" is routed to every process that listens on it, [0, why] at the
// drop and [1] once the board has said its apps again. The worker moves the
// bytes between frames (moy_link_web.c's queue).

#include "moy_platform.h"       // first: the clock, under the port's -std=c99 too

#if defined(MOY_NET_LIVE_PAGE) && MOY_NET_LIVE_PAGE

#include <stdlib.h>
#include <string.h>

#include "moy_evq.h"
#include "moy_link.h"
#include "moy_log.h"

#define APPS 4

static struct {
    char app[APPS][MOY_EVQ_APP];
    uint32_t pid[APPS];                 // each app's stand-in, 0: none
    int told;                           // "board" [1] said since the socket opened
    uint32_t up, down, dropped;
} W;

static void end_standin(int i) {
    if (W.pid[i] != 0) {
        moy_evq_close(W.pid[i]);
        W.pid[i] = 0;
        W.app[i][0] = 0;
    }
}

// The board's 'H': the stand-ins made and ended to match `apps` (n bytes,
// ',' between).
static void apps_are(const char *apps, size_t n) {
    for (int i = 0; i < APPS; i++) {
        size_t an = strlen(W.app[i]);
        bool kept = false;
        for (size_t at = 0; an && at < n;) {
            const char *c = memchr(apps + at, ',', n - at);
            size_t k = c != NULL ? (size_t)(c - apps - at) : n - at;
            kept |= k == an && memcmp(apps + at, W.app[i], an) == 0;
            at += k + 1;
        }
        if (!kept) {
            end_standin(i);
        }
    }
    for (size_t at = 0; at < n;) {
        const char *c = memchr(apps + at, ',', n - at);
        size_t k = c != NULL ? (size_t)(c - apps - at) : n - at;
        bool have = false;
        int free_at = -1;
        for (int i = 0; i < APPS; i++) {
            have |= W.pid[i] != 0 && strlen(W.app[i]) == k && memcmp(W.app[i], apps + at, k) == 0;
            free_at = free_at < 0 && W.pid[i] == 0 ? i : free_at;
        }
        if (!have && free_at >= 0 && k > 0 && k < MOY_EVQ_APP) {
            memcpy(W.app[free_at], apps + at, k);
            W.app[free_at][k] = 0;
            uint32_t pid = moy_log_spawn("board");
            if (moy_evq_open(pid, W.app[free_at], NULL, MOY_EVQ_ANY) == MOY_EVQ_OK) {
                W.pid[free_at] = pid;
            } else {
                W.app[free_at][0] = 0;
            }
        }
        at += k + 1;
    }
    if (!W.told) {
        W.told = 1;
        moy_evq_route("board", "[1]", 3);
    }
}

void moy_svc_web_give(const uint8_t *p, size_t n) {
    if (n >= 2 && p[1] == 'H') {
        apps_are((const char *)p + 2, n - 2);
        return;
    }
    if (n < 4 || p[1] != 'M') {
        return;
    }
    size_t an = p[2];
    if (3 + an + 1 > n) {
        return;
    }
    size_t nn = p[3 + an];
    if (4 + an + nn > n) {
        return;
    }
    for (int i = 0; i < APPS; i++) {
        if (W.pid[i] != 0 && strlen(W.app[i]) == an && memcmp(W.app[i], p + 3, an) == 0) {
            uint32_t took = 0;
            W.down++;
            moy_evq_send_text(W.pid[i], W.app[i], an, (const char *)p + 4 + an, nn,
                              (const char *)p + 4 + an + nn, n - 4 - an - nn, &took);
            return;
        }
    }
}

void moy_svc_web_socket(int on) {
    if (on) {
        W.told = 0;
        return;
    }
    for (int i = 0; i < APPS; i++) {
        end_standin(i);
    }
    W.told = 0;
    moy_evq_route("board", "[0,\"lost\"]", 10);
}

// Between frames, before the link's queue is taken: what the app's
// processes here sent the board's, an 'M' each.
void moy_svc_web_pump(void) {
    static char args[1400];
    for (int i = 0; i < APPS; i++) {
        if (W.pid[i] == 0) {
            continue;
        }
        moy_evq_step(W.pid[i]);
        for (;;) {
            moy_evq_ev_t ev;
            int rc = moy_evq_take(W.pid[i], &ev, args, sizeof args);
            if (rc == MOY_EVQ_RANGE) {
                char *big = malloc(ev.n + 1);
                int got = big != NULL ? moy_evq_take(W.pid[i], &ev, big, ev.n + 1) : rc;
                free(big);
                W.dropped++;
                if (got != MOY_EVQ_OK) {
                    break;
                }
                continue;
            }
            if (rc != MOY_EVQ_OK) {
                break;
            }
            size_t an = strlen(W.app[i]), nn = strlen(ev.name);
            uint8_t *q = moy_link_web_queue(4 + an + nn + ev.n);
            if (q == NULL) {
                W.dropped++;
                continue;
            }
            q[0] = 'm';
            q[1] = 'M';
            q[2] = (uint8_t)an;
            memcpy(q + 3, W.app[i], an);
            q[3 + an] = (uint8_t)nn;
            memcpy(q + 4 + an, ev.name, nn);
            memcpy(q + 4 + an + nn, args, ev.n);
            W.up++;
        }
    }
}

size_t moy_svc_web_served(char *out, size_t cap) {
    size_t n = 0;
    for (int i = 0; i < APPS; i++) {
        size_t an = W.pid[i] != 0 ? strlen(W.app[i]) : 0;
        if (an == 0 || n + an + 1 > cap) {
            continue;
        }
        if (n > 0) {
            out[n++] = ',';
        }
        memcpy(out + n, W.app[i], an);
        n += an;
    }
    return n;
}

void moy_svc_web_stats(uint32_t *apps, uint32_t *up, uint32_t *down, uint32_t *dropped) {
    uint32_t k = 0;
    for (int i = 0; i < APPS; i++) {
        k += W.pid[i] != 0;
    }
    *apps = k;
    *up = W.up;
    *down = W.down;
    *dropped = W.dropped;
}

#endif
