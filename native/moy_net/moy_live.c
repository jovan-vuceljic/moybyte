// moy_live: the live socket's bridge (moy_live.h).
//
// A FRAME is one binary WebSocket message, sealed as the web terminal's are
// (moy_seal.h: (3, i, seq) up under the session's kc, (4, i, seq) down under
// kb, i counting each way from 0 and seq the upgrade's own), so a frame
// dropped, replayed or moved ends the socket 1008 "seal". The open host (no
// sign-in: a test, the dev server) carries the same plaintexts unsealed. A
// plaintext's first byte is its CHANNEL and the rest the channel's message:
//
//   'c'  the socket's own. 'b' a beat, either way, once a MOY_LIVE_BEAT_MS
//        that carried nothing else; 'e' + bytes up, answered at once with
//        'E' + the same bytes (the page's round trip to its board).
//   'n'  the radio link, where the board relays its radio
//        (moy_web_live_link; below).
//   'd'  the device channel: the handles of the kinds this board relays
//        (THE DEVICE CHANNEL, below; moy_live_dev.c serves it).
//   Any other byte is a channel this board does not serve, and its frame is
//   dropped: a page newer than its board loses that channel and nothing else.
//
// THE RADIO LINK. The board runs no game. The page runs the cart and the
// match (native/moy_play/moy_match.c over the page's own link,
// moy_link_web.c), and the board moves ESP-NOW frames between the socket and
// the air unchanged, so a browser on a Zero plays a console with the match
// protocol two consoles play (docs/netplay_v1.md). Up from the page:
//
//   'U'                       the radio up: ESP-NOW over the station
//                             (moy_link_start, a ring of MOY_LIVE_RING)
//   'D'                       the radio down
//   'P' mac(6)                a peer added (ESP-NOW sends a unicast only to one)
//   'R' rate(1)               the PHY rate the frames leave at (wifi_phy_rate_t)
//   'S' {len(2) mac(6) data}  frames to the air, in order (len little-endian)
//
// and down to it:
//
//   'H' up(1) err(2) mac(6) ch(1) max(2)   the radio's state, at the socket's
//                             start and after every 'U' and 'D': whether it is
//                             up, the start's error (0 none), the board's MAC
//                             (the page's address on the air), its channel as
//                             a signed byte, always negative (a Zero serves on
//                             its station's channel and never tunes) and the
//                             longest frame its radio carries
//   'F' {len(2) mac(6) data}  frames heard, oldest first
//
// THE DEVICE CHANNEL. A page's handle of a kind its board relays
// (native/moy_kernel/moy_dev_kinds.h's THE RELAY; the probe's "kinds") is a
// remote row on the page (moy_dev_web.c), its calls in order on this
// channel, each naming the page's row `id`. Up from the page:
//
//   'O' id kn(1) kind cfg     open (moy_dev_open's name and cfg)
//   'C' id                    close
//   'W' id data               write
//   'S' id cfg                set
//
// and down to it:
//
//   'A' id verb(1) rc(4)      the answer to an 'O', a 'W' or an 'S' (rc as
//                             moy_dev answers, little-endian); an answer to
//                             a row open is followed by its 'G'
//   'R' id vals(4 each) data  a record the row's read gave, with the kind's
//                             packet gets read after it
//   'G' id vals(4 each)       the kind's state gets
//   'E' nn(1) name args       an event the drivers posted the session's
//                             process (its arguments a JSON array), after
//                             the records it announces and each row's 'G'
//
// Reads, gets and xfers never cross: the page answers a read from the
// records, a get from the last record read or the last 'G', and an xfer BAD.
//
// Nothing waits on the radio or the page: the bridge's task (one a page's
// socket, made with its buffers when the webhost hands the socket over and
// gone with them at its end) wakes on the socket and every MOY_LIVE_WAIT_MS
// while the radio is up, takes what the
// ring holds and sends it. A page that sends nothing for MOY_LIVE_IDLE_MS
// (its beats included) is gone: the socket closes 1001 "idle". Its
// session's end closes it 1008 "revoked", and another session's page asking
// for the socket 4001 "taken" (moy_wa_take: the newer page has it). The radio
// goes down with the socket, so a page that comes back says 'U' again; a
// match on it waits meanwhile, as a missing input does.

#include "moy_link.h"
#include "moy_live.h"
#include "moy_dev_kinds.h"           // MOY_DEV_RELAYS

#if defined(MOY_NET_LIVE) && MOY_NET_LIVE && defined(MOY_NET_LINK) && MOY_NET_LINK

#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#ifdef ESP_PLATFORM
#include "lwip/sockets.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "moy_tasks.h"
#else
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <pthread.h>
#include <sys/select.h>
#endif

#include "moy_net.h"
#include "moy_seal.h"
#include "moy_webauth.h"
#include "moy_ws.h"

#ifndef MOY_LIVE_RING
#define MOY_LIVE_RING 8192              // the radio's receive ring, bytes (a board may say less)
#endif
#define MOY_LIVE_WAIT_MS 2              // the radio's ring is looked at this often while up
#define MOY_LIVE_REST_MS 100            // ...and the socket's beat with the radio down
#define MOY_LIVE_DEV_MS 10              // ...or with a device channel's row open
#define MOY_LIVE_BEAT_MS 1000
#define MOY_LIVE_IDLE_MS 5000
#define MOY_LIVE_SEND_MS 3000           // a page that takes nothing for this long is gone
#ifndef MOY_LIVE_IN
#define MOY_LIVE_IN 4096                // a page's frames waiting to be whole (one fits)
#endif
#define IN_CAP MOY_LIVE_IN
#define OUT_CAP 1536                    // one frame's plaintext down
#define OUT_ALLOC (MOY_WS_HEAD + OUT_CAP + MOY_SEAL_TAG)
#define BATCH 8                         // the ring's frames one pass takes, at most

// One page's buffers, made when its socket is taken and given back when it
// ends, as the task that serves it is: between pages the bridge holds only
// `live_t`, which on a board without PSRAM (the C3) is the whole point.
typedef struct {
    uint8_t in[IN_CAP];
    char out[OUT_ALLOC];
    uint8_t rx[MOY_LINK_MAX];
} bufs_t;

typedef struct {
    volatile int fd;                    // the socket served, or -1
    int ws;                             // ...as the bridge's task sends on it
    moy_wa_seal_t seal;
    uint32_t up_i, down_i;              // the next frame's index each way
    volatile int cut;                   // 1: the session ended, 2: another one took it
    volatile uint32_t heard;            // moy_net_ms of the page's last frame
    uint32_t said;                      // ...and of the board's
    int radio;                          // the radio up for the page
    bufs_t *b;
    moy_live_stats_t stats;
} live_t;

static live_t S = {.fd = -1};

// The device channel (moy_live_dev.c), on a board that can relay
// (moy_dev_kinds.h's MOY_DEV_RELAYS): named strongly there, which is what
// pulls it out of the component's archive; weak on any other, which links
// none of it.
#if defined(MOY_DEV_RELAYS) && MOY_DEV_RELAYS
#define DEV_HAS(f) 1
#else
#pragma weak moy_live_dev_message
#pragma weak moy_live_dev_pump
#pragma weak moy_live_dev_end
#pragma weak moy_live_dev_stats
#define DEV_HAS(f) ((f) != NULL)
#endif

static live_t *const L = &S;

int moy_web_live_link(uint8_t mac[6]) {
    moy_link_mac(mac);
    return 1;
}

// The plaintext at L->b->out + MOY_WS_HEAD, `n` bytes, sealed and sent: 0, or
// -1 when the socket failed.
static int say(int ws, size_t n) {
    uint8_t *d = (uint8_t *)L->b->out + MOY_WS_HEAD;
    if (L->seal.on) {
        if (moy_seal_ws(1, L->seal.kb, MOY_SEAL_DOWN, L->down_i++, L->seal.seq, d, n, d + n)
            != MOY_SEAL_OK) {
            return -1;
        }
        n += MOY_SEAL_TAG;
    }
    L->stats.down++;
    L->said = moy_net_ms();
    return moy_ws_out(ws, MOY_WS_BINARY, (const char *)d, n, L->b->out);
}

uint8_t *moy_live_out(size_t *cap) {
    *cap = OUT_CAP;
    return (uint8_t *)L->b->out + MOY_WS_HEAD;
}

int moy_live_say(size_t n) {
    return say(L->ws, n);
}

static int state(int ws, int err) {
    uint8_t *p = (uint8_t *)L->b->out + MOY_WS_HEAD;
    uint8_t mac[6] = {0};
    moy_link_mac(mac);
    int ch = moy_link_channel(0);
    ch = ch > 0 ? -ch : ch;
    uint32_t max = moy_link_frame_max();
    p[0] = 'n';
    p[1] = 'H';
    p[2] = (uint8_t)L->radio;
    p[3] = (uint8_t)err;
    p[4] = (uint8_t)((uint32_t)err >> 8);
    memcpy(p + 5, mac, 6);
    p[11] = (uint8_t)(int8_t)ch;
    p[12] = (uint8_t)max;
    p[13] = (uint8_t)(max >> 8);
    return say(ws, 14);
}

static int radio_up(void) {
    if (L->radio) {
        return 0;
    }
    int err = moy_link_start(MOY_LIVE_RING);
    if (err != 0) {
        return err;
    }
    static const uint8_t bcast[6] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
    moy_link_add_peer(bcast);
    L->radio = 1;
    L->stats.radio = 1;
    return 0;
}

static void radio_down(void) {
    if (!L->radio) {
        return;
    }
    moy_link_stop();
    L->radio = 0;
    L->stats.radio = 0;
}

// Records {len(2) mac(6) data} of p[0, n) to the air.
static void sends(const uint8_t *p, size_t n) {
    size_t at = 0;
    while (n - at >= 8) {
        size_t len = (size_t)p[at] | (size_t)p[at + 1] << 8;
        if (len > MOY_LINK_MAX || n - at - 8 < len) {
            return;
        }
        if (!L->radio || moy_link_send(p + at + 2, p + at + 8, len) != 0) {
            L->stats.refused++;
        } else {
            L->stats.air_out++;
        }
        at += 8 + len;
    }
}

// One plaintext from the page: -1 when the socket must end.
static int message(int ws, uint8_t *p, size_t n) {
    if (n < 2) {
        return 0;
    }
    if (p[0] == 'c') {
        if (p[1] == 'e' && n - 2 <= OUT_CAP - 2) {
            uint8_t *o = (uint8_t *)L->b->out + MOY_WS_HEAD;
            memmove(o + 2, p + 2, n - 2);
            o[0] = 'c';
            o[1] = 'E';
            L->stats.echoes++;
            return say(ws, n);
        }
        return 0;
    }
    if (p[0] == 'd') {
        return DEV_HAS(moy_live_dev_message) ? moy_live_dev_message(p, n) : 0;
    }
    if (p[0] != 'n') {
        return 0;
    }
    switch (p[1]) {
        case 'U':
            return state(ws, radio_up());
        case 'D':
            radio_down();
            return state(ws, 0);
        case 'P':
            if (n >= 8 && L->radio) {
                moy_link_add_peer(p + 2);
            }
            return 0;
        case 'R':
            if (n >= 3 && L->radio) {
                moy_link_rate(p[2]);
            }
            return 0;
        case 'S':
            sends(p + 2, n - 2);
            return 0;
        default:
            return 0;
    }
}

// Whole frames out of in[0..*n): -1 at a close, a bad seal or an error.
static int frames_in(int ws, size_t *n) {
    size_t at = 0;
    moy_ws_frame_t f;
    int k;
    while ((k = moy_ws_next(L->b->in, *n, &at, IN_CAP, &f)) > 0) {
        if (f.op == MOY_WS_CLOSE) {
            moy_ws_close(ws, 1000, "");
            return -1;
        }
        if (f.op == MOY_WS_PING) {
            moy_ws_out(ws, MOY_WS_PONG, (const char *)f.p, f.n < 125 ? f.n : 125, L->b->out);
            continue;
        }
        if (f.op != MOY_WS_BINARY) {
            continue;
        }
        size_t len = f.n;
        if (L->seal.on) {
            if (len < MOY_SEAL_TAG
                || moy_seal_ws(0, L->seal.kc, MOY_SEAL_UP, L->up_i++, L->seal.seq, f.p,
                               len - MOY_SEAL_TAG, f.p + len - MOY_SEAL_TAG) != MOY_SEAL_OK) {
                moy_ws_close(ws, 1008, "seal");
                return -1;
            }
            len -= MOY_SEAL_TAG;
        }
        L->stats.up++;
        if (message(ws, f.p, len) < 0) {
            return -1;
        }
    }
    if (k < 0) {
        moy_ws_close(ws, 1009, "big");
        return -1;
    }
    memmove(L->b->in, L->b->in + at, *n - at);
    *n -= at;
    return 0;
}

// What the radio heard since the last pass, to the page: -1 when the socket
// failed.
static int heard(int ws) {
    uint8_t *o = (uint8_t *)L->b->out + MOY_WS_HEAD;
    size_t n = 2;
    o[0] = 'n';
    o[1] = 'F';
    for (int i = 0; i < BATCH * 4; i++) {
        uint8_t mac[6];
        int len = moy_link_recv(mac, L->b->rx, sizeof L->b->rx);
        if (len < 0) {
            break;
        }
        L->stats.air_in++;
        if (n + 8 + (size_t)len > OUT_CAP) {
            if (say(ws, n) < 0) {
                return -1;
            }
            n = 2;
        }
        o[n] = (uint8_t)len;
        o[n + 1] = (uint8_t)((unsigned)len >> 8);
        memcpy(o + n + 2, mac, 6);
        memcpy(o + n + 8, L->b->rx, (size_t)len);
        n += 8 + (size_t)len;
    }
    return n > 2 ? say(ws, n) : 0;
}

static int beat(int ws) {
    uint8_t *o = (uint8_t *)L->b->out + MOY_WS_HEAD;
    o[0] = 'c';
    o[1] = 'b';
    return say(ws, 2);
}

// One page's socket, to its end.
static void pump(int ws) {
    size_t n = 0;
    int devs = 0;                       // the device channel's rows open
    if (state(ws, 0) < 0) {
        return;
    }
    for (;;) {
        if (L->cut) {
            moy_ws_close(ws, L->cut == 2 ? 4001 : 1008, L->cut == 2 ? "taken" : "revoked");
            return;
        }
        uint32_t now = moy_net_ms();
        if (now - L->heard > MOY_LIVE_IDLE_MS) {
            moy_ws_close(ws, 1001, "idle");
            return;
        }
        if (now - L->said >= MOY_LIVE_BEAT_MS && beat(ws) < 0) {
            return;
        }
        fd_set r;
        FD_ZERO(&r);
        FD_SET(ws, &r);
        uint32_t wait = L->radio ? MOY_LIVE_WAIT_MS : devs > 0 ? MOY_LIVE_DEV_MS
                        : MOY_LIVE_REST_MS;
        struct timeval tv = {0, (long)wait * 1000L};
        int k = select(ws + 1, &r, NULL, NULL, &tv);
        if (k < 0 && errno != EINTR) {
            return;
        }
        if (k > 0 && FD_ISSET(ws, &r)) {
            ssize_t m = recv(ws, L->b->in + n, IN_CAP - n, 0);
            if (m <= 0) {
                return;
            }
            L->heard = moy_net_ms();
            n += (size_t)m;
            if (frames_in(ws, &n) < 0) {
                return;
            }
        }
        if (L->radio && heard(ws) < 0) {
            return;
        }
        if (DEV_HAS(moy_live_dev_pump) && (devs = moy_live_dev_pump()) < 0) {
            return;
        }
    }
}

static void serve(int ws) {
    int one = 1;
    setsockopt(ws, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    struct timeval none = {0, 0};
    struct timeval snd = {MOY_LIVE_SEND_MS / 1000, (MOY_LIVE_SEND_MS % 1000) * 1000};
    setsockopt(ws, SOL_SOCKET, SO_RCVTIMEO, &none, sizeof none);
    setsockopt(ws, SOL_SOCKET, SO_SNDTIMEO, &snd, sizeof snd);
    pump(ws);
    radio_down();
    if (DEV_HAS(moy_live_dev_end)) {
        moy_live_dev_end();
    }
}

// The task of one page's socket, to its end.
static void bridge(void) {
    int ws = __atomic_load_n(&L->fd, __ATOMIC_ACQUIRE);
    L->ws = ws;
    L->stats.sessions++;
    L->stats.live = 1;
    serve(ws);
    shutdown(ws, SHUT_WR);
    close(ws);
    L->stats.live = 0;
    moy_net_free(L->b);
    L->b = NULL;
    moy_seal_wipe(&L->seal, sizeof L->seal);
    __atomic_store_n(&L->fd, -1, __ATOMIC_RELEASE);
}

#ifdef ESP_PLATFORM
static void bridge_task(void *arg) {
    (void)arg;
    bridge();
    vTaskDelete(NULL);
}
#else
static void *bridge_thread(void *arg) {
    (void)arg;
    bridge();
    return NULL;
}
#endif

int moy_web_live(int fd, const struct moy_wa_seal *seal) {
    if (__atomic_load_n(&L->fd, __ATOMIC_ACQUIRE) >= 0) {
        L->stats.busy++;
        return -1;
    }
    L->b = moy_net_alloc(sizeof *L->b);
    if (L->b == NULL) {
        return -1;
    }
    if (seal != NULL) {
        L->seal = *seal;
    } else {
        memset(&L->seal, 0, sizeof L->seal);
    }
    L->up_i = L->down_i = 0;
    L->cut = 0;
    L->heard = L->said = moy_net_ms();
    __atomic_store_n(&L->fd, fd, __ATOMIC_RELEASE);
#ifdef ESP_PLATFORM
    if (moy_task_spawn(MOY_TASK_LIVE, bridge_task, NULL, NULL)) {
        return 0;
    }
#else
    pthread_t t;
    if (pthread_create(&t, NULL, bridge_thread, NULL) == 0) {
        pthread_detach(t);
        return 0;
    }
#endif
    __atomic_store_n(&L->fd, -1, __ATOMIC_RELEASE);
    moy_net_free(L->b);
    L->b = NULL;
    return -1;
}

uint32_t moy_web_live_idle_ms(void) {
    if (__atomic_load_n(&L->fd, __ATOMIC_ACQUIRE) < 0) {
        return UINT32_MAX;
    }
    return moy_net_ms() - L->heard;
}

void moy_web_live_cut(int taken) {
    if (__atomic_load_n(&L->fd, __ATOMIC_ACQUIRE) >= 0) {
        L->cut = taken ? 2 : 1;
    }
}

void moy_live_stats(moy_live_stats_t *out) {
    *out = L->stats;
    if (DEV_HAS(moy_live_dev_stats)) {
        moy_live_dev_stats(out);
    }
}

#endif
