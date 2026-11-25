// What the AOT fuzz targets link beside WAMR and moy_ota.c: the host's
// allocation and hash, the http pool's clock and checks (no connection is
// ever kept here), and a native-call entry that never runs code.
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include "moy_ota.h"
void *moy_net_alloc(size_t n) { return malloc(n); }
void moy_net_free(void *p) { free(p); }
void moy_net_sha256(const void *p, size_t n, uint8_t out[32])
{
    moy_sha256_t h;
    moy_sha256_init(&h);
    moy_sha256_update(&h, p, n);
    moy_sha256_final(&h, out);
}
uint32_t moy_net_ms(void) { return 0; }
int moy_conn_alive(void *conn) { (void)conn; return 0; }
void moy_net_reap_after(uint32_t ms) { (void)ms; }
void invokeNative(void) { abort(); }
