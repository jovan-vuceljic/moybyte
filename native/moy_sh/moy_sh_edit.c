// moy_sh_edit: `edit FILE`, the terminal's text editor (#117), a full-screen
// app (moy_sh_app.h) in C, so the Terminal and the recovery floor edit a file
// with the same code and the floor edits `system/settings` with no VM.
//
// THE SCREEN: the file's name on the top row (`*` once changed), the text
// under it, and on the last row what was said last or the keys: with a
// keyboard's Ctrl `^S save  ^X exit`; without one (the T-Deck) the face's
// key row holds Save and Exit. A line wider than the screen scrolls
// sideways while the cursor is on it, marked `$` at the cut.
//
// THE KEYS: the bytes typed, Enter a new line, Backspace and Delete, the
// arrows, Home, End, PgUp and PgDn; ^S saves, ^X (or ^C, or Esc) closes, and
// asks first when the text changed: y saves and closes, n closes, anything
// else goes back to the text. Saving is the store's crash-safe write
// (native/moy_store/moy_fs.h's moy_fs_publish_from), as `settings set` writes.
//
// THE TEXT, at most EDIT_MAX bytes, is a list of blocks (#276), each one
// request of BLK bytes from the host table's alloc (PSRAM on a board), so no
// request the editor makes for text is bigger than a block, whatever the
// file's size: a board without PSRAM has its free memory in pieces, and a
// file that needs one piece its size (or twice it) does not open there. The
// file is read straight into the blocks by the store's crash-safe read
// (moy_fs_read_into) and saved from them by its crash-safe write, which
// passes over the blocks and holds no copy. A block keeps its bytes at its
// start: an insert moves the rest of its block (a key costs at most a
// block's bytes), one that overflows its block moves the block's tail to a
// new one and goes on into blocks of its own, and a delete that leaves two
// neighbours fitting in three quarters of a block joins them, so the blocks
// stay well filled and a key typed and taken back does not make and free one
// each time. vi's register and its undo step are block lists the same way.
// A file that does not exist opens empty and is made at the first save.
//
// BLK is 1 KB: the app's own record and its screen (moy_sh_app.h) are each
// a larger request already, so a smaller block would not lower the largest
// request an open makes; and at 1 KB the heap's header and the block's
// links cost a few percent of it, where a 512-byte block costs twice that
// and twice the walks.

#include <ctype.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "moy_fs.h"
#include "moy_sh_app.h"

#define EDIT_MAX (256u * 1024u)
#define BLK 1024u                       // one block, its links included: every text request
#define PATH_CAP 512
#define NAME_CAP 48
#define MSG_CAP 80
#define TAB 8
#define TITLE moy_term_accent((char[MOY_TERM_ACCENT_BYTES]){0})  // the block's own
#define DIM "\x1b[2m"
#define REV "\x1b[7m"
#define PLAIN "\x1b[0m"
#define CTRL(c) ((c) & 0x1F)

typedef struct blk {
    struct blk *prev, *next;
    uint16_t n;                         // the bytes it holds, from d[0]
    char d[];
} blk_t;

#define BCAP (BLK - offsetof(blk_t, d)) // the bytes a block holds
#define JOIN (BCAP - BCAP / 4)          // neighbours this small together become one

// A text: its blocks, none of them empty, and where the last look into it
// found itself (a block and the position of its first byte), so a walk
// along the text finds each byte where the last one was.
typedef struct {
    blk_t *head, *tail;
    size_t n;
    blk_t *b;
    size_t b0;
} text_t;

typedef struct {
    char path[PATH_CAP];                // the store's path
    char name[NAME_CAP];                // as the title shows it
    text_t t;
    size_t cur;                         // the cursor, a position in the text
    int changed;
    int fresh;                          // the file was not there: a new one
    int ask;                            // the close's question is up
    int top;                            // the first line shown
    int want;                           // the column up and down aim at, -1 the cursor's
    char msg[MSG_CAP];
    // vi: the same record, with its modes, register and undo
    int vi;                             // 0 edit, 1 vi, 2 read-only (view, less, more)
    int mode;                           // VI_NORMAL, VI_INSERT, VI_LINE
    int vis;                            // VISUAL (in NORMAL): 'v' charwise, 'V' linewise, 0 not
    int eol;                            // VISUAL's `$`: the cursor on its line's break
    size_t anchor;                      // VISUAL: the selection's other end
    int count, opcount;                 // the counts typed before a command, before its motion
    int op;                             // the operator or prefix waiting for its next key
    char line[MSG_CAP];                 // the `:`, `/` or `?` line being typed
    size_t line_n;
    char line_kind;
    char pat[MSG_CAP];                  // the last search
    int pat_dir;
    text_t reg;                         // the register: what was yanked or deleted
    int has_reg;
    int reg_lines;                      // whole lines
    text_t undo;                        // the text before the last change and its cursor,
    size_t undo_cur;                    // so u swaps the two and copies nothing
    int has_undo;
    int nu;                             // :set nu
    int dot[48], rec[48];               // the last change's keys; the one being typed
    int dot_n, rec_n, recording, replaying;
} ed_t;

// -- the blocks -------------------------------------------------------------------

static blk_t *blk_new(moy_sh_app_t *a) {
    blk_t *b = moy_sh_app_alloc(a, BLK);
    if (b != NULL) {
        b->prev = b->next = NULL;
        b->n = 0;
    }
    return b;
}

static void unlink_blk(moy_sh_app_t *a, text_t *t, blk_t *b) {
    *(b->prev != NULL ? &b->prev->next : &t->head) = b->next;
    *(b->next != NULL ? &b->next->prev : &t->tail) = b->prev;
    t->b = NULL;
    moy_sh_app_free(a, b);
}

static void text_free(moy_sh_app_t *a, text_t *t) {
    while (t->head != NULL) {
        blk_t *b = t->head;
        t->head = b->next;
        moy_sh_app_free(a, b);
    }
    memset(t, 0, sizeof *t);
}

static size_t dist(size_t x, size_t y) {
    return x > y ? x - y : y - x;
}

// The block holding position `pos` and *off its offset there: at the text's
// end, its last block and that block's end (NULL for an empty text). The
// walk starts from whichever of the text's ends and the last look is nearer.
static blk_t *seek(const text_t *t, size_t pos, size_t *off) {
    text_t *m = (text_t *)t;            // where it looked last is not the text
    *off = 0;
    if (t->head == NULL) {
        return NULL;
    }
    blk_t *b = t->b;
    size_t b0 = t->b0, last = t->n - t->tail->n;
    if (b == NULL || pos < dist(pos, b0)) {
        b = t->head;
        b0 = 0;
    }
    if (dist(pos, last) < dist(pos, b0)) {
        b = t->tail;
        b0 = last;
    }
    while (pos < b0) {
        b = b->prev;
        b0 -= b->n;
    }
    while (pos >= b0 + b->n && b->next != NULL) {
        b0 += b->n;
        b = b->next;
    }
    m->b = b;
    m->b0 = b0;
    *off = pos - b0;
    return b;
}

// What an insert copies in: bytes, or another text from `from` on.
typedef struct {
    const char *p;
    const text_t *t;
    size_t from;
} src_t;

// `n` bytes of `s`, `k` in, to `d`.
static void src_get(const src_t *s, size_t k, char *d, size_t n) {
    if (s->p != NULL) {
        memcpy(d, s->p + k, n);
        return;
    }
    for (size_t pos = s->from + k; n > 0;) {
        size_t off;
        const blk_t *b = seek(s->t, pos, &off);
        size_t m = b->n - off < n ? b->n - off : n;
        memcpy(d, b->d + off, m);
        d += m;
        pos += m;
        n -= m;
    }
}

static void chain_free(moy_sh_app_t *a, blk_t *c) {
    while (c != NULL) {
        blk_t *nx = c->next;
        moy_sh_app_free(a, c);
        c = nx;
    }
}

// `n` bytes of `s` into `t` at `pos`, all of them or (no memory) none.
static int text_ins(moy_sh_app_t *a, text_t *t, size_t pos, const src_t *s, size_t n) {
    if (n == 0) {
        return 1;
    }
    size_t off;
    blk_t *b = seek(t, pos, &off), *first = NULL;
    if (b == NULL) {                    // an empty text: its first block
        if ((b = first = blk_new(a)) == NULL) {
            return 0;
        }
        t->head = t->tail = b;
    } else if (off == 0 && b->prev != NULL && b->prev->n + n <= BCAP) {
        b = b->prev;                    // at a block's start: the end of the one before
        off = b->n;
    }
    if (b->n + n <= BCAP) {
        memmove(b->d + off + n, b->d + off, b->n - off);
        src_get(s, 0, b->d + off, n);
        b->n = (uint16_t)(b->n + n);
        t->n += n;
        t->b = b;                       // where it starts has not moved: the next key's look
        t->b0 = pos - off;
        return 1;
    }
    t->b = NULL;
    // The bytes fill `b` from `off`, then blocks of their own, the last
    // partly; b's tail (r bytes) goes after them, into the last of those
    // where it fits, else into one more. Every block is made before a byte
    // moves.
    size_t r = b->n - off, into_b = BCAP - off < n ? BCAP - off : n, rest = n - into_b;
    size_t k = (rest + BCAP - 1) / BCAP;
    size_t last = k ? rest - (k - 1) * BCAP : off + into_b;
    size_t made = k + (r > BCAP - last);
    blk_t *chain = NULL, *end = NULL;
    for (size_t i = 0; i < made; i++) {
        blk_t *c = blk_new(a);
        if (c == NULL) {
            chain_free(a, chain);
            if (first != NULL) {
                unlink_blk(a, t, first);
            }
            return 0;
        }
        c->prev = end;
        *(end != NULL ? &end->next : &chain) = c;
        end = c;
    }
    if (r > 0) {                        // the tail first, before the bytes cover it
        if (made > k) {
            memcpy(end->d, b->d + off, r);
            end->n = (uint16_t)r;
        } else {
            memcpy(end->d + last, b->d + off, r);
        }
    }
    src_get(s, 0, b->d + off, into_b);
    b->n = (uint16_t)(off + into_b);
    size_t done = into_b;
    for (blk_t *c = chain; done < n; c = c->next) {
        size_t m = n - done < BCAP ? n - done : BCAP;
        src_get(s, done, c->d, m);
        c->n = (uint16_t)(m + (done + m == n && made == k ? r : 0));
        done += m;
    }
    if (chain != NULL) {
        end->next = b->next;
        *(b->next != NULL ? &b->next->prev : &t->tail) = end;
        b->next = chain;
        chain->prev = b;
    }
    t->n += n;
    return 1;
}

// `b` and the block after it as one, when together they fill no more than JOIN.
static void join_next(moy_sh_app_t *a, text_t *t, blk_t *b) {
    blk_t *c = b != NULL ? b->next : NULL;
    if (c != NULL && b->n + c->n <= JOIN) {
        memcpy(b->d + b->n, c->d, c->n);
        b->n = (uint16_t)(b->n + c->n);
        unlink_blk(a, t, c);
    }
}

// [from, to) out of `t`.
static void text_del(moy_sh_app_t *a, text_t *t, size_t from, size_t to) {
    to = to < t->n ? to : t->n;
    while (from < to) {
        size_t off;
        blk_t *b = seek(t, from, &off);
        size_t k = b->n - off < to - from ? b->n - off : to - from;
        memmove(b->d + off, b->d + off + k, b->n - off - k);
        b->n = (uint16_t)(b->n - k);
        t->n -= k;
        to -= k;
        if (b->n == 0) {
            unlink_blk(a, t, b);
        }
    }
    size_t off;
    blk_t *b = seek(t, from, &off);
    if (b != NULL && b->prev != NULL && b->prev->n + b->n <= JOIN) {
        b = b->prev;
    }
    join_next(a, t, b);
}

// A copy of [from, to) of `src` as a text of its own, or (no memory) 0.
static int text_copy(moy_sh_app_t *a, text_t *out, const text_t *src, size_t from, size_t to) {
    src_t s = { NULL, src, from };
    memset(out, 0, sizeof *out);
    return text_ins(a, out, 0, &s, to - from);
}

// -- the text ---------------------------------------------------------------------

static size_t len(const ed_t *e) {
    return e->t.n;
}

static char at(const ed_t *e, size_t i) {
    const text_t *t = &e->t;
    if (t->b != NULL && i >= t->b0 && i - t->b0 < t->b->n) {
        return t->b->d[i - t->b0];
    }
    size_t off;
    const blk_t *b = seek(t, i, &off);
    return b != NULL && off < b->n ? b->d[off] : 0;
}

static void move_to(ed_t *e, size_t pos) {
    e->cur = pos;
}

// `n` bytes of `s` in at the cursor, the cursor after them: whether they went.
static int put_in(moy_sh_app_t *a, ed_t *e, const src_t *s, size_t n) {
    if (n == 0) {
        return 1;
    }
    if (len(e) + n > EDIT_MAX) {
        snprintf(e->msg, sizeof e->msg, "the file is at its %u KB", EDIT_MAX / 1024u);
        return 0;
    }
    if (!text_ins(a, &e->t, e->cur, s, n)) {
        snprintf(e->msg, sizeof e->msg, "out of memory");
        return 0;
    }
    e->cur += n;
    e->changed = 1;
    return 1;
}

static void insert(moy_sh_app_t *a, ed_t *e, char c) {
    src_t s = { &c, NULL, 0 };
    put_in(a, e, &s, 1);
}

static int cont(char c) {
    return ((unsigned char)c & 0xC0) == 0x80;
}

// The character before the cursor out, its continuation bytes with it.
static void back_char(moy_sh_app_t *a, ed_t *e) {
    size_t q = e->cur;
    while (q > 0 && cont(at(e, --q))) {
    }
    if (q < e->cur) {
        text_del(a, &e->t, q, e->cur);
        e->cur = q;
        e->changed = 1;
    }
}

static void del_char(moy_sh_app_t *a, ed_t *e) {
    size_t n = len(e), q = e->cur + 1;
    if (e->cur < n) {
        while (q < n && cont(at(e, q))) {
            q++;
        }
        text_del(a, &e->t, e->cur, q);
        e->changed = 1;
    }
}

static size_t line_start(const ed_t *e, size_t pos) {
    while (pos > 0 && at(e, pos - 1) != '\n') {
        pos--;
    }
    return pos;
}

static size_t line_end(const ed_t *e, size_t pos) {
    size_t n = len(e);
    while (pos < n && at(e, pos) != '\n') {
        pos++;
    }
    return pos;
}

static int advance(int col, char c) {
    return c == '\t' ? (col / TAB + 1) * TAB : cont(c) ? col : col + 1;
}

static int col_of(const ed_t *e, size_t start, size_t pos) {
    int col = 0;
    for (size_t i = start; i < pos; i++) {
        col = advance(col, at(e, i));
    }
    return col;
}

static size_t pos_at(const ed_t *e, size_t start, int col) {
    size_t end = line_end(e, start), i = start;
    int c = 0;
    while (i < end) {
        int nx = advance(c, at(e, i));
        if (nx > col && !cont(at(e, i))) {
            break;
        }
        c = nx;
        i++;
        while (i < end && cont(at(e, i))) {
            i++;
        }
    }
    return i;
}

// The newlines before `pos`, counted a block at a time.
static int line_of(const ed_t *e, size_t pos) {
    int n = 0;
    size_t b0 = 0;
    for (const blk_t *b = e->t.head; b != NULL && b0 < pos; b0 += b->n, b = b->next) {
        const char *p = b->d, *end = b->d + (pos - b0 < b->n ? pos - b0 : b->n);
        while ((p = memchr(p, '\n', (size_t)(end - p))) != NULL) {
            n++;
            p++;
        }
    }
    return n;
}

static int lines(const ed_t *e) {
    return line_of(e, len(e)) + 1;
}

// Where line `ln` starts (the text's end past its last line).
static size_t start_of_line(const ed_t *e, int ln) {
    int k = 0;
    size_t b0 = 0;
    if (ln <= 0) {
        return 0;
    }
    for (const blk_t *b = e->t.head; b != NULL; b0 += b->n, b = b->next) {
        const char *p = b->d, *end = b->d + b->n;
        while ((p = memchr(p, '\n', (size_t)(end - p))) != NULL) {
            p++;
            if (++k == ln) {
                return b0 + (size_t)(p - b->d);
            }
        }
    }
    return len(e);
}

static void vertical(ed_t *e, int d) {
    size_t s = line_start(e, e->cur);
    if (e->want < 0) {
        e->want = col_of(e, s, e->cur);
    }
    int ln = line_of(e, e->cur) + d, last = lines(e) - 1;
    ln = ln < 0 ? 0 : ln > last ? last : ln;
    move_to(e, pos_at(e, start_of_line(e, ln), e->want));
}

// -- the file -----------------------------------------------------------------------

// The file's reads and its save run where the store may be touched (the
// session's hop, moy_sh_hop).
typedef struct {
    const char *path;
    moy_fs_src_t *src;
    moy_fs_sink_t *k;
    int is_dir, exists, rc;
} ed_io_t;

static void ed_save_here(void *arg) {
    ed_io_t *io = arg;
    io->rc = moy_fs_publish_from(io->path, io->src);
}

static void ed_load_here(void *arg) {
    ed_io_t *io = arg;
    moy_vol_stat_t vs;
    io->is_dir = moy_fs_stat(io->path, &vs) == 0 && vs.is_dir;
    if (!io->is_dir) {
        io->rc = moy_fs_read_into(io->path, io->k);
        io->exists = io->rc == 0 || moy_fs_exists(io->path);
    }
}

// The read's sink: the file straight into blocks, each filled before the next.
typedef struct {
    moy_fs_sink_t k;
    moy_sh_app_t *a;
    text_t t;
} ed_sink_t;

static int sink_begin(moy_fs_sink_t *k, size_t n) {
    ed_sink_t *s = (ed_sink_t *)k;
    text_free(s->a, &s->t);
    return n > EDIT_MAX ? EFBIG : 0;
}

static char *sink_room(moy_fs_sink_t *k, size_t *n) {
    ed_sink_t *s = (ed_sink_t *)k;
    blk_t *b = s->t.tail;
    if (b == NULL || b->n == BCAP) {
        if (s->t.n >= EDIT_MAX || (b = blk_new(s->a)) == NULL) {
            return NULL;
        }
        b->prev = s->t.tail;
        *(s->t.tail != NULL ? &s->t.tail->next : &s->t.head) = b;
        s->t.tail = b;
    }
    *n = BCAP - b->n;
    return b->d + b->n;
}

static void sink_took(moy_fs_sink_t *k, size_t n) {
    ed_sink_t *s = (ed_sink_t *)k;
    s->t.tail->n = (uint16_t)(s->t.tail->n + n);
    s->t.n += n;
}

// The save's source: the blocks in order, and the newline vi ends a file with.
typedef struct {
    moy_fs_src_t s;
    const text_t *t;
    const blk_t *b;
    int nl, nl_given;
} ed_src_t;

static size_t src_next(moy_fs_src_t *s, const char **p) {
    ed_src_t *e = (ed_src_t *)s;
    while (e->b != NULL && e->b->n == 0) {
        e->b = e->b->next;
    }
    if (e->b != NULL) {
        *p = e->b->d;
        size_t n = e->b->n;
        e->b = e->b->next;
        return n;
    }
    if (e->nl && !e->nl_given) {
        e->nl_given = 1;
        *p = "\n";
        return 1;
    }
    return 0;
}

static void src_rewind(moy_fs_src_t *s) {
    ed_src_t *e = (ed_src_t *)s;
    e->b = e->t->head;
    e->nl_given = 0;
}

// The text into `path` (the file's own, or vi's `:w FILE`): 0 once saved.
static int save_to(moy_sh_app_t *a, ed_t *e, const char *path) {
    size_t n = len(e);
    int nl = e->vi && n > 0 && at(e, n - 1) != '\n';   // vi ends a file with a newline, as vi does
    ed_src_t src = { { src_next, src_rewind }, &e->t, NULL, nl, 0 };
    ed_io_t io = { .path = path, .src = &src.s };
    moy_sh_hop(moy_sh_app_session(a), ed_save_here, &io);
    int rc = io.rc;
    if (rc != 0) {
        snprintf(e->msg, sizeof e->msg, "not saved: %s", strerror(rc > 0 ? rc : EIO));
        return rc > 0 ? rc : EIO;
    }
    snprintf(e->msg, sizeof e->msg, "saved, %u bytes", (unsigned)(n + (size_t)nl));
    return 0;
}

static void save(moy_sh_app_t *a, ed_t *e) {
    if (e->path[0] == '\0') {
        snprintf(e->msg, sizeof e->msg, "no file name: :w FILE");
        return;
    }
    if (save_to(a, e, e->path) == 0) {
        e->changed = 0;
    }
}

static int say_err(moy_sh_t *s, const char *name, const char *why) {
    char b[160];
    int n = snprintf(b, sizeof b, "edit: %s: %s\n", name, why);
    moy_sh_fd_write(s, 2, b, (size_t)n < sizeof b ? (size_t)n : sizeof b - 1);
    return 1;
}

// `name` (the shell's path) read into the record, the text before freed: NULL,
// or why not (the record as it was). NULL `name`: an empty text with no file.
static const char *ed_load(moy_sh_app_t *a, ed_t *e, const char *name) {
    moy_sh_t *s = moy_sh_app_session(a);
    char path[PATH_CAP] = "";
    ed_sink_t k = { { sink_begin, sink_room, sink_took }, a, { NULL, NULL, 0, NULL, 0 } };
    int rc = ENOENT;
    if (name != NULL) {
        int r = moy_sh_resolve(s, name, path, sizeof path);
        if (r != 0) {
            return r == ENOENT ? "not a file in the store" : strerror(r);
        }
        ed_io_t io = { .path = path, .k = &k.k };
        moy_sh_hop(s, ed_load_here, &io);
        if (io.is_dir) {
            return "is a folder";
        }
        rc = io.rc;
        if (rc != 0) {
            text_free(a, &k.t);
        }
        if (rc != 0 && io.exists) {
            return rc == EFBIG ? "is too big to edit" : rc == ENOMEM ? "out of memory"
                 : rc > 0 ? strerror(rc) : "cannot be read";
        }
    }
    if (k.t.tail != NULL && k.t.tail->n == 0) {
        unlink_blk(a, &k.t, k.t.tail);  // room lent at the end and never read into
    }
    text_free(a, &e->t);
    e->t = k.t;
    e->cur = 0;
    e->want = -1;
    e->top = 0;
    e->changed = 0;
    snprintf(e->path, sizeof e->path, "%s", path);
    const char *base = name != NULL ? strrchr(name, '/') : NULL;
    base = base != NULL && base[1] ? base + 1 : name != NULL ? name : "[no name]";
    snprintf(e->name, sizeof e->name, "%s", base);
    e->fresh = name != NULL && rc != 0;
    snprintf(e->msg, sizeof e->msg, "%s", e->fresh ? "a new file" : "");
    return NULL;
}

static int ed_open(moy_sh_app_t *a, void *st, int argc, char **argv) {
    ed_t *e = st;
    moy_sh_t *s = moy_sh_app_session(a);
    if (argc != 2) {
        moy_sh_fd_write(s, 2, "usage: edit FILE\n", 17);
        return 2;
    }
    const char *why = ed_load(a, e, argv[1]);
    return why != NULL ? say_err(s, argv[1], why) : 0;
}

static void ed_close(moy_sh_app_t *a, void *st) {
    ed_t *e = st;
    text_free(a, &e->t);
}

// -- the screen ---------------------------------------------------------------------

// The cells written from here reversed (`want`) or not, where that is not
// what they are (`on`): what they are then.
static int rev_to(moy_sh_app_t *a, int on, int want) {
    if (on != want) {
        moy_sh_app_write(a, want ? REV : PLAIN);
    }
    return want;
}

// The line at `from` from column `left`, `cols` wide, `$` marking a cut;
// the selection [s0, s1) of the text in reverse video as far as the line
// shows, and its line break, where selected, one reversed cell after it.
static void put_line(moy_sh_app_t *a, const ed_t *e, size_t from, int left, int cols,
                     size_t s0, size_t s1) {
    size_t end = line_end(e, from);
    int width = col_of(e, from, end);
    int cut = width - left > cols - (left > 0);
    int room = cols - (left > 0) - cut;
    if (left > 0) {
        moy_sh_app_write(a, DIM "$" PLAIN);
    }
    int col = 0, shown = 0, kept = 0, rev = 0;
    for (size_t i = from; i < end; i++) {
        char c = at(e, i);
        if (cont(c)) {
            if (kept) {
                moy_sh_app_writen(a, &c, 1);
            }
            continue;
        }
        int nx = advance(col, c), sel = i >= s0 && i < s1;
        kept = 0;
        if (c == '\t') {
            for (int k = col; k < nx; k++) {
                if (k >= left && shown < room) {
                    rev = rev_to(a, rev, sel);
                    moy_sh_app_write(a, " ");
                    shown++;
                }
            }
        } else if (col >= left && shown < room) {
            rev = rev_to(a, rev, sel);
            moy_sh_app_writen(a, &c, 1);
            shown++;
            kept = 1;
        }
        col = nx;
    }
    if (end >= s0 && end < s1 && col >= left && shown < room) {
        rev = rev_to(a, rev, 1);
        moy_sh_app_write(a, " ");
    }
    rev_to(a, rev, 0);
    if (cut) {
        moy_sh_app_write(a, DIM "$" PLAIN);
    }
}

static void ed_draw(moy_sh_app_t *a, void *st) {
    ed_t *e = st;
    int cols, rows;
    moy_sh_app_size(a, &cols, &rows);
    int h = rows - 2;
    int ln = line_of(e, e->cur);
    if (ln < e->top) {
        e->top = ln;
    } else if (ln >= e->top + h) {
        e->top = ln - h + 1;
    }
    char b[MSG_CAP + 64];
    moy_sh_app_write(a, "\x1b[0m\x1b[2J\x1b[H");
    moy_sh_app_write(a, TITLE);
    snprintf(b, sizeof b, "edit %s%s", e->name, e->changed ? " *" : "");
    moy_sh_app_clip(a, b, cols);
    moy_sh_app_write(a, PLAIN);
    size_t p = start_of_line(e, e->top), n = len(e);
    size_t cur = line_start(e, e->cur);
    int ccol = col_of(e, cur, e->cur);
    int left = ccol >= cols - 1 ? ccol - cols / 2 : 0;
    for (int r = 0; r < h && (p < n || r == 0 || at(e, p - 1) == '\n'); r++) {
        snprintf(b, sizeof b, "\x1b[%d;1H", r + 2);
        moy_sh_app_write(a, b);
        put_line(a, e, p, p == cur ? left : 0, cols, 0, 0);
        p = line_end(e, p);
        if (p >= n) {
            break;
        }
        p++;
    }
    snprintf(b, sizeof b, "\x1b[%d;1H" DIM, rows);
    moy_sh_app_write(a, b);
    if (e->ask) {
        moy_sh_app_write(a, TITLE);
        moy_sh_app_clip(a, "Save the changes? y yes, n no", cols);
    } else if (e->msg[0]) {
        moy_sh_app_clip(a, e->msg, cols);
    } else if (moy_sh_app_ctrl(a)) {
        moy_sh_app_clip(a, "^S save  ^X exit", cols);
    }
    char where[24];
    int wn = snprintf(where, sizeof where, "  %d/%d", ln + 1, lines(e));
    if (wn > 0 && wn < cols) {
        snprintf(b, sizeof b, "\x1b[%d;%dH%s", rows, cols - wn + 1, where);
        moy_sh_app_write(a, b);
    }
    snprintf(b, sizeof b, PLAIN "\x1b[%d;%dH", ln - e->top + 2, ccol - left + 1 + (left > 0));
    moy_sh_app_write(a, b);
}

// -- the keys -----------------------------------------------------------------------

static int ed_keys(moy_sh_app_t *a, void *st, const char *p, size_t n) {
    ed_t *e = st;
    const char *end = p + n;
    int cols, rows;
    moy_sh_app_size(a, &cols, &rows);
    int k;
    while ((k = moy_sh_app_key(&p, end)) >= 0) {
        if (e->ask) {
            e->ask = 0;
            if (k == 'y' || k == 'Y' || k == '\r') {
                save(a, e);
                if (!e->changed) {
                    return MOY_SH_APP_END;
                }
            } else if (k == 'n' || k == 'N') {
                return MOY_SH_APP_END;
            }
            continue;
        }
        e->msg[0] = 0;
        int vert = 0;
        switch (k) {
            case CTRL('s'):
                save(a, e);
                break;
            case CTRL('x'):
            case CTRL('c'):
            case 0x1b:
                if (!e->changed) {
                    return MOY_SH_APP_END;
                }
                e->ask = 1;
                break;
            case '\r':
            case '\n':
                insert(a, e, '\n');
                break;
            case 0x08:
            case 0x7F:
                back_char(a, e);
                break;
            case MOY_SH_KEY_DEL:
                del_char(a, e);
                break;
            case MOY_SH_KEY_LEFT:
                if (e->cur > 0) {
                    size_t q = e->cur - 1;
                    while (q > 0 && cont(at(e, q))) {
                        q--;
                    }
                    move_to(e, q);
                }
                break;
            case MOY_SH_KEY_RIGHT:
                if (e->cur < len(e)) {
                    size_t q = e->cur + 1;
                    while (q < len(e) && cont(at(e, q))) {
                        q++;
                    }
                    move_to(e, q);
                }
                break;
            case MOY_SH_KEY_UP:
            case MOY_SH_KEY_DOWN:
                vertical(e, k == MOY_SH_KEY_UP ? -1 : 1);
                vert = 1;
                break;
            case MOY_SH_KEY_PGUP:
            case MOY_SH_KEY_PGDN:
                vertical(e, (k == MOY_SH_KEY_PGUP ? -1 : 1) * (rows > 3 ? rows - 3 : 1));
                vert = 1;
                break;
            case MOY_SH_KEY_HOME:
                move_to(e, line_start(e, e->cur));
                break;
            case MOY_SH_KEY_END:
                move_to(e, line_end(e, e->cur));
                break;
            default:
                if (k == '\t' || (k >= 0x20 && k < 0x100 && k != 0x7F)) {
                    insert(a, e, (char)k);
                }
                break;
        }
        if (!vert) {
            e->want = -1;
        }
    }
    ed_draw(a, e);
    return MOY_SH_APP_GO;
}

static const char *const ED_KEYS[] = {"Save", "\x13", "Exit", "\x18", NULL};

const moy_sh_app_ops_t moy_sh_edit_app = {
    .name = "edit",
    .state = sizeof(ed_t),
    .full = 1,
    .text = 1,
    .keys = ED_KEYS,
    .open = ed_open,
    .keys_in = ed_keys,
    .draw = ed_draw,
    .close = ed_close,
};

// -- vi ------------------------------------------------------------------------------
//
// `vi FILE` and `vim FILE`: a modal editor over this file's blocks, its load
// and its crash-safe save; `view`, `less` and `more` are the same read-only, q
// leaving and the space bar and b paging.
//
//   NORMAL  counts; h j k l and the arrows, w b e, 0 ^ $, gg G NG, Ctrl-F Ctrl-B
//           Ctrl-D Ctrl-U; x X D dd dw de db d$ d0, yy Y yw y$, cc cw c$ C s S;
//           p P J r ~; i a I A o O; u and Ctrl-R; .; / ? n N; ZZ ZQ; v V
//   VISUAL  v charwise, V linewise: NORMAL's motions and counts, / ? n N, move
//           the cursor, the selection's free end; o O the other end; d x, y,
//           c s, J, ~ u U over the selection, D X, Y, C S R over its lines;
//           v V to leave or change kind, Esc and : leave
//   INSERT  the text; Enter, Backspace, Tab, the arrows; Esc back
//   :       w [FILE], q, q!, wq, x, e[!] FILE, N, $, set nu, set nonu
//
// One undo step (the text before the last change, swapped back and forth by u
// and Ctrl-R) and one register, each a block list as the text is: what a heap
// without PSRAM holds beside the text.
//
// A VISUAL selection runs from where v or V was typed to the cursor, the
// character at its later end included (V: their lines, the last one's break
// included; `$` puts the cursor on its line's break, as vim's does). It draws
// in reverse video (SGR 7) as far as each line shows, a selected line break
// as one cell. An operator over it is one change, one undo step, and puts
// the selection in the register (V's as lines, put as dd's are); `.`
// repeats no VISUAL change. view, less and more have no VISUAL: their
// register is put nowhere.

enum { VI_NORMAL, VI_INSERT, VI_LINE };

static int vi_last(const ed_t *e) {
    int n = lines(e) - 1;
    size_t l = len(e);
    if (n > 0 && l > 0 && at(e, l - 1) == '\n') {
        n--;                            // a final newline ends the last line
    }
    return n;
}

static size_t vi_nonblank(const ed_t *e, size_t s) {
    size_t t = line_end(e, s);
    while (s < t && (at(e, s) == ' ' || at(e, s) == '\t')) {
        s++;
    }
    return s;
}

static void vi_goto(ed_t *e, int ln) {
    int last = vi_last(e);
    ln = ln < 0 ? 0 : ln > last ? last : ln;
    move_to(e, vi_nonblank(e, start_of_line(e, ln)));
}

// In NORMAL the cursor sits on a character, never past a line's last (but
// after VISUAL's `$`, on its break), and never on the line after a final
// newline.
static void vi_clamp(ed_t *e) {
    if (e->mode != VI_NORMAL) {
        return;
    }
    if (line_of(e, e->cur) > vi_last(e)) {
        move_to(e, start_of_line(e, vi_last(e)));
    }
    size_t s = line_start(e, e->cur), t = line_end(e, e->cur);
    if (e->cur >= t && t > s && !e->eol) {
        size_t q = t - 1;
        while (q > s && cont(at(e, q))) {
            q--;
        }
        move_to(e, q);
    }
}

// [from, to) into the register, a text of its own, and with `whole` a
// newline closing it where the lines' last has none. The register before
// stays where there is no memory for this one.
static void vi_setreg(moy_sh_app_t *a, ed_t *e, size_t from, size_t to, int whole) {
    text_t t;
    src_t nl = { "\n", NULL, 0 };
    int ok = text_copy(a, &t, &e->t, from, to);
    if (ok && whole && (to == from || at(e, to - 1) != '\n')) {
        ok = text_ins(a, &t, t.n, &nl, 1);
    }
    if (!ok) {
        text_free(a, &t);
        snprintf(e->msg, sizeof e->msg, "out of memory");
        return;
    }
    text_free(a, &e->reg);
    e->reg = t;
    e->has_reg = 1;
    e->reg_lines = whole;
}

// The text before a change, for u: a copy of it in blocks, and its cursor.
// The step before goes first, so two texts are the most held.
static void vi_snap(moy_sh_app_t *a, ed_t *e) {
    text_free(a, &e->undo);
    e->has_undo = text_copy(a, &e->undo, &e->t, 0, len(e));   // 0: this change has no undo
    e->undo_cur = e->cur;
}

// u and Ctrl-R: the text and the step before it swapped, nothing copied.
static void vi_undo(moy_sh_app_t *a, ed_t *e) {
    (void)a;
    if (!e->has_undo) {
        snprintf(e->msg, sizeof e->msg, "nothing to undo");
        return;
    }
    text_t t = e->t;
    size_t cur = e->cur;
    e->t = e->undo;
    e->cur = e->undo_cur;
    e->undo = t;
    e->undo_cur = cur;
    e->changed = 1;
}

static void vi_del(moy_sh_app_t *a, ed_t *e, size_t from, size_t to) {
    text_del(a, &e->t, from, to);
    move_to(e, from);
    if (to > from) {
        e->changed = 1;
    }
}

static void vi_ins(moy_sh_app_t *a, ed_t *e, const char *t, size_t n) {
    src_t s = { t, NULL, 0 };
    put_in(a, e, &s, n);
}

// The register's first `n` bytes in at the cursor.
static void vi_ins_reg(moy_sh_app_t *a, ed_t *e, size_t n) {
    src_t s = { NULL, &e->reg, 0 };
    put_in(a, e, &s, n);
}

static int vi_cls(char c) {
    unsigned char u = (unsigned char)c;
    if (u == ' ' || u == '\t' || u == '\n') {
        return 0;
    }
    return isalnum(u) || u == '_' || u >= 0x80 ? 1 : 2;
}

static size_t vi_w(const ed_t *e, size_t p) {
    size_t n = len(e);
    if (p >= n) {
        return n;
    }
    int c = vi_cls(at(e, p));
    while (c != 0 && p < n && vi_cls(at(e, p)) == c) {
        p++;
    }
    while (p < n && vi_cls(at(e, p)) == 0) {
        p++;
    }
    return p;
}

static size_t vi_b(const ed_t *e, size_t p) {
    while (p > 0 && vi_cls(at(e, p - 1)) == 0) {
        p--;
    }
    if (p == 0) {
        return 0;
    }
    int c = vi_cls(at(e, p - 1));
    while (p > 0 && vi_cls(at(e, p - 1)) == c) {
        p--;
    }
    return p;
}

static size_t vi_e(const ed_t *e, size_t p) {
    size_t n = len(e);
    if (p + 1 >= n) {
        return p;
    }
    p++;
    while (p < n && vi_cls(at(e, p)) == 0) {
        p++;
    }
    if (p >= n) {
        return n - 1;
    }
    int c = vi_cls(at(e, p));
    while (p + 1 < n && vi_cls(at(e, p + 1)) == c) {
        p++;
    }
    return p;
}

// [from, to) of `count` whole lines from the cursor's, the newline after the
// last included where there is one.
static void vi_lines(const ed_t *e, int count, size_t *from, size_t *to) {
    size_t n = len(e), s = line_start(e, e->cur), t = s;
    for (int k = 0; k < count && t < n; k++) {
        t = line_end(e, t);
        if (t < n) {
            t++;
        }
    }
    *from = s;
    *to = t;
}

static int vi_find(ed_t *e, const char *pat, int dir) {
    size_t n = len(e), m = strlen(pat);
    if (m == 0 || m > n) {
        return 0;
    }
    for (size_t k = 1; k <= n; k++) {
        size_t p = dir > 0 ? (e->cur + k) % n : (e->cur + n - (k % n)) % n;
        if (p + m > n) {
            continue;
        }
        size_t i = 0;
        while (i < m && at(e, p + i) == pat[i]) {
            i++;
        }
        if (i == m) {
            move_to(e, p);
            return 1;
        }
    }
    return 0;
}

static void vi_search(ed_t *e, int dir) {
    if (!e->pat[0]) {
        snprintf(e->msg, sizeof e->msg, "no search yet");
    } else if (!vi_find(e, e->pat, dir)) {
        snprintf(e->msg, sizeof e->msg, "not found: %.60s", e->pat);
    }
}

static int vi_ro(ed_t *e) {
    if (e->vi == 2) {
        snprintf(e->msg, sizeof e->msg, "read-only: q leaves");
        return 1;
    }
    return 0;
}

// The `:` line run: MOY_SH_APP_END to leave.
static int vi_ex(moy_sh_app_t *a, ed_t *e, char *c) {
    while (*c == ' ') {
        c++;
    }
    size_t n = strlen(c);
    while (n > 0 && c[n - 1] == ' ') {
        c[--n] = 0;
    }
    if (n == 0) {
        return MOY_SH_APP_GO;
    }
    if (strcmp(c, "q!") == 0 || strcmp(c, "qa!") == 0) {
        return MOY_SH_APP_END;
    }
    if (strcmp(c, "q") == 0 || strcmp(c, "qa") == 0) {
        if (e->changed && e->vi != 2) {
            snprintf(e->msg, sizeof e->msg, "unsaved changes: :wq saves, :q! leaves them");
            return MOY_SH_APP_GO;
        }
        return MOY_SH_APP_END;
    }
    if (strcmp(c, "w") == 0 || strcmp(c, "wq") == 0 || strcmp(c, "x") == 0) {
        if (vi_ro(e)) {
            return MOY_SH_APP_GO;
        }
        if (c[0] == 'x' && !e->changed) {
            return MOY_SH_APP_END;
        }
        save(a, e);
        if (c[0] == 'w' && c[1] == '\0') {
            return MOY_SH_APP_GO;
        }
        return e->changed ? MOY_SH_APP_GO : MOY_SH_APP_END;
    }
    if (c[0] == 'w' && c[1] == ' ') {
        char path[PATH_CAP];
        const char *name = c + 2;
        while (*name == ' ') {
            name++;
        }
        int r = moy_sh_resolve(moy_sh_app_session(a), name, path, sizeof path);
        if (r != 0) {
            snprintf(e->msg, sizeof e->msg, "%.40s: %s", name, strerror(r));
        } else if (save_to(a, e, path) == 0 && e->path[0] == '\0') {
            snprintf(e->path, sizeof e->path, "%s", path);
            snprintf(e->name, sizeof e->name, "%s", name);
            e->changed = 0;
        }
        return MOY_SH_APP_GO;
    }
    if (c[0] == 'e' && (c[1] == ' ' || (c[1] == '!' && c[2] == ' '))) {
        if (e->changed && c[1] != '!') {
            snprintf(e->msg, sizeof e->msg, "unsaved changes: :e! FILE leaves them");
            return MOY_SH_APP_GO;
        }
        const char *name = c + (c[1] == '!' ? 3 : 2);
        while (*name == ' ') {
            name++;
        }
        const char *why = ed_load(a, e, name);
        if (why != NULL) {
            snprintf(e->msg, sizeof e->msg, "%.40s: %s", name, why);
        } else {
            text_free(a, &e->undo);
            e->has_undo = 0;
        }
        return MOY_SH_APP_GO;
    }
    if (strcmp(c, "set nu") == 0 || strcmp(c, "set number") == 0) {
        e->nu = 1;
        return MOY_SH_APP_GO;
    }
    if (strcmp(c, "set nonu") == 0 || strcmp(c, "set nonumber") == 0) {
        e->nu = 0;
        return MOY_SH_APP_GO;
    }
    if (strcmp(c, "$") == 0) {
        vi_goto(e, vi_last(e));
        return MOY_SH_APP_GO;
    }
    if (isdigit((unsigned char)c[0])) {
        vi_goto(e, atoi(c) - 1);
        return MOY_SH_APP_GO;
    }
    snprintf(e->msg, sizeof e->msg, "not a command: %.60s", c);
    return MOY_SH_APP_GO;
}

static int vi_starts_change(int k) {
    return k == 'x' || k == 'X' || k == 'd' || k == 'c' || k == 'p' || k == 'P' || k == 'J'
        || k == 'r' || k == '~' || k == 'o' || k == 'O' || k == 'i' || k == 'a' || k == 'I'
        || k == 'A' || k == 's' || k == 'S' || k == 'C' || k == 'D';
}

// The operator `op` (d, y, c) over [from, to): the register, then the cut.
static void vi_apply(moy_sh_app_t *a, ed_t *e, int op, size_t from, size_t to, int whole) {
    size_t n = len(e);
    to = to > n ? n : to;
    if (to <= from && !whole) {
        if (op == 'c') {
            e->mode = VI_INSERT;
        }
        return;
    }
    vi_setreg(a, e, from, to, whole);
    if (op == 'y') {
        move_to(e, from);
        return;
    }
    if (whole && op == 'c') {
        // cc: the lines' text goes, one empty line stays to type into
        size_t t = to > from && at(e, to - 1) == '\n' ? to - 1 : to;
        vi_del(a, e, from, t);
        e->mode = VI_INSERT;
        return;
    }
    if (whole && op == 'd' && to >= n && from > 0) {
        from--;                         // the last lines: the newline before them goes too
    }
    vi_del(a, e, from, to);
    if (op == 'c') {
        e->mode = VI_INSERT;
    } else if (whole) {
        size_t here = e->cur < len(e) ? e->cur : len(e);
        move_to(e, vi_nonblank(e, line_start(e, here)));
    }
}

static void vi_put(moy_sh_app_t *a, ed_t *e, int after, int count) {
    if (!e->has_reg) {
        snprintf(e->msg, sizeof e->msg, "nothing yanked");
        return;
    }
    if (e->reg_lines) {
        size_t n = len(e), s;
        if (!after) {
            move_to(e, line_start(e, e->cur));
        } else {
            size_t t = line_end(e, e->cur);
            if (t < n) {
                move_to(e, t + 1);
            } else {
                // after the last line, which has no newline: one goes first
                move_to(e, t);
                vi_ins(a, e, "\n", 1);
                s = e->cur;
                for (int k = 0; k < count; k++) {
                    vi_ins_reg(a, e, k + 1 < count ? e->reg.n : e->reg.n - 1);
                }
                move_to(e, vi_nonblank(e, s));
                return;
            }
        }
        s = e->cur;
        for (int k = 0; k < count; k++) {
            vi_ins_reg(a, e, e->reg.n);
        }
        move_to(e, vi_nonblank(e, s));
        return;
    }
    if (after && e->cur < line_end(e, e->cur)) {
        move_to(e, e->cur + 1);
    }
    for (int k = 0; k < count; k++) {
        vi_ins_reg(a, e, e->reg.n);
    }
    if (e->cur > 0) {
        move_to(e, e->cur - 1);
    }
}

static void vi_join(moy_sh_app_t *a, ed_t *e, int count) {
    for (int k = 0; k < (count > 1 ? count - 1 : 1); k++) {
        size_t t = line_end(e, e->cur), n = len(e);
        if (t >= n) {
            break;
        }
        size_t u = t + 1;
        while (u < n && (at(e, u) == ' ' || at(e, u) == '\t')) {
            u++;
        }
        int space = t > line_start(e, t) && at(e, t - 1) != ' ' && u < n && at(e, u) != '\n';
        vi_del(a, e, t, u);
        if (space) {
            vi_ins(a, e, " ", 1);
            move_to(e, e->cur - 1);
        }
    }
}

// The letters of [from, to) in place: `how` 'u' lower, 'U' upper, '~' each
// the other way.
static void vi_case(ed_t *e, size_t from, size_t to, int how) {
    while (from < to) {
        size_t off;
        blk_t *b = seek(&e->t, from, &off);
        for (; off < b->n && from < to; off++, from++) {
            int c = (unsigned char)b->d[off];
            int d = how == 'u' || (how == '~' && isupper(c)) ? tolower(c) : toupper(c);
            if (d != c) {
                b->d[off] = (char)d;
                e->changed = 1;
            }
        }
    }
}

// The VISUAL selection: [*from, *to) of the text, from its earlier end to
// past the character at its later one (V: their lines, with the last one's
// break).
static void vi_sel(const ed_t *e, size_t *from, size_t *to) {
    size_t n = len(e), lo = e->anchor, hi = e->cur;
    if (hi < lo) {
        lo = e->cur;
        hi = e->anchor;
    }
    if (e->vis == 'V') {
        lo = line_start(e, lo);
        hi = line_end(e, hi);
    }
    if (hi < n) {
        hi++;
        while (hi < n && cont(at(e, hi))) {
            hi++;
        }
    }
    *from = lo;
    *to = hi;
}

// VISUAL's operator `k` over the selection, which ends: d x delete, y yanks,
// c s change, J joins its lines, ~ u U turn its letters; D X, Y and C S R
// do so to its whole lines. A change is one undo step and no `.`.
static void vi_vop(moy_sh_app_t *a, ed_t *e, int k) {
    int whole = e->vis == 'V' || strchr("DXYCSR", k) != NULL;
    int op = strchr("xXD", k) != NULL ? 'd' : k == 'Y' ? 'y' : strchr("sCSR", k) != NULL ? 'c' : k;
    size_t from, to, lo = e->anchor < e->cur ? e->anchor : e->cur;
    e->vis = whole ? 'V' : 'v';
    vi_sel(e, &from, &to);
    e->vis = e->eol = e->count = 0;
    if (op != 'y') {
        vi_snap(a, e);
        e->dot_n = 0;
    }
    if (op == 'J') {
        int n = to > from ? line_of(e, to - 1) - line_of(e, from) + 1 : 1;
        move_to(e, from);
        vi_join(a, e, n < 2 ? 2 : n);
    } else if (op == '~' || op == 'u' || op == 'U') {
        vi_case(e, from, to, op);
        move_to(e, lo);
    } else {
        vi_apply(a, e, op, from, to, whole);
        if (op == 'y') {
            move_to(e, lo);
        }
    }
}

#define VI_VERT (-2)                    // a vertical move: the column aimed at stays
#define VI_COUNT_MAX 99999              // a count's ceiling, its further digits dropped
#define VI_DOT (-3)                     // `.`: the caller replays the last change

// One key in NORMAL: MOY_SH_APP_END to leave.
static int vi_normal(moy_sh_app_t *a, ed_t *e, int k, int rows) {
    int ro = e->vi == 2;
    if (e->op == 'r') {
        e->op = 0;
        int cnt = e->count ? e->count : 1;
        e->count = 0;
        if (k >= 0x20 && k < 0x100 && k != 0x7F) {
            for (int i = 0; i < cnt && e->cur < line_end(e, e->cur); i++) {
                char c = (char)k;
                del_char(a, e);
                vi_ins(a, e, &c, 1);
            }
            if (e->cur > 0) {
                move_to(e, e->cur - 1);
            }
        }
        return MOY_SH_APP_GO;
    }
    if (e->op == 'Z') {
        e->op = 0;
        if (k == 'Q') {
            return MOY_SH_APP_END;
        }
        if (k == 'Z') {
            if (e->changed && !ro) {
                save(a, e);
            }
            return e->changed && !ro ? MOY_SH_APP_GO : MOY_SH_APP_END;
        }
        return MOY_SH_APP_GO;
    }
    if (e->op == 'g') {
        e->op = 0;
        if (k == 'g') {
            vi_goto(e, e->count ? e->count - 1 : 0);
        }
        e->count = 0;
        return MOY_SH_APP_GO;
    }
    if ((k >= '1' && k <= '9') || (k == '0' && e->count > 0)) {
        if (e->count <= (VI_COUNT_MAX - 9) / 10) {
            e->count = e->count * 10 + (k - '0');
        }
        return MOY_SH_APP_GO;
    }
    int cnt = e->count ? e->count : 1;
    if (e->op == 'd' || e->op == 'y' || e->op == 'c') {
        int op = e->op;
        e->op = 0;
        long both = (long)cnt * (e->opcount ? e->opcount : 1);
        cnt = both > VI_COUNT_MAX ? VI_COUNT_MAX : (int)both;
        e->count = e->opcount = 0;
        size_t from = e->cur, to = e->cur;
        if (k == op) {
            vi_lines(e, cnt, &from, &to);
            vi_apply(a, e, op, from, to, 1);
            return MOY_SH_APP_GO;
        }
        switch (k) {
            case 'w':
                if (op == 'c' && vi_cls(at(e, from)) != 0) {
                    for (int i = 0; i < cnt; i++) {
                        to = vi_e(e, to) + (i + 1 < cnt);
                    }
                    to++;
                } else {
                    for (int i = 0; i < cnt; i++) {
                        to = vi_w(e, to);
                    }
                    size_t t = line_end(e, from);
                    to = to > t && t > from ? t : to;
                }
                break;
            case 'e':
                for (int i = 0; i < cnt; i++) {
                    to = vi_e(e, to);
                }
                to++;
                break;
            case 'b':
                for (int i = 0; i < cnt; i++) {
                    from = vi_b(e, from);
                }
                break;
            case '$':
                to = line_end(e, from);
                break;
            case '0':
                from = line_start(e, from);
                break;
            default:
                return MOY_SH_APP_GO;   // not a motion: the operator is dropped
        }
        vi_apply(a, e, op, from, to, 0);
        return MOY_SH_APP_GO;
    }
    int counted = e->count > 0;
    e->count = 0;
    int half = rows > 4 ? (rows - 1) / 2 : 1;
    switch (k) {
        case 'h':
        case MOY_SH_KEY_LEFT:
        case 0x08:
        case 0x7F:
            for (int i = 0; i < cnt && e->cur > line_start(e, e->cur); i++) {
                size_t q = e->cur - 1;
                while (q > 0 && cont(at(e, q))) {
                    q--;
                }
                move_to(e, q);
            }
            return MOY_SH_APP_GO;
        case ' ':                       // a page in view and less, l in vi
            if (ro) {
                vertical(e, rows - 2);
                return VI_VERT;
            }
            // fall through
        case 'l':
        case MOY_SH_KEY_RIGHT:
            for (int i = 0; i < cnt && e->cur + 1 < line_end(e, e->cur); i++) {
                size_t q = e->cur + 1;
                while (q < len(e) && cont(at(e, q))) {
                    q++;
                }
                move_to(e, q);
            }
            return MOY_SH_APP_GO;
        case 'j':
        case '+':
        case '\r':
        case MOY_SH_KEY_DOWN:
            vertical(e, cnt);
            if (k == '+' || k == '\r') {
                move_to(e, vi_nonblank(e, line_start(e, e->cur)));
                return MOY_SH_APP_GO;
            }
            return VI_VERT;
        case 'k':
        case '-':
        case MOY_SH_KEY_UP:
            vertical(e, -cnt);
            if (k == '-') {
                move_to(e, vi_nonblank(e, line_start(e, e->cur)));
                return MOY_SH_APP_GO;
            }
            return VI_VERT;
        case 'w':
            for (int i = 0; i < cnt; i++) {
                move_to(e, vi_w(e, e->cur));
            }
            return MOY_SH_APP_GO;
        case 'b':
            if (ro) {
                vertical(e, -(rows - 2));
                return VI_VERT;
            }
            for (int i = 0; i < cnt; i++) {
                move_to(e, vi_b(e, e->cur));
            }
            return MOY_SH_APP_GO;
        case 'e':
            for (int i = 0; i < cnt; i++) {
                move_to(e, vi_e(e, e->cur));
            }
            return MOY_SH_APP_GO;
        case '0':
        case MOY_SH_KEY_HOME:
            move_to(e, line_start(e, e->cur));
            return MOY_SH_APP_GO;
        case '^':
            move_to(e, vi_nonblank(e, line_start(e, e->cur)));
            return MOY_SH_APP_GO;
        case '$':
        case MOY_SH_KEY_END:
            move_to(e, line_end(e, e->cur));
            return MOY_SH_APP_GO;
        case 'G':
            vi_goto(e, counted ? cnt - 1 : vi_last(e));
            return MOY_SH_APP_GO;
        case 'g':
        case 'Z':
            e->op = k;
            e->count = counted ? cnt : 0;
            return MOY_SH_APP_GO;
        case 'r':
            if (!vi_ro(e)) {
                e->op = k;
                e->count = counted ? cnt : 0;
            }
            return MOY_SH_APP_GO;
        case 0x06:                      // Ctrl-F
        case MOY_SH_KEY_PGDN:
            vertical(e, rows - 2);
            return VI_VERT;
        case 'f':
            if (ro) {
                vertical(e, rows - 2);
                return VI_VERT;
            }
            return MOY_SH_APP_GO;
        case 0x02:                      // Ctrl-B
        case MOY_SH_KEY_PGUP:
            vertical(e, -(rows - 2));
            return VI_VERT;
        case 0x04:                      // Ctrl-D
            vertical(e, half);
            return VI_VERT;
        case 0x15:                      // Ctrl-U
            vertical(e, -half);
            return VI_VERT;
        case 'q':
            return ro ? MOY_SH_APP_END : MOY_SH_APP_GO;
        case ':':
        case '/':
        case '?':
            e->mode = VI_LINE;
            e->line_kind = (char)k;
            e->line_n = 0;
            e->line[0] = 0;
            return MOY_SH_APP_GO;
        case 'n':
        case 'N':
            vi_search(e, k == 'n' ? e->pat_dir : -e->pat_dir);
            return MOY_SH_APP_GO;
        case 'u':
        case 0x12:                      // Ctrl-R: the one step back again
            if (!vi_ro(e)) {
                vi_undo(a, e);
            }
            return MOY_SH_APP_GO;
        case '.':
            return !vi_ro(e) && e->dot_n > 0 && !e->replaying ? VI_DOT : MOY_SH_APP_GO;
        default:
            break;
    }
    if (ro) {
        if (vi_starts_change(k) || k == 'y' || k == 'Y') {
            vi_ro(e);
        }
        return MOY_SH_APP_GO;
    }
    switch (k) {
        case 'd':
        case 'y':
        case 'c':
            e->op = k;
            e->opcount = cnt;
            break;
        case 'x':
        case 'X': {
            size_t s = line_start(e, e->cur), t = line_end(e, e->cur);
            size_t from = e->cur, to = e->cur;
            if (k == 'x') {
                to = from + (size_t)cnt < t ? from + (size_t)cnt : t;
            } else {
                from = e->cur > s + (size_t)cnt ? e->cur - (size_t)cnt : s;
            }
            vi_apply(a, e, 'd', from, to, 0);
            break;
        }
        case 'D':
        case 'C':
            vi_apply(a, e, k == 'D' ? 'd' : 'c', e->cur, line_end(e, e->cur), 0);
            break;
        case 's': {
            size_t t = line_end(e, e->cur);
            vi_apply(a, e, 'c', e->cur, e->cur + (size_t)cnt < t ? e->cur + (size_t)cnt : t, 0);
            break;
        }
        case 'S':
        case 'Y': {
            size_t from, to;
            vi_lines(e, cnt, &from, &to);
            vi_apply(a, e, k == 'S' ? 'c' : 'y', from, to, 1);
            break;
        }
        case 'p':
        case 'P':
            vi_put(a, e, k == 'p', cnt);
            break;
        case 'J':
            vi_join(a, e, cnt);
            break;
        case '~': {
            size_t t = line_end(e, e->cur), q = e->cur;
            for (int i = 0; i < cnt && q < t; i++) {
                while (++q < t && cont(at(e, q))) {
                }
            }
            vi_case(e, e->cur, q, '~');
            move_to(e, q);
            break;
        }
        case 'v':
        case 'V':
            e->vis = k;
            e->anchor = e->cur;
            break;
        case 'i':
            e->mode = VI_INSERT;
            break;
        case 'a':
            if (e->cur < line_end(e, e->cur)) {
                move_to(e, e->cur + 1);
            }
            e->mode = VI_INSERT;
            break;
        case 'I':
            move_to(e, vi_nonblank(e, line_start(e, e->cur)));
            e->mode = VI_INSERT;
            break;
        case 'A':
            move_to(e, line_end(e, e->cur));
            e->mode = VI_INSERT;
            break;
        case 'o':
            move_to(e, line_end(e, e->cur));
            vi_ins(a, e, "\n", 1);
            e->mode = VI_INSERT;
            break;
        case 'O': {
            size_t s = line_start(e, e->cur);
            move_to(e, s);
            vi_ins(a, e, "\n", 1);
            move_to(e, s);
            e->mode = VI_INSERT;
            break;
        }
        default:
            break;
    }
    return MOY_SH_APP_GO;
}

// One key in VISUAL: NORMAL's motions move the cursor, the selection's free
// end; an operator acts on the selection; the keys that change the text in
// NORMAL and are not VISUAL's do nothing.
static int vi_visual(moy_sh_app_t *a, ed_t *e, int k, int rows) {
    if (e->op != 0 || (k >= '1' && k <= '9') || (k == '0' && e->count > 0)) {
        return vi_normal(a, e, k, rows);    // a prefix's second key, a count's digit
    }
    e->eol = k == '$' || k == MOY_SH_KEY_END;
    if (k > 0 && k < 0x80 && strchr("vVoOdxXDyYcsCSRJ~uUpPriaIA.\x12", k) != NULL) {
        if (k == 'v' || k == 'V') {
            e->vis = e->vis == k ? 0 : k;
        } else if (k == 'o' || k == 'O') {
            size_t t = e->anchor;
            e->anchor = e->cur;
            move_to(e, t);
        } else if (strchr("pPriaIA.\x12", k) == NULL) {
            vi_vop(a, e, k);
        }
        e->count = 0;
        return MOY_SH_APP_GO;
    }
    if (k == ':') {
        e->vis = 0;                     // the `:` line takes no range
    }
    return vi_normal(a, e, k, rows);
}

// One key in INSERT.
static void vi_insert(moy_sh_app_t *a, ed_t *e, int k) {
    switch (k) {
        case 0x1b:
            e->mode = VI_NORMAL;
            if (e->cur > line_start(e, e->cur)) {
                move_to(e, e->cur - 1);
            }
            break;
        case '\r':
        case '\n':
            vi_ins(a, e, "\n", 1);
            break;
        case 0x08:
        case 0x7F:
            back_char(a, e);
            break;
        case MOY_SH_KEY_DEL:
            del_char(a, e);
            break;
        case MOY_SH_KEY_LEFT:
            if (e->cur > 0) {
                move_to(e, e->cur - 1);
            }
            break;
        case MOY_SH_KEY_RIGHT:
            if (e->cur < len(e)) {
                move_to(e, e->cur + 1);
            }
            break;
        case MOY_SH_KEY_UP:
        case MOY_SH_KEY_DOWN:
            vertical(e, k == MOY_SH_KEY_UP ? -1 : 1);
            break;
        default:
            if (k == '\t' || (k >= 0x20 && k < 0x100 && k != 0x7F)) {
                insert(a, e, (char)k);
            }
            break;
    }
}

// One key in the `:`, `/` or `?` line: MOY_SH_APP_END to leave.
static int vi_line_key(moy_sh_app_t *a, ed_t *e, int k) {
    if (k == 0x1b || ((k == 0x08 || k == 0x7F) && e->line_n == 0)) {
        e->mode = VI_NORMAL;
        return MOY_SH_APP_GO;
    }
    if (k == 0x08 || k == 0x7F) {
        e->line[--e->line_n] = 0;
        return MOY_SH_APP_GO;
    }
    if (k == '\r' || k == '\n') {
        e->mode = VI_NORMAL;
        if (e->line_kind == ':') {
            return vi_ex(a, e, e->line);
        }
        if (e->line_n > 0) {
            snprintf(e->pat, sizeof e->pat, "%s", e->line);
        }
        e->pat_dir = e->line_kind == '/' ? 1 : -1;
        vi_search(e, e->pat_dir);
        return MOY_SH_APP_GO;
    }
    if (k >= 0x20 && k < 0x100 && k != 0x7F && e->line_n + 1 < sizeof e->line) {
        e->line[e->line_n++] = (char)k;
        e->line[e->line_n] = 0;
    }
    return MOY_SH_APP_GO;
}

#define VI_REC ((int)(sizeof ((ed_t *)0)->rec / sizeof ((ed_t *)0)->rec[0]))

// One key, whatever the mode; the change it starts recorded for `.`.
static int vi_key(moy_sh_app_t *a, ed_t *e, int k, int rows) {
    if (e->mode == VI_NORMAL && e->op == 0 && !e->replaying && e->vi != 2 && !e->vis
            && vi_starts_change(k)) {
        vi_snap(a, e);
        e->recording = 1;
        e->rec_n = 0;
        if (e->count > 0) {
            char d[8];
            int m = snprintf(d, sizeof d, "%d", e->count);
            for (int i = 0; i < m && e->rec_n < VI_REC; i++) {
                e->rec[e->rec_n++] = d[i];
            }
        }
    }
    if (e->recording) {
        if (e->rec_n < VI_REC) {
            e->rec[e->rec_n++] = k;
        } else {
            e->recording = 0;           // too long to keep whole: `.` repeats nothing
            e->dot_n = 0;
        }
    }
    int r = MOY_SH_APP_GO;
    if (e->mode == VI_INSERT) {
        vi_insert(a, e, k);
    } else if (e->mode == VI_LINE) {
        r = vi_line_key(a, e, k);
    } else if (k == 0x1b) {
        e->op = 0;
        e->count = e->opcount = 0;
        e->vis = e->eol = 0;
    } else if (e->vis) {
        r = vi_visual(a, e, k, rows);
    } else {
        r = vi_normal(a, e, k, rows);
    }
    if (r == VI_DOT) {
        e->replaying = 1;
        vi_snap(a, e);
        for (int i = 0; i < e->dot_n; i++) {
            vi_key(a, e, e->dot[i], rows);
        }
        e->replaying = 0;
        r = MOY_SH_APP_GO;
    }
    if (e->recording && e->mode == VI_NORMAL && e->op == 0) {
        memcpy(e->dot, e->rec, sizeof e->rec[0] * (size_t)e->rec_n);
        e->dot_n = e->rec_n;
        e->recording = 0;
    }
    if (r == VI_VERT) {
        r = MOY_SH_APP_GO;
    } else {
        e->want = -1;
    }
    vi_clamp(e);
    return r;
}

static void vi_draw(moy_sh_app_t *a, void *st) {
    ed_t *e = st;
    int cols, rows;
    moy_sh_app_size(a, &cols, &rows);
    int h = rows - 1;
    int ln = line_of(e, e->cur);
    if (ln < e->top) {
        e->top = ln;
    } else if (ln >= e->top + h) {
        e->top = ln - h + 1;
    }
    int pad = e->nu ? 4 : 0;
    int tcols = cols - pad > 8 ? cols - pad : cols;
    char b[MSG_CAP + 64];
    moy_sh_app_write(a, "\x1b[0m\x1b[2J\x1b[H");
    size_t p = start_of_line(e, e->top), n = len(e);
    size_t cur = line_start(e, e->cur);
    int ccol = col_of(e, cur, e->cur);
    int left = ccol >= tcols - 1 ? ccol - tcols / 2 : 0;
    int last = vi_last(e);
    size_t s0 = 0, s1 = 0;
    if (e->vis) {
        vi_sel(e, &s0, &s1);
    }
    for (int r = 0; r < h; r++) {
        snprintf(b, sizeof b, "\x1b[%d;1H", r + 1);
        moy_sh_app_write(a, b);
        int lnr = e->top + r;
        if (lnr > last) {
            moy_sh_app_write(a, DIM "~" PLAIN);
            continue;
        }
        if (pad) {
            snprintf(b, sizeof b, DIM "%3d " PLAIN, lnr + 1);
            moy_sh_app_write(a, b);
        }
        put_line(a, e, p, p == cur ? left : 0, tcols, s0, s1);
        p = line_end(e, p);
        if (p < n) {
            p++;
        }
    }
    snprintf(b, sizeof b, "\x1b[%d;1H", rows);
    moy_sh_app_write(a, b);
    if (e->mode == VI_LINE) {
        moy_sh_app_writen(a, &e->line_kind, 1);
        moy_sh_app_writen(a, e->line, e->line_n);
    } else if (e->msg[0]) {
        moy_sh_app_clip(a, e->msg, cols - 16);
    } else if (e->mode == VI_INSERT || e->vis) {
        moy_sh_app_write(a, TITLE);
        moy_sh_app_write(a, e->mode == VI_INSERT ? "-- INSERT --" PLAIN
                            : e->vis == 'V' ? "-- VISUAL LINE --" PLAIN : "-- VISUAL --" PLAIN);
    } else {
        snprintf(b, sizeof b, "\"%s\"%s%s", e->name, e->changed ? " [+]" : "",
                 e->vi == 2 ? " [read-only]" : "");
        moy_sh_app_write(a, DIM);
        moy_sh_app_clip(a, b, cols - 16);
        moy_sh_app_write(a, PLAIN);
    }
    char where[24];
    int wn = snprintf(where, sizeof where, "%d,%d", ln + 1, ccol + 1);
    if (wn > 0 && wn + 2 < cols && e->mode != VI_LINE) {
        snprintf(b, sizeof b, "\x1b[%d;%dH" DIM "%s" PLAIN, rows, cols - wn, where);
        moy_sh_app_write(a, b);
    }
    if (e->mode == VI_LINE) {
        snprintf(b, sizeof b, "\x1b[%d;%dH", rows, (int)e->line_n + 2);
    } else {
        snprintf(b, sizeof b, "\x1b[%d;%dH", ln - e->top + 1, pad + ccol - left + 1 + (left > 0));
    }
    moy_sh_app_write(a, b);
}

static int vi_keys(moy_sh_app_t *a, void *st, const char *p, size_t n) {
    ed_t *e = st;
    const char *end = p + n;
    int cols, rows;
    moy_sh_app_size(a, &cols, &rows);
    int k;
    while ((k = moy_sh_app_key(&p, end)) >= 0) {
        if (e->mode != VI_LINE) {
            e->msg[0] = 0;
        }
        if (vi_key(a, e, k, rows) == MOY_SH_APP_END) {
            return MOY_SH_APP_END;
        }
    }
    vi_draw(a, e);
    return MOY_SH_APP_GO;
}

static int vi_open(moy_sh_app_t *a, void *st, int argc, char **argv) {
    ed_t *e = st;
    moy_sh_t *s = moy_sh_app_session(a);
    int ro = strcmp(argv[0], "view") == 0 || strcmp(argv[0], "less") == 0
          || strcmp(argv[0], "more") == 0;
    if (argc > 2 || (ro && argc != 2)) {
        char b[48];
        int m = snprintf(b, sizeof b, "usage: %s %s\n", argv[0], ro ? "FILE" : "[FILE]");
        moy_sh_fd_write(s, 2, b, (size_t)m < sizeof b ? (size_t)m : sizeof b - 1);
        return 2;
    }
    const char *why = ed_load(a, e, argc == 2 ? argv[1] : NULL);
    if (why == NULL && ro && e->fresh) {
        why = "not a file in the store";   // a pager reads what is there
        ed_close(a, e);                     // an open that fails is not closed
    }
    if (why != NULL) {
        char b[160];
        int m = snprintf(b, sizeof b, "%s: %s: %s\n", argv[0], argc == 2 ? argv[1] : "", why);
        moy_sh_fd_write(s, 2, b, (size_t)m < sizeof b ? (size_t)m : sizeof b - 1);
        return 1;
    }
    e->vi = ro ? 2 : 1;
    e->mode = VI_NORMAL;
    e->pat_dir = 1;
    vi_clamp(e);
    return 0;
}

static void vi_close(moy_sh_app_t *a, void *st) {
    ed_t *e = st;
    text_free(a, &e->reg);
    text_free(a, &e->undo);
    e->has_reg = e->has_undo = 0;
    ed_close(a, st);
}

// The key row a face draws for a console with no Esc key (the T-Deck's
// keyboard, a touch screen): Esc, and :w and :q typed from whatever mode.
static const char *const VI_KEYS[] = {"Esc", "\x1b", "Save", "\x1b:w\r", "Quit", "\x1b:q\r", NULL};
static const char *const VI_RO_KEYS[] = {"Quit", "\x1bq", NULL};

#define VI_APP(nm, k) { .name = nm, .state = sizeof(ed_t), .full = 1, .text = 1, .keys = k, \
                        .open = vi_open, .keys_in = vi_keys, .draw = vi_draw, .close = vi_close }
const moy_sh_app_ops_t moy_sh_vi_app = VI_APP("vi", VI_KEYS);
const moy_sh_app_ops_t moy_sh_vim_app = VI_APP("vim", VI_KEYS);
const moy_sh_app_ops_t moy_sh_view_app = VI_APP("view", VI_RO_KEYS);
const moy_sh_app_ops_t moy_sh_less_app = VI_APP("less", VI_RO_KEYS);
const moy_sh_app_ops_t moy_sh_more_app = VI_APP("more", VI_RO_KEYS);
