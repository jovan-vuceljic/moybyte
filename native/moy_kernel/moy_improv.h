// moy_improv: Improv Wi-Fi's serial frames (improv-wifi.com/serial) off the
// console's receive path, and the frames a board answers with.
//
// THE FRAME: "IMPROV", the version (1), the type, the data's length, the
// data and a checksum, the low byte of the sum of every byte before it. A
// client ends each frame with '\n', and so does moy_improv_frame.
//
// THE RECEIVE PATH (docs/web_console_online_2026-11.md §7). The board's
// USB-Serial/JTAG console hands every byte it reads to moy_improv_feed before
// the REPL sees it (tools/patch_usj_improv.py, where a board defines
// MOY_IMPROV; modmoy_improv.c is its glue and its module). Bytes that match
// the header so far are HELD, and given back in order the moment one does
// not, or once nothing followed them for MOY_IMPROV_HOLD_MS (moy_improv_tick),
// so a person typing at the REPL loses nothing. From the version on the bytes
// are a frame's and none reaches the REPL: an RPC's type is 0x03, which the
// REPL reads as Ctrl-C. A frame whose checksum does not add up is handed on
// as MOY_IMPROV_BAD; one cut short is dropped after MOY_IMPROV_FRAME_MS of
// quiet. The '\n' right after a frame is the frame's.
//
// No allocation, no clock of its own (the caller's `now`, ms), and no lock:
// the glue holds its own around every call. The host builds this file alone
// (tests/test_improv.py).

#ifndef MOY_IMPROV_H
#define MOY_IMPROV_H

#include <stddef.h>
#include <stdint.h>

#define MOY_IMPROV_VERSION 1
#define MOY_IMPROV_DATA_MAX 255
#define MOY_IMPROV_HOLD 8               // bytes a feed may give back beyond its input
#define MOY_IMPROV_FRAME_MAX (MOY_IMPROV_DATA_MAX + 11)
#define MOY_IMPROV_HOLD_MS 30
#define MOY_IMPROV_FRAME_MS 1000

enum {
    MOY_IMPROV_BAD = -1,                // a frame whose checksum does not add up
    MOY_IMPROV_STATE = 0x01,            // board -> client: the current state
    MOY_IMPROV_ERROR = 0x02,            // board -> client: the error state
    MOY_IMPROV_RPC = 0x03,              // client -> board: a command
    MOY_IMPROV_RESULT = 0x04,           // board -> client: a command's result
};

typedef struct {
    uint8_t at;                         // bytes of the frame so far (0: none)
    uint8_t type, len, sum, nl;         // nl: the next byte may be the frame's '\n'
    uint32_t last;                      // when the last byte came
    uint8_t data[MOY_IMPROV_DATA_MAX];
} moy_improv_rx_t;

// A whole frame: its type (or MOY_IMPROV_BAD) and its data.
typedef void (*moy_improv_frame_fn)(void *ctx, int type, const uint8_t *data, size_t n);

// `n` bytes read at `now`: what is not a frame's goes to `out` (room for n +
// MOY_IMPROV_HOLD), its count returned; each frame that ends is handed to `fn`.
size_t moy_improv_feed(moy_improv_rx_t *p, const uint8_t *in, size_t n, uint32_t now,
                       uint8_t *out, moy_improv_frame_fn fn, void *ctx);
// The held header bytes into `out` (room for MOY_IMPROV_HOLD) once they are
// MOY_IMPROV_HOLD_MS old, and a frame MOY_IMPROV_FRAME_MS quiet dropped:
// the count given back.
size_t moy_improv_tick(moy_improv_rx_t *p, uint32_t now, uint8_t *out);
// Whether a header is held or a frame is under way (a tick has work).
int moy_improv_busy(const moy_improv_rx_t *p);
// A frame of `type` around `n` bytes of data into `out` (room for n + 11),
// '\n' included: its length, or 0 when n is over MOY_IMPROV_DATA_MAX.
size_t moy_improv_frame(int type, const uint8_t *data, size_t n, uint8_t *out);

#endif
