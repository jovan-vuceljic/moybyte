// The rows one end of the apps' prefs channel shares (native/moy_net/
// moy_svc_prefs.c), for tests/test_svc_prefs.py: a settings store over
// malloc, set, read and deleted by the test.
#include <stdlib.h>
#include <string.h>

#include "moy_settings.h"

static void *zalloc(size_t n) {
    return calloc(1, n);
}

static void release(void *p, size_t n) {
    (void)n;
    free(p);
}

static const moy_htab_mem_t MEM = {zalloc, release};
static moy_settings_t *S;

void *twin_rows(void) {
    if (S == NULL) {
        S = moy_settings_new(&MEM);
    }
    return S;
}

int twin_set(const char *k, const char *json) {
    return moy_settings_set(S, k, strlen(k), json, strlen(json));
}

int twin_delete(const char *k) {
    return moy_settings_delete(S, k, strlen(k));
}

// Row `k`'s text into `out` (cap bytes): its length, or -1 where none.
int twin_get(const char *k, char *out, size_t cap) {
    const char *j;
    size_t jn;
    if (!moy_settings_get(S, k, strlen(k), &j, &jn)) {
        return -1;
    }
    memcpy(out, j, jn < cap ? jn : cap);
    return (int)jn;
}
