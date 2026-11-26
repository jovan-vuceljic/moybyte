// The store: declarations, state, the build's calls, events, the trace and
// the dump (moy_uitree.h).
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "moy_uitree_int.h"
#include "moy_kmem.h"

// -- the engine's memory ---------------------------------------------------------
// A block carries the size it was asked for in front of it, which is what
// uit_mem counts. PSRAM first; internal SRAM only when PSRAM has none.

#define UIT_HEAD 8u
#define UIT_PLACE (MOY_KMEM_PSRAM | MOY_KMEM_INTERNAL_OK)

static uint32_t mem_live, mem_peak, mem_blocks;

static void *mem_took(char *b, size_t n)
{
    memcpy(b, &n, sizeof n);
    mem_live += (uint32_t)n;
    mem_blocks++;
    if (mem_live > mem_peak)
        mem_peak = mem_live;
    return b + UIT_HEAD;
}

static size_t mem_size(void *p)
{
    size_t n;
    memcpy(&n, (char *)p - UIT_HEAD, sizeof n);
    return n;
}

void *uit_malloc(size_t n)
{
    char *b = moy_kalloc(n + UIT_HEAD, UIT_PLACE);
    return b ? mem_took(b, n) : NULL;
}

void *uit_realloc(void *p, size_t n)
{
    if (!p)
        return uit_malloc(n);
    size_t was = mem_size(p);
    char *b = moy_krealloc((char *)p - UIT_HEAD, n + UIT_HEAD, UIT_PLACE);
    if (!b)
        return NULL;
    mem_live -= (uint32_t)was;
    mem_blocks--;
    return mem_took(b, n);
}

void uit_mfree(void *p)
{
    if (!p)
        return;
    mem_live -= (uint32_t)mem_size(p);
    mem_blocks--;
    moy_kfree((char *)p - UIT_HEAD);
}

void uit_mem(uint32_t out[3])
{
    out[0] = mem_live;
    out[1] = mem_peak;
    out[2] = mem_blocks;
}

void uit_mem_peak_reset(void)
{
    mem_peak = mem_live;
}

static size_t text_len(const char *s, size_t max)
{
    size_t n = 0;
    while (n < max && s[n])
        n++;
    return n;
}

// -- buffers ------------------------------------------------------------------

static int buf_need(uit_buf_t *b, size_t more)
{
    if (b->n + more + 1 <= b->cap)
        return 0;
    uint32_t cap = b->cap ? b->cap : 256;
    while (cap < b->n + more + 1)
        cap *= 2;
    char *p = UIT_REALLOC(b->p, cap);
    if (!p)
        return -1;
    b->p = p;
    b->cap = cap;
    return 0;
}

int uit_buf_put(uit_buf_t *b, const char *s, size_t n)
{
    if (buf_need(b, n))
        return -1;
    uint32_t at = b->n;
    if (n)
        memcpy(b->p + at, s, n);
    b->p[at + n] = 0;
    b->n = at + (uint32_t)n + 1;
    return (int)at;
}

int uit_buf_puts(uit_buf_t *b, const char *s)
{
    return uit_buf_put(b, s, strlen(s));
}

int uit_buf_printf(uit_buf_t *b, const char *fmt, ...)
{
    va_list ap, ap2;
    va_start(ap, fmt);
    va_copy(ap2, ap);
    int n = vsnprintf(NULL, 0, fmt, ap);
    va_end(ap);
    if (n < 0 || buf_need(b, (size_t)n)) {
        va_end(ap2);
        return -1;
    }
    vsnprintf(b->p + b->n, (size_t)n + 1, fmt, ap2);
    va_end(ap2);
    b->n += (uint32_t)n;
    return n;
}

static void buf_raw(uit_buf_t *b, const char *s, size_t n)
{
    if (buf_need(b, n))
        return;
    memcpy(b->p + b->n, s, n);
    b->n += (uint32_t)n;
    b->p[b->n] = 0;
}

void uit_buf_repr(uit_buf_t *b, const char *s, size_t n)
{
    int sq = memchr(s, '\'', n) != NULL, dq = memchr(s, '"', n) != NULL;
    char q = (sq && !dq) ? '"' : '\'';
    buf_raw(b, &q, 1);
    for (size_t i = 0; i < n; i++) {
        unsigned char ch = (unsigned char)s[i];
        char esc[8];
        if (ch == '\\')
            buf_raw(b, "\\\\", 2);
        else if (ch == (unsigned char)q)
            esc[0] = '\\', esc[1] = (char)q, buf_raw(b, esc, 2);
        else if (ch == '\n')
            buf_raw(b, "\\n", 2);
        else if (ch == '\t')
            buf_raw(b, "\\t", 2);
        else if (ch == '\r')
            buf_raw(b, "\\r", 2);
        else if (ch < 0x20 || ch == 0x7f)
            snprintf(esc, sizeof esc, "\\x%02x", ch), buf_raw(b, esc, 4);
        else
            buf_raw(b, (const char *)&s[i], 1);
    }
    buf_raw(b, &q, 1);
}

void uit_buf_free(uit_buf_t *b)
{
    UIT_FREE(b->p);
    b->p = NULL;
    b->n = b->cap = 0;
}

int uit_grow(void **p, int *cap, int need, size_t size)
{
    if (need <= *cap)
        return 0;
    int c = *cap ? *cap : 16;
    while (c < need)
        c *= 2;
    void *q = UIT_REALLOC(*p, (size_t)c * size);
    if (!q)
        return -1;
    *p = q;
    *cap = c;
    return 0;
}

// The failure's words' buffer: the engine's own, made at its first failure (the
// process's one where none can be made).
static char *err_buf(uit_t *e)
{
    static char none[UIT_ERR];
    if (!e->err)
        e->err = UIT_MALLOC(UIT_ERR);
    return e->err ? e->err : none;
}

int uit_fail(uit_t *e, int code, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(err_buf(e), UIT_ERR, fmt, ap);
    va_end(ap);
    e->code[0] = 0;
    return code;
}

int uit_check_fail(uit_t *e, const char *code, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(err_buf(e), UIT_ERR, fmt, ap);
    va_end(ap);
    memcpy(e->code, code, 3);
    e->code[3] = 0;
    return UIT_E_CHECK;
}

const char *uit_str(const uit_t *e, uint16_t off)
{
    return off == UIT_NONE ? "" : e->pool.p + off;
}

// A page's texts repeat (its props' names, their sources, a label table's words): the pool keeps
// each once while it is declared and built, found by hash through `intern`, made at the first put
// and let go when the build ends (a loaded blob's pool is the compile's, already one copy each).
enum { INTERN = 2048, INTERN_FULL = 1536 };      // past FULL texts a new one is not kept (a copy each)

int uit_pool_put(uit_t *e, const char *s, size_t n)
{
    if (n && memchr(s, 0, n)) {
        // a list of texts (an enum's values, a label table's keys) is kept as it is: its order is
        // a dict's on some Pythons, and a copy shared by chance would make the pool's size so too
        int at = uit_buf_put(&e->pool, s, n);
        return at < 0 || at >= (int)UIT_NONE ? -1 : at;
    }
    if (!e->intern && (e->intern = UIT_MALLOC(INTERN * sizeof *e->intern)) != NULL) {
        memset(e->intern, 0xff, INTERN * sizeof *e->intern);
        e->intern[2166136261u & (INTERN - 1)] = 0;      // the empty text, offset 0 (uit_new)
        e->ninterned = 1;
    }
    uint32_t h = 2166136261u;
    for (size_t i = 0; i < n; i++)
        h = (h ^ (uint8_t)s[i]) * 16777619u;
    uint16_t *slot = NULL;
    for (int i = 0; e->intern && i < INTERN; i++) {
        uint16_t *q = &e->intern[(h + (uint32_t)i) & (INTERN - 1)];
        if (*q == UIT_NONE) {
            slot = q;
            break;
        }
        // an offset a build truncated away, or overwritten since, fails the compare
        if ((size_t)*q + n < e->pool.n && !e->pool.p[*q + n] && !memcmp(e->pool.p + *q, s, n))
            return *q;
    }
    int at = uit_buf_put(&e->pool, s, n);
    if (at < 0 || at >= (int)UIT_NONE)
        return -1;
    if (slot && e->ninterned < INTERN_FULL) {
        *slot = (uint16_t)at;
        e->ninterned++;
    }
    return at;
}

static void intern_drop(uit_t *e)
{
    UIT_FREE(e->intern);
    e->intern = NULL;
    e->ninterned = 0;
}

static int pool_put(uit_t *e, const char *s, size_t n)
{
    return uit_pool_put(e, s, n);
}

static int pool_puts(uit_t *e, const char *s)
{
    return pool_put(e, s, strlen(s));
}

// -- the engine -----------------------------------------------------------------

uit_t *uit_new(void)
{
    uit_t *e = UIT_MALLOC(sizeof *e);
    if (!e)
        return NULL;
    memset(e, 0, sizeof *e);
    uit_buf_put(&e->pool, "", 0);       // offset 0 is the empty text
    e->ccur = -1;
    e->pane_cur = -1;
    e->page_tabs = e->page_tabs_now = -1;
    return e;
}

static void free_drew(uit_t *e)
{
    for (int i = 0; i < e->ndrew; i++) {
        UIT_FREE(e->drew[i].rowkey);
        UIT_FREE(e->drew[i].val);
    }
    e->ndrew = 0;
}

// A block cut to `n` elements (none: freed), its capacity with it.
static void shrink(void **p, int *cap, int n, size_t size)
{
    if (n == *cap)
        return;
    if (n == 0) {
        UIT_FREE(*p);
        *p = NULL;
        *cap = 0;
        return;
    }
    void *q = UIT_REALLOC(*p, (size_t)n * size);
    if (q) {
        *p = q;
        *cap = n;
    }
}
#define UIT_SHRINK(e, arr, n, cap) shrink((void **)&(e)->arr, &(e)->cap, (e)->n, sizeof(*(e)->arr))

static void buf_fit(uit_buf_t *b)
{
    if (!b->p || b->n + 1 >= b->cap)
        return;
    char *p = UIT_REALLOC(b->p, b->n + 1);
    if (p) {
        b->p = p;
        b->cap = b->n + 1;
    }
}

void uit_close(uit_t *e)
{
    e->still_ok = 0;
    e->cells_node = 0;
    e->car_node = 0;
    e->cel_node = 0;
    UIT_FREE(e->car);
    UIT_FREE(e->cel);
    UIT_FREE(e->anc);
    UIT_FREE(e->mcells);
    e->car = e->cel = NULL;
    e->anc = NULL;
    e->mcells = NULL;
    e->nmcells = 0;
    e->nanc = 0;
    for (int i = 0; i < e->nvr; i++)
        UIT_FREE(e->vr[i].h);
    UIT_FREE(e->vr);
    e->vr = NULL;
    e->nvr = e->cvr = 0;
    UIT_FREE(e->rects);
    e->rects = NULL;
    e->crects = 0;
    UIT_FREE(e->arr);
    e->arr = NULL;
    free_drew(e);
    // a slot keeps its value: the front end pushes at the next open only what moved
    for (int i = 0; i < e->nslots; i++) {
        uit_slot_t *S = &e->slots[i];
        UIT_FREE(S->sync);
        S->sync = NULL;
        S->sync_set = 0;
    }
    for (int i = 0; i < e->norders; i++) {
        UIT_FREE(e->orders[i].key);
        UIT_FREE(e->orders[i].keys);
    }
    for (int i = 0; i < e->ndrafts; i++) {
        UIT_FREE(e->drafts[i].key);
        UIT_FREE(e->drafts[i].buf);
    }
    e->norders = e->ndrafts = 0;
    e->nids = e->nprev = e->nevs = e->evat = e->tvl_n = 0;
    e->edits = 0;
    e->tvl_slot = -1;
    UIT_SHRINK(e, orders, norders, corders);
    UIT_SHRINK(e, drafts, ndrafts, cdrafts);
    UIT_SHRINK(e, ids, nids, cids);
    UIT_SHRINK(e, prev, nprev, cprev);
    UIT_SHRINK(e, evs, nevs, cevs);
    UIT_SHRINK(e, drew, ndrew, cdrew);
    shrink((void **)&e->tvl, &e->tvl_cap, 0, sizeof *e->tvl);
    uit_buf_free(&e->scratch);
    uit_buf_free(&e->evtext);
    uit_buf_free(&e->trace);
    uit_buf_free(&e->cells);
    uit_buf_free(&e->fits);
    e->trace_at = 0;
    // what stays, cut to what it holds: the declarations and the lowered page
    UIT_SHRINK(e, slots, nslots, cslots);
    UIT_SHRINK(e, acts, nacts, cacts);
    UIT_SHRINK(e, tmpls, ntmpls, ctmpls);
    UIT_SHRINK(e, ops, nops, cops);
    UIT_SHRINK(e, conds, nconds, cconds);
    UIT_SHRINK(e, terms, nterms, cterms);
    UIT_SHRINK(e, nodes, nnodes, cnodes);
    UIT_SHRINK(e, props, nprops, cprops);
    UIT_SHRINK(e, btns, nbtns, cbtns);
    UIT_SHRINK(e, labels, nlabels, clabels);
    buf_fit(&e->pool);
}

void uit_free(uit_t *e)
{
    if (!e)
        return;
    intern_drop(e);
    for (int i = 0; i < e->nslots; i++) {
        UIT_FREE(e->slots[i].s);
        UIT_FREE(e->slots[i].cells);
        UIT_FREE(e->slots[i].at);
        UIT_FREE(e->slots[i].sync);
        UIT_FREE(e->slots[i].mf);
    }
    for (int i = 0; i < e->norders; i++) {
        UIT_FREE(e->orders[i].key);
        UIT_FREE(e->orders[i].keys);
    }
    for (int i = 0; i < e->ndrafts; i++) {
        UIT_FREE(e->drafts[i].key);
        UIT_FREE(e->drafts[i].buf);
    }
    free_drew(e);
    for (int i = 0; i < e->nvr; i++)
        UIT_FREE(e->vr[i].h);
    UIT_FREE(e->vr);
    UIT_FREE(e->slots); UIT_FREE(e->acts); UIT_FREE(e->tmpls); UIT_FREE(e->ops);
    UIT_FREE(e->conds); UIT_FREE(e->terms); UIT_FREE(e->nodes); UIT_FREE(e->props);
    UIT_FREE(e->btns); UIT_FREE(e->ids); UIT_FREE(e->prev); UIT_FREE(e->evs);
    UIT_FREE(e->drew); UIT_FREE(e->orders); UIT_FREE(e->want); UIT_FREE(e->drafts);
    UIT_FREE(e->labels); UIT_FREE(e->tvl); UIT_FREE(e->rects); UIT_FREE(e->arr);
    UIT_FREE(e->car); UIT_FREE(e->cel); UIT_FREE(e->anc); UIT_FREE(e->mcells); UIT_FREE(e->err);
    uit_buf_free(&e->pool); uit_buf_free(&e->scratch); uit_buf_free(&e->evtext); uit_buf_free(&e->cells);
    uit_buf_free(&e->trace);
    uit_buf_free(&e->fits);
    UIT_FREE(e);
}

const char *uit_error(const uit_t *e)
{
    return e->err ? e->err : "";
}

const char *uit_get_cell(const uit_t *e, int slot, int row, int f)
{
    if (slot < 0 || slot >= e->nslots || e->slots[slot].type != UIT_MODEL || row < 0 || row >= e->slots[slot].nrows ||
        f < 0 || f >= e->slots[slot].nf)
        return NULL;
    return uit_cell(e, slot, row, f);
}

int uit_cell_put(uit_t *e, int slot, int row, int f, const char *v)
{
    uit_slot_t *S = &e->slots[slot];
    int i = row * S->nf + f;
    uint32_t at = S->at[i], was = (uint32_t)strlen(S->cells + at), now = (uint32_t)strlen(v);
    if (now != was) {
        uint32_t n = S->cells_n - was + now;
        char *c = UIT_REALLOC(S->cells, (size_t)n + 1);
        if (!c)
            return UIT_E_NOMEM;
        memmove(c + at + now, c + at + was, S->cells_n + 1 - at - was);
        S->cells = c;
        S->cells_n = n;
        for (int j = i + 1; j < S->nrows * S->nf; j++)
            S->at[j] = S->at[j] + now - was;
    }
    memcpy(S->cells + at, v, now);
    return 0;
}

const char *uit_error_code(const uit_t *e)
{
    return e->code;
}

// -- declarations ---------------------------------------------------------------

int uit_state(uit_t *e, const char *name, int type, const char *values, size_t vlen)
{
    if (e->decl_done)
        return uit_fail(e, UIT_E_ARG, UIT_MSG("state %s declared after the first build", "%s"), name);
    if (type < UIT_BOOL || type > UIT_MODEL)
        return uit_fail(e, UIT_E_ARG, UIT_MSG("state %s: no type %d", "state %s %d"), name, type);
    if (UIT_GROW(e, slots, nslots, cslots))
        return UIT_E_NOMEM;
    uit_slot_t *S = &e->slots[e->nslots];
    memset(S, 0, sizeof *S);
    int nm = pool_puts(e, name);
    if (nm < 0)
        return UIT_E_NOMEM;
    S->name = (uint16_t)nm;
    S->type = (uint8_t)type;
    S->model = -1;
    S->vals = UIT_NONE;
    if (type == UIT_ENUM && values) {
        int v = pool_put(e, values, vlen);
        if (v < 0)
            return UIT_E_NOMEM;
        S->vals = (uint16_t)v;
        for (size_t i = 0; i <= vlen; i++)
            if (i == vlen || values[i] == 0)
                S->nvals++;
    }
    return e->nslots++;
}

int uit_model(uit_t *e, int slot, const char *names, size_t nlen, const uint8_t *types, int nf, int key)
{
    if (slot < 0 || slot >= e->nslots || e->slots[slot].type != UIT_MODEL || nf < 1 || nf > UIT_FIELDS ||
        key < 0 || key >= nf)
        return uit_fail(e, UIT_E_ARG, UIT_MSG("model: bad slot %d or %d fields", "model %d %d"), slot, nf);
    uit_slot_t *S = &e->slots[slot];
    if (!S->mf && !(S->mf = UIT_MALLOC(sizeof *S->mf)))
        return UIT_E_NOMEM;
    S->nf = (uint8_t)nf;
    S->key = (uint8_t)key;
    size_t at = 0;
    for (int f = 0; f < nf; f++) {
        size_t n = text_len(names + at, nlen - at);
        int o = pool_put(e, names + at, n);
        if (o < 0)
            return UIT_E_NOMEM;
        S->mf->fname[f] = (uint16_t)o;
        S->mf->ftype[f] = types[f];
        S->mf->fvals[f] = 0;     // an enum's values (`uit_field_enum`); a blob writes it whatever the type
        S->mf->fnvals[f] = 0;
        at += n + 1;
    }
    return 0;
}

int uit_field_enum(uit_t *e, int slot, int f, const char *values, size_t vlen)
{
    if (slot < 0 || slot >= e->nslots || !e->slots[slot].mf || f < 0 || f >= e->slots[slot].nf ||
        e->slots[slot].mf->ftype[f] != UIT_TEXT)
        return uit_fail(e, UIT_E_ARG, UIT_MSG("field_enum: bad slot %d or field %d", "field_enum %d %d"), slot, f);
    uit_fields_t *M = e->slots[slot].mf;
    int v = pool_put(e, values, vlen);
    if (v < 0)
        return UIT_E_NOMEM;
    M->fvals[f] = (uint16_t)v;
    M->fnvals[f] = 1;
    for (size_t i = 0; i < vlen; i++)
        M->fnvals[f] += values[i] == 0;
    return 0;
}

int uit_row_of(uit_t *e, int slot, int model_slot)
{
    if (slot < 0 || slot >= e->nslots || model_slot < 0 || model_slot >= e->nslots)
        return UIT_E_ARG;
    e->slots[slot].model = (int16_t)model_slot;
    return 0;
}

int uit_labels(uit_t *e, const char *name, const char *keys, size_t klen, const char *words,
               size_t wlen)
{
    if (e->decl_done)
        return uit_fail(e, UIT_E_ARG, UIT_MSG("labels %s declared after the first build", "%s"), name);
    int n = 0;
    for (size_t i = 0; i <= klen; i++)
        n += i == klen || keys[i] == 0;
    int w = 0;
    for (size_t i = 0; i <= wlen; i++)
        w += i == wlen || words[i] == 0;
    if (n != w)
        return uit_fail(e, UIT_E_ARG, UIT_MSG("labels %s: %d keys, %d words", "labels %s %d %d"), name, n, w);
    if (UIT_GROW(e, labels, nlabels, clabels))
        return UIT_E_NOMEM;
    int a = pool_puts(e, name), b = pool_put(e, keys, klen), c = pool_put(e, words, wlen);
    if (a < 0 || b < 0 || c < 0)
        return UIT_E_NOMEM;
    uit_labels_t L = {(uint16_t)a, (uint16_t)b, (uint16_t)c, (uint16_t)n};
    e->labels[e->nlabels] = L;
    return e->nlabels++;
}

const char *uit_label_word(const uit_t *e, int table, const char *key, size_t n)
{
    const uit_labels_t *L = &e->labels[table];
    const char *k = uit_str(e, L->keys), *w = uit_str(e, L->words), *dflt = NULL;
    for (int i = 0; i < L->n; i++) {
        size_t kn = strlen(k);
        if (kn == n && !memcmp(k, key, n))
            return w;
        if (kn == 1 && k[0] == '_')
            dflt = w;
        k += kn + 1;
        w += strlen(w) + 1;
    }
    return dflt ? dflt : "";
}

int uit_action(uit_t *e, const char *name, const char *label, const char *hint, const char *when,
               int off, int flags, const char *letters, const char *icon)
{
    if (e->decl_done)
        return uit_fail(e, UIT_E_ARG, UIT_MSG("action %s declared after the first build", "%s"), name);
    if (UIT_GROW(e, acts, nacts, cacts))
        return UIT_E_NOMEM;
    uit_act_t A;
    memset(&A, 0, sizeof A);
    int a = pool_puts(e, name), b = pool_puts(e, label ? label : "");
    if (a < 0 || b < 0)
        return UIT_E_NOMEM;
    A.name = (uint16_t)a;
    A.label = (uint16_t)b;
    A.hint = (int16_t)uit_tmpl_compile(e, hint ? hint : (label ? label : ""), -1);
    if (A.hint < 0)
        return A.hint;
    A.when = -1;
    if (when) {
        int c = uit_cond_compile(e, when, -1);
        if (c < 0)
            return c;
        A.when = (int16_t)c;
    }
    A.off = (uint8_t)off;
    A.flags = (uint16_t)flags;
    int ls = pool_puts(e, letters ? letters : "");
    if (ls < 0)
        return UIT_E_NOMEM;
    A.letters = (uint16_t)ls;
    int ic = pool_puts(e, icon ? icon : "");
    if (ic < 0)
        return UIT_E_NOMEM;
    A.icon = (uint16_t)ic;
    int cs = pool_puts(e, "");
    if (cs < 0)
        return UIT_E_NOMEM;
    A.chars = (uint16_t)cs;
    A.letter = (uint8_t)(letters ? letters[0] : 0);
    A.row = -1;
    e->acts[e->nacts] = A;
    return e->nacts++;
}

int uit_action_row(uit_t *e, int a, int slot)
{
    if (a < 0 || a >= e->nacts || slot < 0 || slot >= e->nslots || e->slots[slot].type != UIT_ROWOF)
        return uit_fail(e, UIT_E_ARG, UIT_MSG("action %d row=%d: no row_of", "%d %d"), a, slot);
    e->acts[a].row = (int16_t)slot;
    return 0;
}

int uit_action_chars(uit_t *e, int a, const char *chars)
{
    if (a < 0 || a >= e->nacts)
        return uit_fail(e, UIT_E_ARG, UIT_MSG("action %d chars=: no action", "%d"), a);
    int c = pool_puts(e, chars);
    if (c < 0)
        return UIT_E_NOMEM;
    e->acts[a].chars = (uint16_t)c;
    return 0;
}

// -- state ----------------------------------------------------------------------

static int slot_ok(uit_t *e, int slot)
{
    return slot >= 0 && slot < e->nslots;
}

int uit_set_int(uit_t *e, int slot, int32_t v)
{
    if (!slot_ok(e, slot))
        return UIT_E_ARG;
    uit_slot_t *S = &e->slots[slot];
    S->i = v;
    S->f = v;
    S->absent = 0;
    S->ver++;
    return 0;
}

int uit_set_num(uit_t *e, int slot, double v)
{
    if (!slot_ok(e, slot))
        return UIT_E_ARG;
    e->slots[slot].f = v;
    e->slots[slot].i = (int32_t)v;
    e->slots[slot].absent = 0;
    e->slots[slot].ver++;
    return 0;
}

int uit_set_text_q(uit_t *e, int slot, const char *s, size_t n)
{
    uit_slot_t *S = &e->slots[slot];
    if (n + 1 > S->scap) {
        char *p = UIT_REALLOC(S->s, n + 1);
        if (!p)
            return UIT_E_NOMEM;
        S->s = p;
        S->scap = (uint32_t)n + 1;
    }
    if (n)
        memcpy(S->s, s, n);
    S->s[n] = 0;
    S->sn = (uint32_t)n;
    return 0;
}

int uit_set_text(uit_t *e, int slot, const char *s, size_t n)
{
    if (!slot_ok(e, slot))
        return UIT_E_ARG;
    int r = uit_set_text_q(e, slot, s, n);
    if (r == 0)
        e->slots[slot].ver++, e->slots[slot].absent = 0;
    return r;
}

int uit_absent(const uit_t *e, int slot)
{
    return slot >= 0 && slot < e->nslots && e->slots[slot].absent;
}

int uit_set_absent(uit_t *e, int slot)
{
    if (!slot_ok(e, slot))
        return UIT_E_ARG;
    uit_slot_t *S = &e->slots[slot];
    S->absent = 1;
    S->i = 0;
    S->f = 0;
    S->sn = 0;
    S->ver++;
    return 0;
}

int uit_set_model(uit_t *e, int slot, int n, const char *cells, size_t len)
{
    if (slot < 0 || slot >= e->nslots || e->slots[slot].type != UIT_MODEL || n < 0)
        return UIT_E_ARG;
    uit_slot_t *S = &e->slots[slot];
    char *c = UIT_MALLOC(len + 1);
    uint32_t *at = UIT_MALLOC(sizeof(uint32_t) * (size_t)(n * S->nf + 1));
    if (!c || !at) {
        UIT_FREE(c);
        UIT_FREE(at);
        return UIT_E_NOMEM;
    }
    memcpy(c, cells, len);
    c[len] = 0;
    size_t p = 0;
    for (int i = 0; i < n * S->nf; i++) {
        if (p > len) {
            UIT_FREE(c);
            UIT_FREE(at);
            return uit_fail(e, UIT_E_ARG, UIT_MSG("model: %d cells short", "model %d"), n * S->nf - i);
        }
        at[i] = (uint32_t)p;
        p += text_len(c + p, len - p) + 1;
    }
    UIT_FREE(S->cells);
    UIT_FREE(S->at);
    S->cells = c;
    S->at = at;
    S->cells_n = (uint32_t)len;
    S->nrows = n;
    S->ver++;
    // the removal rule, for each list over this model with a cur= (settle)
    for (int k = 0; k < e->nnodes; k++)
        if (UIT_IS_LIST(e->nodes[k].kind) && e->nodes[k].slot == slot && e->nodes[k].cur >= 0)
            uit_after_removal(e, k);
    return 0;
}

int32_t uit_get_int(const uit_t *e, int slot)
{
    if (slot < 0 || slot >= e->nslots)
        return 0;
    return e->slots[slot].i;
}

const char *uit_get_text(const uit_t *e, int slot, size_t *n)
{
    if (slot < 0 || slot >= e->nslots)
        return NULL;
    const uit_slot_t *S = &e->slots[slot];
    if (S->type != UIT_TEXT && S->type != UIT_ENUM && S->type != UIT_ROWOF)
        return NULL;
    *n = S->sn;
    return S->s ? S->s : "";
}

void uit_slot_repr(uit_t *e, uit_buf_t *b, int slot)
{
    const uit_slot_t *S = &e->slots[slot];
    switch (S->type) {
    case UIT_BOOL:
        uit_buf_printf(b, "%s", S->i ? "True" : "False");
        break;
    case UIT_INT:
        uit_buf_printf(b, "%ld", (long)S->i);
        break;
    case UIT_NUM:
        uit_buf_printf(b, "%.17g", S->f);
        break;
    case UIT_MODEL:
        uit_buf_printf(b, "[%d rows]", S->nrows);
        break;
    default:
        uit_buf_repr(b, S->s ? S->s : "", S->sn);
    }
}

// -- the build ------------------------------------------------------------------

void uit_build_begin(uit_t *e, const char *page_id)
{
    if (!e->decl_done) {
        e->decl_done = 1;
        e->m_pool = e->pool.n;
        e->m_tmpls = e->ntmpls;
        e->m_ops = e->nops;
        e->m_conds = e->nconds;
        e->m_terms = e->nterms;
    }
    e->pool.n = e->m_pool;
    e->ntmpls = e->m_tmpls;
    e->nops = e->m_ops;
    e->nconds = e->m_conds;
    e->nterms = e->m_terms;
    e->nnodes = e->nprops = e->nbtns = 0;
    int p = pool_puts(e, page_id ? page_id : "");
    e->page_id = p < 0 ? 0 : (uint16_t)p;
    free_drew(e);
}

static uint16_t up(int k)
{
    return k < 0 ? UIT_NONE : (uint16_t)k;
}

static int check_fail(uit_t *e, const char *code, char *out);

void uit_set_app(uit_t *e, int app)
{
    e->app = (uint8_t)(app != 0);
}

int uit_node(uit_t *e, int kind, const char *key, int parent)
{
    if (kind < UIT_PAGE || kind >= UIT_KINDS)
        return uit_fail(e, UIT_E_KIND, UIT_MSG("no kind %d", "%d"), kind);
    if ((parent < 0) != (kind == UIT_PAGE) || parent >= e->nnodes)
        return uit_fail(e, UIT_E_ARG, UIT_MSG("node %s: parent %d", "node %s %d"), key, parent);
    if (e->app) {
        char out[200];
        int r = check_fail(e, uit_check_prop(uit_kind_names[kind], "", UIT_VC_APP, NULL, out, sizeof out), out);
        if (r)
            return r;
    }
    if (UIT_GROW(e, nodes, nnodes, cnodes))
        return UIT_E_NOMEM;
    int k = pool_puts(e, key);
    if (k < 0)
        return UIT_E_NOMEM;
    uit_node_t N;
    memset(&N, 0, sizeof N);
    N.kind = (uint8_t)kind;
    N.key = (uint16_t)k;
    N.parent = up(parent);
    N.kid = N.last = N.next = N.props = UIT_NONE;
    N.act = N.shown = N.focus = N.t_main = N.t_value = N.t_icon = N.t_aux = -1;
    N.slot = N.cur = N.changed = N.on = N.current = N.mark = -1;
    if (kind == UIT_FIELD)
        N.btn = 32;
    if (kind == UIT_SPLIT)
        N.btn = N.nbtn = 8, N.lit = 1;              // pad=8, gap=8, align="center"
    if (kind == UIT_BUBBLE)
        N.btn = 75, N.nbtn = 4;                     // max=0.75, lines=4
    if (kind == UIT_GRID)
        N.btn = 0, N.nbtn = 6, N.lit = 0x11;        // pad=0, gap=6, 1 x 1
    if (kind == UIT_PANES)
        N.nbtn = 6;                                 // the gutter, desk units
    if (kind == UIT_SWITCH) {
        // keyed "switch:NAME": the enum or bool it switches on
        const char *name = strncmp(key, "switch:", 7) ? "" : key + 7;
        int s = uit_slot_find(e, name, strlen(name));
        if (s < 0 || (e->slots[s].type != UIT_ENUM && e->slots[s].type != UIT_BOOL))
            return uit_fail(e, UIT_E_NAME, UIT_MSG("switch %s: no enum or bool of that name", "switch %s"), key);
        N.slot = (int16_t)s;
    }
    int me = e->nnodes++;
    e->nodes[me] = N;
    if (parent >= 0) {
        uit_node_t *P = &e->nodes[parent];
        if (P->last == UIT_NONE)
            P->kid = (uint16_t)me;
        else
            e->nodes[P->last].next = (uint16_t)me;
        P->last = (uint16_t)me;
    }
    return me;
}

int uit_list_of(const uit_t *e, int node)
{
    for (int k = node; k >= 0 && k != (int)UIT_NONE; k = e->nodes[k].parent)
        if (UIT_IS_LIST(e->nodes[k].kind))
            return k;
    return -1;
}

int uit_model_of(uit_t *e, int node)
{
    for (int k = node; k >= 0 && k != (int)UIT_NONE; k = e->nodes[k].parent)
        if (UIT_IS_LIST(e->nodes[k].kind))
            return e->nodes[k].slot;
    return -1;
}

const char *const uit_kind_names[UIT_KINDS] = {"", "page", "group", "label", "info", "link", "button",
                                               "toggle", "rows", "dialog", "seg", "slider", "field",
                                               "empty", "progress", "text_view", "scroll", "menu",
                                               "item", "split", "canvas", "tabs", "switch", "case",
                                               "table", "col", "foot", "cards", "card", "picture",
                                               "popover", "tools", "row", "status", "text_editor",
                                               "panes", "pane", "slot", "panel", "lent",
                                               "rule", "note", "grid", "bubble", "month", "toast", "cells",
                                               "stepper", "hints"};

static const char *const TONES[] = {"ink", "dim", "value", "danger"};
static const char *const BKINDS[] = {"normal", "primary", "tonal", "danger", "toggle", "bar"};   // moy_ui's, then its bar item

static int lit_index(const char *v, const char *const *tab, int n)
{
    for (int i = 0; i < n; i++)
        if (!strcmp(v, tab[i]))
            return i;
    return -1;
}

static int add_prop(uit_t *e, int node, const char *name, const char *src, const char *repr, int kind, int idx)
{
    if (UIT_GROW(e, props, nprops, cprops))
        return UIT_E_NOMEM;
    int a = pool_puts(e, name), b = pool_puts(e, src), c = repr ? pool_puts(e, repr) : (int)UIT_NONE;
    if (a < 0 || b < 0 || c < 0)
        return UIT_E_NOMEM;
    uit_prop_t P = {(uint16_t)a, (uint16_t)b, (uint16_t)c, (uint8_t)kind, (int16_t)idx, UIT_NONE};
    int me = e->nprops++;
    e->props[me] = P;
    uit_node_t *N = &e->nodes[node];
    if (N->props == UIT_NONE) {
        N->props = (uint16_t)me;
    } else {
        int k = N->props;
        while (e->props[k].next != UIT_NONE)
            k = e->props[k].next;
        e->props[k].next = (uint16_t)me;
    }
    return 0;
}

int uit_cond_of(uit_t *e, int node, const char *name)
{
    if (node < 0 || node >= e->nnodes)
        return UIT_E_ARG;
    for (int p = e->nodes[node].props; p != (int)UIT_NONE; p = e->props[p].next) {
        const uit_prop_t *P = &e->props[p];
        if (P->kind == PK_COND && !strcmp(uit_str(e, P->name), name))
            return uit_cond_eval(e, P->idx, -1, -1);
    }
    return -1;
}

// A state of `type` named `src` (an opt of it too), else -1.
static int state_of(uit_t *e, const char *src, int type)
{
    int s = uit_slot_find(e, src, strlen(src));
    return s >= 0 && e->slots[s].type == type ? s : -1;
}

// A prop of a panes or a pane (moy_uitree_int.h's PN_* words): 0, a refusal, or 1 where `name`
// is none of theirs.
static int pane_prop(uit_t *e, int node, const char *name, const char *src, const char *repr)
{
    uit_node_t *N = &e->nodes[node];
    int pane = N->kind == UIT_PANE, s = -2;
    if (!strcmp(name, "size")) {
        N->current = (int16_t)(s = state_of(e, src, UIT_INT));
    } else if (!strcmp(name, "start")) {
        if ((src[0] >= '0' && src[0] <= '9') || src[0] == '-')
            N->btn = (uint16_t)strtol(src, NULL, 10), N->lit |= PN_START;
        else
            N->changed = (int16_t)(s = state_of(e, src, UIT_INT));
    } else if (!strcmp(name, "grow") || !strcmp(name, "head")) {
        if (!strcmp(src, name[0] == 'g' ? "True" : "False"))
            N->lit |= name[0] == 'g' ? PN_GROW : PN_HEADLESS;
    } else if (!strcmp(name, "dir") && !pane) {
        if (strcmp(src, "row") && strcmp(src, "col"))
            return uit_check_fail(e, "T03", UIT_MSG("ui.panes dir=%s: one of row, col", "ui.panes dir=%s"), src);
        if (src[0] == 'c')
            N->lit |= PN_COL;
    } else if (!strcmp(name, "gap") && !pane) {
        N->nbtn = (uint16_t)strtol(src, NULL, 10);
    } else if ((!strcmp(name, "focused") || !strcmp(name, "grown")) && !pane) {
        s = state_of(e, src, UIT_TEXT);
        if (name[0] == 'f')
            N->slot = (int16_t)s;
        else
            N->cur = (int16_t)s;
    } else if (!strcmp(name, "tabs") && pane) {
        N->slot = (int16_t)(s = state_of(e, src, UIT_ENUM));
    } else if (!strcmp(name, "labels") && pane) {
        for (int i = 0; i < e->nlabels; i++)
            if (!strcmp(uit_str(e, e->labels[i].name), src))
                N->cur = (int16_t)i;
        if (N->cur < 0)
            return uit_fail(e, UIT_E_NAME, UIT_MSG("pane labels=%s: no label table of that name", "labels=%s"), src);
    } else if (!strcmp(name, "min") && pane) {
        // one prop a pair: "w h", its tab's value the repr ("_" any other, "" the one pair)
        if (e->nbtns + 3 > e->cbtns) {
            int c = e->cbtns ? 2 * e->cbtns : 16;
            int16_t *p = UIT_REALLOC(e->btns, (size_t)c * sizeof *p);
            if (!p)
                return UIT_E_NOMEM;
            e->btns = p, e->cbtns = c;
        }
        int v = PN_MIN_ONE;
        if (repr && repr[0])
            v = strcmp(repr, "_") ? pool_puts(e, repr) : PN_MIN_ANY;
        if (v == -1 && strcmp(repr, "_"))
            return UIT_E_NOMEM;
        char *end;
        long w = strtol(src, &end, 10), h = strtol(end, NULL, 10);
        if (!N->nbtn)
            N->mark = (int16_t)e->nbtns;
        e->btns[e->nbtns++] = (int16_t)v;
        e->btns[e->nbtns++] = (int16_t)w;
        e->btns[e->nbtns++] = (int16_t)h;
        N->nbtn++;
    } else if (!strcmp(name, "offered") && pane) {
        int c = uit_cond_compile(e, src, -1);
        if (c < 0)
            return c;
        return add_prop(e, node, name, src, repr ? repr : "", PK_COND, c);
    } else {
        return 1;
    }
    if (s == -1)
        return uit_fail(e, UIT_E_NAME, UIT_MSG("%s %s=%s: no state of its type", "%s %s=%s"),
                        uit_kind_names[N->kind], name, src);
    return add_prop(e, node, name, src, repr, PK_LIT, -1);
}

// The check's refusal (`uit_check_prop`'s `out`) as the store's error: 0 where it took the name, or
// where the kind is the store's own (switch, case, row, panel), which the check has no row for.
static int check_fail(uit_t *e, const char *code, char *out)
{
    if (!code || !strncmp(out, "no kind", 7))
        return 0;
    char *what = out, *expected = strchr(what, '\x1f');
    *expected++ = 0;
    char *fix = strchr(expected, '\x1f');
    *fix++ = 0;
    fix[strcspn(fix, "\x1f")] = 0;
    return uit_check_fail(e, code, UIT_MSG("%s; fix: %s%s%s%s", "%s%.0s%.0s%.0s%.0s"), what, fix,
                          expected[0] ? " (expected " : "", expected, expected[0] ? ")" : "");
}

// The API's check at lowering, so a front that carries no check (a compiled app's) is held to the
// contract's table as the others are: a prop name no kind takes, a retired one, a word not the
// prop's, and in an app's store (`uit_set_app`) the shell's own. What a kind does not take by name
// in the API is the store's own: a node's binding (`bind`, `field`) and the head of the kinds whose
// head the store keeps by name (HEADS), which the API gives by position.
static int api_check(uit_t *e, int kind, const char *name, const char *src)
{
    static const struct {
        uint8_t kind;
        const char *name;
    } HEADS[] = {{UIT_PAGE, "title"}, {UIT_GROUP, "caption"}, {UIT_LABEL, "text"}, {UIT_DIALOG, "title"},
                 {UIT_INFO, "label"}, {UIT_EMPTY, "title"}, {UIT_PICTURE, "image"}, {UIT_PROGRESS, "value"},
                 {UIT_STATUS, "text"}, {UIT_COL, "text"}, {UIT_MENU, "caption"}, {UIT_BUBBLE, "text"},
                 {UIT_TOAST, "text"}};
    const char *kn = uit_kind_names[kind];
    if (!uit_prop_type(kn, name)) {
        if (!strcmp(name, "bind") || !strcmp(name, "field"))
            return 0;
        for (size_t i = 0; i < sizeof HEADS / sizeof HEADS[0]; i++)
            if (HEADS[i].kind == kind && !strcmp(name, HEADS[i].name))
                return 0;
    }
    char out[600];
    return check_fail(e, uit_check_prop(kn, name, e->app ? UIT_VC_APP : UIT_VC_ANY, src, out, sizeof out), out);
}

int uit_prop(uit_t *e, int node, const char *name, const char *src, const char *repr)
{
    if (node < 0 || node >= e->nnodes)
        return UIT_E_ARG;
    uit_node_t *N = &e->nodes[node];
    int checked = api_check(e, N->kind, name, src);
    if (checked < 0)
        return checked;
    int model = uit_model_of(e, node);
    if (UIT_IS_LIST(N->kind))
        model = -1;             // a list's own props read the page, not its rows
    int kind = N->kind;
    int16_t *tslot = NULL;
    int list = uit_list_of(e, node);
    e->ccur = list >= 0 && list != node ? e->nodes[list].current : -1;
    if ((!strcmp(name, "shown") && kind != UIT_PAGE) || !strcmp(name, "focus")) {
        int c = uit_cond_compile(e, src, model);
        if (c < 0)
            return c;
        if (name[0] == 's')
            N->shown = (int16_t)c;
        else
            N->focus = (int16_t)c;
        return add_prop(e, node, name, src, repr, PK_COND, c);
    }
    if (kind == UIT_HINTS && (!strcmp(name, "tail") || !strcmp(name, "drop"))) {
        // a hints row's tail= and drop=: conditions of each row of its model, the rows at its
        // end and the rows that go first where the row runs out of room
        int c = uit_cond_compile(e, src, N->slot);
        if (c < 0)
            return c;
        *(name[0] == 't' ? &N->mark : &N->cur) = (int16_t)c;
        return add_prop(e, node, name, src, repr, PK_COND, c);
    }
    if (kind == UIT_HINTS && (!strcmp(name, "keys") || !strcmp(name, "label"))) {
        // a hints row's keys= and label=: templates of each row of its model
        model = N->slot;
        tslot = name[0] == 'k' ? &N->t_value : &N->t_main;
    } else if ((kind == UIT_ROWS || kind == UIT_CARDS) && !strcmp(name, "group")) {
        // a caption drawn where its value changes from the row before: over the rows
        model = N->slot;
        tslot = &N->t_main;
    } else if (kind == UIT_POPOVER && !strcmp(name, "at")) {
        // the rect it hangs from, "X Y W H" on the host's surface (`draw_popover`)
        int t = uit_tmpl_compile(e, src, model);
        if (t < 0)
            return t;
        return add_prop(e, node, name, src, repr, PK_TMPL, t);
    } else if (((kind == UIT_EMPTY || kind == UIT_NOTE) && !strcmp(name, "lines"))
               || (kind == UIT_DIALOG && !strcmp(name, "labels"))) {
        // one prop a line (an empty's or a note's, drawn in order, an empty one left out) or
        // a dialog's button (its label, one a button, in order), each a template
        int t = uit_tmpl_compile(e, src, model);
        if (t < 0)
            return t;
        if (e->tmpls[t].type == UIT_BOOL || e->tmpls[t].type == UIT_MODEL)
            return uit_check_fail(e, "T03", UIT_MSG("%s %s=%s is a %s, not a text", "%s %s %s %s"),
                                  uit_kind_names[kind], name, src, uit_type_name(e->tmpls[t].type));
        return add_prop(e, node, name, src, repr, PK_TMPL, t);
    } else if ((kind == UIT_SEG || kind == UIT_TABS) && !strcmp(name, "text")) {
        // a seg or tabs over a row_of: each row's word, a template over its model's rows; a
        // seg bound to a row's field: its items, one a line, a template over that row
        if (!(N->lit & NL_FIELD) && (N->slot < 0 || e->slots[N->slot].type != UIT_ROWOF))
            return uit_fail(e, UIT_E_ARG, UIT_MSG("%s text=%s before its row_of", "%s %s"),
                            uit_kind_names[kind], src);
        if (!(N->lit & NL_FIELD))
            model = e->slots[N->slot].model;
        tslot = &N->t_value;
    } else if (!strcmp(name, "title") || !strcmp(name, "caption") || !strcmp(name, "text") ||
               !strcmp(name, "label"))
        tslot = &N->t_main;
    else if (!strcmp(name, "value") || (!strcmp(name, "lo") && kind == UIT_SLIDER) ||
             (!strcmp(name, "head") && kind == UIT_BUBBLE))
        tslot = &N->t_value;
    else if (!strcmp(name, "status") && (kind == UIT_BUBBLE || kind == UIT_PAGE))
        tslot = &N->t_aux;
    else if ((kind == UIT_BUBBLE && (!strcmp(name, "side") || !strcmp(name, "tone") || !strcmp(name, "signal"))) ||
             ((kind == UIT_INFO || kind == UIT_LINK) &&
              (!strcmp(name, "tag") || !strcmp(name, "tone") || !strcmp(name, "signal"))) ||
             (kind == UIT_LINK && (!strcmp(name, "swatch") || !strcmp(name, "sub") || !strcmp(name, "count") ||
                                   !strcmp(name, "mark"))) ||
             (kind == UIT_MONTH && (!strcmp(name, "year") || !strcmp(name, "month") || !strcmp(name, "today"))) ||
             (kind == UIT_CARD && (!strcmp(name, "badge") || !strcmp(name, "label_icon") || !strcmp(name, "fill"))) || (kind == UIT_CARDS && (!strcmp(name, "pad") || !strcmp(name, "tone") || !strcmp(name, "label"))) ||
             (kind == UIT_CELLS && (!strcmp(name, "first") || !strcmp(name, "count") || !strcmp(name, "cols") ||
                                    !strcmp(name, "side") || !strcmp(name, "gap") || !strcmp(name, "clear")))) {
        // templates the draw finds among its props by name (uit_tmpl_prop); signal=, a month's
        // year=, month= and today= and a cards list's pad= ints; a carousel's tone= its caption's
        // ink, and label= its desk shelf's caption
        int t = uit_tmpl_compile(e, src, model);
        if (t < 0)
            return t;
        int ty = e->tmpls[t].type, want_int = !strcmp(name, "signal") || kind == UIT_MONTH ||
                                           (kind == UIT_CARDS && name[0] == 'p') || kind == UIT_CELLS;
        if (want_int ? ty != UIT_INT && !e->tmpls[t].lit : ty == UIT_BOOL || ty == UIT_MODEL)
            return uit_check_fail(e, "T03", UIT_MSG("%s %s=%s is a %s, not %s", "%s %s %s %s %s"), uit_kind_names[kind],
                                  name, src, uit_type_name(ty), want_int ? "an int" : "a text");
        return add_prop(e, node, name, src, repr, PK_TMPL, t);
    }
    else if (!strcmp(name, "max") && kind == UIT_PROGRESS)
        tslot = &N->t_aux;
    else if (kind == UIT_SPLIT && (!strcmp(name, "dir") || !strcmp(name, "sizes"))) {
        if (name[0] == 'd' && !strchr(src, '{') && strcmp(src, "row") && strcmp(src, "col"))
            return uit_check_fail(e, "T03", UIT_MSG("ui.split dir=%s: one of row, col", "ui.split dir=%s"), src);
        tslot = name[0] == 'd' ? &N->t_value : &N->t_aux;
    }
    else if (!strcmp(name, "icon"))
        tslot = &N->t_icon;
    else if (!strcmp(name, "image") && (kind == UIT_CARD || kind == UIT_PICTURE)) {
        // the image state or row field it names, as text (the front end's: uit_on_pic)
        char tpl[UIT_ID_MAX + 3];
        snprintf(tpl, sizeof tpl, "{%s}", src);
        int t = uit_tmpl_compile(e, tpl, model);
        if (t < 0)
            return t;
        return add_prop(e, node, name, src, repr, PK_TMPL, t);
    }
    else if (!strcmp(name, "hint") && kind == UIT_TABLE)
        tslot = &N->t_value;
    else if (!strcmp(name, "hint") && kind == UIT_CANVAS)
        tslot = &N->t_main;         // a keys= canvas's confirm hint while it holds focus
    else if ((kind == UIT_CARDS && !strcmp(name, "w")) || (kind == UIT_CARD && !strcmp(name, "sub")) ||
             (kind == UIT_CANVAS && !strcmp(name, "w")) || (kind == UIT_ROW && !strcmp(name, "gap")) ||
             (kind == UIT_BUTTON && !strcmp(name, "w")) || (kind == UIT_PICTURE && !strcmp(name, "side")) || (kind == UIT_POPOVER && !strcmp(name, "anchor")) ||
             (kind == UIT_GRID && !strcmp(name, "w")) || (kind == UIT_LABEL && !strcmp(name, "scale")) ||
             (kind == UIT_TOAST && !strcmp(name, "sub")) ||
             (kind == UIT_GROUP && !strcmp(name, "gap")))
        tslot = &N->t_value;
    else if ((kind == UIT_CARDS && !strcmp(name, "h")) || (kind == UIT_POPOVER && !strcmp(name, "w")) ||
             (kind == UIT_ROW && !strcmp(name, "pad")) || (kind == UIT_GRID && !strcmp(name, "h")) ||
             (kind == UIT_LABEL && !strcmp(name, "w")) || (kind == UIT_TOAST && !strcmp(name, "burst")) ||
             ((kind == UIT_CARD || kind == UIT_PICTURE || kind == UIT_BUTTON) && !strcmp(name, "tone")))
        tslot = &N->t_aux;
    else if ((!strcmp(name, "empty") && UIT_IS_LIST(kind)) ||
             (!strcmp(name, "hint") && (kind == UIT_TOGGLE || kind == UIT_FIELD || kind == UIT_TABS)) ||
             (!strcmp(name, "hi") && kind == UIT_SLIDER))
        tslot = &N->t_aux;
    if (tslot) {
        int t = uit_tmpl_compile(e, src, model);
        if (t < 0)
            return t;
        const uit_tmpl_t *T = &e->tmpls[t];
        if ((kind == UIT_SLIDER && (!strcmp(name, "lo") || !strcmp(name, "hi"))) ||
            (kind == UIT_PROGRESS && (!strcmp(name, "value") || !strcmp(name, "max"))) ||
            (kind == UIT_CARDS && name[1] == 0) || (kind == UIT_PICTURE && !strcmp(name, "side")) ||
            (kind == UIT_POPOVER && !strcmp(name, "w")) || (kind == UIT_CANVAS && !strcmp(name, "w")) ||
            (kind == UIT_BUTTON && !strcmp(name, "w")) || (kind == UIT_ROW && (!strcmp(name, "gap") || !strcmp(name, "pad"))) ||
            (kind == UIT_LABEL && (!strcmp(name, "scale") || !strcmp(name, "w"))) ||
            (kind == UIT_GROUP && !strcmp(name, "gap")) || (kind == UIT_TOAST && !strcmp(name, "burst")) ||
            (kind == UIT_GRID && name[1] == 0)) {
            // an int prop: an int template, or the int literal a number lowers to
            const char *d = src + (src[0] == '-');
            int lit_int = T->lit && *d;
            for (; *d && lit_int; d++)
                lit_int = *d >= '0' && *d <= '9';
            if (T->type != UIT_INT && !lit_int)
                return uit_check_fail(e, "T03", UIT_MSG("%s %s=%s is a %s, not an int", "%s %s %s %s"), uit_kind_names[kind], name, src,
                                      uit_type_name(T->type));
        } else if (!((kind == UIT_SEG || kind == UIT_TABS) && !strcmp(name, "text"))) {      // row words: any type
            if (T->type == UIT_BOOL || T->type == UIT_MODEL)
                return uit_check_fail(e, "T03", UIT_MSG("%s %s=%s is a %s, not a text", "%s %s %s %s"), uit_kind_names[kind], name, src,
                                      uit_type_name(T->type));
        }
        *tslot = (int16_t)t;
        return add_prop(e, node, name, src, repr, PK_TMPL, t);
    }
    if (kind == UIT_PANES || kind == UIT_PANE) {
        int r = pane_prop(e, node, name, src, repr);
        if (r != 1)
            return r;
    }
    if (!strcmp(name, "tone") && kind == UIT_LABEL && strchr(src, '{')) {
        // a templated tone: its word drawn each frame (ink, dim, value, danger; another is ink)
        int t = uit_tmpl_compile(e, src, model);
        if (t < 0)
            return t;
        if (e->tmpls[t].type == UIT_BOOL || e->tmpls[t].type == UIT_MODEL)
            return uit_check_fail(e, "T03", UIT_MSG("label tone=%s is a %s, not a text", "%s %s"), src,
                                  uit_type_name(e->tmpls[t].type));
        return add_prop(e, node, name, src, repr, PK_TMPL, t);
    }
    if (!strcmp(name, "tone") && kind == UIT_LABEL) {
        int i = lit_index(src, TONES, 4);
        if (i <= 0)
            return uit_fail(e, UIT_E_KIND, UIT_MSG("label tone=%s: an ink role this engine does not draw yet", "label tone=%s"), src);
        N->lit = (uint8_t)i;
        return add_prop(e, node, name, src, repr, PK_LIT, i);
    }
    if (kind == UIT_LABEL && (!strcmp(name, "wrap") || !strcmp(name, "face") || !strcmp(name, "align") ||
                              !strcmp(name, "lines"))) {
        static const char *const WRAPS[] = {"cut", "word", "char"}, *const ALIGNS[] = {"start", "center", "end"};
        static const char *const FACES[] = {"ui", "title", "mono", "caption", "key", "op", "result"};
        static const uint8_t CENTRE[] = {0, 1, 4};
        int i = name[0] == 'w' ? lit_index(src, WRAPS, 3) : name[0] == 'f' ? lit_index(src, FACES, 7)
                : name[0] == 'a' ? lit_index(src, ALIGNS, 3) : (int)strtol(src, NULL, 10);
        if (i < 0)
            return uit_fail(e, UIT_E_KIND, UIT_MSG("label %s=%s", "%s %s"), name, src);
        if (name[0] == 'w')
            N->nbtn = (uint16_t)((N->nbtn & ~LT_WRAP) | i);
        else if (name[0] == 'f')
            N->nbtn |= (uint16_t)((i + 1) << LT_FACE_SHIFT);
        else if (name[0] == 'a')
            N->nbtn |= (uint16_t)(CENTRE[i] << LT_ALIGN_SHIFT);
        else
            N->btn = (uint16_t)i, N->nbtn |= LT_LINES;
        return add_prop(e, node, name, src, repr, PK_LIT, i);
    }
    if (kind == UIT_LABEL && !strcmp(name, "size")) {
        if (strcmp(src, "fit") && strcmp(src, "text"))
            return uit_fail(e, UIT_E_KIND, UIT_MSG("label size=%s: \"fit\" or \"text\"", "label size=%s"), src);
        N->nbtn |= src[0] == 'f' ? LT_FIT : LT_TEXT;
        return add_prop(e, node, name, src, repr, PK_LIT, 1);
    }
    if (kind == UIT_CANVAS && (!strcmp(name, "draw") || !strcmp(name, "h") || !strcmp(name, "keys"))) {
        // draw= names the front end's function (uit_on_draw); h= its height in a stack, a number
        // or an int template (t_aux); keys= the front end's function the keys go to while it
        // holds focus (CV_KEYS: a stop)
        if (name[0] == 'h') {
            char *end;
            long v = strtol(src, &end, 10);
            if (*src && !*end) {
                N->btn = (uint16_t)v;
            } else {
                int t = uit_tmpl_compile(e, src, model);
                if (t < 0)
                    return t;
                if (e->tmpls[t].type != UIT_INT)
                    return uit_check_fail(e, "T03", UIT_MSG("canvas h=%s is a %s, not an int", "canvas h=%s %s"), src,
                                          uit_type_name(e->tmpls[t].type));
                N->t_aux = (int16_t)t;
            }
        }
        if (name[0] == 'k')
            N->lit |= CV_KEYS;
        return add_prop(e, node, name, src, repr, PK_LIT, 0);
    }
    if (kind == UIT_CANVAS && !strcmp(name, "reads")) {
        // a state its draw reads, one prop each: what it draws is a function of these (CV_READS),
        // so the page's gen counts them and a frame after it drew may carry one
        int sl = uit_slot_find(e, src, strlen(src));
        if (sl < 0)
            return uit_fail(e, UIT_E_NAME, UIT_MSG("canvas reads=%s: no state of that name", "canvas reads=%s"), src);
        N->lit |= CV_READS;
        return add_prop(e, node, name, src, repr, PK_LIT, sl);
    }
    if (kind == UIT_CANVAS && !strcmp(name, "mark")) {
        // mark=False: a keys= canvas draws no ring while it holds focus (what it hosts marks it)
        if (src[0] == 'F' || src[0] == '0')
            N->lit |= CV_NOMARK;
        return add_prop(e, node, name, src, repr, PK_LIT, (N->lit & CV_NOMARK) == 0);
    }
    if (kind == UIT_TABLE && !strcmp(name, "row") && src[0] == '{') {
        // row= an int state: a row's height in pixels as the host measured it (the text's)
        int t = uit_tmpl_compile(e, src, model);
        if (t < 0)
            return t;
        if (e->tmpls[t].type != UIT_INT)
            return uit_check_fail(e, "T03", UIT_MSG("table row=%s is a %s, not an int", "%s %s"), src,
                                  uit_type_name(e->tmpls[t].type));
        N->btn = 0;
        return add_prop(e, node, name, src, repr, PK_TMPL, t);
    }
    if (kind == UIT_TABLE && !strcmp(name, "row")) {
        // row=: a row's height in the page's unit where a canvas child draws its rows
        long v = strtol(src, NULL, 10);
        if (v < 1 || v > 255)
            return uit_fail(e, UIT_E_KIND, UIT_MSG("table row=%s: 1 to 255", "row=%s"), src);
        N->btn = (uint16_t)v;
        return add_prop(e, node, name, src, repr, PK_LIT, (int)v);
    }
    if (kind == UIT_CANVAS && !strcmp(name, "grow")) {
        // a fill along a row, its w= the basis its share is over (CV_GROW)
        if (src[0] == 'T' || src[0] == '1')
            N->lit |= CV_GROW;
        return add_prop(e, node, name, src, repr, PK_LIT, (N->lit & CV_GROW) != 0);
    }
    if (kind == UIT_ROW && (!strcmp(name, "mid") || !strcmp(name, "grow") || !strcmp(name, "wrap"))) {
        // a row in a row centred on it (RW_MID); a row filling its stack (RW_GROW); a row whose
        // cells pack from its start and wrap (RW_WRAP)
        int bit = name[0] == 'm' ? RW_MID : name[0] == 'g' ? RW_GROW : RW_WRAP;
        if (strcmp(src, "True") && strcmp(src, "False") && strcmp(src, "1") && strcmp(src, "0"))
            return uit_fail(e, UIT_E_KIND, UIT_MSG("row %s=%s: True or False", "row %s=%s"), name, src);
        if (src[0] == 'T' || src[0] == '1')
            N->lit |= bit;
        return add_prop(e, node, name, src, repr, PK_LIT, (N->lit & bit) != 0);
    }
    if ((kind == UIT_SPLIT || kind == UIT_GRID) && (!strcmp(name, "pad") || !strcmp(name, "gap"))) {
        // an int at 1x (the engine scales it), given as a literal
        long v = -1;
        if (*src >= '0' && *src <= '9') {
            char *end;
            v = strtol(src, &end, 10);
            v = *end || v > 255 ? -1 : v;
        }
        if (v < 0)
            return uit_check_fail(e, "T03", UIT_MSG("%s %s=%s is not an int from 0 to 255", "%s %s %s"),
                                  uit_kind_names[kind], name, src);
        if (name[0] == 'p')
            N->btn = (uint16_t)v;
        else
            N->nbtn = (uint16_t)v;
        return add_prop(e, node, name, src, repr, PK_LIT, (int32_t)v);
    }
    if (kind == UIT_SPLIT && !strcmp(name, "align")) {
        static const char *const ALIGNS[] = {"start", "center", "end"};
        int i = lit_index(src, ALIGNS, 3);
        if (i < 0)
            return uit_fail(e, UIT_E_KIND, UIT_MSG("split %s=%s", "%s %s"), name, src);
        N->lit = (uint8_t)((N->lit & SP_RULE) | i);
        return add_prop(e, node, name, src, repr, PK_LIT, i);
    }
    if (kind == UIT_SPLIT && !strcmp(name, "rule")) {
        // rule=True: a rule down (or across) the middle of each gap between its cells
        if (src[0] == 'T' || src[0] == '1')
            N->lit |= SP_RULE;
        return add_prop(e, node, name, src, repr, PK_LIT, (N->lit & SP_RULE) != 0);
    }
    if (kind == UIT_GRID && (!strcmp(name, "cols") || !strcmp(name, "rows"))) {
        // cols in the lit's low nibble, rows in its high one
        long v = strtol(src, NULL, 10);
        if (v < 1 || v > 15)
            return uit_fail(e, UIT_E_KIND, UIT_MSG("grid %s=%s: 1 to 15", "%s %s"), name, src);
        N->lit = name[0] == 'c' ? (uint8_t)((N->lit & 0xf0) | v) : (uint8_t)((N->lit & 0x0f) | (v << 4));
        return add_prop(e, node, name, src, repr, PK_LIT, (int)v);
    }
    if (kind == UIT_BUTTON && !strcmp(name, "span")) {
        long v = strtol(src, NULL, 10);
        if (v < 1 || v > 15)
            return uit_fail(e, UIT_E_KIND, UIT_MSG("button span=%s: 1 to 15", "span=%s"), src);
        N->nbtn = (uint16_t)v;
        return add_prop(e, node, name, src, repr, PK_LIT, (int)v);
    }
    if (kind == UIT_BUBBLE && (!strcmp(name, "max") || !strcmp(name, "lines"))) {
        // max= the share of the room its text may take (1 the whole, in hundredths in btn); lines= at
        // most N lines of text (nbtn, 0 none), its last cut
        double v = strtod(src, NULL);
        if (name[0] == 'm')
            N->btn = (uint16_t)(v > 0 && v <= 1 ? v * 100 + 0.5 : 75);
        else
            N->nbtn = (uint16_t)(v < 0 ? 0 : v);
        return add_prop(e, node, name, src, repr, PK_LIT, (int)v);
    }
    if (kind == UIT_ROWS && !strcmp(name, "by")) {
        // by= a text field (an enum's values are texts in the store): each row draws the case
        // child ("case:VALUE") its value names; nbtn holds the field + 1
        int f = uit_field_find(e, N->slot, src, strlen(src));
        if (f < 0 || e->slots[N->slot].mf->ftype[f] != UIT_TEXT)
            return uit_check_fail(e, "T03", UIT_MSG("rows by=%s: no text or enum field of its rows", "rows by=%s"), src);
        N->nbtn = (uint16_t)(f + 1);
        return add_prop(e, node, name, src, repr, PK_LIT, f);
    }
    if (kind == UIT_ROWS && !strcmp(name, "dir")) {
        // dir="row": a row from a model, its cells along the placed row it stands in (row_kids);
        // dir="col": a column from a model, its cells down the placed stack it stands in (stack)
        if (strcmp(src, "row") && strcmp(src, "col"))
            return uit_fail(e, UIT_E_KIND, UIT_MSG("rows dir=%s: row or col", "rows dir=%s"), src);
        if (src[0] == 'c')
            N->lit |= RS_COL;
        return add_prop(e, node, name, src, repr, PK_LIT, src[0] == 'r');
    }
    if (!strcmp(name, "kind") && kind == UIT_ITEM) {
        N->lit = (uint8_t)!strcmp(src, "danger");
        return add_prop(e, node, name, src, repr, PK_LIT, N->lit);
    }
    if (!strcmp(name, "lend") && kind == UIT_TOOLS) {
        // lent to a site ("bar"): drawn there by its host, nothing on the page
        N->lit |= TL_LEND;
        return add_prop(e, node, name, src, repr, PK_LIT, 0);
    }
    if (!strcmp(name, "arg") && (kind == UIT_BUTTON || kind == UIT_LINK)) {
        // what the site hands its action (takes="arg"): a literal text, or an int (its repr its text)
        return add_prop(e, node, name, src, repr, PK_LIT, repr != NULL && !strcmp(repr, src));
    }
    if (!strcmp(name, "alone") && kind == UIT_BUTTON) {
        if (!strcmp(src, "True"))
            N->btn |= BT_ALONE;
        return add_prop(e, node, name, src, repr, PK_LIT, 0);
    }
    if (!strcmp(name, "look") && kind == UIT_TOAST) {
        // look="flat" (TS_FLAT): the pill in flat fills, the page's room its own; "badge"
        // (TS_BADGE) and "secret" (TS_SECRET): a banner as an achievement's, at the room's foot
        static const char *const LOOKS[] = {"flat", "badge", "secret"};
        int i = lit_index(src, LOOKS, 3);
        if (i < 0)
            return uit_fail(e, UIT_E_KIND, UIT_MSG("toast look=%s: \"flat\", \"badge\" or \"secret\"",
                                                   "toast look=%s"), src);
        N->lit |= (uint8_t)(1 << i);
        return add_prop(e, node, name, src, repr, PK_LIT, 1 << i);
    }
    if (!strcmp(name, "look") && kind == UIT_BUTTON) {
        // look="hero" (BT_HERO): the page's lead verb, half again a row's height, twice the pads, a
        // wider least width
        if (strcmp(src, "hero"))
            return uit_fail(e, UIT_E_KIND, UIT_MSG("button look=%s: \"hero\"", "button look=%s"), src);
        N->btn |= BT_HERO;
        return add_prop(e, node, name, src, repr, PK_LIT, 1);
    }
    if (kind == UIT_STEPPER && (!strcmp(name, "grow") || !strcmp(name, "tone"))) {
        // a fill along a row (BT_GROW); its value's ink, ink or dim (`lit`)
        if (name[0] == 'g') {
            if (!strcmp(src, "True"))
                N->btn |= BT_GROW;
            return add_prop(e, node, name, src, repr, PK_LIT, 0);
        }
        int i = lit_index(src, TONES, 2);
        if (i < 0)
            return uit_fail(e, UIT_E_KIND, UIT_MSG("stepper tone=%s: ink or dim", "stepper tone=%s"), src);
        N->lit = (uint8_t)i;
        return add_prop(e, node, name, src, repr, PK_LIT, i);
    }
    if (!strcmp(name, "grow") && kind == UIT_BUTTON) {
        // a fill along a row (BT_GROW): a bar item's label cut at its cell's end
        if (!strcmp(src, "True"))
            N->btn |= BT_GROW;
        return add_prop(e, node, name, src, repr, PK_LIT, 0);
    }
    if ((UIT_IS_TWO_WAY_OFF(kind) && (!strcmp(name, "when") || !strcmp(name, "off"))) ||
        (kind == UIT_FIELD && !strcmp(name, "grow"))) {
        // a field's, a toggle's or a slider's when=: greyed while it fails (`mark`), not shown
        // where off="hide"; a field's grow=: what a field in a row does already
        if (name[0] == 'w') {
            int c = uit_cond_compile(e, src, model);
            if (c < 0)
                return c;
            N->mark = (int16_t)c;
            return add_prop(e, node, name, src, repr, PK_COND, c);
        }
        if (name[0] == 'o' && !strcmp(src, "hide"))
            N->lit |= NL_HIDE;
        return add_prop(e, node, name, src, repr, PK_LIT, 0);
    }
    if (!strcmp(name, "marked") && kind == UIT_BUTTON) {
        int c = uit_cond_compile(e, src, model);
        if (c < 0)
            return c;
        N->mark = (int16_t)c;
        return add_prop(e, node, name, src, repr, PK_COND, c);
    }
    if (kind == UIT_TEXT_EDITOR && (!strcmp(name, "find") || !strcmp(name, "marks")))
        return add_prop(e, node, name, src, repr, PK_LIT, 0);       // the front end's: it draws the editor
    if (kind == UIT_TEXT_EDITOR && (!strcmp(name, "find_on") || !strcmp(name, "gutter"))) {
        int c = uit_cond_compile(e, src, model);
        if (c < 0)
            return c;
        return add_prop(e, node, name, src, repr, PK_COND, c);
    }
    if (!strcmp(name, "pointer") && kind == UIT_CANVAS)
        return add_prop(e, node, name, src, repr, PK_LIT, 0);     // its front end routes the pointer to it
    if (!strcmp(name, "ground") && kind == UIT_CANVAS)
        return add_prop(e, node, name, src, repr, PK_LIT, 0);     // its front end fills it (a theme role)
    if (!strcmp(name, "kind") && kind == UIT_BUTTON && strchr(src, '{')) {
        // a templated kind: its word drawn each frame (another word is normal)
        int t = uit_tmpl_compile(e, src, model);
        if (t < 0)
            return t;
        if (e->tmpls[t].type == UIT_BOOL || e->tmpls[t].type == UIT_MODEL)
            return uit_check_fail(e, "T03", UIT_MSG("button kind=%s is a %s, not a text", "%s %s"), src,
                                  uit_type_name(e->tmpls[t].type));
        N->lit = 0;
        return add_prop(e, node, name, src, repr, PK_TMPL, t);
    }
    if (!strcmp(name, "kind") && kind == UIT_BUTTON) {
        int i = lit_index(src, BKINDS, 6);
        N->lit = (uint8_t)(i < 0 ? 0 : i);
        return add_prop(e, node, name, src, repr, PK_LIT, i);
    }
    if (!strcmp(name, "field") && kind == UIT_TOGGLE) {
        // a toggle bound to a bool field of its list's row: the row's cell is its value
        int m = uit_model_of(e, node);
        int f = uit_field_find(e, m, src, strlen(src));
        if (f < 0 || e->slots[m].mf->ftype[f] != UIT_BOOL)
            return uit_fail(e, UIT_E_NAME, UIT_MSG("toggle .%s: no bool field of its rows", "toggle .%s"), src);
        N->slot = (int16_t)m;
        N->cur = (int16_t)f;
        N->lit |= NL_FIELD;
        return 0;
    }
    if (!strcmp(name, "field") && kind == UIT_SLIDER) {
        // a slider bound to an int field of its list's row: the row's cell is its value
        int m = uit_model_of(e, node);
        int f = uit_field_find(e, m, src, strlen(src));
        if (f < 0 || e->slots[m].mf->ftype[f] != UIT_INT)
            return uit_fail(e, UIT_E_NAME, UIT_MSG("slider .%s: no int field of its rows", "slider .%s"), src);
        N->slot = (int16_t)m;
        N->cur = (int16_t)f;
        N->lit |= NL_FIELD;
        return 0;
    }
    if (!strcmp(name, "field") && kind == UIT_SEG) {
        // a seg bound to an int field of its list's row: the row's cell is the index of its
        // item, its items the lines its text= renders over the row
        int m = uit_model_of(e, node);
        int f = uit_field_find(e, m, src, strlen(src));
        if (f < 0 || e->slots[m].mf->ftype[f] != UIT_INT)
            return uit_fail(e, UIT_E_NAME, UIT_MSG("seg .%s: no int field of its rows", "seg .%s"), src);
        N->slot = (int16_t)m;
        N->cur = (int16_t)f;
        N->lit |= NL_FIELD;
        return 0;
    }
    if (!strcmp(name, "bind")) {
        int s = uit_slot_find(e, src, strlen(src));
        int t = s < 0 ? 0 : e->slots[s].type;
        int ok = kind == UIT_TOGGLE ? t == UIT_BOOL : UIT_IS_LIST(kind) || kind == UIT_HINTS ? t == UIT_MODEL
                 : kind == UIT_TABS ? t == UIT_ENUM || t == UIT_ROWOF
                 : kind == UIT_SEG ? t == UIT_ENUM || t == UIT_ROWOF : kind == UIT_SLIDER || kind == UIT_CELLS ? t == UIT_INT
                 : kind == UIT_FIELD ? t == UIT_TEXT : kind == UIT_TEXT_VIEW ? t == UIT_TEXT || t == UIT_MODEL : 0;
        if (!ok)
            return uit_fail(e, UIT_E_NAME, UIT_MSG("%s bound to %s: no such state of its type", "%s bound to %s"), uit_kind_names[kind], src);
        N->slot = (int16_t)s;
        return 0;               // the head, not a prop the dump lists
    }
    if (!strcmp(name, "labels") && (kind == UIT_SEG || kind == UIT_TABS)) {
        for (int i = 0; i < e->nlabels; i++)
            if (!strcmp(uit_str(e, e->labels[i].name), src)) {
                N->cur = (int16_t)i;
                return add_prop(e, node, name, src, repr, PK_LIT, i);
            }
        return uit_fail(e, UIT_E_NAME, UIT_MSG("%s labels=%s: no label table of that name", "%s labels=%s"),
                        uit_kind_names[kind], src);
    }
    if (!strcmp(name, "icons") && kind == UIT_TABS) {
        // a label table of an icon a value: its index + 1 in nbtn
        for (int i = 0; i < e->nlabels; i++)
            if (!strcmp(uit_str(e, e->labels[i].name), src)) {
                N->nbtn = (uint16_t)(i + 1);
                return add_prop(e, node, name, src, repr, PK_LIT, i);
            }
        return uit_fail(e, UIT_E_NAME, UIT_MSG("tabs icons=%s: no label table of that name", "icons=%s"), src);
    }
    if (!strcmp(name, "offered") && kind == UIT_TABS) {
        // one prop a value offered on a condition: the condition its source, the value its repr
        int c = uit_cond_compile(e, src, model);
        if (c < 0)
            return c;
        return add_prop(e, node, name, src, repr ? repr : "", PK_COND, c);
    }
    if (!strcmp(name, "look") && (kind == UIT_SEG || kind == UIT_SLIDER || kind == UIT_PROGRESS)) {
        if (!strcmp(src, kind == UIT_SEG ? "cycle" : kind == UIT_SLIDER ? "steps" : "count"))
            N->lit |= kind == UIT_SEG ? NL_CYCLE : NL_STEPS;
        else if (kind == UIT_SEG && !strcmp(src, "swatches"))
            N->lit |= NL_SWATCH;
        else if (kind == UIT_SEG && !strcmp(src, "pictures"))
            N->lit |= NL_PICS;
        else if (kind == UIT_SLIDER && !strcmp(src, "blocks"))
            N->lit |= NL_BLOCKS;
        return add_prop(e, node, name, src, repr, PK_LIT, N->lit);
    }
    if (kind == UIT_FIELD && (!strcmp(name, "max") || !strcmp(name, "commit") || !strcmp(name, "secret"))) {
        if (name[0] == 'm')
            N->btn = (uint16_t)strtol(src, NULL, 10);
        else if (!strcmp(src, "True"))
            N->lit |= name[0] == 'c' ? NL_COMMIT : NL_SECRET;
        return add_prop(e, node, name, src, repr, PK_LIT, 0);
    }
    if (kind == UIT_FIELD && (!strcmp(name, "edit") || !strcmp(name, "keys"))) {
        // edit="open": focus coming onto it begins its edit; keys="number": the on-screen
        // keyboard's layout for it (#239), which draws nothing; keys="name": it takes a
        // name's characters alone (the contract checked the words)
        if (!strcmp(src, "open"))
            N->lit |= NL_OPEN;
        else if (!strcmp(src, "number"))
            N->lit |= NL_NUMBER;
        else if (!strcmp(src, "name"))
            N->lit |= NL_NAME;
        return add_prop(e, node, name, src, repr, PK_LIT, 0);
    }
    if (kind == UIT_CELLS && !strcmp(name, "edge")) {
        if (!strcmp(src, "True"))
            N->lit |= NL_EDGE;
        return add_prop(e, node, name, src, repr, PK_LIT, 0);
    }
    if ((!strcmp(name, "on") && (kind == UIT_TOGGLE || kind == UIT_SEG || kind == UIT_SLIDER || kind == UIT_CELLS ||
                                 kind == UIT_FIELD || kind == UIT_TABLE || kind == UIT_TABS || kind == UIT_BUBBLE ||
                                 kind == UIT_PICTURE || kind == UIT_HINTS)) ||
        (!strcmp(name, "changed") && kind == UIT_FIELD) || (!strcmp(name, "cut") && kind == UIT_BUBBLE) ||
        (!strcmp(name, "close") && (kind == UIT_POPOVER || kind == UIT_ROW || kind == UIT_GROUP)) ||
        ((kind == UIT_MONTH || kind == UIT_STEPPER) && (!strcmp(name, "prev") || !strcmp(name, "next"))) ||
        (kind == UIT_CELLS && !strcmp(name, "pick")) || (kind == UIT_PAGE && !strcmp(name, "shown"))) {
        // on= (and close=, a month's or a stepper's prev=) in `on`; changed= (cut=, next=, a cells' pick=, a
        // page's shown=) in `changed`
        for (int a = 0; a < e->nacts; a++)
            if (!strcmp(uit_str(e, e->acts[a].name), src)) {
                if (name[0] == 'o' || (name[0] == 'c' && name[1] == 'l') || (name[0] == 'p' && name[1] == 'r'))
                    N->on = (int16_t)a;
                else
                    N->changed = (int16_t)a;
                return add_prop(e, node, name, src, repr, PK_ACT, a);
            }
        return uit_fail(e, UIT_E_NAME, UIT_MSG("%s %s=%s: no such action", "%s %s=%s"), uit_kind_names[kind], name, src);
    }
    if (kind == UIT_TEXT_VIEW && !strcmp(name, "field")) {
        // a view of a model: each row's line, this text field
        int f = N->slot >= 0 ? uit_field_find(e, N->slot, src, strlen(src)) : -1;
        if (f < 0 || e->slots[N->slot].mf->ftype[f] != UIT_TEXT)
            return uit_fail(e, UIT_E_NAME, UIT_MSG("text_view .%s: no text field of its model", "text_view .%s"), src);
        N->cur = (int16_t)f;
        return 0;
    }
    if (kind == UIT_CARDS && !strcmp(name, "flow")) {
        // flow=True: its grid in the page's flow, scrolling with the page (CD_FLOW)
        N->lit = (uint8_t)((N->lit & ~CD_FLOW) | (src[0] == 'T' || src[0] == '1' ? CD_FLOW : 0));
        return add_prop(e, node, name, src, repr, PK_LIT, (N->lit & CD_FLOW) != 0);
    }
    if (kind == UIT_TEXT_VIEW && !strcmp(name, "gutter")) {
        // gutter=True: each line's number in a gutter before it (TV_GUTTER)
        N->lit = (uint8_t)((N->lit & ~TV_GUTTER) | (!strcmp(src, "True") ? TV_GUTTER : 0));
        return add_prop(e, node, name, src, repr, PK_LIT, (N->lit & TV_GUTTER) != 0);
    }
    if (kind == UIT_TEXT_VIEW && !strcmp(name, "look")) {
        // "well": its prose on a part's well (TV_WELL)
        N->lit = (uint8_t)((N->lit & ~TV_WELL) | (!strcmp(src, "well") ? TV_WELL : 0));
        return add_prop(e, node, name, src, repr, PK_LIT, (N->lit & TV_WELL) != 0);
    }
    if (kind == UIT_TEXT_VIEW && (!strcmp(name, "follow") || !strcmp(name, "wrap") || !strcmp(name, "face") ||
                                  !strcmp(name, "syntax"))) {
        static const char *const SYNTAXES[] = {"plain", "python", "lua", "json", "sgr", "markdown"};
        if (name[0] == 's') {
            int i = lit_index(src, SYNTAXES, 6);
            N->btn = (uint16_t)(i < 0 ? 4 : i);
        } else if (name[0] == 'f' && name[1] == 'o') {
            N->lit = (uint8_t)((N->lit & ~TV_FOLLOW) | (!strcmp(src, "True") ? TV_FOLLOW : 0));
        } else if (name[0] == 'w') {
            N->lit = (uint8_t)((N->lit & ~TV_WRAP) | (!strcmp(src, "word") ? TV_WRAP : 0));
        } else {
            N->lit = (uint8_t)((N->lit & ~TV_PROSE) | (!strcmp(src, "ui") ? TV_PROSE : 0));
        }
        return add_prop(e, node, name, src, repr, PK_LIT, N->lit);
    }
    if (!strcmp(name, "current") && (kind == UIT_ROWS || kind == UIT_CARDS)) {
        int s = uit_slot_find(e, src, strlen(src));
        int t = s < 0 ? 0 : e->slots[s].type;
        if (t != UIT_TEXT && t != UIT_ROWOF && t != UIT_INT)
            return uit_fail(e, UIT_E_NAME, UIT_MSG("rows current=%s: no text, int or row_of of that name", "rows current=%s"), src);
        N->current = (int16_t)s;
        return add_prop(e, node, name, src, repr, PK_LIT, s);
    }
    if (!strcmp(name, "wash") && kind == UIT_POPOVER) {
        // what it washes under it: the page, the view its anchor lies in, nothing (lit: the
        // toolkit's wash + 1)
        static const char *const WASHES[] = {"none", "page", "view"};
        int i = lit_index(src, WASHES, 3);
        if (i < 0)
            return uit_fail(e, UIT_E_KIND, UIT_MSG("popover wash=%s", "wash=%s"), src);
        N->lit = (uint8_t)(i + 1);
        return add_prop(e, node, name, src, repr, PK_LIT, i);
    }
    if (!strcmp(name, "check") && kind == UIT_ROWS) {
        // check=True: each row's link a pick, the current one's checked (RS_CHECK)
        if (!strcmp(src, "True"))
            N->lit |= RS_CHECK;
        return add_prop(e, node, name, src, repr, PK_LIT, (N->lit & RS_CHECK) != 0);
    }
    if (!strcmp(name, "cur") && UIT_IS_LIST(kind)) {
        int s = uit_slot_find(e, src, strlen(src));
        if (s < 0 || e->slots[s].type != UIT_ROWOF)
            return uit_fail(e, UIT_E_NAME, UIT_MSG("%s cur=%s: no row_of of that name", "%s cur=%s"),
                            uit_kind_names[kind], src);
        N->cur = (int16_t)s;
        return add_prop(e, node, name, src, repr, PK_LIT, s);
    }
    if (!strcmp(name, "changed") && UIT_IS_LIST(kind)) {
        for (int a = 0; a < e->nacts; a++)
            if (!strcmp(uit_str(e, e->acts[a].name), src)) {
                N->changed = (int16_t)a;
                return add_prop(e, node, name, src, repr, PK_ACT, a);
            }
        return uit_fail(e, UIT_E_NAME, UIT_MSG("%s changed=%s: no such action", "%s changed=%s"),
                        uit_kind_names[kind], src);
    }
    if (!strcmp(name, "cols") && kind == UIT_TABLE)
        return add_prop(e, node, name, src, repr, PK_LIT, 0);      // a column's header, one prop each
    if (!strcmp(name, "look") && kind == UIT_GROUP) {
        // "card": a captionless group drawn as a card (lit 1); "rules": its rows ruled apart (2)
        N->lit = (uint8_t)(!strcmp(src, "card") ? 1 : !strcmp(src, "rules") ? 2 : 0);
        return add_prop(e, node, name, src, repr, PK_LIT, N->lit);
    }
    if (!strcmp(name, "look") && kind == UIT_FOOT) {
        // "share": its buttons share its width (lit 1); "band" (2): its rows edge to edge on
        // the alternate surface under a rule; "end" (0): at its end
        N->lit = (uint8_t)(!strcmp(src, "share") ? 1 : !strcmp(src, "band") ? 2 : 0);
        return add_prop(e, node, name, src, repr, PK_LIT, N->lit);
    }
    if ((!strcmp(name, "follow") || !strcmp(name, "snap")) && kind == UIT_SCROLL) {
        // follow=True: its first frame at its foot, a row that comes moving the view (SC_FOLLOW);
        // snap=True: whole units, the cues where some are left out above or below (SC_SNAP)
        int bit = name[0] == 'f' ? SC_FOLLOW : SC_SNAP, on = !strcmp(src, "True");
        N->lit = (uint8_t)((N->lit & ~bit) | (on ? bit : 0));
        return add_prop(e, node, name, src, repr, PK_LIT, on);
    }
    if (!strcmp(name, "buttons") && kind == UIT_DIALOG)
        return add_prop(e, node, name, src, repr, PK_LIT, 0);
    if (!strcmp(name, "kind") && kind == UIT_DIALOG) {
        // its verb (the last button) in the danger look (DL_DANGER); else the primary
        N->lit = (uint8_t)((N->lit & ~DL_DANGER) | (!strcmp(src, "danger") ? DL_DANGER : 0));
        return add_prop(e, node, name, src, repr, PK_LIT, (N->lit & DL_DANGER) != 0);
    }
    if (!strcmp(name, "look") && kind == UIT_CARDS) {
        // "carousel": one row of tiles that snaps, its centre card's words under it (CD_CAROUSEL);
        // "shelf": cards in the rows the band holds, scrolling across (CD_SHELF); "icons": tiles
        // in the columns it holds, scrolling down (CD_ICONS); "column": tiles down the left edge,
        // column after column, shrinking until they fit (CD_COLUMN)
        int lk = !strcmp(src, "carousel") ? CD_CAROUSEL : !strcmp(src, "shelf") ? CD_SHELF
                 : !strcmp(src, "icons") ? CD_ICONS : !strcmp(src, "column") ? CD_COLUMN : 0;
        if (!lk)
            return uit_fail(e, UIT_E_KIND, UIT_MSG("cards look=%s: carousel, shelf, icons, column", "cards look=%s"),
                            src);
        N->lit |= (uint8_t)lk;
        return add_prop(e, node, name, src, repr, PK_LIT, lk);
    }
    if (!strcmp(name, "look") && kind == UIT_PICTURE) {
        // "tile": a carousel's tile of its own, at its place, its shadow round it (PC_TILE)
        if (strcmp(src, "tile"))
            return uit_fail(e, UIT_E_KIND, UIT_MSG("picture look=%s: tile", "picture look=%s"), src);
        N->lit |= PC_TILE;
        return add_prop(e, node, name, src, repr, PK_LIT, PC_TILE);
    }
    if (!strcmp(name, "look") && kind == UIT_DIALOG) {
        // "keys": on the T-Deck its buttons are the band's Enter and Esc, no row of them (DL_KEYS)
        if (strcmp(src, "keys"))
            return uit_fail(e, UIT_E_KIND, UIT_MSG("dialog look=%s: keys", "dialog look=%s"), src);
        N->lit |= DL_KEYS;
        return add_prop(e, node, name, src, repr, PK_LIT, 1);
    }
    return uit_fail(e, UIT_E_KIND, UIT_MSG("%s=: a prop this engine does not draw on this kind (%d)", "%s= %d"), name, kind);
}

int uit_node_action(uit_t *e, int node, int action)
{
    if (node < 0 || node >= e->nnodes || action < 0 || action >= e->nacts)
        return UIT_E_ARG;
    uit_node_t *N = &e->nodes[node];
    if (N->kind == UIT_DIALOG) {
        if (UIT_GROW(e, btns, nbtns, cbtns))
            return UIT_E_NOMEM;
        if (N->nbtn == 0)
            N->btn = (uint16_t)e->nbtns;
        else if (N->btn + N->nbtn != e->nbtns)
            return UIT_E_ARG;
        e->btns[e->nbtns++] = (int16_t)action;
        N->nbtn++;
        return 0;
    }
    N->act = (int16_t)action;
    return 0;
}

static int names_engine_value(const char *src)
{
    return (strstr(src, "@focus") ? GV_FOCUS : 0) | (strstr(src, "@input") || strstr(src, "@touch") ? GV_INPUT : 0);
}

// The states a template, a condition, a node reads (`_reads`): marked in m[slot].
static void mark_tmpl(const uit_t *e, int t, uint8_t *m);

static void mark_cond(const uit_t *e, int c, uint8_t *m)
{
    if (c < 0)
        return;
    const uit_cond_t *C = &e->conds[c];
    for (int i = 0; i < C->n; i++) {
        const uit_term_t *T = &e->terms[C->first + i];
        if ((T->rk == RK_SLOT || T->rk == RK_ROWOF) && T->ref >= 0)
            m[T->ref] = 1;
    }
}

static void mark_tmpl(const uit_t *e, int t, uint8_t *m)
{
    if (t < 0)
        return;
    const uit_tmpl_t *T = &e->tmpls[t];
    for (int i = 0; i < T->ncode; i++) {
        const uit_op_t *o = &e->ops[T->code + i];
        if (o->op == OP_CHOICE) {
            mark_cond(e, o->ref, m);
            mark_tmpl(e, (int16_t)o->c, m);
            mark_tmpl(e, (int16_t)o->d, m);
        } else if ((o->rk == RK_SLOT || o->rk == RK_ROWOF) && o->ref >= 0) {
            m[o->ref] = 1;
        }
    }
}

// Node `k`'s own reads; a list's cur= where `cur`; hint= alone where `hint_only`.
static int cond_engine(const uit_t *e, int c)
{
    if (c < 0)
        return 0;
    const uit_cond_t *C = &e->conds[c];
    for (int i = 0; i < C->n; i++) {
        int rk = e->terms[C->first + i].rk;
        if (rk != RK_SLOT && rk != RK_ROWOF && rk != RK_FIELD)
            return 1;
    }
    return 0;
}

uint32_t uit_tmpl_key(const uit_t *e, int t, int *engine)
{
    if (t < 0)
        return 0;
    uint32_t g = 0;
    const uit_tmpl_t *T = &e->tmpls[t];
    for (int i = 0; i < T->ncode; i++) {
        const uit_op_t *o = &e->ops[T->code + i];
        if (o->op == OP_CHOICE) {
            *engine |= cond_engine(e, o->ref);
            uint8_t m[UIT_GEN_SLOTS] = {0};
            mark_cond(e, o->ref, m);
            for (int j = 0; j < e->nslots && j < UIT_GEN_SLOTS; j++)
                if (m[j])
                    g += (uint32_t)e->slots[j].ver * (uint32_t)(2 * j + 1);
            g += uit_tmpl_key(e, (int16_t)o->c, engine) + uit_tmpl_key(e, (int16_t)o->d, engine);
        } else if ((o->rk == RK_SLOT || o->rk == RK_ROWOF) && o->ref >= 0) {
            g += (uint32_t)e->slots[o->ref].ver * (uint32_t)(2 * o->ref + 1);
        } else if (o->rk && o->rk != RK_FIELD) {
            *engine = 1;
        }
    }
    return g;
}

static void mark_node(const uit_t *e, int k, uint8_t *m, int cur, int hint_only)
{
    const uit_node_t *N = &e->nodes[k];
    for (int p = N->props; p != (int)UIT_NONE; p = e->props[p].next) {
        const uit_prop_t *P = &e->props[p];
        const char *name = uit_str(e, P->name);
        if (hint_only && strcmp(name, "hint"))
            continue;
        if (P->kind == PK_TMPL)
            mark_tmpl(e, P->idx, m);
        else if (P->kind == PK_COND)
            mark_cond(e, P->idx, m);
        else if (P->kind == PK_LIT && (!strcmp(name, "current") || !strcmp(name, "reads")) && P->idx >= 0)
            m[P->idx] = 1;
    }
    if (hint_only)
        return;
    if (N->slot >= 0 && !((N->kind == UIT_TOGGLE || N->kind == UIT_SLIDER) && (N->lit & NL_FIELD)))
        m[N->slot] = 1;         // its bound state, its model, its switch's
    if (cur && UIT_IS_LIST(N->kind) && N->cur >= 0)
        m[N->cur] = 1;
}

static void mark_tree(const uit_t *e, int k, uint8_t *m, int cur, int hint_only)
{
    mark_node(e, k, m, cur, hint_only);
    for (int g = e->nodes[k].kid; g != (int)UIT_NONE; g = e->nodes[g].next)
        mark_tree(e, g, m, cur, hint_only);
}

// What lies outside the page's cells (a cards list each, but one in the page's flow): each node's reads but a cur='s, and
// every hint= inside a cell too.
static void mark_rest(const uit_t *e, int k, uint8_t *m)
{
    if (e->nodes[k].kind == UIT_CARDS && !(e->nodes[k].lit & CD_FLOW)) {
        mark_tree(e, k, m, 0, 1);
        return;
    }
    if (e->nodes[k].kind == UIT_TEXT_VIEW)
        return;                         // a lines view is a region: its rows are its own record's
    mark_node(e, k, m, 0, 0);
    for (int g = e->nodes[k].kid; g != (int)UIT_NONE; g = e->nodes[g].next)
        if (e->nodes[k].kind != UIT_SPLIT || e->nodes[g].kind != UIT_GROUP)
            mark_rest(e, g, m);         // a split's group is a region: its reads are its own gen's
}

static void mark_cells(const uit_t *e, int k, uint8_t *m)
{
    if ((e->nodes[k].kind == UIT_CARDS && !(e->nodes[k].lit & CD_FLOW)) || e->nodes[k].kind == UIT_TEXT_VIEW) {
        mark_tree(e, k, m, 0, 0);
        return;
    }
    for (int g = e->nodes[k].kid; g != (int)UIT_NONE; g = e->nodes[g].next)
        if (e->nodes[k].kind == UIT_SPLIT && e->nodes[g].kind == UIT_GROUP)
            mark_tree(e, g, m, 0, 0);
        else
            mark_cells(e, g, m);
}

int32_t uit_cell_gen(uit_t *e, int k)
{
    uint8_t m[UIT_GEN_SLOTS] = {0};
    uint32_t g = (uint32_t)e->gen + e->edits + e->gv;
    if (e->nslots > UIT_GEN_SLOTS)
        return -1;
    mark_tree(e, k, m, 0, 0);
    for (int i = 0; i < e->nslots; i++)
        if (m[i])
            g += e->slots[i].ver;
    return (int32_t)(g & 0x7fffffff);
}

// What the page's gen counts (`_cell_gens`, `_gen_safe`): every state but those only a cards
// list's rows, a split's group or a lines view read (each region carries a gen of its own,
// `uit_cell_gen`; a lines view's rows are its view record's, moy_ui_api_text_view) and
// those only a list's
// cur= names (focus, which the toolkit draws); and whether it may carry one: no text of the build
// names an engine value (a canvas draws what no state says, but for one that names its states,
// reads=: a frame after one drew carries none, `gen_ok`).
static void gen_of_build(uit_t *e)
{
    e->gen_safe = e->nslots <= UIT_GEN_SLOTS;
    e->gen_vals = 0;
    for (int t = e->m_tmpls; t < e->ntmpls; t++)
        e->gen_vals |= (uint8_t)names_engine_value(uit_str(e, e->tmpls[t].src));
    for (int c = e->m_conds; c < e->nconds; c++)
        e->gen_vals |= (uint8_t)names_engine_value(uit_str(e, e->conds[c].src));
    for (int i = 0; i < e->nslots; i++)
        e->slots[i].in_gen = 1;
    if (!e->gen_safe || !e->nnodes)
        return;
    uint8_t rest[UIT_GEN_SLOTS] = {0}, mine[UIT_GEN_SLOTS] = {0}, seen[UIT_GEN_SLOTS] = {0},
            focus[UIT_GEN_SLOTS] = {0};
    mark_rest(e, 0, rest);
    for (int a = 0; a < e->nacts; a++) {
        mark_tmpl(e, e->acts[a].hint, rest);
        mark_cond(e, e->acts[a].when, rest);
    }
    mark_cells(e, 0, mine);
    mark_tree(e, 0, seen, 0, 0);
    mark_tree(e, 0, focus, 1, 0);
    for (int i = 0; i < e->nslots; i++)
        if (!rest[i] && (mine[i] || (focus[i] && !seen[i])))
            e->slots[i].in_gen = 0;
}

// An array a build grew by doublings held at what it holds: a page keeps its tree as long as it
// lives, and a build that comes again grows it from there.
static void trim(void **p, int n, int *cap, size_t size)
{
    if (n <= 0 || n >= *cap)
        return;
    void *q = UIT_REALLOC(*p, (size_t)n * size);
    if (q) {
        *p = q;
        *cap = n;
    }
}

#define TRIM(e, arr, n, cap) trim((void **)&(e)->arr, (e)->n, &(e)->cap, sizeof *(e)->arr)

int uit_build_end(uit_t *e)
{
    intern_drop(e);
    TRIM(e, slots, nslots, cslots);
    TRIM(e, acts, nacts, cacts);
    TRIM(e, tmpls, ntmpls, ctmpls);
    TRIM(e, ops, nops, cops);
    TRIM(e, conds, nconds, cconds);
    TRIM(e, terms, nterms, cterms);
    TRIM(e, nodes, nnodes, cnodes);
    TRIM(e, props, nprops, cprops);
    TRIM(e, btns, nbtns, cbtns);
    TRIM(e, labels, nlabels, clabels);
    if (e->pool.n && e->pool.n < e->pool.cap) {
        char *q = UIT_REALLOC(e->pool.p, e->pool.n);
        if (q) {
            e->pool.p = q;
            e->pool.cap = e->pool.n;
        }
    }
    e->has_panes = 0;
    for (int k = 0; k < e->nnodes; k++) {
        if (e->nodes[k].kind == UIT_PANES)
            e->has_panes = 1;
        const uit_node_t *N = &e->nodes[k];
        if (N->kind == UIT_DIALOG) {    // labels=: one a button, or none
            int nl = 0;
            for (int p = N->props; p != (int)UIT_NONE; p = e->props[p].next)
                nl += !strcmp(uit_str(e, e->props[p].name), "labels");
            if (nl && nl != N->nbtn)
                return uit_check_fail(e, "N01", UIT_MSG("dialog %s has %d labels for its %d buttons", "%s %d %d"),
                                      uit_str(e, N->key), nl, (int)N->nbtn);
        }
        if (N->kind == UIT_SPLIT)       // a popover's split lays out pictures, labels, progress, groups of them
            for (int p = N->parent; p != (int)UIT_NONE; p = e->nodes[p].parent)
                if (e->nodes[p].kind == UIT_POPOVER)
                    for (int g = N->kid; g != (int)UIT_NONE; g = e->nodes[g].next) {
                        int gk = e->nodes[g].kind;
                        if (gk != UIT_PICTURE && gk != UIT_GROUP && gk != UIT_LABEL && gk != UIT_PROGRESS)
                            return uit_fail(e, UIT_E_KIND, UIT_MSG("a %s in a popover's split", "%s"), uit_kind_names[gk]);
                    }
    }
    e->gen++;
    e->fresh = 1;
    gen_of_build(e);
    return e->nnodes ? 0 : uit_fail(e, UIT_E_ARG, UIT_MSG("a build with no page", ""));
}

void uit_on_draw(uit_t *e, uit_draw_fn fn, void *ud)
{
    e->draw_fn = fn;
    e->draw_ud = ud;
}

int uit_draw_clip(const uit_t *e, int32_t out[4])
{
    if (!e->draw_clip_on)
        return 0;
    memcpy(out, e->draw_clip, sizeof e->draw_clip);
    return 1;
}

void uit_on_pic(uit_t *e, uit_pic_fn fn, void *ud)
{
    e->pic_fn = fn;
    e->pic_ud = ud;
}

void uit_pics_moved(uit_t *e)
{
    e->edits++;
}

void uit_open(uit_t *e)
{
    e->still_ok = 0;
    e->nids = e->nprev = 0;
    e->has_focused = 0;
    e->focus_key[0] = 0;
    uit_want_focus(e, NULL);
    for (int i = 0; i < e->nslots; i++) {
        UIT_FREE(e->slots[i].sync);
        e->slots[i].sync = NULL;
        e->slots[i].sync_set = 0;
    }
    for (int i = 0; i < e->norders; i++)
        e->orders[i].has = 0;
    for (int i = 0; i < e->ndrafts; i++)
        e->drafts[i].has = 0;
    e->nevs = e->evat = 0;
    e->evtext.n = 0;
    free_drew(e);
    if (e->nnodes) {            // the page the store keeps draws as a fresh build's
        e->gen++;
        e->fresh = 1;
    }
}

int uit_want_focus(uit_t *e, const char *key)
{
    for (int i = 0; key && i < e->nids; i++)
        if (e->ids[i].dup && !strcmp(e->ids[i].id, key))
            return uit_check_fail(e, "N08", UIT_MSG("two shown nodes are keyed %s", "%s"), key);
    UIT_FREE(e->want);
    e->want = NULL;
    if (key) {
        size_t n = strlen(key);
        e->want = UIT_MALLOC(n + 1);
        if (e->want)
            memcpy(e->want, key, n + 1);
    }
    return 0;
}

// -- events and the trace ---------------------------------------------------------

int uit_event(uit_t *e, int kind, int a, int b, int c, const char *text, size_t n)
{
    if (UIT_GROW(e, evs, nevs, cevs))
        return UIT_E_NOMEM;
    int at = uit_buf_put(&e->evtext, text ? text : "", text ? n : 0);
    uit_ev_t E = {(uint8_t)kind, (int16_t)a, (int16_t)b, (int16_t)c, (uint32_t)(at < 0 ? 0 : at)};
    e->evs[e->nevs++] = E;
    return 0;
}

int uit_next(uit_t *e, int32_t ev[3], char *buf, size_t cap)
{
    if (e->evat >= e->nevs) {
        e->nevs = e->evat = 0;
        e->evtext.n = 0;
        return UIT_EV_NONE;
    }
    const uit_ev_t *E = &e->evs[e->evat++];
    ev[0] = E->a;
    ev[1] = E->b;
    ev[2] = E->c;
    if (buf && cap) {
        const char *t = e->evtext.p + E->text;
        size_t n = strlen(t);
        if (n >= cap)
            n = cap - 1;
        memcpy(buf, t, n);
        buf[n] = 0;
    }
    return E->kind;
}

void uit_trace(uit_t *e, const char *kind, const char *name, const char *fmt, ...)
{
    if (!(e->flags & UIT_F_TRACE))
        return;
    uit_buf_t *b = &e->trace;
    uit_buf_printf(b, "%s\x01%s\x01", kind, name);
    char tmp[512];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(tmp, sizeof tmp, fmt, ap);
    va_end(ap);
    if (n > (int)sizeof tmp - 1)
        n = sizeof tmp - 1;
    uit_buf_put(b, tmp, n < 0 ? 0 : (size_t)n);
}

int uit_trace_next(uit_t *e, char *buf, size_t cap)
{
    if (e->trace_at >= e->trace.n) {
        e->trace.n = e->trace_at = 0;
        return -1;
    }
    const char *t = e->trace.p + e->trace_at;
    size_t n = strlen(t);
    e->trace_at += (uint32_t)n + 1;
    if (n >= cap)
        n = cap - 1;
    memcpy(buf, t, n);
    buf[n] = 0;
    return (int)n;
}

// -- the dump ---------------------------------------------------------------------

static void dump_node(uit_t *e, uit_buf_t *b, int k, int depth, int model, int row)
{
    const uit_node_t *N = &e->nodes[k];
    for (int i = 0; i < depth; i++)
        uit_buf_printf(b, "  ");
    uit_buf_printf(b, "%s ", uit_kind_names[N->kind]);
    const char *key = uit_str(e, N->key);
    uit_buf_repr(b, key, strlen(key));
    if (N->act >= 0) {
        const uit_act_t *A = &e->acts[N->act];
        uit_buf_printf(b, "  action=%s", uit_str(e, A->name));
        if (!uit_act_can(e, N->act, -1, -1))
            uit_buf_printf(b, "(off: %s)", uit_str(e, e->conds[A->when].src));
    }
    if ((N->kind == UIT_TOGGLE || N->kind == UIT_SLIDER || N->kind == UIT_FIELD) && N->slot >= 0) {
        const uit_slot_t *S = &e->slots[N->slot];
        uit_buf_printf(b, "  bind=%s:%s = ", uit_str(e, S->name), uit_type_name(S->type));
        if (N->kind == UIT_FIELD && (N->lit & NL_SECRET)) {
            uit_buf_printf(b, "'");
            for (uint32_t i = 0; i < S->sn; i++)
                if ((S->s[i] & 0xC0) != 0x80)
                    uit_buf_printf(b, "*");
            uit_buf_printf(b, "'");
        } else {
            uit_slot_repr(e, b, N->slot);
        }
    }
    for (int p = N->props; p != (int)UIT_NONE; p = e->props[p].next) {
        const uit_prop_t *P = &e->props[p];
        const char *name = uit_str(e, P->name), *src = uit_str(e, P->src);
        if (P->kind == PK_LIT && (!strcmp(name, "buttons") || !strcmp(name, "labels")))
            continue;           // the dialog's are listed after; a seg's table is in its words
        uit_buf_printf(b, "  %s=", name);
        if (P->kind == PK_ACT) {
            uit_buf_printf(b, "%s", src);
        } else if (P->kind == PK_COND) {
            uit_buf_repr(b, src, strlen(src));
            uit_buf_printf(b, " = %s", uit_cond_eval(e, P->idx, model, row) ? "True" : "False");
        } else if (P->kind == PK_TMPL && P->repr != UIT_NONE && !strchr(src, '{')) {
            uit_buf_printf(b, "%s", uit_str(e, P->repr));
        } else if (P->kind == PK_TMPL) {
            uint32_t n;
            uint32_t at = uit_tmpl_render(e, P->idx, model, row, &n);
            if (strchr(src, '{')) {
                uit_buf_repr(b, src, strlen(src));
                uit_buf_printf(b, " = ");
            }
            uit_buf_repr(b, e->scratch.p + at, n);
        } else if (P->repr != UIT_NONE) {
            uit_buf_printf(b, "%s", uit_str(e, P->repr));
        } else {
            uit_buf_repr(b, src, strlen(src));
        }
    }
    if (N->kind == UIT_DIALOG) {
        uit_buf_printf(b, "  buttons=");
        for (int i = 0; i < N->nbtn; i++)
            uit_buf_printf(b, "%s%s", i ? "," : "", uit_str(e, e->acts[e->btns[N->btn + i]].name));
    }
    uit_buf_printf(b, "\n");
    if (N->kind == UIT_ROWS) {
        const uit_slot_t *M = &e->slots[N->slot];
        for (int i = 0; i < depth; i++)
            uit_buf_printf(b, "  ");
        uit_buf_printf(b, "  [%d rows of %s]\n", M->nrows, uit_str(e, M->name));
        for (int r = 0; r < M->nrows; r++) {
            for (int i = 0; i < depth; i++)
                uit_buf_printf(b, "  ");
            uit_buf_printf(b, "  row ");
            const char *rk = uit_cell(e, N->slot, r, M->key);
            uit_buf_repr(b, rk, strlen(rk));
            uit_buf_printf(b, "\n");
            int body = uit_row_body(e, k, r);
            for (int c = body < 0 ? (int)UIT_NONE : e->nodes[body].kid; c != (int)UIT_NONE; c = e->nodes[c].next)
                dump_node(e, b, c, depth + 2, N->slot, r);
        }
        return;
    }
    for (int c = N->kid; c != (int)UIT_NONE; c = e->nodes[c].next)
        dump_node(e, b, c, depth + 1, model, row);
}

int uit_dump(uit_t *e, char *buf, size_t cap)
{
    uit_buf_t b = {0};
    e->scratch.n = 0;
    if (e->nnodes)
        dump_node(e, &b, 0, 0, -1, -1);
    size_t n = b.n;
    if (n && b.p[n - 1] == '\n')
        n--;
    if (buf && cap) {
        size_t m = n < cap - 1 ? n : cap - 1;
        memcpy(buf, b.p, m);
        buf[m] = 0;
    }
    uit_buf_free(&b);
    return (int)n;
}

int uit_stats(const uit_t *e, int32_t out[8])
{
    out[0] = e->nnodes;
    out[1] = e->nnodes * (int32_t)sizeof(uit_node_t);
    out[2] = e->ntmpls * (int32_t)sizeof(uit_tmpl_t) + e->nops * (int32_t)sizeof(uit_op_t);
    out[3] = e->nconds * (int32_t)sizeof(uit_cond_t) + e->nterms * (int32_t)sizeof(uit_term_t);
    out[4] = (int32_t)e->pool.n;
    out[5] = e->nprops * (int32_t)sizeof(uit_prop_t);
    int32_t st = e->nslots * (int32_t)sizeof(uit_slot_t);
    for (int i = 0; i < e->nslots; i++)
        st += (int32_t)(e->slots[i].scap + e->slots[i].cells_n + 4u * (uint32_t)(e->slots[i].nrows * e->slots[i].nf));
    out[6] = st;
    out[7] = (int32_t)sizeof(uit_t) + e->cids * 2 * (int32_t)sizeof(uit_id_t) + (int32_t)e->scratch.cap;
    return 0;
}
