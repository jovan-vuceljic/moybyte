// The radio link's page half (moy_link.h) in the browser console: the page
// a Zero serves has its board's radio, over the live socket's link channel
// (moy_live.c's header is the wire). The page runs the cart and the match
// (native/moy_play/moy_match.c over this link, the kernel's instance as on a
// console); the board moves the frames between the socket and the air.
//
// The worker owns the socket and moves the bytes between frames, never
// inside one: moy_link_web_take hands it what this link queued (plaintexts,
// each behind its length), moy_link_web_give one plaintext the board sent,
// and moy_link_web_open whether the socket is open. Nothing here waits on
// the socket: a send while it is closed is refused, a match then waits on
// the peer's input as it does for a lost frame, and a socket that comes back
// with the radio held says 'U' again, its rate and its peers with it.
//
// The page's address on the air is its board's (the 'H' state; the /live
// probe tells the page's Python before the socket opens), and its
// channel the board's, always pinned: a Zero serves its page on its
// station's channel, so the link never tunes.

#if defined(MOY_NET_LIVE_PAGE) && MOY_NET_LIVE_PAGE

#include <string.h>

#include "moy_link.h"

#define OUT_CAP 8192                    // the plaintexts queued between two takes
#define MSG_MAX 1400                    // one 'S' plaintext, at most: a frame's on the socket
#define RING 16384
#define PEERS 8

static struct {
    int open, want, state, up, err, ch, rate, npeers;
    uint32_t max;
    uint8_t mac[6];
    uint8_t peers[PEERS][6];
    uint8_t out[OUT_CAP];
    size_t out_n;
    size_t s_at;                        // the open 'S' plaintext's length field, or OUT_CAP
    moy_link_ring_t ring;
    uint8_t buf[RING];
    moy_link_web_info_t info;
} P = {.rate = -1, .s_at = OUT_CAP};

// The device channel's half (moy_dev_web.c): weak, for a page built with the
// link alone (tests/test_live_link.py's).
#pragma weak moy_dev_web_give
#pragma weak moy_dev_web_socket
// ...and the apps' messages' (moy_svc_web.c), likewise.
#pragma weak moy_svc_web_give
#pragma weak moy_svc_web_socket
#pragma weak moy_svc_web_pump

// A plaintext of `n` bytes on the queue: where its bytes go, or NULL when
// the queue is full (its sends counted refused by the caller).
static uint8_t *queue(size_t n) {
    P.s_at = OUT_CAP;
    if (P.out_n + 2 + n > OUT_CAP) {
        return NULL;
    }
    uint8_t *p = P.out + P.out_n;
    p[0] = (uint8_t)n;
    p[1] = (uint8_t)(n >> 8);
    P.out_n += 2 + n;
    return p + 2;
}

static void say(char kind, const uint8_t *body, size_t n) {
    uint8_t *p = queue(2 + n);
    if (p != NULL) {
        p[0] = 'n';
        p[1] = (uint8_t)kind;
        if (n) {
            memcpy(p + 2, body, n);
        }
    }
}

// The radio's holds said again, on a socket that (re)opened.
static void again(void) {
    if (!P.want) {
        return;
    }
    say('U', NULL, 0);
    if (P.rate >= 0) {
        uint8_t r = (uint8_t)P.rate;
        say('R', &r, 1);
    }
    for (int i = 0; i < P.npeers; i++) {
        say('P', P.peers[i], 6);
    }
}

// A hold taken before the socket opened is said when it does: the page's
// cart can start (at boot, from its address) before the board answered.
int moy_link_start(uint32_t rxbuf) {
    (void)rxbuf;
    if (P.ring.buf == NULL) {
        moy_link_ring_init(&P.ring, P.buf, RING);
    }
    if (!P.want) {
        P.want = 1;
        P.npeers = 0;
        if (P.open) {
            say('U', NULL, 0);
        }
    }
    return 0;
}

void moy_link_stop(void) {
    if (P.want) {
        P.want = 0;
        P.npeers = 0;
        P.rate = -1;
        say('D', NULL, 0);
    }
    P.ring.head = P.ring.used = 0;
}

int moy_link_rate(int rate) {
    P.rate = rate;
    if (P.want) {
        uint8_t r = (uint8_t)rate;
        say('R', &r, 1);
    }
    return 0;
}

int moy_link_channel(int set) {
    (void)set;
    if (!P.state) {
        return 0;
    }
    return P.ch > 0 ? -P.ch : P.ch;
}

int moy_link_add_peer(const uint8_t mac[6]) {
    for (int i = 0; i < P.npeers; i++) {
        if (memcmp(P.peers[i], mac, 6) == 0) {
            return 0;
        }
    }
    if (P.npeers < PEERS) {
        memcpy(P.peers[P.npeers++], mac, 6);
    }
    if (P.want) {
        say('P', mac, 6);
    }
    return 0;
}

void moy_link_mac(uint8_t mac[6]) {
    memcpy(mac, P.mac, 6);
}

uint32_t moy_link_frame_max(void) {
    return P.state && P.max ? P.max : 250u;
}

int moy_link_send(const uint8_t mac[6], const uint8_t *data, size_t len) {
    if (!P.open || !P.want || len > MOY_LINK_MAX) {
        P.info.refused++;
        return MOY_LINK_WEB_DOWN;
    }
    size_t rec = 8 + len;
    uint8_t *p;
    if (P.s_at < OUT_CAP) {
        uint8_t *h = P.out + P.s_at;
        size_t n = (size_t)h[0] | (size_t)h[1] << 8;
        if (n + rec <= MSG_MAX && P.out_n + rec <= OUT_CAP) {
            h[0] = (uint8_t)(n + rec);
            h[1] = (uint8_t)((n + rec) >> 8);
            p = P.out + P.out_n;
            P.out_n += rec;
            goto fill;
        }
    }
    p = queue(2 + rec);
    if (p == NULL) {
        P.info.refused++;
        return MOY_LINK_WEB_DOWN;
    }
    P.s_at = (size_t)(p - P.out) - 2;
    *p++ = 'n';
    *p++ = 'S';
fill:
    p[0] = (uint8_t)len;
    p[1] = (uint8_t)(len >> 8);
    memcpy(p + 2, mac, 6);
    memcpy(p + 8, data, len);
    P.info.sent++;
    return 0;
}

int moy_link_recv(uint8_t mac[6], uint8_t *data, uint32_t cap) {
    if (P.ring.buf == NULL) {
        return -1;
    }
    return moy_link_ring_get(&P.ring, mac, data, cap);
}

void moy_link_stats(moy_link_stats_t *s) {
    memset(s, 0, sizeof *s);
    s->rx = P.ring.rx;
    s->drops = P.ring.drops;
    s->peak = P.ring.peak;
    s->cap = P.ring.cap;
    s->used = P.ring.used;
    s->up = P.want;
}

size_t moy_link_web_take(uint8_t *out, size_t cap) {
    if (P.open && moy_svc_web_pump != NULL) {
        moy_svc_web_pump();
    }
    size_t n = P.out_n < cap ? P.out_n : 0;
    if (n) {
        memcpy(out, P.out, n);
        P.out_n = 0;
        P.s_at = OUT_CAP;
    }
    return n;
}

uint8_t *moy_link_web_queue(size_t n) {
    return queue(n);
}

void moy_link_web_give(const uint8_t *p, size_t n) {
    if (n >= 2 && p[0] == 'd' && moy_dev_web_give != NULL) {
        moy_dev_web_give(p, n);
        return;
    }
    if (n >= 2 && p[0] == 'm' && moy_svc_web_give != NULL) {
        moy_svc_web_give(p, n);
        return;
    }
    if (n < 2 || p[0] != 'n') {
        return;
    }
    if (p[1] == 'H' && n >= 14) {
        P.state = 1;
        P.up = p[2];
        P.err = (int16_t)(p[3] | p[4] << 8);
        memcpy(P.mac, p + 5, 6);
        P.ch = (int8_t)p[11];
        P.max = (uint32_t)p[12] | (uint32_t)p[13] << 8;
        P.info.states++;
        return;
    }
    if (p[1] != 'F' || P.ring.buf == NULL) {
        return;
    }
    size_t at = 2;
    while (n - at >= 8) {
        size_t len = (size_t)p[at] | (size_t)p[at + 1] << 8;
        if (n - at - 8 < len) {
            return;
        }
        if (P.want) {
            moy_link_ring_put(&P.ring, p + at + 2, p + at + 8, (uint32_t)len);
        }
        at += 8 + len;
    }
}

void moy_link_web_open(int on) {
    if (on && !P.open) {
        P.open = 1;
        P.info.opens++;
        P.out_n = 0;
        P.s_at = OUT_CAP;
        again();
        if (moy_dev_web_socket != NULL) {
            moy_dev_web_socket(1);
        }
        if (moy_svc_web_socket != NULL) {
            moy_svc_web_socket(1);
        }
    } else if (!on && P.open) {
        P.open = 0;
        P.up = 0;
        P.out_n = 0;
        P.s_at = OUT_CAP;
        if (moy_dev_web_socket != NULL) {
            moy_dev_web_socket(0);
        }
        if (moy_svc_web_socket != NULL) {
            moy_svc_web_socket(0);
        }
    }
}

void moy_link_web_info(moy_link_web_info_t *out) {
    *out = P.info;
    out->open = (uint8_t)P.open;
    out->held = (uint8_t)P.want;
    out->board_up = (uint8_t)P.up;
    out->state = (uint8_t)P.state;
    out->err = P.err;
    out->ch = P.ch;
    memcpy(out->mac, P.mac, 6);
    out->rx = P.ring.rx;
    out->drops = P.ring.drops;
}

#endif
