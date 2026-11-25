// moy_sh_sys: the operating system dash sees (moy_sh_posix.h).
//
// A DESCRIPTOR is a slot of the running process's table (moy_sh_g.h, in the
// arena) naming an OBJECT, which lives outside the arena (host memory) with a
// count of the descriptors naming it across every process, so a fork's child
// adds a reference to each and its exit drops them (moy_sh_sys_fork/_exit):
//
//   TERM   the terminal: writes go to the host's `out`, reads the host's `in`
//          (end of file without one)
//   NUL    /dev/null
//   MEM    bytes read whole at open: a /dev or /proc read
//   READ   a file of the tree opened read-only, held open from the open to
//          the last close and read a chunk (MOY_SH_CHUNK) at a time, so a
//          reader of any size needs a chunk of the heap; lseek moves its
//          offset (moy_vol_seek). Its size is the one it had at the open
//   FILE   bytes written. Write-only into the tree they STREAM, a chunk
//          (MOY_SH_CHUNK) at a time, into a file held open from the open to
//          the last close, so an open that cannot write fails there: the file
//          itself when it is new or appended to, else `.NAME.tmp` beside it,
//          put over it at the last close, so a cut leaves the old file whole.
//          Read-write (`<>`) and the virtual files' are put whole at the last
//          close (MOY_SH_FILE_MAX)
//   PIPE_R, PIPE_W   the two ends of a pipe buffer, chunks (MOY_SH_CHUNK)
//          of the heap. Stages run one after another (moy_sh.h, THE FORK),
//          so the buffer holds the writer's whole stream and a read of an
//          empty pipe is its end. Past MOY_SH_PIPE_MEM (below), or past a
//          chunk the heap refuses, the stream goes on in a file of the store
//          (SPILL, the `.tmp` of its pipe in /etc/pipes, else /.pipes)
//          through one chunk of the heap, and the reader reads the memory,
//          then the file. The file and its folder go at the pipe's last
//          close, whatever ended its ends, and the boot's first spill
//          sweeps what a reset left (spill_sweep). A
//          spill the store has no room for (or past MOY_SH_SPILL_MAX, so
//          `yes | head` ends), or a chunk the heap refuses with no spill, is
//          said once ("no room to hold N KB", "out of memory at
//          N KB") and ends its writer as
//          SIGPIPE would (a writer ignoring it gets EPIPE), so the reader
//          reads what came before it; a write with no reader left fails with
//          EPIPE
//
// PATHS are the shell's: absolute after the working folder is applied and
// `.`/`..` folded. /dev and /proc are virtual (the host's vread/vlist, with
// /dev/null and /dev/tty here); /bin lists the installed commands (the
// host's lookup); everything else is the store's, under the host's root,
// through moy_vol. `/` lists the virtual folders, the root volume's names and
// the folders mounted beside it (moy_vol_mounts), each once.

#include <errno.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "moy_platform.h"
#include "moy_sh_posix.h"
#include "moy_sh_int.h"
#include "moy_vol.h"

// The bytes a pipe holds in memory before its stream spills: MOY_SH_PIPE_MAX,
// and on a board without PSRAM what its one heap spares above
// MOY_SH_HEAP_RESERVE (moy_sh_board.h) in a terminal session, with a
// pipeline's next pipe filling as this one drains, so a session spills
// before it meets the reserve. The host's harnesses build with a board's
// (tests/test_moy_sh.py's CFLAGS), so every long pipe there spills.
#ifndef MOY_SH_PIPE_MEM
#if defined(MOY_ON_BOARD) && !defined(MOY_HAS_PSRAM)
#define MOY_SH_PIPE_MEM (4u * 1024u)
#else
#define MOY_SH_PIPE_MEM MOY_SH_PIPE_MAX
#endif
#endif

enum { O_TERM = 1, O_NUL, O_MEM, O_READ, O_FILE, O_PIPE_R, O_PIPE_W };

typedef struct pipe_chunk {
    struct pipe_chunk *next;
    size_t len;
    char b[MOY_SH_CHUNK];
} pipe_chunk_t;

// A pipe's stream past its memory: a file of the store held open to read and
// write (MOY_VOL_UPDATE), and one chunk, the bytes written and not yet in
// the file or read from it and not yet taken.
typedef struct {
    char *path;
    moy_vol_file_t *f;
    char b[MOY_SH_CHUNK];
    size_t len, pos;            // b's bytes, and those of them taken (reading)
    int reading;                // b holds bytes read, else bytes to write
    uint32_t end, at;           // the file's bytes; the next read's offset
} spill_t;

typedef struct {
    pipe_chunk_t *head, *tail;  // read from head at `pos`, written at tail
    size_t pos, held;           // ... and the bytes between
    int readers, writers;
    int over;                   // its stream ended its writer
    spill_t *spill;             // its stream past the memory, or NULL
} sh_pipe_t;

struct moy_sh_obj {
    int kind;
    int refs;
    int flags;                  // O_ACCMODE bits and O_APPEND
    int stream;                 // TERM: 1 or 2 (0 for input)
    char *buf;
    size_t len, cap, pos;
    char *path;                 // FILE: where its bytes go
    int vfile;                  // FILE: a virtual file (the host's vwrite)
    moy_vol_file_t *held;       // FILE streamed, READ: the open file
    size_t at;                  // READ: the file's offset of buf[0] (len bytes)
    size_t size;                // READ: its size at the open
    char *tmp;                  // ... when it is written beside `path`
    size_t sent;                // ... its bytes gone to it
    int failed;                 // ... the errno a chunk failed with
    sh_pipe_t *pipe;
};

struct moy_sh_dir {
    struct dirent ent;
    char *names;                // each a type byte, its size (4 bytes), its name and NUL
    size_t len, cap, pos;
    int sized;                  // the store's listing: its sizes are kept, else 0 (as stat)
    int last_dir;               // what readdir answered last: a folder, its size
    uint32_t last_size;
};

#define DIR_HEAD 5u             // a name's type byte and size before it

// --- objects ----------------------------------------------------------------

static struct moy_sh_obj *obj_new(int kind) {
    struct moy_sh_obj *o = moy_sh_halloc(sizeof *o);
    if (o != NULL) {
        memset(o, 0, sizeof *o);
        o->kind = kind;
        o->refs = 1;
    }
    return o;
}

// `proc`: the buffer is a process block (a folder's names), else the host's.
static int buf_add(char **buf, size_t *len, size_t *cap, const void *p, size_t n, size_t max,
                   int proc) {
    if (*len + n > max) {
        return -1;
    }
    if (*len + n > *cap) {
        size_t c = *cap ? *cap : 256;
        while (c < *len + n) {
            c *= 2;
        }
        char *q = proc ? moy_sh_palloc(c) : moy_sh_halloc(c);
        if (q == NULL) {
            return -1;
        }
        if (*len) {
            memcpy(q, *buf, *len);
        }
        if (proc) {
            moy_sh_pfree(*buf);
        } else {
            moy_sh_hfree(*buf);
        }
        *buf = q;
        *cap = c;
    }
    memcpy(*buf + *len, p, n);
    *len += n;
    return 0;
}

static char *dupstr(const char *p) {
    size_t n = strlen(p) + 1;
    char *q = moy_sh_halloc(n);
    if (q != NULL) {
        memcpy(q, p, n);
    }
    return q;
}

static int store_write(const char *path, const char *p, size_t n, int append);
static void stream_close(struct moy_sh_obj *o);
static void read_close(struct moy_sh_obj *o);
static void spill_drop(sh_pipe_t *p);

static void obj_drop(struct moy_sh_obj *o) {
    if (o == NULL || --o->refs > 0) {
        return;
    }
    moy_sh_t *s = moy_sh_cur;
    if (o->held != NULL && o->kind == O_READ) {
        read_close(o);
    } else if (o->held != NULL) {
        stream_close(o);
    } else if (o->kind == O_FILE && o->path != NULL) {
        if (o->vfile) {
            if (s->host.vwrite != NULL) {
                s->host.vwrite(s->host.ctx, o->path, o->buf, o->len);
            }
        } else {
            store_write(o->path, o->buf, o->len, (o->flags & O_APPEND) != 0);
        }
    }
    if (o->pipe != NULL) {
        sh_pipe_t *p = o->pipe;
        if (o->kind == O_PIPE_R) {
            p->readers--;
        } else {
            p->writers--;
        }
        if (p->readers == 0 && p->writers == 0) {
            spill_drop(p);
            while (p->head != NULL) {
                pipe_chunk_t *c = p->head;
                p->head = c->next;
                moy_sh_hfree(c);
            }
            moy_sh_hfree(p);
        }
    }
    moy_sh_hfree(o->buf);
    moy_sh_hfree(o->path);
    moy_sh_hfree(o->tmp);
    moy_sh_hfree(o);
}

static struct moy_sh_proc *proc(void) {
    return &moy_sh_g->proc;
}

static struct moy_sh_obj *fd_obj(int fd) {
    if (fd < 0 || fd >= MOY_SH_FDS) {
        return NULL;
    }
    return proc()->fd[fd];
}

static int fd_lowest(int from) {
    for (int i = from < 0 ? 0 : from; i < MOY_SH_FDS; i++) {
        if (proc()->fd[i] == NULL) {
            return i;
        }
    }
    return -1;
}

static int fd_put(struct moy_sh_obj *o, int from) {
    int fd = fd_lowest(from);
    if (fd < 0) {
        obj_drop(o);
        errno = EMFILE;
        return -1;
    }
    proc()->fd[fd] = o;
    proc()->cloexec[fd] = 0;
    return fd;
}

void moy_sh_sys_start(moy_sh_t *s) {
    (void)s;
    for (int i = 0; i < 3; i++) {
        struct moy_sh_obj *o = obj_new(O_TERM);
        if (o != NULL) {
            o->stream = i;
            o->flags = i == 0 ? O_RDONLY : O_WRONLY;
        }
        proc()->fd[i] = o;
    }
    proc()->cwd = moy_sh_strdup("/");
    proc()->pid = 100;
}

void moy_sh_sys_fork(moy_sh_t *s) {
    (void)s;
    for (int i = 0; i < MOY_SH_FDS; i++) {
        if (proc()->fd[i] != NULL) {
            proc()->fd[i]->refs++;
        }
    }
}

void moy_sh_sys_exit(moy_sh_t *s) {
    (void)s;
    for (int i = 0; i < MOY_SH_FDS; i++) {
        struct moy_sh_obj *o = proc()->fd[i];
        proc()->fd[i] = NULL;
        obj_drop(o);
    }
}

void moy_sh_sys_end(moy_sh_t *s) {
    moy_sh_sys_exit(s);
}

// --- paths ------------------------------------------------------------------

int moy_sh_path(const char *path, char *out, size_t cap) {
    char tmp[MOY_SH_PATH_MAX];
    const char *cwd = proc()->cwd != NULL ? proc()->cwd : "/";
    size_t n;
    if (path[0] == '/') {
        n = strlen(path);
        if (n >= sizeof tmp) {
            return ENAMETOOLONG;
        }
        memcpy(tmp, path, n + 1);
    } else {
        n = (size_t)snprintf(tmp, sizeof tmp, "%s/%s", cwd, path);
        if (n >= sizeof tmp) {
            return ENAMETOOLONG;
        }
    }
    // fold: out is built component by component
    size_t o = 0;
    const char *p = tmp;
    if (cap < 2) {
        return ENAMETOOLONG;
    }
    while (*p) {
        while (*p == '/') {
            p++;
        }
        const char *e = p;
        while (*e && *e != '/') {
            e++;
        }
        size_t len = (size_t)(e - p);
        if (len == 0 || (len == 1 && p[0] == '.')) {
            // nothing
        } else if (len == 2 && p[0] == '.' && p[1] == '.') {
            while (o > 0 && out[o - 1] != '/') {
                o--;
            }
            if (o > 0) {
                o--;
            }
        } else {
            if (o + 1 + len + 1 > cap) {
                return ENAMETOOLONG;
            }
            out[o++] = '/';
            memcpy(out + o, p, len);
            o += len;
        }
        p = e;
    }
    if (o == 0) {
        out[o++] = '/';
    }
    out[o] = 0;
    return 0;
}

static int under(const char *abs, const char *dir) {
    size_t n = strlen(dir);
    return strncmp(abs, dir, n) == 0 && (abs[n] == 0 || abs[n] == '/');
}

static int is_virtual(const char *abs) {
    return under(abs, "/dev") || under(abs, "/proc") || under(abs, "/bin");
}

const char *moy_sh_store_path(const char *abs, char *out, size_t cap) {
    const char *root = moy_sh_cur->host.root != NULL ? moy_sh_cur->host.root : "";
    if (is_virtual(abs)) {
        return NULL;
    }
    const char *etc = moy_sh_cur->host.etc;
    const char *home = moy_sh_cur->home;
    size_t hn = strcmp(home, "/") == 0 ? 0 : strlen(home);
    if (etc != NULL && (under(abs, "/etc") || under(abs, "/.ssh")
                        || (hn > 0 && strncmp(abs, home, hn) == 0 && under(abs + hn, "/.ssh")))) {
        const char *rest = abs + 4;
        if (under(abs, "/.ssh")) {
            rest = abs + 5;
        } else if (!under(abs, "/etc")) {
            rest = abs + hn + 5;            // the home's .ssh
        } else if (under(rest, "/dropbear")) {
            rest += 9;
        }
        size_t n = (size_t)snprintf(out, cap, "%s%s%s", root, etc, rest);
        return n < cap ? out : NULL;
    }
    size_t n = (size_t)snprintf(out, cap, "%s%s", root, strcmp(abs, "/") == 0 && *root ? "" : abs);
    if (n >= cap) {
        return NULL;
    }
    if (n == 0) {
        out[0] = '/';
        out[1] = 0;
    }
    return out;
}

// --- the store --------------------------------------------------------------

static int store_read_here(const char *path, char **buf, size_t *len) {
    moy_vol_t v;
    const char *rest;
    moy_vol_file_t *f;
    uint32_t size = 0;
    int entered = moy_vol_gate_enter(path);
    int r = moy_vol_at(path, &v, &rest);
    if (r == 0) {
        r = moy_vol_open(&v, rest, MOY_VOL_READ, &f);
    }
    if (r == 0) {
        r = moy_vol_size(f, &size);
        if (r == 0 && size > MOY_SH_FILE_MAX) {
            r = EFBIG;
        }
        char *p = r == 0 ? moy_sh_halloc(size + 1) : NULL;
        if (r == 0 && p == NULL) {
            r = ENOMEM;
        }
        size_t got = 0;
        while (r == 0 && got < size) {
            size_t n = 0;
            r = moy_vol_read(f, p + got, size - got, &n);
            if (n == 0) {
                break;
            }
            got += n;
        }
        int c = moy_vol_close(f);
        if (r == 0) {
            r = c;
        }
        if (r == 0) {
            p[got] = 0;
            *buf = p;
            *len = got;
        } else {
            moy_sh_hfree(p);
        }
    }
    moy_vol_gate_leave(entered);
    return r;
}

static int store_write_here(const char *path, const char *p, size_t n, int append) {
    moy_vol_t v;
    const char *rest;
    moy_vol_file_t *f;
    int entered = moy_vol_gate_enter(path);
    int r = moy_vol_at(path, &v, &rest);
    if (r == 0) {
        r = moy_vol_open(&v, rest, append ? MOY_VOL_APPEND : MOY_VOL_WRITE, &f);
    }
    if (r == 0) {
        if (n) {
            r = moy_vol_write(f, p, n);
        }
        int c = moy_vol_close(f);
        if (r == 0) {
            r = c;
        }
    }
    moy_vol_gate_leave(entered);
    return r;
}

// A streamed FILE's three steps: its file opened and held, a chunk written,
// and at the last close its file closed and, written beside `path`, put over
// it (or dropped where a chunk failed).
static int stream_open_here(struct moy_sh_obj *o) {
    const char *at = o->tmp != NULL ? o->tmp : o->path;
    moy_vol_t v;
    const char *rest;
    int entered = moy_vol_gate_enter(at);
    int r = moy_vol_at(at, &v, &rest);
    if (r == 0) {
        r = moy_vol_open(&v, rest, ((o->flags & O_APPEND) ? MOY_VOL_APPEND : MOY_VOL_WRITE)
                         | MOY_VOL_HELD, &o->held);
    }
    if (r != 0) {
        o->held = NULL;
    }
    moy_vol_gate_leave(entered);
    return r;
}

static int stream_put_here(struct moy_sh_obj *o, const char *p, size_t n) {
    int entered = moy_vol_gate_enter(o->path);
    int r = moy_vol_write(o->held, p, n);
    moy_vol_gate_leave(entered);
    return r;
}

static int stream_close_here(struct moy_sh_obj *o) {
    moy_vol_t v, w;
    const char *from, *to;
    int entered = moy_vol_gate_enter(o->path);
    int r = moy_vol_close(o->held);
    o->held = NULL;
    if (o->tmp != NULL && moy_vol_at(o->tmp, &v, &from) == 0) {
        if (r == 0 && !o->failed && moy_vol_at(o->path, &w, &to) == 0) {
            r = moy_vol_replace(&v, from, to);
        }
        if (r != 0 || o->failed) {
            moy_vol_remove(&v, from);
        }
    }
    moy_vol_gate_leave(entered);
    return r;
}

// A READ's steps: its file opened and held, and a chunk read at `pos` into
// its buffer (seeking first when `pos` is not where the last one ended), up
// to the size at the open, so `cat f >> f` ends.
static int read_open_here(struct moy_sh_obj *o) {
    moy_vol_t v;
    const char *rest;
    uint32_t size = 0;
    int entered = moy_vol_gate_enter(o->path);
    int r = moy_vol_at(o->path, &v, &rest);
    if (r == 0) {
        r = moy_vol_open(&v, rest, MOY_VOL_READ | MOY_VOL_HELD, &o->held);
        if (r != 0) {
            o->held = NULL;
        }
    }
    if (r == 0) {
        r = moy_vol_size(o->held, &size);
        o->size = size;
    }
    moy_vol_gate_leave(entered);
    return r;
}

static int read_fill_here(struct moy_sh_obj *o) {
    int entered = moy_vol_gate_enter(o->path);
    int r = 0;
    size_t got = 0, want = o->pos < o->size ? o->size - o->pos : 0;
    if (want > MOY_SH_CHUNK) {
        want = MOY_SH_CHUNK;
    }
    if (want > 0 && o->pos != o->at + o->len) {
        r = moy_vol_seek(o->held, (uint32_t)o->pos);
    }
    while (r == 0 && got < want) {
        size_t n = 0;
        r = moy_vol_read(o->held, o->buf + got, want - got, &n);
        if (n == 0) {
            break;
        }
        got += n;
    }
    o->at = o->pos;
    o->len = r == 0 ? got : 0;
    moy_vol_gate_leave(entered);
    return r;
}

static int store_stat_here(const char *path, moy_vol_stat_t *st) {
    moy_vol_t v;
    const char *rest;
    int entered = moy_vol_gate_enter(path);
    int r = moy_vol_at(path, &v, &rest);
    if (r == 0) {
        r = moy_vol_stat(&v, rest, st);
    }
    moy_vol_gate_leave(entered);
    return r;
}

// A SPILL's steps: its file made (its folder first) and held, a chunk written
// at its end or read at `at`, and the file closed, then removed with its
// folder when no other spill is in it -- never the other way round, so a
// card's entry is never removed under an open file. The boot's first spill
// first removes what its folder holds (moy_vol_tmp_first): no spill is open
// before it, so each file there is one a reset left.

static int spill_first(void *ctx, const char *name, size_t len, int is_dir, uint32_t size) {
    (void)is_dir, (void)size;
    char *out = ctx;
    if (len >= 48) {
        return EINVAL;
    }
    memcpy(out, name, len + 1);
    return 1;
}

static void spill_sweep(const moy_vol_t *v, const char *dir) {
    char name[48], path[MOY_SH_PATH_MAX];
    for (;;) {
        name[0] = 0;
        if (moy_vol_list(v, dir, spill_first, name) != 1 ||
            snprintf(path, sizeof path, "%s/%s", dir, name) >= (int)sizeof path ||
            moy_vol_remove(v, path) != 0) {
            return;
        }
    }
}

static int spill_open_here(spill_t *sp) {
    moy_vol_t v;
    const char *rest;
    int entered = moy_vol_gate_enter(sp->path);
    int r = moy_vol_at(sp->path, &v, &rest);
    if (r == 0) {
        char dir[MOY_SH_PATH_MAX];
        const char *slash = strrchr(rest, '/');
        size_t n = slash != NULL ? (size_t)(slash - rest) : 0;
        if (n > 0 && n < sizeof dir) {
            memcpy(dir, rest, n);
            dir[n] = 0;
            if (moy_vol_tmp_first()) {
                spill_sweep(&v, dir);
            }
            moy_vol_mkdir(&v, dir);         // there already, or the open says why not
        }
        r = moy_vol_open(&v, rest, MOY_VOL_UPDATE | MOY_VOL_HELD, &sp->f);
        if (r != 0) {
            sp->f = NULL;
        }
    }
    moy_vol_gate_leave(entered);
    return r;
}

static int spill_put_here(spill_t *sp) {
    int entered = moy_vol_gate_enter(sp->path);
    int r = moy_vol_seek(sp->f, sp->end);
    if (r == 0) {
        r = moy_vol_write(sp->f, sp->b, sp->len);
    }
    moy_vol_gate_leave(entered);
    return r;
}

static int spill_get_here(spill_t *sp) {
    int entered = moy_vol_gate_enter(sp->path);
    size_t want = sp->end - sp->at < sizeof sp->b ? sp->end - sp->at : sizeof sp->b, got = 0;
    int r = moy_vol_seek(sp->f, sp->at);
    while (r == 0 && got < want) {
        size_t n = 0;
        r = moy_vol_read(sp->f, sp->b + got, want - got, &n);
        if (n == 0) {
            break;
        }
        got += n;
    }
    sp->len = r == 0 ? got : 0;
    moy_vol_gate_leave(entered);
    return r;
}

static int spill_drop_here(spill_t *sp) {
    moy_vol_t v;
    const char *rest;
    int entered = moy_vol_gate_enter(sp->path);
    int r = sp->f != NULL ? moy_vol_close(sp->f) : 0;
    sp->f = NULL;
    if (moy_vol_at(sp->path, &v, &rest) == 0) {
        moy_vol_remove(&v, rest);
        char dir[MOY_SH_PATH_MAX];
        const char *slash = strrchr(rest, '/');
        size_t n = slash != NULL ? (size_t)(slash - rest) : 0;
        if (n > 0 && n < sizeof dir) {
            memcpy(dir, rest, n);
            dir[n] = 0;
            moy_vol_remove(&v, dir);        // refused while another spill is in it
        }
    }
    moy_vol_gate_leave(entered);
    return r;
}

// Each store call runs where the store may be touched: through the host's
// hop (moy_sh_hop), the session current there.
typedef struct {
    int op;
    const char *path;
    char **buf;
    size_t *len;
    const char *p;
    size_t n;
    int append;
    moy_vol_stat_t *st;
    struct moy_sh_obj *o;
    spill_t *sp;
    int r;
} store_call_t;

enum { S_READ, S_WRITE, S_STAT, S_OPEN, S_PUT, S_CLOSE, S_ROPEN, S_FILL,
       S_SOPEN, S_SPUT, S_SGET, S_SDROP };

static void store_here(void *arg) {
    store_call_t *c = arg;
    switch (c->op) {
        case S_READ:
            c->r = store_read_here(c->path, c->buf, c->len);
            break;
        case S_WRITE:
            c->r = store_write_here(c->path, c->p, c->n, c->append);
            break;
        case S_OPEN:
            c->r = stream_open_here(c->o);
            break;
        case S_PUT:
            c->r = stream_put_here(c->o, c->p, c->n);
            break;
        case S_CLOSE:
            c->r = stream_close_here(c->o);
            break;
        case S_ROPEN:
            c->r = read_open_here(c->o);
            break;
        case S_FILL:
            c->r = read_fill_here(c->o);
            break;
        case S_SOPEN:
            c->r = spill_open_here(c->sp);
            break;
        case S_SPUT:
            c->r = spill_put_here(c->sp);
            break;
        case S_SGET:
            c->r = spill_get_here(c->sp);
            break;
        case S_SDROP:
            c->r = spill_drop_here(c->sp);
            break;
        default:
            c->r = store_stat_here(c->path, c->st);
            break;
    }
}

static int store_call(store_call_t *c) {
    moy_sh_hop(moy_sh_cur, store_here, c);
    return c->r;
}

static int store_read(const char *path, char **buf, size_t *len) {
    store_call_t c = { .op = S_READ, .path = path, .buf = buf, .len = len };
    return store_call(&c);
}

static int store_write(const char *path, const char *p, size_t n, int append) {
    store_call_t c = { .op = S_WRITE, .path = path, .p = p, .n = n, .append = append };
    return store_call(&c);
}

static int store_stat(const char *path, moy_vol_stat_t *st) {
    store_call_t c = { .op = S_STAT, .path = path, .st = st };
    return store_call(&c);
}

// A write-only FILE of the tree opened streamed, over `path` when it exists
// and is not appended to.
static int stream_open(struct moy_sh_obj *o, int exists) {
    if (exists && !(o->flags & O_APPEND)) {
        const char *base = strrchr(o->path, '/');
        size_t dir = base != NULL ? (size_t)(base + 1 - o->path) : 0, n = strlen(o->path);
        o->tmp = moy_sh_halloc(n + 6);
        if (o->tmp == NULL) {
            return ENOMEM;
        }
        memcpy(o->tmp, o->path, dir);
        o->tmp[dir] = '.';
        memcpy(o->tmp + dir + 1, o->path + dir, n - dir);
        memcpy(o->tmp + n + 1, ".tmp", 5);
    }
    store_call_t c = { .op = S_OPEN, .o = o };
    return store_call(&c);
}

// The chunk buffered sent to the file: 0, or the errno it failed with (and
// every later write with it).
static int stream_flush(struct moy_sh_obj *o, const char *p, size_t n) {
    if (o->failed == 0 && n > 0) {
        store_call_t c = { .op = S_PUT, .o = o, .p = p, .n = n };
        o->failed = store_call(&c);
        o->sent += o->failed == 0 ? n : 0;
    }
    return o->failed;
}

static ssize_t stream_write(struct moy_sh_obj *o, const char *p, size_t n) {
    if (o->failed == 0 && o->len + n > MOY_SH_CHUNK) {
        stream_flush(o, o->buf, o->len);
        o->len = 0;
    }
    if (o->failed == 0 && n >= MOY_SH_CHUNK) {
        stream_flush(o, p, n);
    } else if (o->failed == 0 && buf_add(&o->buf, &o->len, &o->cap, p, n, MOY_SH_CHUNK, 0) != 0) {
        o->failed = ENOMEM;
    }
    if (o->failed != 0) {
        errno = o->failed;
        return -1;
    }
    return (ssize_t)n;
}

static void stream_close(struct moy_sh_obj *o) {
    stream_flush(o, o->buf, o->len);
    o->len = 0;
    store_call_t c = { .op = S_CLOSE, .o = o };
    store_call(&c);
}

// A READ opened over the tree's `path`, its chunk buffer made: 0 or an errno.
static int read_open(struct moy_sh_obj *o) {
    o->buf = moy_sh_halloc(MOY_SH_CHUNK);
    if (o->buf == NULL) {
        return ENOMEM;
    }
    o->cap = MOY_SH_CHUNK;
    store_call_t c = { .op = S_ROPEN, .o = o };
    return store_call(&c);
}

// Up to `n` bytes at its offset, a chunk read when the offset is past the
// one buffered: the count, 0 at its end, -1 with errno.
static ssize_t read_take(struct moy_sh_obj *o, void *buf, size_t n) {
    if (o->pos < o->at || o->pos >= o->at + o->len) {
        store_call_t c = { .op = S_FILL, .o = o };
        int r = store_call(&c);
        if (r != 0) {
            errno = r;
            return -1;
        }
    }
    size_t left = o->at + o->len > o->pos ? o->at + o->len - o->pos : 0;
    if (n > left) {
        n = left;
    }
    if (n) {
        memcpy(buf, o->buf + (o->pos - o->at), n);
    }
    o->pos += n;
    return (ssize_t)n;
}

static void read_close(struct moy_sh_obj *o) {
    store_call_t c = { .op = S_CLOSE, .o = o };
    store_call(&c);
}

// --- virtual files ----------------------------------------------------------

typedef struct {
    const char *name;
    int found, is_dir;
    uint32_t size;
} find_t;

static int find_ent(void *arg, const char *name, int is_dir, uint32_t size) {
    find_t *f = arg;
    if (strcmp(name, f->name) == 0) {
        f->found = 1;
        f->is_dir = is_dir;
        f->size = size;
        return 1;
    }
    return 0;
}

static int vlist(const char *dir, moy_sh_ent_fn fn, void *arg);

// Whether the virtual `abs` exists: 0 none, 1 a file, 2 a folder.
static int vexists(const char *abs) {
    if (!strcmp(abs, "/dev") || !strcmp(abs, "/proc") || !strcmp(abs, "/bin")) {
        return 2;
    }
    if (!strcmp(abs, "/dev/null") || !strcmp(abs, "/dev/tty")) {
        return 1;
    }
    if (under(abs, "/bin")) {
        const char *name = abs + 5;
        return strchr(name, '/') == NULL && moy_sh_cur->host.lookup != NULL &&
               moy_sh_cur->host.lookup(moy_sh_cur->host.ctx, name) ? 1 : 0;
    }
    char dir[MOY_SH_PATH_MAX];
    const char *slash = strrchr(abs, '/');
    size_t n = (size_t)(slash - abs);
    if (n >= sizeof dir) {
        return 0;
    }
    memcpy(dir, abs, n);
    dir[n] = 0;
    find_t f = { slash + 1, 0, 0, 0 };
    vlist(dir, find_ent, &f);
    return f.found ? (f.is_dir ? 2 : 1) : 0;
}

static int vlist(const char *dir, moy_sh_ent_fn fn, void *arg) {
    moy_sh_t *s = moy_sh_cur;
    if (!strcmp(dir, "/dev")) {
        int r = fn(arg, "null", 0, 0);
        if (!r) {
            r = fn(arg, "tty", 0, 0);
        }
        if (!r && s->host.vlist != NULL) {
            r = s->host.vlist(s->host.ctx, dir, fn, arg) == ENOENT ? 0 : r;
        }
        return r;
    }
    if (s->host.vlist == NULL) {
        return ENOENT;
    }
    return s->host.vlist(s->host.ctx, dir, fn, arg);
}

// --- pipes ------------------------------------------------------------------

static int spill_call(spill_t *sp, int op) {
    store_call_t c = { .op = op, .sp = sp };
    return store_call(&c);
}

// The spill of `p` made: 0, or ENOMEM (no chunk, no path) or the store's errno.
// Its folder is /etc/pipes, or /.pipes where there is no /etc or no folder
// /etc names (a tree with no store).
static int spill_start(sh_pipe_t *p) {
    spill_t *sp = moy_sh_halloc(sizeof *sp);
    if (sp == NULL) {
        return ENOMEM;
    }
    memset(sp, 0, sizeof *sp);
    int r = ENOENT;
    for (int i = moy_sh_cur->host.etc != NULL ? 0 : 1; i < 2 && r == ENOENT; i++) {
        char abs[48], at[MOY_SH_PATH_MAX];
        snprintf(abs, sizeof abs, "%s/%lx.tmp", i == 0 ? "/etc/pipes" : "/.pipes",
                 (unsigned long)(uintptr_t)p);
        const char *path = moy_sh_store_path(abs, at, sizeof at);
        sp->path = path != NULL ? dupstr(path) : NULL;
        if (sp->path == NULL) {
            r = ENOMEM;
            break;
        }
        r = spill_call(sp, S_SOPEN);
        if (r != 0) {
            moy_sh_hfree(sp->path);
            sp->path = NULL;
        }
    }
    if (r != 0) {
        moy_sh_hfree(sp);
        return r;
    }
    p->spill = sp;
    return 0;
}

// The bytes waiting in the chunk written to the file: 0, EFBIG past
// MOY_SH_SPILL_MAX, or the store's errno.
static int spill_flush(spill_t *sp) {
    if (sp->reading || sp->len == 0) {
        return 0;
    }
    int r = sp->end + sp->len > MOY_SH_SPILL_MAX ? EFBIG : spill_call(sp, S_SPUT);
    if (r == 0) {
        sp->end += (uint32_t)sp->len;
        sp->len = 0;
    }
    return r;
}

static int spill_write(spill_t *sp, const char *buf, size_t n) {
    if (sp->reading) {                  // the bytes read and not taken are read again
        sp->at -= (uint32_t)(sp->len - sp->pos);
        sp->reading = 0;
        sp->len = sp->pos = 0;
    }
    while (n > 0) {
        size_t k = sizeof sp->b - sp->len < n ? sizeof sp->b - sp->len : n;
        memcpy(sp->b + sp->len, buf, k);
        sp->len += k;
        buf += k;
        n -= k;
        if (sp->len == sizeof sp->b) {
            int r = spill_flush(sp);
            if (r != 0) {
                return r;
            }
        }
    }
    return 0;
}

static ssize_t spill_read(spill_t *sp, char *buf, size_t n) {
    if (!sp->reading) {
        int r = spill_flush(sp);
        if (r != 0) {
            errno = r;
            return -1;
        }
        sp->reading = 1;
        sp->len = sp->pos = 0;
    }
    size_t got = 0;
    while (got < n) {
        if (sp->pos == sp->len) {
            if (sp->at >= sp->end) {
                break;
            }
            int r = spill_call(sp, S_SGET);
            if (r != 0 || sp->len == 0) {
                errno = r != 0 ? r : EIO;
                return got > 0 ? (ssize_t)got : -1;
            }
            sp->pos = 0;
            sp->at += (uint32_t)sp->len;
        }
        size_t k = sp->len - sp->pos < n - got ? sp->len - sp->pos : n - got;
        memcpy(buf + got, sp->b + sp->pos, k);
        sp->pos += k;
        got += k;
    }
    return (ssize_t)got;
}

// The spill's file closed and removed, and its record freed.
static void spill_drop(sh_pipe_t *p) {
    spill_t *sp = p->spill;
    if (sp != NULL) {
        p->spill = NULL;
        spill_call(sp, S_SDROP);
        moy_sh_hfree(sp->path);
        moy_sh_hfree(sp);
    }
}

// The memory first, then the spill.
static ssize_t pipe_read(sh_pipe_t *p, void *buf, size_t n) {
    size_t got = 0;
    while (got < n && p->head != NULL) {
        pipe_chunk_t *c = p->head;
        size_t k = c->len - p->pos < n - got ? c->len - p->pos : n - got;
        memcpy((char *)buf + got, c->b + p->pos, k);
        got += k;
        p->pos += k;
        p->held -= k;
        if (p->pos == c->len && (c != p->tail || c->len == sizeof c->b)) {
            p->head = c->next;
            p->tail = p->head == NULL ? NULL : p->tail;
            p->pos = 0;
            moy_sh_hfree(c);
        } else if (p->pos == c->len) {
            break;
        }
    }
    if (got < n && p->held == 0 && p->spill != NULL) {
        ssize_t r = spill_read(p->spill, (char *)buf + got, n - got);
        if (r < 0) {
            return got > 0 ? (ssize_t)got : -1;
        }
        got += (size_t)r;
    }
    return (ssize_t)got;
}

// A stream the pipe cannot hold (`err`: ENOMEM, the heap refused a chunk
// and the spill; ENOSPC or EFBIG, the store has no room for the spill; else
// the store's other refusal), said once on the writer's stderr (the
// terminal's when that is this pipe) and the writer ended as SIGPIPE ends it.
static ssize_t pipe_over(sh_pipe_t *p, int err) {
    if (!p->over) {
        p->over = 1;
        char msg[96];
        spill_t *sp = p->spill;
        size_t held = p->held + (sp != NULL ? sp->end + (sp->reading ? 0 : sp->len) : 0);
        unsigned kb = (unsigned)((held + 1023) / 1024);
        int n = err == ENOMEM
                ? snprintf(msg, sizeof msg, "pipe: out of memory at %u KB; write it to a file\n", kb)
                : err == ENOSPC || err == EFBIG
                ? snprintf(msg, sizeof msg, "pipe: no room to hold %u KB\n", kb)
                : snprintf(msg, sizeof msg, "pipe: %s at %u KB\n", strerror(err), kb);
        if (n >= (int)sizeof msg) {
            n = (int)sizeof msg - 1;
        }
        if (sp != NULL && !sp->reading) {
            sp->len = 0;                // what the file refused: the reader reads up to it
        }
        struct moy_sh_obj *e = fd_obj(2);
        moy_sh_t *s = moy_sh_cur;
        if (e != NULL && !(e->kind == O_PIPE_W && e->pipe == p)) {
            moy_sh_write(2, msg, (size_t)n);
        } else if (!moy_sh_replaying(s)) {
            s->host.out(s->host.ctx, 2, msg, (size_t)n);
        }
        moy_sh_raise(SIGPIPE);
    }
    errno = EPIPE;
    return -1;
}

static ssize_t pipe_write(sh_pipe_t *p, const void *buf, size_t n) {
    if (p->readers == 0) {
        errno = EPIPE;
        return -1;
    }
    if (p->over) {
        return pipe_over(p, EPIPE);
    }
    size_t put = 0;
    while (put < n && p->spill == NULL && p->held + n - put <= MOY_SH_PIPE_MEM) {
        pipe_chunk_t *c = p->tail;
        if (c == NULL || c->len == sizeof c->b) {
            c = moy_sh_halloc(sizeof *c);
            if (c == NULL) {
                break;
            }
            c->next = NULL;
            c->len = 0;
            if (p->tail != NULL) {
                p->tail->next = c;
            } else {
                p->head = c;
            }
            p->tail = c;
        }
        size_t k = sizeof c->b - c->len < n - put ? sizeof c->b - c->len : n - put;
        memcpy(c->b + c->len, (const char *)buf + put, k);
        c->len += k;
        put += k;
        p->held += k;
    }
    if (put < n) {
        int r = p->spill == NULL ? spill_start(p) : 0;
        if (r == 0) {
            r = spill_write(p->spill, (const char *)buf + put, n - put);
        }
        if (r != 0) {
            return pipe_over(p, r);
        }
    }
    return (ssize_t)n;
}

// --- descriptors ------------------------------------------------------------

int moy_sh_open(const char *path, int flags, ...) {
    char abs[MOY_SH_PATH_MAX], sp[MOY_SH_PATH_MAX];
    int r = moy_sh_path(path, abs, sizeof abs);
    if (r != 0) {
        errno = r;
        return -1;
    }
    int acc = flags & O_ACCMODE;
    struct moy_sh_obj *o;
    if (!strcmp(abs, "/dev/null")) {
        o = obj_new(O_NUL);
    } else if (!strcmp(abs, "/dev/tty")) {
        o = obj_new(O_TERM);
        if (o != NULL) {
            o->stream = acc == O_RDONLY ? 0 : 1;
        }
    } else if (is_virtual(abs)) {
        int kind = vexists(abs);
        if (kind == 2) {
            errno = EISDIR;
            return -1;
        }
        if (under(abs, "/bin") || (kind == 0 && acc != O_RDONLY)) {
            errno = under(abs, "/bin") && kind == 1 ? EACCES : EROFS;
            return -1;
        }
        if (kind == 0) {
            errno = ENOENT;
            return -1;
        }
        if (acc == O_RDONLY) {
            char *buf = NULL;
            size_t len = 0;
            moy_sh_t *s = moy_sh_cur;
            r = s->host.vread != NULL ? s->host.vread(s->host.ctx, abs, &buf, &len) : ENOENT;
            if (r != 0) {
                errno = r;
                return -1;
            }
            o = obj_new(O_MEM);
            if (o == NULL) {
                moy_sh_hfree(buf);
            } else {
                o->buf = buf;
                o->len = len;
            }
        } else {
            o = obj_new(O_FILE);
            if (o != NULL) {
                o->vfile = 1;
                o->path = dupstr(abs);
            }
        }
    } else {
        const char *p = moy_sh_store_path(abs, sp, sizeof sp);
        moy_vol_stat_t st;
        if (p == NULL) {
            errno = ENAMETOOLONG;
            return -1;
        }
        int exists = store_stat(p, &st) == 0;
        if (exists && st.is_dir) {
            errno = EISDIR;
            return -1;
        }
        if (acc == O_RDONLY) {
            if (!exists) {
                errno = ENOENT;
                return -1;
            }
            o = obj_new(O_READ);
            if (o == NULL) {
                errno = ENOMEM;
                return -1;
            }
            o->path = dupstr(p);
            r = o->path == NULL ? ENOMEM : read_open(o);
            if (r != 0) {
                obj_drop(o);
                errno = r;
                return -1;
            }
        } else {
            if (exists && (flags & O_CREAT) && (flags & O_EXCL)) {
                errno = EEXIST;
                return -1;
            }
            if (!exists && !(flags & O_CREAT)) {
                errno = ENOENT;
                return -1;
            }
            o = obj_new(O_FILE);
            if (o == NULL) {
                errno = ENOMEM;
                return -1;
            }
            o->path = dupstr(p);
            o->flags = flags & (O_ACCMODE | O_APPEND);
            if (o->path == NULL) {
                r = ENOMEM;
            } else if (acc == O_WRONLY) {
                r = stream_open(o, exists);
            } else if (acc == O_RDWR && exists && !(flags & O_TRUNC)) {
                // read and written whole: what was there is kept
                r = store_read(p, &o->buf, &o->len);
                o->cap = o->len;
                o->flags &= ~O_APPEND;
            } else if (!(flags & O_APPEND) || !exists) {
                // created or truncated now, so a refusal is the open's
                r = store_write(p, "", 0, 0);
            }
            if (r != 0 || o->path == NULL) {
                o->path = (moy_sh_hfree(o->path), NULL);
                obj_drop(o);
                errno = r ? r : ENOMEM;
                return -1;
            }
        }
    }
    if (o == NULL) {
        errno = ENOMEM;
        return -1;
    }
    o->flags = (o->flags & ~O_ACCMODE) | acc;
    return fd_put(o, 0);
}

ssize_t moy_sh_read(int fd, void *buf, size_t n) {
    struct moy_sh_obj *o = fd_obj(fd);
    if (o == NULL || (o->flags & O_ACCMODE) == O_WRONLY) {
        errno = EBADF;
        return -1;
    }
    switch (o->kind) {
        case O_MEM:
        case O_FILE: {
            size_t left = o->len > o->pos ? o->len - o->pos : 0;
            if (n > left) {
                n = left;
            }
            if (n) {
                memcpy(buf, o->buf + o->pos, n);
            }
            o->pos += n;
            return (ssize_t)n;
        }
        case O_READ:
            return read_take(o, buf, n);
        case O_PIPE_R:
            return pipe_read(o->pipe, buf, n);
        case O_PIPE_W:
            errno = EBADF;
            return -1;
        case O_TERM: {
            moy_sh_t *s = moy_sh_cur;
            long r = s->host.in != NULL ? s->host.in(s->host.ctx, buf, n) : 0;
            if (r < 0) {
                errno = EIO;
                return -1;
            }
            return (ssize_t)r;
        }
        default:
            return 0;
    }
}

ssize_t moy_sh_write(int fd, const void *buf, size_t n) {
    struct moy_sh_obj *o = fd_obj(fd);
    moy_sh_t *s = moy_sh_cur;
    if (o == NULL || (o->flags & O_ACCMODE) == O_RDONLY) {
        errno = EBADF;
        return -1;
    }
    switch (o->kind) {
        case O_TERM:
            if (!moy_sh_replaying(s)) {     // a replay's output was shown by the run before
                s->host.out(s->host.ctx, o->stream ? o->stream : 1, buf, n);
            }
            return (ssize_t)n;
        case O_NUL:
            return (ssize_t)n;
        case O_FILE:
            if (o->held != NULL) {
                return stream_write(o, buf, n);
            }
            if (buf_add(&o->buf, &o->len, &o->cap, buf, n, MOY_SH_FILE_MAX, 0) != 0) {
                errno = EFBIG;
                return -1;
            }
            return (ssize_t)n;
        case O_PIPE_W:
            return pipe_write(o->pipe, buf, n);
        default:
            errno = EBADF;
            return -1;
    }
}

int moy_sh_close(int fd) {
    struct moy_sh_obj *o = fd_obj(fd);
    if (o == NULL) {
        errno = EBADF;
        return -1;
    }
    proc()->fd[fd] = NULL;
    obj_drop(o);
    return 0;
}

int moy_sh_dup2(int fd, int to) {
    struct moy_sh_obj *o = fd_obj(fd);
    if (o == NULL || to < 0 || to >= MOY_SH_FDS) {
        errno = EBADF;
        return -1;
    }
    if (fd == to) {
        return to;
    }
    o->refs++;
    struct moy_sh_obj *old = proc()->fd[to];
    proc()->fd[to] = o;
    proc()->cloexec[to] = 0;
    obj_drop(old);
    return to;
}

int moy_sh_dup(int fd) {
    struct moy_sh_obj *o = fd_obj(fd);
    if (o == NULL) {
        errno = EBADF;
        return -1;
    }
    o->refs++;
    return fd_put(o, 0);
}

int moy_sh_fcntl(int fd, int cmd, ...) {
    va_list ap;
    va_start(ap, cmd);
    long arg = va_arg(ap, long);
    va_end(ap);
    struct moy_sh_obj *o = fd_obj(fd);
    if (o == NULL) {
        errno = EBADF;
        return -1;
    }
    switch (cmd) {
        case F_DUPFD:
        case F_DUPFD_CLOEXEC: {
            o->refs++;
            int to = fd_put(o, (int)arg);
            if (to >= 0 && cmd == F_DUPFD_CLOEXEC) {
                proc()->cloexec[to] = 1;
            }
            return to;
        }
        case F_GETFD:
            return proc()->cloexec[fd] ? FD_CLOEXEC : 0;
        case F_SETFD:
            proc()->cloexec[fd] = (arg & FD_CLOEXEC) != 0;
            return 0;
        case F_GETFL:
            return o->flags;
        case F_SETFL:
            return 0;
        default:
            errno = EINVAL;
            return -1;
    }
}

int moy_sh_pipe(int fds[2]) {
    sh_pipe_t *p = moy_sh_halloc(sizeof *p);
    struct moy_sh_obj *r = obj_new(O_PIPE_R), *w = obj_new(O_PIPE_W);
    if (p == NULL || r == NULL || w == NULL) {
        moy_sh_hfree(p);
        moy_sh_hfree(r);
        moy_sh_hfree(w);
        errno = ENOMEM;
        return -1;
    }
    memset(p, 0, sizeof *p);
    p->readers = p->writers = 1;
    r->pipe = w->pipe = p;
    r->flags = O_RDONLY;
    w->flags = O_WRONLY;
    fds[0] = fd_put(r, 0);
    if (fds[0] < 0) {
        p->readers = 0;
        obj_drop(w);
        return -1;
    }
    fds[1] = fd_put(w, 0);
    if (fds[1] < 0) {
        moy_sh_close(fds[0]);
        return -1;
    }
    return 0;
}

off_t moy_sh_lseek(int fd, off_t at, int whence) {
    struct moy_sh_obj *o = fd_obj(fd);
    if (o == NULL) {
        errno = EBADF;
        return -1;
    }
    if (o->kind != O_MEM && o->kind != O_FILE && o->kind != O_READ) {
        errno = ESPIPE;
        return -1;
    }
    off_t base = whence == SEEK_SET ? 0 : whence == SEEK_CUR ? (off_t)o->pos
                 : o->kind == O_READ ? (off_t)o->size : (off_t)(o->sent + o->len);
    if (base + at < 0) {
        errno = EINVAL;
        return -1;
    }
    o->pos = (size_t)(base + at);
    return (off_t)o->pos;
}

int moy_sh_isatty(int fd) {
    struct moy_sh_obj *o = fd_obj(fd);
    if (o == NULL || o->kind != O_TERM) {
        errno = o == NULL ? EBADF : ENOTTY;
        return 0;
    }
    return 1;
}

// --- files ------------------------------------------------------------------

static void fill_stat(struct stat *st, const char *abs, int is_dir, uint32_t size, int64_t mtime) {
    memset(st, 0, sizeof *st);
    st->st_mode = is_dir ? (S_IFDIR | 0755) : (S_IFREG | 0755);
    st->st_size = size;
    st->st_mtime = (time_t)mtime;
    st->st_nlink = 1;
    st->st_dev = 1;
    uint32_t h = 2166136261u;
    for (const char *p = abs; *p; p++) {
        h = (h ^ (unsigned char)*p) * 16777619u;
    }
    st->st_ino = h;
}

int moy_sh_stat(const char *path, struct stat *st) {
    char abs[MOY_SH_PATH_MAX], sp[MOY_SH_PATH_MAX];
    int r = moy_sh_path(path, abs, sizeof abs);
    if (r != 0) {
        errno = r;
        return -1;
    }
    if (!strcmp(abs, "/")) {
        fill_stat(st, abs, 1, 0, 0);
        return 0;
    }
    if (is_virtual(abs)) {
        int kind = vexists(abs);
        if (kind == 0) {
            errno = ENOENT;
            return -1;
        }
        fill_stat(st, abs, kind == 2, 0, 0);
        if (kind == 1 && under(abs, "/dev")) {
            st->st_mode = S_IFCHR | 0666;
        }
        return 0;
    }
    const char *p = moy_sh_store_path(abs, sp, sizeof sp);
    moy_vol_stat_t vs;
    r = p != NULL ? store_stat(p, &vs) : ENAMETOOLONG;
    if (r != 0) {
        // a folder the host's root listing names (a mount point on a board)
        char dir[2] = "/";
        find_t f = { abs + 1, 0, 0, 0 };
        if (strchr(abs + 1, '/') == NULL && moy_sh_cur->host.vlist != NULL) {
            moy_sh_cur->host.vlist(moy_sh_cur->host.ctx, dir, find_ent, &f);
        }
        if (f.found) {
            fill_stat(st, abs, f.is_dir, f.size, 0);
            return 0;
        }
        errno = r;
        return -1;
    }
    fill_stat(st, abs, vs.is_dir, vs.size, vs.mtime);
    return 0;
}

int moy_sh_fstat(int fd, struct stat *st) {
    struct moy_sh_obj *o = fd_obj(fd);
    if (o == NULL) {
        errno = EBADF;
        return -1;
    }
    memset(st, 0, sizeof *st);
    st->st_mode = o->kind == O_TERM || o->kind == O_NUL ? S_IFCHR | 0666 :
                  o->kind == O_PIPE_R || o->kind == O_PIPE_W ? S_IFIFO | 0600 : S_IFREG | 0644;
    st->st_size = o->kind == O_READ ? (off_t)o->size
                  : o->kind == O_MEM || o->kind == O_FILE ? (off_t)(o->sent + o->len) : 0;
    return 0;
}

int moy_sh_access(const char *path, int mode) {
    struct stat st;
    (void)mode;
    return moy_sh_stat(path, &st);
}

int moy_sh_faccessat(int dirfd, const char *path, int mode, int flags) {
    (void)dirfd;
    (void)flags;
    return moy_sh_access(path, mode);
}

int moy_sh_chdir(const char *path) {
    char abs[MOY_SH_PATH_MAX];
    struct stat st;
    int r = moy_sh_path(path, abs, sizeof abs);
    if (r != 0) {
        errno = r;
        return -1;
    }
    if (moy_sh_stat(abs, &st) != 0) {
        return -1;
    }
    if (!S_ISDIR(st.st_mode)) {
        errno = ENOTDIR;
        return -1;
    }
    char *cwd = moy_sh_strdup(abs);
    if (cwd == NULL) {
        errno = ENOMEM;
        return -1;
    }
    moy_sh_mfree(proc()->cwd);
    proc()->cwd = cwd;
    return 0;
}

char *moy_sh_getcwd(char *buf, size_t n) {
    const char *cwd = proc()->cwd != NULL ? proc()->cwd : "/";
    size_t len = strlen(cwd) + 1;
    if (buf == NULL) {
        buf = moy_sh_malloc(len);
        n = len;
        if (buf == NULL) {
            errno = ENOMEM;
            return NULL;
        }
    }
    if (len > n) {
        errno = ERANGE;
        return NULL;
    }
    memcpy(buf, cwd, len);
    return buf;
}

// --- folders ----------------------------------------------------------------

static int dir_add(void *arg, const char *name, int is_dir, uint32_t size) {
    struct moy_sh_dir *d = arg;
    char head[DIR_HEAD] = { is_dir ? 'd' : 'f' };
    uint32_t n = d->sized && !is_dir ? size : 0;
    memcpy(head + 1, &n, sizeof n);
    if (buf_add(&d->names, &d->len, &d->cap, head, DIR_HEAD, MOY_SH_FILE_MAX, 1) != 0 ||
        buf_add(&d->names, &d->len, &d->cap, name, strlen(name) + 1, MOY_SH_FILE_MAX, 1) != 0) {
        return ENOMEM;
    }
    return 0;
}

// The root's names come from several places (the virtual folders, the
// host's, the root volume's, the mount points): each is listed once.
static int root_add(void *arg, const char *name, int is_dir, uint32_t size) {
    struct moy_sh_dir *d = arg;
    for (size_t i = 0; i < d->len; i += DIR_HEAD + strlen(d->names + i + DIR_HEAD) + 1) {
        if (strcmp(d->names + i + DIR_HEAD, name) == 0) {
            return 0;
        }
    }
    return dir_add(d, name, is_dir, size);
}

static int vol_ent(void *ctx, const char *name, size_t len, int is_dir, uint32_t size) {
    (void)len;
    return dir_add(ctx, name, is_dir, size);
}

static int vol_root_ent(void *ctx, const char *name, size_t len, int is_dir, uint32_t size) {
    (void)len;
    return root_add(ctx, name, is_dir, size);
}

static int mount_ent(void *arg, const char *name) {
    return root_add(arg, name, 1, 0);
}

// Taken weak: a host whose one volume holds the whole tree has no mounts.
#pragma weak moy_vol_mounts

typedef struct {
    const char *path;
    struct moy_sh_dir *d;
    int r;
    int root;                           // the tree's root: its volume's names and the mounts
} list_call_t;

// A folder of the store listed, where the store may be touched (store_call).
static void list_here(void *arg) {
    list_call_t *c = arg;
    moy_vol_t v;
    const char *rest;
    int entered = moy_vol_gate_enter(c->path);
    c->r = c->path != NULL ? moy_vol_at(c->path, &v, &rest) : ENAMETOOLONG;
    if (c->r == 0) {
        c->r = moy_vol_list(&v, rest, c->root ? vol_root_ent : vol_ent, c->d);
    }
    moy_vol_gate_leave(entered);
    if (c->root && moy_vol_mounts != NULL) {
        moy_vol_mounts(mount_ent, c->d);
    }
}

moy_sh_DIR *moy_sh_opendir(const char *path) {
    char abs[MOY_SH_PATH_MAX], sp[MOY_SH_PATH_MAX];
    struct stat st;
    int r = moy_sh_path(path, abs, sizeof abs);
    if (r != 0) {
        errno = r;
        return NULL;
    }
    if (moy_sh_stat(abs, &st) != 0) {
        return NULL;
    }
    if (!S_ISDIR(st.st_mode)) {
        errno = ENOTDIR;
        return NULL;
    }
    struct moy_sh_dir *d = moy_sh_palloc(sizeof *d);
    if (d == NULL) {
        errno = ENOMEM;
        return NULL;
    }
    memset(d, 0, sizeof *d);
    moy_sh_t *s = moy_sh_cur;
    if (!strcmp(abs, "/bin")) {
        r = s->host.vlist != NULL ? s->host.vlist(s->host.ctx, abs, dir_add, d) : 0;
        r = r == ENOENT ? 0 : r;
    } else if (is_virtual(abs)) {
        r = vlist(abs, dir_add, d);
        r = r == ENOENT && !strcmp(abs, "/proc") ? 0 : r;
    } else {
        int root = !strcmp(abs, "/");
        if (root) {
            dir_add(d, "bin", 1, 0);
            dir_add(d, "dev", 1, 0);
            if (s->host.etc != NULL) {
                dir_add(d, "etc", 1, 0);
            }
            dir_add(d, "proc", 1, 0);
            if (s->host.vlist != NULL) {
                s->host.vlist(s->host.ctx, "/", root_add, d);
            }
        }
        d->sized = 1;
        list_call_t c = { moy_sh_store_path(abs, sp, sizeof sp), d, 0, root };
        moy_sh_hop(s, list_here, &c);
        r = !strcmp(abs, "/") ? 0 : c.r;
    }
    if (r != 0) {
        moy_sh_pfree(d->names);
        moy_sh_pfree(d);
        errno = r;
        return NULL;
    }
    return d;
}

struct dirent *moy_sh_readdir(moy_sh_DIR *d) {
    if (d->pos >= d->len) {
        return NULL;
    }
    char t = d->names[d->pos];
    memcpy(&d->last_size, d->names + d->pos + 1, sizeof d->last_size);
    d->last_dir = t == 'd';
    const char *name = d->names + d->pos + DIR_HEAD;
    size_t n = strlen(name);
    d->pos += DIR_HEAD + n + 1;
    if (n >= sizeof d->ent.d_name) {
        n = sizeof d->ent.d_name - 1;
    }
    memcpy(d->ent.d_name, name, n);
    d->ent.d_name[n] = 0;
#ifdef DT_DIR
    d->ent.d_type = t == 'd' ? DT_DIR : DT_REG;
#else
    (void)t;
#endif
    return &d->ent;
}

void moy_sh_dir_last(const moy_sh_DIR *d, int *is_dir, uint32_t *size) {
    *is_dir = d->last_dir;
    *size = d->last_size;
}

int moy_sh_closedir(moy_sh_DIR *d) {
    if (d != NULL) {
        moy_sh_pfree(d->names);
        moy_sh_pfree(d);
    }
    return 0;
}

// --- processes and signals ---------------------------------------------------

pid_t moy_sh_getpid(void) {
    return proc()->pid;
}

int moy_sh_kill(pid_t pid, int sig) {
    moy_sh_t *s = moy_sh_cur;
    if (pid < 0) {
        pid = -pid;
    }
    if (pid == 0 || pid == proc()->pid) {
        if (sig == 0) {
            return 0;
        }
        return moy_sh_raise(sig);
    }
    if (pid >= MOY_SH_FIRST_CHILD) {
        // a child the shell ran has already run to its end
        if ((sig == 0 || sig == SIGCONT) && moy_sh_kid(pid) >= 0) {
            return 0;
        }
        errno = ESRCH;
        return -1;
    }
    if (sig == 0) {
        int code;
        if (s->host.status != NULL && s->host.status(s->host.ctx, pid, &code) >= 0) {
            return 0;
        }
        errno = ESRCH;
        return -1;
    }
    int r = s->host.kill != NULL ? (*s->host.kill)(s->host.ctx, pid, sig) : ESRCH;
    if (r != 0) {
        errno = r;
        return -1;
    }
    return 0;
}

int moy_sh_sigaction(int sig, const struct sigaction *act, struct sigaction *old) {
    (void)sig;
    (void)act;
    if (old != NULL) {
        memset(old, 0, sizeof *old);
        old->sa_handler = SIG_DFL;
    }
    return 0;
}

int moy_sh_sigprocmask(int how, const sigset_t *set, sigset_t *old) {
    (void)how;
    (void)set;
    if (old != NULL) {
        sigemptyset(old);
    }
    return 0;
}

int moy_sh_tcgetattr(int fd, struct termios *t) {
    (void)fd;
    (void)t;
    errno = ENOTTY;
    return -1;
}

mode_t moy_sh_umask(mode_t m) {
    (void)m;
    return 022;
}

long moy_sh_sysconf(int name) {
    (void)name;
    return 100;
}

// The signal names, by number (kill -l, trap); 0 is EXIT, a number not named
// here is NULL and dash skips it.
const char *const signal_names[NSIG + 1] = {
    [0] = "EXIT",
    [SIGHUP] = "HUP", [SIGINT] = "INT", [SIGQUIT] = "QUIT", [SIGILL] = "ILL",
    [SIGTRAP] = "TRAP", [SIGABRT] = "ABRT", [SIGFPE] = "FPE", [SIGKILL] = "KILL",
    [SIGSEGV] = "SEGV", [SIGPIPE] = "PIPE", [SIGALRM] = "ALRM", [SIGTERM] = "TERM",
    [SIGUSR1] = "USR1", [SIGUSR2] = "USR2", [SIGCHLD] = "CHLD", [SIGCONT] = "CONT",
    [SIGSTOP] = "STOP", [SIGTSTP] = "TSTP", [SIGTTIN] = "TTIN", [SIGTTOU] = "TTOU",
    [SIGWINCH] = "WINCH",
};

const char *moy_sh_strsignal(int sig) {
    static const struct { int sig; const char *text; } texts[] = {
        { SIGHUP, "Hangup" }, { SIGINT, "Interrupt" }, { SIGQUIT, "Quit" },
        { SIGABRT, "Aborted" }, { SIGKILL, "Killed" }, { SIGSEGV, "Segmentation fault" },
        { SIGPIPE, "Broken pipe" }, { SIGALRM, "Alarm clock" }, { SIGTERM, "Terminated" },
        { SIGSTOP, "Stopped (signal)" }, { SIGTSTP, "Stopped" },
    };
    for (size_t i = 0; i < sizeof texts / sizeof texts[0]; i++) {
        if (texts[i].sig == sig) {
            return texts[i].text;
        }
    }
    if (sig > 0 && sig < NSIG && signal_names[sig] != NULL) {
        return signal_names[sig];
    }
    return "Unknown signal";
}

int moy_sh_unsupported(const char *what) {
    moy_sh_t *s = moy_sh_cur;
    static const char msg[] = "sh: the kernel has no ";
    s->host.out(s->host.ctx, 2, msg, sizeof msg - 1);
    s->host.out(s->host.ctx, 2, what, strlen(what));
    s->host.out(s->host.ctx, 2, "\n", 1);
    abort();
}
