// moy_live: the live socket's bridge (moy_live.h).
//
// A FRAME is one binary WebSocket message, sealed as the web terminal's are
// (moy_seal.h: (3, i, seq) up under the session's kc, (4, i, seq) down under
// kb, i counting each way from 0 and seq the upgrade's own, or 0 on a socket
// that signed in on itself: THE SIGN-IN, below), so a frame dropped,
// replayed or moved ends the socket 1008 "seal". The open host (no sign-in:
// a test, the dev server) carries the same plaintexts unsealed. A
// plaintext's first byte is its CHANNEL and the rest the channel's message:
//
//   'c'  the socket's own. 'b' a beat, either way, once a MOY_LIVE_BEAT_MS
//        that carried nothing else; 'e' + bytes up, answered at once with
//        'E' + the same bytes (the page's round trip to its board); 'H' +
//        letters down, a HINT: what the page reads from the webhost's routes
//        changed on the board, so it asks now and asks no other way while
//        the socket is open (THE HINTS, below); 'S' up, the page's last
//        frame in the clear (THE SIGN-IN).
//   'n'  the radio link, where the board relays its radio
//        (moy_web_live_link; below).
//   'd'  the device channel: the handles of the kinds this board relays
//        (THE DEVICE CHANNEL, below; moy_live_dev.c serves it).
//   't'  the web terminal, a face of the board's shell
//        (native/moy_tty/moy_tty_live.c has its messages), where the image
//        has the face: this board then serves no GET /term.
//   'r'  the requests: the webhost's routes asked on the socket (THE
//        REQUESTS, below).
//   'm'  the apps' messages: an app's window on the page and its service
//        on the board (THE APPS' MESSAGES, below; moy_live_svc.c).
//   Any other byte is a channel this board does not serve, and its frame is
//   dropped: a page newer than its board loses that channel and nothing else.
//
// THE SIGN-IN. A page holding a session opens the socket naming it, sealed
// from the first frame. A page with none opens it naming none and signs in
// on it, in the clear, as the webhost's (moy_webhost.c, THE SIGN-IN ON THE
// LIVE SOCKET) until the bridge takes it: its 'r' requests to POST /auth,
// the sign-in's exchanges as moy_webhost.c's header has them (the backoff
// counting the socket's source), answered as any request is, and its
// echoes. Nothing else is served before the seal: another request is
// answered 401 {"error":"session"} and another channel's frame dropped. The
// answer to a credential that made a session (a key login, a pairing) is
// the last frame down in the clear; up, the page checks the board's proof
// and says
//
//   'c' 'S'                   the last frame in the clear
//
// and from the next frame each way both are sealed under that session with
// seq 0, which no sealed request takes, i from 0. The socket is then this
// bridge's, the radio's state its first frame down, and another session's
// page's socket is taken (moy_wa_take).
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
// THE PINS: the board's pins, where it serves them to its page (moy_gpio.c),
// are the kind "pins" (the probe's "kinds" names it, with no lists), one row
// a page, opened 'O' id 4 "pins" and answered 'A' as a kind's open. Its
// messages are its own, the ops moy_gpio_op's:
//
//   'W' id {pin(1) level(1)}  up: each pin driven as it arrives, in order;
//                             answered only where refused: 'A' id 'W' rc(4)
//                             pin(1), rc moy_dev's (BAD off the allowlist,
//                             BUSY held by another process, IO)
//   'S' id pins(1 each)       up: the pins the page watches, the last 'S'
//                             replaced (at most 16)
//   'G' id vals(4 each)       down: each watched pin's level (or its code),
//                             in the order 'S' named them, after an 'S' and
//                             whenever one changed: read after each message
//                             of the row and each pass of the bridge's
//
// THE REQUESTS. The page's requests to the webhost's sealed routes go on
// the socket, never over HTTP, where a board with the socket refuses them
// 410 {"error":"live"}. Each is sealed as a sealed route's request is (its
// session, sequence number and tag on the target, its body AES-GCM;
// moy_seal.h), so the webhost's sign-in check and routes take it as they
// would take one off a connection, and its answer is the same sealed
// records: the socket's own seal is around them, never instead of them. Up
// from the page, in pieces no longer than the probe's "req":
//
//   'Q' id(2) len(4) bytes    a request's first piece: `len` bytes in all,
//                             "METHOD TARGET\n" and its body
//   'B' id(2) bytes           its next pieces, in order
//
// and down to it, from the webhost's poll (moy_webhost.c), whose answer
// goes on the socket as it is written, never whole in either heap, each
// frame a full segment where the answer has the bytes:
//
//   'A' id(2) status(2) n(1) ctype(n) bytes   the answer's head (its
//                                     status, its type) and its body's
//                                     first bytes
//   'D' id(2) bytes                   its body's next, in order (a chunked
//                                     answer's chunks without their framing)
//   'Z' id(2) bytes                   its body's last, and its end
//   'W' id(2) status(2) n(1) ctype(n) bytes   a whole answer in one frame
//
// One request is asked at a time: the page sends the next once the last's
// 'Z' came. A request whose pieces do not add up, that is longer than
// MOY_HTTP_REQ_MAX, that finds one still waiting for the webhost or no
// memory is answered 'W' 503 at once. A request still waiting when
// the socket ends goes with it, and the answer to one the webhost took
// goes nowhere (moy_live_req_say: the socket of its session is gone).
//
// THE APPS' MESSAGES. Each end keeps a stand-in for the other end's
// processes of each app whose service runs on the board, a process of that
// app hearing every message sent to it (moy_evq.h's MOY_EVQ_ANY), and what
// it takes crosses here, where the other end's stand-in sends it again
// (moy_live_svc.c's header). Down to the page:
//
//   'H' budget ';' apps       the RAM the board gives its apps' services,
//                             "<KiB>,<KiB free>" ("-" where it sets none),
//                             and the apps whose services run on it, ','
//                             between: at the socket's start and at each
//                             change
//
// and either way:
//
//   'M' an(1) app nn(1) name args   message `name` sent to app `app`, its
//                             arguments a JSON array
//   'P' kn(1) key total(4) at(4) piece   a served app's prefs row `key`
//                             (`<app>_...`), `total` bytes of JSON text of
//                             which this piece starts at `at` (both little-
//                             endian; total 0xFFFFFFFF: the row deleted),
//                             moy_svc_prefs.c
//
// The services hear the page come and go (the OS message "page", [1] or
// [0]); a window hears the board's socket do so on the page
// (moy_svc_web.c: "board", [1] or [0, why]).
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

#include "moy_platform.h"
#include "moy_link.h"
#include "moy_live.h"
#include "moy_dev_kinds.h"           // MOY_DEV_RELAYS, MOY_DEV_PINS

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
    int ws;                             // ...as the bridge's task sends on it, -1 at its end
    uint32_t gen;                       // the session's, counting sockets taken
    moy_wa_seal_t seal;
    uint32_t up_i, down_i;              // the next frame's index each way
    volatile int cut;                   // 1: the session ended, 2: another one took it
    volatile uint32_t heard;            // moy_net_ms of the page's last frame
    uint32_t said;                      // ...and of the board's
    int radio;                          // the radio up for the page
    bufs_t *b;
    moy_live_req_t *rq;                 // the request being pieced together (the task's)
    uint32_t rq_want;                   // ...its length when whole
    size_t pre;                         // bytes the webhost read past the sign-in, in `in`
    moy_live_req_t *handed;             // ...and the one waiting for the webhost
    moy_live_stats_t stats;
} live_t;

static live_t S = {.fd = -1, .ws = -1};

// THE SEND LOCK: the bridge's task and the webhost's poll (a request's
// answer) both send on the socket, each frame sealed under the next index
// down, so the seal and the send are one step under it; lwIP takes a send
// on one task while another reads (LWIP_NETCONN_FULLDUPLEX). Its storage is
// static (moy_platform.h's mutex, made at its first take).
static moy_mutex_t s_lock = MOY_MUTEX_INIT;
static void lock(void) {
    moy_mutex_lock(&s_lock);
}
static void unlock(void) {
    moy_mutex_unlock(&s_lock);
}

// The device channel (moy_live_dev.c), on a board that can relay
// (moy_dev_kinds.h's MOY_DEV_RELAYS or MOY_DEV_PINS): named strongly there, which is what
// pulls it out of the component's archive; weak on any other, which links
// none of it.
#if (defined(MOY_DEV_RELAYS) && MOY_DEV_RELAYS) || (defined(MOY_DEV_PINS) && MOY_DEV_PINS)
#define DEV_HAS(f) 1
#else
#pragma weak moy_live_dev_message
#pragma weak moy_live_dev_pump
#pragma weak moy_live_dev_end
#pragma weak moy_live_dev_stats
#define DEV_HAS(f) ((f) != NULL)
#endif

// The terminal channel (moy_live.h; native/moy_tty/moy_tty_live.c): weak,
// for an image or a twin without the shell's face.
#pragma weak moy_live_term_take
#pragma weak moy_live_term_message
#pragma weak moy_live_term_fd
#pragma weak moy_live_term_pump
#pragma weak moy_live_term_end

// The apps' messages (moy_live_svc.c): weak, for an image without them.
#pragma weak moy_live_svc_start
#pragma weak moy_live_svc_end
#pragma weak moy_live_svc_message
#pragma weak moy_live_svc_pump
#pragma weak moy_live_svc_stats

static live_t *const L = &S;

int moy_web_live_link(uint8_t mac[6]) {
    moy_link_mac(mac);
    return 1;
}

// Whether the socket's send buffer has room for a whole frame, waiting for
// it as a send would: each segment lwIP sends holds a whole MSS of the heap
// until the page acks it (LWIP_NETIF_TX_SINGLE_PBUF), and a frame written
// into what one ack freed goes as several near-empty segments, so a frame
// is written only once select() says the socket is writable (lwIP's
// TCP_SNDLOWAT: more than two MSS free).
static int room(int ws) {
    fd_set w;
    FD_ZERO(&w);
    FD_SET(ws, &w);
    struct timeval tv = {MOY_LIVE_SEND_MS / 1000, (MOY_LIVE_SEND_MS % 1000) * 1000};
    return select(ws + 1, NULL, &w, NULL, &tv) > 0 ? 0 : -1;
}

// The plaintext at `d`, `n` bytes (MOY_WS_HEAD free before it, MOY_SEAL_TAG
// after), sealed and sent on `ws` under the send lock, which the caller
// holds: 0, or -1 when the socket failed.
static int send_locked(int ws, uint8_t *d, size_t n) {
    if (room(ws) < 0) {
        return -1;
    }
    if (L->seal.on) {
        if (moy_seal_ws(1, L->seal.kb, MOY_SEAL_DOWN, L->down_i++, L->seal.seq, d, n, d + n)
            != MOY_SEAL_OK) {
            return -1;
        }
        n += MOY_SEAL_TAG;
    }
    L->stats.down++;
    L->said = moy_net_ms();
    return moy_ws_out(ws, MOY_WS_BINARY, (const char *)d, n, (char *)d - MOY_WS_HEAD);
}

// The plaintext at L->b->out + MOY_WS_HEAD, `n` bytes, sealed and sent: 0, or
// -1 when the socket failed.
static int say(int ws, size_t n) {
    lock();
    int r = send_locked(ws, (uint8_t *)L->b->out + MOY_WS_HEAD, n);
    unlock();
    return r;
}

int moy_live_req_say(uint32_t gen, uint8_t *p, size_t n) {
    lock();
    int ws = L->ws;
    int r = ws >= 0 && L->gen == gen ? send_locked(ws, p, n) : -1;
    unlock();
    return r;
}

uint8_t *moy_live_out(size_t *cap) {
    *cap = OUT_CAP;
    return (uint8_t *)L->b->out + MOY_WS_HEAD;
}

int moy_live_say(size_t n) {
    return say(L->ws, n);
}

int moy_live_behind_door(void) {
    struct sockaddr_in a;
    socklen_t n = sizeof a;
    int ws = L->ws;
    return ws >= 0 && getpeername(ws, (struct sockaddr *)&a, &n) == 0 && a.sin_family == AF_INET
           && ((const uint8_t *)&a.sin_addr.s_addr)[0] == 127;
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

// THE REQUESTS (above): 'A' 503 and 'Z' for request `id`.
static int refuse(int ws, const uint8_t id[2]) {
    static const char ctype[] = "application/json";
    uint8_t *o = (uint8_t *)L->b->out + MOY_WS_HEAD;
    o[0] = 'r';
    o[1] = 'W';
    o[2] = id[0];
    o[3] = id[1];
    o[4] = 503 & 0xff;
    o[5] = 503 >> 8;
    o[6] = sizeof ctype - 1;
    memcpy(o + 7, ctype, sizeof ctype - 1);
    return say(ws, 7 + sizeof ctype - 1);
}

static void rq_drop(void) {
    moy_net_free(L->rq);
    L->rq = NULL;
}

// A request's piece: 'Q' or 'B', p[0, n) past the channel's byte.
static int request(int ws, const uint8_t *p, size_t n) {
    if (n < 3) {
        return 0;
    }
    const uint8_t *id = p + 1;
    uint16_t want = (uint16_t)(id[0] | id[1] << 8);
    if (p[0] == 'Q') {
        if (n < 7) {
            return 0;
        }
        uint32_t len = (uint32_t)p[3] | (uint32_t)p[4] << 8 | (uint32_t)p[5] << 16
                       | (uint32_t)p[6] << 24;
        rq_drop();
        if (len == 0 || len > MOY_HTTP_REQ_MAX
            || __atomic_load_n(&L->handed, __ATOMIC_ACQUIRE) != NULL
            || (L->rq = moy_net_alloc(sizeof *L->rq + len + 1u)) == NULL) {
            return refuse(ws, id);
        }
        L->rq->len = 0;
        L->rq->id = want;
        L->rq_want = len;
        p += 7;
        n -= 7;
    } else if (p[0] == 'B') {
        if (L->rq == NULL || L->rq->id != want) {
            return 0;
        }
        p += 3;
        n -= 3;
    } else {
        return 0;
    }
    moy_live_req_t *q = L->rq;
    if (n > L->rq_want - q->len) {
        rq_drop();
        return refuse(ws, id);
    }
    memcpy(q->data + q->len, p, n);
    q->len += (uint32_t)n;
    if (q->len < L->rq_want) {
        return 0;
    }
    q->data[q->len] = 0;
    q->gen = L->gen;
    L->rq = NULL;
    L->stats.reqs++;
    __atomic_store_n(&L->handed, q, __ATOMIC_RELEASE);
    return 0;
}

size_t moy_web_live_req(void) {
    return IN_CAP - 8u - MOY_SEAL_TAG;  // a page's frame head is 8 bytes, masked
}

moy_live_req_t *moy_live_req_take(void) {
    return __atomic_exchange_n(&L->handed, NULL, __ATOMIC_ACQ_REL);
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
    if (p[0] == 't') {
        return moy_live_term_message != NULL ? moy_live_term_message(p, n) : 0;
    }
    if (p[0] == 'r') {
        return request(ws, p + 1, n - 1);
    }
    if (p[0] == 'm') {
        return moy_live_svc_message != NULL ? moy_live_svc_message(p, n) : 0;
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

// THE HINTS. What the page reads from the webhost's routes (the store, a
// Zero's Wi-Fi, its update, its official carts) is asked, never pushed; the
// socket says when it changed, one letter a topic, so the page asks then
// instead of on a clock:
//
//   's'  the store: the volumes took a change (moy_vol_changes) the page did
//        not make itself, an SSH session's, a shell's, another page's sync
//   'w'  the board's Wi-Fi (/wifi), 'u' its update (/update), 'o' its
//        official carts (/official): their backends stepped (moy_live_hint,
//        device/moy_webhost.py)
//
// Hints a pass gathered go in one message at its end; a page asks at most
// once a topic for several. The page's own changes are no news to it: while
// the webhost applies a batch the socket's session sent, or the VM steps an
// official install or removal that page asked for (device/moy_webhost.py),
// the store's changes are counted as seen (moy_live_store_mine). Another
// page's install is hinted 's' as its sync is.
uint32_t moy_vol_changes(void);
#pragma weak moy_vol_changes

static uint32_t s_hints;                // the letters 'a'..'z' asked, a bit each
static int s_mine;                      // the page's own batch applying
static uint32_t s_seen;                 // the volumes' count the page knows of

void moy_live_hint(const char *topics) {
    uint32_t b = 0;
    for (; *topics; topics++) {
        if (*topics >= 'a' && *topics <= 'z') {
            b |= 1u << (*topics - 'a');
        }
    }
    __atomic_or_fetch(&s_hints, b, __ATOMIC_ACQ_REL);
}

void moy_live_store_mine(int on) {
    if (on) {
        __atomic_add_fetch(&s_mine, 1, __ATOMIC_ACQ_REL);
        return;
    }
    if (moy_vol_changes != NULL) {
        __atomic_store_n(&s_seen, moy_vol_changes(), __ATOMIC_RELEASE);
    }
    __atomic_sub_fetch(&s_mine, 1, __ATOMIC_ACQ_REL);
}

static void hints_start(void) {
    __atomic_store_n(&s_hints, 0, __ATOMIC_RELEASE);
    __atomic_store_n(&s_seen, moy_vol_changes != NULL ? moy_vol_changes() : 0, __ATOMIC_RELEASE);
}

static int hints(int ws) {
    uint32_t h = 0;
    if (moy_vol_changes != NULL && !__atomic_load_n(&s_mine, __ATOMIC_ACQUIRE)) {
        uint32_t c = moy_vol_changes();
        if (c != __atomic_load_n(&s_seen, __ATOMIC_ACQUIRE)) {
            __atomic_store_n(&s_seen, c, __ATOMIC_RELEASE);
            h |= 1u << ('s' - 'a');
        }
    }
    h |= __atomic_exchange_n(&s_hints, 0, __ATOMIC_ACQ_REL);
    if (!h) {
        return 0;
    }
    uint8_t *o = (uint8_t *)L->b->out + MOY_WS_HEAD;
    size_t n = 0;
    o[n++] = 'c';
    o[n++] = 'H';
    for (int i = 0; i < 26; i++) {
        if (h & (1u << i)) {
            o[n++] = (uint8_t)('a' + i);
        }
    }
    L->stats.hints++;
    return say(ws, n);
}

// One page's socket, to its end.
static void pump(int ws) {
    size_t n = L->pre;
    int devs = 0;                       // the device channel's rows open
    if (state(ws, 0) < 0) {
        return;
    }
    hints_start();
    if (moy_live_svc_start != NULL) {
        moy_live_svc_start();
    }
    if (n > 0 && frames_in(ws, &n) < 0) {
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
        int tfd = moy_live_term_fd != NULL ? moy_live_term_fd() : -1;
        if (tfd >= 0) {
            FD_SET(tfd, &r);
        }
        uint32_t wait = L->radio ? MOY_LIVE_WAIT_MS : devs > 0 ? MOY_LIVE_DEV_MS
                        : MOY_LIVE_REST_MS;
        struct timeval tv = {0, (long)wait * 1000L};
        int k = select((tfd > ws ? tfd : ws) + 1, &r, NULL, NULL, &tv);
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
        if (k > 0 && tfd >= 0 && FD_ISSET(tfd, &r) && moy_live_term_pump() < 0) {
            return;
        }
        if (L->radio && heard(ws) < 0) {
            return;
        }
        if (DEV_HAS(moy_live_dev_pump) && (devs = moy_live_dev_pump()) < 0) {
            return;
        }
        int apps = moy_live_svc_pump != NULL ? moy_live_svc_pump() : 0;
        if (apps < 0) {
            return;
        }
        devs += apps;
        if (hints(ws) < 0) {
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
    rq_drop();
    moy_net_free(moy_live_req_take());
    if (DEV_HAS(moy_live_dev_end)) {
        moy_live_dev_end();
    }
    if (moy_live_svc_end != NULL) {
        moy_live_svc_end();
    }
    if (moy_live_term_end != NULL) {
        moy_live_term_end();
    }
}

// The task of one page's socket, to its end.
static void bridge(void) {
    int ws = __atomic_load_n(&L->fd, __ATOMIC_ACQUIRE);
    L->ws = ws;
    L->stats.sessions++;
    L->stats.live = 1;
    serve(ws);
    lock();
    L->ws = -1;
    shutdown(ws, SHUT_WR);
    close(ws);
    unlock();
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

int moy_web_live(int fd, const struct moy_wa_seal *seal, const uint8_t *pre, size_t pn) {
    if (__atomic_load_n(&L->fd, __ATOMIC_ACQUIRE) >= 0) {
        L->stats.busy++;
        return -1;
    }
    if (pn > IN_CAP || (L->b = moy_net_alloc(sizeof *L->b)) == NULL) {
        return -1;
    }
    if (pn > 0) {
        memcpy(L->b->in, pre, pn);
    }
    L->pre = pn;
    if (seal != NULL) {
        L->seal = *seal;
    } else {
        memset(&L->seal, 0, sizeof L->seal);
    }
    L->up_i = L->down_i = 0;
    L->gen++;
    L->cut = 0;
    L->heard = L->said = moy_net_ms();
    if (moy_live_term_take != NULL) {
        moy_live_term_take();
    }
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

int moy_web_live_term(void) {
    return moy_live_term_message != NULL;
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
    if (moy_live_svc_stats != NULL) {
        uint32_t dropped;
        moy_live_svc_stats(&out->msgs_up, &out->msgs_down, &dropped);
    }
    if (DEV_HAS(moy_live_dev_stats)) {
        moy_live_dev_stats(out);
    }
}

#endif
