// moy_svc_prefs: an app's prefs rows, shared by its service on the board and
// its windows on the page (#256; moy_live.c's THE APPS' MESSAGES, 'P').
//
// An app whose service runs on the board keeps its prefs (native/moy_app's
// `<ns>_<key>` settings rows) on both ends: the service writes the board's,
// a window the page's. Each end scans its rows of the apps served (a row
// whose key is `<app>_...`) when they changed (moy_settings_gen) and sends
// each row whose text differs from what the two ends last agreed on, in
// pieces a frame holds; the other end writes it into its own rows and takes
// it as agreed, so it never comes back. A row gone on one end goes as a
// delete. The scan runs before the end relays its apps' messages, so a row
// a service wrote before it sent "heard" reaches the page before "heard".
//
// THE START. At a session's start the board forgets what was agreed, so
// every served app's rows go down; the page takes the rows it holds as
// agreed when the board names an app ('H'), so the board's win: the
// service's state is the board's, and a window's own row goes up only once
// the window changes it.
//
// THE TABLE. What was agreed is a hash of each row's key and of its text,
// and the key itself in an arena: allocated at the first app served (on the
// board, the service host's start), never on an end that serves none. Full,
// it is forgotten whole: the board then sends every row again, the page
// takes its rows as agreed again.

#include "moy_platform.h"       // first: the clock, under the port's -std=c99 too

#include "moy_link.h"           // the board's MOY_NET_LIVE

#if (defined(MOY_NET_LIVE) && MOY_NET_LIVE) || (defined(MOY_NET_LIVE_PAGE) && MOY_NET_LIVE_PAGE)

#include <stdlib.h>
#include <string.h>

#include "moy_kmem.h"
#include "moy_settings.h"

#define ROWS 64                         // rows agreed on, every app's
#define ARENA 2048                      // their keys' bytes
#define ROW_MAX (64u * 1024u)           // the longest row that crosses
#define GONE 0xFFFFFFFFu                // a piece's total: the row deleted

typedef struct {
    uint32_t kh, vh;                    // the key's hash and the agreed text's
    uint16_t at, n;                     // the key in the arena
    uint8_t seen;                       // in the scan under way
} agreed_t;

static struct {
    moy_settings_t *rows;
    agreed_t *t;                        // ROWS of them, then the arena
    char *arena;
    uint32_t used, an;                  // rows and arena bytes used
    uint32_t gen;                       // the rows' gen at the last scan
    int fresh;                          // scan whatever the gen says
    char *in;                           // a row coming in, its key first
    uint32_t in_total, in_at, in_kn;
    uint32_t sent, took;                // rows each way
} R;

static uint32_t hash(const char *p, size_t n) {
    uint32_t h = 2166136261u;
    for (size_t i = 0; i < n; i++) {
        h = (h ^ (uint8_t)p[i]) * 16777619u;
    }
    return h;
}

void moy_svc_prefs_rows(struct moy_settings *rows) {
    if (R.rows != rows) {
        R.rows = rows;
        R.fresh = 1;
    }
}

static void forget(void) {
    R.used = R.an = 0;
    R.fresh = 1;
}

static int ready(void) {
    if (R.t == NULL) {
        R.t = moy_kalloc(ROWS * sizeof(agreed_t) + ARENA, MOY_KMEM_LIBC);
        if (R.t == NULL) {
            return 0;
        }
        R.arena = (char *)(R.t + ROWS);
        forget();
    }
    return 1;
}

static agreed_t *find(const char *k, size_t kn, uint32_t kh) {
    for (uint32_t i = 0; i < R.used; i++) {
        agreed_t *e = &R.t[i];
        if (e->kh == kh && e->n == kn && memcmp(R.arena + e->at, k, kn) == 0) {
            return e;
        }
    }
    return NULL;
}

// Row `k` agreed on at text hash `vh`: 0 where the table is full (it is
// then forgotten whole, THE TABLE).
static int agree(const char *k, size_t kn, uint32_t vh) {
    uint32_t kh = hash(k, kn);
    agreed_t *e = find(k, kn, kh);
    if (e == NULL) {
        if (R.used == ROWS || R.an + kn > ARENA) {
            forget();
            return 0;
        }
        e = &R.t[R.used++];
        e->kh = kh;
        e->at = (uint16_t)R.an;
        e->n = (uint16_t)kn;
        memcpy(R.arena + R.an, k, kn);
        R.an += (uint32_t)kn;
    }
    e->vh = vh;
    e->seen = 1;
    return 1;
}

static void drop(agreed_t *e) {
    *e = R.t[--R.used];                 // its key's bytes stay until a forget
}

// Whether row key `k` is one of `apps`' (`<app>_...`).
static int served(const char *k, size_t kn, const char *const *apps, int napps) {
    for (int i = 0; i < napps; i++) {
        size_t an = apps[i] != NULL ? strlen(apps[i]) : 0;
        if (an && kn > an + 1 && memcmp(k, apps[i], an) == 0 && k[an] == '_') {
            return 1;
        }
    }
    return 0;
}

void moy_svc_prefs_start(int board) {
    if (board) {
        forget();
    } else {
        R.fresh = 1;
    }
    moy_kfree(R.in);
    R.in = NULL;
}

void moy_svc_prefs_baseline(const char *const *apps, int napps) {
    if (R.rows == NULL || !ready()) {
        return;
    }
    moy_settings_lock();
    const char *k, *j;
    size_t kn, jn;
    for (uint32_t i = 0; moy_settings_at(R.rows, i, &k, &kn, &j, &jn); i++) {
        if (served(k, kn, apps, napps)) {
            agree(k, kn, hash(j, jn));
        }
    }
    R.gen = moy_settings_gen(R.rows);
    R.fresh = 0;
    moy_settings_unlock();
}

// Row `k` (text `j`, `jn` bytes; GONE for a delete) as 'P' pieces through
// `say`. 0, -1 when a say failed.
static int send_row(const char *k, size_t kn, const char *j, uint32_t jn, uint8_t *buf,
                    size_t cap, int (*say)(void *, uint8_t *, size_t), void *ctx) {
    size_t head = 3 + kn + 8;
    if (cap <= head + 16) {
        return 0;
    }
    uint32_t total = jn, at = 0;
    do {
        uint32_t piece = total == GONE ? 0 : total - at;
        if (piece > cap - head) {
            piece = (uint32_t)(cap - head);
        }
        buf[0] = 'm';
        buf[1] = 'P';
        buf[2] = (uint8_t)kn;
        memcpy(buf + 3, k, kn);
        uint8_t *q = buf + 3 + kn;
        for (int b = 0; b < 4; b++) {
            q[b] = (uint8_t)(total >> (8 * b));
            q[4 + b] = (uint8_t)(at >> (8 * b));
        }
        if (piece) {
            memcpy(buf + head, j + at, piece);
        }
        if (say(ctx, buf, head + piece) < 0) {
            return -1;
        }
        at += piece;
    } while (total != GONE && at < total);
    R.sent++;
    return 0;
}

int moy_svc_prefs_scan(const char *const *apps, int napps, uint8_t *buf, size_t cap,
                       int (*say)(void *, uint8_t *, size_t), void *ctx) {
    if (R.rows == NULL || napps == 0 || !ready()) {
        return 0;
    }
    uint32_t g = moy_settings_gen(R.rows);
    if (g == R.gen && !R.fresh) {
        return 0;
    }
    R.gen = g;
    R.fresh = 0;
    for (uint32_t i = 0; i < R.used; i++) {
        R.t[i].seen = 0;
    }
    int rc = 0;
    moy_settings_lock();
    const char *k, *j;
    size_t kn, jn;
    for (uint32_t i = 0; rc == 0 && moy_settings_at(R.rows, i, &k, &kn, &j, &jn); i++) {
        if (!served(k, kn, apps, napps) || kn > 255 || jn > ROW_MAX) {
            continue;
        }
        uint32_t vh = hash(j, jn);
        agreed_t *e = find(k, kn, hash(k, kn));
        if (e != NULL && e->vh == vh) {
            e->seen = 1;
            continue;
        }
        rc = send_row(k, kn, j, (uint32_t)jn, buf, cap, say, ctx);
        if (rc == 0 && !agree(k, kn, vh)) {
            break;                      // forgotten: the next scan sends again
        }
    }
    moy_settings_unlock();
    for (uint32_t i = 0; rc == 0 && i < R.used;) {
        agreed_t *e = &R.t[i];
        if (e->seen || !served(R.arena + e->at, e->n, apps, napps)) {
            i++;
            continue;
        }
        rc = send_row(R.arena + e->at, e->n, NULL, GONE, buf, cap, say, ctx);
        drop(e);
    }
    return rc;
}

void moy_svc_prefs_give(const uint8_t *p, size_t n, const char *const *apps, int napps) {
    if (n < 3 || R.rows == NULL || !ready()) {
        return;
    }
    size_t kn = p[2];
    if (3 + kn + 8 > n || !served((const char *)p + 3, kn, apps, napps)) {
        return;
    }
    const char *k = (const char *)p + 3;
    const uint8_t *q = p + 3 + kn;
    uint32_t total = 0, at = 0;
    for (int b = 0; b < 4; b++) {
        total |= (uint32_t)q[b] << (8 * b);
        at |= (uint32_t)q[4 + b] << (8 * b);
    }
    const char *piece = (const char *)q + 8;
    size_t pn = n - 3 - kn - 8;
    if (total == GONE) {
        agreed_t *e = find(k, kn, hash(k, kn));
        if (e != NULL) {
            drop(e);
        }
        moy_settings_delete(R.rows, k, kn);
        R.gen = moy_settings_gen(R.rows);
        R.took++;
        return;
    }
    if (at == 0) {
        moy_kfree(R.in);
        R.in = total <= ROW_MAX ? moy_kalloc(kn + total + 1, MOY_KMEM_LIBC) : NULL;
        if (R.in == NULL) {
            return;
        }
        memcpy(R.in, k, kn);
        R.in_total = total;
        R.in_at = 0;
        R.in_kn = (uint32_t)kn;
    }
    if (R.in == NULL || at != R.in_at || total != R.in_total || kn != R.in_kn
        || memcmp(R.in, k, kn) != 0 || at + pn > total) {
        moy_kfree(R.in);                // a piece out of order: the row is lost
        R.in = NULL;
        return;
    }
    memcpy(R.in + kn + at, piece, pn);
    R.in_at += (uint32_t)pn;
    if (R.in_at < total) {
        return;
    }
    const char *j = R.in + kn;
    // the gen this write makes is the scan's to pass over, the row agreed
    int fresh = moy_settings_gen(R.rows) != R.gen;
    if (moy_settings_validate(j, total) == MOY_SETTINGS_OK
        && moy_settings_set(R.rows, k, kn, j, total) == MOY_SETTINGS_OK) {
        agree(k, kn, hash(j, total));
        if (!fresh) {
            R.gen = moy_settings_gen(R.rows);
        }
        R.took++;
    }
    moy_kfree(R.in);
    R.in = NULL;
}

void moy_svc_prefs_stats(uint32_t *sent, uint32_t *took) {
    *sent = R.sent;
    *took = R.took;
}

#endif
