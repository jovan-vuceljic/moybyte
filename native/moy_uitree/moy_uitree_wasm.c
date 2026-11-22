// The UI engine's wasm rows (moy_uitree_wasm.h): each a compiled app's
// `moybyte.app` import, over the run's one store.

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "moy_uitree.h"
#include "moy_uitree_int.h"
#include "moy_uitree_wasm.h"
#include "moy_ui_run.h"

#if defined(__has_include) && __has_include("moy_log.h")
#include "moy_log.h"
#pragma weak moy_log_write
#define LOG(level, text, n) \
    do { if (moy_log_write != NULL) moy_log_write((level), MOY_LOG_CURRENT, (text), (n)); } while (0)
#else
#define LOG(level, text, n) ((void)(level), (void)(text), (void)(n))
#endif
enum { LOG_ERR = 3, LOG_INFO = 6 };

// The module that drives a compiled run (none in a library with no compiled run).
#pragma weak moycore_ui_target
#pragma weak moycore_ui_snap
#pragma weak moycore_ui_draw_call

#define DEPTH 8                 // the pages a stack remembers a focus for
#define CANVASES 8              // the canvases of a page a pointer is routed to
#define BACK_EV 0x10000         // `next`'s answer for the bar's back with a page to pop (UT_BACK)

// An action owed to the app, handed out by `next` in the order the frame took it.
typedef struct {
    int act;                    // its index; -1: the bar's back pops the page
    int32_t ev[5];              // its model slot, row, and a pointer's kind, x, y
    uint32_t src;               // where it came from, in `qtext`
} owed_t;

// What a run's app keeps beside its store.
typedef struct {
    uit_t *e;
    uint32_t serial;            // the run it is of
    int live;                   // a run made it
    int err;                    // the run's first refusal (0 none), latched
    char errline[320];
    int handler;                // the action whose handler runs (handed out by next), -1 none
    int opened;                 // the visit is open: a write is traced from here on
    int hook_open;              // the `opened` hook, owed to the next `next` (-1 none)
    uint32_t frames;
    int page;                   // the page node of the build, -1 none
    uit_buf_t when;             // each action's when= source, NUL-terminated, by `when_at`
    uint32_t *when_at;
    int nwhen, cwhen;
    uit_buf_t tmp;              // the call's texts, NUL-terminated
    int depth;                  // the page stack's depth: the leading number of the page's id
    char refocus[DEPTH][48];    // the key focused on each page as the next was pushed
    int refocus_due;            // build_end puts the focus back on this depth's key (-1 none)
    char pname[48];             // the page's name (its id after the depth), for a role key's trace
    char title[64];             // the page's title, for a trace's "on 'TITLE'"
    struct {                    // each canvas of the page a pointer is routed to: its pointer= action,
        int node, act;          // the rect the last frame drew it at and that frame
        int32_t r[4];
        uint32_t frame;
        char key[32];
    } ptr[CANVASES];
    int nptr;
    int held;                   // the canvas a press started on (its `ptr`), held until release; -1 none
    int32_t hx, hy;             // ...the press's last point
    int trapped;                // the app's draw trapped in this frame
    owed_t *q;                  // the actions owed, [qat, qn)
    int qn, qat, qcap;
    uit_buf_t qtext;
} app_t;

// Made by a compiled run's first row through the engine's allocator (PSRAM on
// a board) and freed as the run ends, so an image costs no internal SRAM for it.
static app_t *s_app;

// A canvas's draw: its rect kept for the pointer, and the app's draw called.
static void drawn(void *ud, int node, int x, int y, int w, int h) {
    app_t *a = ud;
    for (int i = 0; i < a->nptr; i++) {
        if (a->ptr[i].node == node) {
            a->ptr[i].r[0] = x, a->ptr[i].r[1] = y, a->ptr[i].r[2] = w, a->ptr[i].r[3] = h;
            a->ptr[i].frame = a->frames;
        }
    }
    if (moycore_ui_draw_call != NULL && !a->trapped && moycore_ui_draw_call(node, x, y, w, h) < 0) {
        a->trapped = 1;
    }
}

static void app_drop(app_t *a) {
    if (a->e != NULL) {
        uit_free(a->e);
    }
    uit_buf_free(&a->when);
    uit_buf_free(&a->tmp);
    uit_buf_free(&a->qtext);
    UIT_FREE(a->when_at);
    UIT_FREE(a->q);
    memset(a, 0, sizeof *a);
}

void moy_uitree_wasm_end(void) {
    if (s_app != NULL) {
        app_drop(s_app);
        UIT_FREE(s_app);
        s_app = NULL;
    }
}

// The run's app: made by the run's first row, dropped when another run opens.
static app_t *app(void) {
    if (s_app == NULL) {
        s_app = UIT_MALLOC(sizeof *s_app);
        if (s_app == NULL) {
            return NULL;
        }
        memset(s_app, 0, sizeof *s_app);
    }
    app_t *a = s_app;
    uint32_t tick = 0, serial = 0;
    if (moycore_ui_snap != NULL) {
        (void)moycore_ui_snap(&tick, &serial);
    }
    if (a->live && a->serial != serial) {
        app_drop(a);
    }
    if (!a->live) {
        a->e = uit_new();
        if (a->e == NULL) {
            return NULL;
        }
        a->live = 1;
        a->serial = serial;
        a->handler = -1;
        a->hook_open = -1;
        a->page = -1;
        a->refocus_due = -1;
        a->held = -1;
        uit_on_draw(a->e, drawn, a);
    }
    return a;
}

// -- refusals ------------------------------------------------------------------

static const char *code_of(const app_t *a, int r) {
    switch (r) {
    case UIT_E_CHECK: {
        const char *c = uit_error_code(a->e);
        return c != NULL && c[0] ? c : "E00";
    }
    case UIT_E_NAME: return "NAME";
    case UIT_E_LANG: return "LANG";
    case UIT_E_KIND: return "KIND";
    case UIT_E_NOMEM: return "NOMEM";
    case UIT_E_BLOB: return "BLOB";
    default: return "ARG";
    }
}

// A refusal of row `row`: latched, logged once, answered.
static int refuse(app_t *a, int r, const char *row, const char *where, const char *msg) {
    if (a->err == 0) {
        a->err = r;
        snprintf(a->errline, sizeof a->errline, "%s uitree_%s(%s): %s", code_of(a, r), row, where,
                 msg != NULL && msg[0] ? msg : uit_error(a->e));
        LOG(LOG_ERR, a->errline, strlen(a->errline));
    }
    return r;
}

static int check(app_t *a, int r, const char *row, const char *where) {
    return r < 0 ? refuse(a, r, row, where, NULL) : r;
}

// The row's app, or below 0: none could be made, or the run's refusal again.
#define APP(a)                                  \
    app_t *a = app();                           \
    if (a == NULL) {                            \
        return UIT_E_NOMEM;                     \
    }                                           \
    if (a->err != 0) {                          \
        return a->err;                          \
    }

// Node `n`'s key path from the page ("page/group#0/info#0") into buf.
static void key_path(const app_t *a, int n, char *buf, size_t cap) {
    int chain[16], k = 0;
    while (n >= 0 && n < a->e->nnodes && k < 16) {
        chain[k++] = n;
        uint16_t p = a->e->nodes[n].parent;
        n = p == UIT_NONE ? -1 : (int)p;
    }
    size_t at = 0;
    buf[0] = 0;
    while (k-- > 0 && at + 1 < cap) {
        int w = snprintf(buf + at, cap - at, "%s%s", at ? "/" : "", uit_str(a->e, a->e->nodes[chain[k]].key));
        at += w > 0 ? (size_t)w : 0;
    }
}

// -- texts across the line --------------------------------------------------------

// The call's texts: each put NUL-terminated into the scratch (its offset),
// read back as pointers once every one is in (a put may move the scratch).
static int put(app_t *a, const uint8_t *p, uint32_t n) {
    return uit_buf_put(&a->tmp, (const char *)p, n);
}

static const char *at(const app_t *a, int off) {
    return off < 0 ? NULL : a->tmp.p + off;
}

#define TEXTS_BEGIN(a) ((a)->tmp.n = 0)

// -- the trace ------------------------------------------------------------------

static void trace(app_t *a, const char *kind, const char *name, const char *fmt, ...) {
    char line[600];
    uint32_t ms = a->frames * 1000u / 30u;
    int n = snprintf(line, sizeof line, "[trace] %02u:%02u:%02u.%03u  %-6s  %-8s ", (unsigned)(ms / 3600000u),
                     (unsigned)(ms / 60000u % 60u), (unsigned)(ms / 1000u % 60u), (unsigned)(ms % 1000u),
                     kind, name);
    if (n < 0 || n >= (int)sizeof line) {
        return;
    }
    va_list ap;
    va_start(ap, fmt);
    int m = vsnprintf(line + n, sizeof line - (size_t)n, fmt, ap);
    va_end(ap);
    n += m < 0 ? 0 : m;
    if (n >= (int)sizeof line) {
        n = (int)sizeof line - 1;
    }
    LOG(LOG_INFO, line, (size_t)n);
}

// A write's trace: the slot's value before (`was`), the value now, and the
// handler it was made in. Nothing is traced before the first frame (the
// values the app starts with) nor where the value did not move.
static void traced_write(app_t *a, int slot, const char *was) {
    if (!a->opened) {
        return;
    }
    uit_buf_t now = {0};
    uit_slot_repr(a->e, &now, slot);
    if (now.p != NULL && strcmp(now.p, was) != 0) {
        const char *in = a->handler >= 0 ? uit_str(a->e, a->e->acts[a->handler].name) : "the app";
        trace(a, "state", uit_str(a->e, a->e->slots[slot].name), "%s -> %s   (in %s)", was, now.p, in);
    }
    uit_buf_free(&now);
}

static int slot_ok(const app_t *a, int slot) {
    return slot >= 0 && slot < a->e->nslots;
}

// The value a write moves, as the trace spells it, into `b` (a model's is its row count).
static void was_of(app_t *a, int slot, uit_buf_t *b) {
    b->n = 0;
    uit_slot_repr(a->e, b, slot);
    if (b->p == NULL) {
        uit_buf_puts(b, "");
    }
}

// -- declare -------------------------------------------------------------------

int32_t moy_uitree_wasm_state(void *x, const uint8_t *name, uint32_t name_n, int32_t type,
                              const uint8_t *values, uint32_t values_n) {
    (void)x;
    APP(a);
    TEXTS_BEGIN(a);
    int n = put(a, name, name_n), v = values_n ? put(a, values, values_n) : -1;
    return check(a, uit_state(a->e, at(a, n), (int)type, at(a, v), values_n), "state", at(a, n));
}

int32_t moy_uitree_wasm_model(void *x, int32_t slot, const uint8_t *names, uint32_t names_n,
                              const uint8_t *types, uint32_t types_n, int32_t key) {
    (void)x;
    APP(a);
    char where[24];
    snprintf(where, sizeof where, "slot %d", (int)slot);
    return check(a, uit_model(a->e, (int)slot, (const char *)names, names_n, types, (int)types_n, (int)key),
                 "model", where);
}

int32_t moy_uitree_wasm_field_enum(void *x, int32_t slot, int32_t f, const uint8_t *values, uint32_t values_n) {
    (void)x;
    APP(a);
    char where[32];
    snprintf(where, sizeof where, "slot %d, field %d", (int)slot, (int)f);
    return check(a, uit_field_enum(a->e, (int)slot, (int)f, (const char *)values, values_n), "field_enum", where);
}

int32_t moy_uitree_wasm_row_of(void *x, int32_t slot, int32_t model) {
    (void)x;
    APP(a);
    char where[32];
    snprintf(where, sizeof where, "slot %d, model %d", (int)slot, (int)model);
    return check(a, uit_row_of(a->e, (int)slot, (int)model), "row_of", where);
}

int32_t moy_uitree_wasm_labels(void *x, const uint8_t *name, uint32_t name_n, const uint8_t *keys,
                               uint32_t keys_n, const uint8_t *words, uint32_t words_n) {
    (void)x;
    APP(a);
    TEXTS_BEGIN(a);
    int n = put(a, name, name_n);
    return check(a, uit_labels(a->e, at(a, n), (const char *)keys, keys_n, (const char *)words, words_n),
                 "labels", at(a, n));
}

int32_t moy_uitree_wasm_action(void *x, const uint8_t *name, uint32_t name_n, const uint8_t *label,
                               uint32_t label_n, const uint8_t *hint, uint32_t hint_n,
                               const uint8_t *when, uint32_t when_n, int32_t off, int32_t flags,
                               const uint8_t *letters, uint32_t letters_n, const uint8_t *icon,
                               uint32_t icon_n) {
    (void)x;
    APP(a);
    TEXTS_BEGIN(a);
    // no hint: its label, as every front's action (uit_action)
    int n = put(a, name, name_n), l = put(a, label, label_n), h = hint_n ? put(a, hint, hint_n) : -1;
    int w = when_n ? put(a, when, when_n) : -1, k = put(a, letters, letters_n), i = put(a, icon, icon_n);
    int r = uit_action(a->e, at(a, n), at(a, l), at(a, h), at(a, w), (int)off, (int)flags, at(a, k), at(a, i));
    if (r < 0) {
        return refuse(a, r, "action", at(a, n), NULL);
    }
    if (r >= a->cwhen) {
        int c = a->cwhen ? a->cwhen * 2 : 8;
        while (c <= r) {
            c *= 2;
        }
        uint32_t *g = UIT_REALLOC(a->when_at, (size_t)c * sizeof *g);
        if (g == NULL) {
            return refuse(a, UIT_E_NOMEM, "action", at(a, n), "no memory for the action's when=");
        }
        a->when_at = g;
        a->cwhen = c;
    }
    int off_w = uit_buf_put(&a->when, w >= 0 ? at(a, w) : "", w >= 0 ? when_n : 0);
    if (off_w < 0) {
        return refuse(a, UIT_E_NOMEM, "action", at(a, n), "no memory for the action's when=");
    }
    a->when_at[r] = (uint32_t)off_w;
    if (r >= a->nwhen) {
        a->nwhen = r + 1;
    }
    return r;
}

int32_t moy_uitree_wasm_action_row(void *x, int32_t act, int32_t slot) {
    (void)x;
    APP(a);
    char where[32];
    snprintf(where, sizeof where, "action %d, slot %d", (int)act, (int)slot);
    return check(a, uit_action_row(a->e, (int)act, (int)slot), "action_row", where);
}

// -- build ---------------------------------------------------------------------

int32_t moy_uitree_wasm_build(void *x, const uint8_t *page, uint32_t page_n) {
    (void)x;
    APP(a);
    TEXTS_BEGIN(a);
    int p = put(a, page, page_n);
    if (p < 0) {
        return refuse(a, UIT_E_NOMEM, "build", "", "no memory for the page's id");
    }
    int depth = 0;
    for (const char *d = at(a, p); *d >= '0' && *d <= '9'; d++) {
        depth = depth * 10 + (*d - '0');
    }
    if (a->opened && depth > a->depth && depth <= DEPTH) {
        char *f = a->refocus[depth - 2 < 0 ? 0 : depth - 2];
        if (uit_focused(a->e, f, sizeof a->refocus[0]) < 0) {
            f[0] = 0;
        }
        trace(a, "page", "push", "page %d%s%s%s", depth, f[0] ? ", opened from '" : "", f, f[0] ? "'" : "");
    } else if (a->opened && depth < a->depth && depth >= 1) {
        const char *f = a->refocus[depth - 1];
        trace(a, "page", "back", "page %d%s%s%s", depth, f[0] ? ", focus back to '" : "", f, f[0] ? "'" : "");
        a->refocus_due = depth - 1;
    }
    a->depth = depth;
    const char *nm = at(a, p);
    while (*nm >= '0' && *nm <= '9') {
        nm++;
    }
    snprintf(a->pname, sizeof a->pname, "%s", nm + (*nm == ' '));
    uit_build_begin(a->e, at(a, p));
    a->page = -1;
    a->title[0] = 0;
    a->nptr = 0;
    a->held = -1;
    return 0;
}

int32_t moy_uitree_wasm_node(void *x, int32_t kind, const uint8_t *key, uint32_t key_n, int32_t parent) {
    (void)x;
    APP(a);
    TEXTS_BEGIN(a);
    int k = put(a, key, key_n);
    int r = uit_node(a->e, (int)kind, at(a, k), (int)parent);
    if (r < 0) {
        char where[160];
        key_path(a, (int)parent, where, sizeof where);
        size_t w = strlen(where);
        snprintf(where + w, sizeof where - w, "%s%s", w ? "/" : "", at(a, k));
        return refuse(a, r, "node", where, NULL);
    }
    if (kind == UIT_PAGE) {
        a->page = r;
    }
    return r;
}

int32_t moy_uitree_wasm_prop(void *x, int32_t node, const uint8_t *name, uint32_t name_n,
                             const uint8_t *src, uint32_t src_n) {
    (void)x;
    APP(a);
    TEXTS_BEGIN(a);
    int n = put(a, name, name_n), s = put(a, src, src_n);
    int r = uit_prop(a->e, (int)node, at(a, n), at(a, s), NULL);
    if (r >= 0 && node == a->page && strcmp(at(a, n), "title") == 0) {
        snprintf(a->title, sizeof a->title, "%s", at(a, s));
    }
    if (r >= 0 && a->e->nodes[node].kind == UIT_CANVAS && strcmp(at(a, n), "pointer") == 0 && a->nptr < CANVASES) {
        for (int k = 0; k < a->e->nacts; k++) {
            if (strcmp(uit_str(a->e, a->e->acts[k].name), at(a, s)) == 0) {
                a->ptr[a->nptr].node = (int)node;
                a->ptr[a->nptr].act = k;
                a->ptr[a->nptr].frame = 0;
                snprintf(a->ptr[a->nptr++].key, sizeof a->ptr[0].key, "%s", uit_str(a->e, a->e->nodes[node].key));
            }
        }
    }
    if (r < 0) {
        char where[200];
        key_path(a, (int)node, where, sizeof where);
        size_t w = strlen(where);
        snprintf(where + w, sizeof where - w, " %s=", at(a, n));
        return refuse(a, r, "prop", where, NULL);
    }
    return r;
}

int32_t moy_uitree_wasm_node_action(void *x, int32_t node, int32_t act) {
    (void)x;
    APP(a);
    int r = uit_node_action(a->e, (int)node, (int)act);
    if (r < 0) {
        char where[160];
        key_path(a, (int)node, where, sizeof where);
        size_t w = strlen(where);
        snprintf(where + w, sizeof where - w, " action %d", (int)act);
        return refuse(a, r, "node_action", where, "no such node or action");
    }
    return r;
}

int32_t moy_uitree_wasm_build_end(void *x) {
    (void)x;
    APP(a);
    int r = check(a, uit_build_end(a->e), "build_end", "");
    if (r >= 0 && a->refocus_due >= 0) {
        if (a->refocus[a->refocus_due][0]) {
            uit_want_focus(a->e, a->refocus[a->refocus_due]);
        }
        a->refocus_due = -1;
    }
    return r;
}

// -- visit and frame --------------------------------------------------------------

int32_t moy_uitree_wasm_open(void *x) {
    (void)x;
    APP(a);
    uit_open(a->e);
    a->opened = 1;
    a->hook_open = -1;
    for (int k = 0; k < a->e->nacts; k++) {
        if ((a->e->acts[k].flags & UIT_A_HOOK) && strcmp(uit_str(a->e, a->e->acts[k].name), "opened") == 0) {
            a->hook_open = k;
        }
    }
    return 0;
}

int32_t moy_uitree_wasm_focus(void *x, const uint8_t *key, uint32_t key_n) {
    (void)x;
    APP(a);
    TEXTS_BEGIN(a);
    int k = key_n ? put(a, key, key_n) : -1;
    uit_want_focus(a->e, at(a, k));
    return 0;
}

// An action owed to the app from `src`; a non-placed one names the page it
// is on, as the layers' queue does (" on 'TITLE'", not for a dialog's).
static void owe(app_t *a, int act, int m, int row, const int32_t *pev, const char *src, int placed) {
    if (a->qn >= a->qcap) {
        int c = a->qcap ? a->qcap * 2 : 8;
        owed_t *q = UIT_REALLOC(a->q, (size_t)c * sizeof *q);
        if (q == NULL) {
            return;
        }
        a->q = q;
        a->qcap = c;
    }
    int off = (int)a->qtext.n;
    int w = placed || strstr(src, " dialog ") != NULL || strncmp(src, "the ", 4) == 0
                ? uit_buf_puts(&a->qtext, src) : uit_buf_printf(&a->qtext, "%s on '%s'", src, a->title);
    if (w < 0 || uit_buf_put(&a->qtext, "", 0) < 0) {
        return;
    }
    owed_t *o = &a->q[a->qn++];
    o->act = act;
    o->ev[0] = m;
    o->ev[1] = row;
    o->ev[2] = pev ? pev[0] : 0;
    o->ev[3] = pev ? pev[1] : 0;
    o->ev[4] = pev ? pev[2] : 0;
    o->src = (uint32_t)off;
}

static int with_flag(const app_t *a, int flag) {
    for (int k = 0; k < a->e->nacts; k++) {
        if (a->e->acts[k].flags & flag) {
            return k;
        }
    }
    return -1;
}

static void pointed(app_t *a, int i, int kind, int32_t x, int32_t y) {
    static const char *const what[] = {"", "down", "drag", "up"};
    char src[80];
    int32_t pev[3] = {kind, x - a->ptr[i].r[0], y - a->ptr[i].r[1]};
    snprintf(src, sizeof src, "pointer %s on canvas '%s'", what[kind], a->ptr[i].key);
    owe(a, a->ptr[i].act, -1, -1, pev, src, 1);
}

// The pointer before the keys: a canvas with pointer= is handed down, drag
// and up in its own coordinates, at the rect the last frame drew it at; the
// press that starts on it holds it until release.
static void pointers(app_t *a, const int32_t *snap) {
    int st = snap[MOYCORE_UI_SNAP_PTR];
    int32_t tx = snap[MOYCORE_UI_SNAP_X], ty = snap[MOYCORE_UI_SNAP_Y];
    if (a->held >= 0) {
        int i = a->held;
        if (st && (st & 2)) {
            if (tx != a->hx || ty != a->hy) {
                a->hx = tx, a->hy = ty;
                pointed(a, i, 2, tx, ty);
            }
            return;
        }
        a->held = -1;
        pointed(a, i, 3, st ? tx : a->hx, st ? ty : a->hy);
        return;
    }
    if (!(st & 4)) {
        return;
    }
    for (int i = 0; i < a->nptr; i++) {
        const int32_t *r = a->ptr[i].r;
        if (a->ptr[i].frame == a->frames && tx >= r[0] && tx < r[0] + r[2] && ty >= r[1] && ty < r[1] + r[3]) {
            pointed(a, i, 1, tx, ty);
            if (st & 2) {
                a->held = i, a->hx = tx, a->hy = ty;
            } else {
                pointed(a, i, 3, tx, ty);
            }
            return;
        }
    }
}

// The keys before the page: a letter an action declares, where the engine
// gives it to that action (not into a focused field), and the confirm role's
// key (A, Enter) where nothing is focused and no dialog shows.
static void keys(app_t *a, const int32_t *snap) {
    char src[16];
    int k = snap[MOYCORE_UI_SNAP_KEY], act;
    if (k >= 'a' && k <= 'z' && (act = uit_letter(a->e, k)) >= 0) {
        snprintf(src, sizeof src, "key '%c'", k);
        owe(a, act, -1, -1, NULL, src, 1);
    }
    act = with_flag(a, UIT_A_ROLE_CONFIRM);
    if (act >= 0 && (((snap[MOYCORE_UI_SNAP_BTNP] >> 4) & 1) || k == 13) && uit_unfocused(a->e) &&
        uit_dialog(a->e) < 0) {
        owe(a, act, -1, -1, NULL, "role confirm", 1);
    }
}

// The more role's key (`m`), after the frame, where no field is focused: the
// focused row's action when it is the role's, else the page's. An action that
// hangs from a rows list's node takes a row and acts on no other.
static void more(app_t *a, const int32_t *snap) {
    int act = with_flag(a, UIT_A_ROLE_MORE);
    if (act < 0 || snap[MOYCORE_UI_SNAP_KEY] != 'm') {
        return;
    }
    const uit_id_t *F = &a->e->focused;
    int has = a->e->has_focused && F->gen == a->e->gen;
    char src[160], id[UIT_ID_MAX * 2 + 2];
    if (has && F->kind == UIT_FIELD) {
        return;
    }
    int row = 0;
    for (int k = 0; k < a->e->nnodes && !row; k++) {
        row = a->e->nodes[k].act == act && uit_model_of(a->e, k) >= 0;
    }
    if (row) {
        if (has && F->row >= 0 && F->act == act) {
            uit_focused(a->e, id, sizeof id);
            snprintf(src, sizeof src, "key more on '%s'", id);
            owe(a, act, uit_model_of(a->e, F->node), F->row, NULL, src, 0);
        }
    } else if (uit_can(a->e, act, -1)) {
        snprintf(src, sizeof src, "key more on '%s'", a->pname);
        owe(a, act, -1, -1, NULL, src, 0);
    }
}

// Back on the bar: a shown dialog's first button, a shown popover's close=,
// the page under this one, else the app's back role.
static void back(app_t *a) {
    char key[64], src[96];
    int act;
    if (uit_dialog(a->e) >= 0) {
        if ((act = uit_back_dialog(a->e, key, sizeof key)) >= 0) {
            snprintf(src, sizeof src, "back on dialog '%s'", key);
            owe(a, act, -1, -1, NULL, src, 0);
        }
        return;
    }
    if ((act = uit_back_popover(a->e, key, sizeof key)) != -2) {
        if (act >= 0) {
            snprintf(src, sizeof src, "back on popover '%s'", key);
            owe(a, act, -1, -1, NULL, src, 0);
        }
        return;
    }
    if (a->depth > 1) {
        owe(a, -1, -1, -1, NULL, "the bar's back", 1);
    } else if ((act = with_flag(a, UIT_A_ROLE_BACK)) >= 0 && uit_can(a->e, act, -1)) {
        owe(a, act, -1, -1, NULL, "role back", 0);
    }
}

int32_t moy_uitree_wasm_frame(void *x, int32_t flags) {
    (void)x;
    APP(a);
    if (flags != 0) {
        return refuse(a, UIT_E_ARG, "frame", "flags", "flags is 0: no frame flag is defined yet");
    }
    if (a->page < 0) {
        return refuse(a, UIT_E_ARG, "frame", "", "no page is built: uitree_build, the nodes, uitree_build_end, "
                      "then uitree_open, before the first frame");
    }
    void *target = moycore_ui_target != NULL ? moycore_ui_target() : NULL;
    uint32_t tick, serial;
    const int32_t *snap = moycore_ui_snap != NULL ? moycore_ui_snap(&tick, &serial) : NULL;
    if (a->qat >= a->qn) {
        a->qn = a->qat = 0;
        a->qtext.n = 0;
    }
    if (snap != NULL) {
        pointers(a, snap);
        keys(a, snap);
    }
    // the bar's title is the app's (its window's): the page's title is the page's to draw
    int32_t got = -1;
    char pk[48];
    int wants = a->depth > 1 || uit_dialog(a->e) >= 0 || uit_popover(a->e, pk, sizeof pk) > 0 ||
                with_flag(a, UIT_A_ROLE_BACK) >= 0;
    if (target != NULL && moy_ui_run_bar(target, moy_ui_span_of((const uint8_t *)"", 0), NULL, 0, wants ? MOY_UI_BAR_BACK : 0u,
                                         &got) == 0 && got == MOY_UI_BAR_UP) {
        back(a);
    }
    a->handler = -1;
    a->frames++;
    a->trapped = 0;
    int depth = a->depth < 1 ? 1 : a->depth > 255 ? 255 : a->depth;
    int r = uit_run_frame(a->e, target, UIT_F_BAND | UIT_F_TRACE | depth << UIT_F_PAGES_SHIFT);
    if (r < 0) {
        return refuse(a, r, "frame", "", "no compiled run is open");
    }
    if (a->trapped) {
        return refuse(a, UIT_E_ARG, "frame", "", "the app's _uitree_draw trapped");
    }
    char line[600];
    while (uit_trace_next(a->e, line, sizeof line) >= 0) {
        char *name = strchr(line, '\x01');
        char *text = name != NULL ? strchr(name + 1, '\x01') : NULL;
        if (text == NULL) {
            continue;
        }
        *name++ = 0;
        *text++ = 0;
        trace(a, line, name, "%s", text);
    }
    // the engine's events after the keys and the bar, each an action placed on the page
    char src[200];
    int32_t w[3];
    int k;
    while ((k = uit_next(a->e, w, src, sizeof src)) != UIT_EV_NONE) {
        if (k == UIT_EV_ACTION) {
            char *cut = strchr(src, '\x02');
            if (cut != NULL) {
                *cut = 0;
            }
            owe(a, w[0], w[1], w[2], NULL, src, 1);
        }                           // a control's write: the slot holds it
    }
    if (snap != NULL) {
        more(a, snap);
    }
    return r;
}

int32_t moy_uitree_wasm_next(void *x, uint8_t *ev, uint32_t ev_cap) {
    (void)x;
    APP(a);
    if (ev_cap < 8u) {
        return refuse(a, UIT_E_ARG, "next", "ev", "ev holds two words (8 bytes): the model slot and the row");
    }
    a->handler = -1;
    if (a->hook_open >= 0) {
        a->handler = a->hook_open;
        a->hook_open = -1;
        trace(a, "action", "opened", "from the engine (open)");
        memset(ev, 0xFF, 8);        // -1, -1: no model, no row
        return a->handler;
    }
    while (a->qat < a->qn) {
        const owed_t *o = &a->q[a->qat++];
        const char *src = a->qtext.p + o->src;
        if (o->act < 0) {
            memset(ev, 0xFF, 8);
            return BACK_EV;         // the app pops its page (a build of the page under it)
        }
        const char *name = uit_str(a->e, a->e->acts[o->act].name);
        if (!uit_can(a->e, o->act, o->ev[1])) {
            const char *cond = o->act < a->nwhen ? a->when.p + a->when_at[o->act] : "";
            int16_t row = a->e->acts[o->act].row;
            if (cond[0]) {
                trace(a, "skip", name, "from %s (when %s is false)", src, cond);
            } else if (row >= 0) {
                trace(a, "skip", name, "from %s (%s holds no row)", src, uit_str(a->e, a->e->slots[row].name));
            }
            continue;
        }
        trace(a, "action", name, "from %s", src);
        a->handler = o->act;
        memcpy(ev, o->ev, ev_cap < sizeof o->ev ? 8u : sizeof o->ev);   // the app's buffer need not be aligned
        return o->act;
    }
    return -1;
}

// -- state -----------------------------------------------------------------------

#define SLOT(a, slot, row)                                                      \
    if (!slot_ok(a, slot)) {                                                    \
        char where_[24];                                                        \
        snprintf(where_, sizeof where_, "slot %d", (int)(slot));                \
        return refuse(a, UIT_E_ARG, row, where_, "no such slot");               \
    }

int32_t moy_uitree_wasm_set_int(void *x, int32_t slot, int32_t v) {
    (void)x;
    APP(a);
    SLOT(a, slot, "set_int");
    uit_buf_t was = {0};
    was_of(a, (int)slot, &was);
    int r = uit_set_int(a->e, (int)slot, v);
    if (r >= 0) {
        traced_write(a, (int)slot, was.p);
    }
    uit_buf_free(&was);
    return check(a, r, "set_int", uit_str(a->e, a->e->slots[slot].name));
}

int32_t moy_uitree_wasm_set_text(void *x, int32_t slot, const uint8_t *s, uint32_t s_n) {
    (void)x;
    APP(a);
    SLOT(a, slot, "set_text");
    uit_buf_t was = {0};
    was_of(a, (int)slot, &was);
    int r;
    if (a->e->slots[slot].type == UIT_NUM) {        // a number crosses as its digits
        TEXTS_BEGIN(a);
        int t = put(a, s, s_n);
        char *end = NULL;
        double v = t >= 0 ? strtod(at(a, t), &end) : 0.0;
        if (t < 0 || end == at(a, t) || *end != 0) {
            uit_buf_free(&was);
            return refuse(a, UIT_E_ARG, "set_text", uit_str(a->e, a->e->slots[slot].name),
                          "a number state takes a number's digits (\"2.5\", \"-3\", \"1e3\")");
        }
        r = uit_set_num(a->e, (int)slot, v);
    } else {
        r = uit_set_text(a->e, (int)slot, (const char *)s, s_n);
    }
    if (r >= 0) {
        traced_write(a, (int)slot, was.p);
    }
    uit_buf_free(&was);
    return check(a, r, "set_text", uit_str(a->e, a->e->slots[slot].name));
}

int32_t moy_uitree_wasm_set_absent(void *x, int32_t slot) {
    (void)x;
    APP(a);
    SLOT(a, slot, "set_absent");
    return check(a, uit_set_absent(a->e, (int)slot), "set_absent", uit_str(a->e, a->e->slots[slot].name));
}

// A cell as the trace shows a value of field type `t`: a text quoted, a bool
// True or False, a number as it is.
static void show_cell(uit_buf_t *b, int t, const char *v) {
    if (t == UIT_BOOL) {
        uit_buf_printf(b, "%s", v[0] == '1' ? "True" : "False");
    } else if (t == UIT_INT || t == UIT_NUM) {
        uit_buf_printf(b, "%s", v);
    } else {
        uit_buf_printf(b, "\"%s\"", v);
    }
}

// A model's rows before a write: its cells and their offsets, copied.
typedef struct {
    int n, nf, key;
    char *cells;
    uint32_t *at;
} rows_t;

static const char *cell_of(const rows_t *r, int row, int f) {
    return r->cells + r->at[row * r->nf + f];
}

static int row_keyed(const rows_t *r, const char *key) {
    for (int i = 0; i < r->n; i++) {
        if (strcmp(cell_of(r, i, r->key), key) == 0) {
            return i;
        }
    }
    return -1;
}

// What a write of `now` over `was` did, as the layers trace a model's set: up
// to two changed rows by field where only fields changed, else the counts
// "[N rows] +added -gone ~changed moved M". 0 where nothing moved.
static int model_detail(const uit_t *e, const uit_slot_t *S, const rows_t *was, const rows_t *now, uit_buf_t *b) {
    int add = 0, gone = 0, chg = 0, moved = 0, nch = 0;
    uit_buf_t ch = {0};
    for (int i = 0; i < now->n; i++) {
        int j = row_keyed(was, cell_of(now, i, now->key));
        if (j < 0) {
            add++;
            continue;
        }
        int first = 1;
        for (int f = 0; f < now->nf; f++) {
            const char *o = cell_of(was, j, f), *v = cell_of(now, i, f);
            if (strcmp(o, v) == 0) {
                continue;
            }
            if (first) {
                chg++;
                if (nch++) {
                    uit_buf_printf(&ch, "%s", "; ");
                }
                show_cell(&ch, S->mf->ftype[now->key], cell_of(now, i, now->key));
                uit_buf_printf(&ch, "%s", ": ");
                first = 0;
            } else {
                uit_buf_printf(&ch, "%s", ", ");
            }
            uit_buf_printf(&ch, "%s ", uit_str(e, S->mf->fname[f]));
            show_cell(&ch, S->mf->ftype[f], o);
            uit_buf_printf(&ch, "%s", " -> ");
            show_cell(&ch, S->mf->ftype[f], v);
        }
    }
    for (int j = 0; j < was->n; j++) {
        if (row_keyed(now, cell_of(was, j, was->key)) < 0) {
            gone++;
        }
    }
    // moved: kept rows whose place among the kept rows changed
    for (int i = 0, j = 0; i < now->n; i++) {
        if (row_keyed(was, cell_of(now, i, now->key)) < 0) {
            continue;
        }
        while (j < was->n && row_keyed(now, cell_of(was, j, was->key)) < 0) {
            j++;
        }
        if (j < was->n && strcmp(cell_of(was, j, was->key), cell_of(now, i, now->key)) != 0) {
            moved++;
        }
        j++;
    }
    int any = add || gone || chg || moved || now->n != was->n;
    if (any) {
        if (add + gone + moved == 0 && chg <= 2 && nch > 0) {
            uit_buf_printf(b, "%s", ch.p);
        } else {
            uit_buf_printf(b, "[%d rows] +%d -%d ~%d moved %d", now->n, add, gone, chg, moved);
        }
    }
    uit_buf_free(&ch);
    return any;
}

int32_t moy_uitree_wasm_set_model(void *x, int32_t slot, int32_t n, const uint8_t *cells, uint32_t cells_n) {
    (void)x;
    APP(a);
    SLOT(a, slot, "set_model");
    uit_slot_t *S = &a->e->slots[slot];
    const char *name = uit_str(a->e, S->name);
    if (S->type != UIT_MODEL || S->mf == NULL) {
        return refuse(a, UIT_E_ARG, "set_model", name, "not a model state, or its fields are not declared "
                      "(uitree_model)");
    }
    rows_t was = {a->opened ? S->nrows : 0, S->nf, S->key, NULL, NULL};
    if (was.n > 0) {
        size_t cn = S->cells_n + 1, an = sizeof(uint32_t) * (size_t)(was.n * was.nf);
        was.cells = UIT_MALLOC(cn);
        was.at = UIT_MALLOC(an);
        if (was.cells == NULL || was.at == NULL) {
            UIT_FREE(was.cells);
            UIT_FREE(was.at);
            return refuse(a, UIT_E_NOMEM, "set_model", name, "no memory for the trace's copy of the rows");
        }
        memcpy(was.cells, S->cells, cn);
        memcpy(was.at, S->at, an);
    }
    int r = uit_set_model(a->e, (int)slot, (int)n, (const char *)cells, cells_n);
    if (r >= 0 && a->opened) {
        S = &a->e->slots[slot];
        rows_t now = {S->nrows, S->nf, S->key, S->cells, S->at};
        uit_buf_t d = {0};
        if (model_detail(a->e, S, &was, &now, &d)) {
            const char *in = a->handler >= 0 ? uit_str(a->e, a->e->acts[a->handler].name) : "the app";
            trace(a, "state", name, "%s   (in %s)", d.p, in);
        }
        uit_buf_free(&d);
    }
    UIT_FREE(was.cells);
    UIT_FREE(was.at);
    return check(a, r, "set_model", name);
}

int32_t moy_uitree_wasm_get_int(void *x, int32_t slot) {
    (void)x;
    APP(a);
    SLOT(a, slot, "get_int");
    return uit_get_int(a->e, (int)slot);
}

static int32_t copy_out(const char *p, size_t n, uint8_t *out, uint32_t cap) {
    memcpy(out, p, n < cap ? n : cap);
    return (int32_t)n;
}

int32_t moy_uitree_wasm_get_text(void *x, int32_t slot, uint8_t *out, uint32_t out_cap) {
    (void)x;
    APP(a);
    SLOT(a, slot, "get_text");
    size_t n = 0;
    if (a->e->slots[slot].type == UIT_NUM) {        // a number: its digits, as the trace spells it
        uit_buf_t b = {0};
        uit_slot_repr(a->e, &b, (int)slot);
        int32_t r = b.p != NULL ? copy_out(b.p, b.n, out, out_cap) : refuse(a, UIT_E_NOMEM, "get_text", "", NULL);
        uit_buf_free(&b);
        return r;
    }
    const char *p = uit_get_text(a->e, (int)slot, &n);
    if (p == NULL) {
        return refuse(a, UIT_E_ARG, "get_text", uit_str(a->e, a->e->slots[slot].name),
                      "not a text, enum, number or row_of state: read it with uitree_get_int");
    }
    return copy_out(p, n, out, out_cap);
}

int32_t moy_uitree_wasm_get_cell(void *x, int32_t slot, int32_t row, int32_t f, uint8_t *out, uint32_t out_cap) {
    (void)x;
    APP(a);
    SLOT(a, slot, "get_cell");
    const char *p = uit_get_cell(a->e, (int)slot, (int)row, (int)f);
    if (p == NULL) {
        char where[64];
        snprintf(where, sizeof where, "%s row %d field %d", uit_str(a->e, a->e->slots[slot].name), (int)row,
                 (int)f);
        return refuse(a, UIT_E_ARG, "get_cell", where, "no such row or field in this model");
    }
    return copy_out(p, strlen(p), out, out_cap);
}

// -- errors and the dump ------------------------------------------------------------

int32_t moy_uitree_wasm_error(void *x, uint8_t *out, uint32_t out_cap) {
    (void)x;
    app_t *a = app();
    if (a == NULL || a->err == 0) {
        return 0;
    }
    return copy_out(a->errline, strlen(a->errline), out, out_cap);
}

int32_t moy_uitree_wasm_dump(void *x, uint8_t *out, uint32_t out_cap) {
    (void)x;
    APP(a);
    return uit_dump(a->e, (char *)out, out_cap);
}
