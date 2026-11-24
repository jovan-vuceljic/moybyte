// moy_ws: the frames of a WebSocket the webhost upgraded (moy_webhost.c's
// GET /term and GET /live), as the stream that serves one speaks them: the
// web terminal's bridge (native/moy_tty/moy_tty_ws.c) and the live socket
// (moy_live.c). RFC 6455's subset the page sends and takes: whole frames
// (no fragments), a payload under 64 KB, the page's masked and the board's
// not. What a frame carries, and its seal, is the stream's.

#ifndef MOY_WS_H
#define MOY_WS_H

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#ifdef ESP_PLATFORM
#include "lwip/sockets.h"
#endif

enum {
    MOY_WS_TEXT = 1,
    MOY_WS_BINARY = 2,
    MOY_WS_CLOSE = 8,
    MOY_WS_PING = 9,
    MOY_WS_PONG = 10,
};

// The most a frame's header takes ahead of its payload, a board's frame
// being unmasked: a caller that leaves this much room before its payload
// sends it without a move.
#define MOY_WS_HEAD 4

typedef struct {
    int op;
    uint8_t *p;                         // the payload, unmasked in place
    size_t n;
} moy_ws_frame_t;

// The next whole frame of in[*at, n), `*at` moved past it: 1 one, 0 when the
// next is not whole yet, -1 for one that would never fit `cap` bytes or that
// says a 64-bit length. moy_ws_send_all: all of p[0, n) on the socket, 0 or
// -1. moy_ws_out: one frame out, header and payload in one send, `buf`
// holding MOY_WS_HEAD + n bytes (the payload is moved to its place in `buf`
// unless it is there). moy_ws_close: a close frame with its code and reason
// (cut short past 56 bytes). Inline: the two streams live in two libraries
// (moy_net's, moy_tty's), and neither links the other.

static inline int moy_ws_next(uint8_t *in, size_t n, size_t *at, size_t cap, moy_ws_frame_t *f) {
    size_t a = *at;
    if (n - a < 2) {
        return 0;
    }
    uint8_t *h = in + a;
    size_t len = h[1] & 0x7F, hn = 2;
    if (len == 126) {
        if (n - a < 4) {
            return 0;
        }
        len = (size_t)h[2] << 8 | h[3];
        hn = 4;
    } else if (len == 127) {
        return -1;
    }
    int masked = h[1] & 0x80;
    if (masked) {
        hn += 4;
    }
    if (n - a < hn + len) {
        return hn + len > cap ? -1 : 0;
    }
    uint8_t *pl = h + hn;
    if (masked) {
        for (size_t i = 0; i < len; i++) {
            pl[i] ^= h[hn - 4 + (i & 3)];
        }
    }
    f->op = h[0] & 0x0F;
    f->p = pl;
    f->n = len;
    *at = a + hn + len;
    return 1;
}

static inline int moy_ws_send_all(int fd, const void *p, size_t n) {
    const char *c = p;
    while (n > 0) {
        ssize_t w = send(fd, c, n, 0);
        if (w < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        c += w;
        n -= (size_t)w;
    }
    return 0;
}

static inline int moy_ws_out(int fd, int op, const char *p, size_t n, char *buf) {
    size_t hn = 2;
    buf[0] = (char)(0x80 | op);
    if (n < 126) {
        buf[1] = (char)n;
    } else {
        buf[1] = 126;
        buf[2] = (char)(n >> 8);
        buf[3] = (char)n;
        hn = 4;
    }
    if (p != buf + hn) {
        memmove(buf + hn, p, n);
    }
    return moy_ws_send_all(fd, buf, hn + n);
}

static inline void moy_ws_close(int fd, int code, const char *why) {
    char b[64];
    size_t n = strlen(why);
    n = n < sizeof b - 8 ? n : sizeof b - 8;
    char p[64];
    p[0] = (char)(code >> 8);
    p[1] = (char)code;
    memcpy(p + 2, why, n);
    moy_ws_out(fd, MOY_WS_CLOSE, p, n + 2, b);
}


#endif // MOY_WS_H
