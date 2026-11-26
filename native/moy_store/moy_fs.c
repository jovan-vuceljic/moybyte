// The store's crash-safe write (moy_fs.h has the contract; runtime/carts/moy_fs.py's
// header has the story every branch below follows).

#include <stdio.h>
#include <string.h>

#include "moy_fs.h"

#define STAMP "#moyfs1 "
#define STAMP_LEN 8u
#define PUBLISH "/.publish"
#define HEAD_MAX 1100u      // the longest marker or stamp line read

enum { MARK_UNREAD = 0, MARK_NONE = 1, MARK_SET = 2 };

typedef struct {
    char *root;             // keep-allocated, len + 1
    size_t len;
    uint8_t state;
    char *mpath;            // the marker's path while MARK_SET: mcap bytes, kept
    size_t mlen, mcap;
    uint32_t chars, crc;
} root_t;

static root_t *roots;       // MOY_FS_ROOTS entries, longest root first
static int nroots;

// -- small things --------------------------------------------------------------

static const uint32_t crc_nib[16] = {
    0x00000000u, 0x1db71064u, 0x3b6e20c8u, 0x26d930acu, 0x76dc4190u,
    0x6b6b51f4u, 0x4db26158u, 0x5005713cu, 0xedb88320u, 0xf00f9344u,
    0xd6d6a3e8u, 0xcb61b38cu, 0x9b64c2b0u, 0x86d3d2d4u, 0xa00ae278u,
    0xbdbdf21cu,
};

uint32_t moy_fs_crc32(uint32_t crc, const void *p, size_t n) {
    const uint8_t *b = p;
    crc = ~crc;
    while (n--) {
        crc ^= *b++;
        crc = (crc >> 4) ^ crc_nib[crc & 15u];
        crc = (crc >> 4) ^ crc_nib[crc & 15u];
    }
    return ~crc;
}

void moy_fs_stamp(const char *data, size_t n, uint32_t *chars, uint32_t *crc) {
    uint32_t c = 0;
    for (size_t i = 0; i < n; i++) {
        c += ((uint8_t)data[i] & 0xc0u) != 0x80u;
    }
    *chars = c;
    *crc = moy_fs_crc32(0, data, n);
}

static int fits(const char *p, size_t n, uint32_t chars, uint32_t crc) {
    uint32_t c, k;
    moy_fs_stamp(p, n, &c, &k);
    return c == chars && k == crc;
}

// A stamp taken a piece at a time: the bytes, the code points, the crc32.
typedef struct {
    size_t n;
    uint32_t chars, crc;
} sum_t;

static void sum_add(sum_t *s, const char *p, size_t n) {
    for (size_t i = 0; i < n; i++) {
        s->chars += ((uint8_t)p[i] & 0xc0u) != 0x80u;
    }
    s->crc = moy_fs_crc32(s->crc, p, n);
    s->n += n;
}

void moy_buf_free(moy_buf_t *b) {
    if (b->p != NULL) {
        moy_store_free(b->p, b->n + 1u);
    }
    b->p = NULL;
    b->n = 0;
}

// `a` and `b` joined, scratch: NULL when there is no memory.
static char *join(const char *a, size_t an, const char *b, size_t *out_n) {
    size_t bn = strlen(b), n = an + bn + 1u;
    char *s = moy_store_alloc(n);
    if (s != NULL) {
        memcpy(s, a, an);
        memcpy(s + an, b, bn);
        *out_n = n;
    }
    return s;
}

// A decimal number that fits 32 bits, the whole of [p, p + n).
static int number(const char *p, size_t n, uint32_t *out) {
    uint64_t v = 0;
    if (n == 0 || n > 10) {
        return 0;
    }
    for (size_t i = 0; i < n; i++) {
        if (p[i] < '0' || p[i] > '9') {
            return 0;
        }
        v = v * 10u + (uint64_t)(p[i] - '0');
    }
    if (v > 0xffffffffu) {
        return 0;
    }
    *out = (uint32_t)v;
    return 1;
}

// "#moyfs1 <chars> <crc>\n" -- `line` is `n` bytes, the newline included.
static int parse_stamp(const char *line, size_t n, uint32_t *chars,
                       uint32_t *crc) {
    if (n < STAMP_LEN + 1u || memcmp(line, STAMP, STAMP_LEN) != 0
        || line[n - 1u] != '\n') {
        return 0;
    }
    const char *p = line + STAMP_LEN, *end = line + n - 1u;
    const char *sp = memchr(p, ' ', (size_t)(end - p));
    if (sp == NULL || memchr(sp + 1, ' ', (size_t)(end - sp - 1)) != NULL) {
        return 0;
    }
    return number(p, (size_t)(sp - p), chars)
           && number(sp + 1, (size_t)(end - sp - 1), crc);
}

// "#moyfs1 <chars> <crc> <path>\n": the path is the rest, never empty.
static int parse_mark(const char *line, size_t n, uint32_t *chars,
                      uint32_t *crc, const char **path, size_t *plen) {
    if (n < STAMP_LEN + 1u || memcmp(line, STAMP, STAMP_LEN) != 0
        || line[n - 1u] != '\n') {
        return 0;
    }
    const char *p = line + STAMP_LEN, *end = line + n - 1u;
    const char *s1 = memchr(p, ' ', (size_t)(end - p));
    if (s1 == NULL) {
        return 0;
    }
    const char *s2 = memchr(s1 + 1, ' ', (size_t)(end - s1 - 1));
    if (s2 == NULL || s2 + 1 == end) {
        return 0;
    }
    if (!number(p, (size_t)(s1 - p), chars)
        || !number(s1 + 1, (size_t)(s2 - s1 - 1), crc)) {
        return 0;
    }
    *path = s2 + 1;
    *plen = (size_t)(end - s2 - 1);
    return 1;
}

static int resolve(const char *path, moy_vol_t *v, const char **rest) {
    return moy_vol_at(path, v, rest);
}

// -- the plain verbs --------------------------------------------------------------

int moy_fs_read_file(const char *path, size_t cap, moy_buf_t *out) {
    moy_vol_t v;
    const char *rest;
    out->p = NULL;
    out->n = 0;
    int rc = resolve(path, &v, &rest);
    return rc ? rc : moy_fs_read_vol(&v, rest, cap, out);
}

int moy_fs_read_vol(const moy_vol_t *v, const char *rest, size_t cap,
                    moy_buf_t *out) {
    moy_vol_file_t *f;
    out->p = NULL;
    out->n = 0;
    int rc = moy_vol_open(v, rest, MOY_VOL_READ, &f);
    if (rc != 0) {
        return rc;
    }
    uint32_t size = 0;
    rc = moy_vol_size(f, &size);
    if (rc == 0 && size > cap) {
        rc = MOY_EFBIG;
    }
    size_t want = size, have = 0;
    char *buf = NULL;
    while (rc == 0) {
        char probe = 0;
        if (buf != NULL && have == want) {
            size_t got = 0;         // as long as it said, unless it grew since
            rc = moy_vol_read(f, &probe, 1, &got);
            if (rc != 0 || got == 0) {
                break;
            }
            if (want >= cap) {
                rc = MOY_EFBIG;
                break;
            }
        }
        if (buf == NULL || have == want) {
            size_t grow = buf == NULL ? want : want + 4096u;
            if (buf != NULL && grow < want + 1u) {
                grow = want + 1u;
            }
            if (grow > cap) {
                grow = cap;
            }
            char *nb = moy_store_alloc(grow + 1u);
            if (nb == NULL) {
                rc = MOY_ENOMEM;
                break;
            }
            if (buf != NULL) {
                memcpy(nb, buf, have);
                moy_store_free(buf, want + 1u);
                nb[have++] = probe;
            }
            buf = nb;
            want = grow;
            if (have == want) {
                continue;
            }
        }
        size_t got = 0;
        rc = moy_vol_read(f, buf + have, want - have, &got);
        if (rc != 0 || got == 0) {
            break;
        }
        have += got;
    }
    int crc_ = moy_vol_close(f);
    if (rc == 0) {
        rc = crc_;
    }
    if (rc != 0) {
        if (buf != NULL) {
            moy_store_free(buf, want + 1u);
        }
        return rc;
    }
    if (buf == NULL) {
        buf = moy_store_alloc(1);
        want = 0;
        if (buf == NULL) {
            return MOY_ENOMEM;
        }
    }
    if (have != want) {             // shrink to what was read, so free sizes agree
        char *nb = moy_store_alloc(have + 1u);
        if (nb == NULL) {
            moy_store_free(buf, want + 1u);
            return MOY_ENOMEM;
        }
        memcpy(nb, buf, have);
        moy_store_free(buf, want + 1u);
        buf = nb;
    }
    buf[have] = 0;
    out->p = buf;
    out->n = have;
    return 0;
}

// The file's first line, newline included, or all of a file with none; at
// most HEAD_MAX bytes into `line`.
static int read_head(const char *path, char *line, size_t *n) {
    moy_vol_t v;
    const char *rest;
    moy_vol_file_t *f;
    *n = 0;
    int rc = resolve(path, &v, &rest);
    if (rc == 0) {
        rc = moy_vol_open(&v, rest, MOY_VOL_READ, &f);
    }
    if (rc != 0) {
        return rc;
    }
    size_t have = 0;
    while (have < HEAD_MAX) {
        size_t got = 0;
        rc = moy_vol_read(f, line + have, HEAD_MAX - have, &got);
        if (rc != 0 || got == 0) {
            break;
        }
        const char *nl = memchr(line + have, '\n', got);
        have += got;
        if (nl != NULL) {
            have = (size_t)(nl - line) + 1u;
            break;
        }
    }
    moy_vol_close(f);
    *n = have;
    return rc;
}

// One buffer as a source of one piece (moy_fs_publish_from's).
typedef struct {
    moy_fs_src_t s;
    const char *p;
    size_t n;
    int given;
} flat_t;

static size_t flat_next(moy_fs_src_t *s, const char **p) {
    flat_t *f = (flat_t *)s;
    if (f->given) {
        return 0;
    }
    f->given = 1;
    *p = f->p;
    return f->n;
}

static void flat_rewind(moy_fs_src_t *s) {
    ((flat_t *)s)->given = 0;
}

static flat_t flat(const void *data, size_t n) {
    flat_t f = { { flat_next, flat_rewind }, data, n, 0 };
    return f;
}

// `head` (hn bytes) and then the source's pieces, as the file at `path`.
static int write_src(const char *path, const char *head, size_t hn, moy_fs_src_t *src) {
    moy_vol_t v;
    const char *rest;
    moy_vol_file_t *f;
    int rc = resolve(path, &v, &rest);
    if (rc == 0) {
        rc = moy_vol_open(&v, rest, MOY_VOL_WRITE, &f);
    }
    if (rc != 0) {
        return rc;
    }
    if (hn) {
        rc = moy_vol_write(f, head, hn);
    }
    src->rewind(src);
    const char *p;
    size_t n;
    while (rc == 0 && (n = src->next(src, &p)) != 0) {
        rc = moy_vol_write(f, p, n);
    }
    int crc_ = moy_vol_close(f);
    return rc ? rc : crc_;
}

int moy_fs_write(const char *path, const void *data, size_t n) {
    flat_t f = flat(data, n);
    return write_src(path, NULL, 0, &f.s);
}

int moy_fs_exists(const char *path) {
    moy_vol_t v;
    const char *rest;
    moy_vol_stat_t st;
    return resolve(path, &v, &rest) == 0 && moy_vol_stat(&v, rest, &st) == 0;
}

int moy_fs_stat(const char *path, moy_vol_stat_t *st) {
    moy_vol_t v;
    const char *rest;
    int rc = resolve(path, &v, &rest);
    return rc ? rc : moy_vol_stat(&v, rest, st);
}

int moy_fs_mkdir(const char *path) {
    moy_vol_t v;
    const char *rest;
    int rc = resolve(path, &v, &rest);
    return rc ? rc : moy_vol_mkdir(&v, rest);
}

int moy_fs_remove(const char *path) {
    moy_vol_t v;
    const char *rest;
    int rc = resolve(path, &v, &rest);
    return rc ? rc : moy_vol_remove(&v, rest);
}

// src and dst on one volume, or EXDEV.
static int rename2(const char *src, const char *dst, int replace) {
    moy_vol_t a, b;
    const char *ra, *rb;
    int rc = resolve(src, &a, &ra);
    if (rc == 0) {
        rc = resolve(dst, &b, &rb);
    }
    if (rc != 0) {
        return rc;
    }
    if (a.kind != b.kind || a.fs != b.fs) {
        return MOY_EXDEV;
    }
    return replace ? moy_vol_replace(&a, ra, rb) : moy_vol_rename(&a, ra, rb);
}

int moy_fs_rename(const char *src, const char *dst) {
    return rename2(src, dst, 0);
}

int moy_fs_write_bytes(const char *path, const void *data, size_t n) {
    size_t tn;
    char *tmp = join(path, strlen(path), ".tmp", &tn);
    if (tmp == NULL) {
        return MOY_ENOMEM;
    }
    int rc = moy_fs_write(tmp, data, n);
    if (rc == 0) {
        rc = rename2(tmp, path, 1);
    }
    if (rc != 0) {
        moy_fs_remove(tmp);         // no staging file outlives a refused write
    }
    moy_store_free(tmp, tn);
    return rc;
}

// -- the marker -----------------------------------------------------------------

// The marker's path lives in one block made with its root and grown only for
// a longer path: made again at every save, it was a small block that lasts,
// made while a batch's buffer was live.
#define MARK_PATH_KEEP 160u

static void drop_mark(root_t *r) {
    r->mlen = 0;
}

static void free_mark(root_t *r) {
    if (r->mpath != NULL) {
        moy_store_free(r->mpath, r->mcap);
    }
    r->mpath = NULL;
    r->mlen = r->mcap = 0;
}

static void set_mark(root_t *r, const char *path, size_t plen, uint32_t chars,
                     uint32_t crc) {
    if (plen + 1u > r->mcap) {
        free_mark(r);
        size_t cap = plen + 1u > MARK_PATH_KEEP ? plen + 1u : MARK_PATH_KEEP;
        r->mpath = moy_store_keep(cap);
        if (r->mpath == NULL) {
            r->state = MARK_NONE;
            return;
        }
        r->mcap = cap;
    }
    memcpy(r->mpath, path, plen);
    r->mlen = plen;
    r->chars = chars;
    r->crc = crc;
    r->state = MARK_SET;
}

int moy_fs_root(const char *root) {
    size_t len = strlen(root);
    while (len && root[len - 1u] == '/') {
        len--;
    }
    if (len == 0) {
        return 0;
    }
    if (roots == NULL) {
        roots = moy_store_keep(MOY_FS_ROOTS * sizeof(root_t));
        if (roots == NULL) {
            return MOY_ENOMEM;
        }
    }
    root_t r;
    int at = -1;
    for (int i = 0; i < nroots; i++) {
        if (roots[i].len == len && memcmp(roots[i].root, root, len) == 0) {
            at = i;
            break;
        }
    }
    if (at >= 0) {
        r = roots[at];
        memmove(&roots[at], &roots[at + 1], (size_t)(nroots - at - 1) * sizeof(root_t));
        nroots--;
    } else {
        memset(&r, 0, sizeof r);
        r.root = moy_store_keep(len + 1u);
        if (r.root == NULL) {
            return MOY_ENOMEM;
        }
        memcpy(r.root, root, len);
        r.len = len;
        r.mpath = moy_store_keep(MARK_PATH_KEEP);   // with the root; a save makes none
        r.mcap = r.mpath != NULL ? MARK_PATH_KEEP : 0;
    }
    // The newest goes first, then a stable sort by length, longest first: an
    // insertion at the first root no longer than it.
    int k = 0;
    while (k < nroots && roots[k].len > len) {
        k++;
    }
    if (nroots == MOY_FS_ROOTS) {           // the shortest falls off
        root_t *last = &roots[nroots - 1];
        if (k == nroots) {
            free_mark(&r);
            moy_store_free(r.root, r.len + 1u);
            return 0;
        }
        free_mark(last);
        moy_store_free(last->root, last->len + 1u);
        nroots--;
    }
    memmove(&roots[k + 1], &roots[k], (size_t)(nroots - k) * sizeof(root_t));
    roots[k] = r;
    nroots++;
    return 0;
}

void moy_fs_roots_clear(void) {
    for (int i = 0; i < nroots; i++) {
        free_mark(&roots[i]);
        moy_store_free(roots[i].root, roots[i].len + 1u);
    }
    nroots = 0;
    if (roots != NULL) {
        moy_store_free(roots, MOY_FS_ROOTS * sizeof(root_t));
        roots = NULL;
    }
}

static root_t *root_for(const char *path) {
    size_t n = strlen(path);
    for (int i = 0; i < nroots; i++) {
        root_t *r = &roots[i];
        if (n > r->len && path[r->len] == '/' && memcmp(path, r->root, r->len) == 0) {
            return r;
        }
    }
    return NULL;
}

static void load_mark(root_t *r) {
    if (r->state != MARK_UNREAD) {
        return;
    }
    r->state = MARK_NONE;
    size_t pn;
    char *p = join(r->root, r->len, PUBLISH, &pn);
    char *line = moy_store_alloc(HEAD_MAX);
    size_t n;
    if (p != NULL && line != NULL && read_head(p, line, &n) == 0) {
        uint32_t chars, crc;
        const char *mp;
        size_t ml;
        if (parse_mark(line, n, &chars, &crc, &mp, &ml)) {
            set_mark(r, mp, ml, chars, crc);
        }
    }
    if (line != NULL) {
        moy_store_free(line, HEAD_MAX);
    }
    if (p != NULL) {
        moy_store_free(p, pn);
    }
}

void moy_fs_unmark(const char *path) {
    root_t *r = root_for(path);
    if (r != NULL) {
        drop_mark(r);
        r->state = MARK_NONE;
    }
}

// -- the backup's name -------------------------------------------------------------

size_t moy_fs_bak_into(const char *path, char *out, size_t cap) {
    const char *slash = strrchr(path, '/');
    size_t dn = slash != NULL ? (size_t)(slash - path) + 1u : 0u, pn = strlen(path);
    size_t en = sizeof(MOY_FS_BAK_EXT) - 1u, bn = pn + 1u + en + 1u;
    if (bn <= cap) {
        memcpy(out, path, dn);
        out[dn] = '.';
        memcpy(out + dn + 1u, path + dn, pn - dn);
        memcpy(out + pn + 1u, MOY_FS_BAK_EXT, en + 1u);
    }
    return bn;
}

char *moy_fs_bak_path(const char *path, size_t *n) {
    size_t bn = moy_fs_bak_into(path, NULL, 0);
    char *s = moy_store_alloc(bn);
    if (s != NULL) {
        moy_fs_bak_into(path, s, bn);
        *n = bn;
    }
    return s;
}

int moy_fs_bak_name(const char *name, size_t n) {
    size_t en = sizeof(MOY_FS_BAK_EXT) - 1u;
    return n > en + 1u && name[0] == '.' && memcmp(name + n - en, MOY_FS_BAK_EXT, en) == 0;
}

int moy_fs_bak_stamp(const char *path, uint32_t *chars, uint32_t *crc) {
    size_t bn, n;
    char *bak = moy_fs_bak_path(path, &bn);
    char *line = moy_store_alloc(HEAD_MAX);
    int ok = 0;
    if (bak != NULL && line != NULL && read_head(bak, line, &n) == 0) {
        ok = parse_stamp(line, n, chars, crc);
    }
    if (line != NULL) {
        moy_store_free(line, HEAD_MAX);
    }
    if (bak != NULL) {
        moy_store_free(bak, bn);
    }
    return ok;
}

// What the published `path` should look like: 1 and its stamp, or 0.
static int stamp_for(const char *path, uint32_t *chars, uint32_t *crc) {
    root_t *r = root_for(path);
    if (r == NULL) {
        return moy_fs_bak_stamp(path, chars, crc);
    }
    load_mark(r);
    if (r->state != MARK_SET || r->mlen != strlen(path)
        || memcmp(r->mpath, path, r->mlen) != 0) {
        return 0;
    }
    *chars = r->chars;
    *crc = r->crc;
    return 1;
}

// -- the crash-safe write and its readers ---------------------------------------------

int moy_fs_read_stamped(const char *path, moy_buf_t *out) {
    moy_buf_t b;
    if (moy_fs_read_file(path, (size_t)-1, &b) != 0) {
        return MOY_FS_NONE;
    }
    const char *nl = memchr(b.p, '\n', b.n);
    size_t hn = nl ? (size_t)(nl - b.p) + 1u : b.n;
    uint32_t chars, crc;
    if (!parse_stamp(b.p, hn, &chars, &crc)) {
        if (b.n == 0) {             // made, and the power went before its stamp
            moy_buf_free(&b);
            return MOY_FS_NONE;
        }
        *out = b;                   // legacy: unstamped, whole
        return 0;
    }
    if (!fits(b.p + hn, b.n - hn, chars, crc)) {
        moy_buf_free(&b);
        return MOY_FS_NONE;         // torn: refused, never published
    }
    moy_buf_t r = { moy_store_alloc(b.n - hn + 1u), b.n - hn };
    if (r.p == NULL) {
        moy_buf_free(&b);
        return MOY_ENOMEM;
    }
    memcpy(r.p, b.p + hn, r.n);
    moy_buf_free(&b);
    *out = r;
    return 0;
}

// The backup `bak`'s text as a read takes it: stamped whole with `want`'s
// stamp (NULL: no stamp is expected), or, for a file that is `gone`, the
// store's unstamped copy (the sync's rotation, moy_sync_apply.c).
// MOY_FS_NONE otherwise.
static int take_bak(const char *bak, const uint32_t *want, int gone, moy_buf_t *out) {
    moy_buf_t b;
    if (moy_fs_read_file(bak, (size_t)-1, &b) != 0) {
        return MOY_FS_NONE;
    }
    const char *nl = memchr(b.p, '\n', b.n);
    size_t hn = nl ? (size_t)(nl - b.p) + 1u : b.n;
    uint32_t chars, crc;
    if (!parse_stamp(b.p, hn, &chars, &crc)) {
        if (!gone || b.n == 0) {
            moy_buf_free(&b);
            return MOY_FS_NONE;
        }
        *out = b;
        return 0;
    }
    if (want == NULL || chars != want[0] || crc != want[1]
        || !fits(b.p + hn, b.n - hn, chars, crc)) {
        moy_buf_free(&b);
        return MOY_FS_NONE;         // another save's, or torn
    }
    moy_buf_t r = { moy_store_alloc(b.n - hn + 1u), b.n - hn };
    if (r.p == NULL) {
        moy_buf_free(&b);
        return MOY_ENOMEM;
    }
    memcpy(r.p, b.p + hn, r.n);
    moy_buf_free(&b);
    *out = r;
    return 0;
}

// The save a read of `path` expects (stamp_for), from its backup. `gone`:
// the file could not be read.
static int read_bak(const char *path, moy_buf_t *out, int gone) {
    uint32_t want[2];
    int known = stamp_for(path, &want[0], &want[1]);
    size_t bn;
    char *bak = moy_fs_bak_path(path, &bn);
    if (bak == NULL) {
        return MOY_ENOMEM;
    }
    int rc = take_bak(bak, known ? want : NULL, gone, out);
    moy_store_free(bak, bn);
    return rc;
}

void moy_fs_forget_bak(const char *path) {
    size_t bn;
    char *bak = moy_fs_bak_path(path, &bn);
    if (bak != NULL) {
        moy_fs_remove(bak);
        moy_store_free(bak, bn);
    }
}

// The marker naming `path` and its stamp, best effort (a save whose marker
// cannot be written publishes without detection).
static void mark_publish(const char *path, size_t plen, uint32_t chars, uint32_t crc) {
    root_t *r = root_for(path);
    if (r == NULL) {
        return;
    }
    size_t mn = r->len + sizeof(PUBLISH);
    char *mark = moy_store_alloc(mn);
    char *line = moy_store_alloc(plen + 32u);
    int rc = MOY_ENOMEM;
    if (mark != NULL && line != NULL) {
        memcpy(mark, r->root, r->len);
        memcpy(mark + r->len, PUBLISH, sizeof(PUBLISH));
        int ln = snprintf(line, plen + 32u, STAMP "%lu %lu ",
                          (unsigned long)chars, (unsigned long)crc);
        memcpy(line + ln, path, plen);
        line[ln + (int)plen] = '\n';
        rc = moy_fs_write(mark, line, (size_t)ln + plen + 1u);
    }
    if (line != NULL) {
        moy_store_free(line, plen + 32u);
    }
    if (mark != NULL) {
        moy_store_free(mark, mn);
    }
    if (rc == 0) {
        set_mark(r, path, plen, chars, crc);
    } else {
        drop_mark(r);
        r->state = MARK_NONE;
    }
}

// The stamp of a source's text, a piece at a time.
static void src_stamp(moy_fs_src_t *src, uint32_t *chars, uint32_t *crc) {
    sum_t s = {0};
    const char *p;
    size_t n;
    src->rewind(src);
    while ((n = src->next(src, &p)) != 0) {
        sum_add(&s, p, n);
    }
    *chars = s.chars;
    *crc = s.crc;
}

static int publish_bak(const char *path, moy_fs_src_t *src, uint32_t chars, uint32_t crc) {
    size_t bn;
    char *bak = moy_fs_bak_path(path, &bn);
    if (bak == NULL) {
        return MOY_ENOMEM;
    }
    char head[32];
    int hn = snprintf(head, sizeof head, STAMP "%lu %lu\n",
                      (unsigned long)chars, (unsigned long)crc);
    int rc = write_src(bak, head, (size_t)hn, src);
    if (rc != 0) {
        moy_fs_remove(bak);         // free the half-written backup
    }
    moy_store_free(bak, bn);
    return rc;
}

int moy_fs_publish_bak(const char *path, const char *data, size_t n) {
    uint32_t chars, crc;
    moy_fs_stamp(data, n, &chars, &crc);
    flat_t f = flat(data, n);
    return publish_bak(path, &f.s, chars, crc);
}

int moy_fs_publish_mark(const char *path, const char *data, size_t n) {
    uint32_t chars, crc, c, k;
    moy_fs_stamp(data, n, &chars, &crc);
    if (!moy_fs_bak_stamp(path, &c, &k) || c != chars || k != crc) {
        return moy_fs_publish(path, data, n);
    }
    mark_publish(path, strlen(path), chars, crc);
    return moy_fs_write(path, data, n);
}

// A save that fails on a file that was not there (a full volume's refusal)
// leaves none of it: not the file cut short, not its backup, not the marker
// that names it. One that fails over an older text keeps the scheme's own
// state, whose backup a read heals from.
int moy_fs_publish_from(const char *path, moy_fs_src_t *src) {
    uint32_t chars, crc;
    src_stamp(src, &chars, &crc);
    int was = moy_fs_exists(path);
    mark_publish(path, strlen(path), chars, crc);
    int rc = publish_bak(path, src, chars, crc);
    if (rc == 0) {
        rc = write_src(path, NULL, 0, src);
    }
    if (rc != 0 && !was) {
        moy_fs_remove(path);
        moy_fs_forget_bak(path);
        moy_fs_unmark(path);
    }
    return rc;
}

int moy_fs_publish(const char *path, const char *data, size_t n) {
    flat_t f = flat(data, n);
    return moy_fs_publish_from(path, &f.s);
}

static void heal(const char *path, const moy_buf_t *b) {
    moy_fs_write(path, b->p, b->n);     // best effort
}

int moy_fs_read(const char *path, const char *at, moy_buf_t *out) {
    return moy_fs_read_in(path, NULL, at, out);
}

int moy_fs_read_in(const char *path, moy_vol_here_t *here, const char *name,
                   moy_buf_t *out) {
    int rc;
    if (here != NULL) {
        const char *at = moy_vol_here_name(here, name);
        rc = at == NULL ? MOY_ENOMEM : moy_fs_read_vol(&here->v, at, (size_t)-1, out);
    } else {
        rc = moy_fs_read_file(name != NULL ? name : path, (size_t)-1, out);
    }
    moy_buf_t rec;
    if (rc != 0) {
        if (read_bak(path, &rec, 1) != 0) {
            return rc;              // the original error
        }
        heal(path, &rec);
        *out = rec;
        return 0;
    }
    uint32_t chars, crc;
    if (!stamp_for(path, &chars, &crc) || fits(out->p, out->n, chars, crc)) {
        return 0;
    }
    if (read_bak(path, &rec, 0) != 0) {
        moy_fs_unmark(path);        // a torn backup: keep the file we can read
        return 0;
    }
    if (rec.n >= out->n && memcmp(rec.p, out->p, out->n) == 0) {
        moy_buf_free(out);          // a truncated publish: finish it
        heal(path, &rec);
        *out = rec;
        return 0;
    }
    moy_buf_free(&rec);             // someone else published here
    moy_fs_forget_bak(path);
    moy_fs_unmark(path);
    return 0;
}

// -- the read into the caller's memory ----------------------------------------------
//
// moy_fs_read_in's story, told over files instead of buffers: what it reads
// whole and then checks, this reads in passes, each through the caller's
// memory or PIECE bytes of the stack. The answers and the files left are
// its; the backup is read once more to check it before it is trusted (as
// read_bak checks it before handing it back), and a heal copies it into the
// file before its text is poured, where heal wrote the copy it held.

#define PIECE 128u

static int open_at(const char *path, int mode, moy_vol_file_t **f) {
    moy_vol_t v;
    const char *rest;
    int rc = resolve(path, &v, &rest);
    return rc ? rc : moy_vol_open(&v, rest, mode, f);
}

// `n` bytes of `f`, or as many as it has left in *got.
static int read_full(moy_vol_file_t *f, char *p, size_t n, size_t *got) {
    *got = 0;
    while (*got < n) {
        size_t k = 0;
        int rc = moy_vol_read(f, p + *got, n - *got, &k);
        if (rc != 0) {
            return rc;
        }
        if (k == 0) {
            break;
        }
        *got += k;
    }
    return 0;
}

// The file at `path` from `skip` bytes in, poured into `k` and summed into
// `s`: 0 or an errno value, *refused where the sink refused.
static int pour(const char *path, uint32_t skip, moy_fs_sink_t *k, sum_t *s, int *refused) {
    moy_vol_file_t *f;
    memset(s, 0, sizeof *s);
    *refused = 0;
    int rc = open_at(path, MOY_VOL_READ, &f);
    if (rc != 0) {
        return rc;
    }
    uint32_t size = 0;
    rc = moy_vol_size(f, &size);
    if (rc == 0 && skip) {
        rc = moy_vol_seek(f, skip);
    }
    size_t want = size > skip ? size - skip : 0;
    if (rc == 0) {
        rc = k->begin(k, want);
        *refused = rc != 0;
    }
    while (rc == 0) {
        char probe = 0;
        size_t got = 0, m = 0;
        if (s->n >= want) {         // as long as it said, unless it grew since
            rc = moy_vol_read(f, &probe, 1, &got);
            if (rc != 0 || got == 0) {
                break;
            }
            want = s->n + 4096u;
        }
        char *p = k->room(k, &m);
        if (p == NULL || m == 0) {
            rc = MOY_ENOMEM;
            *refused = 1;
            break;
        }
        if (got) {
            *p = probe;
        } else {
            rc = moy_vol_read(f, p, m < want - s->n ? m : want - s->n, &got);
            if (rc != 0) {
                break;
            }
        }
        sum_add(s, p, got);
        k->took(k, got);
        if (got == 0) {
            break;
        }
    }
    int crc_ = moy_vol_close(f);
    return rc ? rc : crc_;
}

// The backup `bak` as take_bak takes it, read over and never held: 0 and
// where its text starts (*skip: past its stamp line, or 0 for the store's
// unstamped copy of a file that is gone, `cmp` NULL), or MOY_FS_NONE. With
// `cmp`, *same says whether that text starts with the `cmp_n` bytes the file
// `cmp` holds.
static int bak_text(const char *bak, const uint32_t *want, uint32_t *skip,
                    const char *cmp, size_t cmp_n, int *same) {
    char *line = moy_store_alloc(HEAD_MAX);
    if (line == NULL) {
        return MOY_ENOMEM;
    }
    size_t hn = 0;
    uint32_t chars = 0, crc = 0;
    int rc = read_head(bak, line, &hn);
    int stamped = rc == 0 && parse_stamp(line, hn, &chars, &crc);
    moy_store_free(line, HEAD_MAX);
    if (rc != 0 || hn == 0) {
        return MOY_FS_NONE;         // none, or made and the power went before its stamp
    }
    if (!stamped) {
        *skip = 0;
        return cmp == NULL ? 0 : MOY_FS_NONE;
    }
    if (want == NULL || chars != want[0] || crc != want[1]) {
        return MOY_FS_NONE;         // another save's
    }
    *skip = (uint32_t)hn;
    moy_vol_file_t *f, *g = NULL;
    if (open_at(bak, MOY_VOL_READ, &f) != 0) {
        return MOY_FS_NONE;
    }
    rc = *skip ? moy_vol_seek(f, *skip) : 0;
    int differs = cmp == NULL || open_at(cmp, MOY_VOL_READ, &g) != 0;
    sum_t s = {0};
    char a[PIECE], b[PIECE];
    while (rc == 0) {
        size_t got = 0;
        rc = moy_vol_read(f, a, sizeof a, &got);
        if (rc != 0 || got == 0) {
            break;
        }
        if (!differs && s.n < cmp_n) {
            size_t m = cmp_n - s.n < got ? cmp_n - s.n : got, have = 0;
            differs = read_full(g, b, m, &have) != 0 || have != m || memcmp(a, b, m) != 0;
        }
        sum_add(&s, a, got);
    }
    moy_vol_close(f);
    if (g != NULL) {
        moy_vol_close(g);
    }
    if (rc != 0 || s.chars != chars || s.crc != crc) {
        return MOY_FS_NONE;         // torn: refused, never published
    }
    if (cmp != NULL) {
        *same = !differs && s.n >= cmp_n;
    }
    return 0;
}

// heal's copy, from the backup's text: best effort.
static void heal_from(const char *bak, uint32_t skip, const char *path) {
    moy_vol_file_t *f, *h;
    if (open_at(bak, MOY_VOL_READ, &f) != 0) {
        return;
    }
    if ((skip == 0 || moy_vol_seek(f, skip) == 0) && open_at(path, MOY_VOL_WRITE, &h) == 0) {
        char a[PIECE];
        size_t got = 0;
        while (moy_vol_read(f, a, sizeof a, &got) == 0 && got > 0
               && moy_vol_write(h, a, got) == 0) {
        }
        moy_vol_close(h);
    }
    moy_vol_close(f);
}

int moy_fs_read_into(const char *path, moy_fs_sink_t *k) {
    sum_t got;
    int refused, same = 0;
    uint32_t skip = 0;
    int rc = pour(path, 0, k, &got, &refused);
    if (refused) {
        return rc;
    }
    uint32_t want[2];
    int known = stamp_for(path, &want[0], &want[1]);
    if (rc == 0 && (!known || (got.chars == want[0] && got.crc == want[1]))) {
        return 0;
    }
    size_t bn;
    char *bak = moy_fs_bak_path(path, &bn);
    int r = bak == NULL ? MOY_ENOMEM
            : bak_text(bak, known ? want : NULL, &skip, rc ? NULL : path, got.n, &same);
    if (rc != 0 || (r == 0 && same)) {
        // the file cannot be read, or a truncated publish: finish it
        if (r == 0) {
            sum_t s;
            heal_from(bak, skip, path);
            int r2 = pour(bak, skip, k, &s, &refused);
            rc = r2 == 0 || refused || rc == 0 ? r2 : rc;   // else the file's own error
        }
    } else if (r != 0) {
        moy_fs_unmark(path);        // a torn backup: keep the file we can read
    } else {
        moy_fs_forget_bak(path);    // someone else published here
        moy_fs_unmark(path);
    }
    if (bak != NULL) {
        moy_store_free(bak, bn);
    }
    return rc;
}

// Whether `a` and `b` name entries of one folder.
static int same_folder(const char *a, const char *b) {
    const char *sa = strrchr(a, '/'), *sb = strrchr(b, '/');
    size_t na = sa ? (size_t)(sa - a) : 0, nb = sb ? (size_t)(sb - b) : 0;
    return na == nb && memcmp(a, b, na) == 0;
}

int moy_fs_claim(const char *path, const char *dest, uint32_t chars,
                 uint32_t crc) {
    moy_vol_t v;
    const char *rest;
    // littlefs (2.11) cut between the two commits of a rename across folders
    // loses the source folder's other entries -- the live file beside the
    // backup -- so there the claim declines and the caller writes its copy.
    if (resolve(path, &v, &rest) != 0
        || (v.kind == MOY_VOL_KIND_LFS2 && !same_folder(path, dest))) {
        return 0;
    }
    uint32_t c, k;
    if (!moy_fs_bak_stamp(path, &c, &k) || c != chars || k != crc) {
        return 0;
    }
    size_t bn;
    char *bak = moy_fs_bak_path(path, &bn);
    if (bak == NULL) {
        return 0;
    }
    // `dest` is replaced, as os.rename replaces it on every VFS: a
    // snapshot left by a journal line a power cut tore is an orphan.
    int rc = rename2(bak, dest, 1);
    moy_store_free(bak, bn);
    return rc == 0;
}

int moy_store_skip(const char *name, size_t n, int history) {
    // The browser console's pack (the web_console cart's, native/moy_net/moy_page.h)
    // is fetched again by the digest its manifest names, never carried.
    static const char *const dirs[] = { "thumbs", "__pycache__", "moybyte_web.pack",
                                        "journal", "journal.jsonl" };
    for (int i = 0; i < 5; i++) {
        if ((i < 3 || !history) && strlen(dirs[i]) == n && memcmp(name, dirs[i], n) == 0) {
            return 1;
        }
    }
    return moy_fs_bak_name(name, n) || (n >= 4 && memcmp(name + n - 4, ".tmp", 4) == 0);
}
