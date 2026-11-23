// The public UI API's popovers, menus, card grids, an empty page, tools and
// the app's bar (moy_ui_api.h).

#include "moy_ui_api_int.h"

// -- popovers -------------------------------------------------------------------------

// The body a popover shows of its rows' `body` in `cap`: all of it, else
// the cut, raised to the peek its keep's `peek` found last frame (a row's
// middle half the fade above the cut, `peek_note`), so a cut body always shows
// the top of a row's words over its fade (a phone sheet's peek); never
// under one row.
static int pop_body(moy_ui_ctx_t *c, const moy_ui_keep_t *kb, int body, int cap, int rh) {
    if (body <= cap) {
        return body;
    }
    c->pop.cut = (int16_t)(cap > 0 ? cap : 1);
    int bh = kb != NULL && kb->peek > 0 && kb->peek < cap ? kb->peek : cap;
    return bh < rh ? rh : bh;
}

// A popover's `wash` "view": the view its anchor lies in (a scroll's, else
// the page), inside what a wash covers, but for the anchor grown by its
// ring's reach, which stays as drawn: the four strips around it.
static void wash_view(const moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_box_t a) {
    moy_ui_box_t v = c->pop.view, wb = moy_ui_api_wash_box(c);
    int x0 = v.x > wb.x ? v.x : wb.x, y0 = v.y > wb.y ? v.y : wb.y;
    int x1 = v.x + v.w < wb.x + wb.w ? v.x + v.w : wb.x + wb.w;
    int y1 = v.y + v.h < wb.y + wb.h ? v.y + v.h : wb.y + wb.h;
    int o = 3 * c->fs;
    int hx0 = a.x - o, hy0 = a.y - o, hx1 = a.x + a.w + o, hy1 = a.y + a.h + o;
    hx0 = hx0 < x0 ? x0 : hx0;
    hy0 = hy0 < y0 ? y0 : hy0;
    hx1 = hx1 > x1 ? x1 : hx1;
    hy1 = hy1 > y1 ? y1 : hy1;
    if (x1 <= x0 || y1 <= y0) {
        return;
    }
    if (hx1 <= hx0 || hy1 <= hy0) {
        moy_ui_scrim(s, (moy_ui_box_t){(int16_t)x0, (int16_t)y0, (int16_t)(x1 - x0),
                                       (int16_t)(y1 - y0)});
        return;
    }
    moy_ui_box_t strip[4] = {
        {(int16_t)x0, (int16_t)y0, (int16_t)(x1 - x0), (int16_t)(hy0 - y0)},
        {(int16_t)x0, (int16_t)hy1, (int16_t)(x1 - x0), (int16_t)(y1 - hy1)},
        {(int16_t)x0, (int16_t)hy0, (int16_t)(hx0 - x0), (int16_t)(hy1 - hy0)},
        {(int16_t)hx1, (int16_t)hy0, (int16_t)(x1 - hx1), (int16_t)(hy1 - hy0)},
    };
    for (int i = 0; i < 4; i++) {
        if (strip[i].w > 0 && strip[i].h > 0) {
            moy_ui_scrim(s, strip[i]);
        }
    }
}

// Where a popover `w` wide hung from c->pop.at (centred where c->pop.mid)
// lies for a body `body` high: its card, and in *bh the body's height in
// it. The card keeps `mua_gap` clear of every edge of the surface and never
// covers its anchor: below it, else above it, else on the side with more
// room, its body cut to that room (pop_body: it scrolls to focus, a fade at
// the cut edge). An anchor that is a point (a finger's, `h` 0) starts the
// card there and slides it to fit whole where the surface has the room, as
// a phone's context menu does.
// How far a popover's card keeps off the surface's sides: one hung from
// ui.at's rect the page's gutters (8 px at the scale, 12 on the desk), any
// other the modal band.
static int pop_edge(const moy_ui_ctx_t *c) {
    return c->pop.placed ? (c->cls ? 12 : 8) * c->fs : moy_ui_modal_band(c->fs, c->cls);
}

// The room a popover's card lies in: the surface above the hints band
// where one stands at its foot, which the card leaves showing.
static moy_ui_box_t pop_room(const moy_ui_ctx_t *c) {
    moy_ui_box_t sf = c->surface, hb = c->hint_band;
    if (hb.h > 0 && hb.y > sf.y && hb.y < sf.y + sf.h) {
        sf.h = (int16_t)(hb.y - sf.y);
    }
    return sf;
}

static moy_ui_box_t pop_place(moy_ui_ctx_t *c, const moy_ui_keep_t *kb, int body, int w,
                              int *bh_out) {
    moy_ui_box_t a = c->pop.at, sf = pop_room(c);
    int fs = c->fs, rh = mua_row_h(c), pad = moy_ui_modal_band(fs, c->cls);
    int gap = 4 * fs;
    int x0 = sf.x + gap, x1 = sf.x + sf.w - gap;
    int y0 = sf.y + gap, y1 = sf.y + sf.h - gap;
    int bh = body;
    int x = a.x;
    if (x + w > x1) {
        x = x1 - w;
    }
    if (x < x0) {
        x = x0;
    }
    if (w >= sf.w - 2 * pop_edge(c)) {
        x = sf.x + moy_ui_fdiv(sf.w - w, 2);    // as wide as it may be: centred
    }
    int y;
    if (c->pop.mid) {
        bh = pop_body(c, kb, bh, y1 - y0 - 2 * pad, rh);
        x = sf.x + moy_ui_fdiv(sf.w - w, 2);
        y = sf.y + moy_ui_fdiv(sf.h - (2 * pad + bh), 2);
    } else {
        // the room each side of the anchor, inside the surface's gap (an
        // anchor in a bar beside the surface hangs the card at its edge)
        int top = a.y + a.h + gap > y0 ? a.y + a.h + gap : y0;
        int foot = a.y - gap < y1 ? a.y - gap : y1;
        int below = y1 - top, above = foot - y0;
        int dn = 2 * pad + bh <= below || (2 * pad + bh > above && below >= above);
        int room = dn ? below : above;
        if (a.h == 0 && 2 * pad + bh > room && 2 * pad + bh <= y1 - y0) {
            y = dn ? y1 - (2 * pad + bh) : y0;
        } else {
            bh = pop_body(c, kb, bh, room - 2 * pad, rh);
            y = dn ? top : foot - (2 * pad + bh);
        }
    }
    *bh_out = bh;
    return (moy_ui_box_t){(int16_t)x, (int16_t)y, (int16_t)w, (int16_t)(2 * pad + bh)};
}

// A card's first frame (moy_ui_inst_t's `lent`: a popover's or a dialog's):
// its card drawn `tall` (as high as the surface lets it), what that covered
// kept in `px` (rect `sr` on the canvas, in pixels), the clip it drew under,
// the pointer word it set aside (no row hovers on the tall card) and the
// first stop it recorded; `c` the context drawing it, `kind` the nest it
// opens (2 a dialog, 3 a popover) at `depth`, its nests outside it.
struct moy_ui_lent {
    const moy_ui_ctx_t *c;
    moy_ui_box_t tall, sr;
    int32_t clip[4];
    int32_t ptr;
    int16_t s0, depth;
    uint8_t kind;
    uint16_t px[];
};

struct moy_ui_lent *mua_lent(const moy_ui_ctx_t *c) {
    struct moy_ui_lent *l = c->inst != NULL ? c->inst->lent : NULL;
    return l != NULL && l->c == c ? l : NULL;
}

struct moy_ui_lent *mua_lent_of(const moy_ui_ctx_t *c, int kind) {
    struct moy_ui_lent *l = mua_lent(c);
    return l != NULL && l->kind == kind && l->depth == c->n_nest ? l : NULL;
}

void mua_lent_drop(moy_ui_ctx_t *c) {
    if (mua_lent(c) != NULL) {
        moy_kfree(c->inst->lent);
        c->inst->lent = NULL;
    }
}

int mua_lend(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_box_t t, int kind) {
    moy_canvas_row_t *row = (moy_canvas_row_t *)s->dst;
    if (c->inst->lent != NULL || row == NULL || row->px == NULL) {
        return 0;
    }
    const int32_t *st = row->st;
    int W = (int)st[MOY_ST_W], H = (int)st[MOY_ST_H];
    if (W <= 0 || H <= 0 || (uint32_t)W * (uint32_t)H > row->cap) {
        return 0;
    }
    int x = t.x - (int)st[MOY_ST_CAM_X], y = t.y - (int)st[MOY_ST_CAM_Y];
    if (x < 0 || y < 0 || x + t.w > W || y + t.h > H || x < st[MOY_ST_CX0] || y < st[MOY_ST_CY0]
        || x + t.w > st[MOY_ST_CX1] || y + t.h > st[MOY_ST_CY1]) {
        return 0;
    }
    int h = t.h + MOY_UI_DROP * c->fs;
    if (y + h > H) {
        h = H - y;
    }
    struct moy_ui_lent *l = (struct moy_ui_lent *)moy_kalloc(
        sizeof(*l) + (size_t)t.w * (size_t)h * sizeof(uint16_t),
        MOY_KMEM_PSRAM | MOY_KMEM_INTERNAL_OK);
    if (l == NULL) {
        return 0;
    }
    l->sr = (moy_ui_box_t){(int16_t)x, (int16_t)y, t.w, (int16_t)h};
    l->tall = t;
    memcpy(l->clip, &st[MOY_ST_CX0], sizeof(l->clip));
    l->c = c;
    l->kind = (uint8_t)kind;
    l->depth = (int16_t)c->n_nest;
    c->inst->lent = l;
    return 1;
}

void mua_lend_keep(moy_ui_ctx_t *c, const moy_ui_sink_t *s) {
    moy_canvas_row_t *row = (moy_canvas_row_t *)s->dst;
    int W = (int)row->st[MOY_ST_W];
    struct moy_ui_lent *l = c->inst->lent;
    moy_ui_box_t r = l->sr;
    for (int i = 0; i < r.h; i++) {
        memcpy(l->px + (size_t)i * r.w, row->px + (size_t)(r.y + i) * W + r.x,
               (size_t)r.w * sizeof(uint16_t));
    }
    l->ptr = c->in[MOY_UI_IN_PTR];
    c->in[MOY_UI_IN_PTR] &= ~MOY_UI_P_LIVE;
    l->s0 = (int16_t)c->n_cur;
}

// The columns [*a0, *a1) of row `o` of a card `w` wide and `h` high that
// what it holds draws, as a card of any height draws them: all but the rows
// its rounding blends over what is under it (the corners, r square) and the
// `e` rows at its foot it shows none of.
static void lent_span(int o, int w, int h, int r, int e, int *a0, int *a1) {
    *a0 = *a1 = 0;
    if (o >= h - e) {
        return;
    }
    if (o < r || o >= h - r) {
        if (w > 2 * r) {
            *a0 = r;
            *a1 = w - r;
        }
        return;
    }
    *a1 = w;
}

void mua_lend_put(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_box_t card, int split, int e,
                  int ok) {
    moy_canvas_row_t *row = (moy_canvas_row_t *)s->dst;
    int32_t *st = row->st;
    int W = (int)st[MOY_ST_W], H = (int)st[MOY_ST_H];
    struct moy_ui_lent *l = c->inst->lent;
    uint16_t *px = row->px, *sv = l->px;
    moy_ui_box_t t = l->tall, r = l->sr;
    for (int o = 0; o < r.h; o++) {
        uint16_t *cp = px + (size_t)(r.y + o) * W + r.x, *bp = sv + (size_t)o * r.w;
        for (int i = 0; i < r.w; i++) {
            uint16_t v = cp[i];
            cp[i] = bp[i];
            bp[i] = v;
        }
    }
    if (!ok) {
        return;
    }
    int fs = c->fs, rr = moy_ui_modal_round(fs, c->cls);
    int32_t saved[4];
    memcpy(saved, &st[MOY_ST_CX0], sizeof(saved));
    memcpy(&st[MOY_ST_CX0], l->clip, sizeof(saved));
    static const uint8_t none[1] = {0};
    moy_ui_modal(s, card, (moy_ui_span_t){none, 0}, fs, c->cls, mua_row_h(c));
    int cx0 = st[MOY_ST_CX0] > 0 ? st[MOY_ST_CX0] : 0;
    int cx1 = st[MOY_ST_CX1] < W ? st[MOY_ST_CX1] : W;
    int cy0 = st[MOY_ST_CY0] > 0 ? st[MOY_ST_CY0] : 0;
    int cy1 = st[MOY_ST_CY1] < H ? st[MOY_ST_CY1] : H;
    int x = card.x - (int)st[MOY_ST_CAM_X], y = card.y - (int)st[MOY_ST_CAM_Y];
    memcpy(&st[MOY_ST_CX0], saved, sizeof(saved));
    for (int o = 0; o < card.h; o++) {
        int a0, a1, so = o < split ? o : o + t.h - card.h;
        lent_span(o, r.w, card.h, rr, e, &a0, &a1);
        if (y + o < cy0 || y + o >= cy1 || so >= r.h) {
            continue;
        }
        a0 = x + a0 < cx0 ? cx0 - x : a0;
        a1 = x + a1 > cx1 ? cx1 - x : a1;
        if (a1 > a0) {
            memcpy(px + (size_t)(y + o) * W + x + a0, sv + (size_t)so * r.w + a0,
                   (size_t)(a1 - a0) * sizeof(uint16_t));
        }
    }
}

void mua_lend_stops(moy_ui_ctx_t *c, int dy, int dy_btn) {
    struct moy_ui_lent *l = c->inst->lent;
    for (int i = l->s0; i < c->n_cur; i++) {
        moy_ui_stop_t *p = &c->cur[i];
        int d = (p->flags & STOP_DLG_BTN) ? dy_btn : dy;
        p->b.y = (int16_t)(p->b.y + d);
        if (p->row >= 0 && p->top != INT16_MIN) {
            p->top = (int16_t)(p->top + d);
        }
        if (p->id == c->focus) {
            c->focus_box = p->b;
        }
    }
}

void mua_lend_end(moy_ui_ctx_t *c) {
    c->in[MOY_UI_IN_PTR] = c->inst->lent->ptr;
    mua_lent_drop(c);
}

// The left inset of a popover's body inside its card's band.
static int pop_lp(const moy_ui_ctx_t *c) {
    return c->cls ? mua_kmetric(MOY_UI_K_GROUP, MOY_UI_M_GROUP_PAD) * c->fs
                  : mua_kmetric(MOY_UI_K_ROW, MOY_UI_M_ROW_PAD) * c->fs;
}

// The body has closed, `took` high, its keep `kb` (its peek set): the tall
// card moves to its place (mua_lend_put, its rows where they stand in it),
// the fades of a cut body drawn, and the stops it recorded move with it.
// Where `ok` is 0 (its button row laid out for other widths) only what it
// covered goes back, and the card shows on the next frame.
static void pop_land(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const moy_ui_keep_t *kb,
                     int took, int ok) {
    struct moy_ui_lent *l = c->inst->lent;
    moy_ui_box_t t = l->tall;
    int fs = c->fs, rh = mua_row_h(c), pad = moy_ui_modal_band(fs, c->cls);
    int body = took > 0 ? took : rh, bh;
    moy_ui_box_t card = pop_place(c, kb, body, t.w, &bh);
    c->pop.cut = c->pop.peek = 0;
    c->pop.inside = 0;
    ok = ok && card.h <= t.h;
    // the rows the body shows in: under them the card's own
    mua_lend_put(c, s, card, card.h, card.h - pad - bh, ok);
    c->pop.card = card;
    if (ok) {
        if (bh < took) {
            // a cut body: a fade toward the card at its foot
            moy_canvas_row_t *row = (moy_canvas_row_t *)s->dst;
            int32_t saved[4];
            memcpy(saved, &row->st[MOY_ST_CX0], sizeof(saved));
            int lp = pop_lp(c);
            moy_ui_box_t in = {(int16_t)(card.x + pad - lp), (int16_t)(card.y + pad),
                               (int16_t)(card.w - 2 * (pad - lp)), (int16_t)bh};
            memcpy(&row->st[MOY_ST_CX0], l->clip, sizeof(saved));
            c->fl.susp++;
            mua_edge_fades(c, s, in, took, 0, MOY_UI_FADE_CARD, 1, FADE_H * fs);
            c->fl.susp--;
            memcpy(&row->st[MOY_ST_CX0], saved, sizeof(saved));
        }
        int dy = card.y - t.y;
        mua_lend_stops(c, dy, dy);
        if (l->s0 < c->n_cur && c->cur[l->s0].id == c->pop.id
            && (c->cur[l->s0].flags & STOP_PAGE)) {
            c->cur[l->s0].b.h = (int16_t)bh;        // the body as it shows
        }
    } else {
        c->owe = 1;
        c->inst->owed++;
    }
    mua_lend_end(c);
}

int moy_ui_api_popover(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t id, int w,
                       const moy_ui_over_t *o) {
    o = mua_over(o);
    if (id.n == 0) {
        if (c->n_nest && c->nest[c->n_nest - 1].kind == 3) {
            int used = c->nest[c->n_nest - 1].used;
            moy_ui_keep_t *pk = mua_page_keep(c);
            int took = mua_nest_close(c, s, 3);
            int bw = c->brow_w;
            // a cut body's rows run on: where the cut leaves no row's
            // middle half the fade above it, the next frame cuts at the
            // deepest row middle plus half the fade above it, so the top
            // of a row's words shows over the fade
            int peek = c->pop.cut > 0 && took > c->pop.cut && !c->pop.inside ? c->pop.peek : 0;
            if (mua_lent_of(c, 3) != NULL) {
                if (pk != NULL) {
                    pk->peek = (int16_t)peek;   // its first frame lands cut there
                }
                pop_land(c, s, pk, took, bw == c->brow_was);
            } else if (took != used) {
                c->owe = 1;             // laid out for another body: the next frame redraws
            }
            if (pk != NULL && pk->peek != peek) {
                pk->peek = (int16_t)peek;
                c->owe = 1;
            }
            c->pop.cut = 0;
            if (bw != c->brow_was) {
                c->brow_was = (int16_t)bw;
                c->owe = 1;             // its button row laid out for other widths
            }
            c->brow = 0;
            c->brow_x = c->brow_w = 0;
            c->pop.hide = 0;
        }
        return 0;
    }
    if (c->n_nest >= MOY_UI_API_NEST) {
        return MOY_UI_API_DEEP;
    }
    mua_group_close(c, s);
    c->fl.susp++;                       // an overlay: drawn whole, over the page
    c->fl.dirty = 1;
    c->fl.top = 1;
    // the rect it hangs from: ui.at's, else the one it opened under
    if (c->has_at) {
        c->pop.at = c->at;
        c->pop.view = c->at_view;
        c->has_at = 0;
        c->pop.mid = 0;
        c->pop.placed = 1;
    } else if (c->pop.prev.w == 0) {
        c->pop.at = c->focus_box;
        c->pop.view = c->page;
        c->pop.mid = c->focus_box.w == 0;   // nothing to hang from: centred
        c->pop.placed = 0;
    }
    moy_ui_box_t a = c->pop.at;
    int fs = c->fs, rh = mua_row_h(c);
    uint32_t pid = mua_hash(id.p, id.n, POPOVER_SALT);
    moy_ui_keep_t *kb = mua_keep_of(c, pid);
    int body = kb != NULL && kb->rows > 0 ? kb->rows : rh;
    if (!c->modal) {
        c->owe = 1;                     // its first frame: focus opens in it on the next
    }
    int pad = moy_ui_modal_band(fs, c->cls);
    moy_ui_box_t sf = pop_room(c);
    // a card hung from ui.at's rect may span the surface but for the
    // page's gutters (8 px at the scale, 12 on the desk); any other keeps
    // the modal band each side
    if (w <= 0) {
        w = a.w;
    }
    int edge = pop_edge(c);
    if (w > sf.w - 2 * edge) {
        w = sf.w - 2 * edge;
    }
    if (w < 2 * pad + rh) {
        w = 2 * pad + rh;
    }
    int gap = 4 * fs;
    if (w > sf.w - 2 * gap) {
        w = sf.w - 2 * gap;
    }
    c->pop.cut = 0;
    c->pop.peek = 0;
    c->pop.inside = 0;
    int bh;
    moy_ui_box_t card = pop_place(c, kb, body, w, &bh);
    // no size kept for it yet (its first frame): drawn as tall as the
    // surface lets it, its body laid out in that room, and moved to its
    // place once the body closes (pop_land); where the canvas cannot lend
    // that, its body lays out to size it and nothing draws, the next frame
    // showing it at that size
    c->pop.hide = 0;
    int lent = 0;
    if (kb == NULL) {
        moy_ui_box_t t = {card.x, (int16_t)(sf.y + gap), (int16_t)w, (int16_t)(sf.h - 2 * gap)};
        if (t.h >= 2 * pad + rh && mua_lend(c, s, t, 3)) {
            lent = 1;
            card = t;
            bh = t.h - 2 * pad;
            // the cut its body takes where the room it hangs in cuts it:
            // the room of the side with more of it (below on a tie), the
            // surface's for a centred card, so the rows note their peek
            int y0 = sf.y + gap, y1 = sf.y + sf.h - gap;
            int room = y1 - y0;
            if (!c->pop.mid) {
                int top = a.y + a.h + gap > y0 ? a.y + a.h + gap : y0;
                int foot = a.y - gap < y1 ? a.y - gap : y1;
                room = y1 - top >= foot - y0 ? y1 - top : foot - y0;
            }
            c->pop.cut = (int16_t)(room - 2 * pad > 0 ? room - 2 * pad : 1);
            c->pop.peek = 0;
            c->pop.inside = 0;
        } else {
            c->pop.hide = 1;
            c->owe = 1;
            c->inst->owed++;
        }
    }
    static const uint8_t none[1] = {0};
    if (o->wash == 1) {
        mua_dims(c);
    }
    if (c->pop.hide) {
    } else if (o->wash == 1) {
        mua_wash(c, s);                     // a row's or a card's menu (DESIGN, Menus and washes)
    } else if (o->wash == 2) {
        wash_view(c, s, a);
    }
    if (lent) {
        mua_lend_keep(c, s);
    }
    if (!c->pop.hide) {
        moy_ui_modal(s, card, (moy_ui_span_t){none, 0}, fs, c->cls, rh);
    }
    int lp = pop_lp(c);
    moy_ui_box_t inner = {(int16_t)(card.x + pad - lp), (int16_t)(card.y + pad),
                          (int16_t)(w - 2 * (pad - lp)), (int16_t)bh};
    c->pop.id = pid;
    mua_nest_open(c, 3, pid, inner, body, 0, NULL);
    c->pop.card = card;
    return !c->pop.gone;
}

// -- menus ---------------------------------------------------------------------------

// Field i of a NUL-separated list (empty past its end).
static moy_ui_span_t field_at(const uint8_t *p, size_t len, int i) {
    static const uint8_t none[1] = {0};
    size_t at = 0;
    int k = 0;
    for (size_t j = 0; p != NULL && j <= len; j++) {
        if (j == len || p[j] == 0) {
            if (k == i) {
                return (moy_ui_span_t){p + at, (uint16_t)(j - at)};
            }
            at = j + 1;
            k++;
        }
    }
    return (moy_ui_span_t){none, 0};
}

int32_t moy_ui_api_menu(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t label,
                        const uint8_t *items, size_t len, const uint8_t *icons, size_t ilen,
                        const moy_ui_over_t *o) {
    o = mua_over(o);
    mua_group_close(c, s);
    int fs = c->fs, rh = mua_row_h(c);
    // placed: the rows from ui.at's rect's top left, across its width
    int placed = c->has_at;
    moy_ui_box_t at = c->at;
    c->has_at = 0;
    int ay = at.y;
    if (label.n) {
        int h = mua_kmetric(MOY_UI_K_GROUP, c->cls ? MOY_UI_M_GROUP_CAPTION_DESK
                                               : MOY_UI_M_GROUP_CAPTION) * fs;
        int stacked = 0;
        moy_ui_box_t b = {at.x, (int16_t)ay, at.w, (int16_t)h};
        if (placed) {
            ay += h;
        } else {
            b = mua_place(c, h, &stacked);
        }
        // the caption starts where its rows' icons do: at the rows' pad
        // (moy_ui_vrow's), where the caption's own is a group's
        int rpad = (c->grp_open || c->cls) ? mua_kmetric(MOY_UI_K_GROUP, MOY_UI_M_GROUP_PAD)
                                           : mua_kmetric(MOY_UI_K_ROW, MOY_UI_M_ROW_PAD);
        int dx = (rpad - mua_kmetric(MOY_UI_K_GROUP, MOY_UI_M_GROUP_PAD)) * fs;
        moy_ui_box_t cb = {(int16_t)(b.x + dx), b.y, (int16_t)(b.w - dx), b.h};
        clip_t k;
        EACH_ROW(c, k, s, b, stacked, c->page) {
            moy_ui_caption(s, cb, label, fs, c->cls);
            mua_clip_out(&k);
        }
    } else if (!placed && c->y > 0) {
        int stacked;
        moy_ui_box_t b = mua_place_row(c, mua_rule_h(c), &stacked, 0);
        clip_t k;
        EACH_ROW(c, k, s, b, stacked, c->page) {
            moy_ui_rule(s, b, fs, c->cls);
            mua_clip_out(&k);
        }
    }
    int n = moy_ui_fields(items, len);
    int32_t pick = -1;
    for (int i = 0; i < n; i++) {
        moy_ui_span_t t = field_at(items, len, i);
        moy_ui_span_t ic = field_at(icons, ilen, i);
        if (ic.n) {
            moy_ui_api_icon(c, ic);
        }
        int stacked = 0;
        moy_ui_box_t b;
        if (placed) {
            c->row_slot = c->icon_slot;
            c->row_glyph = c->icon_glyph;
            c->icon_slot = c->icon_glyph = -1;
            b = (moy_ui_box_t){at.x, (int16_t)ay, at.w, (int16_t)rh};
            ay += rh;
        } else {
            b = mua_place(c, rh, &stacked);
        }
        int st = mua_vrow_stop(c, mua_hash(t.p, t.n, 0), b, 0, o, t);
        if (st & MOY_UI_ST_ACTIVATED) {
            pick = i;
        }
        // an item's text after a tab is the key it answers to, drawn as
        // an info row's value
        moy_ui_span_t key = {t.p, 0};
        for (uint16_t j = 0; j < t.n; j++) {
            if (t.p[j] == '\t') {
                key = (moy_ui_span_t){t.p + j + 1, (uint16_t)(t.n - j - 1)};
                t.n = j;
                break;
            }
        }
        if (moy_ui_key_moves(moy_ui_hint_input(), key)) {
            key.n = 0;
        }
        moy_ui_vrow_t r;
        mua_vrow_init(c, &r, t);
        r.value = key;
        r.keys = 1;
        if (i < 32 && ((c->menu_danger >> i) & 1u)) {
            r.kind = MOY_UI_VROW_DANGER;
        }
        mua_vrow_draw(c, s, b, stacked, MOY_UI_V_INFO, st, o, &r);
    }
    c->menu_danger = 0;
    return pick;
}

void moy_ui_api_menu_danger(moy_ui_ctx_t *c, uint32_t rows) {
    c->menu_danger = rows;
}

void moy_ui_api_text(moy_ui_ctx_t *c, int lines, int centre, int tone, int role) {
    c->txt.lines = (int8_t)(lines < 0 ? 0 : lines > 16 ? 16 : lines);
    c->txt.centre = (int8_t)(centre >= 2 && centre <= 4 ? centre : centre != 0);
    c->txt.tone = (int8_t)(tone < 0 || tone > MOY_UI_TONE_DANGER ? 0 : tone);
    c->txt.role = (int8_t)(role < 0 || role > MOY_UI_FONT_RESULT ? -1 : role);
}

void moy_ui_api_text_size(moy_ui_ctx_t *c, int scale, int w) {
    c->txt.scale = (uint8_t)(scale < 0 ? 0 : scale > 16 ? 16 : scale);
    c->txt.w = (int16_t)(w < 0 ? 0 : w > 0x3fff ? 0x3fff : w);
}

void moy_ui_api_card_mark(moy_ui_ctx_t *c, moy_ui_span_t badge, int tone,
                          moy_ui_span_t blank) {
    c->card_slot = (int16_t)(badge.n ? moy_ui_icon_slot(badge.p, badge.n) : -1);
    c->card_glyph = (int16_t)(badge.n ? moy_ui_icon_glyph(badge.p, badge.n) : -1);
    c->card_tone = (int8_t)(tone < 0 || tone > MOY_UI_TONE_LOCKED ? 0 : tone);
    c->card_blank = (int16_t)(blank.n ? moy_ui_icon_slot(blank.p, blank.n) : -1);
    c->card_blank_glyph = (int16_t)(blank.n ? moy_ui_icon_glyph(blank.p, blank.n) : -1);
}

void moy_ui_api_card_lead(moy_ui_ctx_t *c, moy_ui_span_t icon) {
    c->card_lead = (int16_t)(icon.n ? moy_ui_icon_slot(icon.p, icon.n) : -1);
    c->card_lead_glyph = (int16_t)(icon.n ? moy_ui_icon_glyph(icon.p, icon.n) : -1);
}

void moy_ui_api_grid_spread(moy_ui_ctx_t *c, int cols, int foot, int top, int margin,
                            int wrap) {
    c->spread.wrap = (uint8_t)(wrap < 0 ? 0 : wrap > 2 ? 2 : wrap);
    c->spread.margin = (int16_t)(margin < 0 ? 0 : margin);
    c->spread.cols = (uint8_t)(cols < 0 ? 0 : cols > 255 ? 255 : cols);
    c->spread.foot = (int16_t)(foot < 0 ? -1 : foot);
    c->spread.top = (int16_t)(top < 0 ? 0 : top);
}

int moy_ui_api_note(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t icon,
                    const uint8_t *lines, size_t n) {
    mua_grid_end(c, s);
    int slot = moy_ui_icon_slot(icon.p, icon.n), glyph = moy_ui_icon_glyph(icon.p, icon.n);
    int warn = icon.n == 4 && memcmp(icon.p, "warn", 4) == 0;
    int pf = mua_ground_of(c) | (c->tap ? MOY_UI_TAP : 0);
    moy_ui_box_t m = c->has_at ? c->at : c->page;
    int h = moy_ui_note(s, m, slot, glyph, warn, lines, n, c->fs, pf, 0);
    int stacked;
    moy_ui_box_t b = mua_place(c, h, &stacked);
    b.x = m.x;
    b.w = m.w;
    clip_t k;
    EACH_ROW(c, k, s, b, stacked, c->page) {
        moy_ui_note(s, b, slot, glyph, warn, lines, n, c->fs, pf, 1);
        mua_clip_out(&k);
    }
    return b.y + h;
}

int moy_ui_api_empty(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t icon,
                     moy_ui_span_t title, const uint8_t *lines, size_t n) {
    mua_grid_end(c, s);
    int slot = moy_ui_icon_slot(icon.p, icon.n), glyph = moy_ui_icon_glyph(icon.p, icon.n);
    moy_ui_box_t m = c->has_at ? c->at : c->page;
    int h = moy_ui_empty(s, m, slot, glyph, title, lines, n, c->fs, mua_ground_of(c), 0);
    int stacked;
    moy_ui_box_t b = mua_place(c, h, &stacked);
    b.x = m.x;
    b.w = m.w;
    clip_t k;
    EACH_ROW(c, k, s, b, stacked, c->page) {
        moy_ui_empty(s, b, slot, glyph, title, lines, n, c->fs, mua_ground_of(c), 1);
        mua_clip_out(&k);
    }
    return b.y + h;
}

void moy_ui_api_bubble(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t text,
                       moy_ui_span_t head, moy_ui_span_t status, const int32_t *opt, int n,
                       const moy_ui_over_t *o, int32_t out[5]) {
    o = mua_over(o);
    mua_grid_end(c, s);
    int32_t v[MOY_UI_BBO_WORDS] = {0, -1, 0, 75, 4, 0};
    for (int i = 0; opt != NULL && i < n && i < MOY_UI_BBO_WORDS; i++) {
        v[i] = opt[i];
    }
    moy_ui_bubble_t bb = {text, head, status, (int16_t)(v[MOY_UI_BBO_SIDE] != 0),
                          (int16_t)(v[MOY_UI_BBO_SIGNAL] < 0 ? -1 : v[MOY_UI_BBO_SIGNAL] > 4
                                                                       ? 4 : v[MOY_UI_BBO_SIGNAL]),
                          (int16_t)v[MOY_UI_BBO_TONE], (int16_t)v[MOY_UI_BBO_MAX],
                          (int16_t)(v[MOY_UI_BBO_LINES] < 0 ? 0 : v[MOY_UI_BBO_LINES]), 0};
    int placed = c->has_at, g = (c->cls ? 12 : 8) * c->fs;
    moy_ui_box_t room = placed ? c->at
                               : (moy_ui_box_t){(int16_t)(c->page.x + g), 0,
                                                (int16_t)(c->page.w - 2 * g), 0};
    moy_ui_box_t box;
    int cut = 0;
    int h = moy_ui_bubble(s, room, &bb, c->fs, mua_ground_of(c) | (c->tap ? MOY_UI_TAP : 0), 0, &box, &cut);
    int gap = (c->cls ? 6 : 4) * c->fs - mua_kmetric(MOY_UI_K_ROW, MOY_UI_M_ROW_STACK_GAP) * c->fs;
    int stacked;
    moy_ui_box_t b = mua_place(c, placed ? h : h + (gap > 0 ? gap : 0), &stacked);
    room.y = box.y = b.y;
    b.h = (int16_t)h;
    int st = mua_stop(c, mua_id_of(c, o, text), box, 0, mua_name_of(o, text));
    st = st < 0 ? 0 : st;
    bb.flags = mua_mark_flags(st, o) | (v[MOY_UI_BBO_ANCHOR] ? MOY_UI_BUBBLE_ANCHOR : 0);
    clip_t k;
    EACH_ROW(c, k, s, b, stacked, c->page) {
        moy_ui_bubble(s, room, &bb, c->fs, mua_ground_of(c) | (c->tap ? MOY_UI_TAP : 0), 1, NULL, NULL);
        mua_clip_out(&k);
    }
    out[0] = box.x;
    out[1] = box.y;
    out[2] = box.w;
    out[3] = (int32_t)h;                // the block: the bubble and its status line
    out[4] = st | (cut ? MOY_UI_ST_CUT : 0);
}

int moy_ui_api_month(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t title,
                     moy_ui_span_t days, int first, int n, int today) {
    int weeks = (first + n + 6) / 7;
    int h = moy_ui_month_h(weeks, c->fs, c->cls);
    int stacked;
    moy_ui_box_t b;
    if (c->has_at) {
        b = c->at;
        c->has_at = 0;
        stacked = 0;
    } else {
        mua_group_close(c, s);
        b = mua_place(c, h, &stacked);
        int pad = mua_kmetric(MOY_UI_K_ROW, MOY_UI_M_ROW_PAD) * c->fs;
        b.x = (int16_t)(b.x + pad);
        b.w = (int16_t)(b.w - 2 * pad);
        // stacked past the page's foot (a popover's card shorter than its weeks): they tighten into it
        int room = c->page.y + c->page.h - b.y;
        if (room > 0 && room < b.h)
            b.h = (int16_t)room;
    }
    int chevrons = c->cls || moy_ui_input() == MOY_UI_INPUT_TOUCH;
    moy_ui_box_t ch[2] = {{0, 0, 0, 0}, {0, 0, 0, 0}};
    clip_t k;
    EACH_ROW(c, k, s, b, stacked, c->page) {
        moy_ui_month(s, b, title, days, first, n, today, chevrons, c->fs, c->cls, ch);
        mua_clip_out(&k);
    }
    // a press on a chevron pages the month
    int p = c->in[MOY_UI_IN_PTR];
    if (chevrons && (p & MOY_UI_P_LIVE) && (p & MOY_UI_P_EDGE)) {
        int x = c->in[MOY_UI_IN_X], y = c->in[MOY_UI_IN_Y];
        for (int i = 0; i < 2; i++) {
            if (mua_inside(ch[i], x, y)) {
                return i ? 1 : -1;
            }
        }
    }
    return 0;
}

void moy_ui_api_toast(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t text,
                      moy_ui_span_t kind, int flat, int32_t out[4]) {
    moy_ui_box_t m = c->page;
    if (c->has_at) {
        m = c->at;
        c->has_at = 0;
    } else {
        m.y = (int16_t)(m.y + 8 * c->fs);
        m.h = (int16_t)(m.h - 16 * c->fs);
    }
    static const uint8_t check[] = "check";
    moy_ui_span_t ic = kind.n ? kind : (moy_ui_span_t){check, 5};
    int slot = moy_ui_icon_slot(ic.p, ic.n), glyph = moy_ui_icon_glyph(ic.p, ic.n);
    moy_ui_box_t p = {0, 0, 0, 0};
    c->fl.dirty = 1;                    // over the page, whole
    c->fl.top = 1;
    moy_ui_toast(s, m, text, slot, glyph, c->fs, mua_ground_of(c), flat, &p);
    if (out != NULL) {
        out[0] = p.x;
        out[1] = p.y;
        out[2] = p.w;
        out[3] = p.h;
    }
}

// -- card grids ----------------------------------------------------------------------

// The card drawn last: its picture finished over what the app drew in it.
void mua_card_finish(moy_ui_ctx_t *c, const moy_ui_sink_t *s) {
    if (!c->fin_on) {
        return;
    }
    c->fin_on = 0;
    clip_t k;
    c->fl.cast = 1;
    EACH_ROW(c, k, s, c->fin_content, c->grid_open == 1, c->page) {
        if (c->fin_slot >= 0 || c->fin_glyph >= 0 || c->fin_tone == MOY_UI_TONE_DANGER
            || c->fin_tone == MOY_UI_TONE_LOCKED) {
            moy_ui_card_badge(s, c->fin_content, c->fin_slot, c->fin_glyph, c->fin_tone,
                              c->fin_ground, c->fs, mua_ground_of(c));
        }
        moy_ui_card_end(s, c->fin_pic, c->fin_content, c->fin_flags ? MOY_UI_F_FOCUS : 0,
                        c->fin_ground, c->fs, mua_ground_of(c));
        mua_clip_out(&k);
    }
}

// The open grid ends: its last card finished, the page's cursor under its
// last row, and a group it opened in holding its rows' card from there.
void mua_grid_end(moy_ui_ctx_t *c, const moy_ui_sink_t *s) {
    if (!c->grid_open) {
        return;
    }
    mua_card_finish(c, s);
    if (c->grid_open == 1) {
        if (c->grid_i > 0) {
            c->y = (int16_t)(c->grid_y + c->grid_row + c->grid_tall);
        }
        moy_ui_keep_t *k = mua_page_keep(c);
        if (k != NULL) {
            k->rows = c->y;
        }
        if (c->grp_open && c->grp_n == 0) {
            c->grp_top = c->y;
        }
    }
    c->grid_open = 0;
}

void moy_ui_api_grid(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t id, int w, int h,
                     const moy_ui_over_t *o) {
    (void)mua_over(o);
    mua_grid_end(c, s);
    if (id.n == 0) {
        return;
    }
    int fs = c->fs;
    if (w <= 0) {
        w = 48 * fs;
    }
    if (h <= 0) {
        h = w * 3 / 4;
    }
    if (c->grp_open && c->grp_n > 0) {
        mua_group_close(c, s);          // a grid lies on the page's ground
    }
    int pad = mua_pmetric(c, MOY_UI_M_VALUE_ROW_CARD_PAD);
    int gap = mua_pmetric(c, MOY_UI_M_VALUE_ROW_CARD_GAP);
    moy_ui_box_t area;
    if (c->has_at) {
        area = c->at;
        c->has_at = 0;
        c->grid_open = 2;
        c->grid_y = area.y;
    } else {
        area = c->page;
        c->grid_open = 1;
        c->y = (int16_t)(c->y + (c->spread.top > 0
                                     ? c->spread.top * c->fs
                                     : mua_pmetric(c, MOY_UI_M_VALUE_ROW_GRID_TOP)));
        c->grid_y = c->y;
    }
    int cols = (area.w - 2 * pad + gap) / (w + gap);
    cols = cols < 1 ? 1 : cols > 255 ? 255 : cols;
    int span = cols * w + (cols - 1) * gap;
    c->grid_cols = (uint8_t)cols;
    c->grid_i = 0;
    c->grid_x = (int16_t)(area.x + (area.w - span) / 2);
    c->grid_pitch = (int16_t)(w + gap);
    int foot = mua_pmetric(c, MOY_UI_M_VALUE_ROW_CARD_FOOT);
    if (c->spread.cols > 0) {
        // the columns spread across the rect, the gaps taking the rest
        cols = c->spread.cols;
        int m = c->spread.margin * c->fs;
        c->grid_cols = (uint8_t)cols;
        c->grid_x = (int16_t)(area.x + m);
        c->grid_pitch = (int16_t)(cols > 1 ? (area.w - 2 * m - w) / (cols - 1) : w);
        c->spread.cols = 0;
    }
    if (c->spread.foot != 0) {
        foot = c->spread.foot < 0 ? 0 : c->spread.foot * c->fs;
    }
    c->spread.foot = c->spread.top = c->spread.margin = 0;
    c->grid_wrap = c->spread.wrap;
    c->grid_tall = 0;
    c->spread.wrap = 0;
    c->grid_w = (int16_t)w;
    c->grid_h = (int16_t)h;
    c->grid_row = (int16_t)(mua_pmetric(c, MOY_UI_M_VALUE_ROW_CARD_TOP) + h + foot
                            + mua_pmetric(c, MOY_UI_M_VALUE_ROW_GRID_GAP));
}

void moy_ui_api_card(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t title,
                     moy_ui_span_t sub, const moy_ui_over_t *o, int32_t out[5]) {
    o = mua_over(o);
    mua_card_finish(c, s);
    memset(out, 0, 5 * sizeof(int32_t));
    c->pic_clip = (moy_ui_box_t){0, 0, 0, 0};
    c->pic_tbl = 0;
    if (!c->grid_open) {
        return;
    }
    int col = c->grid_i % c->grid_cols;
    if (col == 0 && c->grid_i > 0) {
        c->grid_y = (int16_t)(c->grid_y + c->grid_row + c->grid_tall);
        c->grid_tall = 0;
    }
    int pad = mua_pmetric(c, MOY_UI_M_VALUE_ROW_CARD_PAD), top = mua_pmetric(c, MOY_UI_M_VALUE_ROW_CARD_TOP);
    // a card's labels may run as wide as its column's pitch less a pad
    // either side, past the card no further than its draw reaches (a
    // shadow's 8 px at the scale, mua_clip_row); never narrower than the card
    int lw = c->grid_pitch - 2 * pad, most = c->grid_w + 2 * pad + 16 * c->fs;
    lw = lw > most ? most : lw < c->grid_w + 2 * pad ? c->grid_w + 2 * pad : lw;
    // a fitted grid's row is as tall as its tallest card: a title broken
    // onto a second line grows its card and its row by that line
    int tall = c->grid_wrap == 2 ? moy_ui_card_wrap(s, lw, title, c->fs, mua_ground_of(c)) : 0;
    int grew = tall > c->grid_tall;
    if (grew) {
        c->grid_tall = (uint8_t)(tall > 255 ? 255 : tall);
    }
    if ((col == 0 || grew) && c->grid_open == 1) {
        c->y = (int16_t)(c->grid_y + c->grid_row + c->grid_tall);
        moy_ui_keep_t *k = mua_page_keep(c);
        if (k != NULL) {
            k->rows = c->y;
        }
    }
    if (c->grid_i < 0xffff) {
        c->grid_i++;
    }
    c->icon_slot = c->icon_glyph = -1;
    int stacked = c->grid_open == 1;
    int y = stacked ? c->page.y + c->grid_y - c->scroll : c->grid_y;
    moy_ui_box_t pic = {(int16_t)(c->grid_x + col * c->grid_pitch), (int16_t)(y + top), c->grid_w,
                        c->grid_h};
    moy_ui_box_t b = {(int16_t)(pic.x - pad), (int16_t)y, (int16_t)(pic.w + 2 * pad),
                      (int16_t)(c->grid_row + tall - mua_pmetric(c, MOY_UI_M_VALUE_ROW_GRID_GAP))};
    int st = 0, moved = 0;
    c->at_last = (uint8_t)!stacked;
    if (o->disabled != 1) {
        st = mua_stop(c, mua_id_of(c, o, title), b, 0, mua_name_of(o, title));
        if (st >= 0) {
            // a blank card's picture is the engine's tile: the app draws none
            moved = mua_pic_note(c, o, c->card_blank < 0 && c->card_blank_glyph < 0);
            c->cur[c->n_cur - 1].flags |= STOP_GRID;
            mua_sig_mix(c, sub.p, sub.n);
        }
        st = st < 0 ? 0 : st;
    }
    int f = mua_mark_flags(st, o);
    // a card in a popover's body lies on its panel
    int gnd = mua_ground_of(c) | (c->n_nest && c->nest[c->n_nest - 1].kind == 3 ? MOY_UI_PANEL : 0);
    clip_t k;
    moy_ui_box_t content = pic;
    uint16_t g = 0;
    int any = 0;
    if (moved) {
        // where the card puts its picture: measured under an empty clip
        moy_canvas_row_t *row = (moy_canvas_row_t *)s->dst;
        int32_t saved[4];
        memcpy(saved, &row->st[MOY_ST_CX0], sizeof(saved));
        row->st[MOY_ST_CX1] = row->st[MOY_ST_CX0];
        moy_ui_card(s, b, pic, lw, title, sub, f | (c->grid_wrap ? MOY_UI_F_WRAP : 0), c->fs,
                    gnd, c->card_tone, c->card_lead, c->card_lead_glyph, &content, &g);
        memcpy(&row->st[MOY_ST_CX0], saved, sizeof(saved));
        rc_t q = mua_rc_of(content);
        if (!stacked || mua_rc_cut(&q, mua_rc_of(c->page))) {
            mua_pic_redraw(c, mua_box_of(q));   // (a stacked card's: what its region shows)
        }
    }
    c->fl.cast = 1;
    EACH_ROW(c, k, s, b, stacked, c->page) {
        moy_ui_card(s, b, pic, lw, title, sub, f | (c->grid_wrap ? MOY_UI_F_WRAP : 0), c->fs,
                    gnd, c->card_tone, c->card_lead, c->card_lead_glyph, &content, &g);
        if (c->card_blank >= 0 || c->card_blank_glyph >= 0) {
            moy_ui_card_blank(s, content, c->card_blank, c->card_blank_glyph, c->card_tone,
                              c->fs, gnd);
        }
        any = 1;
    }
    if (!any) {
        out[4] = st;
        c->card_slot = c->card_glyph = c->card_blank = c->card_blank_glyph = -1;
        c->card_lead = c->card_lead_glyph = -1;
        c->card_tone = 0;
        return;                     // scrolled out of view: nothing to draw into
    }
    c->fin_slot = c->card_slot;
    c->fin_glyph = c->card_glyph;
    c->fin_tone = c->card_tone;
    c->card_slot = c->card_glyph = c->card_blank = c->card_blank_glyph = -1;
    c->card_lead = c->card_lead_glyph = -1;
    c->card_tone = 0;
    c->fin_on = 1;
    c->fin_flags = (uint8_t)(f & MOY_UI_F_FOCUS ? 1 : 0);
    c->fin_ground = g;
    c->fin_pic = pic;
    c->fin_content = content;
    out[4] = st;
    if (mua_outside_floor(c, b)) {
        return;                     // a shift frame's: what the app drew there stands
    }
    c->pic_clip = mua_pic_clip(c, content);
    c->pic_tbl = 0;
    out[0] = content.x;
    out[1] = content.y;
    out[2] = content.w;
    out[3] = content.h;
}

int moy_ui_api_table_rows(const moy_ui_ctx_t *c, int32_t out[8]) {
    out[0] = c->tbl.y0;
    out[1] = c->tbl.rh;
    out[2] = c->tbl.view.x;
    out[3] = c->tbl.view.y;
    out[4] = c->tbl.view.w;
    out[5] = c->tbl.view.h;
    out[6] = c->tbl.px;
    out[7] = c->tbl.pw;
    return c->tbl.pw > 0;
}

void moy_ui_api_table_pics(moy_ui_ctx_t *c, const moy_ui_sink_t *s) {
    if (c->tbl.pw <= 0) {
        return;
    }
    moy_ui_box_t v = c->tbl.view;
    moy_ui_box_t pic = {c->tbl.px, v.y, c->tbl.pw, v.h};
    mua_edge_fades(c, s, pic, c->tbl.n * c->tbl.rh, v.y - c->tbl.y0, MOY_UI_DEFAULT, 1, c->tbl.rh);
}

// The tooltip a resting pointer earned this frame (tip_set), over everything.
static void tip_draw(moy_ui_ctx_t *c, const moy_ui_sink_t *s) {
    if (c->tip_at.w > 0 && c->tip[0]) {
        moy_ui_span_t t = {(const uint8_t *)c->tip, (uint16_t)strlen(c->tip)};
        c->fl.dirty = 1;                // over the page, whole
        c->fl.top = 1;
        moy_ui_tip_draw(s, c->tip_at, t, c->surface, c->fs, mua_ground_of(c));
        c->tip_at.w = 0;
        c->tip_shown = 1;
    }
}

void moy_ui_api_page_done(moy_ui_ctx_t *c, const moy_ui_sink_t *s) {
    if (c->n_nest == 0) {
        moy_ui_keep_t *k = mua_page_keep(c);
        if (k != NULL && !c->no_foot) {
            // a page whose rows run past it: its thumb, as a scroll region's (mua_nest_close)
            mua_thumb_track(c, k, c->page, k->rows, c->scroll);
            mua_thumb(c, s, c->page, k->rows, c->scroll);
        }
        mua_page_close(c, s);
        tip_draw(c, s);
        mua_dialog_gone(c);
    }
}

void moy_ui_api_end(moy_ui_ctx_t *c, const moy_ui_sink_t *s) {
    mua_parts_close(c, s);
    if (c->n_nest == 0) {
        mua_group_close(c, s);
        mua_foot_fade(c, s);
        mua_page_close(c, s);
        tip_draw(c, s);
        mua_dialog_gone(c);
    }
}

// -- an empty page, tools, the app's bar ----------------------------------------------

// The words of a tool's label before its tab, and the tooltip: the label
// with the tab as two spaces.
static moy_ui_span_t tool_word(moy_ui_span_t label) {
    moy_ui_span_t w = label;
    for (uint16_t i = 0; i < label.n; i++) {
        if (label.p[i] == '\t') {
            w.n = i;
            break;
        }
    }
    return w;
}

// A resting pointer's tooltip over box b, on the desk, where stop state st
// holds the hover: the label, its tab as two spaces before its key.
static void tip_set(moy_ui_ctx_t *c, moy_ui_box_t b, int st, moy_ui_span_t label) {
    if (!c->cls || !(st & MOY_UI_ST_HOVER) || moy_ui_input() == MOY_UI_INPUT_TOUCH) {
        return;
    }
    size_t n = 0;
    for (uint16_t i = 0; i < label.n && n < MOY_UI_API_TIP - 2; i++) {
        if (label.p[i] == '\t') {
            c->tip[n++] = ' ';
            c->tip[n++] = ' ';
        } else {
            c->tip[n++] = (char)label.p[i];
        }
    }
    c->tip[n] = 0;
    c->tip_at = b;
}

int moy_ui_api_tool(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t icon,
                    moy_ui_span_t label, const moy_ui_over_t *o) {
    o = mua_over(o);
    int slot = moy_ui_icon_slot(icon.p, icon.n), glyph = moy_ui_icon_glyph(icon.p, icon.n);
    moy_ui_span_t word = tool_word(label);
    int stacked;
    moy_ui_box_t b = mua_place(c, mua_row_h(c), &stacked);
    int disabled = o->disabled == 1;
    int st = disabled ? 0 : mua_stop(c, mua_id_of(c, o, word), b, 0, mua_name_of(o, word));
    if (st < 0) {
        st = 0;
    }
    clip_t k;
    EACH_ROW(c, k, s, b, stacked, c->page) {
        int fl = mua_mark_flags(st, o) | (disabled ? MOY_UI_F_DISABLED : 0);
        moy_ui_tool_draw(s, b, slot, glyph, word, fl, mua_interact(st), c->fs, mua_ground_of(c));
        mua_clip_out(&k);
    }
    tip_set(c, b, st, label);
    return (st & MOY_UI_ST_ACTIVATED) != 0;
}

void moy_ui_api_tip(moy_ui_ctx_t *c, const moy_ui_over_t *o, moy_ui_span_t label) {
    o = mua_over(o);
    if (o->id.p == NULL || c->n_cur == 0 || label.n == 0) {
        return;
    }
    const moy_ui_stop_t *t = &c->cur[c->n_cur - 1];
    if (t->id == mua_id_of(c, o, label) && !(t->flags & STOP_PAGE)) {
        tip_set(c, t->b, t->st, label);
    }
}

int32_t moy_ui_api_bar(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_span_t title,
                       const uint8_t *tools, size_t len, uint32_t off) {
    (void)s;
    size_t n = title.n < MOY_UI_API_TIP - 1 ? title.n : MOY_UI_API_TIP - 1;
    if (n) {
        memcpy(c->bar.title, title.p, n);
    }
    c->bar.title[n] = 0;
    int k = moy_ui_fields(tools, len);
    k = k < MOY_UI_API_BAR ? k : MOY_UI_API_BAR;
    c->bar.chip[0] = 0;
    c->bar.chip_at = -1;
    for (int i = 0; i < k; i++) {
        moy_ui_span_t t = field_at(tools, len, i);
        c->bar.slot[i] = (int16_t)moy_ui_icon_slot(t.p, t.n);
        if (c->bar.slot[i] < 0 && t.n) {
            size_t m = t.n < MOY_UI_API_CHIP - 1 ? t.n : MOY_UI_API_CHIP - 1;
            memcpy(c->bar.chip, t.p, m);
            c->bar.chip[m] = 0;
            c->bar.chip_at = (int8_t)i;
        }
    }
    c->bar.n = (uint8_t)k;
    c->bar.off = (uint8_t)(off & ((1u << MOY_UI_API_BAR) - 1u));
    c->bar.back = (off & MOY_UI_BAR_BACK) != 0;
    c->bar.seen = 1;
    int32_t got = c->bar.act;
    c->bar.act = -1;
    if (got == MOY_UI_BAR_UP) {
        return c->bar.back ? got : -1;
    }
    if (got >= k || (got >= 0 && (c->bar.off >> got) & 1u)) {
        got = -1;
    }
    return got;
}

void moy_ui_api_status_band(moy_ui_ctx_t *c, const moy_ui_sink_t *s, moy_ui_box_t b) {
    clip_t k;
    EACH_PIECE(c, k, s, b) {
        moy_ui_status(s, b, (const uint8_t *)"", 0, 0, c->fs);
    }
}

void moy_ui_api_rule(moy_ui_ctx_t *c, const moy_ui_sink_t *s) {
    if (c->has_at) {
        moy_ui_box_t b = c->at;
        c->has_at = 0;
        if (b.h > b.w) {
            b.w = (int16_t)c->fs;
        } else {
            b.h = (int16_t)c->fs;
        }
        clip_t k;
        EACH_PIECE(c, k, s, b) {
            moy_ui_line(s, b, c->fs, mua_ground_of(c));
        }
        return;
    }
    mua_group_close(c, s);
    int stacked;
    moy_ui_box_t r = mua_place(c, mua_rule_h(c), &stacked);
    clip_t k;
    EACH_ROW(c, k, s, r, stacked, c->page) {
        moy_ui_rule(s, r, c->fs, c->cls);
        mua_clip_out(&k);
    }
}

void moy_ui_api_card_at(moy_ui_ctx_t *c, const moy_ui_sink_t *s) {
    if (!c->has_at) {
        return;
    }
    moy_ui_box_t b = c->at;
    c->has_at = 0;
    int flags = mua_ground_of(c) | MOY_UI_CARDED;
    moy_ui_box_t rows = b, last = b;
    if (flags & MOY_UI_DESK) {
        // the ring's foot a pixel under its last row: that row ends a pixel
        // inside the box, and the sides stop where the foot's corners begin
        last.h = (int16_t)(b.h - c->fs);
        rows.h = (int16_t)(last.h - moy_ui_group_r(c->fs));
    }
    clip_t k;
    EACH_PIECE(c, k, s, b) {
        moy_ui_group_band(s, b, rows, 1, c->fs, flags);
        moy_ui_group_end(s, b, last, 0, c->fs, flags);
    }
}

int moy_ui_api_bar_lent(const moy_ui_ctx_t *c, const char **title, int16_t *slots, int *n,
                        uint32_t *off) {
    if (!c->bar.seen) {
        if (!c->page_title[0]) {
            return 0;
        }
        *title = c->page_title;     // a page's title, with nothing more lent
        *n = 0;
        *off = 0;
        return 1;
    }
    *title = c->bar.title[0] ? c->bar.title : c->page_title;
    for (int i = 0; i < c->bar.n; i++) {
        slots[i] = c->bar.slot[i];
    }
    *n = c->bar.n;
    *off = c->bar.off | (c->bar.back ? MOY_UI_BAR_BACK : 0u);
    return 1;
}

const char *moy_ui_api_bar_chip(const moy_ui_ctx_t *c, int *at) {
    *at = c->bar.seen ? c->bar.chip_at : -1;
    return *at >= 0 ? c->bar.chip : "";
}

void moy_ui_api_bar_tap(moy_ui_ctx_t *c, int i) {
    c->bar.act = (int8_t)((i >= 0 && i < MOY_UI_API_BAR) || i == MOY_UI_BAR_UP ? i : -1);
}

int moy_ui_api_back(moy_ui_ctx_t *c, int take) {
    if (moy_ui_api_cancel(c, take)) {
        return 1;
    }
    if (c->bar.seen && c->bar.back) {
        if (take) {
            c->bar.act = MOY_UI_BAR_UP;
        }
        return 1;
    }
    return 0;
}

int moy_ui_api_owes(const moy_ui_ctx_t *c) {
    return c->owe;
}

int moy_ui_api_moved(const moy_ui_ctx_t *c) {
    return c->moved;
}

int moy_ui_api_moving(const moy_ui_ctx_t *c) {
    for (int i = 0; i < MOY_UI_API_KEEP; i++) {
        if (c->keep[i].id && moy_ui_scroll_moving(&c->keep[i].sc)) {
            return 1;
        }
    }
    return 0;
}

int32_t moy_ui_api_offset(moy_ui_ctx_t *c, int x, int y) {
    int pg = mua_page_at(c->cur, c->n_cur, x, y);
    moy_ui_keep_t *k = pg >= 0 ? mua_keep_of(c, c->cur[pg].id) : NULL;
    return k != NULL ? k->scroll : -1;
}

// -- a carousel (ui.cards look "carousel") ----------------------------------------------
//
// The handheld home's band (`home_ui.band`, runtime/home/home_carousel.py) as the engine
// draws and moves it: its geometry, its tiles, the caption under them and its motion (a
// step, a drag, a fling and the slide to the nearest card, moy_ui_api_table.c).

#define CAROUSEL_COVER 128          // a cover's side (SPEC.md 3.6)
#define CAROUSEL_GAP 14             // the gap between tiles, at the font scale
#define CAROUSEL_SQUEEZE_A 2        // the least over and under the caption, at the font scale
#define CAROUSEL_SQUEEZE_B 4
// A version 2 face's caption lines at the font scale (the title's at its own scale): the
// title's line and its baseline, the sub line's baseline under the title's, its line and
// its baseline.
static const int16_t CAROUSEL_LINES[5] = {24, 19, 17, 15, 12};

static int floor_div(int a, int b) {
    return a >= 0 ? a / b : -((-a + b - 1) / b);
}

int moy_ui_api_clean_side(int limit) {
    if (limit >= CAROUSEL_COVER) {
        return limit / CAROUSEL_COVER * CAROUSEL_COVER;
    }
    int side = CAROUSEL_COVER / 2;
    while (side > CAROUSEL_COVER / 8 && side > limit) {
        side /= 2;
    }
    return side;
}

// The font a carousel's title draws in (the hero face where one is installed, else the
// title role's) and the sub line's (the ui role's), each with its metrics.
static uint32_t carousel_font(int role, moy_font_info_t *fi) {
    return moy_ui_font(0, role, fi);
}

// Whether font `id` is a version 2 face: anti-aliased, its line holding its leading
// (`ui_draw.font_v2`).
static int font_v2(uint32_t id, const moy_font_info_t *fi) {
    return id != MOY_FONT_PETME128 && fi->first == 0;
}

void moy_ui_api_carousel_geom(int fs, const int32_t b[4], int side, int32_t out[10]) {
    moy_font_info_t tf, uf;
    uint32_t tid = carousel_font(MOY_UI_FONT_HERO, &tf);
    uint32_t uid = carousel_font(MOY_UI_FONT_UI, &uf);
    int tl = tf.line > 0 ? tf.line : 1;
    int tsc = (16 * fs) / tl;
    tsc = tsc > fs ? tsc : fs;
    int title_h, meta_h, between, above, below;
    int v2 = font_v2(tid, &tf);
    if (v2) {
        const int16_t *L = CAROUSEL_LINES;
        title_h = L[0] * tsc;
        meta_h = L[3] * fs;
        between = L[1] * tsc + (L[2] - L[4]) * fs - title_h;
        above = 6 * fs;
        below = 10 * fs;
    } else {
        title_h = tf.line * tsc;
        meta_h = uf.line * fs;
        above = 12 * fs;
        between = 3 * fs;
        below = 4 * fs;
    }
    int reach = moy_ui_mark_reach(MOY_UI_ITEM_CARD);
    int ring = 2 * fs + 2 > reach ? 2 * fs + 2 : reach;
    int space = b[3];
    // the gaps give before the tile does: a face taller than the targets' takes its pixels
    // from over and under the caption, down to the squeeze, and only what the gaps cannot
    // hold steps the tile down
    int text = title_h + between + meta_h;
    int lo0 = CAROUSEL_SQUEEZE_A * fs, lo1 = CAROUSEL_SQUEEZE_B * fs;
    int card = moy_ui_api_clean_side(side);
    while (card > CAROUSEL_COVER / 8 && ring + 2 * card + text + lo0 + lo1 > space) {
        card = moy_ui_api_clean_side(card - 1);
    }
    int short_ = ring + 2 * card + text + above + below - space;
    if (short_ > 0) {
        int room = above + below - lo0 - lo1;
        int give = short_ < room ? short_ : room;
        int cut = give * (above - lo0) / (room > 1 ? room : 1);
        above -= cut;
        below -= give - cut;
    }
    int foot = above + text + below;
    int top = floor_div(space - 2 * card - foot, 2);
    top = b[1] + (ring > top ? ring : top);
    int title_y = top + 2 * card + above;
    int meta_y = title_y + title_h + between;
    if (v2) {
        meta_y += (CAROUSEL_LINES[4] - uf.ascent) * fs;
        title_y += (CAROUSEL_LINES[1] - tf.ascent) * tsc;
    }
    (void)uid;
    out[0] = card;
    out[1] = card + CAROUSEL_GAP * fs;      // the pitch
    out[2] = top + card;                    // the tiles' centre line
    out[3] = title_y;
    out[4] = title_h;
    out[5] = tsc;
    out[6] = meta_y;
    out[7] = meta_h;
    out[8] = 2 * card;                      // the centre tile's side at rest
    out[9] = ring;
}

void moy_ui_api_carousel_tile(const int32_t g[10], const int32_t b[4], int32_t offset, int i,
                              int32_t out[4]) {
    int32_t card = g[0], pitch = g[1] > 0 ? g[1] : 1, big = g[8];
    int32_t d = i * pitch - offset, ad = d < 0 ? -d : d;
    int32_t t = ad >= pitch ? card : card + (big - card) * (pitch - ad) / pitch;
    int32_t push = (big - card) * (ad < pitch ? ad : pitch) / (2 * pitch);
    d += d > 0 ? push : -push;
    out[0] = b[0] + b[2] / 2 + d - t / 2;
    out[1] = g[2] - t / 2;
    out[2] = t;
    out[3] = t;
}

int moy_ui_api_carousel_at(const int32_t g[10], const int32_t b[4], int32_t offset, int n, int x,
                           int y) {
    int32_t pitch = g[1] > 0 ? g[1] : 1, reach = b[2] / 2 + 2 * g[0];
    int32_t most = (n - 1) * pitch, at = offset < most ? offset : most;
    int near = (int)floor_div(at + pitch / 2, pitch);
    near = near < 0 ? 0 : near > n - 1 ? n - 1 : near;
    int i0 = (int)floor_div(offset - reach, pitch), i1 = (int)floor_div(offset + reach, pitch) + 1;
    i0 = i0 > 0 ? i0 : 0;
    i1 = i1 < n - 1 ? i1 : n - 1;
    int got = -1;
    int32_t gk = -1, t[4];
    for (int i = i0; i <= i1; i++) {
        moy_ui_api_carousel_tile(g, b, offset, i, t);
        int32_t k = 2 * t[2] + (i == near);
        if (t[0] <= x && x < t[0] + t[2] && t[1] <= y && y < t[1] + t[3] && k >= gk) {
            got = i;
            gk = k;
        }
    }
    return got;
}

// A tile's corner radius `side` across in a row of `card`: the depth's card radius on the
// hero, 7/10 of it on a neighbour.
static int tile_r(int side, int card) {
    int r = moy_ui_depth()->card_r;
    if (card < 0) {
        return side > -card ? r * 7 / 5 : r;    // the desk's: a hero's 7/5 of a shelf card's
    }
    return side > card ? r : r * 7 / 10;
}

int moy_ui_api_tile_radius(int side, int card) {
    return tile_r(side, card);
}

void moy_ui_api_tile_cast(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t t[4],
                          const int32_t clip[4], int centre) {
    (void)c;
    clip_t k;
    moy_ui_box_t q = {(int16_t)clip[0], (int16_t)clip[1], (int16_t)clip[2], (int16_t)clip[3]};
    if (mua_clip_in(&k, s, q)) {
        moy_ui_box_t b = {(int16_t)t[0], (int16_t)t[1], (int16_t)t[2], (int16_t)t[3]};
        moy_ui_cast(s, b, MOY_UI_CAST_CARD, centre ? MOY_UI_UNDER_FULL : MOY_UI_UNDER_SMALL);
    }
    mua_clip_out(&k);
}

void moy_ui_api_tile(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t t[4],
                     const int32_t clip[4], int card, int mark, int32_t out[10]) {
    (void)c;
    moy_ui_box_t rect = {(int16_t)t[0], (int16_t)t[1], (int16_t)t[2], (int16_t)t[3]};
    moy_ui_box_t at = rect;
    out[9] = 0;
    clip_t k;
    moy_ui_box_t q = {(int16_t)clip[0], (int16_t)clip[1], (int16_t)clip[2], (int16_t)clip[3]};
    if (mark && mua_clip_in(&k, s, q)) {
        // the mark's box: the tile shrunk by as much as the theme's mark grows a card (a
        // lift's, read off the canvas's edge, where it draws nothing), so the lifted card
        // keeps its side, raised where it lifts
        int w = rect.w, h = rect.h, ink;
        moy_ui_box_t off = {(int16_t)(-4 * w - 64), (int16_t)(-4 * h - 64), (int16_t)w, (int16_t)h}, box;
        moy_ui_focus(s, off, MOY_UI_ITEM_CARD, 0, MOY_UI_MARK_AFTER | (mark & 2 ? MOY_UI_MARK_SELECTED : 0),
                     s->fs, &box, &ink);
        int g = floor_div(box.w - w, 2);
        if (g > 0) {
            at = (moy_ui_box_t){(int16_t)(rect.x + g), (int16_t)(rect.y + g), (int16_t)(w - 2 * g),
                                (int16_t)(h - 2 * g)};
        }
        moy_ui_focus(s, at, MOY_UI_ITEM_CARD, tile_r(rect.w, card), mark & 2 ? MOY_UI_MARK_SELECTED : 0,
                     s->fs, &rect, &ink);
        out[9] = mark & 2 ? 2 : 1;
    }
    if (mark) {
        mua_clip_out(&k);
    }
    out[0] = rect.x;
    out[1] = rect.y;
    out[2] = rect.w;
    out[3] = rect.h;
    out[4] = tile_r(rect.w, card);
    out[5] = at.x;
    out[6] = at.y;
    out[7] = at.w;
    out[8] = at.h;
}

void moy_ui_api_tile_blank(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t tile[10],
                           const int32_t clip[4], moy_ui_span_t icon) {
    clip_t k;
    moy_ui_box_t q = {(int16_t)clip[0], (int16_t)clip[1], (int16_t)clip[2], (int16_t)clip[3]};
    if (mua_clip_in(&k, s, q)) {
        moy_ui_box_t b = {(int16_t)tile[0], (int16_t)tile[1], (int16_t)tile[2], (int16_t)tile[3]};
        int slot = icon.n ? moy_ui_icon_slot(icon.p, icon.n) : -1;
        int glyph = icon.n ? moy_ui_icon_glyph(icon.p, icon.n) : -1;
        moy_ui_card_blank(s, b, slot, glyph, 0, c->fs, mua_ground_of(c));
    }
    mua_clip_out(&k);
}

void moy_ui_api_tile_end(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t tile[10],
                         const int32_t clip[4]) {
    (void)c;
    if (!tile[9]) {
        return;
    }
    clip_t k;
    moy_ui_box_t q = {(int16_t)clip[0], (int16_t)clip[1], (int16_t)clip[2], (int16_t)clip[3]};
    if (mua_clip_in(&k, s, q)) {
        moy_ui_box_t at = {(int16_t)tile[5], (int16_t)tile[6], (int16_t)tile[7], (int16_t)tile[8]};
        moy_ui_box_t box;
        int ink;
        moy_ui_focus(s, at, MOY_UI_ITEM_CARD, (int)tile[4],
                     MOY_UI_MARK_AFTER | (tile[9] == 2 ? MOY_UI_MARK_SELECTED : 0), s->fs, &box, &ink);
    }
    mua_clip_out(&k);
}

// Text `t` from (x, y), its line's top, in font `id` at `scale`: its shadow first, one pixel
// right and down in colour index `shadow` (-1 none), then the text in `ink`.
static void caption_text(const moy_ui_sink_t *s, const moy_text_target_t *tg, uint32_t id,
                         moy_ui_span_t t, int x, int y, int ink, int shadow, int scale) {
    moy_canvas_row_t *row = (moy_canvas_row_t *)s->dst;
    if (shadow >= 0) {
        moy_text(tg, id, MOY_TEXT_DATA, t.p, t.n, x + 1, y + 1, row->pal[moy_ui_pidx(s->cart, shadow)],
                 scale, 0, -1);
    }
    moy_text(tg, id, MOY_TEXT_DATA, t.p, t.n, x, y, row->pal[moy_ui_pidx(s->cart, ink)], scale, 0, -1);
}

static void caption_dot(const moy_ui_sink_t *s, const moy_text_target_t *tg, int x, int y, int d,
                        int ci) {
    moy_canvas_row_t *row = (moy_canvas_row_t *)s->dst;
    moy_target_fill(tg, x, y, d, d, row->pal[moy_ui_pidx(s->cart, ci)]);
}

static void carousel_caption(moy_ui_ctx_t *c, const moy_ui_sink_t *s, int bx, int bw, const int32_t g[10],
                             moy_ui_span_t title, moy_ui_span_t sub, int ink, int shadow, int fs);

void moy_ui_api_carousel_caption(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t band[4],
                                 const int32_t clip[4], const int32_t g[10], moy_ui_span_t title,
                                 moy_ui_span_t sub, int32_t ink) {
    int fs = c->fs, bx = band[0], bw = band[2], shadow = -1;
    if (ink >= MOY_UI_O_ROLE) {
        int t = moy_ui_token(s->look, ink - MOY_UI_O_ROLE);
        ink = t;
    } else if (ink >= 0) {
        ink = moy_theme_nearest(MOY_THEME_RGB | (ink & 0xffffff));
    }
    if (ink >= 0) {
        shadow = moy_theme_nearest(MOY_THEME_RGB | 0x000000);
    }
    clip_t k;
    moy_ui_box_t bb = {(int16_t)clip[0], (int16_t)clip[1], (int16_t)clip[2], (int16_t)clip[3]};
    if (mua_clip_in(&k, s, bb)) {
        carousel_caption(c, s, bx, bw, g, title, sub, ink, shadow, fs);
    }
    mua_clip_out(&k);
}

static void carousel_caption(moy_ui_ctx_t *c, const moy_ui_sink_t *s, int bx, int bw, const int32_t g[10],
                             moy_ui_span_t title, moy_ui_span_t sub, int ink, int shadow, int fs) {
    (void)c;
    moy_canvas_row_t *row = (moy_canvas_row_t *)s->dst;
    const int32_t *st = row->st;
    moy_text_target_t tg = {row->px, row->cap, (int)st[MOY_ST_W], (int)st[MOY_ST_CAM_X],
                            (int)st[MOY_ST_CAM_Y], (int)st[MOY_ST_CX0], (int)st[MOY_ST_CY0],
                            (int)st[MOY_ST_CX1], (int)st[MOY_ST_CY1]};
    int look = s->look;
    int ti = ink >= 0 ? ink : moy_ui_token(look, MOY_UI_T_INK);
    int di = ink >= 0 ? ink : moy_ui_token(look, MOY_UI_T_INK_DIM);
    moy_font_info_t tf, uf;
    uint32_t tid = carousel_font(MOY_UI_FONT_HERO, &tf);
    uint32_t uid = carousel_font(MOY_UI_FONT_UI, &uf);
    int tsc = (int)g[5];
    // the title, cut to what fits the band less 8 px a side at the scale, centred
    size_t tn = moy_text_fit_px(tid, title.p, title.n, bw - 16 * fs, tsc);
    moy_ui_span_t name = {title.p, (uint16_t)tn};
    int tw = moy_text_width(tid, name.p, name.n, tsc);
    caption_text(s, &tg, tid, name, bx + floor_div(bw - tw, 2), (int)g[3], ti, shadow, tsc);
    // the sub line's items (apart by tabs), a dot between each two
    int sep = 12 * fs, mw = 0, k = 0;
    for (size_t i = 0, a = 0; i <= sub.n; i++) {
        if (i == sub.n || sub.p[i] == '\t') {
            mw += moy_text_width(uid, sub.p + a, i - a, fs) + (k ? sep : 0);
            k++;
            a = i + 1;
        }
    }
    if (!sub.n) {
        return;
    }
    int d = font_v2(uid, &uf) ? 2 * fs : fs;
    int my = (int)g[6], dy;
    if (!font_v2(uid, &uf)) {
        dy = my + floor_div(uf.line * fs - d, 2);
    } else {
        int asc = uf.ascent * fs;
        dy = my + asc - floor_div(asc / 2 + d, 2);
    }
    for (int pass = shadow >= 0 ? 0 : 1; pass < 2; pass++) {
        int o = pass ? 0 : 1, ci = pass ? di : shadow;
        int x = bx + floor_div(bw - mw, 2) + o;
        k = 0;
        for (size_t i = 0, a = 0; i <= sub.n; i++) {
            if (i == sub.n || sub.p[i] == '\t') {
                if (k) {
                    caption_dot(s, &tg, x - floor_div(sep + d, 2), dy + o, d, ci);
                }
                moy_text(&tg, uid, MOY_TEXT_DATA, sub.p + a, i - a, x, my + o,
                         row->pal[moy_ui_pidx(s->cart, ci)], fs, 0, -1);
                x += moy_text_width(uid, sub.p + a, i - a, fs) + sep;
                k++;
                a = i + 1;
            }
        }
    }
}

// -- a home grid of cards (ui.cards look "shelf" or "icons") ----------------------------
//
// The home's grid and icons arrangements (runtime/home/home_grid.py, home_icons.py) as the
// engine lays them out, hit-tests and draws round the pictures the app draws: a shelf of
// cards in the rows the band holds, scrolling across, or tiles in the columns it holds,
// scrolling down. Handheld sizes are at the font scale, the desk's in glass pixels at the
// target's 1x (over `u` on a doubled desk).

// A shelf: the margin its first column stands in from the band's edge, the least and the most
// gap a column takes, its top under the band's, the title's baseline under its card and the
// rows a card's title takes.
static const int16_t SHELF_HH[6] = {16, 20, 28, 14, 17, 28};
static const int16_t SHELF_DK[6] = {48, 32, 44, 24, 26, 44};
// Icons: a narrow handheld's tile, a wide one's (CELLS_WIDE or more across), the column gap,
// the row gap, the grid's top under the band's and the caption band; the desk's tile, column
// gap, row gap (its label under the tile), top and label baseline under its tile.
static const int16_t ICONS_HH[6] = {40, 52, 18, 8, 8, 28};
static const int16_t ICONS_DK[5] = {64, 32, 44, 24, 20};
#define CELLS_WIDE 400
#define CELLS_MARGIN 16             // the icons' least margin either side
#define CELLS_FADE 12               // the handheld shelf's last rows dissolve over this many
#define CELLS_TITLE_MAX 120         // the most bytes of a card's title drawn

void moy_ui_api_cells_geom(int look, int fs, int desk, int u, const int32_t b[4],
                           int32_t out[MOY_UI_CELLS_G]) {
    moy_font_info_t uf;
    moy_ui_font(0, MOY_UI_FONT_UI, &uf);
    u = u > 1 ? u : 1;
    memset(out, 0, MOY_UI_CELLS_G * sizeof out[0]);
    int bw = (int)b[2], bh = (int)b[3], side, px, py, rows, cols, x0, y0, tdy = 0, tw, cap = 0;
    if (look == MOY_UI_LOOK_SHELF) {
        int v[6];
        for (int i = 0; i < 6; i++) {
            v[i] = desk ? SHELF_DK[i] / u : SHELF_HH[i] * fs;
        }
        int margin = v[0], g0 = v[1], g1 = v[2], top = v[3], base = v[4], room = v[5];
        side = moy_ui_api_clean_side(desk ? CAROUSEL_COVER / u : CAROUSEL_COVER / 2 * fs);
        for (;;) {
            rows = floor_div(bh - top - side, side + room) + 1;
            rows = rows > 1 ? rows : 1;
            if (rows > 1 || side <= CAROUSEL_COVER / 8) {
                break;
            }
            side = moy_ui_api_clean_side(side - 1);
        }
        int avail = bw - margin, gap = g0;
        for (int g = g0; g <= g1; g++) {
            int p = side + g, last = avail - floor_div(avail - 1, p) * p;
            if (last <= side * 2 / 3) {
                gap = g;
                break;
            }
        }
        px = side + gap;
        py = side + room;
        cols = floor_div(avail - 1, px) + 1;
        x0 = (int)b[0] + margin;
        y0 = (int)b[1] + top;
        tdy = side + base - uf.ascent * fs;
        tw = side;
        out[MOY_UI_CELLS_ACROSS] = 1;
        out[MOY_UI_CELLS_GROW] = desk ? 4 : 3;
    } else {
        int gap, room, top, margin;
        if (desk) {
            side = ICONS_DK[0] / u;
            gap = ICONS_DK[1] / u;
            room = ICONS_DK[2] / u;
            top = ICONS_DK[3] / u;
            tdy = side + ICONS_DK[4] / u - uf.ascent * fs;
            margin = CELLS_MARGIN / u;
        } else {
            side = (bw >= CELLS_WIDE * fs ? ICONS_HH[1] : ICONS_HH[0]) * fs;
            gap = ICONS_HH[2] * fs;
            room = ICONS_HH[3] * fs;
            top = ICONS_HH[4] * fs;
            cap = ICONS_HH[5] * fs;
            margin = CELLS_MARGIN * fs;
        }
        px = side + gap;
        py = side + room;
        cols = (bw - margin) / px;
        cols = cols > 1 ? cols : 1;
        x0 = (int)b[0] + floor_div(bw - cols * px, 2) + gap / 2;
        y0 = (int)b[1] + top;
        rows = floor_div(bh - cap - top - 1, py) + 1;
        rows = rows > 1 ? rows : 1;
        tw = px;
        out[MOY_UI_CELLS_GROW] = 3;
    }
    out[MOY_UI_CELLS_SIDE] = side;
    out[MOY_UI_CELLS_R] = moy_ui_depth()->card_r;
    out[MOY_UI_CELLS_X0] = x0;
    out[MOY_UI_CELLS_Y0] = y0;
    out[MOY_UI_CELLS_PX] = px;
    out[MOY_UI_CELLS_PY] = py;
    out[MOY_UI_CELLS_ROWS] = rows;
    out[MOY_UI_CELLS_COLS] = cols;
    out[MOY_UI_CELLS_TITLE_DY] = tdy;
    out[MOY_UI_CELLS_TITLE_W] = tw;
    out[MOY_UI_CELLS_CAP_H] = cap;
    out[MOY_UI_CELLS_VIEW_H] = bh - cap;
    out[MOY_UI_CELLS_DESK] = desk != 0;
    out[MOY_UI_CELLS_LOOK] = look;
}

// The cards a row of the table holds (a shelf's column, a row of icons).
static int cells_per(const int32_t g[MOY_UI_CELLS_G]) {
    int per = (int)(g[MOY_UI_CELLS_ACROSS] ? g[MOY_UI_CELLS_ROWS] : g[MOY_UI_CELLS_COLS]);
    return per > 0 ? per : 1;
}

// The extent of `n` cards under geometry `g` whose X0 and Y0 are offsets into the band.
static int32_t cells_extent(const int32_t g[MOY_UI_CELLS_G], int n) {
    if (n <= 0) {
        return 0;
    }
    int last = (n - 1) / cells_per(g);
    if (g[MOY_UI_CELLS_ACROSS]) {
        return 2 * g[MOY_UI_CELLS_X0] + last * g[MOY_UI_CELLS_PX] + g[MOY_UI_CELLS_SIDE];
    }
    return 2 * g[MOY_UI_CELLS_Y0] + last * g[MOY_UI_CELLS_PY] + g[MOY_UI_CELLS_SIDE]
           + (g[MOY_UI_CELLS_DESK] ? g[MOY_UI_CELLS_PY] - g[MOY_UI_CELLS_SIDE] : 0);
}

// Geometry `g` with its X0 and Y0 offsets into band `b`.
static void cells_rel(const int32_t g[MOY_UI_CELLS_G], const int32_t b[4], int32_t r[MOY_UI_CELLS_G]) {
    memcpy(r, g, MOY_UI_CELLS_G * sizeof r[0]);
    r[MOY_UI_CELLS_X0] -= b[0];
    r[MOY_UI_CELLS_Y0] -= b[1];
}

int32_t moy_ui_api_cells_extent(const int32_t g[MOY_UI_CELLS_G], const int32_t b[4], int n) {
    int32_t r[MOY_UI_CELLS_G];
    cells_rel(g, b, r);
    return cells_extent(r, n);
}

int32_t moy_ui_api_cells_reveal(const int32_t g[MOY_UI_CELLS_G], const int32_t b[4], int n, int i,
                                int32_t off) {
    if (n <= 0) {
        return 0;
    }
    int32_t r[MOY_UI_CELLS_G];
    cells_rel(g, b, r);
    int per = cells_per(g), across = (int)g[MOY_UI_CELLS_ACROSS];
    int32_t p = (int32_t)(i / per) * (across ? g[MOY_UI_CELLS_PX] : g[MOY_UI_CELLS_PY]);
    int32_t size = across ? g[MOY_UI_CELLS_SIDE] + 2 * r[MOY_UI_CELLS_X0]
                          : 2 * r[MOY_UI_CELLS_Y0] + g[MOY_UI_CELLS_SIDE]
                                + (g[MOY_UI_CELLS_DESK] ? g[MOY_UI_CELLS_PY] - g[MOY_UI_CELLS_SIDE] : 0);
    int32_t view = across ? b[2] : g[MOY_UI_CELLS_VIEW_H];
    int32_t most = cells_extent(r, n) - view;
    if (p < off) {
        off = p;
    } else if (p + size > off + view) {
        off = p + size - view;
    }
    off = off > most ? most : off;
    return off < 0 ? 0 : off;
}

void moy_ui_api_cells_tile(const int32_t g[MOY_UI_CELLS_G], const int32_t b[4], int32_t off, int i,
                           int32_t out[4]) {
    (void)b;
    int per = cells_per(g), a = i / per, k = i % per;
    if (g[MOY_UI_CELLS_ACROSS]) {
        out[0] = g[MOY_UI_CELLS_X0] + a * g[MOY_UI_CELLS_PX] - off;
        out[1] = g[MOY_UI_CELLS_Y0] + k * g[MOY_UI_CELLS_PY];
    } else {
        out[0] = g[MOY_UI_CELLS_X0] + k * g[MOY_UI_CELLS_PX];
        out[1] = g[MOY_UI_CELLS_Y0] + a * g[MOY_UI_CELLS_PY] - off;
    }
    out[2] = out[3] = g[MOY_UI_CELLS_SIDE];
}

int moy_ui_api_cells_at(const int32_t g[MOY_UI_CELLS_G], const int32_t b[4], int32_t off, int n,
                        int x, int y) {
    if (x < b[0] || x >= b[0] + b[2] || y < b[1] || y >= b[1] + g[MOY_UI_CELLS_VIEW_H] || n <= 0) {
        return -1;
    }
    int per = cells_per(g), across = (int)g[MOY_UI_CELLS_ACROSS];
    int side = (int)g[MOY_UI_CELLS_SIDE], px = (int)g[MOY_UI_CELLS_PX], py = (int)g[MOY_UI_CELLS_PY];
    // the row of the table the point lies across, then its cards along it
    int along = across ? x - (int)g[MOY_UI_CELLS_X0] + off : y - (int)g[MOY_UI_CELLS_Y0] + off;
    int a = floor_div(along, across ? px : py);
    for (int k = 0; k < per && a >= 0; k++) {
        int i = a * per + k;
        if (i >= n) {
            break;
        }
        int32_t t[4];
        moy_ui_api_cells_tile(g, b, off, i, t);
        int hx = (int)t[0], hw = side, hh = across ? py : (g[MOY_UI_CELLS_DESK] ? py : side);
        if (!across) {
            hx -= (px - side) / 2;
            hw = px;
        }
        if (x >= hx && x < hx + hw && y >= t[1] && y < t[1] + hh) {
            return i;
        }
    }
    return -1;
}

void moy_ui_api_cells_card(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t g[MOY_UI_CELLS_G],
                           const int32_t t[4], const int32_t clip[4], int focus, moy_ui_span_t title,
                           int32_t ink) {
    clip_t k;
    moy_ui_box_t q = {(int16_t)clip[0], (int16_t)clip[1], (int16_t)clip[2], (int16_t)clip[3]};
    if (mua_clip_in(&k, s, q)) {
        int fs = c->fs, gr = focus ? (int)g[MOY_UI_CELLS_GROW] : 0;
        if (focus) {
            // the theme's focus mark, flat: a ring that moves with every step and lifts nothing
            moy_ui_box_t box = {(int16_t)(t[0] - gr), (int16_t)(t[1] - gr), (int16_t)(t[2] + 2 * gr),
                                (int16_t)(t[3] + 2 * gr)}, got;
            int mi, r = g[MOY_UI_CELLS_R] ? (int)g[MOY_UI_CELLS_R] + gr : 0;
            moy_ui_focus(s, box, MOY_UI_ITEM_CARD, r, MOY_UI_MARK_RING | MOY_UI_MARK_COUNT, fs, &got, &mi);
        }
        if (g[MOY_UI_CELLS_TITLE_DY] && title.n) {
            // its title centred under it in the ui face, cut to the cells' title width: bold on
            // focus (drawn twice a pixel apart), over a black shadow in an ink of its own
            moy_font_info_t uf;
            uint32_t fid = moy_ui_font(0, MOY_UI_FONT_UI, &uf);
            int w = (int)g[MOY_UI_CELLS_TITLE_W], bold = focus && ink == MOY_UI_O_NONE;
            // cut to the title width (a pixel less where bold) with the font's ellipsis
            uint8_t buf[CELLS_TITLE_MAX + 3];
            int ell = 0;
            size_t k = moy_text_cut_px(fid, title.p, title.n, w - (bold ? fs : 0), fs, &ell);
            k = k < CELLS_TITLE_MAX ? k : CELLS_TITLE_MAX;
            memcpy(buf, title.p, k);
            if (ell) {
                memcpy(buf + k, "\xe2\x80\xa6", 3);
                k += 3;
            }
            moy_ui_span_t cut = {buf, (uint16_t)k};
            moy_ui_box_t tb = {(int16_t)(t[0] + t[2] / 2 - w / 2), (int16_t)(t[1] + g[MOY_UI_CELLS_TITLE_DY]),
                               (int16_t)w, (int16_t)(uf.line * fs)};
            moy_ui_label_paint_t lp = {-1, -1, 0, 0, 0};
            int ci;
            if (ink == MOY_UI_O_NONE) {
                ci = moy_ui_token(s->look, MOY_UI_T_INK);
            } else {
                ci = ink >= MOY_UI_O_ROLE ? moy_ui_token(s->look, ink - MOY_UI_O_ROLE)
                                          : moy_theme_nearest(MOY_THEME_RGB | (ink & 0xffffff));
                lp = (moy_ui_label_paint_t){-1, (int16_t)moy_theme_nearest(MOY_THEME_RGB | 0x000000), 255,
                                            1, 1};
            }
            if (bold) {
                moy_ui_box_t b2 = tb;           // bold: drawn twice, a pixel at the scale apart
                b2.x = (int16_t)(b2.x + fs);
                moy_ui_label_paint(s, b2, cut, ci, MOY_TEXT_CENTER, &lp);
            }
            moy_ui_label_paint(s, tb, cut, ci, MOY_TEXT_CENTER, &lp);
        }
    }
    mua_clip_out(&k);
}

void moy_ui_api_cells_foot(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t g[MOY_UI_CELLS_G],
                           const int32_t b[4], const int32_t clip[4], int fade, moy_ui_span_t title,
                           moy_ui_span_t sub) {
    int fs = c->fs;
    clip_t k;
    moy_ui_box_t q = {(int16_t)clip[0], (int16_t)clip[1], (int16_t)clip[2], (int16_t)clip[3]};
    if (!mua_clip_in(&k, s, q)) {
        mua_clip_out(&k);
        return;
    }
    if (g[MOY_UI_CELLS_ACROSS]) {
        if (fade && !g[MOY_UI_CELLS_DESK]) {
            int h = CELLS_FADE * fs;
            moy_ui_fade(s, (moy_ui_box_t){(int16_t)b[0], (int16_t)(b[1] + b[3] - h), (int16_t)b[2], (int16_t)h},
                        moy_ui_token(s->look, MOY_UI_T_DESKTOP), 0, fs, 0);
        }
        mua_clip_out(&k);
        return;
    }
    int cap = (int)g[MOY_UI_CELLS_CAP_H];
    if (cap <= 0) {
        mua_clip_out(&k);
        return;
    }
    // the caption band on the ground under a hairline, the current card's name in the title
    // face from the first column's left and its items after it in the dim ink
    moy_canvas_row_t *row = (moy_canvas_row_t *)s->dst;
    const int32_t *st = row->st;
    moy_text_target_t tg = {row->px, row->cap, (int)st[MOY_ST_W], (int)st[MOY_ST_CAM_X],
                            (int)st[MOY_ST_CAM_Y], (int)st[MOY_ST_CX0], (int)st[MOY_ST_CY0],
                            (int)st[MOY_ST_CX1], (int)st[MOY_ST_CY1]};
    int x = (int)b[0], y = (int)(b[1] + b[3] - cap), w = (int)b[2], look = s->look;
    moy_target_fill(&tg, x, y, w, cap, row->pal[moy_ui_pidx(s->cart, moy_ui_token(look, MOY_UI_T_DESKTOP))]);
    moy_target_fill(&tg, x, y, w, fs, row->pal[moy_ui_pidx(s->cart, moy_ui_token(look, MOY_UI_T_EDGE))]);
    if (!title.n) {
        mua_clip_out(&k);
        return;
    }
    int base = y + 22 * fs, left = (int)g[MOY_UI_CELLS_X0], right = x + w - (left - x);
    moy_font_info_t tf, uf;
    uint32_t tid = moy_ui_font(0, MOY_UI_FONT_TITLE, &tf);
    uint32_t uid = moy_ui_font(0, MOY_UI_FONT_UI, &uf);
    size_t tn = moy_text_fit_px(tid, title.p, title.n, right - left, fs);
    int tw = moy_text_width(tid, title.p, tn, fs);
    caption_text(s, &tg, tid, (moy_ui_span_t){title.p, (uint16_t)tn}, left, base - tf.ascent * fs,
                 moy_ui_token(look, MOY_UI_T_INK), -1, fs);
    int sep = 12 * fs, mx = left + tw + 10 * fs, my = base - uf.ascent * fs, di = moy_ui_token(look, MOY_UI_T_INK_DIM);
    int d = font_v2(uid, &uf) ? 2 * fs : fs, dy;
    if (!font_v2(uid, &uf)) {
        dy = my + floor_div(uf.line * fs - d, 2);
    } else {
        int asc = uf.ascent * fs;
        dy = my + asc - floor_div(asc / 2 + d, 2);
    }
    int n = 0;
    for (size_t i = 0, a = 0; i <= sub.n; i++) {
        if (i < sub.n && sub.p[i] != '\t') {
            continue;
        }
        size_t m = moy_text_fit_px(uid, sub.p + a, i - a, right - mx, fs);
        if (!m) {
            break;
        }
        if (n) {
            caption_dot(s, &tg, mx - floor_div(sep + d, 2), dy, d, di);
        }
        moy_text(&tg, uid, MOY_TEXT_DATA, sub.p + a, m, mx, my, row->pal[moy_ui_pidx(s->cart, di)], fs, 0, -1);
        mx += moy_text_width(uid, sub.p + a, m, fs) + sep;
        n++;
        a = i + 1;
    }
    mua_clip_out(&k);
}

// -- the desk's carousel (ui.cards look "carousel" on the desk class) -------------------------
//
// The desk home (runtime/home/home_carousel.py): the selected card the hero beside its details,
// over a shelf of one-size cards that bleeds off the right edge, its caption over it. Laid out
// in glass pixels at the target's 1x (over `u` on a doubled desk), its type at whole scales of
// the face no smaller than the font scale.
#define DESK_DETAILS_MIN 280        // the narrowest details pane beside the hero
#define DESK_SHELF_GAP 42           // the details block's foot to the shelf's caption

static int imax(int a, int b) {
    return a > b ? a : b;
}

static int imin(int a, int b) {
    return a < b ? a : b;
}

// The whole scale a face whose line is `line` px draws a line about `px` px tall in, the font
// scale `fs` at the least (`text_scale`).
static int desk_scale(int px, int fs, int line) {
    line = line > 0 ? line : 1;
    return imax(fs, (px + line / 2) / line);
}

// The shelf's margin in from the band's edges: a twentieth of its width, 12 to 48 px.
static int desk_pad(int w, int u) {
    return imin(48 / u, imax(12 / u, w / 20));
}

void moy_ui_api_carousel_desk(int fs, int u, int keys, int brows, const int32_t b[4],
                              int32_t out[MOY_UI_DESK_G]) {
    moy_font_info_t tf, uf;
    moy_ui_font(0, MOY_UI_FONT_TITLE, &tf);
    moy_ui_font(0, MOY_UI_FONT_UI, &uf);
    u = u > 1 ? u : 1;
    int cx = (int)b[0], cy = (int)b[1], cw = (int)b[2], foot = (int)(b[1] + b[3]);
    int pad = desk_pad(cw, u), top = 24 / u, apart = 32 / u;
    int ring = imax(2 * fs + 2, moy_ui_mark_reach(MOY_UI_ITEM_CARD));
    int lh = uf.line, tl = tf.line;
    int ts = desk_scale(40 / u, fs, tl), ms = desk_scale(14 / u, fs, lh);
    int ks = desk_scale(13 / u, fs, lh), vs = desk_scale(15 / u, fs, lh);
    int bh = imax(42 / u, 20 * fs);
    int need = tl * ts + lh * (ms + ks + vs) + bh + 60 / u + brows;
    int cap_h = lh * ms + 8 / u;
    int room = foot - cy - top - cap_h - 72 / u;
    // a short band gives up, in turn, most of the slack round the shelf's caption, the facts'
    // row and the metadata's line
    int rows[2] = {1, 1}, cut[2] = {lh * (ks + vs) + 22 / u, lh * ms + 14 / u};
    int least = CAROUSEL_COVER / 2;
    if (imax(least, need) + least / 2 > room) {
        room += 48 / u;
    }
    for (int k = 0; k < 2; k++) {
        if (imax(least, need) + least / 2 > room) {
            rows[k] = 0;
            need -= cut[k];
        }
    }
    int hero = cw / 4 / CAROUSEL_COVER * CAROUSEL_COVER;
    while (hero > CAROUSEL_COVER && imax(hero, need) + hero / 2 > room) {
        hero -= CAROUSEL_COVER;
    }
    if (hero < CAROUSEL_COVER || imax(hero, need) + hero / 2 > room) {
        hero = least;
    }
    while (hero > CAROUSEL_COVER / 8 && imax(hero, need) + hero / 2 > room) {
        hero /= 2;
    }
    int hx = cx + pad, hy = cy + top;
    int dx = hx + hero + apart, dy = hy, pane = imax(hero, need), block = pane;
    if (cx + cw - pad - dx < DESK_DETAILS_MIN / u) {
        // too narrow for the pane beside the hero: the hero over the pane where the height
        // holds both at a hero no smaller
        int up = CAROUSEL_COVER;
        while (up > hero && up + apart + need + up / 2 > room) {
            up /= 2;
        }
        if (up >= hero && up + apart + need + up / 2 <= room) {
            hero = up;
            dx = hx;
            dy = hy + hero + apart;
            pane = need;
            block = hero + apart + need;
        }
    }
    int shelf = hero / 2;
    int spare = imax(0, foot - cy - top - block - cap_h - shelf);
    const moy_ui_depth_t *d = moy_ui_depth();
    int down = imax(ring, (d->shadow ? d->blur : 0) + d->dy);
    // the caption SHELF_GAP under the details, the spare height under the shelf; a height
    // short of that splits what it has, keeping the shelf's lift and shadow off the strip
    int cap_y = hy + block + imin(DESK_SHELF_GAP / u, imax(spare / 2, spare - imax(down, 20 / u)));
    if (!keys) {
        // no strip under touch: the shelf stands at most the side margin off the glass's foot
        cap_y = imax(cap_y, foot - pad - shelf - cap_h);
    }
    int shelf_y = cap_y + cap_h;
    int32_t o[MOY_UI_DESK_G] = {hx, hy, hero, hero, dx, dy, imax(0, cx + cw - pad - dx), pane,
                                cx, cap_y, cw, imax(0, imin(foot, shelf_y + shelf + down) - cap_y),
                                shelf, shelf_y, pad, ts, ms, ks, vs, bh, rows[0], rows[1], ring,
                                20 / u};
    memcpy(out, o, sizeof o);
}

void moy_ui_api_desk_shelf_geom(int fs, int u, const int32_t b[4], int side, int32_t out[MOY_UI_CELLS_G]) {
    moy_font_info_t uf;
    moy_ui_font(0, MOY_UI_FONT_UI, &uf);
    u = u > 1 ? u : 1;
    int ms = desk_scale(14 / u, fs, uf.line);
    memset(out, 0, MOY_UI_CELLS_G * sizeof out[0]);
    out[MOY_UI_CELLS_SIDE] = side;
    out[MOY_UI_CELLS_R] = moy_ui_depth()->card_r;
    out[MOY_UI_CELLS_X0] = b[0] + desk_pad((int)b[2], u);
    out[MOY_UI_CELLS_Y0] = b[1] + uf.line * ms + 8 / u;
    out[MOY_UI_CELLS_PX] = side + 20 / u;
    out[MOY_UI_CELLS_PY] = side;
    out[MOY_UI_CELLS_ROWS] = 1;
    out[MOY_UI_CELLS_COLS] = 1;
    out[MOY_UI_CELLS_TITLE_DY] = ms;            // (the caption's scale)
    out[MOY_UI_CELLS_VIEW_H] = b[3];
    out[MOY_UI_CELLS_ACROSS] = 1;
    out[MOY_UI_CELLS_DESK] = 1;
    out[MOY_UI_CELLS_LOOK] = MOY_UI_LOOK_DESK;
}

int moy_ui_api_desk_at(const int32_t g[MOY_UI_CELLS_G], const int32_t b[4], int32_t off, int n, int x,
                       int y) {
    int left = (int)(g[MOY_UI_CELLS_X0] + g[MOY_UI_CELLS_SIDE] - g[MOY_UI_CELLS_PX]);
    return x < left ? -1 : moy_ui_api_cells_at(g, b, off, n, x, y);
}

void moy_ui_api_desk_caption(moy_ui_ctx_t *c, const moy_ui_sink_t *s, const int32_t g[MOY_UI_CELLS_G],
                             const int32_t b[4], const int32_t clip[4], moy_ui_span_t label, int n) {
    clip_t k;
    moy_ui_box_t q = {(int16_t)clip[0], (int16_t)clip[1], (int16_t)clip[2], (int16_t)clip[3]};
    if (!mua_clip_in(&k, s, q)) {
        mua_clip_out(&k);
        return;
    }
    // the label and the count, apart by a dot, in the dim ink on the ground over the first card
    moy_canvas_row_t *row = (moy_canvas_row_t *)s->dst;
    const int32_t *st = row->st;
    moy_text_target_t tg = {row->px, row->cap, (int)st[MOY_ST_W], (int)st[MOY_ST_CAM_X],
                            (int)st[MOY_ST_CAM_Y], (int)st[MOY_ST_CX0], (int)st[MOY_ST_CY0],
                            (int)st[MOY_ST_CX1], (int)st[MOY_ST_CY1]};
    moy_font_info_t uf;
    uint32_t uid = moy_ui_font(0, MOY_UI_FONT_UI, &uf);
    int sc = (int)g[MOY_UI_CELLS_TITLE_DY], x = (int)g[MOY_UI_CELLS_X0], y = (int)b[1], sep = 6 * c->fs;
    int di = moy_ui_token(s->look, MOY_UI_T_INK_DIM);
    uint16_t ink = row->pal[moy_ui_pidx(s->cart, di)];
    moy_text(&tg, uid, MOY_TEXT_DATA, label.p, label.n, x, y, ink, sc, 0, -1);
    x += moy_text_width(uid, label.p, label.n, sc) + sep;
    int dy;
    if (!font_v2(uid, &uf)) {
        dy = y + floor_div(uf.line * sc - sc, 2);
    } else {
        int asc = uf.ascent * sc;
        dy = y + asc - floor_div(asc / 2 + sc, 2);
    }
    caption_dot(s, &tg, x, dy, sc, di);
    uint8_t cnt[12];
    size_t cn = sizeof cnt;
    unsigned v = n > 0 ? (unsigned)n : 0u;
    do {
        cnt[--cn] = (uint8_t)('0' + v % 10u);
        v /= 10u;
    } while (v && cn);
    moy_text(&tg, uid, MOY_TEXT_DATA, cnt + cn, sizeof cnt - cn, x + sc + sep, y, ink, sc, 0, -1);
    mua_clip_out(&k);
}
