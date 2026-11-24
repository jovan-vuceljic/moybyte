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
// (native/moy_store/moy_fs.h's moy_fs_publish), as `settings set` writes.
//
// THE TEXT is a gap buffer from the host table's alloc (PSRAM on a board),
// at most EDIT_MAX bytes; a file that does not exist opens empty and is made
// at the first save.

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "moy_fs.h"
#include "moy_sh_app.h"

#define EDIT_MAX (256u * 1024u)
#define PATH_CAP 512
#define NAME_CAP 48
#define MSG_CAP 80
#define TAB 8
#define GROW 1024u
#define TITLE "\x1b[0;36m"
#define DIM "\x1b[2m"
#define PLAIN "\x1b[0m"
#define CTRL(c) ((c) & 0x1F)

typedef struct {
    char path[PATH_CAP];                // the store's path
    char name[NAME_CAP];                // as the title shows it
    char *buf;
    size_t cap, g0, g1;                 // the gap: [g0, g1), the cursor at g0
    int changed;
    int fresh;                          // the file was not there: a new one
    int ask;                            // the close's question is up
    int top;                            // the first line shown
    int want;                           // the column up and down aim at, -1 the cursor's
    char msg[MSG_CAP];
    // vi: the same record, with its modes, register and undo
    int vi;                             // 0 edit, 1 vi, 2 read-only (view, less, more)
    int mode;                           // VI_NORMAL, VI_INSERT, VI_LINE
    int count, opcount;                 // the counts typed before a command, before its motion
    int op;                             // the operator or prefix waiting for its next key
    char line[MSG_CAP];                 // the `:`, `/` or `?` line being typed
    size_t line_n;
    char line_kind;
    char pat[MSG_CAP];                  // the last search
    int pat_dir;
    char *reg;                          // the register: what was yanked or deleted
    size_t reg_n;
    int reg_lines;                      // whole lines
    char *undo;                         // the text before the last change, a gap buffer
    size_t undo_cap, undo_g0, undo_g1;  // as `buf`, so u swaps the two and copies nothing
    int nu;                             // :set nu
    int dot[48], rec[48];               // the last change's keys; the one being typed
    int dot_n, rec_n, recording, replaying;
} ed_t;

// -- the text ---------------------------------------------------------------------

static size_t len(const ed_t *e) {
    return e->cap - (e->g1 - e->g0);
}

static char at(const ed_t *e, size_t i) {
    return i < e->g0 ? e->buf[i] : e->buf[i + (e->g1 - e->g0)];
}

static void move_to(ed_t *e, size_t pos) {
    if (pos < e->g0) {
        size_t k = e->g0 - pos;
        memmove(e->buf + e->g1 - k, e->buf + pos, k);
        e->g0 = pos;
        e->g1 -= k;
    } else if (pos > e->g0) {
        size_t k = pos - e->g0;
        memmove(e->buf + e->g0, e->buf + e->g1, k);
        e->g0 += k;
        e->g1 += k;
    }
}

static int room(moy_sh_app_t *a, ed_t *e, size_t need) {
    if (e->g1 - e->g0 >= need) {
        return 1;
    }
    size_t n = len(e);
    if (n + need > EDIT_MAX) {
        snprintf(e->msg, sizeof e->msg, "the file is at its %u KB", EDIT_MAX / 1024u);
        return 0;
    }
    size_t cap = e->cap + need + GROW;
    char *b = moy_sh_app_alloc(a, cap);
    if (b == NULL) {
        snprintf(e->msg, sizeof e->msg, "out of memory");
        return 0;
    }
    size_t tail = e->cap - e->g1;
    memcpy(b, e->buf, e->g0);
    memcpy(b + cap - tail, e->buf + e->g1, tail);
    moy_sh_app_free(a, e->buf);
    e->buf = b;
    e->g1 = cap - tail;
    e->cap = cap;
    return 1;
}

static void insert(moy_sh_app_t *a, ed_t *e, char c) {
    if (room(a, e, 1)) {
        e->buf[e->g0++] = c;
        e->changed = 1;
    }
}

static int cont(char c) {
    return ((unsigned char)c & 0xC0) == 0x80;
}

static void back_char(ed_t *e) {
    while (e->g0 > 0) {
        char c = e->buf[--e->g0];
        e->changed = 1;
        if (!cont(c)) {
            break;
        }
    }
}

static void del_char(ed_t *e) {
    if (e->g1 < e->cap) {
        e->g1++;
        e->changed = 1;
        while (e->g1 < e->cap && cont(e->buf[e->g1])) {
            e->g1++;
        }
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

static int line_of(const ed_t *e, size_t pos) {
    int n = 0;
    for (size_t i = 0; i < pos; i++) {
        n += at(e, i) == '\n';
    }
    return n;
}

static int lines(const ed_t *e) {
    return line_of(e, len(e)) + 1;
}

static size_t start_of_line(const ed_t *e, int ln) {
    size_t n = len(e), i = 0;
    for (int k = 0; k < ln && i < n; i++) {
        k += at(e, i) == '\n';
    }
    return i;
}

static void vertical(ed_t *e, int d) {
    size_t s = line_start(e, e->g0);
    if (e->want < 0) {
        e->want = col_of(e, s, e->g0);
    }
    int ln = line_of(e, e->g0) + d, last = lines(e) - 1;
    ln = ln < 0 ? 0 : ln > last ? last : ln;
    move_to(e, pos_at(e, start_of_line(e, ln), e->want));
}

// -- the file -----------------------------------------------------------------------

// The file's reads and its save run where the store may be touched (the
// session's hop, moy_sh_hop).
typedef struct {
    const char *path;
    const char *text;
    size_t n;
    moy_buf_t *b;
    int is_dir, exists, rc;
} ed_io_t;

static void ed_save_here(void *arg) {
    ed_io_t *io = arg;
    io->rc = moy_fs_publish(io->path, io->text, io->n);
}

static void ed_load_here(void *arg) {
    ed_io_t *io = arg;
    moy_vol_stat_t vs;
    io->is_dir = moy_fs_stat(io->path, &vs) == 0 && vs.is_dir;
    if (!io->is_dir) {
        io->rc = moy_fs_read(io->path, NULL, io->b);
        io->exists = io->rc == 0 || moy_fs_exists(io->path);
    }
}

// The text into `path` (the file's own, or vi's `:w FILE`): 0 once saved.
static int save_to(moy_sh_app_t *a, ed_t *e, const char *path) {
    size_t n = len(e), tail = e->cap - e->g1;
    char *text = moy_sh_app_alloc(a, n + 1);
    if (text == NULL) {
        snprintf(e->msg, sizeof e->msg, "not saved: out of memory");
        return ENOMEM;
    }
    memcpy(text, e->buf, e->g0);
    memcpy(text + e->g0, e->buf + e->g1, tail);
    if (e->vi && n > 0 && text[n - 1] != '\n') {
        text[n++] = '\n';              // vi ends a file with a newline, as vi does
    }
    ed_io_t io = { .path = path, .text = text, .n = n };
    moy_sh_hop(moy_sh_app_session(a), ed_save_here, &io);
    int rc = io.rc;
    moy_sh_app_free(a, text);
    if (rc != 0) {
        snprintf(e->msg, sizeof e->msg, "not saved: %s", strerror(rc > 0 ? rc : EIO));
        return rc > 0 ? rc : EIO;
    }
    snprintf(e->msg, sizeof e->msg, "saved, %u bytes", (unsigned)n);
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
    moy_buf_t b = {0};
    int rc = ENOENT;
    if (name != NULL) {
        int r = moy_sh_resolve(s, name, path, sizeof path);
        if (r != 0) {
            return r == ENOENT ? "not a file in the store" : strerror(r);
        }
        ed_io_t io = { .path = path, .b = &b };
        moy_sh_hop(s, ed_load_here, &io);
        if (io.is_dir) {
            return "is a folder";
        }
        rc = io.rc;
        if (rc != 0 && io.exists) {
            return rc > 0 ? strerror(rc) : "cannot be read";
        }
    }
    size_t n = rc == 0 ? b.n : 0;
    if (n > EDIT_MAX) {
        moy_buf_free(&b);
        return "is too big to edit";
    }
    size_t cap = n + GROW;
    char *buf = moy_sh_app_alloc(a, cap);
    if (buf == NULL) {
        moy_buf_free(&b);
        return "out of memory";
    }
    if (n) {
        memcpy(buf + cap - n, b.p, n);
    }
    moy_buf_free(&b);
    if (e->buf != NULL) {
        moy_sh_app_free(a, e->buf);
    }
    e->buf = buf;
    e->cap = cap;
    e->g0 = 0;
    e->g1 = cap - n;
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
    moy_sh_app_free(a, e->buf);
    e->buf = NULL;
}

// -- the screen ---------------------------------------------------------------------

static void put_line(moy_sh_app_t *a, const ed_t *e, size_t from, int left, int cols) {
    size_t end = line_end(e, from);
    int width = col_of(e, from, end);
    int cut = width - left > cols - (left > 0);
    int room = cols - (left > 0) - cut;
    if (left > 0) {
        moy_sh_app_write(a, DIM "$" PLAIN);
    }
    int col = 0, shown = 0, kept = 0;
    for (size_t i = from; i < end; i++) {
        char c = at(e, i);
        if (cont(c)) {
            if (kept) {
                moy_sh_app_writen(a, &c, 1);
            }
            continue;
        }
        int nx = advance(col, c);
        kept = 0;
        if (c == '\t') {
            for (int k = col; k < nx; k++) {
                if (k >= left && shown < room) {
                    moy_sh_app_write(a, " ");
                    shown++;
                }
            }
        } else if (col >= left && shown < room) {
            moy_sh_app_writen(a, &c, 1);
            shown++;
            kept = 1;
        }
        col = nx;
    }
    if (cut) {
        moy_sh_app_write(a, DIM "$" PLAIN);
    }
}

static void ed_draw(moy_sh_app_t *a, void *st) {
    ed_t *e = st;
    int cols, rows;
    moy_sh_app_size(a, &cols, &rows);
    int h = rows - 2;
    int ln = line_of(e, e->g0);
    if (ln < e->top) {
        e->top = ln;
    } else if (ln >= e->top + h) {
        e->top = ln - h + 1;
    }
    char b[MSG_CAP + 64];
    moy_sh_app_write(a, "\x1b[0m\x1b[2J\x1b[H" TITLE);
    snprintf(b, sizeof b, "edit %s%s", e->name, e->changed ? " *" : "");
    moy_sh_app_clip(a, b, cols);
    moy_sh_app_write(a, PLAIN);
    size_t p = start_of_line(e, e->top), n = len(e);
    size_t cur = line_start(e, e->g0);
    int ccol = col_of(e, cur, e->g0);
    int left = ccol >= cols - 1 ? ccol - cols / 2 : 0;
    for (int r = 0; r < h && (p < n || r == 0 || at(e, p - 1) == '\n'); r++) {
        snprintf(b, sizeof b, "\x1b[%d;1H", r + 2);
        moy_sh_app_write(a, b);
        put_line(a, e, p, p == cur ? left : 0, cols);
        p = line_end(e, p);
        if (p >= n) {
            break;
        }
        p++;
    }
    snprintf(b, sizeof b, "\x1b[%d;1H" DIM, rows);
    moy_sh_app_write(a, b);
    if (e->ask) {
        moy_sh_app_write(a, PLAIN TITLE);
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
                back_char(e);
                break;
            case MOY_SH_KEY_DEL:
                del_char(e);
                break;
            case MOY_SH_KEY_LEFT:
                if (e->g0 > 0) {
                    size_t q = e->g0 - 1;
                    while (q > 0 && cont(at(e, q))) {
                        q--;
                    }
                    move_to(e, q);
                }
                break;
            case MOY_SH_KEY_RIGHT:
                if (e->g1 < e->cap) {
                    size_t q = e->g0 + 1;
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
                move_to(e, line_start(e, e->g0));
                break;
            case MOY_SH_KEY_END:
                move_to(e, line_end(e, e->g0));
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
// `vi FILE` and `vim FILE`: a modal editor over this file's gap buffer, its load
// and its crash-safe save; `view`, `less` and `more` are the same read-only, q
// leaving and the space bar and b paging.
//
//   NORMAL  counts; h j k l and the arrows, w b e, 0 ^ $, gg G NG, Ctrl-F Ctrl-B
//           Ctrl-D Ctrl-U; x X D dd dw de db d$ d0, yy Y yw y$, cc cw c$ C s S;
//           p P J r ~; i a I A o O; u and Ctrl-R; .; / ? n N; ZZ ZQ
//   INSERT  the text; Enter, Backspace, Tab, the arrows; Esc back
//   :       w [FILE], q, q!, wq, x, e[!] FILE, N, $, set nu, set nonu
//
// One undo step (the text before the last change, swapped back and forth by u
// and Ctrl-R) and one register: what a heap without PSRAM holds beside the text.

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

// In NORMAL the cursor sits on a character, never past a line's last, and
// never on the line after a final newline.
static void vi_clamp(ed_t *e) {
    if (e->mode != VI_NORMAL) {
        return;
    }
    if (line_of(e, e->g0) > vi_last(e)) {
        move_to(e, start_of_line(e, vi_last(e)));
    }
    size_t s = line_start(e, e->g0), t = line_end(e, e->g0);
    if (e->g0 >= t && t > s) {
        size_t q = t - 1;
        while (q > s && cont(at(e, q))) {
            q--;
        }
        move_to(e, q);
    }
}

static char *vi_text(moy_sh_app_t *a, const ed_t *e, size_t from, size_t to) {
    char *t = moy_sh_app_alloc(a, to - from + 2);
    if (t == NULL) {
        return NULL;
    }
    for (size_t i = from; i < to; i++) {
        t[i - from] = at(e, i);
    }
    t[to - from] = 0;
    return t;
}

static void vi_setreg(moy_sh_app_t *a, ed_t *e, size_t from, size_t to, int whole) {
    char *t = vi_text(a, e, from, to);
    if (t == NULL) {
        snprintf(e->msg, sizeof e->msg, "out of memory");
        return;
    }
    size_t n = to - from;
    if (whole && (n == 0 || t[n - 1] != '\n')) {
        t[n++] = '\n';
        t[n] = 0;
    }
    if (e->reg != NULL) {
        moy_sh_app_free(a, e->reg);
    }
    e->reg = t;
    e->reg_n = n;
    e->reg_lines = whole;
}

// The text before a change, for u: a gap buffer like the text's, its gap at
// the cursor. The step before goes first, so two texts are the most held.
static void vi_snap(moy_sh_app_t *a, ed_t *e) {
    if (e->undo != NULL) {
        moy_sh_app_free(a, e->undo);
        e->undo = NULL;
    }
    size_t n = len(e), cap = n + GROW, tail = e->cap - e->g1;
    char *t = moy_sh_app_alloc(a, cap);
    if (t == NULL) {
        return;                         // this change has no undo
    }
    memcpy(t, e->buf, e->g0);
    memcpy(t + cap - tail, e->buf + e->g1, tail);
    e->undo = t;
    e->undo_cap = cap;
    e->undo_g0 = e->g0;
    e->undo_g1 = cap - tail;
}

// u and Ctrl-R: the text and the step before it swapped, nothing copied.
static void vi_undo(moy_sh_app_t *a, ed_t *e) {
    (void)a;
    if (e->undo == NULL) {
        snprintf(e->msg, sizeof e->msg, "nothing to undo");
        return;
    }
    char *b = e->buf;
    size_t cap = e->cap, g0 = e->g0, g1 = e->g1;
    e->buf = e->undo;
    e->cap = e->undo_cap;
    e->g0 = e->undo_g0;
    e->g1 = e->undo_g1;
    e->undo = b;
    e->undo_cap = cap;
    e->undo_g0 = g0;
    e->undo_g1 = g1;
    e->changed = 1;
}

static void vi_del(ed_t *e, size_t from, size_t to) {
    move_to(e, from);
    e->g1 += to - from;
    if (to > from) {
        e->changed = 1;
    }
}

static void vi_ins(moy_sh_app_t *a, ed_t *e, const char *t, size_t n) {
    if (n > 0 && room(a, e, n)) {
        memcpy(e->buf + e->g0, t, n);
        e->g0 += n;
        e->changed = 1;
    }
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
    size_t n = len(e), s = line_start(e, e->g0), t = s;
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
        size_t p = dir > 0 ? (e->g0 + k) % n : (e->g0 + n - (k % n)) % n;
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
        } else if (e->undo != NULL) {
            moy_sh_app_free(a, e->undo);
            e->undo = NULL;
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
        vi_del(e, from, t);
        e->mode = VI_INSERT;
        return;
    }
    if (whole && op == 'd' && to >= n && from > 0) {
        from--;                         // the last lines: the newline before them goes too
    }
    vi_del(e, from, to);
    if (op == 'c') {
        e->mode = VI_INSERT;
    } else if (whole) {
        size_t here = e->g0 < len(e) ? e->g0 : len(e);
        move_to(e, vi_nonblank(e, line_start(e, here)));
    }
}

static void vi_put(moy_sh_app_t *a, ed_t *e, int after, int count) {
    if (e->reg == NULL) {
        snprintf(e->msg, sizeof e->msg, "nothing yanked");
        return;
    }
    if (e->reg_lines) {
        size_t n = len(e), s;
        if (!after) {
            move_to(e, line_start(e, e->g0));
        } else {
            size_t t = line_end(e, e->g0);
            if (t < n) {
                move_to(e, t + 1);
            } else {
                // after the last line, which has no newline: one goes first
                move_to(e, t);
                vi_ins(a, e, "\n", 1);
                s = e->g0;
                for (int k = 0; k < count; k++) {
                    vi_ins(a, e, e->reg, k + 1 < count ? e->reg_n : e->reg_n - 1);
                }
                move_to(e, vi_nonblank(e, s));
                return;
            }
        }
        s = e->g0;
        for (int k = 0; k < count; k++) {
            vi_ins(a, e, e->reg, e->reg_n);
        }
        move_to(e, vi_nonblank(e, s));
        return;
    }
    if (after && e->g0 < line_end(e, e->g0)) {
        move_to(e, e->g0 + 1);
    }
    for (int k = 0; k < count; k++) {
        vi_ins(a, e, e->reg, e->reg_n);
    }
    if (e->g0 > 0) {
        move_to(e, e->g0 - 1);
    }
}

static void vi_join(moy_sh_app_t *a, ed_t *e, int count) {
    for (int k = 0; k < (count > 1 ? count - 1 : 1); k++) {
        size_t t = line_end(e, e->g0), n = len(e);
        if (t >= n) {
            break;
        }
        size_t u = t + 1;
        while (u < n && (at(e, u) == ' ' || at(e, u) == '\t')) {
            u++;
        }
        int space = t > line_start(e, t) && at(e, t - 1) != ' ' && u < n && at(e, u) != '\n';
        vi_del(e, t, u);
        if (space) {
            vi_ins(a, e, " ", 1);
            move_to(e, e->g0 - 1);
        }
    }
}

#define VI_VERT (-2)                    // a vertical move: the column aimed at stays
#define VI_DOT (-3)                     // `.`: the caller replays the last change

// One key in NORMAL: MOY_SH_APP_END to leave.
static int vi_normal(moy_sh_app_t *a, ed_t *e, int k, int rows) {
    int ro = e->vi == 2;
    if (e->op == 'r') {
        e->op = 0;
        int cnt = e->count ? e->count : 1;
        e->count = 0;
        if (k >= 0x20 && k < 0x100 && k != 0x7F) {
            for (int i = 0; i < cnt && e->g0 < line_end(e, e->g0); i++) {
                char c = (char)k;
                del_char(e);
                vi_ins(a, e, &c, 1);
            }
            if (e->g0 > 0) {
                move_to(e, e->g0 - 1);
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
        e->count = e->count * 10 + (k - '0');
        return MOY_SH_APP_GO;
    }
    int cnt = e->count ? e->count : 1;
    if (e->op == 'd' || e->op == 'y' || e->op == 'c') {
        int op = e->op;
        e->op = 0;
        cnt *= e->opcount ? e->opcount : 1;
        e->count = e->opcount = 0;
        size_t from = e->g0, to = e->g0;
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
            for (int i = 0; i < cnt && e->g0 > line_start(e, e->g0); i++) {
                size_t q = e->g0 - 1;
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
            for (int i = 0; i < cnt && e->g0 + 1 < line_end(e, e->g0); i++) {
                size_t q = e->g0 + 1;
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
                move_to(e, vi_nonblank(e, line_start(e, e->g0)));
                return MOY_SH_APP_GO;
            }
            return VI_VERT;
        case 'k':
        case '-':
        case MOY_SH_KEY_UP:
            vertical(e, -cnt);
            if (k == '-') {
                move_to(e, vi_nonblank(e, line_start(e, e->g0)));
                return MOY_SH_APP_GO;
            }
            return VI_VERT;
        case 'w':
            for (int i = 0; i < cnt; i++) {
                move_to(e, vi_w(e, e->g0));
            }
            return MOY_SH_APP_GO;
        case 'b':
            if (ro) {
                vertical(e, -(rows - 2));
                return VI_VERT;
            }
            for (int i = 0; i < cnt; i++) {
                move_to(e, vi_b(e, e->g0));
            }
            return MOY_SH_APP_GO;
        case 'e':
            for (int i = 0; i < cnt; i++) {
                move_to(e, vi_e(e, e->g0));
            }
            return MOY_SH_APP_GO;
        case '0':
        case MOY_SH_KEY_HOME:
            move_to(e, line_start(e, e->g0));
            return MOY_SH_APP_GO;
        case '^':
            move_to(e, vi_nonblank(e, line_start(e, e->g0)));
            return MOY_SH_APP_GO;
        case '$':
        case MOY_SH_KEY_END:
            move_to(e, line_end(e, e->g0));
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
            size_t s = line_start(e, e->g0), t = line_end(e, e->g0);
            size_t from = e->g0, to = e->g0;
            if (k == 'x') {
                to = from + (size_t)cnt < t ? from + (size_t)cnt : t;
            } else {
                from = e->g0 > s + (size_t)cnt ? e->g0 - (size_t)cnt : s;
            }
            vi_apply(a, e, 'd', from, to, 0);
            break;
        }
        case 'D':
        case 'C':
            vi_apply(a, e, k == 'D' ? 'd' : 'c', e->g0, line_end(e, e->g0), 0);
            break;
        case 's': {
            size_t t = line_end(e, e->g0);
            vi_apply(a, e, 'c', e->g0, e->g0 + (size_t)cnt < t ? e->g0 + (size_t)cnt : t, 0);
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
        case '~':
            for (int i = 0; i < cnt && e->g0 < line_end(e, e->g0); i++) {
                char c = at(e, e->g0);
                char t = isupper((unsigned char)c) ? (char)tolower((unsigned char)c)
                       : (char)toupper((unsigned char)c);
                del_char(e);
                vi_ins(a, e, &t, 1);
            }
            break;
        case 'i':
            e->mode = VI_INSERT;
            break;
        case 'a':
            if (e->g0 < line_end(e, e->g0)) {
                move_to(e, e->g0 + 1);
            }
            e->mode = VI_INSERT;
            break;
        case 'I':
            move_to(e, vi_nonblank(e, line_start(e, e->g0)));
            e->mode = VI_INSERT;
            break;
        case 'A':
            move_to(e, line_end(e, e->g0));
            e->mode = VI_INSERT;
            break;
        case 'o':
            move_to(e, line_end(e, e->g0));
            vi_ins(a, e, "\n", 1);
            e->mode = VI_INSERT;
            break;
        case 'O': {
            size_t s = line_start(e, e->g0);
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

// One key in INSERT.
static void vi_insert(moy_sh_app_t *a, ed_t *e, int k) {
    switch (k) {
        case 0x1b:
            e->mode = VI_NORMAL;
            if (e->g0 > line_start(e, e->g0)) {
                move_to(e, e->g0 - 1);
            }
            break;
        case '\r':
        case '\n':
            vi_ins(a, e, "\n", 1);
            break;
        case 0x08:
        case 0x7F:
            back_char(e);
            break;
        case MOY_SH_KEY_DEL:
            del_char(e);
            break;
        case MOY_SH_KEY_LEFT:
            if (e->g0 > 0) {
                move_to(e, e->g0 - 1);
            }
            break;
        case MOY_SH_KEY_RIGHT:
            if (e->g0 < len(e)) {
                move_to(e, e->g0 + 1);
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
    if (e->mode == VI_NORMAL && e->op == 0 && !e->replaying && e->vi != 2
            && vi_starts_change(k)) {
        vi_snap(a, e);
        e->recording = 1;
        e->rec_n = 0;
        if (e->count > 0 && e->count < 100000) {
            char d[8];
            int m = snprintf(d, sizeof d, "%d", e->count);
            for (int i = 0; i < m && e->rec_n < VI_REC; i++) {
                e->rec[e->rec_n++] = d[i];
            }
        }
    }
    if (e->recording && e->rec_n < VI_REC) {
        e->rec[e->rec_n++] = k;
    }
    int r = MOY_SH_APP_GO;
    if (e->mode == VI_INSERT) {
        vi_insert(a, e, k);
    } else if (e->mode == VI_LINE) {
        r = vi_line_key(a, e, k);
    } else if (k == 0x1b) {
        e->op = 0;
        e->count = e->opcount = 0;
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
    int ln = line_of(e, e->g0);
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
    size_t cur = line_start(e, e->g0);
    int ccol = col_of(e, cur, e->g0);
    int left = ccol >= tcols - 1 ? ccol - tcols / 2 : 0;
    int last = vi_last(e);
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
        put_line(a, e, p, p == cur ? left : 0, tcols);
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
    } else if (e->mode == VI_INSERT) {
        moy_sh_app_write(a, TITLE "-- INSERT --" PLAIN);
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
    if (e->reg != NULL) {
        moy_sh_app_free(a, e->reg);
        e->reg = NULL;
    }
    if (e->undo != NULL) {
        moy_sh_app_free(a, e->undo);
        e->undo = NULL;
    }
    ed_close(a, st);
}

#define VI_APP(nm) { .name = nm, .state = sizeof(ed_t), .full = 1, .text = 1, .keys = NULL, \
                     .open = vi_open, .keys_in = vi_keys, .draw = vi_draw, .close = vi_close }
const moy_sh_app_ops_t moy_sh_vi_app = VI_APP("vi");
const moy_sh_app_ops_t moy_sh_vim_app = VI_APP("vim");
const moy_sh_app_ops_t moy_sh_view_app = VI_APP("view");
const moy_sh_app_ops_t moy_sh_less_app = VI_APP("less");
const moy_sh_app_ops_t moy_sh_more_app = VI_APP("more");
