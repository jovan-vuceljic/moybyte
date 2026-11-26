// The secure door (moy_net.h, HTTPS ON DEMAND): TLS on MOY_TLS_PORT, opened
// by the page and closed again when nobody uses it.
//
// The door terminates TLS and nothing else. Each connection it accepts is
// shaken hands with, then, at its first request bytes, joined to a loopback
// connection to the webhost's own port, named to the webhost as the browser
// it carries (moy_web_via), and one task pumps bytes between the two. The
// webhost serves it as any other connection (its routes, its seals, the live
// socket and the terminal it hands on), so nothing above the socket knows
// the browser came over TLS. Only this task touches a TLS context; the
// webhost and the bridges write plain bytes to the loopback.
//
// What it holds lives only while it is open: the task and its stack, the
// pump's buffer, the certificate's and key's DER, the ticket keys and, per
// connection, the TLS context. The certificate and key are parsed per
// handshake and freed after it (the image's CONFIG_MBEDTLS_DYNAMIC_FREE_*
// frees a configuration's own certificate after the handshake, so each
// connection has its own configuration), and the record buffers are made per
// record (CONFIG_MBEDTLS_DYNAMIC_BUFFER). A browser's later connections
// resume by session ticket, which skips the handshake's curve work.
//
// THE CERTIFICATE is self-signed EC P-256, made the first time the door opens
// and kept in the system folder (MOY_TLS_CERT, MOY_TLS_KEY), so the browser's
// exception for it survives a reboot. It is made, read and written on the
// webhost's task, which owns the store; the door's task never touches a file.

#include "moy_platform.h"
#include "moy_net.h"

#if defined(MOY_ON_BOARD)
#include "moy_tasks.h"
#endif

#if defined(MOY_ON_BOARD) && defined(MOY_NET_HTTPS) && MOY_NET_HTTPS

#define MBEDTLS_ALLOW_PRIVATE_ACCESS
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include "mbedtls/ecp.h"
#include "mbedtls/net_sockets.h"
#include "mbedtls/oid.h"
#include "mbedtls/platform_util.h"
#include "mbedtls/pk.h"
#include "mbedtls/ssl.h"
#include "mbedtls/ssl_ticket.h"
#include "mbedtls/x509_crt.h"
#include "moy_seal.h"
#include "moy_vol.h"

#define PUMP 2048u                  // one record's worth each way (OUT_CONTENT_LEN)
#define DER_MAX 1024u
#define HS_MS 10000u                // a handshake's whole budget
#define WAIT_MS 250u
#define QUIET_MS 15000u             // a connection that never asks anything (a preconnect)
#define WRITE_TRIES 3

enum { DOWN = 0, STARTING = 1, UP = 2 };

typedef struct {
    int fd;                         // the browser's
    int up;                         // the loopback to the webhost, -1 until its first bytes
    uint32_t peer;                  // the browser's IPv4 address (network order)
    uint32_t at;                    // when it was shaken hands with
    uint8_t shook;
    mbedtls_ssl_context ssl;
    mbedtls_ssl_config conf;
    mbedtls_x509_crt crt;
    mbedtls_pk_context pk;
} conn_t;

typedef struct {
    int lfd;
    uint16_t back;                  // the webhost's port
    uint8_t conns;
    uint32_t idle_at;               // when the last connection closed
    unsigned char *buf;
    unsigned char der[2][DER_MAX];  // the certificate, the key
    size_t der_n[2];
    mbedtls_ssl_ticket_context tkt;
    conn_t *c[MOY_TLS_CONNS];       // made per connection, NULL when the slot is free
} door_t;

static door_t *D;
static int s_state;
static char s_system[MOY_WEB_PATH_MAX];

static int rng(void *ctx, unsigned char *out, size_t n) {
    (void)ctx;
    moy_seal_random(out, n);
    return 0;
}

// -- the certificate (the webhost's task) ---------------------------------------

static int file_read(const char *leaf, unsigned char *out, size_t cap, size_t *n) {
    char path[MOY_WEB_PATH_MAX + 16];
    snprintf(path, sizeof path, "%s%s", s_system, leaf);
    moy_vol_t v;
    const char *rest;
    moy_vol_file_t *f = NULL;
    int g = moy_vol_gate_enter(path);
    int rc = moy_vol_at(path, &v, &rest);
    if (rc == 0) {
        rc = moy_vol_open(&v, rest, MOY_VOL_READ, &f);
    }
    *n = 0;
    if (rc == 0) {
        size_t k = 1;
        while (rc == 0 && k > 0 && *n < cap) {
            rc = moy_vol_read(f, out + *n, cap - *n, &k);
            *n += rc == 0 ? k : 0;
        }
        moy_vol_close(f);
    }
    moy_vol_gate_leave(g);
    return rc == 0 && *n > 0 && *n < cap ? 0 : -1;
}

static int file_write(const char *leaf, const unsigned char *p, size_t n) {
    char path[MOY_WEB_PATH_MAX + 16], tmp[MOY_WEB_PATH_MAX + 20];
    snprintf(path, sizeof path, "%s%s", s_system, leaf);
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    moy_vol_t v;
    const char *rest, *trest;
    moy_vol_file_t *f = NULL;
    int g = moy_vol_gate_enter(path);
    int rc = moy_vol_at(path, &v, &rest);
    if (rc == 0) {
        rc = moy_vol_at(tmp, &v, &trest);
    }
    if (rc == 0) {
        rc = moy_vol_open(&v, trest, MOY_VOL_WRITE, &f);
    }
    if (rc == 0) {
        rc = moy_vol_write(f, p, n);
        int c = moy_vol_close(f);
        rc = rc ? rc : c;
    }
    if (rc == 0) {
        rc = moy_vol_replace(&v, trest, rest);
    }
    moy_vol_gate_leave(g);
    return rc;
}

// DER written at the END of `buf` by mbedtls: moved to its start.
static size_t der_front(unsigned char *buf, size_t cap, int n) {
    if (n <= 0) {
        return 0;
    }
    memmove(buf, buf + cap - (size_t)n, (size_t)n);
    return (size_t)n;
}

// A fresh key and its self-signed certificate into D->der.
static int make_cert(void) {
    mbedtls_pk_context key;
    mbedtls_x509write_cert w;
    mbedtls_pk_init(&key);
    mbedtls_x509write_crt_init(&w);
    unsigned char serial[16];
    rng(NULL, serial, sizeof serial);
    serial[0] &= 0x7f;
    char board[33], subject[64];
    moy_web_board_id(board);
    snprintf(subject, sizeof subject, "CN=Moybyte %.8s,O=Moybyte", board);
    int rc = mbedtls_pk_setup(&key, mbedtls_pk_info_from_type(MBEDTLS_PK_ECKEY));
    if (rc == 0) {
        rc = mbedtls_ecp_gen_key(MBEDTLS_ECP_DP_SECP256R1, mbedtls_pk_ec(key), rng, NULL);
    }
    if (rc == 0) {
        mbedtls_x509write_crt_set_version(&w, MBEDTLS_X509_CRT_VERSION_3);
        mbedtls_x509write_crt_set_md_alg(&w, MBEDTLS_MD_SHA256);
        mbedtls_x509write_crt_set_subject_key(&w, &key);
        mbedtls_x509write_crt_set_issuer_key(&w, &key);
        rc = mbedtls_x509write_crt_set_subject_name(&w, subject);
    }
    if (rc == 0) {
        rc = mbedtls_x509write_crt_set_issuer_name(&w, subject);
    }
    if (rc == 0) {
        rc = mbedtls_x509write_crt_set_serial_raw(&w, serial, sizeof serial);
    }
    if (rc == 0) {
        // Fixed dates, as the board's clock may read 2000 when this runs;
        // under the 825 days Apple's TLS rules allow a server certificate.
        rc = mbedtls_x509write_crt_set_validity(&w, "20261101000000", "20290131000000");
    }
    if (rc == 0) {
        rc = mbedtls_x509write_crt_set_basic_constraints(&w, 0, -1);
    }
    if (rc == 0) {
        rc = mbedtls_x509write_crt_set_key_usage(&w, MBEDTLS_X509_KU_DIGITAL_SIGNATURE);
    }
    if (rc == 0) {
        const char *eku = MBEDTLS_OID_SERVER_AUTH;
        mbedtls_asn1_sequence s = {
            .buf = {.tag = MBEDTLS_ASN1_OID, .len = MBEDTLS_OID_SIZE(MBEDTLS_OID_SERVER_AUTH),
                    .p = (unsigned char *)eku},
            .next = NULL,
        };
        rc = mbedtls_x509write_crt_set_ext_key_usage(&w, &s);
    }
    if (rc == 0) {
        int n = mbedtls_x509write_crt_der(&w, D->der[0], DER_MAX, rng, NULL);
        D->der_n[0] = der_front(D->der[0], DER_MAX, n);
        n = mbedtls_pk_write_key_der(&key, D->der[1], DER_MAX);
        D->der_n[1] = der_front(D->der[1], DER_MAX, n);
        rc = D->der_n[0] && D->der_n[1] ? 0 : -1;
    }
    mbedtls_x509write_crt_free(&w);
    mbedtls_pk_free(&key);
    return rc;
}

// The kept certificate, or a new one made and kept: 0, else nonzero.
static int cert(void) {
    if (file_read(MOY_TLS_CERT, D->der[0], DER_MAX, &D->der_n[0]) == 0
        && file_read(MOY_TLS_KEY, D->der[1], DER_MAX, &D->der_n[1]) == 0) {
        return 0;
    }
    if (make_cert() != 0) {
        printf("TLS certificate not made\n");
        return -1;
    }
    int rc = file_write(MOY_TLS_KEY, D->der[1], D->der_n[1]);
    rc = rc ? rc : file_write(MOY_TLS_CERT, D->der[0], D->der_n[0]);
    if (rc != 0) {
        printf("TLS certificate not kept: %d\n", rc);   // made again at the next open
    }
    return 0;
}

// -- a connection (the door's task) -------------------------------------------------

static int bio_send(void *ctx, const unsigned char *p, size_t n) {
    conn_t *c = ctx;
    ssize_t k = send(c->fd, p, n, 0);
    if (k < 0) {
        return errno == EAGAIN || errno == EWOULDBLOCK ? MBEDTLS_ERR_SSL_WANT_WRITE
                                                       : MBEDTLS_ERR_NET_SEND_FAILED;
    }
    return (int)k;
}

static int bio_recv(void *ctx, unsigned char *p, size_t n) {
    conn_t *c = ctx;
    ssize_t k = recv(c->fd, p, n, c->shook ? MSG_DONTWAIT : 0);
    if (k < 0) {
        return errno == EAGAIN || errno == EWOULDBLOCK ? MBEDTLS_ERR_SSL_WANT_READ
                                                       : MBEDTLS_ERR_NET_RECV_FAILED;
    }
    return (int)k;
}

static void conn_end(int i) {
    conn_t *c = D->c[i];
    if (c == NULL) {
        return;
    }
    if (c->shook) {
        mbedtls_ssl_close_notify(&c->ssl);
    }
    close(c->fd);
    if (c->up >= 0) {
        close(c->up);
    }
    mbedtls_ssl_free(&c->ssl);
    mbedtls_ssl_config_free(&c->conf);
    mbedtls_x509_crt_free(&c->crt);
    mbedtls_pk_free(&c->pk);
    heap_caps_free(c);
    D->c[i] = NULL;
    if (--D->conns == 0) {
        D->idle_at = moy_net_ms();
    }
}

static const int SUITES[] = {MBEDTLS_TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256, 0};

static int conn_setup(conn_t *c) {
    mbedtls_ssl_init(&c->ssl);
    mbedtls_ssl_config_init(&c->conf);
    mbedtls_x509_crt_init(&c->crt);
    mbedtls_pk_init(&c->pk);
    int rc = mbedtls_ssl_config_defaults(&c->conf, MBEDTLS_SSL_IS_SERVER,
                                         MBEDTLS_SSL_TRANSPORT_STREAM, MBEDTLS_SSL_PRESET_DEFAULT);
    if (rc == 0) {
        mbedtls_ssl_conf_rng(&c->conf, rng, NULL);
        mbedtls_ssl_conf_ciphersuites(&c->conf, SUITES);
        mbedtls_ssl_conf_max_tls_version(&c->conf, MBEDTLS_SSL_VERSION_TLS1_2);
        mbedtls_ssl_conf_session_tickets_cb(&c->conf, mbedtls_ssl_ticket_write,
                                            mbedtls_ssl_ticket_parse, &D->tkt);
        rc = mbedtls_x509_crt_parse_der(&c->crt, D->der[0], D->der_n[0]);
    }
    if (rc == 0) {
        rc = mbedtls_pk_parse_key(&c->pk, D->der[1], D->der_n[1], NULL, 0, rng, NULL);
    }
    if (rc == 0) {
        rc = mbedtls_ssl_conf_own_cert(&c->conf, &c->crt, &c->pk);
    }
    if (rc == 0) {
        rc = mbedtls_ssl_setup(&c->ssl, &c->conf);
    }
    if (rc == 0) {
        mbedtls_ssl_set_bio(&c->ssl, c, bio_send, bio_recv, NULL);
    }
    return rc;
}

static void timeout(int fd, int opt, uint32_t ms) {
    struct timeval tv = {(long)(ms / 1000u), (long)(ms % 1000u) * 1000L};
    setsockopt(fd, SOL_SOCKET, opt, &tv, sizeof(tv));
}

// The loopback to the webhost for the browser at `peer`: its end is bound
// first, so the webhost has the browser's name before the connection exists.
static int loopback(uint16_t port, uint32_t peer) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        return -1;
    }
    struct sockaddr_in a;
    socklen_t an = sizeof a;
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    uint16_t mine = 0;
    if (bind(fd, (struct sockaddr *)&a, sizeof a) == 0
        && getsockname(fd, (struct sockaddr *)&a, &an) == 0) {
        mine = ntohs(a.sin_port);
        moy_web_via(mine, peer);
    }
    a.sin_port = htons(port);
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (mine == 0 || connect(fd, (struct sockaddr *)&a, sizeof a) != 0) {
        moy_web_via(mine, 0);
        close(fd);
        return -1;
    }
    int one = 1;
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    timeout(fd, SO_SNDTIMEO, MOY_HTTP_SEND_MS);
    return fd;
}

// Accept one connection and shake hands with it, the other connections
// waiting: it joins the pump, or it is closed.
static void conn_open(void) {
    int i = 0;
    while (i < MOY_TLS_CONNS && D->c[i] != NULL) {
        i++;
    }
    struct sockaddr_in a;
    socklen_t an = sizeof a;
    memset(&a, 0, sizeof a);
    int fd = accept(D->lfd, (struct sockaddr *)&a, &an);
    conn_t *c = fd >= 0 && i < MOY_TLS_CONNS ? heap_caps_calloc(1, sizeof(conn_t), MALLOC_CAP_8BIT)
                                              : NULL;
    if (c == NULL) {
        if (fd >= 0) {
            close(fd);
        }
        return;
    }
    D->c[i] = c;
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) & ~O_NONBLOCK);
    timeout(fd, SO_RCVTIMEO, 1000);
    timeout(fd, SO_SNDTIMEO, MOY_HTTP_SEND_MS);
    c->fd = fd;
    c->up = -1;
    c->peer = a.sin_family == AF_INET ? a.sin_addr.s_addr : 0u;
    D->conns++;
    uint32_t t0 = moy_net_ms();
    int rc = conn_setup(c);
    while (rc == 0 && !mbedtls_ssl_is_handshake_over(&c->ssl)) {
        rc = mbedtls_ssl_handshake_step(&c->ssl);
        if (rc == MBEDTLS_ERR_SSL_WANT_READ || rc == MBEDTLS_ERR_SSL_WANT_WRITE) {
            rc = moy_net_ms() - t0 < HS_MS ? 0 : rc;
        }
    }
    if (rc != 0) {
        conn_end(i);
        return;
    }
    c->shook = 1;
    c->at = moy_net_ms();
}

// The browser's bytes to the webhost: 0, or -1 when the connection ended.
// The loopback is made with its first bytes, so a connection the browser
// opens ahead of a request (a preconnect) waits here, not on the webhost's
// read timeout.
static int down(conn_t *c) {
    do {
        int n = mbedtls_ssl_read(&c->ssl, D->buf, PUMP);
        if (n == MBEDTLS_ERR_SSL_WANT_READ || n == MBEDTLS_ERR_SSL_WANT_WRITE) {
            return 0;
        }
        if (n > 0 && c->up < 0) {
            c->up = loopback(D->back, c->peer);
        }
        if (n <= 0 || c->up < 0 || moy_http_send(c->up, D->buf, (size_t)n) != 0) {
            return -1;
        }
    } while (mbedtls_ssl_get_bytes_avail(&c->ssl) > 0);
    return 0;
}

// The webhost's bytes to the browser.
static int up(conn_t *c) {
    ssize_t n = recv(c->up, D->buf, PUMP, MSG_DONTWAIT);
    if (n < 0) {
        return errno == EAGAIN || errno == EWOULDBLOCK ? 0 : -1;
    }
    if (n == 0) {
        return -1;
    }
    for (size_t at = 0, tries = 0; at < (size_t)n;) {
        int k = mbedtls_ssl_write(&c->ssl, D->buf + at, (size_t)n - at);
        if ((k == MBEDTLS_ERR_SSL_WANT_WRITE || k == MBEDTLS_ERR_SSL_WANT_READ)
            && ++tries < WRITE_TRIES) {
            continue;
        }
        if (k <= 0) {
            return -1;
        }
        at += (size_t)k;
    }
    return 0;
}

static void door_free(void) {
    for (int i = 0; i < MOY_TLS_CONNS; i++) {
        conn_end(i);
    }
    if (D->lfd >= 0) {
        close(D->lfd);
    }
    mbedtls_ssl_ticket_free(&D->tkt);
    heap_caps_free(D->buf);
    mbedtls_platform_zeroize(D->der, sizeof D->der);
    heap_caps_free(D);
    D = NULL;
}

static void door_task(void *arg) {
    (void)arg;
    D->idle_at = moy_net_ms();
    __atomic_store_n(&s_state, UP, __ATOMIC_RELEASE);
    for (;;) {
        fd_set rd;
        FD_ZERO(&rd);
        int top = -1, ready = 0;
        if (D->conns < MOY_TLS_CONNS) {
            FD_SET(D->lfd, &rd);
            top = D->lfd;
        }
        for (int i = 0; i < MOY_TLS_CONNS; i++) {
            conn_t *c = D->c[i];
            if (c != NULL) {
                FD_SET(c->fd, &rd);
                top = c->fd > top ? c->fd : top;
                if (c->up >= 0) {
                    FD_SET(c->up, &rd);
                    top = c->up > top ? c->up : top;
                }
                ready |= mbedtls_ssl_get_bytes_avail(&c->ssl) > 0;
            }
        }
        struct timeval tv = {0, ready ? 0 : (long)WAIT_MS * 1000L};
        if (select(top + 1, &rd, NULL, NULL, &tv) < 0) {
            moy_net_sleep_ms(WAIT_MS);
            continue;
        }
        for (int i = 0; i < MOY_TLS_CONNS; i++) {
            conn_t *c = D->c[i];
            if (c == NULL) {
                continue;
            }
            int gone = 0;
            if (FD_ISSET(c->fd, &rd) || mbedtls_ssl_get_bytes_avail(&c->ssl) > 0) {
                gone = down(c) != 0;
            }
            if (!gone && c->up >= 0 && FD_ISSET(c->up, &rd)) {
                gone = up(c) != 0;
            }
            if (gone || (c->up < 0 && moy_net_ms() - c->at >= QUIET_MS)) {
                conn_end(i);
            }
        }
        if (D->conns < MOY_TLS_CONNS && FD_ISSET(D->lfd, &rd)) {
            conn_open();
        }
        if (D->conns == 0 && moy_net_ms() - D->idle_at >= MOY_TLS_IDLE_MS) {
            break;
        }
    }
    door_free();
    __atomic_store_n(&s_state, DOWN, __ATOMIC_RELEASE);
    moy_task_delete(MOY_TASK_TLS, NULL);
}

// -- the door's face --------------------------------------------------------------------

void moy_tls_at(const char *system) {
    snprintf(s_system, sizeof s_system, "%s", system ? system : "");
}

int moy_tls_low(void) {
    return heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT) < MOY_TLS_TERM_FREE
           || heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)
                  < MOY_TLS_TERM_BLOCK;
}

int moy_tls_open(uint16_t back) {
    int st = __atomic_load_n(&s_state, __ATOMIC_ACQUIRE);
    if (st == UP) {
        return MOY_TLS_UP;
    }
    if (st != DOWN) {
        return MOY_TLS_STARTING;
    }
    if (s_system[0] == '\0') {
        return -MOY_EINVAL;
    }
    D = heap_caps_calloc(1, sizeof(door_t), MALLOC_CAP_8BIT);
    unsigned char *buf = heap_caps_malloc(PUMP, MALLOC_CAP_8BIT);
    if (D == NULL || buf == NULL) {
        heap_caps_free(D);
        heap_caps_free(buf);
        D = NULL;
        return -MOY_ENOMEM;
    }
    D->buf = buf;
    D->back = back;
    D->lfd = -1;
    mbedtls_ssl_ticket_init(&D->tkt);
    int rc = cert();
    if (rc == 0) {
        rc = mbedtls_ssl_ticket_setup(&D->tkt, rng, NULL, MBEDTLS_CIPHER_AES_128_GCM, 86400);
    }
    if (rc == 0) {
        D->lfd = moy_http_listen(MOY_TLS_PORT);
        rc = D->lfd < 0 ? D->lfd : 0;
    }
    if (rc == 0) {
        __atomic_store_n(&s_state, STARTING, __ATOMIC_RELEASE);
        if (!moy_task_spawn(MOY_TASK_TLS, door_task, NULL, NULL)) {
            __atomic_store_n(&s_state, DOWN, __ATOMIC_RELEASE);
            rc = -MOY_ENOMEM;
        }
    }
    if (rc != 0) {
        door_free();
        return rc < 0 ? rc : -MOY_EIO;
    }
    return MOY_TLS_STARTING;
}

#endif
