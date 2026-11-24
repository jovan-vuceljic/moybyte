// moy_improv: Improv Wi-Fi's serial frames. moy_improv.h is the authority.

#include "moy_improv.h"

#include <string.h>

static const uint8_t HEADER[6] = { 'I', 'M', 'P', 'R', 'O', 'V' };

// The header bytes held so far (p->at of them) into out.
static size_t give_back(moy_improv_rx_t *p, uint8_t *out) {
    size_t n = p->at < sizeof HEADER ? p->at : sizeof HEADER;
    memcpy(out, HEADER, n);
    p->at = 0;
    return n;
}

size_t moy_improv_feed(moy_improv_rx_t *p, const uint8_t *in, size_t n, uint32_t now,
                       uint8_t *out, moy_improv_frame_fn fn, void *ctx) {
    size_t o = 0;
    for (size_t i = 0; i < n; i++) {
        uint8_t b = in[i];
        if (p->nl) {
            p->nl = 0;
            if (b == '\n') {
                continue;
            }
        }
        p->last = now;
        if (p->at < sizeof HEADER) {
            if (b == HEADER[p->at]) {
                p->at++;
                continue;
            }
            if (p->at) {
                o += give_back(p, out + o);
                if (b == HEADER[0]) {
                    p->at = 1;
                    continue;
                }
            }
            out[o++] = b;
            continue;
        }
        if (p->at == sizeof HEADER) {           // the version
            if (b != MOY_IMPROV_VERSION) {
                o += give_back(p, out + o);
                if (b == HEADER[0]) {
                    p->at = 1;
                } else {
                    out[o++] = b;
                }
                continue;
            }
            p->sum = 0;
            for (size_t k = 0; k < sizeof HEADER; k++) {
                p->sum += HEADER[k];
            }
            p->sum += b;
            p->at++;
            continue;
        }
        if (p->at == sizeof HEADER + 1) {       // the type
            p->type = b;
            p->sum += b;
            p->at++;
            continue;
        }
        if (p->at == sizeof HEADER + 2) {       // the length
            p->len = b;
            p->sum += b;
            p->at++;
            continue;
        }
        size_t got = (size_t)p->at - (sizeof HEADER + 3);
        if (got < p->len) {
            p->data[got] = b;
            p->sum += b;
            p->at++;
            continue;
        }
        p->at = 0;                              // the checksum: the frame is whole
        p->nl = 1;
        if (fn != NULL) {
            fn(ctx, b == p->sum ? (int)p->type : MOY_IMPROV_BAD, p->data, p->len);
        }
    }
    return o;
}

size_t moy_improv_tick(moy_improv_rx_t *p, uint32_t now, uint8_t *out) {
    uint32_t quiet = now - p->last;
    if (p->at == 0) {
        return 0;
    }
    if (p->at <= sizeof HEADER) {
        return quiet >= MOY_IMPROV_HOLD_MS ? give_back(p, out) : 0;
    }
    if (quiet >= MOY_IMPROV_FRAME_MS) {
        p->at = 0;                              // cut short: none of it was the REPL's
    }
    return 0;
}

int moy_improv_busy(const moy_improv_rx_t *p) {
    return p->at != 0;
}

size_t moy_improv_frame(int type, const uint8_t *data, size_t n, uint8_t *out) {
    if (n > MOY_IMPROV_DATA_MAX) {
        return 0;
    }
    memcpy(out, HEADER, sizeof HEADER);
    size_t o = sizeof HEADER;
    out[o++] = MOY_IMPROV_VERSION;
    out[o++] = (uint8_t)type;
    out[o++] = (uint8_t)n;
    if (n) {
        memcpy(out + o, data, n);
    }
    o += n;
    uint8_t sum = 0;
    for (size_t k = 0; k < o; k++) {
        sum += out[k];
    }
    out[o++] = sum;
    out[o++] = '\n';
    return o;
}
