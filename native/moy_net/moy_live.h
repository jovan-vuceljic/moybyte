// moy_live: the live socket (#256), one sealed WebSocket from the page a
// board serves to that board, multiplexed by channel and served on a task of
// its own, so neither the page's frame nor the board's waits on it. Its
// channels are the radio link (a Zero relays its ESP-NOW radio to the
// browser console it serves, which plays a match on it as a console does,
// docs/netplay_v1.md section 5), the device channel (the board's device
// APIs a page's cart holds by handle, moy_live_dev.c, and its pins), the
// web terminal, the requests (the webhost's routes, asked and answered on
// the socket as over HTTP) and the apps' messages (a window on the page and
// its service on the board, moy_live_svc.c). moy_live.c's header is the wire.
//
// The webhost answers GET /live's upgrade (moy_webhost.c, sealed as /term
// is) and hands the socket here. A board builds the bridge where its
// mpconfigboard.h says MOY_NET_LIVE (the Zeros); everywhere else /live is
// absent (404) and a page has no live socket.

#ifndef MOY_LIVE_H
#define MOY_LIVE_H

#include <stddef.h>
#include <stdint.h>

struct moy_wa_seal;

// The upgraded socket `fd` taken, under the session's `seal` (NULL on the
// open host): 0, else nonzero (another page's socket is live, or no memory).
int moy_web_live(int fd, const struct moy_wa_seal *seal);
// 1 where the board relays its radio on the link channel, with its address
// on the air (the page's, which its Python reads from the /live probe before
// the socket opens) into `mac`.
int moy_web_live_link(uint8_t mac[6]);
// 1 where the socket carries the web terminal (its 't' channel), and the
// board serves no GET /term.
int moy_web_live_term(void);
// The terminal channel ('t'), native/moy_tty/moy_tty_live.c's: the socket
// handed over (on the console's task), a message from the page, the face's
// end to watch (-1: none), its bytes to the page, and the socket's end.
int moy_live_term_take(void);
int moy_live_term_message(const uint8_t *p, size_t n);
int moy_live_term_fd(void);
int moy_live_term_pump(void);
void moy_live_term_end(void);
// THE REQUESTS ('r', moy_live.c): the most plaintext one frame up carries
// (the probe's "req"); a request the page sent whole, taken by the webhost
// (moy_webhost.c, its poll), which frees it with moy_net_free, NULL with
// none: `len` bytes at `data`, "METHOD TARGET\n" and the body, sealed as
// over HTTP; and one plaintext of its answer down on the socket of session
// `gen` (`p` with MOY_WS_HEAD bytes free before it and MOY_SEAL_TAG after,
// sealed in place): 0, or -1 when that socket is gone.
typedef struct {
    uint32_t len, gen;
    uint16_t id;
    char data[];
} moy_live_req_t;
size_t moy_web_live_req(void);
moy_live_req_t *moy_live_req_take(void);
int moy_live_req_say(uint32_t gen, uint8_t *p, size_t n);
// THE HINTS (moy_live.c): `topics` (letters) told to the page at the
// bridge's next pass; and the webhost's word that the socket's own page's
// sync applies (`on` 1 before, 0 after), whose changes are no news to it.
void moy_live_hint(const char *topics);
void moy_live_store_mine(int on);
// The webhost's (moy_webauth.c): how long since the page last sent a frame
// (UINT32_MAX with none), and the socket's end: the page's session ended
// (1008 "revoked"), or `taken` by another session's page (4001 "taken").
uint32_t moy_web_live_idle_ms(void);
void moy_web_live_cut(int taken);

// THE DEVICE CHANNEL (moy_live_dev.c; moy_live.c's header is the wire): the
// bridge's hooks, each on its task. A 'd' plaintext from the page; a pass's
// pushes (the rows open, or -1 when the socket failed); the session's end.
int moy_live_dev_message(const uint8_t *p, size_t n);
int moy_live_dev_pump(void);
void moy_live_dev_end(void);
// ...and the bridge's, for them: where a plaintext down is written (`cap`
// bytes), and its send (0, or -1 when the socket failed).
uint8_t *moy_live_out(size_t *cap);
int moy_live_say(size_t n);
// The kinds this board relays to its page (moy_dev_relayed's text), for the
// /live probe's "kinds": its length.
size_t moy_web_live_kinds(char *out, size_t cap);

// THE APPS' MESSAGES ('m', moy_live_svc.c; moy_live.c's header is the wire):
// an app whose service runs on this board, served to a page's windows of it
// (`on`) or no longer (the service host's, on one task); and the bridge's
// hooks, each on its task: a session's start and end, an 'm' plaintext from
// the page, and a pass's pushes (the stand-ins open, or -1 when the socket
// failed). Its counts: messages up, down, and dropped (too long for a frame).
void moy_live_svc_serve(const char *app, int on);
void moy_live_svc_start(void);
void moy_live_svc_end(void);
int moy_live_svc_message(const uint8_t *p, size_t n);
int moy_live_svc_pump(void);
void moy_live_svc_stats(uint32_t *up, uint32_t *down, uint32_t *dropped);

typedef struct {
    uint32_t sessions;                  // sockets taken
    uint32_t busy;                      // upgrades refused while one is live
    uint32_t up, down;                  // frames from the page, frames to it
    uint32_t air_out, air_in;           // radio frames sent for the page, heard for it
    uint32_t refused;                   // radio sends the radio refused
    uint32_t echoes;                    // 'e' round trips answered
    uint8_t live, radio;                // a socket is served; the radio is up for it
    // the device channel: rows open now, calls served, writes a device took,
    // records and events pushed (moy_live_dev_stats)
    uint32_t devs, dev_calls, dev_writes, dev_pushes;
    uint32_t hints;                     // hint messages sent (THE HINTS, moy_live.c)
    uint32_t reqs;                      // requests the page sent whole (THE REQUESTS)
    uint32_t msgs_up, msgs_down;        // apps' messages each way (THE APPS' MESSAGES)
} moy_live_stats_t;

void moy_live_stats(moy_live_stats_t *out);
// The device channel's counts into its fields of *out (moy_live_dev.c).
void moy_live_dev_stats(moy_live_stats_t *out);

#endif // MOY_LIVE_H
