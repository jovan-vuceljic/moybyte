// moy_live_svc: the live socket's apps' messages, the board's half
// (moy_live.h; moy_live.c's header is the wire, its channel 'm').
//
// An app's window runs in the page and its service on the board (#256): the
// two exchange the `send`/`on` messages they exchange on one device. Each
// end keeps a STAND-IN for the other end's processes of each app the board
// serves: a process of that app whose queue is opened MOY_EVQ_ANY
// (native/moy_kernel/moy_evq.h), so every message sent to the app on its
// end reaches it whatever the name, and what it takes crosses the socket,
// where the other end's stand-in sends it again to the app's processes
// there. The rule is each end's, as on one device: the stand-in runs the
// app, so its own processes are its senders, and a process of another app
// reaches it only by the app's `receives`. The page's half is
// moy_svc_web.c.
//
// Which apps the board serves is its service host's word
// (moy_live_svc_serve): the page is told at the socket's start and at each
// change ('H'), the board's stand-ins are made then, and its services are
// told the page came and went (the OS message "page", [up]). A message no
// frame holds (past OUT_CAP) is dropped and counted.

#include "moy_link.h"            // the board's MOY_NET_LIVE and MOY_NET_LINK
#include "moy_live.h"

#if defined(MOY_NET_LIVE) && MOY_NET_LIVE && defined(MOY_NET_LINK) && MOY_NET_LINK

#include <stdlib.h>
#include <string.h>

#include "moy_evq.h"
#include "moy_log.h"
#include "moy_net.h"

#define APPS 4                  // apps whose services this board serves to a page

static struct {
    char app[APPS][MOY_EVQ_APP];        // the apps served, "" a free row
    uint32_t gen;                       // counts their changes (moy_live_svc_serve)
    uint32_t said;                      // ...the generation the page was told
    uint32_t pid[APPS];                 // each served app's stand-in this session, 0 none
    char has[APPS][MOY_EVQ_APP];        // ...the app it stands in for
    int live;                           // a session is served
    int told;                           // ...and its services told "page" [1]
    uint32_t up, down, dropped;         // every session's
} S;

void moy_live_svc_serve(const char *app, int on) {
    int free_at = -1;
    for (int i = 0; i < APPS; i++) {
        if (strcmp(S.app[i], app) == 0) {
            if (!on) {
                S.app[i][0] = 0;
                __atomic_add_fetch(&S.gen, 1, __ATOMIC_RELEASE);
            }
            return;
        }
        free_at = free_at < 0 && !S.app[i][0] ? i : free_at;
    }
    if (on && free_at >= 0 && strlen(app) < MOY_EVQ_APP) {
        strcpy(S.app[free_at], app);
        __atomic_add_fetch(&S.gen, 1, __ATOMIC_RELEASE);
    }
}

static void say_page(int up) {
    moy_evq_route("page", up ? "[1]" : "[0]", 3);
}

static void drop_standin(int i) {
    if (S.pid[i] != 0) {
        moy_evq_close(S.pid[i]);
        S.pid[i] = 0;
        S.has[i][0] = 0;
    }
}

// The stand-ins made and ended to match the apps served, and the page told
// them ('H' and each app's name, ',' between): 0, -1 when the socket failed.
static int reconcile(void) {
    uint32_t g = __atomic_load_n(&S.gen, __ATOMIC_ACQUIRE);
    if (g == S.said) {
        return 0;
    }
    S.said = g;
    size_t cap;
    uint8_t *o = moy_live_out(&cap);
    size_t n = 2;
    o[0] = 'm';
    o[1] = 'H';
    for (int i = 0; i < APPS; i++) {
        char app[MOY_EVQ_APP];
        memcpy(app, S.app[i], sizeof app);
        app[MOY_EVQ_APP - 1] = 0;
        if (S.pid[i] != 0 && strcmp(S.has[i], app) != 0) {
            drop_standin(i);
        }
        if (!app[0]) {
            continue;
        }
        if (S.pid[i] == 0) {
            uint32_t pid = moy_log_spawn("page");
            if (moy_evq_open(pid, app, NULL, MOY_EVQ_ANY) == MOY_EVQ_OK) {
                S.pid[i] = pid;
                strcpy(S.has[i], app);
            }
        }
        size_t an = strlen(app);
        if (n + an + 1 < cap) {
            if (n > 2) {
                o[n++] = ',';
            }
            memcpy(o + n, app, an);
            n += an;
        }
    }
    return moy_live_say(n);
}

void moy_live_svc_start(void) {
    S.said = __atomic_load_n(&S.gen, __ATOMIC_ACQUIRE) - 1;    // tell the page
    S.live = 1;
    S.told = 0;
}

void moy_live_svc_end(void) {
    if (!S.live) {
        return;
    }
    S.live = 0;
    for (int i = 0; i < APPS; i++) {
        drop_standin(i);
    }
    if (S.told) {
        say_page(0);
    }
}

// An 'M' from the page: its app's stand-in here sends it to the app.
int moy_live_svc_message(const uint8_t *p, size_t n) {
    if (n < 4 || p[1] != 'M') {
        return 0;
    }
    size_t an = p[2];
    if (3 + an + 1 > n) {
        return 0;
    }
    const char *app = (const char *)p + 3;
    size_t nn = p[3 + an];
    if (4 + an + nn > n) {
        return 0;
    }
    for (int i = 0; i < APPS; i++) {
        if (S.pid[i] != 0 && strlen(S.has[i]) == an && memcmp(S.has[i], app, an) == 0) {
            uint32_t took = 0;
            S.up++;
            moy_evq_send_text(S.pid[i], app, an, (const char *)p + 4 + an, nn,
                              (const char *)p + 4 + an + nn, n - 4 - an - nn, &took);
            return 0;
        }
    }
    return 0;
}

// What the app's processes here sent the page's: an 'M' each, its app, its
// name and its arguments. 0, -1 when the socket failed.
static int relay(int i) {
    size_t cap;
    uint8_t *o = moy_live_out(&cap);
    const char *app = S.has[i];
    size_t an = strlen(app);
    moy_evq_step(S.pid[i]);
    for (;;) {
        moy_evq_ev_t ev;
        size_t at = 4 + an + MOY_EVQ_NAME;
        int rc = moy_evq_take(S.pid[i], &ev, (char *)o + at, cap - at);
        if (rc == MOY_EVQ_RANGE) {
            char *big = malloc(ev.n + 1);
            if (big == NULL || moy_evq_take(S.pid[i], &ev, big, ev.n + 1) != MOY_EVQ_OK) {
                free(big);
                return 0;
            }
            free(big);
            S.dropped++;
            continue;
        }
        if (rc != MOY_EVQ_OK) {
            return 0;
        }
        size_t nn = strlen(ev.name);
        memmove(o + 4 + an + nn, o + at, ev.n);
        o[0] = 'm';
        o[1] = 'M';
        o[2] = (uint8_t)an;
        memcpy(o + 3, app, an);
        o[3 + an] = (uint8_t)nn;
        memcpy(o + 4 + an, ev.name, nn);
        S.down++;
        if (moy_live_say(4 + an + nn + ev.n) < 0) {
            return -1;
        }
    }
}

int moy_live_svc_pump(void) {
    if (reconcile() < 0) {
        return -1;
    }
    if (!S.told) {                      // after the stand-ins, which hear the answers
        S.told = 1;
        say_page(1);
    }
    int open = 0;
    for (int i = 0; i < APPS; i++) {
        if (S.pid[i] != 0) {
            open++;
            if (relay(i) < 0) {
                return -1;
            }
        }
    }
    return open;
}

void moy_live_svc_stats(uint32_t *up, uint32_t *down, uint32_t *dropped) {
    *up = S.up;
    *down = S.down;
    *dropped = S.dropped;
}

#endif
