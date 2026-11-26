// The frame: the page walked through the toolkit's verbs, call for call as
// the reference replay makes them (runtime/uitree/uitree_app.py's
// `Engine._replay_page` and its `_r_*`), with focus, the hints band, a
// list's cursor and the queue of what the user did.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "moy_text.h"
#include "moy_ui_tables.h"
#include "moy_uitree_int.h"

#define NODE(k) (&e->nodes[k])
#define KIDS(k, c) for (int c = NODE(k)->kid; c != (int)UIT_NONE; c = NODE(c)->next)

static void canvas_draw(uit_t *e, int k, int model, int row, int x, int y, int w, int h);

// Whether the page carries a gen this frame: it may (`gen_safe`), and no canvas drew in the last
// frame but one that names its states (a canvas draws what no state says, so a frame after one
// drew is drawn whole; reads= names what it draws, `canvas_drew`).
static int gen_ok(const uit_t *e)
{
    return e->gen_safe && !e->canvas_last;
}

// Whether node `k` is a carousel (`ui.cards(look="carousel")`); whether it is a cards list of a
// look that is one stop, its key the id (a carousel, a shelf, icons).
#define IS_CAROUSEL(k) (NODE(k)->kind == UIT_CARDS && (NODE(k)->lit & CD_CAROUSEL))
#define IS_ONE_STOP(k) (NODE(k)->kind == UIT_CARDS && (NODE(k)->lit & (CD_CAROUSEL | CD_SHELF | CD_ICONS | CD_COLUMN)))

// A carousel's card: its first `ui.card`, -1 none.
static int carousel_card(uit_t *e, int k)
{
    KIDS(k, g)
    if (NODE(g)->kind == UIT_CARD)
        return g;
    return -1;
}

// Canvas k drew this frame: unless it names the states it draws (reads=, which the gen counts),
// the next frame carries no gen.
static void canvas_drew(uit_t *e, int k)
{
    if (!(e->nodes[k].lit & CV_READS))
        e->canvas_now = 1;
}

static moy_ui_span_t span_of(const char *p, size_t n)
{
    moy_ui_span_t s = {(const uint8_t *)p, (uint16_t)n};
    return s;
}

static moy_ui_span_t sspan(uit_t *e, uint32_t at, uint32_t n)
{
    return span_of(e->scratch.p + at, n);
}

// -- actions and shown ------------------------------------------------------------

int uit_act_can(uit_t *e, int a, int model, int row)
{
    const uit_act_t *A = &e->acts[a];
    if (A->row >= 0 && row < 0) {
        // row=: off while its row_of names no row of its model
        const uit_slot_t *R = &e->slots[A->row];
        if (uit_row_find(e, R->model, R->s ? R->s : "", R->sn) < 0)
            return 0;
    }
    return A->when < 0 || uit_cond_eval(e, A->when, model, row);
}

int uit_can(uit_t *e, int a, int row)
{
    if (a < 0 || a >= e->nacts)
        return 0;
    return uit_act_can(e, a, -1, row);
}

int uit_letter(uit_t *e, int ch)
{
    if (ch <= 0 || ch > 127 || uit_dialog(e) >= 0)
        return -1;
    for (int a = 0; a < e->nacts; a++)
        if (strchr(uit_str(e, e->acts[a].chars), ch) && uit_act_can(e, a, -1, -1))
            return a;
    if (ch >= 'A' && ch <= 'Z')
        ch += 32;
    for (int a = 0; a < e->nacts; a++)
        if (strchr(uit_str(e, e->acts[a].letters), ch) && uit_act_can(e, a, -1, -1))
            return a;
    return -1;
}

int uit_shown(uit_t *e, int node, int model, int row)
{
    const uit_node_t *N = NODE(node);
    if (UIT_IS_TWO_WAY_OFF(N->kind) && (N->lit & NL_HIDE) && N->mark >= 0 && !uit_cond_eval(e, N->mark, model, row))
        return 0;
    return N->shown < 0 || uit_cond_eval(e, N->shown, model, row);
}

static int is_stop(int kind)
{
    return kind == UIT_LINK || kind == UIT_BUTTON || kind == UIT_TOGGLE || kind == UIT_SEG ||
           kind == UIT_SLIDER || kind == UIT_FIELD || kind == UIT_ITEM || kind == UIT_TABS ||
           kind == UIT_CARD || kind == UIT_BUBBLE || kind == UIT_CELLS || kind == UIT_STEPPER;
}

// The case child of `k` ("case:VALUE") whose value is v, else its "case:_", else -1.
static int case_for(uit_t *e, int k, const char *v, size_t vn)
{
    int other = -1;
    KIDS(k, c) {
        const char *cv = uit_str(e, NODE(c)->key) + 5;     // "case:VALUE"
        if (strlen(cv) == vn && !memcmp(cv, v, vn))
            return c;
        if (other < 0 && !strcmp(cv, "_"))
            other = c;
    }
    return other;
}

int uit_case_of(uit_t *e, int k)
{
    const uit_slot_t *S = &e->slots[NODE(k)->slot];
    const char *v = S->type == UIT_BOOL ? (S->i ? "True" : "False") : S->s ? S->s : "";
    return case_for(e, k, v, S->type == UIT_BOOL ? strlen(v) : S->sn);
}

int uit_row_body(uit_t *e, int k, int row)
{
    const uit_node_t *N = NODE(k);
    if (N->kind != UIT_ROWS || !N->nbtn)
        return k;
    const char *v = uit_cell(e, N->slot, row, N->nbtn - 1);
    return case_for(e, k, v, strlen(v));
}

static const char *row_key(uit_t *e, int model, int row)
{
    return model < 0 || row < 0 ? "" : uit_cell(e, model, row, e->slots[model].key);
}

// The id node `k` draws under on row `row`: KEY or ROWKEY/KEY, cut to the
// toolkit's length.
static void node_id(uit_t *e, int k, int model, int row, char out[UIT_ID_MAX + 1])
{
    if (row < 0)
        snprintf(out, UIT_ID_MAX + 1, "%s", uit_str(e, NODE(k)->key));
    else
        snprintf(out, UIT_ID_MAX + 1, "%s/%s", row_key(e, model, row), uit_str(e, NODE(k)->key));
}

// -- the trace's "drew": a text prop's value, compared with the last drawn ----

static void drew(uit_t *e, int k, int t, int model, int row, const char *v, size_t n)
{
    if (!(e->flags & UIT_F_TRACE))
        return;
    int prop = t;
    const char *src = uit_str(e, e->tmpls[t].src);
    if (!strchr(src, '{'))
        return;
    const char *rk = row_key(e, model, row);
    uit_drew_t *D = NULL;
    for (int i = 0; i < e->ndrew; i++)
        if (e->drew[i].node == k && e->drew[i].prop == prop && !strcmp(e->drew[i].rowkey, rk)) {
            D = &e->drew[i];
            break;
        }
    if (D && (strlen(D->val) != n || memcmp(D->val, v, n))) {
        uit_buf_t b = {0};
        if (row >= 0)
            uit_buf_printf(&b, "'%s/%s' ", rk, uit_str(e, NODE(k)->key));
        uit_buf_repr(&b, src, strlen(src));
        uit_buf_printf(&b, " -> ");
        uit_buf_repr(&b, v, n);
        uit_trace(e, "drew", uit_kind_names[NODE(k)->kind], "%s", b.p);
        uit_buf_free(&b);
    }
    if (!D) {
        if (uit_grow((void **)&e->drew, &e->cdrew, e->ndrew + 1, sizeof *e->drew))
            return;
        D = &e->drew[e->ndrew++];
        D->node = (int16_t)k;
        D->prop = (int16_t)prop;
        D->rowkey = UIT_MALLOC(strlen(rk) + 1);
        if (D->rowkey)
            strcpy(D->rowkey, rk);
        D->val = NULL;
    }
    UIT_FREE(D->val);
    D->val = UIT_MALLOC(n + 1);
    if (D->val) {
        memcpy(D->val, v, n);
        D->val[n] = 0;
    }
}

// A text prop now (`_t`), template `t` of node `k` (-1: none given): an
// action's label for the main text a link or button names none of.
static uint32_t text_t(uit_t *e, int k, int t, int model, int row, uint32_t *n)
{
    const uit_node_t *N = NODE(k);
    if (t < 0) {
        const char *s = t == N->t_main && N->act >= 0 ? uit_str(e, e->acts[N->act].label) : "";
        *n = (uint32_t)strlen(s);
        return (uint32_t)uit_buf_put(&e->scratch, s, *n);
    }
    uint32_t at = uit_tmpl_render(e, t, model, row, n);
    drew(e, k, t, model, row, e->scratch.p + at, *n);
    return at;
}

// The main text (prop 0) or the value (prop 1).
static uint32_t text(uit_t *e, int k, int prop, int model, int row, uint32_t *n)
{
    return text_t(e, k, prop == 0 ? NODE(k)->t_main : NODE(k)->t_value, model, row, n);
}

// -- ids --------------------------------------------------------------------------

static uit_id_t *id_find(uit_id_t *ids, int n, const char *id)
{
    for (int i = 0; i < n; i++)
        if (!strcmp(ids[i].id, id))
            return &ids[i];
    return NULL;
}

static void id_put(uit_t *e, int k, int model, int row, const char *id)
{
    uit_id_t *I = id_find(e->ids, e->nids, id);
    if (I) {
        I->dup |= I->node != k;
    } else {
        if (e->nids == e->cids) {       // from 4: a placed page draws a handful
            int c = e->cids ? 2 * e->cids : 4;
            uit_id_t *q = UIT_REALLOC(e->ids, (size_t)c * sizeof *q);
            if (!q)
                return;
            e->ids = q;
            e->cids = c;
        }
        I = &e->ids[e->nids++];
        strcpy(I->id, id);
        I->dup = 0;
    }
    I->node = (int16_t)k;
    I->row = (int16_t)row;
    I->act = NODE(k)->act;
    I->kind = NODE(k)->kind;
    I->gen = e->gen;
    (void)model;
}

// A button's tone= as the override's ink: a role of the look's token row by its name, or
// "#RRGGBB"; -1 for none.
static int32_t button_ink(const char *p, uint32_t n)
{
    if (n == 7 && p[0] == '#') {
        int32_t v = 0;
        for (uint32_t i = 1; i < 7; i++) {
            char ch = p[i];
            int d = ch >= '0' && ch <= '9' ? ch - '0' : ch >= 'a' && ch <= 'f' ? ch - 'a' + 10
                    : ch >= 'A' && ch <= 'F' ? ch - 'A' + 10 : -1;
            if (d < 0)
                return -1;
            v = v * 16 + d;
        }
        return v;
    }
    for (int i = 0; i < MOY_UI_TOKENS && n; i++)
        if (strlen(moy_ui_token_names[i]) == n && !memcmp(moy_ui_token_names[i], p, n))
            return MOY_UI_O_ROLE + i;
    return -1;
}

// The override a stop draws with (`_o`): its id, `disabled` where its
// action is greyed off, its icon given to the toolkit.
static void over_for(uit_t *e, int k, int model, int row, moy_ui_ctx_t *c, moy_ui_over_t *o, char id[UIT_ID_MAX + 1])
{
    moy_ui_over_none(o);
    node_id(e, k, model, row, id);
    id_put(e, k, model, row, id);
    moy_ui_over_text(o, MOY_UI_OV_ID, span_of(id, strlen(id)));
    const uit_node_t *N = NODE(k);
    if (N->act >= 0 && e->acts[N->act].off == 2 && !uit_act_can(e, N->act, model, row)) {
        int32_t one = 1;
        moy_ui_over_put(o, MOY_UI_OV_DISABLED, &one);
    }
    if (row >= 0) {
        int list = uit_list_of(e, k);
        if (list >= 0 && NODE(list)->current >= 0) {
            int32_t on = uit_row_current(e, list, model, row), one = 1;
            moy_ui_over_put(o, MOY_UI_OV_CURRENT, &on);
            if (NODE(list)->kind == UIT_ROWS && (NODE(list)->lit & RS_CHECK))
                moy_ui_over_put(o, MOY_UI_OV_CHECK, &one);
        }
    }
    if (N->mark >= 0 && UIT_IS_TWO_WAY_OFF(N->kind) && !uit_cond_eval(e, N->mark, model, row)) {
        int32_t one = 1;
        moy_ui_over_put(o, MOY_UI_OV_DISABLED, &one);
    } else if (N->mark >= 0 && N->kind == UIT_BUTTON) {
        int32_t on = uit_cond_eval(e, N->mark, model, row) != 0;
        moy_ui_over_put(o, MOY_UI_OV_CURRENT, &on);
    }
    if (N->kind == UIT_BUTTON && N->t_aux >= 0) {
        uint32_t n, at = uit_tmpl_render(e, N->t_aux, model, row, &n);
        int32_t ink = button_ink(e->scratch.p + at, n);
        if (ink >= 0)
            moy_ui_over_put(o, MOY_UI_OV_INK, &ink);
    }
    if (N->t_icon >= 0) {
        uint32_t n, at = uit_tmpl_render(e, N->t_icon, model, row, &n);
        if (n)
            moy_ui_api_icon(c, sspan(e, at, n));
    } else if (N->act >= 0 && uit_str(e, e->acts[N->act].icon)[0]) {
        const char *ic = uit_str(e, e->acts[N->act].icon);      // the action's, where the node names none
        moy_ui_api_icon(c, span_of(ic, strlen(ic)));
    }
}

// -- events -----------------------------------------------------------------------

static void fire(uit_t *e, int a, int k, int model, int row, const char *how)
{
    uit_buf_t b = {0};
    char id[UIT_ID_MAX * 2 + 2];
    if (row < 0)
        snprintf(id, sizeof id, "%s", uit_str(e, NODE(k)->key));
    else
        snprintf(id, sizeof id, "%s/%s", row_key(e, model, row), uit_str(e, NODE(k)->key));
    uit_buf_printf(&b, "%s ", how ? how : uit_kind_names[NODE(k)->kind]);
    uit_buf_repr(&b, id, strlen(id));
    uit_buf_printf(&b, " on ");
    uint32_t n, at = uit_tmpl_render(e, NODE(0)->t_main, -1, -1, &n);
    uit_buf_repr(&b, e->scratch.p + at, n);
    uit_buf_printf(&b, "\x02%s", id);           // the node that fired it (ui.push's opener)
    for (int p = NODE(k)->props; p != (int)UIT_NONE; p = e->props[p].next)
        if (e->props[p].kind == PK_LIT && !strcmp(uit_str(e, e->props[p].name), "arg"))
            uit_buf_printf(&b, "%c%s", e->props[p].idx ? 4 : 3, uit_str(e, e->props[p].src));
    uit_event(e, UIT_EV_ACTION, a, model, row, b.p, b.n);
    uit_buf_free(&b);
}

// A list's cur written to row key `v`; `user` where a user's move put it there (focus from one
// of its rows to another, or the list's own keys or press), the one move its changed= runs on.
void uit_cur_moved(uit_t *e, int node, const char *v, size_t n, const char *why, int user)
{
    int ck = NODE(node)->cur;
    uit_slot_t *S = &e->slots[ck];
    uit_buf_t b = {0};
    uit_buf_repr(&b, S->s ? S->s : "", S->sn);
    uit_buf_printf(&b, " -> ");
    uit_buf_repr(&b, v, n);
    uit_buf_printf(&b, "   (%s)", why);
    uit_set_text(e, ck, v, n);
    UIT_FREE(S->sync);
    S->sync = UIT_MALLOC(n + 1);
    if (S->sync) {
        memcpy(S->sync, v, n);
        S->sync[n] = 0;
    }
    S->sync_set = 1;
    uit_trace(e, "state", uit_str(e, S->name), "%s", b.p);
    uit_buf_free(&b);
    uit_event(e, UIT_EV_WRITE, ck, -1, -1, NULL, 0);
    int ch = NODE(node)->changed;
    if (ch >= 0 && user) {
        int m = NODE(node)->slot, r = uit_row_find(e, m, v, n);
        if (r >= 0) {
            uit_buf_t s = {0};
            uit_buf_printf(&s, "%s ", uit_kind_names[NODE(node)->kind]);
            const char *key = uit_str(e, NODE(node)->key);
            uit_buf_repr(&s, key, strlen(key));
            uit_buf_printf(&s, " cur moved");
            uit_event(e, UIT_EV_ACTION, ch, m, r, s.p, s.n);
            uit_buf_free(&s);
        }
    }
}

// G15's removal rule: the current row gone, the next row in the old order
// that is still there, else the one before it, else none.
void uit_after_removal(uit_t *e, int node)
{
    const uit_node_t *N = NODE(node);
    int m = N->slot;
    const uit_slot_t *M = &e->slots[m];
    const char *lkey = uit_str(e, N->key);
    uit_order_t *O = NULL;
    for (int i = 0; i < e->norders; i++)
        if (!strcmp(e->orders[i].key, lkey))
            O = &e->orders[i];
    if (O && O->has && O->ver == M->ver && O->slot == m)
        return;                 // its rows as last taken: a frame that pushed no model does no row's work
    // the new order
    uit_buf_t nb = {0};
    for (int r = 0; r < M->nrows; r++) {
        const char *k = uit_cell(e, m, r, M->key);
        uit_buf_put(&nb, k, strlen(k));
    }
    int had = O && O->has;
    char *old = had ? O->keys : NULL;
    uint32_t oldn = had ? O->n : 0;
    if (!O) {
        if (uit_grow((void **)&e->orders, &e->corders, e->norders + 1, sizeof *e->orders)) {
            uit_buf_free(&nb);
            return;
        }
        O = &e->orders[e->norders++];
        O->key = UIT_MALLOC(strlen(lkey) + 1);
        if (O->key)
            strcpy(O->key, lkey);
    }
    O->keys = nb.p;
    O->n = nb.n;
    O->has = 1;
    O->ver = M->ver;
    O->slot = (int16_t)m;
    if (N->cur < 0 || !had) {
        UIT_FREE(old);
        return;
    }
    const uit_slot_t *C = &e->slots[N->cur];
    const char *cur = C->s ? C->s : "";
    size_t cn = C->sn;
    int in_new = uit_row_find(e, m, cur, cn) >= 0, in_old = -1, i = 0;
    for (uint32_t p = 0; p < oldn; p += (uint32_t)strlen(old + p) + 1, i++)
        if (!strcmp(old + p, cur))
            in_old = i;
    if (in_new || in_old < 0) {
        UIT_FREE(old);
        return;
    }
    const char *nxt = NULL;
    i = 0;
    for (uint32_t p = 0; p < oldn; p += (uint32_t)strlen(old + p) + 1, i++)
        if (i > in_old && uit_row_find(e, m, old + p, strlen(old + p)) >= 0) {
            nxt = old + p;
            break;
        }
    if (!nxt) {
        i = 0;
        for (uint32_t p = 0; p < oldn; p += (uint32_t)strlen(old + p) + 1, i++)
            if (i < in_old && uit_row_find(e, m, old + p, strlen(old + p)) >= 0)
                nxt = old + p;
    }
    char why[96];
    uit_buf_t q = {0};
    uit_buf_repr(&q, cur, cn);
    snprintf(why, sizeof why, "removal of %s", q.p);
    uit_buf_free(&q);
    uit_cur_moved(e, node, nxt ? nxt : "", nxt ? strlen(nxt) : 0, why, 0);
    UIT_FREE(e->slots[N->cur].sync);   // focus follows cur onto that row
    e->slots[N->cur].sync = NULL;
    e->slots[N->cur].sync_set = 1;
    UIT_FREE(old);
}

// -- two-way controls: the engine's writes ------------------------------------------

// The repr of text `s` into `b`, its characters starred for a secret field.
static void repr_of(uit_buf_t *b, const char *s, size_t n, int secret)
{
    if (!secret) {
        uit_buf_repr(b, s, n);
        return;
    }
    uit_buf_printf(b, "'");
    for (size_t i = 0; i < n; i++)
        if ((s[i] & 0xC0) != 0x80)
            uit_buf_printf(b, "*");
    uit_buf_printf(b, "'");
}

// Node `k`'s state written (`_two_way`): its trace line `was -> now   (how)`,
// the write's event, then the action `then` names (-1 none).
static void wrote(uit_t *e, int k, const char *was, const char *now, const char *how, int then)
{
    const uit_node_t *N = NODE(k);
    if (e->flags & UIT_F_TRACE)
        uit_trace(e, "state", uit_str(e, e->slots[N->slot].name), "%s -> %s   (%s)", was, now, how);
    uit_event(e, UIT_EV_WRITE, N->slot, -1, -1, NULL, 0);
    if (then >= 0)
        fire(e, then, k, -1, -1, NULL);
}

// A toggle or a slider bound to its row's field written (`_row_write`): the
// cell, the model's version, its trace line `KEY: FIELD old -> new   (from
// toggle .FIELD)`, the cell's event, then its on= handed the row.
static void row_wrote(uit_t *e, int k, int model, int row, const char *cell, const char *was,
                      const char *now)
{
    const uit_node_t *N = NODE(k);
    uit_slot_t *M = &e->slots[model];
    if (uit_cell_put(e, model, row, N->cur, cell))
        return;
    M->ver++;
    if (e->flags & UIT_F_TRACE) {
        uit_buf_t key = {0};
        const char *kv = uit_cell(e, model, row, M->key), *f = uit_str(e, M->mf->fname[N->cur]);
        if (M->mf->ftype[M->key] == UIT_TEXT)
            uit_buf_repr(&key, kv, strlen(kv));
        else
            uit_buf_printf(&key, "%s", kv);
        uit_trace(e, "state", uit_str(e, M->name), "%s: %s %s -> %s   (from %s .%s)", key.p, f,
                  was, now, uit_kind_names[N->kind], f);
        uit_buf_free(&key);
    }
    uit_event(e, UIT_EV_CELL, model, row, N->cur, NULL, 0);
    if (N->on >= 0)
        fire(e, N->on, k, model, row, NULL);
}

// Node `k`'s text state written from `s`: the trace's reprs, the write, `then`.
static void wrote_text(uit_t *e, int k, const char *s, size_t n, const char *how, int then)
{
    uit_slot_t *S = &e->slots[NODE(k)->slot];
    int secret = NODE(k)->kind == UIT_FIELD && (NODE(k)->lit & NL_SECRET);
    uit_buf_t was = {0}, now = {0}, why = {0};
    if (e->flags & UIT_F_TRACE) {
        repr_of(&was, S->s ? S->s : "", S->sn, secret);
        repr_of(&now, s, n, secret);
        // how: "from" (a control's own write), "typed" or "field" (a commit)
        if (how[0] == 'f' && how[1] == 'r')
            uit_buf_printf(&why, "from %s ", uit_kind_names[NODE(k)->kind]);
        else
            uit_buf_printf(&why, how[0] == 't' ? "typed in field " : "field ");
        const char *key = uit_str(e, NODE(k)->key);
        uit_buf_repr(&why, key, strlen(key));
        if (how[0] == 'f' && how[1] == 'i')
            uit_buf_printf(&why, " committed");
    }
    uit_set_text(e, NODE(k)->slot, s, n);
    wrote(e, k, was.p ? was.p : "", now.p ? now.p : "", why.p ? why.p : "", then);
    uit_buf_free(&was);
    uit_buf_free(&now);
    uit_buf_free(&why);
}

static uit_draft_t *draft_find(uit_t *e, const char *key)
{
    for (int i = 0; i < e->ndrafts; i++)
        if (!strcmp(e->drafts[i].key, key))
            return &e->drafts[i];
    return NULL;
}

// Field `key`'s buffer, `cap` bytes at least.
static uit_draft_t *draft_of(uit_t *e, const char *key, size_t cap)
{
    uit_draft_t *D = draft_find(e, key);
    if (!D) {
        if (uit_grow((void **)&e->drafts, &e->cdrafts, e->ndrafts + 1, sizeof *e->drafts))
            return NULL;
        D = &e->drafts[e->ndrafts];
        memset(D, 0, sizeof *D);
        D->key = UIT_MALLOC(strlen(key) + 1);
        if (!D->key)
            return NULL;
        strcpy(D->key, key);
        e->ndrafts++;
    }
    if (cap < 1)
        cap = 1;
    if (D->cap < cap) {
        char *p = UIT_REALLOC(D->buf, cap);
        if (!p)
            return NULL;
        D->buf = p;
        D->cap = (uint16_t)cap;
    }
    return D;
}

const char *uit_draft(const uit_t *e, const char *key, size_t *n)
{
    uit_draft_t *D = draft_find((uit_t *)e, key);
    if (!D || !D->has)
        return NULL;
    *n = D->n;
    return D->buf;
}

// A commit field's draft written to its state (`_commit_field`): Enter, focus
// leaving it, every way out. changed= runs when the state moves.
static void commit_field(uit_t *e, int k)
{
    uit_draft_t *D = draft_find(e, uit_str(e, NODE(k)->key));
    if (!D || !D->has)
        return;
    D->has = 0;
    const uit_slot_t *S = &e->slots[NODE(k)->slot];
    if (D->n == S->sn && !memcmp(D->buf, S->s ? S->s : "", D->n))
        return;
    wrote_text(e, k, D->buf, D->n, "field", NODE(k)->changed);
}

int uit_leave(uit_t *e)
{
    for (int i = 0; i < e->nids; i++) {
        const uit_id_t *I = &e->ids[i];
        if (I->kind == UIT_FIELD && I->gen == e->gen && I->node >= 0 && I->node < e->nnodes)
            commit_field(e, I->node);
    }
    return e->nevs - e->evat;
}

int uit_stop(const uit_t *e, int i, char *buf, size_t cap)
{
    if (i < 0 || i >= e->nids)
        return -1;
    const uit_id_t *I = &e->ids[i];
    if (buf && cap)
        snprintf(buf, cap, "%s", I->id);
    int k = I->kind;
    if (k == UIT_SEG && I->gen == e->gen && (e->nodes[I->node].lit & NL_CYCLE))
        k = UIT_KINDS;
    return k;
}

int uit_focused(const uit_t *e, char *buf, size_t cap)
{
    if (buf && cap)
        snprintf(buf, cap, "%s", e->focus_key);
    return (int)strlen(e->focus_key);
}

// The items of a seg at the scratch's end, NUL-separated (`words`): their
// count into *count, the current one's index into *at (-1 none).
static uint32_t seg_items(uit_t *e, const uit_node_t *N, uint32_t *len, int *count, int *at)
{
    const uit_slot_t *S = &e->slots[N->slot];
    const char *cur = S->s ? S->s : "";
    uint32_t start = e->scratch.n;
    *at = -1;
    *count = 0;
    if (S->type == UIT_ENUM) {
        const char *v = uit_str(e, S->vals);
        for (int i = 0; i < S->nvals; i++) {
            size_t vn = strlen(v);
            if (vn == S->sn && !memcmp(v, cur, vn))
                *at = i;
            const char *w = N->cur >= 0 ? uit_label_word(e, N->cur, v, vn) : v;
            uit_buf_puts(&e->scratch, w);
            v += vn + 1;
        }
        *count = S->nvals;
        if (*at < 0)
            *at = 0;
    } else {
        int m = S->model;
        const uit_slot_t *M = &e->slots[m];
        for (int r = 0; r < M->nrows; r++) {
            const char *key = uit_cell(e, m, r, M->key);
            if (strlen(key) == S->sn && !memcmp(key, cur, S->sn))
                *at = r;
            uint32_t n;
            uit_tmpl_render(e, N->t_value, m, r, &n);
        }
        *count = M->nrows;
    }
    *len = e->scratch.n > start ? e->scratch.n - start - 1 : 0;
    return start;
}

// A swatches seg's `count` words (NUL-separated at scratch offset `at`) as colours: four bytes a
// word, little-endian, appended to the scratch; their offset, their length in *len.
static uint32_t swatch_words(uit_t *e, uint32_t at, int count, uint32_t *len)
{
    uint32_t start = e->scratch.n;
    for (int i = 0; i < count; i++) {
        const char *w = e->scratch.p + at;
        uint32_t v = (uint32_t)strtol(w, NULL, 0) & 0xffffff;
        at += (uint32_t)strlen(w) + 1;
        uint8_t b[4] = {(uint8_t)v, (uint8_t)(v >> 8), (uint8_t)(v >> 16), 0};
        if (uit_buf_put(&e->scratch, (const char *)b, 4) >= 0)
            e->scratch.n--;             // uit_buf_put keeps a NUL past what it wrote
    }
    *len = e->scratch.n - start;
    return start;
}

// The items of a seg bound to an int field of row `row` of `model` at the scratch's end,
// NUL-separated: the lines its text= renders over the row, the field's cell the current one.
static uint32_t field_seg_items(uit_t *e, const uit_node_t *N, int model, int row, uint32_t *len, int *count,
                                int *at)
{
    uint32_t n, start = uit_tmpl_render(e, N->t_value, model, row, &n);
    char *p = e->scratch.p + start;
    *count = n ? 1 : 0;
    for (uint32_t i = 0; i < n; i++)
        if (p[i] == '\n')
            p[i] = 0, ++*count;
    *at = (int)strtol(uit_cell(e, model, row, N->cur), NULL, 10);
    if (*at < 0 || *at >= *count)
        *at = 0;
    *len = n;
    return start;
}

// The value seg `N`'s item `i` stands for (an enum's value, a row's key).
static const char *seg_key(uit_t *e, const uit_node_t *N, int i)
{
    const uit_slot_t *S = &e->slots[N->slot];
    if (S->type == UIT_ENUM) {
        const char *v = uit_str(e, S->vals);
        while (i-- > 0)
            v += strlen(v) + 1;
        return v;
    }
    return uit_cell(e, S->model, i, e->slots[S->model].key);
}

// -- the stops, in the page's order -------------------------------------------------

typedef struct {
    int16_t node, row;
} stop_t;

typedef struct {
    stop_t *s;
    int n, cap;
} stops_t;

static void stop_put(stops_t *out, int node, int row)
{
    if (uit_grow((void **)&out->s, &out->cap, out->n + 1, sizeof *out->s))
        return;
    out->s[out->n].node = (int16_t)node;
    out->s[out->n].row = (int16_t)row;
    out->n++;
}

static void stops_of(uit_t *e, int k, int model, int row, stops_t *out)
{
    KIDS(k, c) {
        const uit_node_t *N = NODE(c);
        if (!uit_shown(e, c, model, row))
            continue;
        if (IS_ONE_STOP(c)) {
            if (e->slots[N->slot].nrows)
                stop_put(out, c, 0);        // one stop, as a table's
        } else if (N->kind == UIT_ROWS || N->kind == UIT_CARDS) {
            for (int r = 0, b; r < e->slots[N->slot].nrows; r++)
                if ((b = uit_row_body(e, c, r)) >= 0)
                    stops_of(e, b, N->slot, r, out);
        } else if (N->kind == UIT_TABLE) {
            if (e->slots[N->slot].nrows)
                stop_put(out, c, 0);        // one stop, as its first row
        } else if (N->kind == UIT_SWITCH) {
            int cs = uit_case_of(e, c);
            if (cs >= 0)
                stops_of(e, cs, model, row, out);
        } else if (N->kind == UIT_DIALOG || N->kind == UIT_POPOVER || (N->kind == UIT_TOOLS && (N->lit & TL_LEND))) {
            continue;               // drawn over the page, or at the site it is lent to
        } else if (N->kind == UIT_CANVAS && (N->lit & CV_KEYS)) {
            stop_put(out, c, row);  // a canvas that takes the keys while it holds focus
        } else if (N->kind == UIT_TABS && N->t_aux >= 0) {
            continue;               // tabs the band names (hint=): the tabs keys or a tap switch them
        } else if (is_stop(N->kind)) {
            if (N->act < 0 || uit_act_can(e, N->act, model, row))
                stop_put(out, c, row);
        } else {
            stops_of(e, c, model, row, out);
        }
    }
}

// The id node KEY (or ROWKEY/KEY) draws under this frame, as the walk will
// draw: shown, its action on, its row in the model. 0: it will not draw.
static int drawn_id(uit_t *e, int k, const char *rowkey, size_t rn, const char *nodekey, char out[UIT_ID_MAX + 1])
{
    KIDS(k, c) {
        const uit_node_t *N = NODE(c);
        if (!uit_shown(e, c, -1, -1))
            continue;
        if (N->kind == UIT_ROWS || (N->kind == UIT_CARDS && !IS_ONE_STOP(c))) {
            if (!rn)
                continue;
            int r = uit_row_find(e, N->slot, rowkey, rn), b = r < 0 ? -1 : uit_row_body(e, c, r);
            if (b < 0)
                continue;
            KIDS(b, g) {
                if (!strcmp(uit_str(e, NODE(g)->key), nodekey) && uit_shown(e, g, N->slot, r) &&
                    (NODE(g)->act < 0 || uit_act_can(e, NODE(g)->act, N->slot, r))) {
                    snprintf(out, UIT_ID_MAX + 1, "%.*s/%s", (int)rn, rowkey, nodekey);
                    return 1;
                }
            }
            continue;
        }
        if (N->kind == UIT_SWITCH) {
            int cs = uit_case_of(e, c);
            if (cs >= 0 && drawn_id(e, cs, rowkey, rn, nodekey, out))
                return 1;
            continue;
        }
        if (N->kind == UIT_TOOLS && (N->lit & TL_LEND))
            continue;
        if (N->kind == UIT_TABLE || IS_ONE_STOP(c)) {
            if (rn || strcmp(uit_str(e, N->key), nodekey))
                continue;
            snprintf(out, UIT_ID_MAX + 1, "%s", nodekey);     // one stop, its key the id
            return 1;
        }
        if (N->act >= 0 && !uit_act_can(e, N->act, -1, -1))
            continue;
        if (!rn && !strcmp(uit_str(e, N->key), nodekey)) {
            snprintf(out, UIT_ID_MAX + 1, "%s", nodekey);
            return 1;
        }
        if (drawn_id(e, c, rowkey, rn, nodekey, out))
            return 1;
    }
    return 0;
}

static int drawn_key(uit_t *e, const char *key, char out[UIT_ID_MAX + 1])
{
    // a key with a slash: a node's (a button's arg=, "NAME/ARG"), else a row's and its node's
    const char *slash = strrchr(key, '/');
    if (drawn_id(e, 0, "", 0, key, out))
        return 1;
    return slash && drawn_id(e, 0, key, (size_t)(slash - key), slash + 1, out);
}

// The key of the first node a fresh page's first frame draws whose focus= holds.
static int fresh_focus(uit_t *e, int k)
{
    KIDS(k, c) {
        const uit_node_t *N = NODE(c);
        if (!uit_shown(e, c, -1, -1) || N->kind == UIT_DIALOG || N->kind == UIT_POPOVER || UIT_IS_LIST(N->kind))
            continue;
        if (N->kind == UIT_SWITCH) {
            int cs = uit_case_of(e, c), got = cs >= 0 ? fresh_focus(e, cs) : -1;
            if (got >= 0)
                return got;
            continue;
        }
        if (N->focus >= 0 && uit_cond_eval(e, N->focus, -1, -1))
            return c;
        int got = fresh_focus(e, c);
        if (got >= 0)
            return got;
    }
    return -1;
}

int uit_dialog(uit_t *e)
{
    if (!e->nnodes)
        return -1;
    KIDS(0, c)
    if (NODE(c)->kind == UIT_DIALOG && uit_shown(e, c, -1, -1))
        return c;
    return -1;
}

// The shown popover at the page's root, or -1.
static int popover_of(uit_t *e)
{
    if (!e->nnodes)
        return -1;
    KIDS(0, c)
    if (NODE(c)->kind == UIT_POPOVER && uit_shown(e, c, -1, -1))
        return c;
    return -1;
}

int uit_popover(uit_t *e, char *buf, size_t cap)
{
    int p = popover_of(e);
    if (p < 0 || !buf || !cap)
        return 0;
    snprintf(buf, cap, "%s", uit_str(e, NODE(p)->key));
    return 1;
}

int uit_back_popover(uit_t *e, char *buf, size_t cap)
{
    int p = popover_of(e);
    if (p < 0)
        return -2;
    if (buf && cap)
        snprintf(buf, cap, "%s", uit_str(e, NODE(p)->key));
    return NODE(p)->on;
}

int uit_unfocused(const uit_t *e)
{
    return !e->has_focused;
}

int uit_editing(const uit_t *e)
{
    return e->editing;
}

int uit_back_dialog(uit_t *e, char *buf, size_t cap)
{
    int d = uit_dialog(e);
    if (d < 0 || !NODE(d)->nbtn)
        return -1;
    if (buf && cap)
        snprintf(buf, cap, "%s", uit_str(e, NODE(d)->key));
    return e->btns[NODE(d)->btn];
}

// -- the hints band -------------------------------------------------------------------

static void hint_add(uit_buf_t *b, const char *s, size_t n)
{
    uit_buf_put(b, s, n);
}

static void hint_act(uit_t *e, uit_buf_t *b, int a)
{
    uint32_t n, at = uit_tmpl_render(e, e->acts[a].hint, -1, -1, &n);
    hint_add(b, e->scratch.p + at, n);
}

// Dialog `d`'s labels= template of its button i, else -1 (the button is its action's word).
static int dialog_label(uit_t *e, int d, int i)
{
    for (int p = NODE(d)->props; p != (int)UIT_NONE; p = e->props[p].next)
        if (!strcmp(uit_str(e, e->props[p].name), "labels") && i-- == 0)
            return e->props[p].idx;
    return -1;
}

// Dialog `d`'s button i as the band names it: its label, else its action's hint.
static void hint_button(uit_t *e, uit_buf_t *b, int d, int i)
{
    int t = dialog_label(e, d, i);
    if (t < 0) {
        hint_act(e, b, e->btns[NODE(d)->btn + i]);
        return;
    }
    uint32_t n, at = uit_tmpl_render(e, t, -1, -1, &n);
    hint_add(b, e->scratch.p + at, n);
}

static int role_action(uit_t *e, int flag)
{
    for (int a = 0; a < e->nacts; a++)
        if (e->acts[a].flags & flag)
            return a;
    return -1;
}

// A page's tabs in the band where they say what the tabs keys do (hint=).
static void hint_tabs(uit_t *e, uit_buf_t *b, int k)
{
    if (NODE(k)->t_aux < 0)
        return;
    uint32_t n, at = uit_tmpl_render(e, NODE(k)->t_aux, -1, -1, &n);
    if (n) {
        hint_add(b, "tabs", 4);
        hint_add(b, e->scratch.p + at, n);
    }
}

// Whether action a goes in the band by its keys: an arrow role or a letter, and available.
static int band_key(uit_t *e, int a)
{
    return (e->acts[a].letter || (e->acts[a].flags & (UIT_A_ARROWS_V | UIT_A_ARROWS_H))) &&
           uit_act_can(e, a, -1, -1);
}

// Action a's keys in the band, and the next action's with it where that one says the same:
// two on the up and down arrows are the scroll keys, two on left and right the change keys,
// two letters both letters. Answers the last action it took.
static int hint_keys(uit_t *e, uit_buf_t *b, int a)
{
    int ax = e->acts[a].flags & (UIT_A_ARROWS_V | UIT_A_ARROWS_H);
    uint32_t n, at = uit_tmpl_render(e, e->acts[a].hint, -1, -1, &n);
    int two = 0;
    if (a + 1 < e->nacts && band_key(e, a + 1) &&
        (e->acts[a + 1].flags & (UIT_A_ARROWS_V | UIT_A_ARROWS_H)) == ax) {
        uint32_t n2, at2 = uit_tmpl_render(e, e->acts[a + 1].hint, -1, -1, &n2);
        two = n2 == n && !memcmp(e->scratch.p + at, e->scratch.p + at2, n);
    }
    char keys[4];
    if (ax & UIT_A_ARROWS_V) {
        hint_add(b, two ? "scroll" : "up down", two ? 6 : 7);
    } else if (ax) {
        hint_add(b, two ? "change" : "left right", two ? 6 : 10);
    } else {
        int l = e->acts[a].letter, l2 = two ? e->acts[a + 1].letter : 0;
        keys[0] = (char)(l >= 'a' && l <= 'z' ? l - 32 : l);
        keys[1] = ' ';
        keys[2] = (char)(l2 >= 'a' && l2 <= 'z' ? l2 - 32 : l2);
        hint_add(b, keys, two ? 3 : 1);
    }
    hint_add(b, e->scratch.p + at, n);
    return two ? a + 1 : a;
}

// The fields shown under node `k`.
static int shown_fields(uit_t *e, int k)
{
    int n = 0;
    KIDS(k, c) {
        if (!uit_shown(e, c, -1, -1))
            continue;
        n += NODE(c)->kind == UIT_FIELD ? 1 : shown_fields(e, c);
    }
    return n;
}

// The band's items, NUL-separated into b (its length b->n, the last NUL
// included).
static void hints(uit_t *e, uit_buf_t *b, int pages)
{
    b->n = 0;
    int d = uit_dialog(e);
    if (d >= 0) {
        const uit_node_t *D = NODE(d);
        if (shown_fields(e, d) > 1) {
            hint_add(b, "scroll", 6);       // the arrows move between its fields
            hint_add(b, "Field", 5);
        }
        // its first button's key: in a field's edit the one that never types
        int field = e->editing;
        if (D->nbtn == 1) {
            hint_add(b, field ? "cancel" : "back", field ? 6 : 4);
            hint_button(e, b, d, 0);
        } else if (D->nbtn > 1) {
            hint_add(b, "confirm", 7);
            hint_button(e, b, d, D->nbtn - 1);
            hint_add(b, field ? "cancel" : "back", field ? 6 : 4);
            hint_button(e, b, d, 0);
        }
        return;
    }
    int pop = popover_of(e);
    if (pop >= 0) {
        // a popover: Back closes it; what lies under it takes no keys
        const uit_id_t *F = &e->focused;
        int in = 0;
        for (int k = e->has_focused && F->gen == e->gen ? F->node : -1; k >= 0 && k != (int)UIT_NONE;
             k = NODE(k)->parent)
            if (k == pop)
                in = 1;
        if (in && F->act >= 0 && uit_act_can(e, F->act, -1, -1)) {
            hint_add(b, "confirm", 7);
            hint_act(e, b, F->act);
        }
        hint_add(b, "back", 4);
        if (NODE(pop)->on >= 0)
            hint_act(e, b, NODE(pop)->on);
        else
            hint_add(b, "Close", 5);
        return;
    }
    if (e->has_focused) {
        const uit_id_t *F = &e->focused;
        int a = F->act;
        if (a < 0 && (F->kind == UIT_BUBBLE || F->kind == UIT_FIELD) && F->gen == e->gen)
            a = NODE(F->node)->on;      // a bubble's press is its on=, Enter in a field's edit its on=
        int on = a >= 0 && uit_act_can(e, a, -1, -1);
        if (F->kind == UIT_FIELD && F->gen == e->gen && !e->editing) {
            hint_add(b, "confirm", 7);  // a field is a stop until Enter opens its edit
            hint_add(b, "Edit", 4);
            on = 0;
        } else if (F->kind == UIT_FIELD && F->gen == e->gen && (NODE(F->node)->lit & NL_COMMIT)) {
            static const char DONE[] = "confirm\0Done\0cancel\0Cancel";
            uit_buf_put(b, DONE, sizeof DONE - 1);
            return;
        }
        if (F->kind == UIT_SEG || F->kind == UIT_SLIDER) {
            hint_add(b, "change", 6);
            hint_add(b, "Change", 6);
        }
        if (F->kind == UIT_CELLS && F->node >= 0 && NODE(F->node)->changed >= 0) {
            hint_add(b, "confirm", 7);      // a cells' pick=: Enter takes the cell
            hint_add(b, "Use", 3);
        }
        if (F->kind == UIT_TOGGLE) {
            int t = F->gen == e->gen && F->node >= 0 ? NODE(F->node)->t_aux : -1;
            hint_add(b, "confirm", 7);
            if (t >= 0) {
                int m = uit_model_of(e, F->node);
                uint32_t n, at = uit_tmpl_render(e, t, m, m >= 0 ? F->row : -1, &n);
                hint_add(b, e->scratch.p + at, n);
            } else {
                hint_add(b, "Change", 6);
            }
        } else if (F->kind == UIT_CARDS && F->gen == e->gen && IS_ONE_STOP(F->node)) {
            int cd = carousel_card(e, F->node), m = NODE(F->node)->slot;
            if (cd >= 0 && NODE(cd)->act >= 0 && F->row >= 0 && F->row < e->slots[m].nrows &&
                uit_act_can(e, NODE(cd)->act, m, F->row)) {
                hint_add(b, "confirm", 7);
                hint_act(e, b, NODE(cd)->act);
            }
        } else if (F->kind == UIT_TABLE) {
            int t = F->gen == e->gen ? NODE(F->node)->t_value : -1;
            uint32_t n = 0, at = t >= 0 ? uit_tmpl_render(e, t, -1, -1, &n) : 0;
            if (n) {
                hint_add(b, "confirm", 7);
                hint_add(b, e->scratch.p + at, n);
            }
        } else if (on) {
            uint32_t n, at = uit_tmpl_render(e, e->acts[a].hint, -1, -1, &n);
            if (n) {
                hint_add(b, "confirm", 7);
                hint_add(b, e->scratch.p + at, n);
            }
        }
        if (F->kind == UIT_CANVAS && F->gen == e->gen && NODE(F->node)->t_main >= 0) {
            int m = uit_model_of(e, F->node);   // a keys= canvas's hint=, over its row in a list
            uint32_t n, at = uit_tmpl_render(e, NODE(F->node)->t_main, m, m >= 0 ? F->row : -1, &n);
            if (n) {
                hint_add(b, "confirm", 7);
                hint_add(b, e->scratch.p + at, n);
            }
        }
        if (F->kind == UIT_TEXT_VIEW) {
            hint_add(b, "scroll", 6);       // a text that runs on: the arrows scroll it
            hint_add(b, "Scroll", 6);
        }
    } else {
        int a = role_action(e, UIT_A_ROLE_CONFIRM);
        if (a >= 0 && uit_act_can(e, a, -1, -1)) {
            uint32_t n, at = uit_tmpl_render(e, e->acts[a].hint, -1, -1, &n);
            if (n) {
                hint_add(b, "confirm", 7);
                hint_add(b, e->scratch.p + at, n);
            }
        }
    }
    if (e->page_tabs >= 0 && e->page_tabs_gen == e->gen && uit_shown(e, e->page_tabs, -1, -1))
        hint_tabs(e, b, e->page_tabs);
    if ((e->flags & UIT_F_DESK) && e->tv_stop && !(e->has_focused && e->focused.kind == UIT_TEXT_VIEW)) {
        hint_add(b, "PgUp PgDn", 9);        // the page's text runs on: PgUp and PgDn page it
        hint_add(b, "Scroll", 6);
    }
    for (int a = 0; a < e->nacts; a++)
        if (band_key(e, a))
            a = hint_keys(e, b, a);
    if (e->nband_extra)
        uit_buf_put(b, e->band_extra, e->nband_extra - 1u);
    int a = pages == 1 ? role_action(e, UIT_A_ROLE_BACK) : -1;
    int app = pages == 1 && a < 0 ? role_action(e, UIT_A_APP_BACK) : -1;
    if (app >= 0 && uit_act_can(e, app, -1, -1)) {
        // the app's back: its words; in a field's edit the keys that never type
        uint32_t n, at = uit_tmpl_render(e, e->acts[app].hint, -1, -1, &n);
        int field = e->editing;
        hint_add(b, field ? "cancel" : "back", field ? 6 : 4);
        hint_add(b, e->scratch.p + at, n);
        return;
    }
    if (a < 0) {
        hint_add(b, "back", 4);
        hint_add(b, "Back", 4);
        return;
    }
    if (uit_act_can(e, a, -1, -1)) {
        uint32_t n, at = uit_tmpl_render(e, e->acts[a].hint, -1, -1, &n);
        if (n) {
            hint_add(b, "back", 4);
            hint_add(b, e->scratch.p + at, n);
        }
    }
}

// -- the walk ---------------------------------------------------------------------------

static void walk(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row);

// A field (`_r_field`): a commit field types into its draft, written by
// Enter or focus leaving it; another writes its state at each edit.
// What Enter in a field runs: the action Shift+Enter answers where Shift is held and it is on,
// else the field's on=.
static int field_enter(uit_t *e, const moy_ui_ctx_t *c, int on)
{
    if (!(c->in[MOY_UI_IN_MODS] & MOY_UI_MOD_SHIFT))
        return on;
    for (int a = 0; a < e->nacts; a++)
        if (e->acts[a].flags & UIT_A_SHIFT_ENTER)
            return uit_act_can(e, a, -1, -1) ? a : on;
    return on;
}

static void draw_field(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    moy_ui_over_t o;
    char id[UIT_ID_MAX + 1];
    uint32_t hn = 0, ha = 0, ln, la;
    over_for(e, k, model, row, c, &o, id);
    if (e->in_foot) {
        int32_t one = 1;
        moy_ui_over_put(&o, MOY_UI_OV_BARE, &one);      // its box on the foot's lead
    }
    if (N->t_aux >= 0)
        ha = text_t(e, k, N->t_aux, model, row, &hn);
    la = text(e, k, 0, model, row, &ln);
    size_t max = N->btn;
    uit_draft_t *D = draft_of(e, uit_str(e, N->key), max);
    if (!D)
        return;
    const uit_slot_t *S = &e->slots[N->slot];
    int commit = (N->lit & NL_COMMIT) != 0;
    const char *cur = commit && D->has ? D->buf : (S->s ? S->s : "");
    size_t cn = commit && D->has ? D->n : S->sn;
    uint32_t was = (uint32_t)uit_buf_put(&e->scratch, cur, cn);
    size_t len = cn;
    if (len > max) {
        len = max;
        while (len > 0 && ((uint8_t)e->scratch.p[was + len] & 0xC0) == 0x80)
            len--;              // never half a character
    }
    memmove(D->buf, e->scratch.p + was, len);
    int32_t one = 1;
    if (N->lit & NL_SECRET)
        moy_ui_over_put(&o, MOY_UI_OV_SECRET, &one);
    if (N->lit & NL_OPEN)
        moy_ui_over_put(&o, MOY_UI_OV_TYPING, &one);    // edit="open"
    if (N->lit & NL_NAME)
        moy_ui_over_put(&o, MOY_UI_OV_NAME, &one);      // keys="name"
    if (N->t_aux >= 0)
        moy_ui_over_text(&o, MOY_UI_OV_HINT, sspan(e, ha, hn));
    int32_t r = moy_ui_api_field(c, s, sspan(e, la, ln), (uint8_t *)D->buf, max, len, &o);
    size_t nl = (size_t)(r & 0xffff);
    int done = (r & 0x10000) != 0;
    int moved = nl != cn || memcmp(D->buf, e->scratch.p + was, nl);
    if (commit) {
        if (moved) {
            D->has = 1;
            D->n = (uint16_t)nl;
            e->edits++;
        }
        if (done) {
            commit_field(e, k);
            if (N->on >= 0)
                fire(e, field_enter(e, c, N->on), k, -1, -1, NULL);
        }
        return;
    }
    if (moved)
        wrote_text(e, k, D->buf, nl, "typed", N->changed);
    if (done && N->on >= 0)
        fire(e, field_enter(e, c, N->on), k, -1, -1, NULL);
}

// A text view's lines: a model's rows (each its text field), or a text cut at its newlines (none
// for an empty text), where each starts kept while the text's version holds.
typedef struct {
    uit_t *e;
    int slot, f;
} tv_src_t;

static const uint8_t *tv_line(void *src, int32_t i, size_t *len)
{
    tv_src_t *t = src;
    uit_t *e = t->e;
    const uit_slot_t *S = &e->slots[t->slot];
    if (t->f >= 0) {
        const char *v = uit_cell(e, t->slot, i, t->f);
        *len = strlen(v);
        return (const uint8_t *)v;
    }
    uint32_t a = e->tvl[i], b = i + 1 < e->tvl_n ? e->tvl[i + 1] - 1 : S->sn;
    *len = b - a;
    return (const uint8_t *)S->s + a;
}

static int tv_lines(uit_t *e, int slot)
{
    const uit_slot_t *S = &e->slots[slot];
    if (e->tvl_slot == slot && e->tvl_ver == S->ver && e->tvl_s == S->s && e->tvl)
        return e->tvl_n;
    e->tvl_n = 0;
    if (S->sn) {
        for (uint32_t i = 0; i <= S->sn; i++) {
            if (i && S->s[i - 1] != '\n')
                continue;
            if (uit_grow((void **)&e->tvl, &e->tvl_cap, e->tvl_n + 1, sizeof *e->tvl))
                return e->tvl_n = 0;
            e->tvl[e->tvl_n++] = i;
        }
    }
    e->tvl_slot = (int16_t)slot, e->tvl_ver = S->ver, e->tvl_s = S->s;
    return e->tvl_n;
}

static void draw_text_view(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    moy_ui_over_t o;
    char id[UIT_ID_MAX + 1];
    tv_src_t src = {e, N->slot, N->cur};
    moy_ui_lines_t L = {&src, N->cur >= 0 ? e->slots[N->slot].nrows : tv_lines(e, N->slot), tv_line};
    int32_t opt[MOY_UI_TXO_LEN] = MOY_UI_TXO_DEFAULTS, out[2];
    opt[MOY_UI_TXO_SYNTAX] = N->btn;
    opt[MOY_UI_TXO_KEYS] = 1;           // a stop where it runs on
    opt[MOY_UI_TXO_FACE] = (N->lit & TV_PROSE) ? MOY_UI_TXF_UI : MOY_UI_TXF_MONO;
    opt[MOY_UI_TXO_WRAP] = (N->lit & TV_WRAP) != 0;
    opt[MOY_UI_TXO_FOLLOW] = (N->lit & TV_FOLLOW) != 0;
    opt[MOY_UI_TXO_GUTTER] = (N->lit & TV_GUTTER) != 0;
    if (N->lit & TV_WELL)
        opt[MOY_UI_TXO_PAPER] = 0;      // look="well"
    over_for(e, k, model, row, c, &o, id);
    moy_ui_api_text_view(c, s, span_of(id, strlen(id)), &L, opt, NULL, &o, out);
    int32_t box[4];
    if (moy_ui_api_box(c, span_of(id, strlen(id)), box))
        e->tv_stop_now = 1;
}

// A label's rows as the toolkit's labels, drawn; or with `h`, measured (their steps added to *h).
// A label's rows drawn, or with `h` measured: each row's `part` of the measure (3 its height,
// 4 how far the stack moves past it) added to *h.
static uint32_t prop_text(uit_t *e, int k, const char *name, int model, int row, uint32_t *n);

static int32_t len_of(uit_t *e, int t, int model, int row, int32_t dflt);
static int32_t int_of(uit_t *e, int t, int model, int row, int32_t dflt);

static void label_rows_m(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row, int32_t *h,
                         int part)
{
    const uit_node_t *N = NODE(k);
    moy_ui_over_t o;
    uint32_t n1, a1;
    if (N->t_icon >= 0 && !h) {
        uint32_t n, at = uit_tmpl_render(e, N->t_icon, model, row, &n);
        if (n)
            moy_ui_api_icon(c, sspan(e, at, n));
    }
    // tone=: a literal's index, or a template's word (dim, value, danger; another is ink)
    int tone = N->lit;
    if (!tone) {
        uint32_t nt, mark = e->scratch.n, at = prop_text(e, k, "tone", model, row, &nt);
        static const char *const TONES[] = {"dim", "value", "danger"};
        for (int i = 0; i < 3 && !tone; i++)
            if (nt == strlen(TONES[i]) && !memcmp(e->scratch.p + at, TONES[i], nt))
                tone = i + 1;
        e->scratch.n = mark;
    }
    a1 = text(e, k, 0, model, row, &n1);
    // scale=: its face at that whole scale, never under the page's; w=: its text at most that wide
    int32_t sc = int_of(e, N->t_value, model, row, 0), cap = len_of(e, N->t_aux, model, row, 0);
    sc = sc > e->fs ? sc : 0;
    int t = N->nbtn, opts = tone || (t & ~LT_CHAR) || sc || cap > 0;
    int lines = (t & LT_WRAP) == LT_WORD || (t & LT_LINES) ? (N->btn ? N->btn : 16) : 0;
    // wrap="char": lines of what fits the page's width, cut anywhere, each a label
    uint32_t per = 0;
    if ((t & LT_WRAP) == LT_CHAR) {
        moy_font_info_t fi;
        moy_ui_font(s->cart, MOY_UI_FONT_UI, &fi);
        int cw = fi.w * e->fs;
        per = (uint32_t)((e->pw - 32) / (cw > 1 ? cw : 1));
        if (per < 8)
            per = 8;
    }
    // `per` characters a line (a UTF-8 sequence is one); one line however long unwrapped,
    // none for an empty text cut by character (the reference's range over its length)
    if ((t & LT_WRAP) == LT_CHAR && !n1)
        return;
    int face = ((t >> LT_FACE_SHIFT) & 7) - 1;
    if ((t & LT_TEXT) && face < 0)
        face = MOY_UI_FONT_UI;          // size="text": drawn in the face it is measured in (`natural`)
    if ((t & LT_FIT) && face >= 0) {
        // its face where the theme has one that draws every character of its text and the
        // text fits the page's width in it, else the page's own face
        moy_font_info_t fi;
        uint32_t f = moy_ui_font(moy_ui_cart_on(), face, &fi);
        if (!f || !moy_text_covers(f, (const uint8_t *)e->scratch.p + a1, n1)) {
            face = -1;
        } else {
            int32_t out[5];
            moy_ui_api_text(c, lines, (t >> LT_ALIGN_SHIFT) & 7, tone, face);
            moy_ui_over_none(&o);
            moy_ui_api_measure(c, s, MOY_UI_MEASURE_LABEL, sspan(e, a1, n1), &o, out);
            if (out[2] > e->pw - 32)
                face = -1;
        }
    }
    const char *txt = e->scratch.p + a1;
    uint32_t at = 0;
    do {
        uint32_t m = at, chars = 0;
        while (m < n1 && chars < per) {
            m++;
            while (m < n1 && (txt[m] & 0xc0) == 0x80)
                m++;
            chars++;
        }
        if ((t & LT_WRAP) != LT_CHAR)
            m = n1;
        if (opts) {
            moy_ui_api_text(c, lines, (t >> LT_ALIGN_SHIFT) & 7, tone, face);
            moy_ui_api_text_size(c, sc, cap);
        }
        moy_ui_over_none(&o);
        if (h) {
            int32_t out[5];
            moy_ui_api_measure(c, s, MOY_UI_MEASURE_LABEL, sspan(e, a1 + at, m - at), opts ? &o : NULL, out);
            *h += out[part];
        } else {
            moy_ui_api_label(c, s, sspan(e, a1 + at, m - at), opts ? &o : NULL);
        }
        at = m;
    } while (at < n1);
}

static void label_rows(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row, int32_t *h)
{
    label_rows_m(e, c, s, k, model, row, h, 4);
}

// The scale a spacing at 1x is multiplied by: the host's (`uit_set_scale`, the chrome scale in
// force), else 2 on a desk and the font scale else. Hairlines, borders and rules take none.
static int32_t space_unit(const uit_t *e)
{
    return e->sc > 0 ? e->sc : (e->flags & UIT_F_DESK) ? 2 : e->fs;
}

// A spacing prop (template `t`, an int at 1x, literal or bound) in pixels; `dflt` (1x) where
// none is given.
static int32_t space_of(uit_t *e, int t, int model, int row, int32_t dflt)
{
    return (t < 0 ? dflt : int_of(e, t, model, row, 0)) * space_unit(e);
}

// A split's or a grid's gap or pad (an int at 1x) in pixels.
static int gap_px(uit_t *e, int v)
{
    return v * space_unit(e);
}

// How tall a split's column draws, measured before it draws: -1 where it holds a kind with no
// measure, which lays it out from its cell's top (`_col_h`).
static int col_h(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    int32_t h = 0;
    KIDS(k, g) {
        const uit_node_t *N = NODE(g);
        if (!uit_shown(e, g, model, row) ||
            (N->act >= 0 && !uit_act_can(e, N->act, model, row) && e->acts[N->act].off != 2))
            continue;
        if (N->kind == UIT_LABEL) {
            label_rows(e, c, s, g, model, row, &h);
        } else if (N->kind == UIT_BUTTON) {
            uint32_t n, a = text(e, g, 0, model, row, &n);
            moy_ui_over_t o;
            moy_ui_over_none(&o);
            int32_t one = 1, out[5];
            moy_ui_over_put(&o, MOY_UI_OV_FIT, &one);
            moy_ui_api_measure(c, s, MOY_UI_MEASURE_BUTTON, sspan(e, a, n), &o, out);
            h += out[4];
        } else {
            return -1;
        }
    }
    return h;
}

static void walk(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row);
// Node `k`'s scroll region opened (`ui.scroll`'s, a placed rows list's): its gen counts what it
// reads, so its scroll takes shift frames; `lit`'s SC_FOLLOW keeps its foot in view, SC_SNAP
// draws it in whole units.
static void scroll_open(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int lit)
{
    const char *key = uit_str(e, NODE(k)->key);
    int32_t one = 1, gen = (e->flags & UIT_F_GEN) && gen_ok(e) ? uit_cell_gen(e, k) : -1;
    moy_ui_over_t o;
    moy_ui_over_none(&o);
    if (lit & SC_FOLLOW)
        moy_ui_over_put(&o, MOY_UI_OV_FOLLOW, &one);
    if (lit & SC_SNAP)
        moy_ui_over_put(&o, MOY_UI_OV_SNAP, &one);
    if (gen >= 0)
        moy_ui_over_put(&o, MOY_UI_OV_GEN, &gen);
    moy_ui_api_scroll(c, s, span_of(key, strlen(key)), &o);
}

static void draw(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row);

// An int prop's value (template `t`, `dflt` where none is given).
static int32_t int_of(uit_t *e, int t, int model, int row, int32_t dflt)
{
    if (t < 0)
        return dflt;
    uint32_t n, mark = e->scratch.n, a = uit_tmpl_render(e, t, model, row, &n);
    int32_t v = (int32_t)strtol(e->scratch.p + a, NULL, 10);
    e->scratch.n = mark;
    return v;
}

// A size a build gives (w=, h=, side=): the handheld's at its font scale, the desk's as given.
static int32_t size_of(uit_t *e, int32_t v)
{
    return (e->flags & UIT_F_DESK) ? v : v * e->fs;
}

static uint32_t prop_text(uit_t *e, int k, const char *name, int model, int row, uint32_t *n);
static int32_t prop_int(uit_t *e, int k, const char *name, int model, int row);

// A card's or a picture's marks (`ui.card`'s o): its icon tile where it names an icon and holds
// no picture (`pic`), its tone (the sub line's ink, the veil a danger tone lays on its picture),
// the lock where its tone is "locked", a card's badge= icon on its picture's corner.
static void card_mark(uit_t *e, moy_ui_ctx_t *c, int k, int model, int row, int pic)
{
    const uit_node_t *N = NODE(k);
    static const char *const TONE_NAMES[] = {"ink", "dim", "value", "danger"};
    uint32_t tn = 0, ta = N->t_aux >= 0 ? uit_tmpl_render(e, N->t_aux, model, row, &tn) : 0;
    int tone = 0, locked = tn == 6 && !memcmp(e->scratch.p + ta, "locked", 6);
    for (int i = 0; i < 4 && tn && !locked; i++)
        if (strlen(TONE_NAMES[i]) == tn && !memcmp(e->scratch.p + ta, TONE_NAMES[i], tn))
            tone = i;
    uint32_t bn = 0, ba = N->kind == UIT_CARD ? prop_text(e, k, "badge", model, row, &bn) : 0;
    if ((N->t_icon < 0 || pic) && !tn && !bn)
        return;
    uint32_t in = 0, ia = N->t_icon >= 0 && !pic ? uit_tmpl_render(e, N->t_icon, model, row, &in) : 0;
    moy_ui_api_card_mark(c, sspan(e, ba, bn), locked ? 4 : tone, sspan(e, ia, in));
}

// A card's label_icon=: the icon before its label.
static void card_lead(uit_t *e, moy_ui_ctx_t *c, int k, int model, int row)
{
    uint32_t n = 0, a = prop_text(e, k, "label_icon", model, row, &n);
    if (n)
        moy_ui_api_card_lead(c, sspan(e, a, n));
}

// A card's or a picture's image (`image=`): its text into the scratch at *a (*n 0 where it names
// none or no front end draws pictures), and whether the front end holds the picture: 0, else the
// picture's gen (uit_pic_fn).
static int pic_held(uit_t *e, int k, int model, int row, uint32_t *a, uint32_t *n)
{
    *a = prop_text(e, k, "image", model, row, n);
    if (!e->pic_fn)
        *n = 0;
    return *n ? e->pic_fn(e->pic_ud, k, e->scratch.p + *a, *n, NULL) : 0;
}

// The card's tile (`out`, moy_ui_api_card's) handed to the front end, which draws the picture
// where it holds it and else owes it: clipped to the page's room cut to the scroll's floor, and
// whether the card is focused (its tile lifted, larger than the others').
static void pic_draw(uit_t *e, moy_ui_ctx_t *c, int k, uint32_t a, uint32_t n, const int32_t out[5])
{
    if (!n || out[2] <= 0)
        return;
    int32_t room = e->rect[3] > e->band_h ? e->rect[3] - e->band_h : 0;
    int32_t r[12] = {out[0], out[1], out[2], out[3], e->rect[0], e->rect[1], e->rect[2], room,
                     (out[4] & MOY_UI_ST_FOCUS) != 0, 0, 0, 0};
    moy_ui_api_card_clip(c, r + 4);
    if (r[6] > 0 && r[7] > 0)
        e->pic_fn(e->pic_ud, k, e->scratch.p + a, n, r);
}

// A card of a cards list (`_r_cards`' per row): its id, its marks, its label and sub line, its
// picture where the front end holds it, the picture's gen its gen (the icon tile while it has
// none, and no gen: a shift frame draws it again).
static void draw_card(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    moy_ui_over_t o;
    char id[UIT_ID_MAX + 1];
    over_for(e, k, model, row, c, &o, id);
    uint32_t pa, pn;
    int held = pic_held(e, k, model, row, &pa, &pn);
    int32_t pic_gen = pn ? held : 0;    // no app picture: the tile is the engine's alone
    if (!pn || held > 0)
        moy_ui_over_put(&o, MOY_UI_OV_GEN, &pic_gen);
    card_mark(e, c, k, model, row, held);
    card_lead(e, c, k, model, row);
    uint32_t n1, n2, a1 = text(e, k, 0, model, row, &n1), a2 = text(e, k, 1, model, row, &n2);
    int32_t out[5];
    moy_ui_api_card(c, s, sspan(e, a1, n1), sspan(e, a2, n2), &o, out);
    pic_draw(e, c, k, pa, pn, out);
    if ((out[4] & 2) && N->act >= 0 && uit_act_can(e, N->act, model, row))
        fire(e, N->act, k, model, row, NULL);
}

// A cards list (`_r_cards`): its own scrolled region, a grid of its cards, a caption and a grid
// of its own where its group= changes.
static void draw_cards(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k)
{
    const uit_node_t *N = NODE(k);
    const char *key = uit_str(e, N->key);
    int m = N->slot, desk = (e->flags & UIT_F_DESK) != 0, subs = 0, flow = (N->lit & CD_FLOW) != 0;
    int32_t w = size_of(e, int_of(e, N->t_value, -1, -1, 0)), h = size_of(e, int_of(e, N->t_aux, -1, -1, 0));
    if (flow) {
        // in the page's flow: its grid on the page's next rows (in a group, between its caption
        // and its rows), its cards stops of the page, scrolling with it
        moy_ui_api_grid(c, s, span_of(key, strlen(key)), w, h, NULL);
        uit_after_removal(e, k);
        for (int r = 0; r < e->slots[m].nrows; r++) {
            uint32_t mark = e->scratch.n;
            KIDS(k, g)
            if (NODE(g)->kind == UIT_CARD)
                draw_card(e, c, s, g, m, r);
            e->scratch.n = mark;
        }
        moy_ui_api_grid(c, s, span_of("", 0), 0, 0, NULL);
        return;
    }
    moy_ui_over_t go;
    int32_t gen = (e->flags & UIT_F_GEN) && gen_ok(e) ? uit_cell_gen(e, k) : -1;
    moy_ui_over_none(&go);
    if (gen >= 0)
        moy_ui_over_put(&go, MOY_UI_OV_GEN, &gen);
    moy_ui_api_scroll(c, s, span_of(key, strlen(key)), gen >= 0 ? &go : NULL);
    KIDS(k, g)
    if (NODE(g)->t_value >= 0)
        subs = 1;
    int margin = desk ? 16 : 8, foot = desk ? (subs ? 52 : 30) : 26 + (subs ? 6 : 0), cols = 0;
    int32_t pad = prop_int(e, k, "pad", -1, -1);
    if (pad > 0) {
        // pad=: the gap between its cards at 1x, a margin of 16 (or the gap, where that is
        // more) at either side; as many columns as its room holds at that gap, spread across it
        int32_t gp = pad * space_unit(e), mp = (pad > 16 ? pad : 16) * space_unit(e), room[5];
        margin = (int)(mp / e->fs);     // the spread's margin is in the font scale's steps
        moy_ui_api_measure(c, s, MOY_UI_MEASURE_PROGRESS, span_of("", 0), NULL, room);
        cols = (int)((room[2] - 2 * mp + gp) / (w + gp > 0 ? w + gp : 1));
        cols = cols < 1 ? 1 : cols;
    }
    int grid = N->t_main < 0, capped = 0;
    if (grid) {
        moy_ui_api_grid_spread(c, cols, foot, 4, margin, 2);
        moy_ui_api_grid(c, s, span_of(key, strlen(key)), w, h, NULL);
    }
    uit_after_removal(e, k);
    uit_buf_t cap = {0}, gid = {0};
    for (int r = 0; r < e->slots[m].nrows; r++) {
        uint32_t mark = e->scratch.n;
        if (N->t_main >= 0) {
            uint32_t n, a = uit_tmpl_render(e, N->t_main, m, r, &n);
            if (!capped || n != cap.n || memcmp(e->scratch.p + a, cap.p, n)) {
                if (grid)
                    moy_ui_api_grid(c, s, span_of("", 0), 0, 0, NULL);
                if (capped)
                    moy_ui_api_group(c, s, span_of("", 0), NULL);
                moy_ui_api_group(c, s, sspan(e, a, n), NULL);
                cap.n = 0;
                uit_buf_printf(&cap, "%.*s", (int)n, e->scratch.p + a);
                gid.n = 0;
                uit_buf_printf(&gid, "%s %.*s", key, (int)n, e->scratch.p + a);
                moy_ui_api_grid_spread(c, cols, foot, 4, margin, 2);
                moy_ui_api_grid(c, s, span_of(gid.p, gid.n), w, h, NULL);
                grid = capped = 1;
            }
        }
        KIDS(k, g)
        if (NODE(g)->kind == UIT_CARD)
            draw_card(e, c, s, g, m, r);
        e->scratch.n = mark;
    }
    uit_buf_free(&cap);
    uit_buf_free(&gid);
    if (grid)
        moy_ui_api_grid(c, s, span_of("", 0), 0, 0, NULL);
    if (capped)
        moy_ui_api_group(c, s, span_of("", 0), NULL);
    moy_ui_api_end(c, s);
    moy_ui_api_scroll(c, s, span_of("", 0), NULL);
}

// A cards list of the carousel look (`look="carousel"`, the handheld home's band): from where
// the page's stack stands to its foot, across its room, one row of tiles (moy_ui_api_carousel:
// its keys, a drag and a fling, the slide to the centre, the settle); a tile's size a function
// of its distance from the centre alone, the centre card's twice the others', each other pushed
// out by its share of what the centre grew (moy_ui_api_carousel_tile); in each rect of the floor
// the frame draws, every tile's shadow, then the tiles smallest first, the centre's last and,
// at rest with the focus, lifted by the theme's mark, and the centre card's label and sub line
// under them, in its tone= where it names one (a theme role or "#RRGGBB", over a black shadow:
// a band on pixels the theme does not know, a wallpaper). Opening the centre card fires its
// card's action; cur= follows the card the row rests on. The page's carousel as the frame left
// it is the front end's to ask after (uit_carousel).
enum { CAROUSEL_PARTS = 24, CAROUSEL_FLOOR = 8 };
static void draw_desk_shelf(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k);
static void draw_carousel(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k)
{
    if (e->flags & UIT_F_DESK) {
        draw_desk_shelf(e, c, s, k);
        return;
    }
    const uit_node_t *N = NODE(k);
    int m = N->slot, n = e->slots[m].nrows, cd = carousel_card(e, k);
    const char *key = uit_str(e, N->key);
    uit_after_removal(e, k);
    int32_t at[5];
    moy_ui_api_measure(c, s, MOY_UI_MEASURE_PROGRESS, span_of("", 0), NULL, at);
    int32_t band[4] = {e->rect[0], at[1], e->rect[2], e->rect[1] + e->rect[3] - at[1]};
    if (band[3] <= 0)
        return;
    moy_ui_api_space(c, band[3]);
    int32_t g[10];
    moy_ui_api_carousel_geom(e->fs, band, size_of(e, int_of(e, N->t_value, -1, -1, 64)), g);
    int32_t card = g[0], pitch = g[1] > 0 ? g[1] : 1;
    int cur = 0;
    if (N->cur >= 0) {
        const uit_slot_t *C = &e->slots[N->cur];
        int r = uit_row_find(e, m, C->s ? C->s : "", C->sn);
        if (r >= 0)
            cur = r;
    }
    id_put(e, k, m, n ? cur : -1, key);
    // its rows' cells, each its row's key: made again only where its model moved
    uit_buf_t *B = &e->cells;
    uint32_t ckey = (uint32_t)e->gen * 65537u + (uint32_t)e->slots[m].ver * 257u + (uint32_t)n;
    if (e->cells_node != k + 1 || e->cells_key != ckey) {
        B->n = 0;
        for (int r = 0; r < n; r++) {
            const char *v = row_key(e, m, r);
            uit_buf_put(B, v, strlen(v));
        }
        e->cells_node = (int16_t)(k + 1);
        e->cells_key = ckey;
    }
    int32_t out[5];
    moy_ui_api_carousel(c, s, span_of(key, strlen(key)), band, g, (const uint8_t *)B->p, n ? B->n : 0, cur,
                        out);
    int32_t off = out[2];
    int focused = out[4], moving = out[3] != 0;
    // the card nearest the centre at this scroll
    int32_t most = (int32_t)(n - 1) * pitch;
    int near = n ? (int)((off < most ? off : most) + pitch / 2) / pitch : 0;
    near = near < 0 ? 0 : near > n - 1 ? n - 1 : near;
    if (!e->car && !(e->car = UIT_MALLOC(UIT_CAROUSEL_WORDS * sizeof *e->car)))
        return;
    int32_t *cw = e->car;
    memcpy(cw, band, 4 * sizeof band[0]);
    memcpy(cw + 4, g, sizeof g);
    cw[14] = off;
    cw[15] = out[3];
    cw[16] = near;
    cw[17] = out[0];
    cw[18] = n;
    cw[19] = focused;
    e->car_node = (int16_t)(k + 1);
    // the floor: the rects the frame draws (it keeps nothing: the band's view)
    int32_t F[CAROUSEL_FLOOR][4], q[4];
    int nf = 0;
    while (moy_ui_api_table_floor(c, q) > 0)
        if (nf < CAROUSEL_FLOOR)
            memcpy(F[nf++], q, sizeof q);
    // the tiles the floor meets, each its row and its rect, smallest first
    typedef struct { int32_t i, r[4]; } part_t;
    part_t P[CAROUSEL_PARTS];
    int np = 0;
    int32_t pr[8], i;
    while ((i = moy_ui_api_table_part(c, s, pr)) >= 0) {
        if (np >= CAROUSEL_PARTS || i >= n)
            continue;
        int32_t t[4];
        moy_ui_api_carousel_tile(g, band, off, i, t);
        if (t[0] + t[2] <= band[0] || t[0] >= band[0] + band[2])
            continue;
        int j = np;
        int32_t key2 = 2 * t[2] + (i == near);
        while (j > 0 && 2 * P[j - 1].r[2] + (P[j - 1].i == near) > key2) {
            P[j] = P[j - 1];
            j--;
        }
        P[j].i = i;
        memcpy(P[j].r, t, sizeof t);
        np++;
    }
    uint32_t tn, tmark = e->scratch.n, ta = prop_text(e, k, "tone", -1, -1, &tn);
    int32_t ink = tn ? button_ink(e->scratch.p + ta, tn) : -1;
    e->scratch.n = tmark;
    for (int f = 0; f < nf; f++) {
        // each rect of the floor: the tiles' shadows, the tiles, the caption
        int32_t *Q = F[f];
        for (int j = 0; j < np; j++)
            moy_ui_api_tile_cast(c, s, P[j].r, Q, P[j].i == near);
        for (int j = 0; j < np; j++) {
            int r = P[j].i, centre = r == near, rest = centre && !moving;
            int32_t tile[10];
            moy_ui_api_tile(c, s, P[j].r, Q, card, rest && focused, tile);
            uint32_t pa = 0, pn = 0, mark = e->scratch.n;
            int held = cd >= 0 && pic_held(e, cd, m, r, &pa, &pn);
            if (!held) {
                uint32_t in = 0, ia = cd >= 0 && NODE(cd)->t_icon >= 0 ? uit_tmpl_render(e, NODE(cd)->t_icon, m, r, &in) : 0;
                moy_ui_api_tile_blank(c, s, tile, Q, sspan(e, ia, in));
            }
            if (pn) {
                // the front end's picture, drawn where it holds it, else owed: its tile, its clip,
                // what it is (2 a carousel's, 4 the centre's, 8 at rest, 1 lifted), its corners
                // and the size it decodes at
                int32_t pq[12] = {tile[0], tile[1], tile[2], tile[3], Q[0], Q[1], Q[2], Q[3],
                                  2 | (centre ? 4 : 0) | (rest ? 8 : 0) | tile[9], tile[4], g[8], g[8]};
                e->pic_fn(e->pic_ud, cd, e->scratch.p + pa, pn, pq);
            }
            e->scratch.n = mark;
            moy_ui_api_tile_end(c, s, tile, Q);
        }
        if (n && cd >= 0) {
            uint32_t mark = e->scratch.n, n1, n2;
            uint32_t a1 = text(e, cd, 0, m, near, &n1), a2 = text(e, cd, 1, m, near, &n2);
            moy_ui_api_carousel_caption(c, s, band, Q, g, sspan(e, a1, n1), sspan(e, a2, n2),
                                        ink >= 0 ? ink : MOY_UI_O_NONE);
            e->scratch.n = mark;
        }
    }
    int got = out[0];
    if (got < 0 || got >= n)
        return;
    const char *gk = row_key(e, m, got);
    size_t gn = strlen(gk);
    if (N->cur >= 0) {
        const uit_slot_t *C = &e->slots[N->cur];
        if (gn != C->sn || memcmp(gk, C->s ? C->s : "", gn))
            uit_cur_moved(e, k, gk, gn, "carousel", got != cur);   // (no move where it showed its cur)
    }
    id_put(e, k, m, got, key);
    if (out[1] && cd >= 0 && NODE(cd)->act >= 0 && uit_act_can(e, NODE(cd)->act, m, got))
        fire(e, NODE(cd)->act, cd, m, got, NULL);
}

// A cards list of the shelf or icons look (`look="shelf"`, `look="icons"`, the home's grid and
// icons arrangements): from where the page's stack stands to its foot, across its room, a grid
// of cards (moy_ui_api_cells_grid: its keys, its taps, a drag and a fling); in each rect of the
// floor the frame draws, every card but the current one, its picture the front end's (its tile,
// its clip, 16 a cell's, its corners, the size it decodes at) and its label under it, then the
// current card over its neighbours, grown by the focus and ringed flat while the cards hold the
// keys, its label bold; then the foot (a handheld shelf's fade into the ground, the handheld
// icons' caption band naming the current card and its sub line). In tone= (a theme role or
// "#RRGGBB") its labels lie over a black shadow and no fade hides what is under the band.
// Opening a card fires its card's action; cur= follows the card the keys are on. The page's
// cells as the frame left them are the front end's to ask after (uit_cells). The column look
// (`look="column"`): its tiles `w=` across on rows `h=` apart (in pixels; the class's desk
// tile where unset), each its card's `fill=` (a theme role or "#RRGGBB", a template; empty the
// tile's own) under its picture, 24 of the tile's 44 across, centred, and its label under it.
static void cells_pic(uit_t *e, int cd, int m, int r, const int32_t t[4], const int32_t *Q, int flags,
                      int corners, int side)
{
    uint32_t pa = 0, pn = 0, mark = e->scratch.n;
    if (cd >= 0 && pic_held(e, cd, m, r, &pa, &pn) && pn) {
        int32_t pq[12] = {t[0], t[1], t[2], t[3], Q[0], Q[1], Q[2], Q[3], flags, corners, side, side};
        e->pic_fn(e->pic_ud, cd, e->scratch.p + pa, pn, pq);
    }
    e->scratch.n = mark;
}

// The column look's geometry (cards list `k`, its card `cd`) in band `b` at font scale `fs`
// (moy_ui_api_column_geom), its tiles `w=` and rows `h=` apart, its widest label measured.
static void column_geom(uit_t *e, int k, int cd, const int32_t b[4], int fs, int desk,
                        int32_t g[MOY_UI_CELLS_G])
{
    const uit_node_t *N = NODE(k);
    int m = N->slot, n = e->slots[m].nrows, u = desk ? moy_ui_render_scale() : 1;
    int32_t side = int_of(e, N->t_value, -1, -1, 0), pitch = int_of(e, N->t_aux, -1, -1, 0);
    side = side > 0 ? side : desk ? 44 / u : 40 * fs;
    pitch = pitch > 0 ? pitch : desk ? 74 / u : 62 * fs;
    moy_font_info_t uf;
    uint32_t fid = moy_ui_font(0, MOY_UI_FONT_UI, &uf);
    int most = 0;
    for (int r = 0; r < n && cd >= 0; r++) {
        uint32_t mark = e->scratch.n, n1, a1 = text(e, cd, 0, m, r, &n1);
        int w = moy_text_width(fid, (const uint8_t *)e->scratch.p + a1, n1, fs);
        most = w > most ? w : most;
        e->scratch.n = mark;
    }
    moy_ui_api_column_geom(fs, desk, side, pitch, most, n, b, g);
}

static void draw_cells(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k)
{
    const uit_node_t *N = NODE(k);
    int m = N->slot, n = e->slots[m].nrows, cd = carousel_card(e, k);
    int column = (N->lit & CD_COLUMN) != 0;
    int look = (N->lit & CD_SHELF) ? MOY_UI_LOOK_SHELF : MOY_UI_LOOK_ICONS;
    const char *key = uit_str(e, N->key);
    uit_after_removal(e, k);
    int32_t at[5];
    moy_ui_api_measure(c, s, MOY_UI_MEASURE_PROGRESS, span_of("", 0), NULL, at);
    int32_t band[4] = {e->rect[0], at[1], e->rect[2], e->rect[1] + e->rect[3] - at[1]};
    if (band[3] <= 0)
        return;
    moy_ui_api_space(c, band[3]);
    int desk = (e->flags & UIT_F_DESK) != 0;
    int32_t g[MOY_UI_CELLS_G];
    if (column) {
        column_geom(e, k, cd, band, e->fs, desk, g);
    } else {
        moy_ui_api_cells_geom(look, e->fs, desk, desk ? moy_ui_render_scale() : 1, band, g);
    }
    int across = (int)g[MOY_UI_CELLS_ACROSS];
    int per = (int)(across ? g[MOY_UI_CELLS_ROWS] : g[MOY_UI_CELLS_COLS]);
    per = per < 1 ? 1 : per > 16 ? 16 : per;
    int cur = 0;
    if (N->cur >= 0) {
        const uit_slot_t *C = &e->slots[N->cur];
        int r = uit_row_find(e, m, C->s ? C->s : "", C->sn);
        if (r >= 0)
            cur = r;
    }
    id_put(e, k, m, n ? cur : -1, key);
    // its cards' keys, `per` a row of the table (the last row's cards to come empty): made
    // again only where its model or the grid's rows moved
    uit_buf_t *B = &e->cells;
    int rows = (n + per - 1) / per;
    uint32_t ckey = (uint32_t)e->gen * 65537u + (uint32_t)e->slots[m].ver * 257u + (uint32_t)n
                    + (uint32_t)per * 0x9e3779b1u;
    if (e->cells_node != k + 1 || e->cells_key != ckey) {
        B->n = 0;
        for (int r = 0; r < rows * per; r++) {
            const char *v = r < n ? row_key(e, m, r) : "";
            uit_buf_put(B, v, strlen(v));
        }
        e->cells_node = (int16_t)(k + 1);
        e->cells_key = ckey;
    }
    int32_t out[5];
    moy_ui_api_cells_grid(c, s, span_of(key, strlen(key)), band, g, (const uint8_t *)B->p, n ? B->n : 0, n,
                     cur, out);
    int32_t off = out[2];
    int focused = out[4], sel = out[0];
    if (!e->cel && !(e->cel = UIT_MALLOC(UIT_CELLS_WORDS * sizeof *e->cel)))
        return;
    int32_t *cw = e->cel;
    memcpy(cw, band, 4 * sizeof band[0]);
    memcpy(cw + 4, g, sizeof g);
    cw[20] = off;
    cw[21] = out[3];
    cw[22] = sel;
    cw[23] = n;
    cw[24] = focused;
    e->cel_node = (int16_t)(k + 1);
    int32_t F[CAROUSEL_FLOOR][4], q[4];
    int nf = 0;
    while (moy_ui_api_table_floor(c, q) > 0)
        if (nf < CAROUSEL_FLOOR)
            memcpy(F[nf++], q, sizeof q);
    // the table's rows the floor meets
    int32_t pr[8], i, lo = -1, hi = -1;
    while ((i = moy_ui_api_table_part(c, s, pr)) >= 0) {
        lo = lo < 0 || i < lo ? i : lo;
        hi = i > hi ? i : hi;
    }
    uint32_t tn, tmark = e->scratch.n, ta = prop_text(e, k, "tone", -1, -1, &tn);
    int32_t ink = tn ? button_ink(e->scratch.p + ta, tn) : -1;
    e->scratch.n = tmark;
    int side = (int)g[MOY_UI_CELLS_SIDE], cr = (int)g[MOY_UI_CELLS_R], gr = (int)g[MOY_UI_CELLS_GROW];
    int vh = (int)g[MOY_UI_CELLS_VIEW_H];
    for (int f = 0; f < nf; f++) {
        int32_t *Q = F[f];
        // the cards inside the view (the caption band under it is the foot's)
        int32_t V[4] = {Q[0], Q[1], Q[2], Q[3]};
        int vy1 = band[1] + vh;
        if (V[1] + V[3] > vy1)
            V[3] = vy1 - V[1] > 0 ? vy1 - V[1] : 0;
        for (int pass = 0; pass < 2 && lo >= 0 && V[3] > 0; pass++) {
            for (int r = pass ? sel : lo * per; r < n && (pass ? r == sel : r < (hi + 1) * per); r++) {
                int on = r == sel && focused;
                if (!pass && r == sel)
                    continue;
                int32_t t[4];
                moy_ui_api_cells_tile(g, band, off, r, t);
                int gg = on ? gr : 0;
                int32_t pt[4] = {t[0] - gg, t[1] - gg, t[2] + 2 * gg, t[3] + 2 * gg};
                if (column) {
                    // its tile in its fill, its picture 24 of the tile's 44 on it
                    uint32_t fmark = e->scratch.n, fn = 0, fa = cd >= 0 ? prop_text(e, cd, "fill", m, r, &fn) : 0;
                    int32_t fill = fn ? button_ink(e->scratch.p + fa, fn) : -1;
                    e->scratch.n = fmark;
                    moy_ui_api_cells_plate(c, s, t, V, fill >= 0 ? fill : MOY_UI_O_NONE);
                    int32_t is = t[2] * 24 / 44;
                    int32_t it[4] = {t[0] + (t[2] - is) / 2, t[1] + (t[3] - is) / 2, is, is};
                    cells_pic(e, cd, m, r, it, V, 16 | on, 0, is);
                } else {
                    cells_pic(e, cd, m, r, pt, V, 16 | on, cr ? cr + gg : 0, side);
                }
                uint32_t mark = e->scratch.n, n1;
                uint32_t a1 = cd >= 0 ? text(e, cd, 0, m, r, &n1) : 0;
                if (cd < 0)
                    n1 = 0;
                moy_ui_api_cells_card(c, s, g, t, V, on, sspan(e, a1, n1), ink >= 0 ? ink : MOY_UI_O_NONE);
                e->scratch.n = mark;
            }
        }
    }
    if (nf && n && cd >= 0) {
        // the foot, across the band the frame draws whole (the caption band lies under the view)
        uint32_t mark = e->scratch.n, n1, n2;
        uint32_t a1 = text(e, cd, 0, m, sel, &n1), a2 = text(e, cd, 1, m, sel, &n2);
        moy_ui_api_cells_foot(c, s, g, band, band, ink < 0, sspan(e, a1, n1), sspan(e, a2, n2));
        e->scratch.n = mark;
    }
    if (sel < 0 || sel >= n)
        return;
    const char *gk = row_key(e, m, sel);
    size_t gn = strlen(gk);
    if (N->cur >= 0) {
        const uit_slot_t *C = &e->slots[N->cur];
        if (gn != C->sn || memcmp(gk, C->s ? C->s : "", gn))
            uit_cur_moved(e, k, gk, gn, "cells", sel != cur);
    }
    id_put(e, k, m, sel, key);
    if (out[1] && cd >= 0 && NODE(cd)->act >= 0 && uit_act_can(e, NODE(cd)->act, m, sel))
        fire(e, NODE(cd)->act, cd, m, sel, NULL);
}

// A cards list of the carousel look on the desk class (the desk home's shelf): from where the
// page's stack stands to its foot, one row of cards `w=` a side (moy_ui_api_desk_shelf_geom),
// its motion the desk's (moy_ui_api_cells_grid under MOY_UI_LOOK_DESK: the current card moves
// at once and the shelf glides to show it); in each rect of the floor the frame draws, cut at
// the shelf's margin, its caption (`label=` and the count of its cards, apart by a dot), every
// card's shadow, then the cards, the current one last and, at rest, under the theme's focus
// mark where the cards hold the keys and focus draws, else its current mark: the card the app
// describes beside the shelf. Each card's picture is the front end's (its tile, its clip, 4 the current
// card's and 1 lifted, its corners, the size it decodes at). Opening a card fires its card's
// action; cur= follows the current card. The shelf as the frame left it is the front end's to
// ask after (uit_cells).
static void draw_desk_shelf(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k)
{
    const uit_node_t *N = NODE(k);
    int m = N->slot, n = e->slots[m].nrows, cd = carousel_card(e, k);
    const char *key = uit_str(e, N->key);
    uit_after_removal(e, k);
    int32_t at[5];
    moy_ui_api_measure(c, s, MOY_UI_MEASURE_PROGRESS, span_of("", 0), NULL, at);
    int32_t band[4] = {e->rect[0], at[1], e->rect[2], e->rect[1] + e->rect[3] - at[1]};
    if (band[3] <= 0)
        return;
    moy_ui_api_space(c, band[3]);
    int32_t g[MOY_UI_CELLS_G];
    int side = (int)int_of(e, N->t_value, -1, -1, 64);
    moy_ui_api_desk_shelf_geom(e->fs, moy_ui_render_scale(), band, side > 0 ? side : 64, g);
    int cur = 0;
    if (N->cur >= 0) {
        const uit_slot_t *C = &e->slots[N->cur];
        int r = uit_row_find(e, m, C->s ? C->s : "", C->sn);
        if (r >= 0)
            cur = r;
    }
    id_put(e, k, m, n ? cur : -1, key);
    // its cards' keys, one a row of the table: made again only where its model moved
    uit_buf_t *B = &e->cells;
    uint32_t ckey = (uint32_t)e->gen * 65537u + (uint32_t)e->slots[m].ver * 257u + (uint32_t)n + 0x5bd1e995u;
    if (e->cells_node != k + 1 || e->cells_key != ckey) {
        B->n = 0;
        for (int r = 0; r < n; r++) {
            const char *v = row_key(e, m, r);
            uit_buf_put(B, v, strlen(v));
        }
        e->cells_node = (int16_t)(k + 1);
        e->cells_key = ckey;
    }
    int32_t out[5];
    moy_ui_api_cells_grid(c, s, span_of(key, strlen(key)), band, g, (const uint8_t *)B->p, n ? B->n : 0, n,
                          cur, out);
    int32_t off = out[2];
    int focused = out[4], sel = out[0], moving = out[3] != 0;
    if (!e->cel && !(e->cel = UIT_MALLOC(UIT_CELLS_WORDS * sizeof *e->cel)))
        return;
    int32_t *cw = e->cel;
    memcpy(cw, band, 4 * sizeof band[0]);
    memcpy(cw + 4, g, sizeof g);
    cw[20] = off;
    cw[21] = out[3];
    cw[22] = sel;
    cw[23] = n;
    cw[24] = focused;
    e->cel_node = (int16_t)(k + 1);
    int32_t F[CAROUSEL_FLOOR][4], q[4];
    int nf = 0;
    while (moy_ui_api_table_floor(c, q) > 0)
        if (nf < CAROUSEL_FLOOR)
            memcpy(F[nf++], q, sizeof q);
    int32_t pr[8], i, lo = -1, hi = -1;
    while ((i = moy_ui_api_table_part(c, s, pr)) >= 0) {
        lo = lo < 0 || i < lo ? i : lo;
        hi = i > hi ? i : hi;
    }
    // the current card at rest wears the focus mark where the cards hold the keys and focus
    // draws (not under touch, nor while a window or a dialog over the page holds the marks),
    // else its current mark
    int at_rest = focused && moy_ui_sink_marks(s) ? 1 : 2;
    int32_t left = g[MOY_UI_CELLS_X0] + g[MOY_UI_CELLS_SIDE] - g[MOY_UI_CELLS_PX];
    uint32_t ln, lmark = e->scratch.n, la = prop_text(e, k, "label", -1, -1, &ln);
    for (int f = 0; f < nf; f++) {
        // the floor rect, cut at the shelf's margin: a card scrolled across it is cut there
        int32_t *Q = F[f], V[4] = {Q[0], Q[1], Q[2], Q[3]};
        if (V[0] < left) {
            V[2] = V[0] + V[2] - left > 0 ? V[0] + V[2] - left : 0;
            V[0] = left;
        }
        if (V[2] <= 0)
            continue;
        moy_ui_api_desk_caption(c, s, g, band, V, sspan(e, la, ln), n);
        for (int pass = 0; pass < 3 && lo >= 0; pass++) {
            // the shadows, the cards, then the current card over its neighbours
            for (int r = lo; r <= hi && r < n; r++) {
                if (pass && (r == sel) != (pass == 2))
                    continue;
                int32_t t[4];
                moy_ui_api_cells_tile(g, band, off, r, t);
                if (t[0] + t[2] <= left || t[0] >= band[0] + band[2])
                    continue;
                if (!pass) {
                    moy_ui_api_tile_cast(c, s, t, V, 0);
                    continue;
                }
                int rest = r == sel && !moving;
                int32_t tile[10];
                moy_ui_api_tile(c, s, t, V, -(int)g[MOY_UI_CELLS_SIDE], rest ? at_rest : 0, tile);
                int32_t pt[4] = {tile[0], tile[1], tile[2], tile[3]};
                cells_pic(e, cd, m, r, pt, V, (r == sel ? 4 : 0) | (tile[9] ? 1 : 0), (int)tile[4],
                          (int)g[MOY_UI_CELLS_SIDE]);
                moy_ui_api_tile_end(c, s, tile, V);
            }
        }
    }
    e->scratch.n = lmark;
    if (sel < 0 || sel >= n)
        return;
    const char *gk = row_key(e, m, sel);
    size_t gn = strlen(gk);
    if (N->cur >= 0) {
        const uit_slot_t *C = &e->slots[N->cur];
        if (gn != C->sn || memcmp(gk, C->s ? C->s : "", gn))
            uit_cur_moved(e, k, gk, gn, "carousel", sel != cur);
    }
    id_put(e, k, m, sel, key);
    if (out[1] && cd >= 0 && NODE(cd)->act >= 0 && uit_act_can(e, NODE(cd)->act, m, sel))
        fire(e, NODE(cd)->act, cd, m, sel, NULL);
}

int uit_cells(const uit_t *e, int32_t out[UIT_CELLS_WORDS])
{
    if (!e->cel_node)
        return 0;
    memcpy(out, e->cel, UIT_CELLS_WORDS * sizeof out[0]);
    return 1;
}

int uit_cells_tile(const uit_t *e, int i, int32_t out[4])
{
    const int32_t *w = e->cel;
    if (!e->cel_node || i < 0 || i >= w[23])
        return 0;
    moy_ui_api_cells_tile(w + 4, w, w[20], i, out);
    return out[0] + out[2] > w[0] && out[0] < w[0] + w[2] && out[1] + out[3] > w[1]
           && out[1] < w[1] + w[4 + MOY_UI_CELLS_VIEW_H];
}

int uit_cells_at(const uit_t *e, int x, int y)
{
    if (!e->cel_node)
        return -1;
    if (e->cel[4 + MOY_UI_CELLS_LOOK] == MOY_UI_LOOK_DESK)
        return moy_ui_api_desk_at(e->cel + 4, e->cel, e->cel[20], e->cel[23], x, y);
    return moy_ui_api_cells_at(e->cel + 4, e->cel, e->cel[20], e->cel[23], x, y);
}

int uit_cells_geom(uit_t *e, const int32_t b[4], int fs, int desk, int32_t out[16])
{
    for (int k = 0; k < (int)e->nnodes; k++) {
        if (NODE(k)->kind != UIT_CARDS || !(NODE(k)->lit & (CD_SHELF | CD_ICONS | CD_COLUMN)))
            continue;
        if (NODE(k)->lit & CD_COLUMN) {
            column_geom(e, k, carousel_card(e, k), b, fs, desk, out);
            return 1;
        }
        moy_ui_api_cells_geom((NODE(k)->lit & CD_SHELF) ? MOY_UI_LOOK_SHELF : MOY_UI_LOOK_ICONS, fs, desk,
                              desk ? moy_ui_render_scale() : 1, b, out);
        return 1;
    }
    return 0;
}

int uit_carousel_desk(const int32_t b[4], int fs, int keys, int nsets, const int32_t *counts,
                      const char *const *labels, const char *const *kinds, int32_t out[UIT_DESK_WORDS])
{
    moy_ui_desk_sets_t sets;
    if (nsets < 0 || nsets > MOY_UI_DESK_SETS)
        return -1;
    sets.n = nsets;
    for (int k = 0, at = 0; k < nsets; k++) {
        if (counts[k] < 0 || counts[k] > MOY_UI_DESK_SET_MAX)
            return -1;
        sets.count[k] = (uint8_t)counts[k];
        for (int i = 0; i < counts[k]; i++, at++) {
            int kind = -1;
            for (int j = 0; j <= 3; j++)                // normal, primary, tonal, danger
                if (!strcmp(kinds[at], moy_ui_button_kinds[j][0]))
                    kind = j;
            if (kind < 0)
                return -1;
            sets.kind[k][i] = (uint8_t)kind;
            sets.label[k][i] = (moy_ui_span_t){(const uint8_t *)labels[at], (uint16_t)strlen(labels[at])};
        }
    }
    moy_ui_api_carousel_desk(fs, moy_ui_render_scale(), keys, &sets, b, out);
    return 0;
}

int uit_carousel(const uit_t *e, int32_t out[UIT_CAROUSEL_WORDS])
{
    if (!e->car_node)
        return 0;
    memcpy(out, e->car, UIT_CAROUSEL_WORDS * sizeof out[0]);
    return 1;
}

int uit_carousel_tile(const uit_t *e, int row, int32_t out[4])
{
    if (!e->car_node || row < 0 || row >= e->car[18])
        return 0;
    moy_ui_api_carousel_tile(e->car + 4, e->car, e->car[14], row, out);
    return out[0] + out[2] > e->car[0] && out[0] < e->car[0] + e->car[2];
}

int uit_carousel_at(const uit_t *e, int x, int y)
{
    if (!e->car_node || x < e->car[0] || x >= e->car[0] + e->car[2])
        return -1;
    return moy_ui_api_carousel_at(e->car + 4, e->car, e->car[14], e->car[18], x, y);
}

int uit_carousel_geom(uit_t *e, const int32_t b[4], int fs, int desk, int32_t out[10])
{
    for (int k = 0; k < (int)e->nnodes; k++) {
        if (!IS_CAROUSEL(k))
            continue;
        int32_t side = int_of(e, NODE(k)->t_value, -1, -1, 64);
        moy_ui_api_carousel_geom(fs, b, desk ? side : side * fs, out);
        return 1;
    }
    return 0;
}

static void put_rect(uit_t *e, int k, const int32_t r[4]);

// A picture of look="tile": a carousel's tile of its own at its place (its part, a stop where it
// has on=): its shadow round it, its picture the front end's over the tile at the radius of a
// carousel's centre card (pic_fn's flags 4), else its icon on a blank tile, the focus mark round
// it where it holds the keys.
static void draw_tile_picture(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model,
                              int row, int32_t side, int on)
{
    char key[UIT_ID_MAX + 1];
    node_id(e, k, model, row, key);
    int32_t one = 1, zero = 0, r[5];
    moy_ui_over_t o;
    moy_ui_over_none(&o);
    moy_ui_over_text(&o, MOY_UI_OV_ID, span_of(key, strlen(key)));
    moy_ui_over_put(&o, MOY_UI_OV_BARE, &one);      // the tile is its well
    moy_ui_over_put(&o, MOY_UI_OV_MARK, &zero);     // ...and its mark the tile's own
    if (!on)
        moy_ui_over_put(&o, MOY_UI_OV_DISABLED, &one);
    moy_ui_api_part(c, s, span_of(key, strlen(key)), side, side, &o, r);
    int32_t t[4] = {c->pa_box.x, c->pa_box.y, c->pa_box.w, c->pa_box.h};
    put_rect(e, k, t);                  // where a press on it lands (`uit_rect`)
    if (!c->pa_none && t[2] > 0) {
        // (the sink's clip bounds what shows: its shadow falls round the place)
        static const int32_t all[4] = {-0x3fff, -0x3fff, 0x7ffe, 0x7ffe};
        int desk = (e->flags & UIT_F_DESK) != 0, mark = (r[4] & MOY_UI_ST_FOCUS) && moy_ui_sink_marks(s);
        int32_t tile[10];
        moy_ui_api_tile_cast(c, s, t, all, 1);
        moy_ui_api_tile(c, s, t, all, desk ? -(t[2] / 2) : t[2] / 2, mark, tile);
        uint32_t pa, pn, m = e->scratch.n;
        if (pic_held(e, k, model, row, &pa, &pn) && pn) {
            int32_t pq[12] = {tile[0], tile[1], tile[2], tile[3], all[0], all[1], all[2], all[3], 4, tile[4],
                              tile[2], tile[3]};
            e->pic_fn(e->pic_ud, k, e->scratch.p + pa, pn, pq);
        } else {
            // no picture held: its icon on a blank tile
            uint32_t in = 0, ia = NODE(k)->t_icon >= 0 ? uit_tmpl_render(e, NODE(k)->t_icon, model, row, &in) : 0;
            moy_ui_api_tile_blank(c, s, tile, all, sspan(e, ia, in));
        }
        e->scratch.n = m;
        moy_ui_api_tile_end(c, s, tile, all);
    }
    if (on && (r[4] & MOY_UI_ST_ACTIVATED))
        fire(e, NODE(k)->on, k, model, row, NULL);
}

// One picture at its own place (`_r_picture`): a card with no words, its icon on a tinted tile;
// look="tile" a carousel's tile (draw_tile_picture). With on= it is a stop a tap or Enter fires
// on= from, else no stop.
static void draw_picture(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    int32_t side = size_of(e, int_of(e, N->t_value, model, row, 64)), one = 1, out[5];
    int on = N->on >= 0 && uit_act_can(e, N->on, model, row);
    if (N->lit & PC_TILE) {
        draw_tile_picture(e, c, s, k, model, row, side, on);
        return;
    }
    moy_ui_over_t o;
    moy_ui_over_none(&o);
    if (!on)
        moy_ui_over_put(&o, MOY_UI_OV_DISABLED, &one);
    moy_ui_api_grid_spread(c, 1, -1, 4, (e->flags & UIT_F_DESK) ? 16 : 8, 0);
    moy_ui_api_grid(c, s, span_of("pic ", 4), side, side, NULL);
    uint32_t pa, pn;
    int held = pic_held(e, k, model, row, &pa, &pn);
    card_mark(e, c, k, model, row, held);
    moy_ui_api_card(c, s, span_of("", 0), span_of("", 0), &o, out);
    pic_draw(e, c, k, pa, pn, out);
    moy_ui_api_grid(c, s, span_of("", 0), 0, 0, NULL);
    if (on && (out[4] & MOY_UI_ST_ACTIVATED))
        fire(e, N->on, k, model, row, NULL);
}

// A seg of look="pictures": its items image texts (`own:KEY`, `store:KIND/NAME`), the row the
// engine's (moy_ui_api_pics) and each item's picture the front end's, drawn in its tile over the
// plate. The row's gen is the pictures' while the front end holds every one (a shift frame moves
// them), none while one is owed (it draws again).
static void draw_pics(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                      uint32_t a1, uint32_t n1)
{
    const uit_node_t *N = NODE(k);
    int field = (N->lit & NL_FIELD) != 0, count, at;
    uint32_t len, items = field ? field_seg_items(e, N, model, row, &len, &count, &at)
                                : seg_items(e, N, &len, &count, &at);
    int32_t gen = 0, all = 1;
    for (int i = 0, p = (int)items; i < count; i++) {
        size_t n = strlen(e->scratch.p + p);
        int held = n && e->pic_fn ? e->pic_fn(e->pic_ud, k, e->scratch.p + p, n, NULL) : 0;
        all &= held > 0 || !n || !e->pic_fn;
        gen = gen * 31 + held;
        p += (int)n + 1;
    }
    moy_ui_over_t o;
    char id[UIT_ID_MAX + 1];
    over_for(e, k, model, row, c, &o, id);
    if (all)
        moy_ui_over_put(&o, MOY_UI_OV_GEN, &gen);
    int32_t box[5];
    int got = moy_ui_api_pics(c, s, sspan(e, a1, n1), count, at, &o, box);
    if (e->pic_fn && box[2] > 0) {
        int32_t room = e->rect[3] > e->band_h ? e->rect[3] - e->band_h : 0;
        for (int i = 0, p = (int)items; i < count; i++) {
            size_t n = strlen(e->scratch.p + p);
            int32_t r[9] = {0, 0, 0, 0, e->rect[0], e->rect[1], e->rect[2], room, 0};
            moy_ui_api_pics_tile(c, box, count, i, r);
            moy_ui_api_card_clip(c, r + 4);
            if (n && r[6] > 0 && r[7] > 0)
                e->pic_fn(e->pic_ud, k, e->scratch.p + p, n, r);
            p += (int)n + 1;
        }
    }
    if (got >= 0 && got < count && got != at) {
        if (field) {
            char was[16], now[16];
            snprintf(was, sizeof was, "%d", at);
            snprintf(now, sizeof now, "%d", got);
            row_wrote(e, k, model, row, now, was, now);
        } else {
            const char *v = seg_key(e, N, got);
            wrote_text(e, k, v, strlen(v), "from", N->on);
        }
    }
}

// A split's cells' sizes across `span` (`_spans`): its first `limit` sizes, with a weight ("N*")
// among them each int a fixed size in desk units and the weights sharing the rest, else every int
// a weight; the last takes what rounding leaves, across (`across`) the fixed sizes the span cannot
// hold sharing it by their sizes. The count into *count.
enum { SPLIT_CELLS = 8 };
static int32_t split_spans(uit_t *e, const uit_node_t *N, int model, int row, int32_t room, int32_t gap,
                           int across, int limit, int32_t spans[SPLIT_CELLS], int *count)
{
    uint32_t zn, za = uit_tmpl_render(e, N->t_aux, model, row, &zn);
    int32_t v[SPLIT_CELLS];
    uint8_t weight[SPLIT_CELLS];
    int nz = 0, any_w = 0;
    const char *p = e->scratch.p + za, *end = p + zn;
    while (p < end && nz < SPLIT_CELLS && nz < limit) {
        while (p < end && *p == ' ')
            p++;
        if (p >= end)
            break;
        char *stop;
        long x = strtol(p, &stop, 10);
        weight[nz] = stop < end && *stop == '*';
        if (weight[nz])
            x = stop == p ? 1 : x, stop++, any_w = 1;
        v[nz++] = (int32_t)x;
        p = stop;
        while (p < end && *p != ' ')
            p++;
    }
    int32_t sum = 0, span = room - gap * (nz - 1);
    if (any_w) {
        int32_t fixed = 0, ws = 0;
        for (int i = 0; i < nz; i++)
            if (weight[i])
                ws += v[i];
            else
                fixed += size_of(e, v[i]);
        int32_t rest = span - fixed > 0 ? span - fixed : 0, share = across && fixed > span && span > 0;
        for (int i = 0; i < nz; i++)
            spans[i] = weight[i] ? rest * v[i] / (ws > 1 ? ws : 1)
                       : share   ? (int32_t)((int64_t)size_of(e, v[i]) * span / fixed)
                                 : size_of(e, v[i]);
    } else {
        int32_t tot = 0;
        for (int i = 0; i < nz; i++)
            tot += v[i];
        for (int i = 0; i < nz; i++)
            spans[i] = span * v[i] / (tot > 1 ? tot : 1);
    }
    for (int i = 0; i < nz; i++)
        sum += spans[i];
    if (nz)
        spans[nz - 1] += span - sum;
    *count = nz;
    return span;
}

static void label_rows_m(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row, int32_t *h,
                         int part);

// How tall a popover split's kid draws (`_pop_kid_h`): a label's lines, a progress row.
static int32_t pop_kid_h(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    int32_t h = 0, out[5];
    if (NODE(k)->kind == UIT_LABEL) {
        label_rows_m(e, c, s, k, model, row, &h, 3);
        return h;
    }
    if (NODE(k)->kind == UIT_PROGRESS) {
        moy_ui_api_measure(c, s, MOY_UI_MEASURE_PROGRESS, span_of("", 0), NULL, out);
        return out[3];
    }
    return 0;
}

static int32_t pop_cell_h(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    if (N->kind == UIT_PICTURE)
        return size_of(e, int_of(e, N->t_value, model, row, 64)) + size_of(e, 8);
    if (N->kind != UIT_GROUP)
        return pop_kid_h(e, c, s, k, model, row);
    int32_t h = 0;
    KIDS(k, g)
    if (uit_shown(e, g, model, row))
        h += pop_kid_h(e, c, s, g, model, row);
    return h;
}

// A split in a popover's body (`_pop_split`, dir "row"): its cells side by side on the body's
// rows, in by its pad, as tall as its tallest cell; a group cell its kids one under another.
static void pop_split(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    int kids[SPLIT_CELLS], nk = 0;
    int32_t hs[SPLIT_CELLS], top = 0, out[5];
    KIDS(k, g)
    if (nk < SPLIT_CELLS && uit_shown(e, g, model, row)) {
        hs[nk] = pop_cell_h(e, c, s, g, model, row);
        if (hs[nk] > top)
            top = hs[nk];
        kids[nk++] = g;
    }
    moy_ui_api_measure(c, s, MOY_UI_MEASURE_PROGRESS, span_of("", 0), NULL, out);   // where the body's stack stands
    int pad = gap_px(e, N->btn), gap = gap_px(e, N->nbtn);
    moy_ui_api_space(c, top + 2 * pad);
    if (!out[2])
        return;
    int32_t x = out[0] + pad, y = out[1] + pad, w = out[2] - 2 * pad > 0 ? out[2] - 2 * pad : 0;
    int32_t spans[SPLIT_CELLS];
    int nz;
    split_spans(e, N, model, row, w, gap, 1, nk, spans, &nz);
    int32_t at = x;
    for (int i = 0; i < nk && i < nz; i++) {
        int g = kids[i];
        if (NODE(g)->kind == UIT_GROUP) {
            int32_t cy = y;
            KIDS(g, gg) {
                if (!uit_shown(e, gg, model, row))
                    continue;
                int32_t kh = pop_kid_h(e, c, s, gg, model, row);
                moy_ui_api_at(c, at, cy, spans[i], kh);
                draw(e, c, s, gg, model, row);
                cy += kh;
            }
        } else {
            moy_ui_api_at(c, at, y, spans[i], hs[i]);
            draw(e, c, s, g, model, row);
        }
        at += spans[i] + gap;
    }
}

// A popover (`_r_popover`): centred across the page, from the top of its anchor's stop (a list's
// current row for "LIST.cur") as a point it slides up from to fit whole; on the desk a button's
// or a link's hangs under it; its close= fired the frame it is dismissed.
static void placed_popover(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k);

// A popover's override: its wash= (lit: the toolkit's wash + 1, 0 none given)
static const moy_ui_over_t *pop_over(const uit_node_t *N, moy_ui_over_t *o)
{
    int32_t w = N->lit - 1;
    if (!N->lit)
        return NULL;
    moy_ui_over_none(o);
    moy_ui_over_put(o, MOY_UI_OV_WASH, &w);
    return o;
}

static void draw_popover(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    if (e->placed) {
        placed_popover(e, c, s, k);
        return;
    }
    const uit_node_t *N = NODE(k);
    const char *key = uit_str(e, N->key);
    int32_t w = size_of(e, int_of(e, N->t_aux, model, row, 200));
    if (N->t_value >= 0) {
        uint32_t n, mark = e->scratch.n, a = uit_tmpl_render(e, N->t_value, model, row, &n);
        const char *want = e->scratch.p + a;
        size_t wn = n;
        if (n > 4 && !memcmp(want + n - 4, ".cur", 4))
            for (int l = 0; l < e->nnodes; l++) {
                const uit_node_t *L = NODE(l);
                const char *mn = uit_str(e, e->slots[L->slot].name);
                if (UIT_IS_LIST(L->kind) && L->cur >= 0 && strlen(mn) == n - 4 && !memcmp(mn, want, n - 4)) {
                    const uit_slot_t *C = &e->slots[L->cur];
                    want = C->s ? C->s : "", wn = C->sn;
                    break;
                }
            }
        for (int i = 0; i < e->nids; i++) {
            const uit_id_t *I = &e->ids[i];
            const char *got = I->row >= 0 ? row_key(e, uit_model_of(e, I->node), I->row) : uit_str(e, NODE(I->node)->key);
            int32_t box[4];
            if (strlen(got) == wn && !memcmp(got, want, wn)) {
                if (moy_ui_api_box(c, span_of(I->id, strlen(I->id)), box)) {
                    int32_t x = e->rect[0] + (e->rect[2] - w) / 2, y = box[1] - 8;
                    int kd = NODE(I->node)->kind;
                    if ((e->flags & UIT_F_DESK) && I->row < 0 && (kd == UIT_BUTTON || kd == UIT_LINK)) {
                        // on the desk a button's or a link's hangs under it, its left edge at
                        // the anchor's, kept inside the page
                        int32_t most = e->rect[0] + e->rect[2] - w;
                        x = box[0] < most ? box[0] : most;
                        x = x > e->rect[0] ? x : e->rect[0];
                        y = box[1] + box[3] + 4;
                    }
                    moy_ui_api_at(c, x, y, w, 0);
                }
                break;
            }
        }
        e->scratch.n = mark;
    }
    for (int p = N->props; p != (int)UIT_NONE; p = e->props[p].next) {
        // at=: hung from the rect its host hands in, "X Y W H" (none while it renders empty)
        const uit_prop_t *P = &e->props[p];
        if (P->kind != PK_TMPL || strcmp(uit_str(e, P->name), "at"))
            continue;
        uint32_t n, mark = e->scratch.n, a = uit_tmpl_render(e, P->idx, model, row, &n);
        char t[64];
        size_t m = n < sizeof t - 1 ? n : sizeof t - 1;
        memcpy(t, e->scratch.p + a, m);
        t[m] = 0;
        e->scratch.n = mark;
        long r[4];
        char *q = t;
        int got = 0;
        for (char *end; got < 4; got++, q = end) {
            r[got] = strtol(q, &end, 10);
            if (end == q)
                break;
        }
        if (got == 4)
            moy_ui_api_at(c, (int32_t)r[0], (int32_t)r[1], (int32_t)r[2], (int32_t)r[3]);
    }
    moy_ui_over_t o;
    if (!moy_ui_api_popover(c, s, span_of(key, strlen(key)), w, pop_over(N, &o)) && N->on >= 0)
        fire(e, N->on, k, -1, -1, NULL);
    e->in_pop = 1;
    walk(e, c, s, k, model, row);
    e->in_pop = 0;
    if (e->pop_hints_n) {
        // the bare page's band: the toolkit draws it in the card, under a rule
        moy_ui_api_hints(c, s, e->pop_hints, e->pop_hints_n, NULL);
        e->pop_hints_n = 0;
    }
    moy_ui_api_popover(c, s, span_of("", 0), 0, NULL);
}

// A split (not in a popover): its cells across the page's room in by its pad, each a fixed size
// in desk units or a weight of what is left ("N*"; with none, every size a weight); a group cell
// its own scrolled column, any other kind drawn as it stands.
// The width a link row `k` needs to draw its icon, its label and, with `value`, its value
// whole (the toolkit's MOY_UI_MEASURE_LINK; without, its least, as its value gives way to its
// label), 0 where it is not shown.
static int32_t link_w(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                      int value)
{
    if (!uit_shown(e, k, model, row))
        return 0;
    char t[256];
    uint32_t n1, a1 = text(e, k, 0, model, row, &n1);
    size_t m = n1 < sizeof t - 1 ? n1 : sizeof t - 1, v = 0;
    memcpy(t, e->scratch.p + a1, m);
    if (value) {
        t[m++] = '\t';
        uint32_t n2, a2 = text(e, k, 1, model, row, &n2);
        v = n2 < sizeof t - m ? n2 : sizeof t - m;
        memcpy(t + m, e->scratch.p + a2, v);
    }
    // measured with its icon, as it draws (`over_for`)
    const uit_node_t *N = NODE(k);
    int16_t slot = c->icon_slot, glyph = c->icon_glyph;
    uint32_t mark = e->scratch.n, n = 0, at = 0;
    const char *ic = NULL;
    if (N->t_icon >= 0)
        at = uit_tmpl_render(e, N->t_icon, model, row, &n), ic = e->scratch.p + at;
    else if (N->act >= 0)
        ic = uit_str(e, e->acts[N->act].icon), n = (uint32_t)strlen(ic);
    if (n) {
        c->icon_slot = (int16_t)moy_ui_icon_slot((const uint8_t *)ic, n);
        c->icon_glyph = (int16_t)moy_ui_icon_glyph((const uint8_t *)ic, n);
    }
    e->scratch.n = mark;
    int32_t out[5];
    moy_ui_api_measure(c, s, MOY_UI_MEASURE_LINK, span_of(t, m + v), NULL, out);
    c->icon_slot = slot, c->icon_glyph = glyph;
    return out[2];
}

// The widest link row in region `k` (`_row_w`): every row of a rows' model, a group's own, a
// scroll's and its switch's shown case's; with `value` their values whole, without their least.
static int32_t row_w(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                     int value)
{
    int32_t w = 0, x;
    KIDS(k, g) {
        const uit_node_t *N = NODE(g);
        if (N->kind == UIT_ROWS) {
            for (int r = 0, b; r < e->slots[N->slot].nrows; r++)
                if ((b = uit_row_body(e, g, r)) >= 0)
                    KIDS(b, kk)
                    if (NODE(kk)->kind == UIT_LINK && (x = link_w(e, c, s, kk, N->slot, r, value)) > w)
                    w = x;
        } else if (N->kind == UIT_LINK) {
            if ((x = link_w(e, c, s, g, model, row, value)) > w)
                w = x;
        } else if (N->kind == UIT_GROUP || N->kind == UIT_SCROLL || N->kind == UIT_CASE) {
            if ((x = row_w(e, c, s, g, model, row, value)) > w)
                w = x;
        } else if (N->kind == UIT_SWITCH) {
            int cs = uit_case_of(e, g);
            if (cs >= 0 && (x = row_w(e, c, s, cs, model, row, value)) > w)
                w = x;
        }
    }
    return w;
}

static int32_t row_need(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                        int32_t h, int least);
static int32_t button_w(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row);

// The width seg `k` (a seg of words) needs to show its label and options whole, else 0.
static int32_t seg_need(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    if (N->lit & (NL_PICS | NL_FIELD | NL_CYCLE | NL_SWATCH))
        return 0;
    uint32_t mark = e->scratch.n, n1, len;
    int count, at;
    uint32_t a1 = text(e, k, 0, model, row, &n1), items = seg_items(e, N, &len, &count, &at);
    char buf[256];
    uint32_t n = 0;
    if (n1 + 1 + len <= sizeof buf) {
        memcpy(buf, e->scratch.p + a1, n1);
        buf[n1] = '\t';
        memcpy(buf + n1 + 1, e->scratch.p + items, len);
        n = n1 + 1 + len;
    }
    e->scratch.n = mark;
    int32_t out[5] = {0};
    if (n)
        moy_ui_api_measure(c, s, MOY_UI_MEASURE_SEG, span_of(buf, n), NULL, out);
    return out[2];
}

// A row split's widths (`_fit_spans`): each group cell whose link rows need more than its size,
// and each row whose cells' natural widths do, gives it widened to that need, the cells beside
// it giving up at most half their share, down to their needs (a row's least: `row_need`; a
// group's, its links' labels, whose values give way).
static void fit_spans(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int *kids, int nk,
                      int model, int row, int32_t *spans, int nz, int32_t h)
{
    int32_t need[SPLIT_CELLS] = {0}, floor[SPLIT_CELLS];
    int any = 0;
    for (int i = 0; i < nk && i < nz; i++)
        if (NODE(kids[i])->kind == UIT_GROUP)
            any |= (need[i] = row_w(e, c, s, kids[i], model, row, 1)) > 0;
        else if (NODE(kids[i])->kind == UIT_ROW)
            any |= (need[i] = row_need(e, c, s, kids[i], model, row, h, 0)) > 0;
        else if (NODE(kids[i])->kind == UIT_SEG)
            any |= (need[i] = seg_need(e, c, s, kids[i], model, row)) > 0;
    if (!any)
        return;
    for (int j = 0; j < nz; j++) {
        int32_t least = j >= nk ? need[j]
                        : NODE(kids[j])->kind == UIT_ROW ? row_need(e, c, s, kids[j], model, row, h, 1)
                        : NODE(kids[j])->kind == UIT_GROUP ? row_w(e, c, s, kids[j], model, row, 0)
                        : need[j];
        floor[j] = spans[j] / 2 > least ? spans[j] / 2 : least;
    }
    for (int i = 0; i < nk && i < nz; i++) {
        int32_t short_ = need[i] - spans[i];
        for (int j = 0; j < nz && short_ > 0; j++) {
            int32_t give = j != i ? spans[j] - floor[j] : 0;
            give = give < short_ ? give : short_;
            if (give > 0) {
                spans[j] -= give;
                spans[i] += give;
                short_ -= give;
            }
        }
    }
}

static int32_t fixed_h(uit_t *e, int k);

// The height cell `k` of a column split needs: its fixed height (`fixed_h`), a row split's
// tallest cell's; 0 where it is a fill.
static int32_t cell_h(uit_t *e, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    if (N->kind == UIT_SPLIT) {
        uint32_t dn, da = uit_tmpl_render(e, N->t_value, model, row, &dn);
        if (dn != 3 || memcmp(e->scratch.p + da, "row", 3))
            return 0;
        int32_t h = 0, x;
        KIDS(k, g)
        if (uit_shown(e, g, model, row) && (x = cell_h(e, g, model, row)) > h)
            h = x;
        return h + 2 * gap_px(e, N->btn);
    }
    int32_t h = fixed_h(e, k);
    return h > 0 ? h : 0;
}

// A column split's heights at a font scale over 1, where a build's sizes, its design's at 1,
// no longer hold their text: each cell shorter than it needs (`cell_h`; a row of buttons) is
// given it from the last cell, which takes what the others leave, down to that cell's own need.
static void fit_heights(uit_t *e, const int *kids, int nk, int model, int row, int32_t *spans, int nz)
{
    if (e->fs <= 1)
        return;
    int last = (nk < nz ? nk : nz) - 1;
    for (int i = 0; i < last; i++) {
        int32_t short_ = cell_h(e, kids[i], model, row) - spans[i];
        int32_t give = spans[last] - cell_h(e, kids[last], model, row);
        give = give < short_ ? give : short_;
        if (give > 0)
            spans[last] -= give, spans[i] += give;
    }
}

static int32_t h_row(const uit_t *e);

// The least a palette of cells takes in a column: its rows, each a third of its side and 8 px at
// least -- a square still told apart and pointed at.
static int32_t cells_least(uit_t *e, int k, int model, int row)
{
    int32_t sc = (e->flags & UIT_F_DESK) ? 1 : e->fs;
    int32_t count = prop_int(e, k, "count", model, row), cols = prop_int(e, k, "cols", model, row);
    int32_t side = prop_int(e, k, "side", model, row) * sc, least;
    count = count ? count : 64, cols = cols ? cols : 8, side = side ? side : 12 * sc;
    least = (side + 2) / 3 > 8 ? (side + 2) / 3 : 8;
    return (count + cols - 1) / cols * (least < side ? least : side);
}

// A column split whose cells run past its room (a window shorter than its design, a font
// scale its sizes do not hold): the overrun -- what the last cell's room falls short of 0 --
// given by the palettes of cells before it, which fit their cells to the room they get, each by
// its share of what lies above its least (cells_least). Answers what is left over where it holds
// a palette: the column scrolls by that (draw_split).
static int32_t fit_room(uit_t *e, const int *kids, int nk, int32_t *spans, int nz, int32_t span,
                        int model, int row)
{
    int last = (nk < nz ? nk : nz) - 1;
    int32_t over = -span;
    for (int i = 0; i < last; i++)
        over += spans[i];
    int cells = 0;
    for (int i = 0; i < last; i++)
        cells |= NODE(kids[i])->kind == UIT_CELLS;
    if (over <= 0 || !cells)
        return 0;
    int32_t room[SPLIT_CELLS], all = 0;
    for (int i = 0; i < last; i++) {
        int32_t least = NODE(kids[i])->kind == UIT_CELLS ? cells_least(e, kids[i], model, row) : spans[i];
        room[i] = spans[i] > least ? spans[i] - least : 0;
        all += room[i];
    }
    if (!all)
        return over;
    int32_t take = over < all ? over : all, took = 0;
    for (int i = 0; i < last; i++) {
        int32_t give = (int32_t)((int64_t)room[i] * take / all);
        spans[i] -= give, took += give;
    }
    for (int i = 0; i < last && took < take; i++)      // what the shares rounded off
        if (room[i] > 0)
            spans[i]--, took++;
    return over - took;
}

static void fill_token(const moy_ui_sink_t *s, int32_t x, int32_t y, int32_t w, int32_t h, int token);
static void rule_in(moy_ui_ctx_t *c, const moy_ui_sink_t *s, int32_t x, int32_t y, int32_t w, int32_t h);
static void put_rect(uit_t *e, int k, const int32_t r[4]);

// A canvas's h=: its number, or its int template's value.
static int32_t canvas_h(uit_t *e, int k)
{
    const uit_node_t *N = NODE(k);
    return N->t_aux >= 0 ? int_of(e, N->t_aux, -1, -1, 0) : N->btn;
}

static int flow_shown(uit_t *e, int g, int model, int row);
static int32_t flow_h(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int g, int model, int row,
                      int32_t x, int32_t y, int32_t w);
static void flow_draw(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int g, int model, int row,
                      const int32_t r[4]);
static void put_cell(uit_t *e, int k, int model, int row, const int32_t r[4]);

// Whether split `k` stands among a flowing page's rows: in a group or a scroll, or beside a shown
// row that is no region in its page, its case or its split's cell (a tools row lent to a site
// draws elsewhere, so it is none). A split alone there (or a
// split's or a grid's cell) lays that room out in cells.
static int split_flows(uit_t *e, int k)
{
    if (e->placed || e->in_pop)
        return 0;
    int p = NODE(k)->parent;
    if (p == (int)UIT_NONE)
        return 0;
    int pk = NODE(p)->kind, cell = pk == UIT_GROUP && NODE(p)->parent != UIT_NONE &&
                                   NODE(NODE(p)->parent)->kind == UIT_SPLIT;
    if ((pk == UIT_GROUP && !cell) || pk == UIT_SCROLL)
        return 1;
    if (pk != UIT_PAGE && pk != UIT_CASE && !cell)
        return 0;
    KIDS(p, g) {
        int gk = NODE(g)->kind;
        if (g != k && gk != UIT_POPOVER && gk != UIT_DIALOG && gk != UIT_FOOT && gk != UIT_TOAST &&
            gk != UIT_SPLIT && gk != UIT_GRID && !(gk == UIT_TOOLS && (NODE(g)->lit & TL_LEND)) &&
            uit_shown(e, g, -1, -1))
            return 1;
    }
    return 0;
}

// A split among a flowing page's rows: at the flow's place, its cells across it at their sizes
// (a column split's down it), each a column as tall as it needs, the split as tall as its tallest
// cell (their sum); the rows after it under it.
static void flow_split(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    uint32_t dn, da = uit_tmpl_render(e, N->t_value, model, row, &dn);
    int across = dn == 3 && !memcmp(e->scratch.p + da, "row", 3);
    int pad = gap_px(e, N->btn), gap = gap_px(e, N->nbtn), nz, kids[SPLIT_CELLS], nk = 0;
    int32_t out[5], spans[SPLIT_CELLS], hs[SPLIT_CELLS], h = 0;
    moy_ui_api_measure(c, s, MOY_UI_MEASURE_PROGRESS, span_of("", 0), NULL, out);
    int32_t x = out[0] + pad, y = out[1] + pad, room = out[2] - 2 * pad;
    int32_t step_gap = out[4] - out[3] > 0 ? out[4] - out[3] : 0;
    KIDS(k, g)
    if (nk < SPLIT_CELLS && flow_shown(e, g, model, row))
        kids[nk++] = g;
    int32_t span = split_spans(e, N, model, row, room, gap, 1, SPLIT_CELLS, spans, &nz);
    for (int i = 0, at = 0; i < nk; i++) {
        int32_t w = !across ? room : i < nz && i < nk - 1 ? spans[i] : span - at;
        if (across && i >= nz)
            w = 0;
        hs[i] = w > 0 ? flow_h(e, c, s, kids[i], model, row, x + (across ? at : 0), y, w) : 0;
        if (across) {
            h = hs[i] > h ? hs[i] : h;
            at += w + gap;
        } else {
            h += hs[i] + (i ? gap : 0);
        }
    }
    int grouped = moy_ui_api_group_row(c, s, h + 2 * pad);
    for (int i = 0, at = 0; i < nk; i++) {
        int32_t w = !across ? room : i < nz && i < nk - 1 ? spans[i] : span - at;
        if (across && (i >= nz || w <= 0))
            continue;
        if (i && (N->lit & SP_RULE)) {
            if (across)
                fill_token(s, x + at - gap + gap / 2, y, 1, h, MOY_UI_T_BORDER);
            else
                fill_token(s, x, y + at - gap + gap / 2, room, 1, MOY_UI_T_BORDER);
        }
        int32_t cell[4] = {across ? x + at : x, across ? y : y + at, w, across ? h : hs[i]};
        flow_draw(e, c, s, kids[i], model, row, cell);
        at += (across ? w : hs[i]) + gap;
    }
    if (!grouped && !e->in_flow)
        moy_ui_api_space(c, h + 2 * pad + step_gap);
}

static void draw_split(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    if (e->in_pop) {
        pop_split(e, c, s, k, model, row);
        return;
    }
    if (split_flows(e, k)) {
        flow_split(e, c, s, k, model, row);
        return;
    }
    uint32_t dn, da = uit_tmpl_render(e, N->t_value, model, row, &dn);
    int across = dn == 3 && !memcmp(e->scratch.p + da, "row", 3);
    int pad = gap_px(e, N->btn), gap = gap_px(e, N->nbtn), nz;
    int32_t r[4], spans[SPLIT_CELLS];
    moy_ui_inset32(e->rect, pad, pad, r);
    int32_t span = split_spans(e, N, model, row, across ? r[2] : r[3], gap, across, SPLIT_CELLS, spans, &nz);
    int kids[SPLIT_CELLS], nk = 0;
    KIDS(k, g)
    if (nk < SPLIT_CELLS && uit_shown(e, g, model, row))
        kids[nk++] = g;
    int32_t over = 0;
    if (across)
        fit_spans(e, c, s, kids, nk, model, row, spans, nz, r[3]);
    else
        fit_heights(e, kids, nk, model, row, spans, nz), over = fit_room(e, kids, nk, spans, nz, span, model, row);
    // a column its palettes could not fit: its cells at their spans in a region that scrolls, its
    // last cell none, what they place ending at its view
    int cut = 0;
    char rid[UIT_ID_MAX + 1];
    if (over > 0) {
        snprintf(rid, sizeof rid, "split %s", uit_str(e, N->key));
        moy_ui_api_at(c, r[0], r[1], r[2], r[3]);
        moy_ui_api_scroll(c, s, span_of(rid, strlen(rid)), NULL);
        cut = moy_ui_api_cut(c, 1);
    }
    int32_t at = 0;
    for (int i = 0; i < nk && i < nz; i++) {
        int g = kids[i];
        int32_t sz = i < nk - 1 ? spans[i] : span - at, y = r[1] + at;
        if (over > 0) {
            int32_t m[5];
            sz = i < nk - 1 ? spans[i] : 0;
            c->has_at = 0;
            moy_ui_api_measure(c, s, MOY_UI_MEASURE_PROGRESS, span_of("", 0), NULL, m);
            y = m[1];
        }
        if (i && (N->lit & SP_RULE)) {
            int32_t mid = at - gap + gap / 2;
            if (across)
                fill_token(s, r[0] + mid, r[1], 1, r[3], MOY_UI_T_BORDER);
            else
                rule_in(c, s, r[0], y - gap + gap / 2, r[2], 1);
        }
        int32_t cell[4] = {across ? r[0] + at : r[0], across ? r[1] : y, across ? sz : r[2],
                           across ? r[3] : sz};
        at += sz + gap;
        if (over > 0)
            moy_ui_api_space(c, sz + gap);
        if (NODE(g)->kind == UIT_CANVAS && (NODE(g)->lit & CV_KEYS)) {
            moy_ui_api_at(c, cell[0], cell[1], cell[2], cell[3]);  // a stop: drawn placed in its cell
            draw(e, c, s, g, model, row);
            moy_ui_api_at(c, e->rect[0], e->rect[1], e->rect[2], e->rect[3]);
            continue;
        }
        if (NODE(g)->kind == UIT_CANVAS) {
            put_rect(e, g, cell);       // where a press on it lands (`uit_rect`)
            canvas_drew(e, g);
            if (e->draw_fn)             // a cell of its own that only draws: drawn into the cell
                canvas_draw(e, g, model, row, cell[0], cell[1], cell[2], cell[3]);
            continue;
        }
        if (NODE(g)->kind == UIT_GRID || NODE(g)->kind == UIT_SPLIT) {     // a grid's or a split's room is its cell
            int32_t was[4];
            memcpy(was, e->rect, sizeof was);
            memcpy(e->rect, cell, sizeof cell);
            draw(e, c, s, g, model, row);
            memcpy(e->rect, was, sizeof was);
            continue;
        }
        if (NODE(g)->kind != UIT_GROUP) {   // any other node drawn placed in its cell
            moy_ui_api_at(c, cell[0], cell[1], cell[2], cell[3]);
            draw(e, c, s, g, model, row);
            moy_ui_api_at(c, e->rect[0], e->rect[1], e->rect[2], e->rect[3]);
            continue;
        }
        char sid[UIT_ID_MAX + 1];
        snprintf(sid, sizeof sid, "split %s %d", uit_str(e, N->key), i);
        if (NODE(g)->lit == 1) {        // look="card": its card's plate behind the cell
            moy_ui_api_at(c, cell[0], cell[1], cell[2], cell[3]);
            moy_ui_api_card_at(c, s);
        }
        moy_ui_api_at(c, cell[0], cell[1], cell[2], cell[3]);
        int32_t cg = (e->flags & UIT_F_GEN) && gen_ok(e) ? uit_cell_gen(e, g) : -1;
        moy_ui_over_t go;           // the region carries a gen of its own, as a cards list's does
        moy_ui_over_none(&go);
        if (cg >= 0)
            moy_ui_over_put(&go, MOY_UI_OV_GEN, &cg);
        moy_ui_api_scroll(c, s, span_of(sid, strlen(sid)), cg >= 0 ? &go : NULL);
        uint8_t was = e->in_cell;
        int32_t room[4];
        memcpy(room, e->rect, sizeof room);
        memcpy(e->rect, cell, sizeof cell);     // a split in it is laid out in its cell
        e->in_cell = 1;
        if (across && (N->lit & SP_ALIGN) == 1) {
            int used = col_h(e, c, s, g, model, row);
            if (used >= 0)
                moy_ui_api_space(c, (cell[3] - used) / 2);
        }
        walk(e, c, s, g, model, row);
        e->in_cell = was;
        memcpy(e->rect, room, sizeof room);
        moy_ui_api_end(c, s);
        moy_ui_api_scroll(c, s, span_of("", 0), NULL);
        moy_ui_api_at(c, e->rect[0], e->rect[1], e->rect[2], e->rect[3]);
    }
    if (over > 0) {
        moy_ui_api_cut(c, cut);
        c->has_at = 0;
        moy_ui_api_end(c, s);
        moy_ui_api_scroll(c, s, span_of("", 0), NULL);
        moy_ui_api_at(c, e->rect[0], e->rect[1], e->rect[2], e->rect[3]);
    }
}

// A grid (`_r_grid`): its room (the page's, or its cell of a split) in by its pad, cut into rows
// then cols with its gap between; each child takes the next cell (a button's span= cells along
// its row), drawn placed there where it is shown: a hidden one leaves its cells empty, so no key
// moves.
static void put_rect(uit_t *e, int k, const int32_t r[4]);

static void draw_grid(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    int cols = N->lit & 15, rows = N->lit >> 4;
    int pad = gap_px(e, N->btn), gap = gap_px(e, N->nbtn);
    int32_t r[4], down[16][4], across[16][4];
    moy_ui_inset32(e->rect, pad, pad, r);
    if (r[2] < 0)
        r[2] = 0;
    if (r[3] < 0)
        r[3] = 0;
    moy_ui_split(r, rows, gap, 0, down, 16);
    int i = 0;
    KIDS(k, g) {
        const uit_node_t *G = NODE(g);
        int span = G->kind == UIT_BUTTON && G->nbtn ? G->nbtn : 1;
        int r0 = i / cols, c0 = i % cols;
        i += span;
        if (r0 >= rows)
            break;
        if (!uit_shown(e, g, model, row) ||
            (G->act >= 0 && !uit_act_can(e, G->act, model, row) && e->acts[G->act].off != 2))
            continue;
        moy_ui_split(down[r0], cols, gap, 1, across, 16);
        int c1 = c0 + span - 1 < cols ? c0 + span - 1 : cols - 1;
        int32_t cell[4] = {across[c0][0], across[c0][1], across[c1][0] + across[c1][2] - across[c0][0],
                           across[c0][3]};
        put_rect(e, g, cell);
        moy_ui_api_at(c, cell[0], cell[1], cell[2], cell[3]);
        draw(e, c, s, g, model, row);
    }
}

// A menu: its items in order, a `rows` among them an item per row of its model, each shown and
// its action on; an item's id is its text (its letter after a tab where the band shows keys).
typedef struct {
    int16_t node, model, row;
} item_t;

static int item_add(uit_buf_t *b, int k, int model, int row)
{
    item_t it = {(int16_t)k, (int16_t)model, (int16_t)row};
    return uit_buf_put(b, (const char *)&it, sizeof it) < 0 ? -1 : 0;
}

// A menu item's label as its menu draws it: its text, and its action's letter after a tab where
// the input shows keys (`keys`).
static void item_label(uit_t *e, int g, int model, int row, int keys, uit_buf_t *b)
{
    const uit_act_t *A = &e->acts[NODE(g)->act];
    uint32_t mark = e->scratch.n, ln, la = text(e, g, 0, model, row, &ln);
    uit_buf_printf(b, "%.*s", (int)ln, e->scratch.p + la);
    e->scratch.n = mark;
    const char *hot = uit_str(e, A->letters);
    if (hot[0] && keys)
        uit_buf_printf(b, "\t%c", hot[0] >= 'a' && hot[0] <= 'z' ? hot[0] - 32 : hot[0]);
}

static void draw_menu(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    uit_buf_t its = {0}, labels = {0}, icons = {0};
    KIDS(k, c2) {
        const uit_node_t *N = NODE(c2);
        if (N->kind == UIT_ROWS) {
            for (int r = 0, b; r < e->slots[N->slot].nrows; r++)
                if ((b = uit_row_body(e, c2, r)) >= 0)
                    KIDS(b, g) {
                    if (uit_shown(e, g, N->slot, r) && uit_act_can(e, NODE(g)->act, N->slot, r))
                        item_add(&its, g, N->slot, r);
                }
        } else if (uit_shown(e, c2, model, row) && uit_act_can(e, N->act, model, row)) {
            item_add(&its, c2, model, row);
        }
    }
    int n = (int)(its.n / (sizeof(item_t) + 1));
    static const char BACK[] = "back\0Back", BAR[] = "change\0Move\0confirm\0Open\0back\0Back";
    int keys = (e->flags & UIT_F_ON_BAR) ? moy_ui_api_hints_w(c, s, (const uint8_t *)BAR, sizeof BAR - 1) > 0
               : moy_ui_api_hints_w(c, s, (const uint8_t *)BACK, sizeof BACK - 1) > 0;
    int32_t danger = 0;
    for (int i = 0; i < n; i++) {
        item_t it;
        memcpy(&it, its.p + i * (sizeof(item_t) + 1), sizeof it);
        const uit_node_t *N = NODE(it.node);
        const uit_act_t *A = &e->acts[N->act];
        if (i)
            uit_buf_printf(&labels, "%c", 0), uit_buf_printf(&icons, "%c", 0);
        item_label(e, it.node, it.model, it.row, keys, &labels);
        if (N->t_icon >= 0) {
            uint32_t in, ia = uit_tmpl_render(e, N->t_icon, it.model, it.row, &in);
            uit_buf_printf(&icons, "%.*s", (int)in, e->scratch.p + ia);
        } else {
            uit_buf_printf(&icons, "%s", uit_str(e, A->icon));
        }
        if (N->lit && i < 32)
            danger |= (int32_t)1 << i;
    }
    e->menu_keys = (uint8_t)keys;
    if (danger)
        moy_ui_api_menu_danger(c, danger);
    uint32_t cn, ca = text(e, k, 0, model, row, &cn);
    int got = moy_ui_api_menu(c, s, sspan(e, ca, cn), (const uint8_t *)(labels.p ? labels.p : ""), labels.n,
                              (const uint8_t *)(icons.p ? icons.p : ""), icons.n, NULL);
    // each item's id: its text, cut to what the toolkit keeps
    const char *l = labels.p;
    for (int i = 0; i < n; i++) {
        item_t it;
        memcpy(&it, its.p + i * (sizeof(item_t) + 1), sizeof it);
        char id[UIT_ID_MAX + 1];
        snprintf(id, sizeof id, "%s", l);
        id_put(e, it.node, it.model, it.row, id);
        l += strlen(l) + 1;
        if (i == got && uit_act_can(e, NODE(it.node)->act, it.model, it.row))
            fire(e, NODE(it.node)->act, it.node, it.model, it.row, NULL);
    }
    uit_buf_free(&its), uit_buf_free(&labels), uit_buf_free(&icons);
}

// A rect filled in theme token `token` (the reference's `cv.rect(..., th[ROLE])`).
static void fill_token(const moy_ui_sink_t *s, int32_t x, int32_t y, int32_t w, int32_t h, int token)
{
    moy_ui_box_t b = {(int16_t)x, (int16_t)y, (int16_t)w, (int16_t)h}, none = {0, 0, 0, 0};
    moy_ui_fill_uncovered(s, b, none, moy_ui_token(s->look, token));
}

// An enum's tab strip across the page's top (`_r_tabs`): a band cut from its room.
// An enum's tabs in `band`: a tap or left and right while focused write the value.
static void tabs_in(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, const int32_t band[4])
{
    const uit_node_t *N = NODE(k);
    moy_ui_api_at(c, band[0], band[1], band[2], band[3]);
    int count, at;
    uint32_t len, items = seg_items(e, N, &len, &count, &at);
    moy_ui_over_t o;
    char id[UIT_ID_MAX + 1];
    over_for(e, k, -1, -1, c, &o, id);
    if (N->t_aux >= 0) {
        int32_t zero = 0;
        moy_ui_over_put(&o, MOY_UI_OV_MARK, &zero);     // tabs the band names: no stop, so no mark
        e->page_tabs_now = (int16_t)k;
    }
    int got = moy_ui_api_choice(c, s, 9, span_of("", 0), (const uint8_t *)e->scratch.p + items, len, at, &o);
    if (got >= 0 && got < count && got != at) {
        const char *v = seg_key(e, N, got);
        wrote_text(e, k, v, strlen(v), "from", N->on);
    }
}

// A flow page's tabs: a band cut from the page's top.
static void draw_tabs(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k)
{
    int desk = (e->flags & UIT_F_DESK) != 0, mn;
    int bh = moy_ui_metrics(MOY_UI_K_VALUE_ROW, &mn)[desk ? 17 : 16] * e->fs, pad = desk ? 8 : 0;
    int32_t band[4], rest[4];
    moy_ui_cut(e->rect, MOY_UI_CUT_TOP, bh + 2 * pad, band, rest);
    memcpy(e->rect, rest, sizeof rest);
    if (pad)
        moy_ui_inset32(band, 2 * pad, pad, band);
    tabs_in(e, c, s, k, band);
    moy_ui_api_space(c, bh + 2 * pad);  // a flowing page's rows start under them
    // what follows them takes the rest, over a flowing page's hints band
    int32_t h = e->rect[3] > e->band_h ? e->rect[3] - e->band_h : 0;
    moy_ui_api_at(c, e->rect[0], e->rect[1], e->rect[2], h);
}

static int32_t row_unit(const uit_t *e);

// A table (`_r_table`): its columns' headers and its rows' cells, one stop
// whose current row follows focus and cur=.
static void draw_table(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k)
{
    const uit_node_t *N = NODE(k);
    int m = N->slot;
    uit_after_removal(e, k);
    const uit_slot_t *M = &e->slots[m];
    int at = 0;
    if (N->cur >= 0) {
        const uit_slot_t *C = &e->slots[N->cur];
        int r = uit_row_find(e, m, C->s ? C->s : "", C->sn);
        if (r >= 0)
            at = r;
    }
    const char *key = uit_str(e, N->key);
    int cv = -1;                        // a canvas child: it draws each row (a table of parts)
    KIDS(k, g0)
    if (NODE(g0)->kind == UIT_CANVAS) {
        cv = g0;
        break;
    }
    moy_ui_api_at(c, e->rect[0], e->rect[1], e->rect[2], e->rect[3]);
    id_put(e, k, m, M->nrows ? at : -1, key);
    if (!M->nrows) {
        uint32_t n = 0, a = N->t_aux >= 0 ? uit_tmpl_render(e, N->t_aux, -1, -1, &n) : 0;
        moy_ui_api_label(c, s, n ? sspan(e, a, n) : span_of("", 0), NULL);
        return;
    }
    // its cells made again only where the build, its model or a state its columns read moved
    uit_buf_t *B = &e->cells;
    int engine = 0;
    uint32_t ckey = (uint32_t)e->gen * 65537u + (uint32_t)M->ver * 257u + (uint32_t)M->nrows;
    KIDS(k, g0)
    if (NODE(g0)->kind == UIT_COL)
        ckey += uit_tmpl_key(e, NODE(g0)->t_main, &engine);
    int ncol = 0;
    uint32_t cols_n = 0;
    for (int p = N->props; p != (int)UIT_NONE; p = e->props[p].next)
        if (!strcmp(uit_str(e, e->props[p].name), "cols")) {
            cols_n += (uint32_t)strlen(uit_str(e, e->props[p].src)) + 1;
            ncol++;
        }
    if (engine || e->cells_node != k + 1 || e->cells_key != ckey || B->n < cols_n) {
        B->n = 0;
        for (int p = N->props; p != (int)UIT_NONE; p = e->props[p].next)
            if (!strcmp(uit_str(e, e->props[p].name), "cols"))
                uit_buf_puts(B, uit_str(e, e->props[p].src));
        uint32_t mark = e->scratch.n;
        for (int r = 0; r < M->nrows && cv >= 0; r++) {
            // a row's cell, which a frame that carries rows compares: its fields, 0x1f between
            uint32_t at0 = B->n;
            for (int f = 0; f < M->nf; f++) {
                const char *v = uit_cell(e, m, r, f);
                if (B->n > at0)
                    B->p[B->n - 1] = 0x1f;  // the field before ends at the separator, not its NUL
                uit_buf_put(B, v, strlen(v));
            }
            if (B->n == at0)
                uit_buf_put(B, "", 0);
        }
        for (int r = 0; r < M->nrows && cv < 0; r++) {
            int i = 0;
            KIDS(k, g) {
                if (NODE(g)->kind != UIT_COL || i >= ncol)
                    continue;
                uint32_t n = 0, a = NODE(g)->t_main >= 0 ? uit_tmpl_render(e, NODE(g)->t_main, m, r, &n) : 0;
                uit_buf_put(B, e->scratch.p + a, n);
                e->scratch.n = mark;
                i++;
            }
            for (; i < ncol; i++)
                uit_buf_put(B, "", 0);
        }
        e->cells_node = (int16_t)(k + 1);
        e->cells_key = ckey;
    }
    moy_ui_over_t o;
    moy_ui_over_none(&o);
    moy_ui_over_text(&o, MOY_UI_OV_ID, span_of(key, strlen(key)));
    if (cv >= 0) {
        int32_t rh = N->btn ? (int32_t)N->btn * row_unit(e) : len_of(e, uit_tmpl_prop(e, k, "row"), -1, -1, row_unit(e));
        int32_t part[2] = {0, rh > 0 ? rh : 1}, one = 1;
        moy_ui_over_put(&o, MOY_UI_OV_PART, part);
        moy_ui_over_put(&o, MOY_UI_OV_BAR, &one);
    }
    int32_t out[2] = {at, 0};
    moy_ui_api_table(c, s, span_of("", 0), (const uint8_t *)B->p, cols_n, (const uint8_t *)B->p + cols_n,
                     B->n - cols_n, at, &o, out);
    if (cv >= 0) {
        int32_t pr[8];
        int32_t i;
        canvas_drew(e, cv);             // its rows are a canvas's: the next frame carries no gen but by reads=
        for (i = c->tp.id ? c->tp.i : 0; c->tp.id && i < c->tp.e && i < M->nrows; i++) {
            // each row in view where a press on it lands (`uit_rect`'s ROWKEY/KEY), drawn this
            // frame or not
            int32_t x1 = c->tp.x1, cell[4] = {x1 ? c->tp.x0 + i * c->tp.rh : c->tp.x,
                                              x1 ? c->tp.y0 : c->tp.y0 + i * c->tp.rh,
                                              x1 ? c->tp.rh : c->tp.w, x1 ? c->tp.w : c->tp.rh};
            put_cell(e, cv, m, i, cell);
        }
        while ((i = moy_ui_api_table_part(c, s, pr)) >= 0)
            if (e->draw_fn && i < M->nrows) {
                memcpy(e->draw_clip, pr + 4, sizeof e->draw_clip);     // what of the row the view shows
                e->draw_clip_on = 1;
                canvas_draw(e, cv, m, i, pr[0], pr[1], pr[2], pr[3]);
                e->draw_clip_on = 0;
            }
    }
    int got = out[0];
    if (got < 0 || got >= M->nrows)
        return;
    const char *gk = uit_cell(e, m, got, M->key);
    size_t gn = strlen(gk);
    if (N->cur >= 0) {
        const uit_slot_t *C = &e->slots[N->cur];
        if (gn != C->sn || memcmp(gk, C->s ? C->s : "", gn))
            uit_cur_moved(e, k, gk, gn, "table", got != at);
    }
    id_put(e, k, m, got, key);
    if (out[1] && N->on >= 0)
        fire(e, N->on, k, m, got, NULL);
}

// A shared foot's label (`_foot_label`): its first shown label with a text, else -1.
static int foot_label(uit_t *e, int k)
{
    if (!NODE(k)->lit)
        return -1;
    KIDS(k, g) {
        if (NODE(g)->kind != UIT_LABEL || NODE(g)->t_main < 0 || !uit_shown(e, g, -1, -1))
            continue;
        uint32_t n, mark = e->scratch.n;
        uit_tmpl_render(e, NODE(g)->t_main, -1, -1, &n);
        e->scratch.n = mark;
        if (n)
            return g;
    }
    return -1;
}

static int32_t fixed_h(uit_t *e, int k);
static int placed_shown(uit_t *e, int k, int model, int row);
static void stack(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                  const int32_t r[4]);

// A foot of the end look holding more than labels and buttons (a row, a field, a note): its
// children stacked by the placed rule, its height theirs.
static int32_t foot_stacked(uit_t *e, int k)
{
    int32_t h = 0, any = 0;
    if (NODE(k)->lit == 1)
        return 0;
    KIDS(k, g) {
        any |= NODE(g)->kind != UIT_LABEL && NODE(g)->kind != UIT_BUTTON;
        if (placed_shown(e, g, -1, -1))
            h += fixed_h(e, g);
    }
    return any ? h : 0;
}

// The foot's line over its buttons (`_foot_line`): its label's line, else 0.
static int foot_line(uit_t *e, int k)
{
    if (foot_label(e, k) < 0)
        return 0;
    moy_font_info_t fi;
    int line = moy_font_info(moy_text_print_font(), &fi) ? fi.line : 8;
    return line + ((e->flags & UIT_F_DESK) ? 8 : 4 * e->fs);
}

// The page's shown foot (`_foot_of`): at its root, or in the shown case of a switch there.
static int foot_of(uit_t *e)
{
    KIDS(0, k) {
        if (!uit_shown(e, k, -1, -1))
            continue;
        if (NODE(k)->kind == UIT_FOOT)
            return k;
        if (NODE(k)->kind == UIT_SWITCH) {
            int cs = uit_case_of(e, k);
            if (cs < 0)
                continue;
            KIDS(cs, g)
            if (NODE(g)->kind == UIT_FOOT && uit_shown(e, g, -1, -1))
                return g;
        }
    }
    return -1;
}

static void draw(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row);
static int32_t empty_controls_h(uit_t *e, int k, int model, int row);
static void empty_controls(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                           int32_t x, int32_t w, int32_t y);
static int32_t natural(uit_t *e, int k, int model, int row, int32_t h);
static int32_t bar_item_w(uit_t *e, int k, int model, int row, int32_t h);
static int32_t row_gap(const uit_t *e);

// A button's kind, the toolkit's: its literal's, or its template's word this frame (normal,
// primary, tonal, danger; another word normal).
static int button_kind(uit_t *e, int k, int model, int row)
{
    static const char *const KINDS[] = {"normal", "primary", "tonal", "danger"};
    if (NODE(k)->lit)
        return NODE(k)->lit;
    uint32_t n, mark = e->scratch.n, at = prop_text(e, k, "kind", model, row, &n);
    int kind = 0;
    for (int i = 1; i < 4 && n; i++)
        if (n == strlen(KINDS[i]) && !memcmp(e->scratch.p + at, KINDS[i], n))
            kind = i;
    e->scratch.n = mark;
    return kind;
}

// Whether button `k` shows an icon: its icon= rendered, else its action's.
static int btn_icon(uit_t *e, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    if (N->t_icon < 0)
        return N->act >= 0 && uit_str(e, e->acts[N->act].icon)[0];
    uint32_t ni, mark = e->scratch.n;
    uit_tmpl_render(e, N->t_icon, model, row, &ni);
    e->scratch.n = mark;
    return ni != 0;
}

// Cells `w` of a row `used` wide in `room`: where they do not fit, a labelled button with an
// icon, from the end, stands as its icon alone until they do (the toolkit drops a label that keeps
// no character beside its icon); a row from a model's cells are `fit_cells`' to cut. `km`, `kr`
// each cell's model and row, NULL for `model`, `row`. Answers the width they take then.
#define ALONE_W(e) (((e)->flags & UIT_F_DESK) ? 36 : 26 * (e)->fs)
static int32_t icons_alone(uit_t *e, const int16_t *kids, const int16_t *km, const int16_t *kr, int model,
                        int row, int32_t *w, int n, int32_t used, int32_t room)
{
    int32_t a = ALONE_W(e);
    for (int i = n - 1; i >= 0 && used > room; i--) {
        const uit_node_t *G = NODE(kids[i]);
        if (G->kind == UIT_BUTTON && !(G->btn & (BT_ALONE | BT_GROW)) && w[i] > a && !(km && km[i] != model)
            && btn_icon(e, kids[i], km ? km[i] : model, kr ? kr[i] : row))
            used -= w[i] - a, w[i] = a;
    }
    return used;
}

// A button's natural width: its label's with the toolkit's pads (its minimum taken), and its
// icon's room where it has one beside its label.
static int32_t button_w(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    uint32_t n, mark = e->scratch.n, a = text(e, k, 0, model, row, &n);
    int icon = btn_icon(e, k, model, row);
    int32_t out[5];
    moy_ui_api_measure(c, s, MOY_UI_MEASURE_BUTTON, sspan(e, a, n), NULL, out);
    e->scratch.n = mark;
    int desk = (e->flags & UIT_F_DESK) != 0;
    if (icon && (N->btn & BT_ALONE))    // a bar item's (flat, no plate) the narrower
        return desk ? (N->lit == 5 ? 28 : 36) : 26 * e->fs;
    int32_t w = out[2] + (icon ? (desk ? 20 : 14 * e->fs) : 0);
    if (N->btn & BT_HERO) {
        // look="hero": twice the pads, a least width half again the toolkit's
        int32_t least = desk ? 112 : 84 * e->fs;
        w += desk ? 32 : 24 * e->fs;
        w = w > least ? w : least;
    }
    return w;
}

// A button's height on a flowing page: the toolkit's, half again for look="hero".
static int32_t button_h(uit_t *e, int k, int32_t h)
{
    return (NODE(k)->btn & BT_HERO) ? h * 3 / 2 : h;
}

// An empty's line onto `b`, broken at word breaks into lines of its column (the width `w` it
// is drawn in, a page or a cell, less its margins, at most 420 on the desk), NUL-separated.
static void empty_line(uit_t *e, const moy_ui_sink_t *s, uit_buf_t *b, const char *p, uint32_t n,
                       int32_t w)
{
    int32_t room = w - 32 * e->fs;
    if ((e->flags & UIT_F_DESK) && room > 420)
        room = 420;
    uint32_t start = 0, brk = 0;
    for (uint32_t i = 0; i <= n; i++) {
        if (i < n && p[i] != ' ')
            continue;
        if (brk > start && moy_ui_role_w(s, MOY_UI_FONT_CAPTION, span_of(p + start, i - start)) > room) {
            uit_buf_printf(b, "%.*s", (int)(brk - start), p + start);
            uit_buf_printf(b, "%c", 0);
            start = brk + 1;
        }
        brk = i;
    }
    uit_buf_printf(b, "%.*s", (int)(n - start), p + start);
}

// The page's docked foot (`ui.dock`, on the page's ground), look="share"
// (`_r_foot`): its buttons share its width, its label a line of its own over
// them; on a handheld under a rule. A stacked foot's children lead in as
// the keys band's hints do.
static int flow_shown(uit_t *e, int g, int model, int row);

static void draw_foot(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    int desk = (e->flags & UIT_F_DESK) != 0, fs = e->fs;
    int32_t x = e->foot_r[0], y = e->foot_r[1], w = e->foot_r[2], h = e->foot_r[3];
    int fh = desk ? 30 : 20 * fs, pad = desk ? 7 : fs, m = desk ? 16 : 4 * fs;
    int by = y + h - fh - pad;
    if (NODE(k)->lit == 2) {            // a band: its rows edge to edge on the alternate surface
        int32_t r[4] = {x, y, w, h};
        fill_token(s, x, y, w, h, MOY_UI_T_SURFACE_ALT);
        fill_token(s, x, y, w, fs, MOY_UI_T_BORDER);
        e->in_foot = 1;
        stack(e, c, s, k, model, row, r);
        e->in_foot = 0;
        return;
    }
    if (!desk)
        fill_token(s, x + m, y, w - 2 * m, 1, MOY_UI_T_BORDER);
    if (foot_stacked(e, k)) {
        int lead = desk ? m : MOY_UI_HINT_LEAD(0) * fs;
        int32_t r[4] = {x + lead, y + pad, w - 2 * lead, h - 2 * pad};
        e->in_foot = 1;
        stack(e, c, s, k, model, row, r);
        e->in_foot = 0;
        return;
    }
    int16_t btn[16];
    int nb = 0;
    KIDS(k, g) {
        const uit_node_t *G = NODE(g);
        if (G->kind == UIT_BUTTON && nb < 16 && flow_shown(e, g, model, row))
            btn[nb++] = (int16_t)g;     // a grey one too: it stays, dimmed
    }
    if (!NODE(k)->lit) {
        // the end look: its buttons at their natural widths at its end, its labels before them;
        // on the desk under a rule where it holds buttons
        int gap = desk ? 8 : 4 * fs;
        int32_t bw[16], bx = x + w - m;
        for (int i = 0; i < nb; i++) {
            bw[i] = button_w(e, c, s, btn[i], model, row);
            bx -= bw[i] + (i ? gap : 0);
        }
        if (nb && desk)
            fill_token(s, x + m, y, w - 2 * m, 1, MOY_UI_T_BORDER);
        int32_t lw = bx - (nb ? gap : 0) - x - 26;
        KIDS(k, g)
        if (NODE(g)->kind == UIT_LABEL && uit_shown(e, g, model, row)) {
            moy_ui_api_at(c, x + 26, by, lw > 0 ? lw : 0, fh);
            label_rows(e, c, s, g, model, row, NULL);
        }
        for (int i = 0; i < nb; i++) {
            moy_ui_api_at(c, bx, by, bw[i], fh);
            draw(e, c, s, btn[i], model, row);
            bx += bw[i] + gap;
        }
        return;
    }
    int lab = foot_label(e, k);
    if (lab >= 0) {
        moy_ui_api_at(c, x + m, y + pad, w - 2 * m, by - y - pad);
        label_rows(e, c, s, lab, model, row, NULL);
    }
    if (!nb)
        return;
    int32_t r[4] = {x + m, by, w - 2 * m, fh}, cells[16][4];
    if (nb == 1)
        memcpy(cells[0], r, sizeof r);
    else
        moy_ui_split(r, nb, desk ? 8 : 4 * fs, 1, cells, 16);
    for (int i = 0; i < nb; i++) {
        moy_ui_api_at(c, cells[i][0], cells[i][1], cells[i][2], cells[i][3]);
        draw(e, c, s, btn[i], model, row);
    }
}

// -- a row of the page's flow ---------------------------------------------------------------
//
// A `ui.row` on a page the toolkit stacks (not a placed one): its children side by side on one
// row of the stack, as tall as its tallest. A button takes its natural width (unless grow=), a
// picture its side and its margin, a rule a line down the row between its neighbours, a label
// after the row's filler its text's width; the filler
// (a grow= button, else the first other child) takes the width left. A row whose children all
// take their own widths centres them; pad= sets it in from either side. A group in it is a
// column, its children one under the next from its cell's top (a button its natural width);
// every other child is centred down the row.

enum { FLOW_KIDS = 16 };
static int32_t h_row(const uit_t *e);
static int32_t len_of(uit_t *e, int t, int model, int row, int32_t dflt);

static int32_t pic_side(uit_t *e, int k, int model, int row)
{
    return size_of(e, int_of(e, NODE(k)->t_value, model, row, 64));
}

static int32_t pic_margin(uit_t *e)
{
    return ((e->flags & UIT_F_DESK) ? 16 : 8) * e->fs;
}

static int flow_shown(uit_t *e, int g, int model, int row)
{
    const uit_node_t *G = NODE(g);
    return uit_shown(e, g, model, row) && G->kind != UIT_DIALOG && G->kind != UIT_POPOVER &&
           (G->act < 0 || uit_act_can(e, G->act, model, row) || e->acts[G->act].off == 2);
}

static int32_t len_of(uit_t *e, int t, int model, int row, int32_t dflt);

// The gap between a column's children: its group's gap=, else a small one.
static int32_t col_gap(uit_t *e, int k, int model, int row)
{
    return space_of(e, NODE(k)->t_value, model, row, 2);
}

static int32_t flow_h(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int g, int model, int row,
                      int32_t x, int32_t y, int32_t w);

// A column's height at width `w`: its children's, a small gap between them.
static int32_t col_h_at(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                        int32_t x, int32_t y, int32_t w)
{
    int32_t h = 0;
    int n = 0;
    KIDS(k, g)
    if (flow_shown(e, g, model, row))
        h += flow_h(e, c, s, g, model, row, x, y, w) + (n++ ? col_gap(e, k, model, row) : 0);
    return h;
}

static int32_t flow_row(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row, int dry);

// Child `g`'s height in a cell `w` wide at (x, y).
static int32_t flow_h(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int g, int model, int row,
                      int32_t x, int32_t y, int32_t w)
{
    const uit_node_t *G = NODE(g);
    int32_t out[5], h = 0;
    uint32_t n, mark = e->scratch.n, a;
    switch (G->kind) {
    case UIT_LABEL:
        moy_ui_api_at(c, x, y, w, 0x3fff);
        label_rows_m(e, c, s, g, model, row, &h, 3);
        return h;
    case UIT_STEPPER:                   // a bar item's height, as its chevrons are
        moy_ui_api_at(c, x, y, w, 0);
        moy_ui_api_measure(c, s, MOY_UI_MEASURE_BUTTON, span_of("", 0), NULL, out);
        return out[3] > 0 ? out[3] : ((e->flags & UIT_F_DESK) ? 30 : 20 * e->fs);
    case UIT_BUTTON:
        a = text(e, g, 0, model, row, &n);
        moy_ui_api_at(c, x, y, w, 0);
        moy_ui_api_measure(c, s, MOY_UI_MEASURE_BUTTON, sspan(e, a, n), NULL, out);
        e->scratch.n = mark;
        return button_h(e, g, out[3] > 0 ? out[3] : ((e->flags & UIT_F_DESK) ? 30 : 20 * e->fs));
    case UIT_PICTURE:
        return pic_side(e, g, model, row) + ((e->flags & UIT_F_DESK) ? 6 : 4 * e->fs);
    case UIT_PROGRESS:
        moy_ui_api_at(c, x, y, w, 0);
        moy_ui_api_measure(c, s, MOY_UI_MEASURE_PROGRESS, span_of("", 0), NULL, out);
        return out[3];
    case UIT_GROUP:
        return col_h_at(e, c, s, g, model, row, x, y, w);
    case UIT_ROW:                       // a row in a column: its cells' height in the cell
        moy_ui_api_at(c, x, y, w, 0);
        return flow_row(e, c, s, g, model, row, 1);
    case UIT_RULE:
        return 0;                       // a row's rule: as tall as the row it divides
    }
    return h_row(e);
}

static void flow_draw(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int g, int model, int row,
                      const int32_t r[4]);

// A column down `r`: each child its own height, a small gap between.
static void col_draw(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                     const int32_t r[4])
{
    int32_t y = r[1];
    KIDS(k, g) {
        if (!flow_shown(e, g, model, row))
            continue;
        int32_t h = flow_h(e, c, s, g, model, row, r[0], y, r[2]), cell[4] = {r[0], y, r[2], h};
        if (NODE(g)->kind == UIT_BUTTON && !(NODE(g)->btn & BT_GROW)) {
            int32_t bw = button_w(e, c, s, g, model, row);
            cell[2] = bw < r[2] ? bw : r[2];    // a button its natural width (a grow= one across)
        }
        flow_draw(e, c, s, g, model, row, cell);
        y += h + col_gap(e, k, model, row);
    }
}

// Child `g` drawn into its cell `r`.
static void flow_draw(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int g, int model, int row,
                      const int32_t r[4])
{
    int kind = NODE(g)->kind;
    if (kind == UIT_GROUP) {
        col_draw(e, c, s, g, model, row, r);
        return;
    }
    if (kind == UIT_PICTURE) {
        int32_t m = pic_margin(e);
        moy_ui_api_at(c, r[0] - m, r[1], r[2] + m, r[3]);
    } else {
        moy_ui_api_at(c, r[0], r[1], r[2], r[3]);
    }
    uint8_t was = e->in_flow;
    e->in_flow = 1;
    draw(e, c, s, g, model, row);
    e->in_flow = was;
}

// A child's natural width in a wrap= row: a button's, a picture's side and margin, a label's
// text and its inset either side (its measure's), a group's widest child; any other kind the row's whole width.
static int32_t wrap_w(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int g, int model, int row,
                      int32_t x, int32_t y, int32_t room)
{
    int32_t w = 0, lw;
    switch (NODE(g)->kind) {
    case UIT_BUTTON:
        return button_w(e, c, s, g, model, row);
    case UIT_PICTURE:
        return pic_side(e, g, model, row) + pic_margin(e);
    case UIT_LABEL:
        lw = 0;
        moy_ui_api_at(c, x, y, room, 0x3fff);
        label_rows_m(e, c, s, g, model, row, &lw, 2);
        return lw < room ? lw : room;
    case UIT_GROUP:
        KIDS(g, k)
        if (flow_shown(e, k, model, row) && (lw = wrap_w(e, c, s, k, model, row, x, y, room)) > w)
            w = lw;
        return w < room ? w : room;
    default:
        return room;
    }
}

// A wrap= row (`ui.row(wrap=True)`): its children at their natural widths from its start, gap=
// apart; a child that does not fit after another starts a line under them, the lines gap= apart.
static int32_t draw_wrap_row(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int model, int row,
                             const int16_t *kids, int n, int32_t x, int32_t y, int32_t room, int32_t gap,
                             int32_t step_gap, int dry)
{
    int32_t ws[FLOW_KIDS], hs[FLOW_KIDS], top = y;
    for (int i = 0; i < n; i++) {
        int32_t w = wrap_w(e, c, s, kids[i], model, row, x, y, room);
        ws[i] = w < room ? w : room;
    }
    for (int a = 0; a < n;) {
        int b = a + 1;
        int32_t used = ws[a];
        while (b < n && used + gap + ws[b] <= room)
            used += gap + ws[b++];
        int32_t rh = 0, cx = x;
        for (int i = a; i < b; i++) {
            int32_t px = NODE(kids[i])->kind == UIT_PICTURE ? pic_margin(e) : 0;
            hs[i] = flow_h(e, c, s, kids[i], model, row, cx + px, top, ws[i] - px);
            rh = hs[i] > rh ? hs[i] : rh;
            cx += ws[i] + gap;
        }
        cx = x;
        for (int i = a; i < b && !dry; i++) {
            int kind = NODE(kids[i])->kind;
            int32_t px = kind == UIT_PICTURE ? pic_margin(e) : 0;
            int32_t ty = kind == UIT_GROUP || kind == UIT_PICTURE ? top : top + (rh - hs[i]) / 2;
            int32_t cell[4] = {cx + px, ty, ws[i] - px, hs[i]};
            flow_draw(e, c, s, kids[i], model, row, cell);
            cx += ws[i] + gap;
        }
        top += rh + (b < n ? gap : 0);
        a = b;
    }
    if (!dry && !e->in_flow)
        moy_ui_api_space(c, top - y + step_gap);   // in a column's cell its column moves on
    return top - y + step_gap;
}

// A row's rule at (x, y, w, h), inside the view its cells end at (moy_ui_api_cut).
static void rule_in(moy_ui_ctx_t *c, const moy_ui_sink_t *s, int32_t x, int32_t y, int32_t w, int32_t h)
{
    if (c->cut_on) {
        int32_t y1 = y + h < c->cut.y + c->cut.h ? y + h : c->cut.y + c->cut.h;
        y = y > c->cut.y ? y : c->cut.y;
        h = y1 - y;
    }
    if (h > 0)
        fill_token(s, x, y, w, h, MOY_UI_T_BORDER);
}

// A row of a flowing page: its cells across, drawn, or with `dry` only measured. Answers the
// height it moves the page's rows down by, its gap under it taken.
static int32_t flow_row(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row, int dry)
{
    int16_t kids[FLOW_KIDS];
    int32_t ws[FLOW_KIDS], hs[FLOW_KIDS], out[5];
    int n = 0, fill = -1, desk = (e->flags & UIT_F_DESK) != 0;
    KIDS(k, g)
    if (n < FLOW_KIDS && flow_shown(e, g, model, row))
        kids[n++] = (int16_t)g;
    if (!n)
        return 0;
    moy_ui_api_measure(c, s, MOY_UI_MEASURE_PROGRESS, span_of("", 0), NULL, out);
    int32_t x = out[0], y = out[1], room = out[2], gap = space_of(e, NODE(k)->t_value, model, row, 6);
    int32_t step_gap = out[4] - out[3] > 0 ? out[4] - out[3] : 0, used = 0;
    int32_t pad = space_of(e, NODE(k)->t_aux, model, row, 0);   // pad=: in from either side
    x += pad, room -= 2 * pad;
    if (NODE(k)->lit & RW_WRAP) {
        int cut = dry ? 0 : moy_ui_api_cut(c, !e->placed && !e->in_foot);  // as below
        int32_t h = draw_wrap_row(e, c, s, model, row, kids, n, x, y, room, gap, step_gap, dry);
        if (!dry)
            moy_ui_api_cut(c, cut);
        return h;
    }
    for (int i = 0; i < n; i++) {
        const uit_node_t *G = NODE(kids[i]);
        if ((G->kind == UIT_BUTTON || G->kind == UIT_STEPPER) && (G->btn & BT_GROW))
            fill = i;
    }
    for (int i = 0; i < n && fill < 0; i++)
        if (NODE(kids[i])->kind != UIT_BUTTON && NODE(kids[i])->kind != UIT_PICTURE &&
            NODE(kids[i])->kind != UIT_RULE && NODE(kids[i])->kind != UIT_STEPPER)
            fill = i;
    for (int i = 0; i < n; i++) {
        int g = kids[i], kind = NODE(g)->kind;
        ws[i] = 0;
        if (i == fill)
            continue;
        if (kind == UIT_BUTTON) {
            ws[i] = button_w(e, c, s, g, model, row);
        } else if (kind == UIT_PICTURE) {
            ws[i] = pic_side(e, g, model, row) + pic_margin(e);
        } else if (kind == UIT_RULE) {
            ws[i] = desk ? 1 : e->fs;
        } else if (kind == UIT_STEPPER) {
            ws[i] = natural(e, g, model, row, h_row(e));
        } else if (kind == UIT_LABEL) {
            int32_t lw = 0;
            moy_ui_api_at(c, x, y, room, 0x3fff);
            label_rows_m(e, c, s, g, model, row, &lw, 2);
            ws[i] = lw;
        } else {
            ws[i] = room / n;
        }
        used += ws[i];
    }
    used += gap * (n - 1);
    if (used > room && n > 1) {         // wider than the room: the gaps close first
        int32_t g = gap - (used - room + n - 2) / (n - 1);
        g = g > 0 ? g : 0;
        used -= (gap - g) * (n - 1), gap = g;
    }
    used = icons_alone(e, kids, NULL, NULL, model, row, ws, n, used, room);
    int32_t at = x;
    if (fill >= 0)
        ws[fill] = room - used > 0 ? room - used : 0;
    else if (used < room)
        at = x + (room - used) / 2;
    int32_t rh = 0, cx = at;
    for (int i = 0; i < n; i++) {
        int32_t cw = ws[i], px = NODE(kids[i])->kind == UIT_PICTURE ? pic_margin(e) : 0;
        hs[i] = flow_h(e, c, s, kids[i], model, row, cx + px, y, cw - px);
        rh = hs[i] > rh ? hs[i] : rh;
        cx += cw + gap;
    }
    if (dry)
        return rh + step_gap;
    int grouped = moy_ui_api_group_row(c, s, rh);     // a row of an open group: its rule
    // its cells scroll with the page: what they place ends at its view, as a stacked row does
    int cut = moy_ui_api_cut(c, !e->placed && !e->in_foot);
    cx = at;
    for (int i = 0; i < n; i++) {
        int kind = NODE(kids[i])->kind;
        int32_t px = kind == UIT_PICTURE ? pic_margin(e) : 0;
        int32_t top = kind == UIT_GROUP || kind == UIT_PICTURE ? y : y + (rh - hs[i]) / 2;
        int32_t cell[4] = {cx + px, top, ws[i] - px, hs[i]};
        if (kind == UIT_RULE)
            rule_in(c, s, cx, y, ws[i], rh);     // a rule between its neighbours
        else
            flow_draw(e, c, s, kids[i], model, row, cell);
        cx += ws[i] + gap;
    }
    moy_ui_api_cut(c, cut);
    if (!grouped && !e->in_flow)
        moy_ui_api_space(c, rh + step_gap);
    return rh + step_gap;
}

// What the nodes after `k` on a flowing page move its rows down by, measured: -1 where one is a
// kind with no measure here (a row, a label and a button have one).
static int32_t flow_rest(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    int32_t sum = 0, out[5];
    for (int g = NODE(k)->next; g != (int)UIT_NONE; g = NODE(g)->next) {
        const uit_node_t *G = NODE(g);
        if (!uit_shown(e, g, model, row) || (G->act >= 0 && !uit_act_can(e, G->act, model, row) &&
                                             e->acts[G->act].off != 2) ||
            G->kind == UIT_DIALOG || G->kind == UIT_POPOVER)
            continue;                   // not drawn, or over the page
        c->has_at = 0;                  // the last measure's ui.at rect: no row draws in it
        if (G->kind == UIT_ROW && !(G->lit & RW_GROW)) {
            sum += flow_row(e, c, s, g, model, row, 1);
        } else if (G->kind == UIT_LABEL) {
            label_rows(e, c, s, g, model, row, &sum);
        } else if (G->kind == UIT_BUTTON) {
            uint32_t n, mark = e->scratch.n, a = text(e, g, 0, model, row, &n);
            moy_ui_api_measure(c, s, MOY_UI_MEASURE_BUTTON, sspan(e, a, n), NULL, out);
            e->scratch.n = mark;
            sum += button_h(e, g, out[3]) + out[4] - out[3];
        } else {
            sum = -1;
            break;
        }
    }
    c->has_at = 0;
    return sum;
}

// A row of a flowing page. A grow= one fills its stack: under its cells, the room its page
// leaves below what follows it, so the rows after it stand at the page's foot.
static void draw_flow_row(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    int32_t out[5];
    flow_row(e, c, s, k, model, row, 0);
    if (!(NODE(k)->lit & RW_GROW) || c->page.h <= 0)
        return;
    int32_t rest = flow_rest(e, c, s, k, model, row);
    if (rest < 0)
        return;
    // the rest's rows each count the gap after them, as the page's do: the rows end at the
    // page's foot, which a page that fills its room never scrolls past
    moy_ui_api_measure(c, s, MOY_UI_MEASURE_PROGRESS, span_of("", 0), NULL, out);
    int32_t room = c->page.y + c->page.h - out[1] - rest;
    moy_ui_api_space(c, room > 0 ? room : 0);
}

// -- a long rows list: the rows in view ------------------------------------------------------
//
// A rows list of more than UIT_VROWS_MIN rows stacked on the page or a scroll region itself (its
// ancestors up to the page, or the nearest scroll, groups and switches; ui.view answers) lays out
// only the rows the view shows, UIT_VROWS_MARGIN more each side, widened to whole blocks of
// UIT_VROWS_BLOCK (so a shift frame's stops match the last frame's but where the window crosses a
// block), and the focused row with its two neighbours (an arrow's next stop): every other row is space as tall as it last drew (a row never
// drawn: the height of the first that drew). The rows total is what a whole walk makes where the
// rows are alike, its stops only the drawn rows'.
#define UIT_VROWS_MIN 32
#define UIT_VROWS_MARGIN 2
#define UIT_VROWS_BLOCK 4

static int vrows_ok(uit_t *e, int k)
{
    for (int p = NODE(k)->parent; p >= 0 && p != (int)UIT_NONE; p = NODE(p)->parent) {
        int kd = NODE(p)->kind;
        if (kd == UIT_SCROLL)
            return 1;
        if (kd != UIT_PAGE && kd != UIT_GROUP && kd != UIT_SWITCH && kd != UIT_CASE)
            return 0;
    }
    return 1;
}

static uit_vrows_t *vrows_of(uit_t *e, int k, int n, int w, int fs)
{
    const char *key = uit_str(e, NODE(k)->key);
    uint32_t hk = 2166136261u;
    for (const char *p = key; *p; p++)
        hk = (hk ^ (uint8_t)*p) * 16777619u;
    uit_vrows_t *V = NULL;
    for (int i = 0; i < e->nvr; i++)
        if (e->vr[i].key == hk)
            V = &e->vr[i];
    if (!V) {
        if (e->nvr == e->cvr) {
            int cap = e->cvr ? 2 * e->cvr : 2;
            uit_vrows_t *a = UIT_REALLOC(e->vr, (size_t)cap * sizeof(*a));
            if (!a)
                return NULL;
            e->vr = a, e->cvr = cap;
        }
        V = &e->vr[e->nvr++];
        memset(V, 0, sizeof(*V));
        V->key = hk;
        V->unit = -1;
        V->n = -1;
        V->focus = -1;
    }
    if (V->n != n || V->w != w || V->fs != fs) {
        if (V->cap < n) {
            int16_t *h = UIT_REALLOC(V->h, (size_t)n * sizeof(int16_t));
            if (!h)
                return NULL;
            V->h = h, V->cap = n;
        }
        for (int i = 0; i < n; i++)
            V->h[i] = -1;
        V->n = n, V->w = (int16_t)w, V->fs = (uint8_t)fs;
    }
    return V;
}

static void walk(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row);

// Row `r` of rows node `k`: its body walked (by=: the case its row names).
static void walk_row(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int r)
{
    int b = uit_row_body(e, k, r);
    if (b >= 0)
        walk(e, c, s, b, NODE(k)->slot, r);
}

// v: ui.view's answer. 0 where it could not keep its heights (the whole list walks instead).
static int draw_vrows(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, const int32_t *v)
{
    const uit_node_t *N = NODE(k);
    int nr = e->slots[N->slot].nrows;
    uit_vrows_t *V = vrows_of(e, k, nr, v[3], v[4]);
    if (!V)
        return 0;
    int16_t *h = V->h;
    int next = 0;
    if (V->unit < 0) {
        int y0 = c->y;
        walk_row(e, c, s, k, 0);
        h[0] = (int16_t)(c->y - y0);
        V->unit = h[0] > 0 ? h[0] : 1;
        next = 1;
    }
    int u = V->unit, top = v[1], bot = v[1] + v[2], pos = v[0], first = -1, last = nr;
    for (int i = 0; i < nr; i++) {
        if (pos >= bot) {
            last = i;
            break;
        }
        pos += h[i] >= 0 ? h[i] : u;
        if (first < 0 && pos > top)
            first = i;
    }
    if (first < 0)
        first = last;
    first -= UIT_VROWS_MARGIN;
    first = first < 0 ? 0 : first - first % UIT_VROWS_BLOCK;
    last += UIT_VROWS_MARGIN + UIT_VROWS_BLOCK - 1;
    last -= last % UIT_VROWS_BLOCK;
    last = last > nr ? nr : last;
    // the focused row, where it lies outside them
    int f = -1;
    char fid[UIT_ID_MAX + 1];
    if (moy_ui_api_focus(c, span_of(NULL, 0), fid, sizeof fid) > 0) {
        const char *sl = strrchr(fid, '/');
        size_t fn = sl ? (size_t)(sl - fid) : 0;
        for (int r = first; sl && r < last && f < 0; r++) {
            const char *rk = row_key(e, N->slot, r);
            if (strlen(rk) == fn && !memcmp(rk, fid, fn))
                f = r;
        }
        if (sl && f < 0)
            f = uit_row_find(e, N->slot, fid, fn);
    }
    // ...and its neighbours: a focus an arrow just moved has no name till drawn, so last
    // frame's focused row stands for it
    int g = f >= 0 ? f : V->focus < nr ? V->focus : -1;
    V->focus = f;
    int skip = 0;
    for (int r = next; r < nr; r++) {
        if ((r < first || r >= last) && r != f && (g < 0 || r < g - 1 || r > g + 1)) {
            skip += h[r] >= 0 ? h[r] : u;
            continue;
        }
        moy_ui_api_space(c, skip);
        skip = 0;
        int y0 = c->y;
        walk_row(e, c, s, k, r);
        h[r] = (int16_t)(c->y - y0);
    }
    moy_ui_api_space(c, skip);
    return 1;
}

int uit_tmpl_prop(const uit_t *e, int k, const char *name)
{
    for (int p = NODE(k)->props; p != (int)UIT_NONE; p = e->props[p].next)
        if (e->props[p].kind == PK_TMPL && !strcmp(uit_str(e, e->props[p].name), name))
            return e->props[p].idx;
    return -1;
}

// A template prop of `k` rendered into the scratch (n 0 where it has none): its offset.
static uint32_t prop_text(uit_t *e, int k, const char *name, int model, int row, uint32_t *n)
{
    int t = uit_tmpl_prop(e, k, name);
    *n = 0;
    return t < 0 ? 0 : uit_tmpl_render(e, t, model, row, n);
}

// Whether a shown popover hangs from node `k` on `row`: its anchor= the row's key, or the node's.
static int hung_from(uit_t *e, int k, int model, int row)
{
    const char *want = row >= 0 ? row_key(e, model, row) : uit_str(e, NODE(k)->key);
    size_t wn = strlen(want);
    for (int p = 0; p < e->nnodes; p++) {
        if (NODE(p)->kind != UIT_POPOVER || NODE(p)->t_value < 0 || !uit_shown(e, p, -1, -1))
            continue;
        uint32_t n, mark = e->scratch.n, a = uit_tmpl_render(e, NODE(p)->t_value, -1, -1, &n);
        int hit = n == wn && !memcmp(e->scratch.p + a, want, n);
        e->scratch.n = mark;
        if (hit)
            return 1;
    }
    return 0;
}

// A chat's bubble: its text, head= and status= drawn by the toolkit's bubble, side=, tone=, signal=,
// max= and lines= its words; a press fires on=, or cut= where its text was cut.
static void draw_bubble(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    uint32_t ns, nt, ng, mark = e->scratch.n, as = prop_text(e, k, "side", model, row, &ns);
    uint32_t at = prop_text(e, k, "tone", model, row, &nt), ag = prop_text(e, k, "signal", model, row, &ng);
    const char *sc = e->scratch.p;
    int32_t opt[MOY_UI_BBO_WORDS] = {ns == 3 && !memcmp(sc + as, "out", 3),
                                     ng ? (int32_t)strtol(sc + ag, NULL, 10) : -1,
                                     nt == 6 && !memcmp(sc + at, "failed", 6) ? MOY_UI_BUBBLE_FAILED : 0,
                                     N->btn, N->nbtn, hung_from(e, k, model, row)};
    e->scratch.n = mark;
    uint32_t n1, nh, a1 = text(e, k, 0, model, row, &n1);
    uint32_t ah = text_t(e, k, N->t_value, model, row, &nh);
    as = text_t(e, k, N->t_aux, model, row, &ns);
    moy_ui_over_t o;
    char id[UIT_ID_MAX + 1];
    over_for(e, k, model, row, c, &o, id);
    int32_t out[5];
    moy_ui_api_bubble(c, s, sspan(e, a1, n1), sspan(e, ah, nh), sspan(e, as, ns), opt, MOY_UI_BBO_WORDS, &o, out);
    if (out[4] & 2) {
        int cut = (out[4] & MOY_UI_ST_CUT) && N->changed >= 0, a = cut ? N->changed : N->on;
        if (a >= 0 && uit_act_can(e, a, model, row))
            fire(e, a, k, model, row, cut ? "bubble (cut)" : NULL);
    }
}

// A template int prop of `k` (0 where it has none).
static int32_t prop_int(uit_t *e, int k, const char *name, int model, int row)
{
    uint32_t n, mark = e->scratch.n, at = prop_text(e, k, name, model, row, &n);
    int32_t v = n ? (int32_t)strtol(e->scratch.p + at, NULL, 10) : 0;
    e->scratch.n = mark;
    return v;
}

// A month's calendar: year= and month= (1-12) in the toolkit's month, today= marked (0 none);
// a press on its head's previous or next chevron fires prev= or next=.
static void draw_month(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    static const char *const NAMES[12] = {"January", "February", "March", "April", "May", "June", "July",
                                          "August", "September", "October", "November", "December"};
    static const uint8_t DAYS[12] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    static const uint8_t DOW[12] = {0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4};
    int32_t y = prop_int(e, k, "year", model, row), m = prop_int(e, k, "month", model, row);
    if (m < 1 || m > 12)
        return;
    int leap = y % 4 == 0 && (y % 100 != 0 || y % 400 == 0), yy = m < 3 ? y - 1 : y;
    int first = (yy + yy / 4 - yy / 100 + yy / 400 + DOW[m - 1] + 1 + 6) % 7;     // 0 Monday (Sakamoto)
    char title[24];
    int tn = snprintf(title, sizeof title, "%s %ld", NAMES[m - 1], (long)y);
    int step = moy_ui_api_month(c, s, span_of(title, (size_t)tn), span_of("MTWTFSS", 7), first,
                                DAYS[m - 1] + (m == 2 && leap), prop_int(e, k, "today", model, row));
    int a = step < 0 ? NODE(k)->on : step > 0 ? NODE(k)->changed : -1;
    if (a >= 0 && uit_act_can(e, a, model, row))
        fire(e, a, k, model, row, NULL);
}

static void put_cell(uit_t *e, int k, int model, int row, const int32_t r[4]);

// A hints row: each row of its model a keycap hint, keys= its keys (an action the input's keys
// draw, or keys spelled out) and label= what they do; the rows tail= holds stand at its end, the
// others from its start in order while they fit, the rows drop= holds going first, the last
// first (moy_ui_api_hint_row). No stop: a press on one fires on= with its row.
static void draw_hints(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k)
{
    enum { MAX = 16 };
    const uit_node_t *N = NODE(k);
    int m = N->slot, rows[MAX], n = 0, tail = 0;
    uint32_t drop = 0;
    // each row's keys and words rendered one after the other into the scratch, each with its
    // NUL: the pairs' items, made with nothing taken from the heap once the scratch has grown
    uit_buf_t *b = &e->scratch;
    uint32_t mark = b->n;
    for (int end = 0; end < 2; end++)
        for (int r = 0; m >= 0 && r < e->slots[m].nrows && n < MAX; r++) {
            if ((N->mark >= 0 && uit_cond_eval(e, N->mark, m, r)) != end)
                continue;
            uint32_t kn = 0, ln = 0;
            if (N->t_value >= 0)
                uit_tmpl_render(e, N->t_value, m, r, &kn);
            else
                uit_buf_put(b, "", 0);
            if (N->t_main >= 0)
                uit_tmpl_render(e, N->t_main, m, r, &ln);
            else
                uit_buf_put(b, "", 0);
            if (!end && N->cur >= 0 && uit_cond_eval(e, N->cur, m, r))
                drop |= 1u << n;
            rows[n++] = r;
            tail += end;
        }
    int32_t sp[4 + 2 * MAX];
    uint32_t len = b->n > mark ? b->n - mark - 1u : 0;
    int at = moy_ui_api_hint_row(c, s, (const uint8_t *)(len ? b->p + mark : ""), len, tail, drop, sp,
                                 4 + 2 * n);
    b->n = mark;
    for (int i = 0; i < n; i++)
        if (sp[5 + 2 * i] > sp[4 + 2 * i]) {
            int32_t r[4] = {sp[4 + 2 * i], sp[1], sp[5 + 2 * i] - sp[4 + 2 * i], sp[3]};
            put_cell(e, k, m, rows[i], r);      // where a press on it lands (`uit_rect` ROWKEY/KEY)
        }
    if (at >= 0 && at < n && N->on >= 0 && uit_act_can(e, N->on, m, rows[at]))
        fire(e, N->on, k, m, rows[at], NULL);
}

// An info's or a link's tag=, tone= (its ink: a theme role) and signal= (0-4 bars) on `o`; the
// tag's text stays in the scratch for the draw.
static void value_over(uit_t *e, int k, int model, int row, moy_ui_over_t *o)
{
    uint32_t ng, nt, nk, ag = prop_text(e, k, "signal", model, row, &ng);
    uint32_t ak = prop_text(e, k, "tone", model, row, &nk), at = prop_text(e, k, "tag", model, row, &nt);
    int32_t sig = ng ? (int32_t)strtol(e->scratch.p + ag, NULL, 10) : -1, ink = nk ? button_ink(e->scratch.p + ak, nk) : -1;
    if (ng)
        moy_ui_over_put(o, MOY_UI_OV_SIGNAL, &sig);
    if (ink >= 0)
        moy_ui_over_put(o, MOY_UI_OV_INK, &ink);
    if (nt)
        moy_ui_over_text(o, MOY_UI_OV_TAG, sspan(e, at, nt));
    uint32_t nw, aw = prop_text(e, k, "swatch", model, row, &nw);
    int32_t chip = nw ? button_ink(e->scratch.p + aw, nw) : -1;     // a link's colour chip: "#RRGGBB"
    if (chip >= 0 && chip < MOY_UI_O_ROLE)
        moy_ui_over_put(o, MOY_UI_OV_FILL, &chip);
}

static void put_cell(uit_t *e, int k, int model, int row, const int32_t r[4]);

// A canvas's draw function run on node `k`: under the fit report, the texts it draws are its.
static void canvas_draw(uit_t *e, int k, int model, int row, int x, int y, int w, int h)
{
    int16_t was[3] = {e->fit_k, e->fit_model, e->fit_row};
    if (e->fits_on)
        e->fit_k = (int16_t)k, e->fit_model = (int16_t)model, e->fit_row = (int16_t)row;
    e->draw_fn(e->draw_ud, k, model, row, x, y, w, h);
    e->fit_k = was[0], e->fit_model = was[1], e->fit_row = was[2];
}

// -- the fit report (`uit_fits`) ---------------------------------------------------------

// A text the toolkit drew, for the node being drawn (moy_ui_fit_fn).
static void fit_told(void *ud, const uint8_t *p, size_t n, int x, int y, int w, int room, int how)
{
    uit_t *e = ud;
    char id[UIT_ID_MAX + 1] = "";
    int kind = 0;
    if (e->fit_k >= 0) {
        node_id(e, e->fit_k, e->fit_model, e->fit_row, id);
        kind = NODE(e->fit_k)->kind;
    }
    uit_buf_printf(&e->fits, "%s\x1f%d\x1f%d\x1f%d\x1f%d\x1f%d\x1f%d\x1f%.*s\x1e", id, kind, how, x, y, w, room,
                   (int)n, (const char *)p);
}

void uit_fits_on(uit_t *e, int on)
{
    e->fits_on = on != 0;
    if (!on)
        uit_buf_free(&e->fits);
}

int uit_fits(uit_t *e, char *buf, size_t cap)
{
    int n = (int)e->fits.n;
    if (buf && (size_t)n <= cap)
        memcpy(buf, e->fits.p, (size_t)n);
    return n;
}

static void draw_node(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row);

// Node `k` drawn: under the fit report, the texts the toolkit draws meanwhile are its.
static void draw(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    if (!e->fits_on) {
        draw_node(e, c, s, k, model, row);
        return;
    }
    int16_t was[3] = {e->fit_k, e->fit_model, e->fit_row};
    e->fit_k = (int16_t)k, e->fit_model = (int16_t)model, e->fit_row = (int16_t)row;
    draw_node(e, c, s, k, model, row);
    e->fit_k = was[0], e->fit_model = was[1], e->fit_row = was[2];
}

// Note `k`'s icon ("info" where it has none) and each line's paragraph into `lines`,
// NUL-separated, empty ones kept.
static moy_ui_span_t note_of(uit_t *e, int k, int model, int row, uit_buf_t *lines)
{
    const uit_node_t *N = NODE(k);
    uint32_t ni, ai = N->t_icon >= 0 ? uit_tmpl_render(e, N->t_icon, model, row, &ni) : 0;
    if (N->t_icon < 0 || !ni)
        ai = 0, ni = 0;
    int any = 0;
    for (int p = N->props; p != (int)UIT_NONE; p = e->props[p].next) {
        const uit_prop_t *P = &e->props[p];
        if (strcmp(uit_str(e, P->name), "lines"))
            continue;
        uint32_t n, at = uit_tmpl_render(e, P->idx, model, row, &n);
        if (any++)
            uit_buf_printf(lines, "%c", 0);
        uit_buf_printf(lines, "%.*s", (int)n, e->scratch.p + at);
    }
    return ni ? sspan(e, ai, ni) : span_of("info", 4);
}

// A link with sub=: a list's two-line row (moy_ui_api_value2), its icon= the lead ("@NAME" a
// person's initials), its value at the right of its label, sub= under them, count= a badge at the
// sub's right, tag= a pill or mark= an icon after the label.
static void link_two(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    moy_ui_over_t o;
    char id[UIT_ID_MAX + 1];
    uint32_t n[7] = {0}, a[7] = {0};
    a[0] = text(e, k, 0, model, row, &n[0]);
    a[1] = text(e, k, 1, model, row, &n[1]);
    if (N->t_icon >= 0)
        a[2] = uit_tmpl_render(e, N->t_icon, model, row, &n[2]);
    a[3] = prop_text(e, k, "sub", model, row, &n[3]);
    a[4] = prop_text(e, k, "count", model, row, &n[4]);
    a[5] = prop_text(e, k, "tag", model, row, &n[5]);
    a[6] = prop_text(e, k, "mark", model, row, &n[6]);
    moy_ui_over_none(&o);
    node_id(e, k, model, row, id);
    id_put(e, k, model, row, id);
    moy_ui_over_text(&o, MOY_UI_OV_ID, span_of(id, strlen(id)));
    moy_ui_row2_t r2;
    memset(&r2, 0, sizeof(r2));
    r2.lead = sspan(e, a[2], n[2]);
    r2.person = (int16_t)(n[2] > 0 && r2.lead.p[0] == '@');
    if (r2.person)
        r2.lead.p++, r2.lead.n--;
    r2.value = sspan(e, a[1], n[1]);
    r2.sub = sspan(e, a[3], n[3]);
    r2.count = sspan(e, a[4], n[4]);
    r2.tag = sspan(e, a[5], n[5]);
    r2.mark = sspan(e, a[6], n[6]);
    if (moy_ui_api_value2(c, s, sspan(e, a[0], n[0]), &r2, &o) && uit_act_can(e, N->act, model, row))
        fire(e, N->act, k, model, row, NULL);
}

static void draw_node(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    moy_ui_over_t o;
    char id[UIT_ID_MAX + 1];
    uint32_t n1, n2, a1, a2;
    switch (N->kind) {
    case UIT_GROUP:
        a1 = text(e, k, 0, model, row, &n1);
        if (N->lit == 1)
            moy_ui_api_group_card(c, s);        // look="card": its rows on a card of their own
        else if (N->lit == 2)
            moy_ui_api_group_rules(c, s);       // look="rules": its rows ruled apart
        else
            moy_ui_api_group(c, s, sspan(e, a1, n1), NULL);
        walk(e, c, s, k, model, row);
        moy_ui_api_group(c, s, span_of("", 0), NULL);
        break;
    case UIT_LABEL:
        label_rows(e, c, s, k, model, row, NULL);
        break;
    case UIT_LINK:
        if (uit_tmpl_prop(e, k, "sub") >= 0) {
            link_two(e, c, s, k, model, row);
            break;
        }
        // fall through
    case UIT_INFO:
        a1 = text(e, k, 0, model, row, &n1);
        a2 = text(e, k, 1, model, row, &n2);
        over_for(e, k, model, row, c, &o, id);
        value_over(e, k, model, row, &o);
        if (moy_ui_api_value(c, s, N->kind == UIT_INFO ? MOY_UI_V_INFO : MOY_UI_V_LINK, sspan(e, a1, n1),
                             sspan(e, a2, n2), &o) &&
            N->kind == UIT_LINK && uit_act_can(e, N->act, model, row))
            fire(e, N->act, k, model, row, NULL);
        break;
    case UIT_BUTTON:
        a1 = text(e, k, 0, model, row, &n1);
        over_for(e, k, model, row, c, &o, id);
        o.small = (e->flags & UIT_F_BAR) && (N->btn & BT_ALONE);    // one bar, one icon size
        if (e->in_cell) {
            int32_t one = 1;
            moy_ui_over_put(&o, MOY_UI_OV_FIT, &one);
        }
        n2 = n1;
        if ((N->btn & BT_ALONE) && (N->t_icon >= 0 || (N->act >= 0 && uit_str(e, e->acts[N->act].icon)[0])))
            n1 = 0;                 // its icon alone, its word its tooltip
        int32_t big[5] = {0};
        if ((N->btn & BT_HERO) && !e->in_flow && !e->in_cell && !e->in_foot && !e->placed &&
            moy_ui_api_measure(c, s, MOY_UI_MEASURE_BUTTON, sspan(e, a1, n1), NULL, big)) {
            // a hero button stacked on the page: its own width at the row's start, half again as tall
            big[2] = button_w(e, c, s, k, model, row);
            moy_ui_api_at(c, big[0], big[1], big[2], button_h(e, k, big[3]));
        }
        a2 = moy_ui_api_button(c, s, sspan(e, a1, n1), button_kind(e, k, model, row), &o);
        if (big[2])
            moy_ui_api_space(c, button_h(e, k, big[3]) + big[4] - big[3]);
        if (n1 != n2)
            moy_ui_api_tip(c, &o, sspan(e, a1, n2));
        if (a2 && uit_act_can(e, N->act, model, row))
            fire(e, N->act, k, model, row, NULL);
        break;
    case UIT_TOGGLE: {
        uit_slot_t *S = &e->slots[N->slot];
        int field = (N->lit & NL_FIELD) != 0;
        int cur = field ? uit_cell(e, model, row, N->cur)[0] == '1' : S->i != 0;
        a1 = text(e, k, 0, model, row, &n1);
        over_for(e, k, model, row, c, &o, id);
        int got = moy_ui_api_toggle(c, s, sspan(e, a1, n1), cur, &o) != 0;
        if (got != cur && field) {
            row_wrote(e, k, model, row, got ? "1" : "0", cur ? "True" : "False", got ? "True" : "False");
        } else if (got != cur) {
            uit_set_int(e, N->slot, got);
            uit_buf_t b = {0};
            const char *key = uit_str(e, N->key);
            uit_buf_printf(&b, "from toggle ");
            uit_buf_repr(&b, key, strlen(key));
            wrote(e, k, cur ? "True" : "False", got ? "True" : "False", b.p, N->on);
            uit_buf_free(&b);
        }
        break;
    }
    case UIT_SEG: {
        a1 = text(e, k, 0, model, row, &n1);
        if (N->lit & NL_PICS) {
            draw_pics(e, c, s, k, model, row, a1, n1);
            break;
        }
        int count, at;
        if (N->lit & NL_FIELD) {
            // bound to an int field of its row: its items the lines text= renders over the row
            uint32_t len, items = field_seg_items(e, N, model, row, &len, &count, &at);
            over_for(e, k, model, row, c, &o, id);
            int got = moy_ui_api_choice(c, s, (N->lit & NL_CYCLE) ? MOY_UI_V_CYCLE : MOY_UI_V_SEG,
                                        sspan(e, a1, n1), (const uint8_t *)e->scratch.p + items, len, at, &o);
            if (got >= 0 && got < count && got != at) {
                char was[16], now[16];
                snprintf(was, sizeof was, "%d", at);
                snprintf(now, sizeof now, "%d", got);
                row_wrote(e, k, model, row, now, was, now);
            }
            break;
        }
        uint32_t len, items = seg_items(e, N, &len, &count, &at);
        int look = (N->lit & NL_CYCLE) ? MOY_UI_V_CYCLE : MOY_UI_V_SEG;
        if (N->lit & NL_SWATCH) {
            // the swatches look: each word a colour (0xRRGGBB, any base strtol reads), packed as
            // the swatch row's little-endian words
            look = MOY_UI_V_SWATCH;
            items = swatch_words(e, items, count, &len);
        }
        over_for(e, k, model, row, c, &o, id);
        int got = moy_ui_api_choice(c, s, look, sspan(e, a1, n1),
                                    (const uint8_t *)e->scratch.p + items, len, at, &o);
        if (got >= 0 && got < count && got != at) {
            const char *v = seg_key(e, N, got);
            wrote_text(e, k, v, strlen(v), "from", N->on);
        }
        break;
    }
    case UIT_SLIDER: {
        uint32_t ln, hn, la = uit_tmpl_render(e, N->t_value, model, row, &ln);
        int32_t lo = (int32_t)strtol(e->scratch.p + la, NULL, 10);
        uint32_t ha = uit_tmpl_render(e, N->t_aux, model, row, &hn);
        int32_t hi = (int32_t)strtol(e->scratch.p + ha, NULL, 10);
        a1 = text(e, k, 0, model, row, &n1);
        over_for(e, k, model, row, c, &o, id);
        if (N->lit & (NL_STEPS | NL_BLOCKS)) {
            int32_t look = (N->lit & NL_BLOCKS) ? 2 : 1;     // look="blocks": the steps across the row
            moy_ui_over_put(&o, MOY_UI_OV_STEPS, &look);
        }
        int field = (N->lit & NL_FIELD) != 0;
        int32_t cur = field ? (int32_t)strtol(uit_cell(e, model, row, N->cur), NULL, 10) : e->slots[N->slot].i;
        int32_t got = moy_ui_api_slider(c, s, sspan(e, a1, n1), cur, lo, hi, &o);
        if (got != cur && field) {
            char was[16], now[16];
            snprintf(was, sizeof was, "%ld", (long)cur);
            snprintf(now, sizeof now, "%ld", (long)got);
            row_wrote(e, k, model, row, now, was, now);
        } else if (got != cur) {
            uit_set_int(e, N->slot, got);
            char was[16], now[16];
            snprintf(was, sizeof was, "%ld", (long)cur);
            snprintf(now, sizeof now, "%ld", (long)got);
            uit_buf_t b = {0};
            const char *key = uit_str(e, N->key);
            uit_buf_printf(&b, "from slider ");
            uit_buf_repr(&b, key, strlen(key));
            wrote(e, k, was, now, b.p, N->on);
            uit_buf_free(&b);
        }
        break;
    }
    case UIT_STEPPER: {
        // value= between the chevrons, each greyed while its action (prev= in `on`, next= in
        // `changed`) is off; a step fires it
        a1 = text(e, k, 1, model, row, &n1);
        int can = (N->on >= 0 && uit_act_can(e, N->on, model, row) ? 1 : 0) |
                  (N->changed >= 0 && uit_act_can(e, N->changed, model, row) ? 2 : 0);
        over_for(e, k, model, row, c, &o, id);
        int32_t box[4];
        int step = moy_ui_api_stepper(c, s, sspan(e, a1, n1), can, N->lit ? MOY_UI_TONE_DIM : MOY_UI_TONE_INK, &o,
                                      box);
        put_rect(e, k, box);            // where a press on it lands (`uit_rect`)
        if (step)
            fire(e, step < 0 ? N->on : N->changed, k, model, row, NULL);
        break;
    }
    case UIT_FIELD:
        draw_field(e, c, s, k, model, row);
        break;
    case UIT_ROWS: {
        const uit_slot_t *M = &e->slots[N->slot];
        uit_after_removal(e, k);
        if (!M->nrows && N->t_aux >= 0) {
            uint32_t n, at = uit_tmpl_render(e, N->t_aux, -1, -1, &n);
            if (n)
                moy_ui_api_label(c, s, sspan(e, at, n), NULL);
        }
        int32_t vw[5];
        if (N->t_main < 0 && M->nrows > UIT_VROWS_MIN && vrows_ok(e, k) && moy_ui_api_view(c, vw)
            && draw_vrows(e, c, s, k, vw))
            break;
        // group=: a caption where its text changes from the row before, the rows under it on its card
        uint32_t cap_at = 0, cap_n = 0;
        int capped = 0;
        for (int r = 0; r < e->slots[N->slot].nrows; r++) {
            if (N->t_main >= 0) {
                uint32_t n, at = uit_tmpl_render(e, N->t_main, N->slot, r, &n);
                if (!capped || n != cap_n || memcmp(e->scratch.p + at, e->scratch.p + cap_at, n)) {
                    if (capped)
                        moy_ui_api_group(c, s, span_of("", 0), NULL);
                    moy_ui_api_group(c, s, sspan(e, at, n), NULL);
                    cap_at = at, cap_n = n, capped = 1;
                }
            }
            walk_row(e, c, s, k, r);
        }
        if (capped)
            moy_ui_api_group(c, s, span_of("", 0), NULL);
        break;
    }
    case UIT_TEXT_VIEW:
        draw_text_view(e, c, s, k, model, row);
        break;
    case UIT_MENU:
        draw_menu(e, c, s, k, model, row);
        break;
    case UIT_SPLIT:
        draw_split(e, c, s, k, model, row);
        break;
    case UIT_GRID:
        draw_grid(e, c, s, k, model, row);
        break;
    case UIT_CANVAS: {
        // a row of the page that only draws, no stop; with keys= a stop, its ring unless mark=False;
        // in a list's body under its row's id (ROWKEY/KEY)
        char key[UIT_ID_MAX + 1];
        node_id(e, k, model, row, key);
        int32_t one = 1, r[5];
        moy_ui_over_none(&o);
        moy_ui_over_text(&o, MOY_UI_OV_ID, span_of(key, strlen(key)));
        if ((e->flags & UIT_F_BARE) || e->in_foot)
            moy_ui_over_put(&o, MOY_UI_OV_BARE, &one);       // a bare page's canvases sink no well
        if (N->lit & CV_KEYS) {
            if (N->lit & CV_NOMARK)
                moy_ui_over_put(&o, MOY_UI_OV_MARK, &(int32_t){0});
            id_put(e, k, model, row, key);
        } else {
            moy_ui_over_put(&o, MOY_UI_OV_DISABLED, &one);
        }
        moy_ui_api_part(c, s, span_of(key, strlen(key)), 0, canvas_h(e, k), &o, r);
        // where it stands, drawn this pass or left as the shift frame's move left it (r's 0s)
        int32_t at[4] = {c->pa_box.x, c->pa_box.y, c->pa_box.w, c->pa_box.h};
        put_rect(e, k, at);             // where a press on it lands (`uit_rect`)
        if (model >= 0)
            put_cell(e, k, model, row, at); // in a list's body: its row's (`uit_rect`'s ROWKEY/KEY)
        canvas_drew(e, k);
        if (e->draw_fn && !c->pa_none)
            canvas_draw(e, k, model, row, r[0], r[1], r[2], r[3]);
        break;
    }
    case UIT_TABS:
        draw_tabs(e, c, s, k);
        break;
    case UIT_ROW:                       // (a placed page's own rows are `place_at`'s; this one flows)
        draw_flow_row(e, c, s, k, model, row);
        break;
    case UIT_SWITCH: {
        int cs = uit_case_of(e, k);
        if (cs >= 0)
            walk(e, c, s, cs, model, row);
        break;
    }
    case UIT_TABLE:
        draw_table(e, c, s, k);
        break;
    case UIT_FOOT:
        draw_foot(e, c, s, k, model, row);
        break;
    case UIT_CARDS:
        if (NODE(k)->lit & CD_CAROUSEL)
            draw_carousel(e, c, s, k);
        else if (NODE(k)->lit & (CD_SHELF | CD_ICONS | CD_COLUMN))
            draw_cells(e, c, s, k);
        else
            draw_cards(e, c, s, k);
        break;
    case UIT_PICTURE:
        draw_picture(e, c, s, k, model, row);
        break;
    case UIT_POPOVER:
        draw_popover(e, c, s, k, model, row);
        break;
    case UIT_SCROLL:
        scroll_open(e, c, s, k, N->lit);
        walk(e, c, s, k, model, row);
        moy_ui_api_scroll(c, s, span_of("", 0), NULL);
        break;
    case UIT_PROGRESS: {
        uint32_t vn, hn, va = uit_tmpl_render(e, N->t_value, model, row, &vn);
        int32_t v = (int32_t)strtol(e->scratch.p + va, NULL, 10);
        uint32_t ha = uit_tmpl_render(e, N->t_aux, model, row, &hn);
        int32_t hi = (int32_t)strtol(e->scratch.p + ha, NULL, 10);
        a1 = text(e, k, 0, model, row, &n1);
        // stacked in a split's cell: its label and percent on a line, its bar under them, across
        // the cell (a flow row's progress too; on the page its stacked row holds them on one)
        int32_t pv[5], pm[5], pstep = -1;
        if (e->in_cell && !e->in_flow && moy_ui_api_view(c, pv)) {
            moy_ui_api_measure(c, s, MOY_UI_MEASURE_PROGRESS, span_of("", 0), NULL, pm);
            int32_t gap = pm[4] - pm[3] > 0 ? pm[4] - pm[3] : 0, ph[5];
            moy_ui_api_at(c, pm[0], pm[1], pm[2], 1);
            moy_ui_api_measure(c, s, MOY_UI_MEASURE_PROGRESS, span_of("", 0), NULL, ph);
            moy_ui_api_at(c, pm[0], pm[1], pm[2], ph[3]);
            pstep = ph[3] + gap + ((e->flags & UIT_F_DESK) ? 6 : 3 * e->fs);
        }
        if (!(N->lit & NL_STEPS)) {
            moy_ui_api_progress(c, s, sspan(e, a1, n1), v, hi, NULL);
            if (pstep >= 0)
                moy_ui_api_space(c, pstep);
            break;
        }
        // look="count": the label, where there is one, says the count in its own words
        char cnt[32];
        moy_ui_span_t l = sspan(e, a1, n1);
        if (!n1)
            l = span_of(cnt, hi ? (size_t)snprintf(cnt, sizeof cnt, "%ld of %ld", (long)v, (long)hi) : 0);
        int32_t one = 1;
        moy_ui_over_none(&o);
        moy_ui_over_put(&o, MOY_UI_OV_STEPS, &one);
        moy_ui_api_progress(c, s, l, v, hi, &o);
        if (pstep >= 0)
            moy_ui_api_space(c, pstep);
        break;
    }
    case UIT_RULE:
        moy_ui_api_rule(c, s);
        break;
    case UIT_CELLS: {
        // the palette's colours from first=, count= of them in rows of cols=, each a side=
        // square (a handheld's at its scale) less gap=, the colour clear= (none where it has
        // none) shown as clear; the int it is bound to their current one, which on= hears
        // move; Enter or a tap on a cell fires pick=
        int32_t sc = (e->flags & UIT_F_DESK) ? 1 : e->fs;
        uint32_t cn, cm = e->scratch.n, ca = prop_text(e, k, "clear", model, row, &cn);
        int32_t clear = cn ? (int32_t)strtol(e->scratch.p + ca, NULL, 10) : -1;
        e->scratch.n = cm;
        int32_t first = prop_int(e, k, "first", model, row), count = prop_int(e, k, "count", model, row);
        int32_t cols = prop_int(e, k, "cols", model, row), side = prop_int(e, k, "side", model, row) * sc;
        int32_t gap = prop_int(e, k, "gap", model, row) * space_unit(e), cur = e->slots[N->slot].i;
        int picked = 0;
        over_for(e, k, model, row, c, &o, id);
        moy_ui_over_put(&o, MOY_UI_OV_MARK, &(int32_t){0});    // its mark is the cursor on its cell
        int32_t got = moy_ui_api_cells(c, s, span_of(id, strlen(id)), first, count ? count : 64,
                                       cols ? cols : 8, side ? side : 12 * sc, gap, cur,
                                       (N->lit & NL_EDGE) != 0, clear, &o, &picked);
        if (got != cur) {
            char was[16], now[16];
            uit_set_int(e, N->slot, got);
            snprintf(was, sizeof was, "%ld", (long)cur);
            snprintf(now, sizeof now, "%ld", (long)got);
            uit_buf_t b = {0};
            const char *key = uit_str(e, N->key);
            uit_buf_printf(&b, "from cells ");
            uit_buf_repr(&b, key, strlen(key));
            wrote(e, k, was, now, b.p, N->on);
            uit_buf_free(&b);
        }
        if (picked && N->changed >= 0 && uit_act_can(e, N->changed, model, row))
            fire(e, N->changed, k, model, row, NULL);
        break;
    }
    case UIT_TOAST: {
        // its pill over the foot of the page's body, clear of its docked foot (look="flat": in
        // flat fills, filling the page's room); its icon, else check. With sub=, the banner:
        // its card centred at the top of the page's room, the icon's tile, the text in `value`
        // over the sub line, a burst= of confetti from its edges (1..255 of the way out, 0
        // none); look="badge" an achievement's, at the foot of the room, ringed in the accent,
        // burst= its shine crossing it, and "secret" the badge's with the confetti too. Its
        // rect is the pill's or the card's.
        int desk = (e->flags & UIT_F_DESK) != 0, flat = (N->lit & TS_FLAT) != 0;
        uint32_t ni = 0, ai = N->t_icon >= 0 ? uit_tmpl_render(e, N->t_icon, model, row, &ni) : 0;
        int32_t out[4], lift = flat ? 0 : desk ? 12 : 6 * e->fs;
        a1 = text(e, k, 0, model, row, &n1);
        if (!n1)
            break;
        if (N->t_value >= 0) {
            a2 = text(e, k, 1, model, row, &n2);
            int32_t burst = N->t_aux >= 0 ? int_of(e, N->t_aux, model, row, 0) : 0;
            static const uint8_t check[] = "check";
            moy_ui_span_t ic = ni ? sspan(e, ai, ni) : (moy_ui_span_t){check, 5};
            moy_ui_box_t b = {0, 0, 0, 0};
            c->fl.dirty = 1;            // over the page, whole (as the pill)
            c->fl.top = 1;
            burst = burst < 0 ? 0 : burst > 255 ? 255 : burst;
            int slot = moy_ui_icon_slot(ic.p, ic.n), glyph = moy_ui_icon_glyph(ic.p, ic.n);
            if (N->lit & (TS_BADGE | TS_SECRET)) {
                moy_ui_badge(s, e->rect[0] + e->rect[2] / 2, e->rect[1] + e->rect[3], sspan(e, a1, n1),
                             sspan(e, a2, n2), slot, glyph, burst, (N->lit & TS_SECRET) ? burst : 0, e->fs,
                             desk, &b);
            } else {
                moy_ui_unlock(s, e->rect[0] + e->rect[2] / 2, e->rect[1], sspan(e, a1, n1), sspan(e, a2, n2),
                              slot, glyph, burst, e->fs, desk, &b);
            }
            out[0] = b.x, out[1] = b.y, out[2] = b.w, out[3] = b.h;
        } else {
            moy_ui_api_at(c, e->rect[0], e->rect[1], e->rect[2], e->rect[3] - lift);
            moy_ui_api_toast(c, s, sspan(e, a1, n1), sspan(e, ai, ni), flat, out);
        }
        put_rect(e, k, out);
        break;
    }
    case UIT_BUBBLE:
        draw_bubble(e, c, s, k, model, row);
        break;
    case UIT_MONTH:
        draw_month(e, c, s, k, model, row);
        break;
    case UIT_HINTS:
        draw_hints(e, c, s, k);
        break;
    case UIT_NOTE: {
        uit_buf_t lines = {0};
        moy_ui_span_t icon = note_of(e, k, model, row, &lines);
        moy_ui_api_note(c, s, icon, (const uint8_t *)(lines.p ? lines.p : ""), lines.n);
        uit_buf_free(&lines);
        break;
    }
    case UIT_EMPTY: {
        uint32_t ni, ai = N->t_icon >= 0 ? uit_tmpl_render(e, N->t_icon, model, row, &ni) : 0;
        if (N->t_icon < 0 || !ni)
            ai = 0, ni = 0;
        a1 = text(e, k, 0, model, row, &n1);
        uit_buf_t lines = {0};
        int any = 0;
        for (int p = N->props; p != (int)UIT_NONE; p = e->props[p].next) {
            const uit_prop_t *P = &e->props[p];
            if (strcmp(uit_str(e, P->name), "lines"))
                continue;
            uint32_t n, at = uit_tmpl_render(e, P->idx, model, row, &n);
            if (!n)
                continue;
            if (any++)
                uit_buf_printf(&lines, "%c", 0);
            empty_line(e, s, &lines, e->scratch.p + at, n, c->has_at ? c->at.w : c->page.w);
        }
        int32_t m[4] = {c->has_at ? c->at.x : c->page.x, 0, c->has_at ? c->at.w : c->page.w, 0};
        // on the desk a sixth of the page down, as its column of words, as far as the room under
        // it holds what it says and its controls; where they run past the view even at the
        // top, no disc (an empty icon)
        int32_t ev[5];
        moy_ui_span_t icon = ni ? sspan(e, ai, ni) : span_of("warn", 4);
        if (c->has_at) {
            // placed at its rect: no disc where what it says and its controls would run past it
            moy_ui_box_t mb = {0, 0, c->at.w, 0};
            const uint8_t *lp = (const uint8_t *)(lines.p ? lines.p : "");
            int desk = (e->flags & UIT_F_DESK) ? MOY_UI_DESK : 0;
            if (moy_ui_empty(s, mb, 0, -1, sspan(e, a1, n1), lp, lines.n, e->fs, desk, 0) +
                    empty_controls_h(e, k, model, row) > c->at.h)
                icon = span_of("", 0);
        } else if (moy_ui_api_view(c, ev)) {
            moy_ui_box_t mb = {0, 0, (int16_t)ev[3], 0};
            moy_ui_span_t t = sspan(e, a1, n1);
            const uint8_t *lp = (const uint8_t *)(lines.p ? lines.p : "");
            int desk = (e->flags & UIT_F_DESK) ? MOY_UI_DESK : 0;
            int32_t need = moy_ui_empty(s, mb, 0, -1, t, lp, lines.n, e->fs, desk, 0)
                           + empty_controls_h(e, k, model, row);
            int32_t room = ev[2] - ev[0];
            if (need > room) {
                icon = span_of("", 0);
                need = moy_ui_empty(s, mb, -1, -1, t, lp, lines.n, e->fs, desk, 0)
                       + empty_controls_h(e, k, model, row);
            }
            int32_t sp = e->rect[3] / 6;
            sp = sp < room - need ? sp : room - need;
            if (desk && ev[0] == 0 && sp > 0)
                moy_ui_api_space(c, sp);
        }
        int32_t y = moy_ui_api_empty(c, s, icon, sspan(e, a1, n1),
                                     (const uint8_t *)(lines.p ? lines.p : ""), lines.n);
        uit_buf_free(&lines);
        empty_controls(e, c, s, k, model, row, m[0], m[2], y);
        break;
    }
    case UIT_DIALOG: {
        a1 = text(e, k, 0, model, row, &n1);
        uit_buf_t b = {0};
        // look="keys" on the T-Deck: the band's Enter and Esc are its buttons, no row of them
        int nb = (N->lit & DL_KEYS) && e->input == UIT_IN_TDECK && N->nbtn <= 2 ? 0 : N->nbtn;
        // each button's label: its labels= template (one a button), else its action's
        for (int i = 0; i < nb; i++) {
            int t = dialog_label(e, k, i);
            if (i)
                uit_buf_printf(&b, "%c", 0);
            if (t >= 0) {
                uint32_t ln, la = uit_tmpl_render(e, t, model, row, &ln);
                uit_buf_printf(&b, "%.*s", (int)ln, e->scratch.p + la);
            } else {
                uit_buf_printf(&b, "%s", uit_str(e, e->acts[e->btns[N->btn + i]].label));
            }
        }
        // the labels joined by NULs: b.n counts them (uit_buf_printf of "%c", 0 adds one byte)
        // the verb's kind, the toolkit's: primary (1), or with kind="danger" danger (3)
        int pick = moy_ui_api_dialog(c, s, sspan(e, a1, n1), (const uint8_t *)(b.p ? b.p : ""), b.n,
                                     (N->lit & DL_DANGER) ? 3 : 1, NULL);
        uit_buf_free(&b);
        walk(e, c, s, k, model, row);
        moy_ui_api_dialog(c, s, span_of("", 0), (const uint8_t *)"", 0, 0, NULL);
        if (pick >= 0 && pick < nb) {
            int a = e->btns[N->btn + pick];
            uit_buf_t t = {0};
            const char *nm = uit_str(e, e->acts[a].name);
            uit_buf_printf(&t, "button ");
            uit_buf_repr(&t, nm, strlen(nm));
            uit_buf_printf(&t, " of dialog ");
            uint32_t n, at = uit_tmpl_render(e, N->t_main, -1, -1, &n);
            uit_buf_repr(&t, e->scratch.p + at, n);
            uit_event(e, UIT_EV_ACTION, a, -1, -1, t.p, t.n);
            uit_buf_free(&t);
        }
        break;
    }
    }
}

// The height an empty's controls take under what it says (empty_controls').
static int32_t empty_controls_h(uit_t *e, int k, int model, int row)
{
    int desk = (e->flags & UIT_F_DESK) != 0, mn;
    int32_t hh = (moy_ui_metrics(MOY_UI_K_VALUE_ROW, &mn)[desk ? 17 : 16] + 4) * e->fs, h = 0;
    KIDS(k, c2) {
        const uit_node_t *N = NODE(c2);
        if (!uit_shown(e, c2, model, row))
            continue;
        if (N->act >= 0 && !uit_act_can(e, N->act, model, row) && e->acts[N->act].off != 2)
            continue;
        h += hh + row_gap(e);
    }
    return h;
}

// An empty's controls under what it says (from y), each its natural width and a value row
// and 4 px tall, centred across x..x+w, one under the next.
static void empty_controls(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                           int32_t x, int32_t w, int32_t y)
{
    int desk = (e->flags & UIT_F_DESK) != 0, mn;
    int32_t hh = (moy_ui_metrics(MOY_UI_K_VALUE_ROW, &mn)[desk ? 17 : 16] + 4) * e->fs;
    KIDS(k, c2) {
        const uit_node_t *N = NODE(c2);
        if (!uit_shown(e, c2, model, row))
            continue;
        if (N->act >= 0 && !uit_act_can(e, N->act, model, row) && e->acts[N->act].off != 2)
            continue;
        int32_t bw = natural(e, c2, model, row, hh);
        bw = bw < 0 || bw > w ? w : bw;
        int32_t r[4] = {x + (w - bw) / 2, y, bw, hh};
        put_rect(e, c2, r);
        moy_ui_api_at(c, r[0], r[1], r[2], r[3]);
        draw(e, c, s, c2, model, row);
        y += hh + row_gap(e);
    }
}

static void walk(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    KIDS(k, c2) {
        const uit_node_t *N = NODE(c2);
        if (!uit_shown(e, c2, model, row))
            continue;
        if (N->act >= 0 && !uit_act_can(e, N->act, model, row) && e->acts[N->act].off != 2)
            continue;
        draw(e, c, s, c2, model, row);
    }
}

// -- focus, before the page draws and after ---------------------------------------------

static int id_in(uit_t *e, const char *want, char out[UIT_ID_MAX + 1])
{
    for (int i = 0; i < e->nprev; i++) {
        const uit_id_t *I = &e->prev[i];
        int hit;
        if (I->row >= 0) {
            // a row drawn last frame that its model still holds (a list filtered since keeps
            // fewer): never "" for a row past its end
            int m = I->gen == e->gen ? uit_model_of(e, I->node) : -1;
            hit = m >= 0 && I->row < e->slots[m].nrows && *want && !strcmp(row_key(e, m, I->row), want);
        } else {
            hit = !strcmp(I->id, want);
        }
        if (hit) {
            strcpy(out, I->id);
            return 1;
        }
    }
    return 0;
}

static int is_menu_rows(uit_t *e, int k);
static void menu_row_id(uit_t *e, int link, int m, int r, char id[UIT_ID_MAX + 1]);

static int row_stop_id(uit_t *e, int lst, const char *key, size_t n, char out[UIT_ID_MAX + 1])
{
    int r = uit_row_find(e, NODE(lst)->slot, key, n);
    if (r < 0)
        return 0;
    if (e->placed && is_menu_rows(e, lst)) {
        menu_row_id(e, NODE(lst)->kid, NODE(lst)->slot, r, out);     // a menu row's id is its text
        return 1;
    }
    if (NODE(lst)->kind == UIT_TABLE || IS_ONE_STOP(lst)) {
        snprintf(out, UIT_ID_MAX + 1, "%s", uit_str(e, NODE(lst)->key));     // one stop, its key the id
        return 1;
    }
    int b = uit_row_body(e, lst, r);
    if (NODE(lst)->parent != UIT_NONE && NODE(NODE(lst)->parent)->kind == UIT_MENU) {
        KIDS(b < 0 ? lst : b, g)                // a menu's item: its id is its label (`draw_menu`)
        if (NODE(g)->kind == UIT_ITEM && uit_shown(e, g, NODE(lst)->slot, r)) {
            uit_buf_t l = {0};
            item_label(e, g, NODE(lst)->slot, r, e->menu_keys, &l);
            snprintf(out, UIT_ID_MAX + 1, "%.*s", (int)l.n, l.p ? l.p : "");
            uit_buf_free(&l);
            return 1;
        }
        return 0;
    }
    KIDS(b < 0 ? lst : b, g)
    if (is_stop(NODE(g)->kind) && NODE(g)->kind != UIT_SEG) {
        snprintf(out, UIT_ID_MAX + 1, "%.*s/%s", (int)n, key, uit_str(e, NODE(g)->key));
        return 1;
    }
    return 0;
}

static void focus_to(moy_ui_ctx_t *c, const char *id)
{
    moy_ui_api_focus(c, span_of(id, strlen(id)), NULL, 0);
}

// The shown dialog's button `key` names (its action's name or its label): its label, the
// toolkit's id for it, into out; 0 where no shown dialog has such a button.
static int dialog_button(uit_t *e, const char *key, char out[UIT_ID_MAX + 1])
{
    int d = uit_dialog(e);
    if (d < 0)
        return 0;
    const uit_node_t *N = NODE(d);
    for (int i = 0; i < N->nbtn; i++) {
        int a = e->btns[N->btn + i], t = dialog_label(e, d, i);
        if (t >= 0) {
            uint32_t ln, la = uit_tmpl_render(e, t, -1, -1, &ln);
            snprintf(out, UIT_ID_MAX + 1, "%.*s", (int)ln, e->scratch.p + la);
        } else {
            snprintf(out, UIT_ID_MAX + 1, "%s", uit_str(e, e->acts[a].label));
        }
        if (!strcmp(key, uit_str(e, e->acts[a].name)) || !strcmp(key, out))
            return 1;
    }
    return 0;
}

// `_land_focus`: (whether focus moved, a node foreseen into ahead).
// Whether node k draws this frame: it and each node over it shown, each case its switch's pick.
static int drawn_now(uit_t *e, int k)
{
    for (; k > 0 && k != (int)UIT_NONE; k = NODE(k)->parent) {
        if (!uit_shown(e, k, -1, -1))
            return 0;
        int p = NODE(k)->parent;
        if (p != (int)UIT_NONE && NODE(p)->kind == UIT_SWITCH && uit_case_of(e, p) != k)
            return 0;
    }
    return 1;
}

static int land_focus(uit_t *e, moy_ui_ctx_t *c, char ahead[UIT_ID_MAX + 1])
{
    int moved = 0;
    ahead[0] = 0;
    char fid[UIT_ID_MAX + 1];
    int fresh_prev = e->fresh && e->nprev && e->prev[0].gen == e->gen;    // not another page's
    if (fresh_prev) {
        e->fresh = 0;
    } else if (e->fresh && e->nnodes) {
        int k = fresh_focus(e, 0);
        if (k >= 0 && drawn_key(e, uit_str(e, NODE(k)->key), fid)) {
            moy_ui_api_focus_ahead(c, span_of(fid, strlen(fid)));
            moved = 1;
            e->fresh = 0;
        }
    }
    int asked = 0;                      // ui.focus found its node: the app's word on where focus goes
    if (e->want) {
        const char *key = e->want;
        if (id_find(e->prev, e->nprev, key))
            snprintf(fid, sizeof fid, "%s", key);
        else if (dialog_button(e, key, fid))
            ;
        else if (!id_in(e, key, fid)) {
            if (drawn_key(e, key, fid))
                strcpy(ahead, fid);
            else
                fid[0] = 0;
        }
        if (fid[0]) {
            focus_to(c, fid);
            moved = asked = 1;
            uit_want_focus(e, NULL);
        }
    }
    if (fresh_prev) {
        for (int i = 0; i < e->nprev; i++) {
            const uit_id_t *I = &e->prev[i];
            if (I->gen == e->gen && NODE(I->node)->focus >= 0 &&
                uit_cond_eval(e, NODE(I->node)->focus, uit_model_of(e, I->node), I->row)) {
                focus_to(c, I->id);
                moved = 1;
                break;
            }
        }
    }
    for (int k = 0; k < e->nnodes; k++) {
        const uit_node_t *L = NODE(k);
        if (!UIT_IS_LIST(L->kind) || L->cur < 0 || !drawn_now(e, k))
            continue;               // (a list this frame hides moves focus when it shows)
        uit_slot_t *S = &e->slots[L->cur];
        const char *v = S->s ? S->s : "";
        if (S->sync_set && S->sync && !strcmp(S->sync, v))
            continue;
        // a written cur moves the focus onto its row, but where the app asked for a focus of its own
        if (!asked) {
            if (!id_in(e, v, fid) && !(*v && row_stop_id(e, k, v, S->sn, fid)))
                continue;
            focus_to(c, fid);
            moved = 1;
        }
        UIT_FREE(S->sync);
        S->sync = UIT_MALLOC(S->sn + 1);
        if (S->sync)
            memcpy(S->sync, v, S->sn + 1);
        S->sync_set = 1;
    }
    return moved;
}

static void focus_after(uit_t *e, moy_ui_ctx_t *c, int moved, const char *ahead, const uit_id_t *last)
{
    if (ahead[0] && !id_find(e->ids, e->nids, ahead))
        uit_want_focus(e, ahead);
    char f[UIT_ID_MAX + 1];
    int fl = moy_ui_api_focus(c, span_of(NULL, 0), f, sizeof f);
    const uit_id_t *I = fl >= 0 ? id_find(e->ids, e->nids, f) : NULL;
    e->has_focused = I != NULL;
    if (I)
        e->focused = *I;
    snprintf(e->focus_key, sizeof e->focus_key, "%s", fl > 0 ? f : "");
    if (last && last->kind == UIT_FIELD && last->gen == e->gen &&
        (!I || I->node != last->node || I->gen != last->gen))
        commit_field(e, last->node);    // focus left a commit field: its draft is written
    if (!I || moved)
        return;
    int m = uit_model_of(e, I->node);
    int lst = -1;
    for (int k = I->node; k >= 0 && k != (int)UIT_NONE; k = NODE(k)->parent)
        if (UIT_IS_LIST(NODE(k)->kind)) {
            lst = k;
            break;
        }
    if (lst < 0 || NODE(lst)->cur < 0)
        return;
    const char *v = I->row >= 0 ? row_key(e, m, I->row) : "";
    const uit_slot_t *S = &e->slots[NODE(lst)->cur];
    if (strlen(v) != S->sn || memcmp(v, S->s ? S->s : "", S->sn)) {
        // focus arriving from outside the list writes its cur and is no move of it
        int from = -1;
        if (last && last->gen == e->gen && last->row >= 0)
            for (int k = last->node; k >= 0 && k != (int)UIT_NONE; k = NODE(k)->parent)
                if (UIT_IS_LIST(NODE(k)->kind)) {
                    from = k;
                    break;
                }
        uit_cur_moved(e, lst, v, strlen(v), "focus", from == lst);
    }
}

// -- the frame ----------------------------------------------------------------------------

// Every state's version, the builds and the drafts' edits: moves whenever anything a frame reads may have.
// -- the placed layout ------------------------------------------------------------------------
//
// One rule, the engine's for every placed surface (the Editor's pages; the window manager's
// bar, dock and chrome by the same rule): a container gives each shown child a rect along its
// axis, a child fixed (its kind's height, `fixed_h`) or a fill (the fills share what the fixed
// leave); a text editor takes whole lines and hands the rest to the child under it; a row lent
// to a site takes none; popovers and dialogs draw last, over it. A flowing page is the case
// whose one fill is the page itself, which the toolkit stacks (`walk`); a placed page
// (uit_set_placed) is stacked by this rule from its root. The pass that draws a child records
// its rect (`uit_rect`); `uit_place` runs the pass with nothing drawn.

enum { PLACE_KIDS = 48 };

void uit_set_placed(uit_t *e, int on)
{
    e->placed = (uint8_t)(on != 0);
}

void uit_set_ground(uit_t *e, int x, int y, int w, int h)
{
    e->ground[0] = (int16_t)x, e->ground[1] = (int16_t)y, e->ground[2] = (int16_t)w, e->ground[3] = (int16_t)h;
}

void uit_set_band_extra(uit_t *e, const char *s, size_t n)
{
    if (n > sizeof e->band_extra)
        n = 0;
    memcpy(e->band_extra, s, n);
    e->nband_extra = (uint8_t)n;
}

static int32_t fdiv(int32_t a, int32_t b)
{
    int32_t q = a / b;
    return (a % b != 0 && (a < 0) != (b < 0)) ? q - 1 : q;
}

// The rect table made ready for a pass: every node unplaced.
static int rects_ready(uit_t *e)
{
    if (e->crects < e->nnodes) {
        int16_t *r = UIT_REALLOC(e->rects, (size_t)e->nnodes * 4 * sizeof *r);
        if (!r)
            return 0;
        e->rects = r, e->crects = e->nnodes;
    }
    for (int i = 0; i < e->nnodes; i++)
        e->rects[4 * i + 2] = -1;
    e->nmcells = 0;
    return 1;
}

static void put_rect(uit_t *e, int k, const int32_t r[4])
{
    if (k < e->crects) {
        int16_t *p = e->rects + 4 * k;
        p[0] = (int16_t)r[0], p[1] = (int16_t)r[1], p[2] = (int16_t)r[2], p[3] = (int16_t)r[3];
    }
}

int uit_rect(const uit_t *e, const char *key, int32_t out[4])
{
    const char *sl = strchr(key, '/');
    for (int i = 0; sl && i < e->nmcells; i++) {     // ROWKEY/KEY: a model row's cell
        const uit_mc_t *m = &e->mcells[i];
        const char *rk = uit_cell((uit_t *)e, m->model, m->row, e->slots[m->model].key);
        if (strlen(rk) == (size_t)(sl - key) && !memcmp(rk, key, (size_t)(sl - key)) &&
            !strcmp(uit_str(e, e->nodes[m->node].key), sl + 1)) {
            out[0] = m->r[0], out[1] = m->r[1], out[2] = m->r[2], out[3] = m->r[3];
            return 1;
        }
    }
    for (int k = (e->crects < e->nnodes ? e->crects : e->nnodes) - 1; k >= 0; k--) {
        const int16_t *p = e->rects + 4 * k;
        if (p[2] >= 0 && !strcmp(uit_str(e, e->nodes[k].key), key)) {
            out[0] = p[0], out[1] = p[1], out[2] = p[2], out[3] = p[3];
            return 1;
        }
    }
    return 0;
}

// A placed row's height: 48 on the desk, 22 at the scale on a handheld.
static int32_t h_row(const uit_t *e)
{
    return (e->flags & UIT_F_DESK) ? 48 : 22 * e->fs;
}

// Whether font `f` is a version 2 face (moy_text.h: its line holds its leading).
static int font_v2(uint32_t f)
{
    moy_font_info_t i;
    return f && moy_font_info(f, &i) && i.first == 0;
}

static uint32_t role_font(int role, moy_font_info_t *fi)
{
    return moy_ui_font(moy_ui_cart_on(), role, fi);
}

// A text editor's line pitch: a version 2 mono face's glyph box, else its line and a lead.
static int32_t pitch(const uit_t *e)
{
    moy_font_info_t fi, gi;
    uint32_t f = role_font(MOY_UI_FONT_MONO, &fi);
    int v2 = f && moy_font_info(f, &gi) && gi.first == 0;
    return (v2 ? gi.h : fi.line + 2) * e->fs;
}

// A status band's height: 20 under a version 2 `ui` face, 12 under petme128, never under the
// face's line and a pixel above and below.
static int32_t status_h(const uit_t *e)
{
    moy_font_info_t fi;
    uint32_t f = role_font(MOY_UI_FONT_UI, &fi);
    int32_t least = font_v2(f) ? 20 : 12;
    return (least > fi.line + 2 ? least : fi.line + 2) * e->fs;
}

// A child's height along a stack: > 0 fixed, -1 a fill, 0 none (a row lent to a site).
static int32_t fixed_h(uit_t *e, int k)
{
    const uit_node_t *N = NODE(k);
    switch (N->kind) {
    case UIT_CANVAS:
        return canvas_h(e, k) ? canvas_h(e, k) * ((e->flags & UIT_F_DESK) ? 1 : e->fs) : -1;
    case UIT_SWITCH:
    case UIT_CASE:
    case UIT_PANES:
    case UIT_PANE:
    case UIT_TEXT_EDITOR:
    case UIT_SLOT:
    case UIT_PANEL:
    case UIT_SCROLL:                    // a scroll region: what its stack leaves, its rows scrolled in it
    case UIT_TABLE:                     // a table: what its stack leaves, its rows scrolled in it
    case UIT_TEXT_VIEW:                 // a text view: what its stack leaves, its lines scrolled in it
        return -1;
    case UIT_GRID:                      // a grid: its h=, else what its stack leaves
        return N->t_aux >= 0 ? len_of(e, N->t_aux, -1, -1, 0) : -1;
    case UIT_STATUS:
        return status_h(e);
    case UIT_ROWS:                      // a rows list: what its stack leaves, its rows scrolled in it
    case UIT_HINTS:                     // a hints row: a fill of its stack
    case UIT_EMPTY:                     // an empty: what its stack leaves, its words in it
        return -1;
    case UIT_RULE:                      // a rule across: its line
        return (e->flags & UIT_F_DESK) ? 1 : e->fs;
    case UIT_NOTE:                      // a note in a foot: as tall as its lines (uit_frame measures it)
        return N->btn ? N->btn : h_row(e);
    case UIT_TOOLS:
        if ((N->lit & TL_LEND) || (N->parent != UIT_NONE && NODE(N->parent)->kind == UIT_PANE &&
                                   (e->flags & UIT_F_DESK)))
            return 0;
        break;
    case UIT_LABEL:
        if ((N->nbtn & LT_LINES) || (N->nbtn & LT_WRAP) == LT_WORD) {
            moy_font_info_t fi;
            role_font(MOY_UI_FONT_UI, &fi);
            return (((N->nbtn & LT_LINES) ? N->btn : 2) * (fi.line + 2) + 6) * e->fs;
        }
        break;
    case UIT_ROW: {
        int st = 0, field = 0;
        if (N->lit & RW_GROW)
            return -1;                  // a growing row: a fill of its stack
        KIDS(k, g) {
            int gk = NODE(g)->kind;
            if (gk == UIT_CASE || gk == UIT_SWITCH || gk == UIT_PANEL || gk == UIT_GROUP)
                return -1;              // a row of regions or columns: the rule turned, a fill of its stack
            st |= gk == UIT_STATUS;
            field |= gk == UIT_FIELD;
        }
        int tap = 0;                    // under touch, a button a finger takes beside it
        KIDS(k, g)
        tap |= e->input == UIT_IN_TOUCH && NODE(g)->kind == UIT_BUTTON && placed_shown(e, g, -1, -1);
        if (st && !field && !tap)
            return status_h(e);         // a status line's
        int32_t hh = h_row(e);
        KIDS(k, g)                      // a row as tall as its tallest canvas of a fixed h=
        if (NODE(g)->kind == UIT_CANVAS && fixed_h(e, g) > hh)
            hh = fixed_h(e, g);
        return hh;
    }
    }
    return h_row(e);
}

// Shown in a placed container: its condition holds and its action is on (or greys).
static int placed_shown(uit_t *e, int k, int model, int row)
{
    const uit_node_t *N = NODE(k);
    return uit_shown(e, k, model, row) &&
           (N->act < 0 || uit_act_can(e, N->act, model, row) || e->acts[N->act].off == 2);
}

static const char SEP[] = " \xc2\xb7 ";           // a status template's fields are split at it

// The width of `n` bytes in font `f` at `scale`.
static int32_t text_px(uint32_t f, const char *p, size_t n, int scale)
{
    return moy_text_width(f, (const uint8_t *)p, n, scale);
}

static void place_at(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                     const int32_t r[4]);
static void pn_draw(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                    const int32_t r[4]);

// `n` bytes onto a line of text (its NUL kept past its length).
static void line_put(uit_buf_t *b, const char *p, size_t n)
{
    if (uit_buf_put(b, p, n) >= 0)
        b->n--;
}

// A cell's height down a column from a model (`stack`): a button its w= (its length along the
// list, as along a row from a model), else a square of the column's width `w`; a label its line
// and its pads; the rest as down any stack.
static int32_t model_col_h(uit_t *e, int k, int model, int row, int32_t w)
{
    const uit_node_t *N = NODE(k);
    if (N->kind == UIT_BUTTON)
        return N->t_value >= 0 ? natural(e, k, model, row, w) : w;
    if (N->kind == UIT_LABEL) {
        moy_font_info_t fi;
        role_font(MOY_UI_FONT_UI, &fi);
        return (fi.line + 8) * e->fs;
    }
    return fixed_h(e, k);
}

// A column from a model's cells (rows `g` of dir="col"): each row's body's children on that row,
// a column from a model among them its own cells in their place.
static void col_kids(uit_t *e, int g, int32_t w, int16_t *kids, int16_t *km, int16_t *kr, int32_t *hs, int *n)
{
    int m = NODE(g)->slot;
    for (int i = 0, y; i < e->slots[m].nrows; i++)
        if ((y = uit_row_body(e, g, i)) >= 0)
            KIDS(y, b) {
                if (*n == PLACE_KIDS || !placed_shown(e, b, m, i))
                    continue;
                if (NODE(b)->kind == UIT_ROWS && (NODE(b)->lit & RS_COL)) {
                    col_kids(e, b, w, kids, km, kr, hs, n);
                    continue;
                }
                kids[*n] = (int16_t)b, km[*n] = (int16_t)m, kr[*n] = (int16_t)i;
                hs[(*n)++] = model_col_h(e, b, m, i, w);
            }
}

// The shown children of `k` down `r`: fixed rows their height, the fills sharing the rest; a
// `rows` among them of dir="col" a cell per child of each row's body, on that row (`model_col_h`).
static void stack(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                  const int32_t r[4])
{
    int16_t kids[PLACE_KIDS], km[PLACE_KIDS], kr[PLACE_KIDS];
    int32_t hs[PLACE_KIDS], fixed = 0;
    int n = 0, fills = 0;
    int body = NODE(k)->kind == UIT_PANE;      // a pane's body: its tools are its header's
    KIDS(k, g) {
        int kind = NODE(g)->kind;
        if (n == PLACE_KIDS || kind == UIT_POPOVER || kind == UIT_DIALOG || (body && kind == UIT_TOOLS) ||
            !placed_shown(e, g, model, row))
            continue;
        if (kind == UIT_ROWS && (NODE(g)->lit & RS_COL)) {
            int was = n;
            col_kids(e, g, r[2], kids, km, kr, hs, &n);
            for (int i = was; i < n; i++)
                if (hs[i] > 0)
                    fixed += hs[i];
                else if (hs[i] < 0)
                    fills++;
            continue;
        }
        kids[n] = (int16_t)g, km[n] = (int16_t)model, kr[n] = (int16_t)row;
        hs[n] = fixed_h(e, g);
        if (hs[n] > 0)
            fixed += hs[n];
        else if (hs[n] < 0)
            fills++;
        n++;
    }
    int32_t room = r[3] - fixed > 0 ? r[3] - fixed : 0, spare = 0, y = r[1];
    if (!fills)
        fills = 1;
    for (int i = 0; i < n; i++) {
        int32_t kh = hs[i];
        if (!kh)
            continue;
        kh = (kh < 0 ? room / fills : kh) + spare;
        spare = 0;
        if (NODE(kids[i])->kind == UIT_TEXT_EDITOR && i < n - 1) {
            int32_t p = pitch(e);
            spare = p > 0 ? kh % p : 0;     // whole lines; the child under it takes the rest
            kh -= spare;
        }
        int32_t cell[4] = {r[0], y, r[2], kh};
        if (km[i] != model) {
            const uit_node_t *K = NODE(kids[i]);
            if (K->kind == UIT_BUTTON && K->lit == MOY_UI_BUTTON_BAR && !(K->btn & BT_ALONE)) {
                // a labelled bar item down a column: its own width, centred across
                int32_t nw = bar_item_w(e, kids[i], km[i], kr[i], kh);
                if (nw > 0 && nw < cell[2])
                    cell[0] += (cell[2] - nw) / 2, cell[2] = nw;
            }
            put_cell(e, kids[i], km[i], kr[i], cell);   // a column's cell: its row's (`uit_rect`)
        }
        place_at(e, c, s, kids[i], km[i], kr[i], cell);
        y += kh;
    }
    if (e->placing)
        return;
    KIDS(k, g) {
        int kind = NODE(g)->kind;
        if ((kind == UIT_POPOVER || kind == UIT_DIALOG) && e->nlate < (int)(sizeof e->late / sizeof *e->late) &&
            placed_shown(e, g, model, row))
            e->late[e->nlate++] = (int16_t)g;       // over every child, after the page
    }
}

// A status line: its first field always, the others while they fit, joined by the `ui`
// face's separator, its words on the page's text column (the text view's inset).
static void draw_status(uit_t *e, const moy_ui_sink_t *s, int k, int model, int row, const int32_t r[4])
{
    int mn, fs = e->fs;
    int pad = moy_ui_metrics(MOY_UI_K_STATUS, &mn)[1] * fs;
    uint32_t n, at = text(e, k, 0, model, row, &n);
    moy_font_info_t fi;
    uint32_t f = role_font(MOY_UI_FONT_UI, &fi);
    const char *p = e->scratch.p + at, *end = p + n;
    const char *sep = font_v2(f) ? "  \xc2\xb7  " : " - ";
    size_t sl = strlen(sep), ql = sizeof SEP - 1;
    uit_buf_t line = {0};
    const char *cut = p;
    while (cut + ql <= end && memcmp(cut, SEP, ql))
        cut++;
    if (cut + ql > end)
        cut = end;
    line_put(&line, p, (size_t)(cut - p));
    int32_t room = r[2] - 2 * pad;
    while (cut < end) {
        const char *f0 = cut + ql, *f1 = f0;
        while (f1 + ql <= end && memcmp(f1, SEP, ql))
            f1++;
        if (f1 + ql > end)
            f1 = end;
        size_t was = line.n;
        line_put(&line, sep, sl);
        line_put(&line, f0, (size_t)(f1 - f0));
        if (text_px(f, line.p, line.n, fs) > room) {
            line.n = was;
            break;
        }
        cut = f1;
    }
    int32_t x = r[0], tx = x + 8 * fs - pad;
    moy_ui_box_t b = {(int16_t)x, (int16_t)r[1], (int16_t)r[2], (int16_t)r[3]};
    if (tx > x) {
        moy_ui_box_t g = {(int16_t)x, (int16_t)r[1], (int16_t)(tx - x), (int16_t)r[3]};
        moy_ui_status(s, g, (const uint8_t *)"", 0, 0, s->fs);
        b.x = (int16_t)tx, b.w = (int16_t)(r[2] - (tx - x));
    }
    moy_ui_status(s, b, (const uint8_t *)(line.p ? line.p : ""), line.n, 1, s->fs);
    uit_buf_free(&line);
}

// A placed row's unit: the host's (`uit_set_unit`), else 1 on a desk and the font scale else.
static int32_t row_unit(const uit_t *e)
{
    return e->unit > 0 ? e->unit : (e->flags & UIT_F_DESK) ? 1 : e->fs;
}

// A length prop (template `t`) in pixels: a literal in the row's unit, an int state as the host
// measured it; `dflt` (pixels) where none is given.
static int32_t len_of(uit_t *e, int t, int model, int row, int32_t dflt)
{
    if (t < 0)
        return dflt;
    int32_t v = int_of(e, t, model, row, 0);
    return e->tmpls[t].lit ? v * row_unit(e) : v;
}

// A placed row's gap between its cells, and a column's between its rows: 2 at 1x.
static int32_t row_gap(const uit_t *e)
{
    return 2 * space_unit(e);
}


// A row's shown cells in order, each with the list row it draws on (`km`, `kr`): a `rows` among
// them a cell per row of its model, its kids shown on that row (a row from a model).
static int lender(uit_t *e, int k, const char *site);

static int row_kids(uit_t *e, int k, int model, int row, int16_t *kids, int16_t *km, int16_t *kr, int *st,
                    int *st_shown)
{
    int n = 0;
    KIDS(k, g) {
        int kind = NODE(g)->kind;
        *st |= kind == UIT_STATUS;
        if (n == PLACE_KIDS || !placed_shown(e, g, model, row))
            continue;
        if (kind == UIT_ROWS) {
            int m = NODE(g)->slot;
            for (int r = 0, y; r < e->slots[m].nrows; r++)
                if ((y = uit_row_body(e, g, r)) >= 0)
                    KIDS(y, b)
                    if (n < PLACE_KIDS && placed_shown(e, b, m, r))
                    kids[n] = (int16_t)b, km[n] = (int16_t)m, kr[n++] = (int16_t)r;
            continue;
        }
        if (kind == UIT_LENT) {         // a lent site: the shown lender's cells, in its place
            int t = lender(e, 0, uit_str(e, NODE(g)->key));
            if (t >= 0)
                KIDS(t, b)
                if (n < PLACE_KIDS && placed_shown(e, b, model, row))
                    kids[n] = (int16_t)b, km[n] = (int16_t)model, kr[n++] = (int16_t)row;
            continue;
        }
        *st_shown |= kind == UIT_STATUS;
        kids[n] = (int16_t)g, km[n] = (int16_t)model, kr[n++] = (int16_t)row;
    }
    return n;
}

// The width row `k`'s cells take at their natural widths, its gaps and pads: on a placed page
// `row_cells`'s, 0 where one of them is a fill; else `draw_flow_row`'s, a fill taking none. With
// `least`, each labelled button with an icon as its icon alone (`icons_alone`), and a flow row's
// gaps closed.
static int32_t row_need(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                        int32_t h, int least)
{
    int16_t kids[PLACE_KIDS], km[PLACE_KIDS], kr[PLACE_KIDS];
    int st = 0, st_shown = 0, desk = (e->flags & UIT_F_DESK) != 0;
    int n = row_kids(e, k, model, row, kids, km, kr, &st, &st_shown);
    const uit_node_t *R = NODE(k);
    int32_t w = 0, x;
    for (int i = 0; i < n; i++) {
        int kind = NODE(kids[i])->kind;
        if (kind == UIT_RULE)
            x = desk ? 1 : e->fs;
        else if (!e->placed && kind == UIT_BUTTON)
            x = button_w(e, c, s, kids[i], km[i], kr[i]);
        else if ((x = natural(e, kids[i], km[i], kr[i], h)) < 0 && e->placed)
            return 0;
        if (least && kind == UIT_BUTTON && x > ALONE_W(e) && !(NODE(kids[i])->btn & (BT_ALONE | BT_GROW))
            && btn_icon(e, kids[i], km[i], kr[i]))
            x = ALONE_W(e);
        w += x > 0 ? x : 0;
    }
    int32_t gap = space_of(e, R->t_value, model, row, e->placed ? 2 : 6);
    gap = least && !e->placed ? 0 : gap;
    int32_t pad = space_of(e, R->t_aux, model, row, 0);
    return n ? w + gap * (n - 1) + 2 * pad : 0;
}

// A model row's cell placed: kept for `uit_rect`'s ROWKEY/KEY (its node's own rect is one cell's).
static void put_cell(uit_t *e, int k, int model, int row, const int32_t r[4])
{
    if (!e->mcells && !(e->mcells = UIT_MALLOC(UIT_MCELLS * sizeof *e->mcells)))
        return;
    if (e->nmcells < UIT_MCELLS) {
        uit_mc_t *m = &e->mcells[e->nmcells++];
        m->node = (int16_t)k, m->model = (int16_t)model, m->row = (int16_t)row;
        m->r[0] = (int16_t)r[0], m->r[1] = (int16_t)r[1], m->r[2] = (int16_t)r[2], m->r[3] = (int16_t)r[3];
    }
}

// A bar item's width in a box `h` high: its icon's ink and its label (moy_ui_bar_item_w).
static int32_t bar_item_w(uit_t *e, int k, int model, int row, int32_t h)
{
    const uit_node_t *N = NODE(k);
    const char *ic = N->act >= 0 ? uit_str(e, e->acts[N->act].icon) : "";
    uint32_t in = strlen(ic), ia = 0, n = 0, at = 0;
    int slot = -1, glyph = -1;
    if (N->t_icon >= 0) {
        ia = uit_tmpl_render(e, N->t_icon, model, row, &in);
        ic = e->scratch.p + ia;
    }
    if (in) {
        slot = moy_ui_icon_slot((const uint8_t *)ic, in);
        glyph = moy_ui_icon_glyph((const uint8_t *)ic, in);
    }
    if (!((N->btn & BT_ALONE) && (N->t_icon >= 0 || in)))
        at = text(e, k, 0, model, row, &n);
    return moy_ui_bar_item_w(slot, glyph, sspan(e, at, n), h, e->fs);
}

// A row cell's natural width, or -1 where it grows (`_natural`).
static int32_t natural(uit_t *e, int k, int model, int row, int32_t h)
{
    const uit_node_t *N = NODE(k);
    uint32_t n, at;
    if (N->kind == UIT_BUTTON) {
        if (N->btn & BT_GROW)
            return -1;                  // a growing button: a fill
        if (N->t_value >= 0)            // its w=: a literal in units, a template's size (`size_of`)
            return e->tmpls[N->t_value].lit ? len_of(e, N->t_value, model, row, 0)
                                            : size_of(e, int_of(e, N->t_value, model, row, 0));
        if (N->lit == MOY_UI_BUTTON_BAR)
            return bar_item_w(e, k, model, row, h);
        if (N->t_icon >= 0 && (N->btn & BT_ALONE))
            return h;
        // its label in the face and at the scale it draws in, and its plate's pads and icon
        moy_font_info_t fi;
        at = text(e, k, 0, model, row, &n);
        return text_px(role_font(MOY_UI_FONT_UI, &fi), e->scratch.p + at, n, e->fs) + 28 * e->fs;
    }
    if (N->kind == UIT_STATUS) {
        at = text(e, k, 0, model, row, &n);
        const char *p = e->scratch.p + at;
        size_t ql = sizeof SEP - 1;
        for (size_t i = 0; i + ql <= n; i++)
            if (!memcmp(p + i, SEP, ql))
                return -1;              // a line of fields grows
        moy_font_info_t fi;
        int mn, pad = moy_ui_metrics(MOY_UI_K_STATUS, &mn)[1] * e->fs;
        return text_px(role_font(MOY_UI_FONT_UI, &fi), p, n, e->fs) + 2 * pad + 2;
    }
    if (N->kind == UIT_SLIDER && (N->lit & NL_BLOCKS)) {
        // a meter with no label: 10 units a step and 12 more (its blocks' margins); labelled, a fill
        at = text(e, k, 0, model, row, &n);
        if (!n) {
            int32_t lo = int_of(e, N->t_value, model, row, 0), hi = int_of(e, N->t_aux, model, row, 0);
            return ((hi > lo ? hi - lo : 1) * 10 + 12) * row_unit(e);
        }
    }
    if (N->kind == UIT_STEPPER) {
        if (N->btn & BT_GROW)
            return -1;                  // a growing stepper: a fill
        at = text(e, k, 1, model, row, &n);
        return moy_ui_stepper_w(sspan(e, at, n), h, e->fs);
    }
    if (N->kind == UIT_GRID && N->t_value >= 0)
        return len_of(e, N->t_value, model, row, 0);     // a grid's w=
    if (N->kind == UIT_LABEL && (N->nbtn & LT_TEXT)) {
        // size="text": its text's width in the ui face (`label_rows_m` draws it in that face, as
        // a text block from its cell's left), room after it, and where it shows an icon, its box
        // and gap (`moy_ui_text_block`'s)
        moy_font_info_t fi;
        int32_t ic = 0;
        if (N->t_icon >= 0) {
            uit_tmpl_render(e, N->t_icon, model, row, &n);
            ic = n ? (16 + ((e->flags & UIT_F_DESK) ? 6 : 4)) * e->fs : 0;
        }
        at = text(e, k, 0, model, row, &n);
        return text_px(role_font(MOY_UI_FONT_UI, &fi), e->scratch.p + at, n, e->fs) + 8 * e->fs + ic;
    }
    if (N->kind == UIT_CANVAS && N->t_value >= 0 && !(N->lit & CV_GROW)) {
        if (e->tmpls[N->t_value].lit && !int_of(e, N->t_value, model, row, 0))
            return -1;                  // w=0 grows
        return len_of(e, N->t_value, model, row, 0);     // a fixed cell along x, as h= down
    }
    if (N->kind == UIT_ROW) {
        // a row in a row: its cells' widths and gaps where none grows; one with nothing shown
        // a spacer; a grow= row a fill
        if (N->lit & RW_GROW)
            return -1;
        int16_t kids[PLACE_KIDS], km[PLACE_KIDS], kr[PLACE_KIDS];
        int st = 0, sts = 0, nk = row_kids(e, k, model, row, kids, km, kr, &st, &sts);
        int32_t sum = 0;
        if (!nk)
            return -1;
        for (int i = 0; i < nk; i++) {
            int32_t v = natural(e, kids[i], km[i], kr[i], h);
            if (v < 0)
                return -1;
            sum += v;
        }
        return sum + space_of(e, N->t_value, model, row, 2) * (nk > 1 ? nk - 1 : 0) +
               2 * space_of(e, N->t_aux, model, row, 0);
    }
    if (N->kind == UIT_LABEL && N->t_icon >= 0) {
        text(e, k, 0, model, row, &n);
        if (!n)
            return 22 * ((e->flags & UIT_F_DESK) ? 1 : e->fs);   // an icon alone: its box and a gap
    }
    if (N->kind == UIT_RULE)
        return 9 * row_unit(e);         // a rule in a row: its line and a margin either side
    return -1;
}

// A row of fixed cells wider than its `room`: its model's cells (`km` not the row's `model`) cut
// to one width, the widest first, never under the row's height `h`; those that still do not fit
// dropped from the end (`_fit_cells`). Answers the cells left.
static int fit_cells(int16_t *kids, int16_t *km, int16_t *kr, int32_t *nat, int model, int n, int32_t room,
                     int32_t gap, int32_t h)
{
    int32_t sum = gap * (n > 1 ? n - 1 : 0), most = 0;
    for (int i = 0; i < n; i++) {
        sum += nat[i];
        if (km[i] != model && nat[i] > most)
            most = nat[i];
    }
    if (sum <= room || !most)
        return n;
    int32_t lo = h < most ? h : most, hi = most;    // the widest cap that fits, else the floor
    while (lo < hi) {
        int32_t cap = lo + (hi - lo + 1) / 2, t = gap * (n > 1 ? n - 1 : 0);
        for (int i = 0; i < n; i++)
            t += km[i] != model && nat[i] > cap ? cap : nat[i];
        if (t <= room)
            lo = cap;
        else
            hi = cap - 1;
    }
    sum = gap * (n > 1 ? n - 1 : 0);
    for (int i = 0; i < n; i++) {
        if (km[i] != model && nat[i] > lo)
            nat[i] = lo;
        sum += nat[i];
    }
    for (int i = n - 1; i >= 0 && sum > room; i--)
        if (km[i] != model) {
            sum -= nat[i] + (n > 1 ? gap : 0);
            for (int j = i; j < n - 1; j++)
                kids[j] = kids[j + 1], km[j] = km[j + 1], kr[j] = kr[j + 1], nat[j] = nat[j + 1];
            n--;
        }
    return n;
}

// Cells i0..i1 their widths: a fixed one its own, the fills their basis and an even share of what
// `room` leaves, the last of them the remainder.
static void row_share(const int32_t *nat, const int32_t *base, int32_t *ws, int i0, int i1, int32_t room)
{
    int grow = 0, last = -1;
    for (int i = i0; i < i1; i++)
        if (nat[i] < 0)
            grow++, last = i, room -= base[i];
        else
            room -= nat[i];
    int32_t each = fdiv(room, grow > 1 ? grow : 1);
    for (int i = i0; i < i1; i++) {
        int32_t v = nat[i] >= 0 ? nat[i] : base[i] + each + (i == last ? room - each * (grow > 1 ? grow : 1) : 0);
        ws[i] = v < 0 ? 0 : v;
    }
}

// A row's cells across it: each its natural width, the growing ones sharing the rest, inside
// its pad= and gap= apart; a mid= row centred on it, each side's fills sharing that side's room.
// Whether row `k` holds a canvas of a fixed h= taller than a line (its height `fixed_h`'s).
static int canvas_tall(uit_t *e, int k)
{
    KIDS(k, g)
    if (NODE(g)->kind == UIT_CANVAS && fixed_h(e, g) > h_row(e))
        return 1;
    return 0;
}

static void row_cells(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                      const int32_t r[4])
{
    int16_t kids[PLACE_KIDS], km[PLACE_KIDS], kr[PLACE_KIDS];
    int32_t nat[PLACE_KIDS], ws[PLACE_KIDS], base[PLACE_KIDS];
    int st = 0, st_shown = 0, mid = -1, grow = 0;
    int n = row_kids(e, k, model, row, kids, km, kr, &st, &st_shown);
    const uit_node_t *R = NODE(k);
    if (st && !st_shown && !e->placing) {
        moy_ui_box_t b = {(int16_t)r[0], (int16_t)r[1], (int16_t)r[2], (int16_t)r[3]};
        moy_ui_api_status_band(c, s, b);        // a status row's band, its line hidden
    }
    for (int i = 0; i < n; i++) {
        nat[i] = natural(e, kids[i], km[i], kr[i], r[3]);
        grow += nat[i] < 0;
        if (mid < 0 && NODE(kids[i])->kind == UIT_ROW && (NODE(kids[i])->lit & RW_MID))
            mid = i;
    }
    if (!grow)
        for (int i = 0; i < n; i++)
            if (NODE(kids[i])->kind == UIT_TABS) {
                nat[i] = -1;            // a row of fixed cells: its tabs take the rest
                break;
            }
    for (int i = 0; i < n; i++)         // a fill's basis: a growing canvas's w=, its share over it
        base[i] = nat[i] < 0 && NODE(kids[i])->kind == UIT_CANVAS ? len_of(e, NODE(kids[i])->t_value, model, row, 0) : 0;
    int32_t gap = R->kind == UIT_ROW ? space_of(e, R->t_value, model, row, 2) : row_gap(e);
    int32_t pad = R->kind == UIT_ROW ? space_of(e, R->t_aux, model, row, 0) : 0;
    int32_t x0 = r[0] + pad, x1 = r[0] + r[2] - pad, ms = 0, b = 0;
    int32_t sum = gap * (n > 1 ? n - 1 : 0);
    for (int i = 0; i < n; i++)
        sum += nat[i] >= 0 ? nat[i] : base[i];
    icons_alone(e, kids, km, kr, model, row, nat, n, sum, x1 - x0);
    int fills = 0;
    for (int i = 0; i < n; i++)
        fills += nat[i] < 0;
    if (!fills && mid < 0)
        n = fit_cells(kids, km, kr, nat, model, n, x1 - x0, gap, r[3]);
    if (mid < 0)
        row_share(nat, base, ws, 0, n, x1 - x0 - gap * (n > 1 ? n - 1 : 0));
    else {
        int32_t a = x0 + gap * mid, cx = r[0] + fdiv(r[2], 2);
        b = x1 - gap * (n - 1 - mid);
        for (int i = 0; i < n; i++)
            if (i != mid) {
                int32_t v = nat[i] >= 0 ? nat[i] : base[i];
                if (i < mid)
                    a += v;
                else
                    b -= v;
            }
        int32_t half = cx - a < b - cx ? cx - a : b - cx;
        if (half < 0)
            half = 0;
        if (nat[mid] < 0 || nat[mid] > 2 * half)
            ms = cx - half, ws[mid] = 2 * half;     // a mid of fills, or one wider than it: the widest
                                                    // span centred that clears both (its cells cut to it)
        else
            ms = r[0] + fdiv(r[2] - nat[mid], 2), ws[mid] = nat[mid];
        row_share(nat, base, ws, 0, mid, ms - x0 - gap * mid);
        row_share(nat, base, ws, mid + 1, n, x1 - (ms + ws[mid]) - gap * (n - 1 - mid));
    }
    int32_t x = x0;
    for (int i = 0; i < n; i++) {
        int g = kids[i];
        if (i == mid)
            x = ms;
        else if (mid >= 0 && i == mid + 1) {
            x = x1 - gap * (n - 2 - mid);
            for (int j = mid + 1; j < n; j++)
                x -= ws[j];
        }
        int32_t kw = ws[i];
        int32_t cell[4] = {x, r[1] + 2, kw, r[3] - 4};
        int gk = NODE(g)->kind;
        if (gk == UIT_STATUS || gk == UIT_CASE || gk == UIT_SWITCH || gk == UIT_PANEL || gk == UIT_CANVAS ||
            gk == UIT_ROW || gk == UIT_STEPPER || gk == UIT_TABS ||
            (gk == UIT_BUTTON && NODE(g)->lit == MOY_UI_BUTTON_BAR))
            cell[1] = r[1], cell[3] = r[3];     // a band, a region, a bar item, a stepper, tabs: the row's height
        else if (gk == UIT_BUTTON && (NODE(g)->btn & BT_ALONE) && NODE(g)->t_value >= 0 && kw < cell[3])
            cell[1] += (cell[3] - kw) / 2, cell[3] = kw;    // an icon of its own w=: square, centred down
        if (km[i] != model)
            put_cell(e, g, km[i], kr[i], cell);
        if (gk == UIT_RULE) {
            // a line down the row between its neighbours, in from its ends
            int32_t u = row_unit(e), line = (e->flags & UIT_F_DESK) ? 1 : e->fs, in = 4 * u;
            put_rect(e, g, cell);
            if (!e->placing && r[3] > 2 * in)
                fill_token(s, x + (kw - line) / 2, r[1] + in, line, r[3] - 2 * in, MOY_UI_T_BORDER);
        } else if (e->placing || gk == UIT_ROW)
            place_at(e, c, s, g, km[i], kr[i], cell);   // a placement records the cells, drawing none
        else if (gk == UIT_BUTTON) {
            int32_t hh = h_row(e);      // a line tall, centred in a row a canvas made taller
            if (cell[3] > hh && canvas_tall(e, k)) {
                cell[1] += (cell[3] - hh) / 2;
                cell[3] = hh;
            }
            put_rect(e, g, cell);
            moy_ui_api_at(c, cell[0], cell[1], cell[2], cell[3]);
            draw(e, c, s, g, km[i], kr[i]);
        } else {
            moy_ui_api_at(c, cell[0], cell[1], cell[2], cell[3]);
            place_at(e, c, s, g, km[i], kr[i], cell);
        }
        x += kw + gap;
    }
}

// A handheld's tool row: a cell each across the width, a word's its width (two cells at
// most), the icons sharing the rest.
static void tool_cells(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                       const int32_t r[4])
{
    int16_t kids[PLACE_KIDS];
    int32_t ws[PLACE_KIDS], words = 0;
    int n = 0, icons = 0;
    KIDS(k, g)
    if (n < PLACE_KIDS && placed_shown(e, g, model, row))
        kids[n++] = (int16_t)g;
    int nk = n > 1 ? n : 1;
    for (int i = 0; i < n; i++) {
        if (NODE(kids[i])->btn & BT_ALONE) {
            ws[i] = -1;
            icons++;
            continue;
        }
        int32_t v = natural(e, kids[i], model, row, r[3]), most = fdiv(2 * r[2], nk);
        ws[i] = v < most ? v : most;
        words += ws[i];
    }
    int32_t rest = r[2] - words, x = r[0];
    int j = 0, ic = icons > 1 ? icons : 1;
    for (int i = 0; i < n; i++) {
        int32_t kw = ws[i];
        if (kw < 0) {
            kw = fdiv(rest * (j + 1), ic) - fdiv(rest * j, ic);
            j++;
        }
        int32_t cell[4] = {x, r[1] + 1, kw - 1, r[3] - 2};
        put_rect(e, kids[i], cell);
        moy_ui_api_at(c, cell[0], cell[1], cell[2], cell[3]);
        draw(e, c, s, kids[i], model, row);
        x += kw;
    }
}

// A panel: the desk's and the handheld's arrangements stacked; any other its ground and its
// words down its middle.
static void draw_panel(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                       const int32_t r[4])
{
    const char *key = uit_str(e, NODE(k)->key);
    if (!strcmp(key, "hand") || !strcmp(key, "desk")) {
        stack(e, c, s, k, model, row, r);
        return;
    }
    if (e->placing)
        return;
    int32_t g = (e->flags & UIT_F_DESK) ? 6 : 4;
    fill_token(s, r[0] + g, r[1] + g, r[2] - 2 * g, r[3] - 2 * g, MOY_UI_T_PANEL);
    int32_t ty = r[1] + fdiv(r[3], 2) - 4;
    KIDS(k, l) {
        if (NODE(l)->kind != UIT_LABEL || !placed_shown(e, l, model, row))
            continue;
        int32_t cell[4] = {r[0] + g, ty, r[2] - 2 * g, 16};
        place_at(e, c, s, l, model, row, cell);
        ty += 18;
    }
}

// A canvas in a placed page: a part of its own the front end draws into (its clip and ground
// the front end's); a stop only with keys=, as in a flowing page.
static void draw_canvas_at(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row)
{
    const char *key = uit_str(e, NODE(k)->key);
    moy_ui_over_t o;
    int32_t got[5];
    moy_ui_over_none(&o);
    moy_ui_over_text(&o, MOY_UI_OV_ID, span_of(key, strlen(key)));
    if ((e->flags & UIT_F_BARE) || e->in_foot) {
        int32_t one = 1;
        moy_ui_over_put(&o, MOY_UI_OV_BARE, &one);       // a bare page's canvases, and a foot's, sink no well
    }
    if (NODE(k)->lit & CV_KEYS)
        id_put(e, k, model, row, key);  // a stop while it takes the keys, as in a flowing page (`draw`)
    else
        moy_ui_over_put(&o, MOY_UI_OV_DISABLED, &(int32_t){1});
    moy_ui_api_part(c, s, span_of(key, strlen(key)), 0, 0, &o, got);
    canvas_drew(e, k);
    if (e->draw_fn)
        canvas_draw(e, k, model, row, got[0], got[1], got[2], got[3]);
}

// Node `k` in its rect: the rect recorded, the node drawn there (in a placement, only the
// regions a host places are walked).
static void place_at(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                     const int32_t r[4])
{
    const uit_node_t *N = NODE(k);
    put_rect(e, k, r);
    switch (N->kind) {
    case UIT_PANES:
    case UIT_PANE:
        pn_draw(e, c, s, k, model, row, r);
        return;
    case UIT_CASE:
        stack(e, c, s, k, model, row, r);
        return;
    case UIT_SWITCH: {
        int cs = uit_case_of(e, k);
        if (cs >= 0)
            stack(e, c, s, cs, model, row, r);
        return;
    }
    case UIT_PANEL:
        draw_panel(e, c, s, k, model, row, r);
        return;
    case UIT_ROW:
        row_cells(e, c, s, k, model, row, r);
        return;
    }
    if (e->placing)
        return;
    switch (N->kind) {
    case UIT_TOOLS:
        if (N->lit & TL_LEND)
            return;                     // drawn at the site it is lent to
        if (e->flags & UIT_F_DESK)
            row_cells(e, c, s, k, model, row, r);
        else
            tool_cells(e, c, s, k, model, row, r);
        return;
    case UIT_STATUS:
        draw_status(e, s, k, model, row, r);
        return;
    case UIT_BUTTON: {
        int32_t hh = h_row(e);
        moy_ui_api_at(c, r[0], r[1], r[2], r[3] < hh ? r[3] : hh);
        draw(e, c, s, k, model, row);
        return;
    }
    case UIT_CANVAS:
        moy_ui_api_at(c, r[0], r[1], r[2], r[3]);
        draw_canvas_at(e, c, s, k, model, row);
        return;
    case UIT_TABS:
        tabs_in(e, c, s, k, r);
        return;
    case UIT_TABLE:
    case UIT_GRID: {
        // a table, a grid: laid out in its cell (a grid its w= and h= at the cell's top)
        int32_t was[4], cell[4] = {r[0], r[1], r[2], r[3]};
        if (N->kind == UIT_GRID && N->t_value >= 0) {
            int32_t gw = len_of(e, N->t_value, model, row, 0);
            cell[2] = gw < r[2] ? gw : r[2];
        }
        if (N->kind == UIT_GRID && N->t_aux >= 0) {
            int32_t gh = len_of(e, N->t_aux, model, row, 0);
            cell[3] = gh < r[3] ? gh : r[3];
        }
        memcpy(was, e->rect, sizeof was);
        memcpy(e->rect, cell, sizeof cell);
        draw(e, c, s, k, model, row);
        memcpy(e->rect, was, sizeof was);
        return;
    }
    case UIT_GROUP:
        if (N->parent != UIT_NONE && NODE(N->parent)->kind == UIT_ROW) {
            col_draw(e, c, s, k, model, row, r);    // a group in a row: a column down its cell
            return;
        }
        break;
    case UIT_ROWS:                      // a rows list in a stack: a scroll region of its own
        moy_ui_api_at(c, r[0], r[1], r[2], r[3]);
        scroll_open(e, c, s, k, 0);
        draw(e, c, s, k, model, row);
        moy_ui_api_scroll(c, s, span_of("", 0), NULL);
        return;
    case UIT_TEXT_EDITOR: {
        // its document is the front end's: it draws the editor's rows in the rect, under the
        // node's id (a stop)
        const char *key = uit_str(e, N->key);
        id_put(e, k, model, row, key);
        if (e->draw_fn)
            canvas_draw(e, k, model, row, r[0], r[1], r[2], r[3]);
        return;
    }
    }
    moy_ui_api_at(c, r[0], r[1], r[2], r[3]);
    draw(e, c, s, k, model, row);
}

// -- the panes ------------------------------------------------------------------------
//
// A split (`ui.panes`) is the rule's container along its axis: each child held at its size
// (its size= state, else its start=, never under its minimum) and the one that grows the fill;
// where the fill falls under its minimum the held children give it room, last first, down to
// their own (the desk Editor's rule, `uitree_editor.fit`). Under the outermost panes' least size,
// or with a pane grown, one pane stands over the whole area. A placement records the
// arrangement and each hosted body's rect for the host; the dividers are `moy_ui_api_split`'s,
// drawn inline in the page's pass or into a host's own (`uit_splits`).

enum { PN_GUTTER = 6, PN_HEADER = 32, PN_FLOOR_W = 64, PN_FLOOR_H = PN_HEADER + 16, PN_DOUBLE_MS = 400 };

static int pn_shown(uit_t *e, int k);
static int offered(uit_t *e, int k, const char *v);

// Pane `k` offers tab value `v` (its offered= condition holds, or it names none for `v`).
static int pn_offers(uit_t *e, int k, const char *v)
{
    return offered(e, k, v);
}

// A pane's tab values on offer, counted; the first into *first (NULL none).
static int pn_tabs(uit_t *e, int k, const char **first)
{
    const uit_node_t *N = NODE(k);
    if (first)
        *first = NULL;
    if (N->slot < 0)
        return -1;
    const uit_slot_t *S = &e->slots[N->slot];
    const char *v = uit_str(e, S->vals);
    int n = 0;
    for (int i = 0; i < S->nvals; i++, v += strlen(v) + 1)
        if (pn_offers(e, k, v)) {
            if (first && !n)
                *first = v;
            n++;
        }
    return n;
}

static int pn_shown(uit_t *e, int k)
{
    const uit_node_t *N = NODE(k);
    if (!placed_shown(e, k, -1, -1))
        return 0;
    if (N->kind == UIT_PANE)
        return N->slot < 0 || pn_tabs(e, k, NULL) > 0;     // a pane left with no tab goes
    if (N->kind == UIT_PANES) {
        KIDS(k, g) if (pn_shown(e, g)) return 1;           // ...and a split left empty
        return 0;
    }
    return 1;
}

// A child's least size along `axis`, in pixels, its gutters in.
static int32_t pn_min(uit_t *e, int k, int axis)
{
    const uit_node_t *N = NODE(k);
    int32_t du = e->du;
    if (N->kind == UIT_PANE) {
        int32_t floor = axis ? PN_FLOOR_H : PN_FLOOR_W, d = floor, most = 0;
        const int16_t *m = e->btns + (N->nbtn ? N->mark : 0);
        if (!N->nbtn)
            return floor * du;
        if (m[0] == PN_MIN_ONE)
            return m[1 + axis] * du;
        for (int i = 0; i < N->nbtn; i++)
            if (m[3 * i] == PN_MIN_ANY)
                d = m[3 * i + 1 + axis];
        const uit_slot_t *S = &e->slots[N->slot];
        const char *v = uit_str(e, S->vals);
        for (int j = 0; j < S->nvals; j++, v += strlen(v) + 1) {      // by tab: the largest offered
            if (!pn_offers(e, k, v))
                continue;
            int32_t got = d;
            for (int i = 0; i < N->nbtn; i++)
                if (m[3 * i] != PN_MIN_ANY && !strcmp(uit_str(e, (uint16_t)m[3 * i]), v))
                    got = m[3 * i + 1 + axis];
            if (got > most)
                most = got;
        }
        return most * du;
    }
    if (N->kind != UIT_PANES)
        return 0;
    int32_t sum = 0, most = 0;
    int n = 0;
    KIDS(k, g) {
        if (!pn_shown(e, g))
            continue;
        int32_t m = pn_min(e, g, axis);
        sum += m, n++;
        if (m > most)
            most = m;
    }
    if (!!(N->lit & PN_COL) == axis)
        return sum + (int32_t)N->nbtn * du * (n > 1 ? n - 1 : 0);
    return most;
}

// A child's held size now, in pixels: its state, else its start (desk units); -1 it grows.
static int32_t pn_held(uit_t *e, int k)
{
    const uit_node_t *N = NODE(k);
    if ((N->lit & PN_GROW) || N->current < 0)
        return -1;
    const uit_slot_t *S = &e->slots[N->current];
    if (!S->absent)
        return S->i;
    int32_t st = (N->lit & PN_START) ? (int16_t)N->btn
                 : N->changed >= 0 && !e->slots[N->changed].absent ? e->slots[N->changed].i : 0;
    return st * e->du;
}

// The children's sizes along a span `total` long (`uitree_editor.fit`).
static void pn_fit(const int32_t *held, const int32_t *mins, int n, int32_t total, int32_t *sizes)
{
    int flex = n - 1;
    for (int i = n - 1; i >= 0; i--)
        if (held[i] < 0)
            flex = i;
    int32_t rest = total;
    for (int i = 0; i < n; i++) {
        sizes[i] = held[i] < 0 ? 0 : held[i] > mins[i] ? held[i] : mins[i];
        if (i != flex)
            rest -= sizes[i];
    }
    int32_t need = mins[flex] - rest;
    for (int i = n - 1; i >= 0 && need > 0; i--) {
        if (i == flex)
            continue;
        int32_t give = sizes[i] - mins[i] < need ? sizes[i] - mins[i] : need;
        if (give > 0)
            sizes[i] -= give, rest += give, need -= give;
    }
    sizes[flex] = rest > 0 ? rest : 0;
}

// The first shown pane under `k` in reading order whose node is `want` (-1: any), else -1.
static int pn_pane_in(uit_t *e, int k, int want)
{
    KIDS(k, g) {
        if (!pn_shown(e, g))
            continue;
        if (NODE(g)->kind == UIT_PANE && (want < 0 || g == want))
            return g;
        if (NODE(g)->kind == UIT_PANES) {
            int got = pn_pane_in(e, g, want);
            if (got >= 0)
                return got;
        }
    }
    return -1;
}

// The shown pane under `k` keyed `key` (n bytes), else -1.
static int pn_pane_keyed(uit_t *e, int k, const char *key, size_t n)
{
    KIDS(k, g) {
        if (!pn_shown(e, g))
            continue;
        if (NODE(g)->kind == UIT_PANE) {
            const char *gk = uit_str(e, NODE(g)->key);
            if (strlen(gk) == n && !memcmp(gk, key, n))
                return g;
        } else if (NODE(g)->kind == UIT_PANES) {
            int got = pn_pane_keyed(e, g, key, n);
            if (got >= 0)
                return got;
        }
    }
    return -1;
}

// The pane shown over the whole panes area, else -1: the grown one, else the focused one
// where the area is under the outermost panes' least size.
static int pn_alone(uit_t *e, int k, const int32_t r[4])
{
    const uit_node_t *N = NODE(k);
    if (N->cur >= 0 && !e->slots[N->cur].absent) {
        const uit_slot_t *S = &e->slots[N->cur];
        int p = pn_pane_keyed(e, k, S->s ? S->s : "", S->sn);
        if (p >= 0)
            return p;
    }
    if (r[2] < pn_min(e, k, 0) || r[3] < pn_min(e, k, 1)) {
        int p = e->pane_cur >= 0 ? pn_pane_in(e, k, e->pane_cur) : -1;
        return p >= 0 ? p : pn_pane_in(e, k, -1);
    }
    return -1;
}

static void pn_rec(uit_pa_t *a, int k, const int32_t r[4], const uit_arr_t *A)
{
    a->node = (int16_t)k;
    for (int i = 0; i < 4; i++)
        a->r[i] = (int16_t)r[i];
    a->depth = A->depth;
    memcpy(a->path, A->path, PN_DEPTH);
}

// The split's id as the toolkit keeps its dividers: "split:" and its children's keys.
static size_t pn_sid(uit_t *e, const uit_ps_t *P, char *out, size_t cap)
{
    size_t n = (size_t)snprintf(out, cap, "split:");
    for (int j = 0; j < P->nk && n < cap; j++)
        n += (size_t)snprintf(out + n, cap - n, "%s%s", j ? "/" : "", uit_str(e, NODE(P->kids[j])->key));
    return n < cap ? n : cap - 1;
}

// Held size `k`'s state written (`v` -1: put back, absent), traced `why` and queued.
static void pn_write(uit_t *e, int k, int32_t v, const char *why, int i, const char *sid)
{
    int sl = NODE(k)->current;
    uit_slot_t *S = &e->slots[sl];
    int32_t was = S->absent ? -1 : S->i;
    if (v < 0)
        uit_set_absent(e, sl);
    else
        uit_set_int(e, sl, v);
    if (e->flags & UIT_F_TRACE) {
        char a[16], b[16];
        snprintf(a, sizeof a, was < 0 ? "None" : "%d", (int)was);
        snprintf(b, sizeof b, v < 0 ? "None" : "%d", (int)v);
        uit_buf_t t = {0};
        uit_buf_printf(&t, "%s -> %s   (divider %d of ", a, b, i);
        uit_buf_repr(&t, sid, strlen(sid));
        uit_buf_printf(&t, " %s)", why);
        uit_trace(e, "state", uit_str(e, S->name), "%s", t.p ? t.p : "");
        uit_buf_free(&t);
    }
    uit_event(e, UIT_EV_WRITE, sl, -1, -1, NULL, 0);
    e->arr->writes++;
}

static int pn_holds(uit_t *e, int k)
{
    return NODE(k)->current >= 0 && !(NODE(k)->lit & PN_GROW);
}

// The pane of a split's child the keys reach, its index, else -1.
static int pn_keys_child(uit_t *e, const uit_ps_t *P)
{
    if (e->pane_cur < 0 || e->arr->root < 0 || pn_pane_in(e, e->arr->root, e->pane_cur) < 0)
        return -1;
    for (int j = 0; j < P->nk; j++)
        if (P->kids[j] == e->pane_cur)
            return j;
    return -1;
}

// Split `si`'s dividers drawn on `c`: a press on one held, its drag's let-go writing the held
// sizes beside it, a double tap putting them back. `out` (UIT_SP_*) where one is held.
static int pn_split(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int si, int32_t *out)
{
    uit_arr_t *A = e->arr;
    uit_ps_t *P = &A->splits[si];
    int32_t u = e->du, n = P->nk;
    int32_t opt[MOY_UI_SPO_N] = {0}, got[PN_KIDS], w[4 * PN_KIDS + 4];
    opt[MOY_UI_SPO_FLAGS] = (P->axis ? MOY_UI_SPLIT_Y : 0) | MOY_UI_SPLIT_DRAG | MOY_UI_SPLIT_FOCUS;
    opt[MOY_UI_SPO_GAP] = P->gap;
    opt[MOY_UI_SPO_CUR] = pn_keys_child(e, P);
    opt[MOY_UI_SPO_SLOP] = A->mouse ? 0 : 8 * u;
    if (!A->mouse)
        opt[MOY_UI_SPO_HIT_W] = 16 * u, opt[MOY_UI_SPO_HIT_L] = 48 * u;
    opt[MOY_UI_SPO_HANDLE_W] = 6 * u, opt[MOY_UI_SPO_HANDLE_L] = 36 * u;
    opt[MOY_UI_SPO_LINE] = 2 * u;
    memcpy(got, P->sizes, (size_t)n * sizeof *got);
    char sid[96];
    size_t sn = pn_sid(e, P, sid, sizeof sid);
    moy_ui_api_at(c, P->r[0], P->r[1], P->r[2], P->r[3]);
    moy_ui_api_split(c, s, span_of(sid, sn), got, n, P->mins, opt, w);
    int32_t i = w[4 * n], at = w[4 * n + 1], stop = w[4 * n + 2], bits = w[4 * n + 3];
    if (i < 0 || i >= n - 1)
        return 0;
    if (bits & MOY_UI_SPD_LET_GO) {
        if (bits & MOY_UI_SPD_LIVE) {
            for (int j = i; j <= i + 1; j++) {
                int k = P->kids[j];
                if (pn_holds(e, k) && (pn_held(e, k) != got[j] || e->slots[NODE(k)->current].absent))
                    pn_write(e, k, got[j], "let go", i, sid);
            }
        } else {
            uint32_t key = 2166136261u;
            for (size_t b = 0; b < sn; b++)
                key = (key ^ (uint8_t)sid[b]) * 16777619u;
            key = key * 31u + (uint32_t)i + 1u;
            if (A->tap_key != key || (uint32_t)(A->clock - A->tap_at) >= PN_DOUBLE_MS) {
                A->tap_key = key, A->tap_at = A->clock;
                return 0;
            }
            A->tap_key = 0;
            for (int j = i; j <= i + 1; j++) {
                int k = P->kids[j];
                if (pn_holds(e, k) && !e->slots[NODE(k)->current].absent)
                    pn_write(e, k, -1, "tapped twice", i, sid);
            }
        }
        return 1;
    }
    out[UIT_SP_SPLIT] = si, out[UIT_SP_DIV] = i, out[UIT_SP_AT] = at, out[UIT_SP_STOP] = stop;
    out[UIT_SP_LIVE] = (bits & MOY_UI_SPD_LIVE) != 0;
    if ((bits & MOY_UI_SPD_LIVE) && stop >= 0) {
        int p = P->kids[i + stop];
        if (NODE(p)->kind == UIT_PANES)
            p = pn_pane_in(e, p, -1);
        out[UIT_SP_FLASH] = p;
        out[UIT_SP_MIN] = p >= 0 ? pn_min(e, p, P->axis) : 0;
    }
    return 0;
}

static void pn_lay(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                   const int32_t r[4])
{
    uit_arr_t *A = e->arr;
    const uit_node_t *N = NODE(k);
    int16_t kids[PN_KIDS];
    int n = 0;
    KIDS(k, g) if (n < PN_KIDS && pn_shown(e, g)) kids[n++] = (int16_t)g;
    if (n == 1) {
        pn_draw(e, c, s, kids[0], model, row, r);
        return;
    }
    if (!n)
        return;
    int axis = (N->lit & PN_COL) != 0;
    int32_t gap = (int32_t)N->nbtn * space_unit(e), span = r[2 + axis] - gap * (n - 1);
    uit_ps_t P;
    memset(&P, 0, sizeof P);
    P.node = (int16_t)k, P.nk = (uint8_t)n, P.axis = (uint8_t)axis, P.gap = (int16_t)gap;
    for (int i = 0; i < 4; i++)
        P.r[i] = (int16_t)r[i];
    P.depth = A->depth;
    memcpy(P.path, A->path, PN_DEPTH);
    for (int j = 0; j < n; j++) {
        P.kids[j] = kids[j];
        P.held[j] = pn_held(e, kids[j]);
        P.mins[j] = pn_min(e, kids[j], axis);
    }
    pn_fit(P.held, P.mins, n, span, P.sizes);
    int si = -1;
    if (!A->ghost && A->nsplits < PN_SPLITS) {
        si = A->nsplits++;
        A->splits[si] = P;
    }
    if (!e->placing && si >= 0 && pn_split(e, c, s, si, A->held))
        A->owe = 1;          // the page is drawn again with the sizes written
    int record = A->arranging && e->placing;
    int32_t x = r[0], y = r[1], w = r[2], h = r[3];
    uint8_t base = A->depth;
    for (int j = 0; j < n; j++) {
        int32_t sz = j < n - 1 ? P.sizes[j] : (axis ? h : w);
        int32_t cell[4] = {x, y, axis ? w : sz, axis ? sz : h}, div[4] = {0, 0, 0, 0};
        if (j < n - 1) {
            if (!axis) {
                div[0] = x + sz, div[1] = y, div[2] = gap, div[3] = h;
                x += sz + gap, w -= sz + gap;
            } else {
                div[0] = x, div[1] = y + sz, div[2] = w, div[3] = gap;
                y += sz + gap, h -= sz + gap;
            }
        }
        if (base < PN_DEPTH)
            A->path[base] = (uint8_t)j;
        A->depth = (uint8_t)(base + 1);
        pn_draw(e, c, s, kids[j], model, row, cell);
        A->depth = base;
        if (record && j < n - 1 && A->ndivs < PN_MAX) {
            uit_pd_t *D = &A->divs[A->ndivs++];
            for (int i = 0; i < 4; i++)
                D->r[i] = (int16_t)div[i];
            D->depth = base, D->i = (uint8_t)j, D->axis = (uint8_t)axis;
            memcpy(D->path, A->path, PN_DEPTH);
        }
    }
}

static void pane_head(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                      const int32_t r[4], int32_t hh)
{
    const uit_node_t *N = NODE(k);
    int32_t x = r[0], y = r[1], w = r[2];
    fill_token(s, x, y, w, hh - 1, MOY_UI_T_PANEL);
    fill_token(s, x, y + hh - 1, w, 1, MOY_UI_T_BORDER);
    int32_t tw = 0;
    KIDS(k, t) {
        if (NODE(t)->kind != UIT_TOOLS || !placed_shown(e, t, model, row))
            continue;
        int nk = 0;
        KIDS(t, g) {
            if (!placed_shown(e, g, model, row))
                continue;
            int32_t v = natural(e, g, model, row, hh - 4);
            tw += (v > 0 ? v : 0) + 4, nk++;
        }
        int32_t cell[4] = {x + w - tw - 4, y + 2, tw, hh - 4};
        put_rect(e, t, cell);
        row_cells(e, c, s, t, model, row, cell);
        break;
    }
    if (N->slot >= 0) {
        // its tabs, every value of its enum (`_r_tabs`)
        moy_ui_api_at(c, x + 6, y + 2, w - tw - 16, hh - 4);
        int count, at;
        uint32_t len, items = seg_items(e, N, &len, &count, &at);
        const char *name = uit_str(e, e->slots[N->slot].name);
        int got = moy_ui_api_choice(c, s, 9, span_of(name, strlen(name)), (const uint8_t *)e->scratch.p + items,
                                    len, at, NULL);
        id_put(e, k, model, row, name);
        if (got >= 0 && got < count && got != at) {
            const char *v = seg_key(e, N, got);
            const uit_slot_t *S = &e->slots[N->slot];
            uit_buf_t b = {0};
            uit_buf_repr(&b, S->s ? S->s : "", S->sn);
            uit_buf_printf(&b, " -> ");
            uit_buf_repr(&b, v, strlen(v));
            uit_buf_printf(&b, "   (from tabs ");
            uit_buf_repr(&b, name, strlen(name));
            uit_buf_printf(&b, ")");
            uit_set_text(e, N->slot, v, strlen(v));
            if (e->flags & UIT_F_TRACE)
                uit_trace(e, "state", name, "%s", b.p);
            uit_buf_free(&b);
            uit_event(e, UIT_EV_WRITE, N->slot, -1, -1, NULL, 0);
        }
        return;
    }
    moy_ui_api_at(c, x + 10, y + 2, w - tw - 20, hh - 4);
    uint32_t n, at;
    if (N->t_icon >= 0) {
        at = uit_tmpl_render(e, N->t_icon, model, row, &n);
        moy_ui_api_icon(c, sspan(e, at, n));
    }
    at = text(e, k, 0, model, row, &n);
    moy_ui_api_label(c, s, sspan(e, at, n), NULL);
}

static void pane_at(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                    const int32_t r[4])
{
    uit_arr_t *A = e->arr;
    if (A->arranging && e->placing && A->npanes < PN_MAX)
        pn_rec(&A->panes[A->npanes++], k, r, A);
    if (A->ghost)
        return;
    int32_t hh = (NODE(k)->lit & PN_HEADLESS) ? 0 : PN_HEADER * e->du;
    if (A->norder < PN_MAX)
        pn_rec(&A->order[A->norder++], k, r, A);
    if (!e->placing && hh)
        pane_head(e, c, s, k, model, row, r, hh);
    int32_t body[4] = {r[0], r[1] + hh, r[2], r[3] - hh > 0 ? r[3] - hh : 0};
    stack(e, c, s, k, model, row, body);
}

static void panes_at(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                     const int32_t r[4])
{
    uit_arr_t *A = e->arr;
    int p = NODE(k)->parent;
    if (p == (int)UIT_NONE || (NODE(p)->kind != UIT_PANE && NODE(p)->kind != UIT_PANES)) {
        A->root = (int16_t)k;
        A->depth = 0;
        if (A->arranging && e->placing) {
            A->npanes = A->ndivs = 0;
            A->least[0] = (int16_t)pn_min(e, k, 0), A->least[1] = (int16_t)pn_min(e, k, 1);
        }
        int alone = pn_alone(e, k, r);
        if (A->arranging && e->placing) {
            A->alone = (int16_t)alone;
            for (int i = 0; i < 4; i++)
                A->alone_r[i] = (int16_t)r[i];
        }
        if (alone >= 0) {
            if (e->placing) {
                // the arrangement under the pane alone, as a host's placement answers it
                A->ghost = 1;
                pn_lay(e, c, s, k, model, row, r);
                A->ghost = 0;
            }
            A->arranging = 0;
            pn_draw(e, c, s, alone, model, row, r);
            A->arranging = 1;
            return;
        }
    }
    pn_lay(e, c, s, k, model, row, r);
}

static void pn_draw(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k, int model, int row,
                    const int32_t r[4])
{
    if (!e->arr)
        return;
    switch (NODE(k)->kind) {
    case UIT_PANES:
        panes_at(e, c, s, k, model, row, r);
        return;
    case UIT_PANE:
        pane_at(e, c, s, k, model, row, r);
        return;
    }
    place_at(e, c, s, k, model, row, r);
}

// A pass begins: its splits and the panes it draws let go (a placement's bodies too).
static int pn_pass(uit_t *e)
{
    if (!e->has_panes)
        return 1;
    if (!e->arr) {
        e->arr = UIT_MALLOC(sizeof *e->arr);
        if (!e->arr)
            return 0;
        memset(e->arr, 0, sizeof *e->arr);
        e->arr->alone = -1;
    }
    uit_arr_t *A = e->arr;
    A->nsplits = A->norder = 0;
    A->root = -1;
    A->depth = A->ghost = 0;
    A->arranging = 1;
    for (int i = 0; i < UIT_SP_N; i++)
        A->held[i] = -1;
    return 1;
}

void uit_panes_set(uit_t *e, int du, const char *pane_cur, int mouse, uint32_t clock)
{
    e->du = (int16_t)(du > 0 ? du : 1);
    e->pane_cur = -1;
    for (int k = 0; pane_cur && pane_cur[0] && k < e->nnodes; k++)
        if (NODE(k)->kind == UIT_PANE && !strcmp(uit_str(e, NODE(k)->key), pane_cur))
            e->pane_cur = (int16_t)k;
    if (e->arr)
        e->arr->mouse = (uint8_t)(mouse != 0), e->arr->clock = clock;
}

void uit_set_unit(uit_t *e, int unit)
{
    e->unit = (int16_t)(unit > 0 ? unit : 0);
}

void uit_set_scale(uit_t *e, int scale)
{
    e->sc = (int16_t)(scale > 0 ? scale : 0);
}

static int pn_put(int32_t *out, int at, int max, const uit_pa_t *a)
{
    if (at + 10 > max)
        return at;
    out[at] = a->node;
    for (int i = 0; i < 4; i++)
        out[at + 1 + i] = a->r[i];
    out[at + 5] = a->depth;
    for (int i = 0; i < PN_DEPTH; i++)
        out[at + 6 + i] = a->path[i];
    return at + 10;
}

int uit_panes(const uit_t *e, int32_t *out, int max)
{
    const uit_arr_t *A = e->arr;
    if (!A || max < UIT_PN_HEAD)
        return 0;
    out[0] = A->root, out[1] = A->alone, out[2] = A->least[0], out[3] = A->least[1];
    out[4] = A->npanes, out[5] = A->ndivs, out[6] = A->norder, out[7] = A->nsplits;
    int at = UIT_PN_HEAD;
    for (int i = 0; i < A->npanes; i++)
        at = pn_put(out, at, max, &A->panes[i]);
    for (int i = 0; i < A->ndivs; i++) {
        const uit_pd_t *D = &A->divs[i];
        if (at + 11 > max)
            break;
        for (int j = 0; j < 4; j++)
            out[at + j] = D->r[j];
        out[at + 4] = D->depth;
        for (int j = 0; j < PN_DEPTH; j++)
            out[at + 5 + j] = D->path[j];
        out[at + 9] = D->i, out[at + 10] = D->axis;
        at += 11;
    }
    for (int i = 0; i < A->norder; i++)
        at = pn_put(out, at, max, &A->order[i]);
    for (int i = 0; i < A->nsplits; i++) {
        const uit_ps_t *P = &A->splits[i];
        if (at + 12 + 4 * P->nk > max)
            break;
        out[at] = P->node, out[at + 1] = P->nk, out[at + 2] = P->axis, out[at + 3] = P->gap;
        for (int j = 0; j < 4; j++)
            out[at + 4 + j] = P->r[j];
        out[at + 8] = P->depth;
        for (int j = 0; j < PN_DEPTH; j++)
            out[at + 9 + j] = P->path[j];
        at += 9 + PN_DEPTH;
        for (int j = 0; j < P->nk; j++) {
            out[at] = P->kids[j], out[at + 1] = P->sizes[j], out[at + 2] = P->mins[j], out[at + 3] = P->held[j];
            at += 4;
        }
    }
    return at;
}

int uit_pane_ask(uit_t *e, int node, int what, int arg)
{
    if (node < 0 || node >= e->nnodes || (NODE(node)->kind != UIT_PANE && NODE(node)->kind != UIT_PANES))
        return UIT_E_ARG;
    switch (what) {
    case UIT_PQ_SHOWN:
        return pn_shown(e, node);
    case UIT_PQ_MIN:
        return pn_min(e, node, arg != 0);
    case UIT_PQ_HELD:
        return pn_held(e, node);
    case UIT_PQ_OFFERS: {
        const uit_node_t *N = NODE(node);
        if (N->kind != UIT_PANE || N->slot < 0 || arg < 0 || arg >= e->slots[N->slot].nvals)
            return UIT_E_ARG;
        const char *v = uit_str(e, e->slots[N->slot].vals);
        for (int i = 0; i < arg; i++)
            v += strlen(v) + 1;
        return pn_offers(e, node, v);
    }
    }
    return UIT_E_ARG;
}

int uit_splits(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int flags, int32_t out[UIT_SP_N])
{
    for (int i = 0; i < UIT_SP_N; i++)
        out[i] = -1;
    out[UIT_SP_WRITES] = out[UIT_SP_OWE] = 0;
    uit_arr_t *A = e->arr;
    if (!A)
        return 0;
    e->flags = (e->flags & ~UIT_F_TRACE) | (flags & UIT_F_TRACE);
    A->writes = 0;
    for (int i = 0; i < A->nsplits; i++)
        if (pn_split(e, c, s, i, out))
            out[UIT_SP_OWE] = 1;
    if (A->alone >= 0) {
        // the pane alone over the panes' rect: a split of one, its focus the pane the keys reach
        int32_t one = 0, w[4 + 4], opt[MOY_UI_SPO_N] = {0};
        opt[MOY_UI_SPO_FLAGS] = MOY_UI_SPLIT_FOCUS;
        moy_ui_api_at(c, A->alone_r[0], A->alone_r[1], A->alone_r[2], A->alone_r[3]);
        moy_ui_api_split(c, s, span_of("split alone", 11), &one, 1, NULL, opt, w);
    }
    out[UIT_SP_WRITES] = A->writes;
    return e->nevs - e->evat;
}

void uit_split_held(const uit_t *e, int32_t out[UIT_SP_N])
{
    for (int i = 0; i < UIT_SP_N; i++)
        out[i] = e->arr ? e->arr->held[i] : -1;
    out[UIT_SP_WRITES] = out[UIT_SP_OWE] = 0;
}

int uit_place(uit_t *e, int x, int y, int w, int h, int flags, int fs)
{
    if (!e->nnodes)
        return 0;
    if (!rects_ready(e))
        return UIT_E_NOMEM;
    e->flags = flags & ~(UIT_F_UP | UIT_F_DOWN);
    e->fs = fs;
    e->placing = 1;
    int32_t r[4] = {x, y, w, h};
    if (!pn_pass(e)) {
        e->placing = 0;
        return UIT_E_NOMEM;
    }
    stack(e, NULL, NULL, 0, -1, -1, r);
    e->placing = 0;
    return 0;
}

// A placed page's band hints: a dialog's, else the focused stop's; none while nothing or a text
// editor holds focus (a text surface keeps its keys).
// The innermost shown row or group under `k` whose close= says what Back does there, else -1
// (`_closer`: a switch its one case, a list's rows none).
static int closer_of(uit_t *e, int k)
{
    const uit_node_t *N = NODE(k);
    if (!uit_shown(e, k, -1, -1))
        return -1;
    if (N->kind == UIT_SWITCH) {
        int cs = uit_case_of(e, k);
        return cs < 0 ? -1 : closer_of(e, cs);
    }
    KIDS(k, g) {
        if (UIT_IS_LIST(NODE(g)->kind))
            continue;
        int got = closer_of(e, g);
        if (got >= 0)
            return got;
    }
    return (N->kind == UIT_ROW || N->kind == UIT_GROUP) && N->on >= 0 ? k : -1;
}

int uit_page_shown(const uit_t *e)
{
    return e->nnodes && NODE(0)->kind == UIT_PAGE ? NODE(0)->changed : -1;
}

int uit_back_closer(uit_t *e, char *buf, size_t cap)
{
    int g = e->nnodes && uit_dialog(e) < 0 ? closer_of(e, 0) : -1;
    if (g < 0)
        return -2;
    if (buf && cap)
        snprintf(buf, cap, "%s", uit_str(e, NODE(g)->key));
    return uit_act_can(e, NODE(g)->on, -1, -1) ? NODE(g)->on : -1;
}

// An action's hint into the band where it renders any.
static void hint_named(uit_t *e, uit_buf_t *b, const char *verb, int a)
{
    uint32_t n, at = uit_tmpl_render(e, e->acts[a].hint, -1, -1, &n);
    if (n) {
        hint_add(b, verb, strlen(verb));
        hint_add(b, e->scratch.p + at, n);
    }
}

// Whether popover `p` holds words alone (See why): nothing in it takes the keys.
static int pop_note(uit_t *e, int p)
{
    KIDS(p, g) {
        int kind = NODE(g)->kind;
        if (kind == UIT_FIELD || kind == UIT_ROWS || kind == UIT_LINK || kind == UIT_BUTTON || kind == UIT_MENU ||
            kind == UIT_SLIDER || kind == UIT_TOGGLE || kind == UIT_SEG || kind == UIT_CELLS || kind == UIT_STEPPER)
            return 0;
    }
    return 1;
}

int uit_take_focused(uit_t *e)
{
    const uit_id_t *F = &e->focused;
    if (!e->has_focused || F->gen != e->gen || F->kind != UIT_LINK || popover_of(e) < 0)
        return 0;
    int m = F->row >= 0 ? uit_model_of(e, F->node) : -1;
    if (F->act < 0 || !uit_act_can(e, F->act, m, F->row))
        return 1;
    fire(e, F->act, F->node, m, F->row, NULL);
    return 1;
}

void uit_anchor(uit_t *e, const char *name, int x, int y, int w, int h)
{
    if (e->nanc >= UIT_ANCS)
        return;
    if (!e->anc && !(e->anc = UIT_MALLOC(UIT_ANCS * sizeof *e->anc)))
        return;
    uit_anc_t *A = &e->anc[e->nanc++];
    snprintf(A->name, UIT_ID_MAX + 1, "%s", name);
    int16_t *a = A->r;
    a[0] = (int16_t)x, a[1] = (int16_t)y, a[2] = (int16_t)w, a[3] = (int16_t)h;
}

// The rect a popover hangs from (`_part_anchor`): a part the front end placed this frame
// ("code.caret"), a pane's header ("PANE.head"), or a node's whole rect as this frame placed
// it (a text editor, a slot, a row); 0 none.
static int anchor_rect(uit_t *e, const char *name, size_t n, int32_t out[4])
{
    for (int i = 0; i < e->nanc; i++)
        if (strlen(e->anc[i].name) == n && !memcmp(e->anc[i].name, name, n)) {
            for (int j = 0; j < 4; j++)
                out[j] = e->anc[i].r[j];
            return 1;
        }
    if (n > 5 && !memcmp(name + n - 5, ".head", 5) && e->arr) {
        const uit_arr_t *A = e->arr;
        for (int i = 0; i < A->norder; i++) {
            const uit_node_t *P = NODE(A->order[i].node);
            const char *key = uit_str(e, P->key);
            if (strlen(key) == n - 5 && !memcmp(key, name, n - 5)) {
                if (P->lit & PN_HEADLESS)
                    return 0;
                for (int j = 0; j < 3; j++)
                    out[j] = A->order[i].r[j];
                out[3] = PN_HEADER * e->du;
                return 1;
            }
        }
    }
    if (memchr(name, '.', n) || !e->rects)
        return 0;
    for (int k = 0; k < e->nnodes; k++) {
        const uit_node_t *N = NODE(k);
        const char *key = uit_str(e, N->key);
        if (N->kind != UIT_POPOVER && strlen(key) == n && !memcmp(key, name, n)) {
            const int16_t *r = e->rects + 4 * k;
            if (r[2] < 0)
                continue;           // not placed this frame (hidden): a shown node of the key may be
            for (int j = 0; j < 4; j++)
                out[j] = r[j];
            return 1;
        }
    }
    return 0;
}

// Whether rows node `k` is a popover's list of one link a row (`_menu_rows`).
static int is_menu_rows(uit_t *e, int k)
{
    const uit_node_t *L = NODE(k);
    return L->kind == UIT_ROWS && L->parent != UIT_NONE && NODE(L->parent)->kind == UIT_POPOVER &&
           L->kid != UIT_NONE && NODE(L->kid)->next == UIT_NONE && NODE(L->kid)->kind == UIT_LINK;
}

// A menu row's text and id: the link's label, its value after a tab, cut to what the toolkit keeps.
static void menu_row_id(uit_t *e, int link, int m, int r, char id[UIT_ID_MAX + 1])
{
    uint32_t mark = e->scratch.n, ln, la = text(e, link, 0, m, r, &ln), vn = 0, va = 0;
    if (NODE(link)->t_value >= 0)
        va = text(e, link, 1, m, r, &vn);
    if (vn)
        snprintf(id, UIT_ID_MAX + 1, "%.*s\t%.*s", (int)ln, e->scratch.p + la, (int)vn, e->scratch.p + va);
    else
        snprintf(id, UIT_ID_MAX + 1, "%.*s", (int)ln, e->scratch.p + la);
    e->scratch.n = mark;
}

// A popover's list of one link a row is a menu (`_menu_rows`): a choice row each, its value at
// the row's right, its id its text; the row taken runs the link's action on it.
static void menu_rows(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k)
{
    const uit_node_t *L = NODE(k);
    int link = L->kid, m = L->slot, nr = e->slots[m].nrows;
    if (!nr) {
        uint32_t n, at = L->t_aux >= 0 ? uit_tmpl_render(e, L->t_aux, -1, -1, &n) : 0;
        if (L->t_aux >= 0 && n) {
            moy_ui_over_t o;
            moy_ui_over_none(&o);
            moy_ui_api_text(c, 0, 0, 1, -1);      // tone "dim"
            moy_ui_api_label(c, s, sspan(e, at, n), &o);
        }
        return;
    }
    uit_buf_t labels = {0}, icons = {0};
    int ti = NODE(link)->t_icon;
    for (int r = 0; r < nr; r++) {
        if (r) {
            uit_buf_printf(&labels, "%c", 0);
            if (ti >= 0)
                uit_buf_printf(&icons, "%c", 0);
        }
        char id[UIT_ID_MAX + 1];
        menu_row_id(e, link, m, r, id);
        uit_buf_printf(&labels, "%s", id);
        id_put(e, link, m, r, id);
        if (ti >= 0) {
            // the link's icon= on its row: the menu row's icon
            uint32_t n, mark = e->scratch.n, at = uit_tmpl_render(e, ti, m, r, &n);
            uit_buf_printf(&icons, "%.*s", (int)n, e->scratch.p + at);
            e->scratch.n = mark;
        }
    }
    int got = moy_ui_api_menu(c, s, span_of("", 0), (const uint8_t *)labels.p, labels.n,
                              (const uint8_t *)(icons.p ? icons.p : ""), icons.n, NULL);
    if (got >= 0 && got < nr && uit_act_can(e, NODE(link)->act, m, got))
        fire(e, NODE(link)->act, link, m, got, NULL);
    uit_buf_free(&labels);
    uit_buf_free(&icons);
}

// A popover on a placed page (`uitree_editor.Engine._r_popover`): hung from its anchor= (a
// whole text editor, or a part of one), `w=` wide; one hung from a whole node stands over that
// node's top, centred where it opens on a field, else at its start. Its field, its words as
// they flow, its menu rows,
// anything else as it draws; a note (words alone) names its close in its own band.
static void placed_popover(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int k)
{
    const uit_node_t *N = NODE(k);
    const char *key = uit_str(e, N->key);
    int32_t w = int_of(e, N->t_aux, -1, -1, 200), a[4];
    if (N->t_value >= 0) {
        uint32_t n, mark = e->scratch.n, at = uit_tmpl_render(e, N->t_value, -1, -1, &n);
        const char *name = e->scratch.p + at;
        if (n && anchor_rect(e, name, n, a)) {
            if (!memchr(name, '.', n) && a[2] - 16 * e->fs < w) {
                // hung from a node narrower than it (a tool): under it, at its start, inside
                // the page's room
                int32_t right = e->rect[0] + e->rect[2];
                a[0] = a[0] + w > right ? right - w : a[0];
                a[0] = a[0] < e->rect[0] ? e->rect[0] : a[0];
                a[1] += a[3], a[2] = w, a[3] = 0;
            } else if (!memchr(name, '.', n)) {
                // hung from a whole node: over its top, a field's popover centred, a list at
                // its start
                if (N->kid != UIT_NONE && NODE(N->kid)->kind == UIT_FIELD)
                    a[0] += fdiv(a[2] - w, 2), a[1] += 4 * e->fs;
                a[2] = w, a[3] = 0;
            }
            moy_ui_api_at(c, a[0], a[1], a[2], a[3]);
        }
        e->scratch.n = mark;
    }
    for (int p = N->props; p != (int)UIT_NONE; p = e->props[p].next) {
        // at=: hung from the rect its host hands in, "X Y W H" (none while it renders empty)
        const uit_prop_t *P = &e->props[p];
        if (P->kind != PK_TMPL || strcmp(uit_str(e, P->name), "at"))
            continue;
        uint32_t n, mark = e->scratch.n, a = uit_tmpl_render(e, P->idx, -1, -1, &n);
        char t[64];
        size_t m = n < sizeof t - 1 ? n : sizeof t - 1;
        memcpy(t, e->scratch.p + a, m);
        t[m] = 0;
        e->scratch.n = mark;
        long r[4];
        char *q = t;
        int got = 0;
        for (char *end; got < 4; got++, q = end) {
            r[got] = strtol(q, &end, 10);
            if (end == q)
                break;
        }
        if (got == 4)
            moy_ui_api_at(c, (int32_t)r[0], (int32_t)r[1], (int32_t)r[2], (int32_t)r[3]);
    }
    moy_ui_over_t o;
    if (!moy_ui_api_popover(c, s, span_of(key, strlen(key)), w, pop_over(N, &o)) && N->on >= 0)
        fire(e, N->on, k, -1, -1, NULL);
    KIDS(k, g) {
        if (!uit_shown(e, g, -1, -1))
            continue;
        if (is_menu_rows(e, g))
            menu_rows(e, c, s, g);
        else
            draw(e, c, s, g, -1, -1);
    }
    if (pop_note(e, k) && N->on >= 0) {
        uint32_t n, at = uit_tmpl_render(e, e->acts[N->on].hint, -1, -1, &n);
        if (n) {
            uint32_t hb = e->scratch.n;
            uit_buf_put(&e->scratch, "cancel", 6);
            uit_buf_put(&e->scratch, e->scratch.p + at, n);
            moy_ui_api_hints(c, s, (const uint8_t *)e->scratch.p + hb, e->scratch.n - hb - 1, NULL);
        }
    }
    moy_ui_api_popover(c, s, span_of("", 0), 0, NULL);
}

// A placed page's band hints (`uitree_editor.Engine._hints`): a dialog's; none over a note; under
// a popover or a closer row, the arrows' walk of its list, what Enter does on the focused stop
// (and Shift+Enter in a field) and what Back closes; else none while nothing or a text editor
// holds focus (a text surface keeps its keys), the focused stop's otherwise.
static void placed_hints(uit_t *e, uit_buf_t *b, int pages)
{
    b->n = 0;
    if (uit_dialog(e) >= 0) {
        hints(e, b, pages);
        return;
    }
    int pop = popover_of(e);
    if (pop >= 0 && pop_note(e, pop))
        return;
    int closer = pop >= 0 ? pop : closer_of(e, 0);
    if (closer < 0) {
        if (e->has_focused && e->focused.kind != UIT_TEXT_EDITOR)
            hints(e, b, pages);
        return;
    }
    if (pop >= 0)
        KIDS(pop, g)
        if (NODE(g)->kind == UIT_ROWS && NODE(g)->cur >= 0) {
            static const char PICK[] = "scroll\0Pick";
            uit_buf_put(b, PICK, sizeof PICK - 1);
            break;
        }
    if (e->has_focused && e->focused.gen == e->gen) {
        const uit_id_t *F = &e->focused;
        int a = F->kind == UIT_FIELD ? NODE(F->node)->on : F->act;
        if (F->kind == UIT_FIELD && !e->editing) {
            static const char EDIT[] = "confirm\0Edit";   // a stop until Enter opens its edit
            uit_buf_put(b, EDIT, sizeof EDIT - 1);
        } else if (a >= 0 && uit_act_can(e, a, -1, F->row))
            hint_named(e, b, "confirm", a);
        if (F->kind == UIT_FIELD && e->editing)
            for (int s = 0; s < e->nacts; s++)
                if (e->acts[s].flags & UIT_A_SHIFT_ENTER) {
                    if (uit_act_can(e, s, -1, -1))
                        hint_named(e, b, "Shift+enter", s);
                    break;
                }
    }
    if (NODE(closer)->on >= 0)
        hint_named(e, b, "back", NODE(closer)->on);
}

int uit_row_stop(uit_t *e, const char *cur, const char *rowkey, char *buf, size_t cap)
{
    int s = uit_slot_find(e, cur, strlen(cur));
    char id[UIT_ID_MAX + 1];
    if (s < 0 || !buf || !cap)
        return 0;
    for (int k = 0; k < e->nnodes; k++)
        if (UIT_IS_LIST(NODE(k)->kind) && NODE(k)->cur == s)
            return row_stop_id(e, k, rowkey, strlen(rowkey), id) && snprintf(buf, cap, "%s", id) > 0;
    return 0;
}

int uit_band(const uit_t *e, int32_t out[4])
{
    for (int i = 0; i < 4; i++)
        out[i] = e->band[i];
    return e->nnodes && e->band[3] > 0;
}

int uit_stop_over(const uit_t *e, int i)
{
    if (i < 0 || i >= e->nids)
        return -1;
    for (int k = e->ids[i].node; k >= 0 && k != (int)UIT_NONE; k = e->nodes[k].parent)
        if (e->nodes[k].kind == UIT_DIALOG || e->nodes[k].kind == UIT_POPOVER)
            return 1;
    return 0;
}

int uit_page_rects(const uit_t *e, int32_t out[8])
{
    memcpy(out, e->rect, 4 * sizeof *out);
    if (e->nnodes && e->foot >= 0)
        memcpy(out + 4, e->foot_r, 4 * sizeof *out);
    else
        out[4] = out[5] = out[6] = out[7] = 0;
    return e->nnodes && e->foot >= 0;
}

int uit_gens(uit_t *e, int32_t *out, int cap)
{
    if (!e->nnodes || e->page_gen < 0)
        return 0;
    int n = 0;
    if (n < cap)
        out[n] = e->page_gen;
    n++;
    for (int k = 1; k < e->nnodes; k++)
        if ((NODE(k)->kind == UIT_CARDS && !(NODE(k)->lit & CD_FLOW)) || NODE(k)->kind == UIT_SCROLL ||
            (NODE(k)->kind == UIT_GROUP && NODE(NODE(k)->parent)->kind == UIT_SPLIT)) {
            if (n < cap)
                out[n] = uit_cell_gen(e, k);
            n++;
        }
    return n;
}

int uit_hints(uit_t *e, char *buf, size_t cap)
{
    if (!e->nnodes)
        return 0;
    int pages = (e->flags >> 8) & 0xff;
    uint32_t sn = e->scratch.n;
    uit_buf_t hb = {0};
    if (e->placed)
        placed_hints(e, &hb, pages ? pages : 1);
    else
        hints(e, &hb, pages ? pages : 1);
    e->scratch.n = sn;
    int n = (int)hb.n;
    if (buf && (size_t)n <= cap)
        memcpy(buf, hb.p, (size_t)n);
    uit_buf_free(&hb);
    return n;
}

// Whether the focused stop is a field whose edit is open (mid-frame, a stop not drawn yet as
// the frame before drew it): what its hints name.
static void edit_sync(uit_t *e, moy_ui_ctx_t *c)
{
    e->editing = (uint8_t)(e->has_focused && e->focused.kind == UIT_FIELD && moy_ui_api_typing_drawing(c));
}

// A placed page's band: the page's last row, cut from its room, where it names anything.
static void placed_band(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, uit_buf_t *hb, int pages)
{
    edit_sync(e, c);
    placed_hints(e, hb, pages);
    if (!hb->n)
        return;
    static const char BAR[] = "change\0Move\0confirm\0Open\0back\0Back";
    const uint8_t *hp = (e->flags & UIT_F_ON_BAR) ? (const uint8_t *)BAR : (const uint8_t *)hb->p;
    size_t hn = (e->flags & UIT_F_ON_BAR) ? sizeof BAR - 1 : hb->n - 1;
    if (moy_ui_api_hints_w(c, s, hp, hn) <= 0)
        return;
    int32_t band[4], rest[4];
    moy_ui_cut(e->rect, MOY_UI_CUT_BOTTOM, h_row(e), band, rest);
    moy_ui_api_at(c, band[0], band[1], band[2], band[3]);
    moy_ui_api_hints(c, s, hp, hn, NULL);
    memcpy(e->rect, rest, sizeof rest);
}

// A placed page's pass: its children stacked down its room, its popovers and dialogs last.
static void placed_walk(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s)
{
    if (!rects_ready(e) || !pn_pass(e))
        return;
    e->nlate = 0;
    stack(e, c, s, 0, -1, -1, e->rect);
    for (int i = 0; i < e->nlate; i++) {
        moy_ui_api_at(c, e->rect[0], e->rect[1], e->rect[2], e->rect[3]);
        draw(e, c, s, e->late[i], -1, -1);
    }
}

static uint32_t still_sum(const uit_t *e)
{
    uint32_t g = (uint32_t)e->gen * 65537u + e->edits;
    for (int i = 0; i < e->nslots; i++)
        g += (uint32_t)e->slots[i].ver * (uint32_t)(2 * i + 1);
    return g;
}

int uit_still(uit_t *e, const moy_ui_ctx_t *c, int x, int y, int w, int h, int flags, int fs, int input)
{
    if (!e->still_ok || !e->nnodes || e->fresh || e->want || e->evat < e->nevs || e->trace_at < e->trace.n)
        return 0;
    if ((flags & (UIT_F_UP | UIT_F_DOWN)) || flags != e->flags || fs != e->fs || input != e->input
        || x != e->cx || y != e->cy || w != e->cw || h != e->ch)
        return 0;
    if (still_sum(e) != e->still_ver || e->has_focused != e->still_had
        || (e->has_focused && (e->focused.node != e->still_focus.node || e->focused.row != e->still_focus.row
                               || e->focused.gen != e->still_focus.gen
                               || strcmp(e->focused.id, e->still_focus.id))))
        return 0;
    const int32_t *in = c->in;
    if (in[MOY_UI_IN_BTNP] || in[MOY_UI_IN_KEY] || in[MOY_UI_IN_REP] || in[MOY_UI_IN_KEYREP]
        || in[MOY_UI_IN_WHEEL_X] || in[MOY_UI_IN_WHEEL_Y] || (in[MOY_UI_IN_PTR] & (MOY_UI_P_HELD | MOY_UI_P_EDGE))
        || c->act || c->press)
        return 0;
    return !moy_ui_api_moved(c) && !moy_ui_api_moving(c) && !moy_ui_api_owes(c);
}

// Whether node `k` is shown and a split or a grid, or a switch whose shown case holds one: the
// page is then laid out in cells, and its band cut from its room.
static int in_cells(uit_t *e, int k)
{
    int kind = NODE(k)->kind;
    if (!uit_shown(e, k, -1, -1))
        return 0;
    if (kind == UIT_GRID || (kind == UIT_SPLIT && !split_flows(e, k)))
        return 1;
    int cs = kind == UIT_SWITCH ? uit_case_of(e, k) : -1;
    if (cs >= 0)
        KIDS(cs, g)
        if (in_cells(e, g))
            return 1;
    return 0;
}

int uit_frame(uit_t *e, moy_ui_ctx_t *c, const moy_ui_sink_t *s, int x, int y, int w, int h,
              int flags, int fs, int input)
{
    if (!e->nnodes)
        return 0;
    e->flags = flags & ~(UIT_F_UP | UIT_F_DOWN);
    e->fs = fs;
    e->input = input;
    e->cx = (int16_t)x, e->cy = (int16_t)y, e->cw = (int16_t)w, e->ch = (int16_t)h;
    e->scratch.n = 0;
    e->nanc = 0;
    if (e->fits_on) {
        e->fits.n = 0;
        e->fit_k = -1;
        moy_ui_fit_tap(fit_told, e);
    }
    int pages = (flags >> 8) & 0xff;
    uit_id_t last = e->focused;             // the last frame's focus
    int had_last = e->has_focused;
    // the page
    moy_ui_over_t o;
    moy_ui_over_none(&o);
    const char *pid = uit_str(e, e->page_id);
    moy_ui_over_text(&o, MOY_UI_OV_ID, span_of(pid, strlen(pid)));
    if (flags & UIT_F_BARE) {
        int32_t one = 1;
        moy_ui_over_put(&o, MOY_UI_OV_BARE, &one);
    }
    // the engine values the page's text names, as this frame begins (its gens count them)
    e->gv = 0;
    if (e->gen_vals & GV_FOCUS) {
        char fv[UIT_ID_MAX + 1];
        int n = moy_ui_api_focus(c, span_of(NULL, 0), fv, sizeof fv);
        uint32_t h = 2166136261u;
        for (int i = 0; i < n; i++)
            h = (h ^ (uint8_t)fv[i]) * 16777619u;
        e->gv += h;
    }
    if (e->gen_vals & GV_INPUT)
        e->gv += (uint32_t)(input + 1) * 40503u;
    if (e->placed && (flags & UIT_F_BAND)) {
        // a placed page's hints band takes the page's foot only while its focus has hints (a
        // focus the last frame landed on): the page's layout moves with it, so its gen does
        uit_buf_t band = {0};
        placed_hints(e, &band, pages ? pages : 1);
        if (band.n)
            e->gv += 2654435761u;
        uit_buf_free(&band);
    }
    e->page_gen = -1;
    e->canvas_last = e->canvas_now;
    e->canvas_now = 0;
    if ((flags & UIT_F_GEN) && gen_ok(e)) {
        uint32_t g = (uint32_t)e->gen + e->edits + e->gv;
        for (int i = 0; i < e->nslots; i++)
            if (e->slots[i].in_gen)
                g += e->slots[i].ver;
        int32_t gen = (int32_t)(g & 0x7fffffff);
        moy_ui_over_put(&o, MOY_UI_OV_GEN, &gen);
        e->page_gen = gen;
    }
    e->foot = (int16_t)foot_of(e);
    int redone = 0;                 // the page's pass runs again, clamped (moy_ui_api_page_again)
    int moved = 0;
    char ahead[UIT_ID_MAX + 1];
again:;
    int ground = e->placed && e->ground[2] > 0;
    if (ground)
        moy_ui_api_at(c, e->ground[0], e->ground[1], e->ground[2], e->ground[3]);
    uint32_t n, at = text(e, 0, 0, -1, -1, &n);
    moy_ui_box_t box;
    moy_ui_api_page(c, s, sspan(e, at, n), &o, &box);
    e->pw = box.w;
    e->rect[0] = box.x, e->rect[1] = box.y, e->rect[2] = box.w, e->rect[3] = box.h;
    if (ground)
        e->rect[0] = x, e->rect[1] = y, e->rect[2] = w, e->rect[3] = h;
    uit_buf_t hb = {0};
    e->band_h = 0;
    if (e->placed) {
        if (flags & UIT_F_BAND)
            placed_band(e, c, s, &hb, pages ? pages : 1);
        goto ids;
    }
    if (redone) {
        // the page's second pass: focus where the first pass left it, by the first pass's ids
        char f2[UIT_ID_MAX + 1];
        int n2 = moy_ui_api_focus(c, span_of(NULL, 0), f2, sizeof f2);
        const uit_id_t *now2 = n2 > 0 ? id_find(e->ids, e->nids, f2) : NULL;
        if (now2) {
            e->focused = *now2;
            e->has_focused = 1;
        }
        goto band;
    }
    // what focus is on as the page begins
    char f[UIT_ID_MAX + 1];
    int fl = moy_ui_api_focus(c, span_of(NULL, 0), f, sizeof f);
    const uit_id_t *now = fl >= 0 ? id_find(e->ids, e->nids, f) : NULL;
    if (now) {
        e->focused = *now;
        e->has_focused = 1;
    } else if (fl == 0 && e->has_focused) {
        int d = (flags & UIT_F_DOWN) ? 1 : (flags & UIT_F_UP) ? -1 : 0;
        e->has_focused = 0;
        if (d) {
            stops_t st = {0};
            stops_of(e, 0, -1, -1, &st);
            for (int i = 0; i < st.n; i++)
                if (e->focused.gen == e->gen && st.s[i].node == e->focused.node && st.s[i].row == e->focused.row) {
                    int j = i + d;
                    if (j < 0 || j >= st.n)
                        j = i;
                    const uit_node_t *N = NODE(st.s[j].node);
                    e->focused.node = st.s[j].node;
                    e->focused.row = st.s[j].row;
                    e->focused.act = N->act;
                    e->focused.kind = N->kind;
                    e->has_focused = 1;
                    break;
                }
            UIT_FREE(st.s);
        }
    }
    if (!e->has_focused && !e->want) {
        stops_t st = {0};
        stops_of(e, 0, -1, -1, &st);
        if (st.n) {
            const uit_node_t *N = NODE(st.s[0].node);
            e->focused.node = st.s[0].node;
            e->focused.row = st.s[0].row;
            e->focused.act = N->act;
            e->focused.kind = N->kind;
            e->focused.gen = e->gen;
            e->has_focused = 1;
        }
        UIT_FREE(st.s);
    }
band:
    // the hints band
    edit_sync(e, c);
    hints(e, &hb, pages ? pages : 1);
    if (hb.n && (flags & UIT_F_BAND)) {
        static const char BAR[] = "change\0Move\0confirm\0Open\0back\0Back";
        const uint8_t *hp = (flags & UIT_F_ON_BAR) ? (const uint8_t *)BAR : (const uint8_t *)hb.p;
        size_t hn = (flags & UIT_F_ON_BAR) ? sizeof BAR - 1 : hb.n - 1;
        int placed = e->foot >= 0;
        KIDS(0, k)
        if (in_cells(e, k))
            placed = 1;
        int card = 0;           // a bare page's shown popover is the page: the band in its body
        if (flags & UIT_F_BARE)
            KIDS(0, k)
            if (NODE(k)->kind == UIT_POPOVER && uit_shown(e, k, -1, -1))
                card = 1;
        moy_ui_over_t so;           // the page's status= words, which the band leads with
        moy_ui_over_none(&so);
        if (NODE(0)->t_aux >= 0 && !(flags & UIT_F_ON_BAR)) {
            uint32_t sn, sa = uit_tmpl_render(e, NODE(0)->t_aux, -1, -1, &sn);
            if (sn)
                moy_ui_over_text(&so, MOY_UI_OV_HINT, span_of(e->scratch.p + sa, sn));
        }
        if (card) {
            e->pop_hints = hp, e->pop_hints_n = hn;
        } else if (!placed) {
            // a flowing page's band docks at its foot: the room its pictures may draw in ends over it
            if (moy_ui_api_hints_w(c, s, hp, hn) > 0) {
                int mn;
                e->band_h = (flags & UIT_F_DESK) ? moy_ui_metrics(MOY_UI_K_VALUE_ROW, &mn)[17] * fs : 20 * fs;
            }
            moy_ui_api_hints(c, s, hp, hn, &so);
        } else if (moy_ui_api_hints_w(c, s, hp, hn) > 0) {
            // a placed page's band: a handheld's its room's last line, the desk's and a foot's
            // at the page's foot
            int32_t band[4], rest[4];
            int mn, hh = 20 * fs;
            if (flags & UIT_F_DESK)
                hh = moy_ui_metrics(MOY_UI_K_VALUE_ROW, &mn)[17] * fs;
            moy_ui_cut(e->rect, 1, hh, band, rest);
            if (!(flags & UIT_F_DESK) && e->foot < 0)
                moy_ui_api_at(c, band[0], band[1], band[2], band[3]);
            moy_ui_api_hints(c, s, hp, hn, &so);
            memcpy(e->rect, rest, sizeof rest);
        }
    }
    if (e->foot >= 0) {
        // the foot: docked above the band, on the page's ground; a note in it as tall as its
        // lines at the foot's width (fixed_h reads it)
        int32_t got[4], lead = (flags & UIT_F_DESK) ? 16 : MOY_UI_HINT_LEAD(0) * fs;
        KIDS(e->foot, g) {
            if (NODE(g)->kind != UIT_NOTE)
                continue;
            uit_buf_t lines = {0};
            uint32_t mark = e->scratch.n;
            moy_ui_span_t icon = note_of(e, g, -1, -1, &lines);
            NODE(g)->btn = (uint16_t)moy_ui_api_note_h(c, s, icon, (const uint8_t *)(lines.p ? lines.p : ""),
                                                        lines.n, e->rect[2] - 2 * lead);
            e->scratch.n = mark;
            uit_buf_free(&lines);
        }
        int32_t fh = foot_stacked(e, e->foot), desk = (flags & UIT_F_DESK) != 0;
        int32_t dh = fh ? fh + (NODE(e->foot)->lit == 2 ? 0 : desk ? 14 : 2 * fs)
                        : (desk ? 44 : 22 * fs) + foot_line(e, e->foot);
        if (moy_ui_api_dock(c, dh, got)) {
            memcpy(e->foot_r, got, sizeof got);
            e->rect[3] = got[1] - e->rect[1] > 0 ? got[1] - e->rect[1] : 0;
        }
    }
ids:;
    if (redone) {
        e->nids = 0;
    } else {
        // this frame's ids
        uit_id_t *t = e->prev;
        int tc = e->cprev;
        e->prev = e->ids;
        e->cprev = e->cids;
        e->nprev = e->nids;
        e->ids = t;
        e->cids = tc;
        e->nids = 0;
        moved = land_focus(e, c, ahead);
    }
    e->tv_stop_now = 0;
    e->page_tabs_now = -1;
    if (e->placed)
        placed_walk(e, c, s);
    else if (rects_ready(e))            // a flowing page's rects: where its canvases drew
        walk(e, c, s, 0, -1, -1);
    moy_ui_api_page_done(c, s);         // the next frame's plan reads what this one drew
    if (!redone && moy_ui_api_page_again(c)) {
        // the page closed short of its scroll (rows hidden under it): it draws again, clamped,
        // in this frame, its input taken by the first pass
        redone = 1;
        uit_buf_free(&hb);
        e->scratch.n = 0;
        e->nanc = 0;
        e->canvas_now = 0;
        e->pop_hints_n = 0;
        if (e->fits_on) {
            e->fits.n = 0;
            e->fit_k = -1;
        }
        goto again;
    }
    e->band[0] = c->hint_band.x, e->band[1] = c->hint_band.y;
    e->band[2] = c->hint_band.w, e->band[3] = c->hint_band.h;
    e->pop_hints_n = 0;         // (its buffer goes with this frame)
    e->tv_stop = e->tv_stop_now;
    e->page_tabs = e->page_tabs_now;
    e->page_tabs_gen = e->gen;
    // after: what holds focus, and whether the band named another node's verbs
    int had = e->has_focused, was_editing = e->editing;
    uit_id_t was = e->focused;
    focus_after(e, c, moved, ahead, had_last ? &last : NULL);
    edit_sync(e, c);
    int owe = 0;
    if (e->arr && e->arr->owe)
        owe = 1, e->arr->owe = 0;       // a divider's let-go wrote held sizes
    int32_t fb[4];
    if (e->focus_key[0] && !moy_ui_api_hit_box(c, span_of(e->focus_key, strlen(e->focus_key)), fb)) {
        if (strcmp(e->lost, e->focus_key))      // focus on a stop the frame drew none of: the
            owe = 1;                            // next begin passes it on (once for each)
        snprintf(e->lost, sizeof e->lost, "%s", e->focus_key);
    } else
        e->lost[0] = 0;
    if (had != e->has_focused || was_editing != e->editing ||
        (had && (was.node != e->focused.node || was.gen != e->focused.gen))) {
        uit_buf_t hb2 = {0};
        if (e->placed)
            placed_hints(e, &hb2, pages ? pages : 1);
        else
            hints(e, &hb2, pages ? pages : 1);
        owe |= hb2.n != hb.n || (hb.n && memcmp(hb.p, hb2.p, hb.n));
        uit_buf_free(&hb2);
    }
    uit_buf_free(&hb);
    e->still_ver = still_sum(e);
    e->still_focus = e->focused;
    e->still_had = (uint8_t)e->has_focused;
    e->still_ok = !owe;
    if (e->fits_on)
        moy_ui_fit_tap(NULL, NULL);
    if (flags & UIT_F_BACK)             // the way back the host's back takes (uit_run_backed)
        moy_ui_api_way(c, pages > 1 || uit_dialog(e) >= 0 || popover_of(e) >= 0 ||
                              role_action(e, UIT_A_ROLE_BACK) >= 0);
    return (e->nevs - e->evat) | (owe ? 1 << 16 : 0);
}

// -- a row lent to a site ---------------------------------------------------------

// The source of node `k`'s prop `name`, else NULL.
static const char *prop_src(uit_t *e, int k, const char *name)
{
    for (int p = NODE(k)->props; p != (int)UIT_NONE; p = e->props[p].next)
        if (!strcmp(uit_str(e, e->props[p].name), name))
            return uit_str(e, e->props[p].src);
    return NULL;
}

// The shown `tools lend=SITE` under `k` (a hidden node hides its subtree, a switch shows its
// one case, a list holds none), else -1.
static int lender(uit_t *e, int k, const char *site)
{
    const uit_node_t *N = NODE(k);
    if (!uit_shown(e, k, -1, -1) || UIT_IS_LIST(N->kind))
        return -1;
    if (N->kind == UIT_TOOLS && (N->lit & TL_LEND)) {
        const char *s = prop_src(e, k, "lend");
        return s && !strcmp(s, site) ? k : -1;
    }
    if (N->kind == UIT_SWITCH) {
        int cs = uit_case_of(e, k);
        return cs < 0 ? -1 : lender(e, cs, site);
    }
    KIDS(k, g) {
        int r = lender(e, g, site);
        if (r >= 0)
            return r;
    }
    return -1;
}

// `uit_live`'s walk: what `lender` walks, each shown node of `units` setting its bit of
// `*mask` and each shown lender's site held against the ones met before it.
static int live_walk(uit_t *e, int k, const int16_t *units, int n, uint32_t *mask, int16_t *lend,
                     int *nlend, int *node)
{
    const uit_node_t *N = NODE(k);
    if (!uit_shown(e, k, -1, -1) || UIT_IS_LIST(N->kind))
        return 0;
    for (int i = 0; i < n; i++)
        if (units[i] == k)
            *mask |= 1u << i;
    if (N->kind == UIT_TOOLS && (N->lit & TL_LEND)) {
        const char *site = prop_src(e, k, "lend");
        for (int i = 0; i < *nlend; i++)
            if (!strcmp(prop_src(e, lend[i], "lend"), site)) {
                *node = k;
                return uit_check_fail(e, "L03", UIT_MSG("two shown rows lend to %s: %s and %s", "%s %s %s"), site,
                                      uit_str(e, NODE(lend[i])->key), uit_str(e, N->key));
            }
        if (*nlend < UIT_LIVE_LENDERS)
            lend[(*nlend)++] = (int16_t)k;
        return 0;
    }
    if (N->kind == UIT_SWITCH) {
        int cs = uit_case_of(e, k);
        return cs < 0 ? 0 : live_walk(e, cs, units, n, mask, lend, nlend, node);
    }
    KIDS(k, g) {
        int r = live_walk(e, g, units, n, mask, lend, nlend, node);
        if (r < 0)
            return r;
    }
    return 0;
}

int uit_live(uit_t *e, const int16_t *units, int n, int *node)
{
    int lenders = 0;
    for (int k = 0; k < e->nnodes && lenders < 2; k++)
        lenders += NODE(k)->kind == UIT_TOOLS && (NODE(k)->lit & TL_LEND);
    if (!e->nnodes || n < 0 || n > 31 || (!n && lenders < 2))
        return n < 0 || n > 31 ? UIT_E_ARG : 0;
    uint32_t mask = 0;
    int16_t lend[UIT_LIVE_LENDERS];
    int nlend = 0, r = live_walk(e, 0, units, n, &mask, lend, &nlend, node);
    return r < 0 ? r : (int)mask;
}

// Whether tabs node `k` offers value `v`: no offered= for it, or its condition holds.
static int offered(uit_t *e, int k, const char *v)
{
    for (int p = NODE(k)->props; p != (int)UIT_NONE; p = e->props[p].next) {
        const uit_prop_t *P = &e->props[p];
        if (P->kind == PK_COND && P->repr != UIT_NONE && !strcmp(uit_str(e, P->name), "offered") &&
            !strcmp(uit_str(e, P->repr), v))
            return uit_cond_eval(e, P->idx, -1, -1);
    }
    return 1;
}

// A cell's four texts onto `text` at `*at`: 0, or -1 where they do not fit.
static int lent_texts(char *text, size_t cap, size_t *at, const char *const t[4], const size_t n[4])
{
    for (int i = 0; i < 4; i++) {
        if (*at + n[i] + 1 > cap)
            return -1;
        memcpy(text + *at, t[i], n[i]);
        text[*at + n[i]] = 0;
        *at += n[i] + 1;
    }
    return 0;
}

int uit_lent(uit_t *e, const char *site, int32_t *cells, int max, char *text, size_t cap)
{
    if (!e->nnodes)
        return -1;
    int k = lender(e, 0, site);
    if (k < 0)
        return -1;
    uint32_t mark = e->scratch.n;
    size_t at = 0;
    int n = 0, r = 0;
    KIDS(k, g) {
        if (n >= max)
            break;
        const uit_node_t *G = NODE(g);
        if (!placed_shown(e, g, -1, -1))
            continue;
        const char *key = uit_str(e, G->key);
        if (G->kind == UIT_TABS && e->slots[G->slot].type != UIT_ENUM) {
            r = uit_fail(e, UIT_E_KIND, UIT_MSG("tabs over a row_of in a row lent to %s: an enum's tabs",
                                                "row_of tabs lent to %s"), site);
            break;
        } else if (G->kind == UIT_TABS) {
            const uit_slot_t *S = &e->slots[G->slot];
            const char *v = uit_str(e, S->vals);
            for (int i = 0; i < S->nvals && n < max; i++, v += strlen(v) + 1) {
                size_t vn = strlen(v);
                if (!offered(e, g, v))
                    continue;
                const char *t[4] = {key, v, G->cur >= 0 ? uit_label_word(e, G->cur, v, vn) : v,
                                    G->nbtn ? uit_label_word(e, G->nbtn - 1, v, vn) : ""};
                size_t tn[4] = {strlen(t[0]), vn, strlen(t[2]), strlen(t[3])};
                int32_t *c = cells + n * UIT_LC_INTS;
                c[0] = UIT_LC_TAB, c[1] = g, c[2] = i, c[4] = G->on;
                c[3] = vn == S->sn && S->s && !memcmp(v, S->s, vn) ? UIT_LC_CUR : 0;
                if (lent_texts(text, cap, &at, t, tn) < 0)
                    goto small;
                n++;
            }
        } else if (G->kind == UIT_BUTTON || G->kind == UIT_LABEL) {
            uint32_t ln = 0, in = 0, la = text_t(e, g, G->t_main, -1, -1, &ln), ia = 0;
            if (G->kind == UIT_BUTTON && G->t_icon >= 0)
                ia = uit_tmpl_render(e, G->t_icon, -1, -1, &in);
            const char *t[4] = {key, "", e->scratch.p + la, in ? e->scratch.p + ia : ""};
            size_t tn[4] = {strlen(key), 0, ln, in};
            int32_t *c = cells + n * UIT_LC_INTS;
            c[0] = G->kind == UIT_LABEL ? UIT_LC_TEXT : UIT_LC_BUTTON, c[1] = g, c[2] = -1, c[3] = 0, c[4] = -1;
            if (G->kind == UIT_BUTTON) {
                c[4] = G->act;
                c[3] = ((G->btn & BT_ALONE) ? UIT_LC_ALONE : 0) | (G->lit == 1 ? UIT_LC_PRIMARY : 0) |
                       (G->act < 0 || uit_act_can(e, G->act, -1, -1) ? UIT_LC_ON : 0) |
                       (G->mark >= 0 && uit_cond_eval(e, G->mark, -1, -1) ? UIT_LC_MARKED : 0);
            }
            if (lent_texts(text, cap, &at, t, tn) < 0)
                goto small;
            n++;
        } else {
            r = uit_fail(e, UIT_E_KIND, UIT_MSG("a %s in a row lent to %s: tabs, buttons and a label",
                                                "%s lent to %s"), uit_kind_names[G->kind], site);
            break;
        }
    }
    e->scratch.n = mark;
    return r < 0 ? r : n;
small:
    e->scratch.n = mark;
    return uit_fail(e, UIT_E_ARG, UIT_MSG("the lent row's texts pass %u bytes", "lent %u"), (unsigned)cap);
}

// The lent row's rule (the bar's zone): its cells pack from the left in their order, the run
// of buttons at its end stands at the zone's right end, END short of it, and a hairline closes
// a run of tabs and opens that end run. GAP, LEAST, GROUP and END are at fs 1.
enum { LZ_GAP = 5, LZ_LEAST = 2, LZ_GROUP = 8, LZ_END = 6 };
#define LP(i) (cells + (i) * UIT_LP_INTS)

// Whether cell `i` shows its label at `density` (`words`: a button its word at density 1).
static int lp_named(const int32_t *c, int density, int words)
{
    if (!c[2])
        return 0;
    if (c[0] == UIT_LC_TAB)
        return density == 2 || (density == 1 && (c[1] & UIT_LC_CUR));
    return c[0] == UIT_LC_BUTTON && (density == 2 || (density == 1 && words)) && !(c[1] & UIT_LC_ALONE);
}

static int32_t lp_width(const int32_t *c, int density, int words, int32_t h, int32_t pad)
{
    if (c[0] == UIT_LC_TEXT)
        return 0;
    if (lp_named(c, density, words))
        return c[2];
    return c[0] == UIT_LC_TAB && (c[1] & UIT_LC_CUR) ? h + 2 * pad : h;
}

int uit_lent_place(int32_t *cells, int n, int32_t x0, int32_t w, int32_t h, int fs, int32_t pad,
                   int32_t *hair, int *nhair, int32_t *need)
{
    int end = n, lines = 0, tablines = 0, text = 0, density = 2, words = 1;
    w -= LZ_END * fs;
    if (w < 0)
        w = 0;
    while (end > 0 && LP(end - 1)[0] == UIT_LC_BUTTON)
        end--;
    // a line before cell i: after a run of tabs, and before the end run
#define LINE(i) ((i) > 0 && (i) < n && ((LP((i) - 1)[0] == UIT_LC_TAB && LP(i)[0] != UIT_LC_TAB) || \
                                        ((i) == end && end > 0)))
    for (int i = 0; i < n; i++) {
        text |= LP(i)[0] == UIT_LC_TEXT;
        lines += LINE(i);
        tablines += i > 0 && LP(i - 1)[0] == UIT_LC_TAB && LP(i)[0] != UIT_LC_TAB;
    }
    int32_t gaps = n - 1 - lines, lg = 0, least = 0;
    static const uint8_t TRY[4][2] = {{2, 1}, {1, 1}, {1, 0}, {0, 0}};
    for (int t = 0; t < 4; t++) {
        density = TRY[t][0], words = TRY[t][1];
        lg = density == 1 ? 0 : LZ_LEAST * fs;      // the current tab's name goes before the gaps do
        least = lg * (gaps > 0 ? gaps : 0) + LZ_GROUP * fs * lines;
        int32_t cur = -1, widest = -1;
        for (int i = 0; i < n; i++) {
            int32_t *c = LP(i);
            least += lp_width(c, density, words, h, pad);
            if (c[0] == UIT_LC_TAB && (c[1] & UIT_LC_CUR) && cur < 0)
                cur = lp_width(c, density, words, h, pad);
            if (c[0] == UIT_LC_TAB && c[2] && c[2] > widest)
                widest = c[2];
        }
        // the current tab is named, and the buttons keep their words, only where every tab
        // named in the current one's place fits: which tab is current never changes the strip's look
        int32_t more = density == 1 && cur >= 0 && widest >= 0 && widest > cur ? widest - cur : 0;
        if (least + more <= w || density == 0)
            break;
    }
    int32_t spare = w - least > 0 ? w - least : 0, gap = lg;
    if (!text) {
        int32_t g = spare / (gaps > 1 ? gaps : 1), most = LZ_GAP * fs - lg;
        gap = lg + (g < most ? g : most);
    }
    int nh = 0;
    int32_t x = x0;
    for (int i = 0; i < n; i++) {
        int32_t *c = LP(i);
        int32_t cw = lp_width(c, density, words, h, pad);
        if (i) {
            if (LINE(i)) {
                x += LZ_GROUP * fs;
                if (i == end && !text) {
                    int32_t rest = 0;
                    for (int j = end; j < n; j++)
                        rest += lp_width(LP(j), density, words, h, pad);
                    int32_t at = x0 + w - rest - gap * (n - end - 1);
                    if (at > x)
                        x = at;
                }
                if (nh < n)
                    hair[nh++] = x - (LZ_GROUP * fs + fs) / 2;
            } else {
                x += gap;
            }
        }
        if (c[0] == UIT_LC_TEXT) {
            cw = spare;                 // a line of text takes the room left
            spare = 0;
        }
        if (x + cw > x0 + w) {
            for (int j = i; j < n; j++)
                LP(j)[4] = -1;
            break;
        }
        c[3] = x, c[4] = cw, c[5] = c[0] == UIT_LC_TEXT || lp_named(c, density, words);
        x += cw;
    }
#undef LINE
    *nhair = nh;
    int32_t icons = LZ_LEAST * fs * (n - 1 - tablines > 0 ? n - 1 - tablines : 0) + LZ_GROUP * fs * tablines + LZ_END * fs;
    for (int i = 0; i < n; i++)
        icons += lp_width(LP(i), 0, 0, h, pad);
    *need = icons;
    return density;
}
#undef LP
