// moy_ssh: the server around Dropbear's session (moy_ssh.h), and the POSIX
// names Dropbear asks for (port/moy_ssh_port.h). Shared by the board and the
// host harness; what differs is behind ESP_PLATFORM.

#include "includes.h"
#include "dbutil.h"
#include "session.h"
#include "runopts.h"
#include "dbrandom.h"
#include "signkey.h"
#include "gensignkey.h"
#include "gened25519.h"
#include "dbmalloc.h"
#include "channel.h"
#include "chansession.h"
#include "packet.h"

#include "moy_kmem.h"
#include "moy_platform.h"
#include "moy_seal.h"
#include "moy_ssh.h"
#include "moy_tty.h"
#include "moy_fs.h"

#ifdef ESP_PLATFORM
#include <errno.h>
#include <time.h>

#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#endif

#define SYS_PATH 192u
#define KEYS_MAX (16u * 1024u)

// A second connection signing in while a session is served (THE TAKEOVER,
// below): its socket (-1: none), the jump its exit takes, its session's
// globals, and the served session's while its own are swapped in.
typedef struct {
    int fd;
    jmp_buf jmp;
    struct sshsession *sess, *sess_was;
    struct serversession *svr, *svr_was;
} next_t;

// The server's own state, PSRAM (moy_ssh_globals): the jump an exit takes
// (`at`: the served session's, or the next's while its turn runs), the
// stored record and what getpwnam and crypt answer with.
typedef struct {
    jmp_buf jmp;
    jmp_buf *at;
    int lfd;                    // the listening socket while a session is served
    unsigned epoch;             // the served session's allocations' (1 or 2)
    next_t next;
    char hash[MOY_SSH_HASH_MAX];
    char crypt[MOY_SSH_HASH_MAX];
    char user[33];
    struct passwd pw;
    moy_ssh_stats_t stats;
    size_t session_base;
    uint32_t accepted_at;
    char sys[SYS_PATH];         // the store's system folder
    char *keys;                 // the connection's authorized keys, or NULL
    size_t keys_n;
    int set_up;
} moy_state_t;

static moy_state_t *g;
#define s_jmp (g->jmp)
#define s_hash (g->hash)
#define s_stats (g->stats)
#define s_session_base (g->session_base)
#define s_accepted_at (g->accepted_at)

// -- memory ------------------------------------------------------------------

// Every block carries its size ahead of it, so the counters follow frees.
typedef union {
    size_t n;
    max_align_t align;
} moy_head_t;

static void *raw_alloc(size_t n) {
#ifdef ESP_PLATFORM
    return moy_kalloc(n, MOY_KMEM_PSRAM | MOY_KMEM_ZERO);
#else
    return moy_kalloc(n, MOY_KMEM_ZERO);
#endif
}

static void raw_free(void *p) {
#ifdef ESP_PLATFORM
    heap_caps_free(p);
#else
    free(p);
#endif
}

static void count(size_t add, size_t sub) {
    if (g == NULL) {
        return;
    }
    s_stats.heap_now += add;
    s_stats.heap_now -= sub;
    if (s_stats.heap_now > s_stats.heap_peak) {
        s_stats.heap_peak = s_stats.heap_now;
    }
    if (s_stats.heap_now - s_session_base > s_stats.session_peak
            && s_stats.heap_now > s_session_base) {
        s_stats.session_peak = s_stats.heap_now - s_session_base;
    }
}

void *moy_ssh_calloc(size_t n, size_t size) {
    if (size != 0 && n > SIZE_MAX / size) {
        return NULL;
    }
    size_t want = n * size;
    moy_head_t *h = raw_alloc(sizeof *h + want);
    if (h == NULL) {
        return NULL;
    }
    h->n = want;
    count(want, 0);
    return h + 1;
}

void moy_ssh_free(void *p) {
    if (p == NULL) {
        return;
    }
    moy_head_t *h = (moy_head_t *)p - 1;
    count(0, h->n);
    raw_free(h);
}

void *moy_ssh_realloc(void *p, size_t n) {
    if (p == NULL) {
        return moy_ssh_calloc(1, n);
    }
    moy_head_t *h = (moy_head_t *)p - 1;
    void *q = moy_ssh_calloc(1, n);
    if (q == NULL) {
        return NULL;
    }
    memcpy(q, p, h->n < n ? h->n : n);
    moy_ssh_free(p);
    return q;
}

// -- the globals in PSRAM (port/moy_ssh_port.h) ----------------------------------

int moy_ssh_globals(void) {
    if (g != NULL) {
        return 0;
    }
    g = raw_alloc(sizeof *g);
    if (g == NULL) {
        return -1;
    }
    s_stats.heap_now = s_stats.heap_peak = sizeof *g;
    g->lfd = g->next.fd = -1;
    moy_ssh_g_ses = moy_ssh_calloc(1, sizeof(struct sshsession));
    moy_ssh_g_svr_ses = moy_ssh_calloc(1, sizeof(struct serversession));
    moy_ssh_g_opts = moy_ssh_calloc(1, sizeof(runopts));
    moy_ssh_g_svr_opts = moy_ssh_calloc(1, sizeof(svr_runopts));
    moy_ssh_g_ciphers = moy_ssh_calloc(TAB_SIZE, sizeof(struct ltc_cipher_descriptor));
    moy_ssh_g_hashes = moy_ssh_calloc(TAB_SIZE, sizeof(struct ltc_hash_descriptor));
    return moy_ssh_algos() == 0 && g && moy_ssh_g_ses && moy_ssh_g_svr_ses && moy_ssh_g_opts && moy_ssh_g_svr_opts
           && moy_ssh_g_ciphers && moy_ssh_g_hashes ? 0 : -1;
}

// -- the store's files ------------------------------------------------------------

// `name` in the system folder read whole, on the console's task: 0 and its
// bytes in *out (moy_buf_free's), or an errno.
static int sys_read(const char *name, moy_buf_t *out) {
    char path[SYS_PATH + 32];
    snprintf(path, sizeof path, "%s/%s", g->sys, name);
    int entered = moy_vol_gate_enter(path);
    int r = moy_fs_read(path, NULL, out);
    moy_vol_gate_leave(entered);
    return r;
}

static int sys_publish(const char *name, const void *p, size_t n) {
    char path[SYS_PATH + 32];
    snprintf(path, sizeof path, "%s/%s", g->sys, name);
    int entered = moy_vol_gate_enter(path);
    int r = moy_fs_publish(path, p, n);
    moy_vol_gate_leave(entered);
    return r;
}

// `key` in a `key = value` file's text: its value's first word into out.
static int conf_get(const char *t, size_t n, const char *key, char *out, size_t cap) {
    size_t kn = strlen(key);
    const char *end = t + n;
    while (t < end) {
        const char *nl = memchr(t, '\n', end - t);
        const char *e = nl != NULL ? nl : end;
        while (t < e && (*t == ' ' || *t == '\t')) {
            t++;
        }
        if ((size_t)(e - t) > kn && !memcmp(t, key, kn)
                && (t[kn] == ' ' || t[kn] == '\t' || t[kn] == '=')) {
            const char *v = t + kn;
            while (v < e && (*v == ' ' || *v == '\t' || *v == '=')) {
                v++;
            }
            size_t k = 0;
            while (v < e && *v != ' ' && *v != '\t' && *v != '\r' && *v != '#' && k + 1 < cap) {
                out[k++] = *v++;
            }
            out[k] = 0;
            return 1;
        }
        t = e + 1;
    }
    return 0;
}

// What a connection reads at its start (moy_ssh.h's SIGN-IN), on the
// console's task.
typedef struct {
    char hash[MOY_SSH_HASH_MAX];
    int password_auth;
    char *keys;
    size_t keys_n;
} conf_t;

static void conf_here(void *arg) {
    conf_t *c = arg;
    moy_buf_t b = {0};
    c->hash[0] = 0;
    if (sys_read("password", &b) == 0) {
        size_t n = strcspn(b.p, "\r\n");
        uint32_t iter;
        char salt[MOY_SEAL_PW_SALT_MAX + 1];
        uint8_t w0[32], l[MOY_SEAL_POINT];
        if (n < sizeof c->hash && moy_seal_pw_parse(b.p, n, &iter, salt, sizeof salt, w0, l)) {
            memcpy(c->hash, b.p, n);
            c->hash[n] = 0;
        }
        moy_seal_wipe(w0, sizeof w0);
        moy_buf_free(&b);
    }
    c->password_auth = 1;
    if (sys_read("ssh", &b) == 0) {
        char v[8];
        if (conf_get(b.p, b.n, "password_auth", v, sizeof v)) {
            c->password_auth = strcmp(v, "no") != 0;
        }
        moy_buf_free(&b);
    }
    c->keys = NULL;
    c->keys_n = 0;
    if (sys_read("authorized_keys", &b) == 0) {
        if (b.n <= KEYS_MAX) {
            c->keys = moy_ssh_calloc(1, b.n + 1);
            if (c->keys != NULL) {
                memcpy(c->keys, b.p, b.n);
                c->keys_n = b.n;
            }
        }
        moy_buf_free(&b);
    }
}

const char *moy_ssh_system(void) {
    return g != NULL ? g->sys : "";
}

const char *moy_ssh_keys(size_t *n) {
    *n = g->keys_n;
    return g->keys;
}

// -- the POSIX names ----------------------------------------------------------

struct passwd *moy_ssh_getpwnam(const char *name) {
    if (g == NULL || s_hash[0] == '\0' || name == NULL || strlen(name) >= sizeof g->user) {
        return NULL;
    }
    struct passwd *pw = &g->pw;
    strcpy(g->user, name);
    memset(pw, 0, sizeof *pw);
    pw->pw_name = g->user;
    pw->pw_passwd = s_hash;
    pw->pw_dir = (char *)"/";
    pw->pw_shell = (char *)"/bin/sh";
    pw->pw_uid = geteuid();             // the server's own: one account
    pw->pw_gid = getegid();
    return pw;
}

int moy_ssh_getgroups(int n, gid_t *list) {
    (void)n;
    (void)list;
    errno = ENOSYS;
    return -1;
}

#ifdef ESP_PLATFORM
// The one account is the server's own (uid 0); newlib declares these and the
// port has none.
uid_t getuid(void) {
    return 0;
}

uid_t geteuid(void) {
    return 0;
}

gid_t getegid(void) {
    return 0;
}

struct passwd *getpwuid(uid_t uid) {
    (void)uid;
    return moy_ssh_getpwnam("moy");
}

int nanosleep(const struct timespec *req, struct timespec *rem) {
    if (rem != NULL) {
        rem->tv_sec = 0;
        rem->tv_nsec = 0;
    }
    if (req == NULL || req->tv_nsec < 0 || req->tv_nsec >= 1000000000) {
        errno = EINVAL;
        return -1;
    }
    TickType_t t = pdMS_TO_TICKS((uint32_t)req->tv_sec * 1000u + (uint32_t)(req->tv_nsec / 1000000));
    vTaskDelay(t ? t : 1);
    return 0;
}

char *dirname(char *path) {
    char *slash = path != NULL ? strrchr(path, '/') : NULL;
    if (slash == NULL) {
        return (char *)".";
    }
    if (slash == path) {
        return (char *)"/";
    }
    *slash = '\0';
    return path;
}
#endif

void moy_ssh_entropy(void *buf, size_t n) {
    moy_seal_random(buf, n);
}

void moy_ssh_log(int priority, const char *msg) {
    (void)priority;
    printf("SSH %s\n", msg);
}

void moy_ssh_exit_jump(int code) {
    (void)code;
    longjmp(*g->at, 1);
}

// -- the password ---------------------------------------------------------------

_Static_assert(MOY_SSH_HASH_MAX >= MOY_SEAL_PW_RECORD, "a record fits");

// Dropbear compares crypt(password, stored) with stored: the record itself
// when the password is the one it was made from (moy_seal_pw_check), else a
// string no record equals.
char *moy_ssh_crypt(const char *key, const char *stored) {
    char *out = g->crypt;
    size_t n = strlen(stored);
    if (n < sizeof g->crypt && moy_seal_pw_check(key, strlen(key), stored, n)) {
        memcpy(out, stored, n + 1u);
    } else {
        s_stats.refused++;
        strcpy(out, "*");
    }
    return out;
}

// -- the server -------------------------------------------------------------------

int moy_ssh_setup(const char *system_dir) {
    if (strlen(system_dir) >= SYS_PATH) {
        printf("SSH the system folder's path is too long\n");
        return -1;
    }
    if (moy_ssh_globals() != 0) {
        printf("SSH no memory\n");
        return -1;
    }
    strcpy(g->sys, system_dir);
    if (moy_tty_setup() != 0) {
        printf("SSH no memory\n");
        return -1;
    }
    moy_tty_set_etc(g->sys);
    _dropbear_exit = svr_dropbear_exit;
    _dropbear_log = svr_dropbear_log;
    if (g->set_up) {
        return 0;
    }
    // Setup's own allocations (the options, the host key) live in epoch 0,
    // which no session frees. An exit here returns to this frame.
    m_malloc_set_epoch(0);
    g->at = &s_jmp;
    if (setjmp(s_jmp) != 0) {
        printf("SSH setup failed\n");
        return -1;
    }
    seedrandom();
    // -R: no key file is read or written here; the key is the store's
    char *argv[] = {"dropbear", "-F", "-R", NULL};
    svr_getopts(3, argv);
    load_all_hostkeys();
    enum signkey_type type = DROPBEAR_SIGNKEY_ED25519;
    moy_buf_t key = {0};
    buffer *b;
    if (sys_read("ssh_host_key", &key) == 0) {
        b = buf_new(key.n);
        buf_putbytes(b, (const unsigned char *)key.p, key.n);
        buf_setpos(b, 0);
        m_burn(key.p, key.n);
        moy_buf_free(&key);
        if (buf_get_priv_key(b, svr_opts.hostkey, &type) != DROPBEAR_SUCCESS
                || type != DROPBEAR_SIGNKEY_ED25519) {
            buf_burn_free(b);
            printf("SSH the host key does not read\n");
            return -1;
        }
        buf_burn_free(b);
    } else {
        uint32_t t0 = moy_tty_ms();
        svr_opts.hostkey->ed25519key = gen_ed25519_priv_key(256);
        b = buf_new(MAX_PRIVKEY_SIZE);
        buf_put_priv_key(b, svr_opts.hostkey, type);
        int r = sys_publish("ssh_host_key", b->data, b->len);
        buf_burn_free(b);
        printf("SSH host key made in %u ms%s\n", (unsigned)(moy_tty_ms() - t0),
               r != 0 ? ", not stored" : "");
    }
    g->set_up = 1;
    return 0;
}

int moy_ssh_listen(int port) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        return -1;
    }
    int one = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in a;
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET;
    a.sin_port = htons(port);
    a.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(fd, (struct sockaddr *)&a, sizeof a) != 0 || listen(fd, 1) != 0) {
        close(fd);
        return -1;
    }
    s_stats.listening = 1;
    return fd;
}

// The session's shell opened, on the face's task.
static void mark_shell(void) {
    s_stats.signed_in++;
    s_stats.handshake_ms = moy_tty_ms() - s_accepted_at;
}

// -- Dropbear's side of the face (port/moy_ssh_port.h) -------------------------------

// One face at a time (native/moy_tty/moy_tty.h): while the browser console's
// Terminal holds it, a shell, a command or `sftp` is refused and the client
// reads why on its stderr, its status 1 (the patch's moy_channel_refuse),
// where a channel failure would read only "shell request failed". Out of
// memory stays a channel failure.
#define BUSY_SAYS "the terminal is open in a browser; close it there and try again"

// The `sftp` subsystem arrives as the command SFTPSERVER_PATH
// (port/localoptions.h), and so does an `exec` of that name, as on OpenSSH.
// A board with no PSRAM refuses it: its buffers (native/moy_tty/README.md,
// Memory) do not fit beside a session in the one internal heap, and a refusal
// is what the client reports, where running out would cut a transfer short.
int moy_ssh_command(const char *cmd, int pty, int cols, int rows, int *fd, pid_t *pid,
                    const char **says) {
    *says = NULL;
    if (cmd != NULL && strcmp(cmd, SFTPSERVER_PATH) == 0) {
        #if defined(MOY_ON_BOARD) && !defined(MOY_HAS_PSRAM)
        return -1;
        #endif
        cmd = NULL;
        pty = MOY_TTY_SFTP;
    }
    int r = moy_tty_open(MOY_TTY_SSH, cmd, pty, cols, rows, mark_shell, fd, pid);
    if (r == MOY_TTY_EBUSY) {
        *says = pty == 1 ? BUSY_SAYS "\r\n" : BUSY_SAYS "\n";   // a terminal's line ends CR LF
    }
    return r == 0 ? 0 : -1;
}

int moy_ssh_reap(pid_t *pid, int *status) {
    return moy_tty_reap(MOY_TTY_SSH, pid, status);
}

int moy_ssh_signal(pid_t pid, int sig) {
    return moy_tty_signal(pid, sig);
}

void moy_ssh_winch(pid_t pid, int cols, int rows) {
    moy_tty_winch(pid, cols, rows);
}

// -- the takeover ------------------------------------------------------------------
//
// THE TAKEOVER (owner, 2026-11-25): a new connection that signs in ends the
// session served, which is told so on its terminal and closed; one that does
// not sign in ends nobody's. While a session is served its loop also waits on
// the listening socket (Dropbear's session_loop, moy_ssh_loop_fds and
// moy_ssh_loop_heard), so a second connection is accepted beside it and its
// own session -- its globals swapped in for its turn of each loop, its
// allocations in the other epoch, its exit jumping back here -- runs its key
// exchange and sign-in while the first one goes on. Signed in, it is served
// from then on (moy_ssh_serve_one); its exit before that (a wrong password,
// AUTH_TIMEOUT, its client gone, no memory) frees what it took and leaves the
// served session as it was. One at a time: a third waits in the backlog.

#define TAKEN_SAYS "\r\nanother session signed in; this one is closing\r\n"
// What a second connection's sign-in must find free beside a session on a
// board without PSRAM, whose one internal heap the served session, its face
// and WiFi share: room for its handshake (about a session's own Dropbear
// peak, stats()'s session_peak) with WiFi's share left over it, and one block
// for its largest buffer. Under it the connection is closed unanswered and
// the session served goes on: a sign-in never takes the heap the board runs
// on.
#define NEXT_ROOM (32u * 1024u)
#define NEXT_BLOCK (8u * 1024u)

// The globals the second connection's (on) or the served session's (off).
static void as_next(int on) {
    next_t *n = &g->next;
    if (on) {
        n->sess_was = moy_ssh_g_ses;
        n->svr_was = moy_ssh_g_svr_ses;
        moy_ssh_g_ses = n->sess;
        moy_ssh_g_svr_ses = n->svr;
        m_malloc_set_epoch(3u - g->epoch);
        g->at = &n->jmp;
    } else {
        moy_ssh_g_ses = n->sess_was;
        moy_ssh_g_svr_ses = n->svr_was;
        m_malloc_set_epoch(g->epoch);
        g->at = &g->jmp;
    }
}

// The second connection gone (its session's cleanup ran, or never began).
static void next_end(void) {
    next_t *n = &g->next;
    m_malloc_free_epoch(3u - g->epoch, 1);
    close(n->fd);
    n->fd = -1;
    moy_ssh_free(n->sess);
    moy_ssh_free(n->svr);
    n->sess = NULL;
    n->svr = NULL;
    s_stats.ended++;
}

static int next_room(void) {
#if defined(MOY_ON_BOARD) && !defined(MOY_HAS_PSRAM)
    return heap_caps_get_free_size(MALLOC_CAP_INTERNAL) >= NEXT_ROOM
           && heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL) >= NEXT_BLOCK;
#else
    return 1;
#endif
}

// The store's sign-in record and keys, for the connection signing in now.
static void conf_take(conf_t *c) {
    strcpy(s_hash, c->hash);
    moy_ssh_free(g->keys);
    g->keys = c->keys;
    g->keys_n = c->keys_n;
    svr_opts.noauthpass = !c->password_auth;
    s_stats.sessions++;
    s_accepted_at = moy_tty_ms();
}

static void next_begin(void) {
    next_t *n = &g->next;
    int fd = accept(g->lfd, NULL, NULL);
    if (fd < 0) {
        return;
    }
    conf_t c;
    if (!next_room()) {
        printf("SSH a second sign-in has no memory beside this session\n");
        close(fd);
        return;
    }
    moy_tty_hop(conf_here, &c);
    n->sess = moy_ssh_calloc(1, sizeof(struct sshsession));
    n->svr = moy_ssh_calloc(1, sizeof(struct serversession));
    if (c.hash[0] == 0 || n->sess == NULL || n->svr == NULL) {
        moy_ssh_free(c.keys);
        n->fd = fd;
        next_end();
        return;
    }
    conf_take(&c);
    n->fd = fd;
    as_next(1);
    if (setjmp(n->jmp) == 0) {
        svr_session_begin(fd, -1);
        as_next(0);
    } else {
        as_next(0);
        next_end();
    }
}

// The served session ended for the one that signed in beside it: told so on
// each channel, what it queued sent (a second at most), then closed.
static void take_over(void) {
    moy_channels_end(TAKEN_SAYS);
    uint32_t t0 = moy_tty_ms();
    while (!isempty(&ses.writequeue) && moy_tty_ms() - t0 < 1000) {
        fd_set w;
        FD_ZERO(&w);
        FD_SET(ses.sock_out, &w);
        struct timeval tv = {0, 100000};
        if (select(ses.sock_out + 1, NULL, &w, NULL, &tv) > 0) {
            write_packet();
        }
    }
    dropbear_close("another session signed in");
}

int moy_ssh_loop_fds(fd_set *readfd, fd_set *writefd, struct timeval *timeout, int maxfd) {
    next_t *n = &g->next;
    if (n->fd < 0) {
        if (g->lfd >= 0) {
            FD_SET(g->lfd, readfd);
            maxfd = g->lfd > maxfd ? g->lfd : maxfd;
        }
        return maxfd;
    }
    if (timeout->tv_sec > 1) {
        timeout->tv_sec = 1;            // its timeouts are looked at every loop
    }
    volatile int top = maxfd;
    as_next(1);
    if (setjmp(n->jmp) == 0) {
        int m = session_loop_fds(readfd, writefd);
        top = m > top ? m : top;
        as_next(0);
    } else {
        as_next(0);
        next_end();
    }
    return top;
}

void moy_ssh_loop_heard(fd_set *readfd, fd_set *writefd) {
    next_t *n = &g->next;
    if (n->fd < 0) {
        if (g->lfd >= 0 && FD_ISSET(g->lfd, readfd)) {
            FD_CLR(g->lfd, readfd);
            next_begin();
        }
        return;
    }
    volatile int in = 0;
    as_next(1);
    if (setjmp(n->jmp) == 0) {
        session_loop_step(readfd, writefd, svr_chansess_checksignal);
        in = ses.authstate.authdone;
        as_next(0);
    } else {
        as_next(0);
        next_end();
        return;
    }
    if (in) {
        take_over();
    }
}

int moy_ssh_serve_one(int lfd, int wait_ms) {
    fd_set r;
    FD_ZERO(&r);
    FD_SET(lfd, &r);
    struct timeval tv = {wait_ms / 1000, (wait_ms % 1000) * 1000};
    int n = select(lfd + 1, &r, NULL, NULL, &tv);
    if (n < 0) {
        return errno == EINTR ? 1 : -1;
    }
    if (n == 0) {
        return 1;
    }
    int fd = accept(lfd, NULL, NULL);
    if (fd < 0) {
        return 1;
    }
    conf_t c;
    moy_tty_hop(conf_here, &c);
    if (c.hash[0] == 0) {
        // no password set: no SSH
        moy_ssh_free(c.keys);
        close(fd);
        s_stats.ended++;
        return 0;
    }
    conf_take(&c);
    s_session_base = s_stats.heap_now;
    s_stats.session_peak = 0;

    memset(&ses, 0, sizeof ses);
    memset(&svr_ses, 0, sizeof svr_ses);
    g->lfd = lfd;
    g->epoch = 1;
    g->at = &s_jmp;
    m_malloc_set_epoch(1);
    seedrandom();
    // The session served, then each that signed in beside it and ended it,
    // or was signing in when it ended (THE TAKEOVER).
    volatile int served = fd, resumed = 0;
    for (;;) {
        if (setjmp(s_jmp) == 0) {
            if (resumed) {
                session_loop(svr_chansess_checksignal);
            } else {
                svr_session(served, -1);
            }
        }
        m_malloc_free_epoch(g->epoch, 1);
        close(served);
        moy_tty_reap_all(MOY_TTY_SSH, 5000);
        s_stats.ended++;
        next_t *nx = &g->next;
        if (nx->fd < 0) {
            break;
        }
        moy_ssh_free(moy_ssh_g_ses);
        moy_ssh_free(moy_ssh_g_svr_ses);
        moy_ssh_g_ses = nx->sess;
        moy_ssh_g_svr_ses = nx->svr;
        nx->sess = NULL;
        nx->svr = NULL;
        served = nx->fd;
        nx->fd = -1;
        g->epoch = 3u - g->epoch;
        m_malloc_set_epoch(g->epoch);
        resumed = 1;
    }
    m_malloc_set_epoch(0);
    g->lfd = -1;
    moy_ssh_free(g->keys);
    g->keys = NULL;
    g->keys_n = 0;
    s_hash[0] = 0;
    return 0;
}

void moy_ssh_stats(moy_ssh_stats_t *out) {
    if (g == NULL) {
        memset(out, 0, sizeof *out);
    } else {
        *out = s_stats;
    }
    moy_tty_stats_t t;
    moy_tty_stats(&t);
    out->arena_peak = t.arena_peak;
}
