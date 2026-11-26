// The store's imports on the host, over malloc and the POSIX volume: what the
// ctypes binding links (tools/native_check.py --component fs). Every path
// is its own POSIX path; moy_store_host_live is the bytes held now, so a test
// can see a call leave nothing behind.

#include <stdlib.h>

#include "moy_vol.h"

static long live, most, largest;

long moy_store_host_live(void) {
    return live;
}

// The largest request and the most held at once, since the last call that
// reset them (the shell's app harness, native/moy_sh/host/app_main.c).
void moy_store_host_meter(long *biggest, long *held, int reset) {
    *biggest = largest;
    *held = most;
    if (reset) {
        largest = 0;
        most = live;
    }
}

int moy_vol_at(const char *path, moy_vol_t *v, const char **rest) {
    v->kind = MOY_VOL_KIND_POSIX;
    v->fs = NULL;
    *rest = path;
    return 0;
}

void moy_store_tick(void) {
}

void *moy_store_alloc(size_t n) {
    void *p = calloc(1, n ? n : 1);
    if (p != NULL) {
        live += (long)n;
        most = live > most ? live : most;
        largest = (long)n > largest ? (long)n : largest;
    }
    return p;
}

void *moy_store_keep(size_t n) {
    return moy_store_alloc(n);
}

void moy_store_free(void *p, size_t n) {
    if (p != NULL) {
        live -= (long)n;
        free(p);
    }
}
