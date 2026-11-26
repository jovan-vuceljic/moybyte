// moy_tty_live: the web terminal on the live socket, its 't' channel
// (native/moy_net/moy_live.c's header is the wire; README.md, The web
// terminal). A board that builds the live socket (the Zeros) serves its page's
// terminal here, on the socket's own task and buffers, and does not serve
// GET /term (moy_tty_ws.c, the consoles'): one socket, one session.
//
// The page opens the face ('O' with its size) when its Terminal asks, sends
// keys ('k') and sizes ('s'), and closes it ('C') when the Terminal lets go.
// The board says it opened ('A') or why not ('B': 0 another transport's face
// runs, 1 no memory), sends the face's bytes ('D', what the pair holds when
// the first arrives, as moy_tty_ws.c gathers them) and its end ('X' and the
// shell's exit status). The socket's end (a close, a takeover, its session's
// end, an idle page) ends the face with it.

#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#ifdef ESP_PLATFORM
#include "lwip/sockets.h"
#endif

#include "moy_tty.h"
#include "moy_tty_int.h"

extern const moy_tty_shell_t moy_tty_moy_sh;

// The live socket's (native/moy_net/moy_live.h), reached weakly: an image
// without the live socket links none of this channel's callers.
uint8_t *moy_live_out(size_t *cap);
int moy_live_say(size_t n);
int moy_live_behind_door(void);
#pragma weak moy_live_out
#pragma weak moy_live_say
#pragma weak moy_live_behind_door
// ...and the secure door's (native/moy_net/moy_tls_srv.c), where the image
// takes one: a face behind it opens only while the heap has room for it.
int moy_tls_low(void);
#pragma weak moy_tls_low

static struct {
    int sfd;                            // the face's end, or -1
    pid_t pid;
    int held;                           // the face task held for the live socket
    moy_tty_ws_stats_t stats;
} T = {.sfd = -1};

static uint16_t u16(const uint8_t *p) {
    return (uint16_t)(p[0] | p[1] << 8);
}

static int say(char kind, const void *p, size_t n) {
    size_t cap;
    uint8_t *o = moy_live_out(&cap);
    if (n + 2 > cap) {
        n = cap - 2;
    }
    o[0] = 't';
    o[1] = (uint8_t)kind;
    if (n) {
        memmove(o + 2, p, n);
    }
    T.stats.frames_out++;
    return moy_live_say(2 + n);
}

// On the console's task, as the webhost hands the socket over: the face's
// state and which task its hops wait for (moy_tty_setup). The face task is
// held at the first open, on the bridge's.
int moy_live_term_take(void) {
    if (moy_tty_setup() != 0) {
        return MOY_TTY_ENOMEM;
    }
    if (moy_tty_state()->shell == NULL) {
        moy_tty_set_shell(&moy_tty_moy_sh);
    }
    return 0;
}

static void face_end(void) {
    if (T.sfd < 0) {
        return;
    }
    close(T.sfd);
    T.sfd = -1;
    moy_tty_reap_all(MOY_TTY_WEB, 5000);
    T.stats.live = 0;
}

// 'B' why: 0 another transport holds the face, 1 none could start, 2 the
// heap is too short for one behind the secure door (moy_net.h,
// MOY_TLS_TERM_FREE).
static int face_open(int cols, int rows) {
    face_end();
    if (moy_tls_low != NULL && moy_live_behind_door != NULL && moy_live_behind_door()
        && moy_tls_low()) {
        T.stats.refused++;
        uint8_t why = 2;
        return say('B', &why, 1);
    }
    if (!T.held) {
        if (moy_tty_hold(MOY_TTY_WEB, 1) != 0) {
            uint8_t why = 1;
            return say('B', &why, 1);
        }
        T.held = 1;
    }
    int sfd;
    pid_t pid;
    int r = moy_tty_open(MOY_TTY_WEB, NULL, 1, cols, rows, NULL, &sfd, &pid);
    if (r != 0) {
        T.stats.refused++;
        uint8_t why = r == MOY_TTY_EBUSY ? 0 : 1;
        return say('B', &why, 1);
    }
    T.sfd = sfd;
    T.pid = pid;
    T.stats.sessions++;
    T.stats.live = 1;
    return say('A', NULL, 0);
}

int moy_live_term_message(const uint8_t *p, size_t n) {
    if (n < 2 || moy_live_out == NULL) {
        return 0;
    }
    switch (p[1]) {
        case 'O':
            return n >= 6 ? face_open(u16(p + 2), u16(p + 4)) : 0;
        case 'C':
            face_end();
            return 0;
        case 's':
            if (n >= 6 && T.sfd >= 0 && u16(p + 2) > 0 && u16(p + 4) > 0 && u16(p + 2) < 1000
                && u16(p + 4) < 1000) {
                moy_tty_winch(T.pid, u16(p + 2), u16(p + 4));
            }
            return 0;
        case 'k':
            if (T.sfd >= 0 && n > 2) {
                T.stats.in_bytes += (uint32_t)(n - 2);
                size_t at = 2;
                while (at < n) {
                    ssize_t m = send(T.sfd, p + at, n - at, 0);
                    if (m <= 0) {
                        break;
                    }
                    at += (size_t)m;
                }
            }
            return 0;
        default:
            return 0;
    }
}

int moy_live_term_fd(void) {
    return T.sfd;
}

int moy_live_term_pump(void) {
    if (T.sfd < 0) {
        return 0;
    }
    size_t cap;
    uint8_t *o = moy_live_out(&cap);
    uint8_t *d = o + 2;
    size_t room = cap - 2, n = 0;
    ssize_t m = recv(T.sfd, d, room, 0);
    if (m <= 0) {
        pid_t p;
        int status = 0;
        for (int t = 0; t < 500 && !moy_tty_reap(MOY_TTY_WEB, &p, &status); t += 10) {
            moy_tty_nap(10);
        }
        close(T.sfd);
        T.sfd = -1;
        T.stats.live = 0;
        uint8_t s[4] = {(uint8_t)status, (uint8_t)(status >> 8), (uint8_t)(status >> 16),
                        (uint8_t)(status >> 24)};
        return say('X', s, 4);
    }
    n = (size_t)m;
    while (n < room) {
        m = recv(T.sfd, d + n, room - n, MSG_DONTWAIT);
        if (m <= 0) {
            break;
        }
        n += (size_t)m;
    }
    T.stats.out_bytes += (uint32_t)n;
    o[0] = 't';
    o[1] = 'D';
    T.stats.frames_out++;
    return moy_live_say(2 + n);
}

void moy_live_term_end(void) {
    face_end();
    if (T.held) {
        moy_tty_hold(MOY_TTY_WEB, 0);
        T.held = 0;
    }
}

void moy_tty_live_stats(moy_tty_ws_stats_t *out) {
    *out = T.stats;
}
