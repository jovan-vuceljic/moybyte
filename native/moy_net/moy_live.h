// moy_live: the live socket (#256), one sealed WebSocket from the page a
// board serves to that board, multiplexed by channel and served on a task of
// its own, so neither the page's frame nor the board's waits on it. Its first
// channel is the radio link: a Zero relays its ESP-NOW radio to the browser
// console it serves, which plays a match on it as a console does
// (docs/netplay_v1.md section 5). moy_live.c's header is the wire.
//
// The webhost answers GET /live's upgrade (moy_webhost.c, sealed as /term
// is) and hands the socket here. A board builds the bridge where its
// mpconfigboard.h says MOY_NET_LIVE (the Zeros); everywhere else /live is
// absent (404) and a page has no live socket.

#ifndef MOY_LIVE_H
#define MOY_LIVE_H

#include <stdint.h>

struct moy_wa_seal;

// The upgraded socket `fd` taken, under the session's `seal` (NULL on the
// open host): 0, else nonzero (another page's socket is live, or no memory).
int moy_web_live(int fd, const struct moy_wa_seal *seal);
// 1 where the board relays its radio on the link channel, with its address
// on the air (the page's, which its Python reads from the /live probe before
// the socket opens) into `mac`.
int moy_web_live_link(uint8_t mac[6]);
// The webhost's (moy_webauth.c): how long since the page last sent a frame
// (UINT32_MAX with none), and the socket's end: the page's session ended
// (1008 "revoked"), or `taken` by another session's page (4001 "taken").
uint32_t moy_web_live_idle_ms(void);
void moy_web_live_cut(int taken);

typedef struct {
    uint32_t sessions;                  // sockets taken
    uint32_t busy;                      // upgrades refused while one is live
    uint32_t up, down;                  // frames from the page, frames to it
    uint32_t air_out, air_in;           // radio frames sent for the page, heard for it
    uint32_t refused;                   // radio sends the radio refused
    uint32_t echoes;                    // 'e' round trips answered
    uint8_t live, radio;                // a socket is served; the radio is up for it
} moy_live_stats_t;

void moy_live_stats(moy_live_stats_t *out);

#endif // MOY_LIVE_H
