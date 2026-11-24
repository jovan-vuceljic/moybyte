// The run's context and its RUN sink (moy_ui_run.h).

#include "moy_platform.h"

#include <stdlib.h>
#include <string.h>

#include "moy_kmem.h"

#define CTX_ALLOC(n) moy_kalloc((n), MOY_KMEM_PSRAM | MOY_KMEM_INTERNAL_OK)

#include "moy.h"
#include "moy_canvas.h"
#include "moy_theme.h"
#include "moy_ui_run.h"

// The RUN sink lends an RGB565 canvas as a row (a compile-time check, not a
// preprocessor one: MicroPython's qstr pass preprocesses without the build's
// definitions).
_Static_assert(sizeof(moy_pixel) == sizeof(uint16_t), "the RUN sink lends an RGB565 canvas");

// The generation the run's look was built under (0: none yet, which no live
// theme has), and the run's serial it was built for. A generation is counted
// by one console from its own start, so a later console (or run) can reach the
// same number on another theme: the look is rebuilt for each run.
static uint32_t s_gen, s_gen_serial;

// The live theme's token row and its name, copied when the generation differs
// from `have`: native/moy_app/moy_app_wasm.c's. Answers the generation, 0
// while no run is bound; weak, so an image without the app ABI draws no rows.
#if __has_include("moy_app_wasm.h")
#include "moy_app_wasm.h"
#else
uint32_t moy_app_wasm_theme(int32_t *out, uint32_t have, char *name, uint32_t cap);
#endif
#pragma weak moy_app_wasm_theme

// What every drawing row opens with: the RUN sink over the run's target, lent
// as `row`, the look current, the run's draw state saved in `saved` and reset.
typedef struct {
    moy_ui_sink_t s;
    moy_canvas_row_t row;
    moy_canvas *c;
    moy_canvas saved;
} run_t;

// The snapshot's face word (MOYCORE_UI_FACE_*), 0 with no run.
static int32_t run_face(void) {
    uint32_t tick = 0, serial = 0;
    const int32_t *snap = moycore_ui_snap(&tick, &serial);
    return snap != NULL ? snap[MOYCORE_UI_SNAP_FACE] : 0;
}

static int face_fs(int32_t face) {
    int fs = (face >> MOYCORE_UI_FACE_FS_SHIFT) & 0xFF;
    return fs > 1 ? fs : 1;
}

static int open_run(run_t *r, moy_canvas *c) {
    if (c == NULL || moy_app_wasm_theme == NULL) {
        return -MOY_UI_STALE;
    }
    uint32_t tick = 0, serial = 0;
    const int32_t *snap = moycore_ui_snap(&tick, &serial);
    int32_t face = snap != NULL ? snap[MOYCORE_UI_SNAP_FACE] : 0;
    int fs = face_fs(face);
    if (serial != s_gen_serial) {
        s_gen = 0;
        s_gen_serial = serial;
    }
    int32_t tok[MOY_UI_TOKENS];
    char name[MOY_UI_SHAPE_NAME];
    uint32_t gen = moy_app_wasm_theme(tok, s_gen, name, sizeof(name));
    if (gen == 0u) {
        return -MOY_UI_STALE;
    }
    if (gen != s_gen) {
        const moy_ui_shape_t *now = moy_ui_shape();
        // The live theme names another shape than the shell installed: it
        // is resolved into a block of its own (PSRAM), which the UI copies.
        moy_ui_shape_t *sh = name[0] && now != NULL && strcmp(name, now->name) != 0
            ? CTX_ALLOC(sizeof(*sh)) : NULL;
        if (sh != NULL) {
            moy_theme_shape(name, strlen(name), sh);
            moy_ui_shape_use(sh);
            free(sh);
        }
        moy_ui_look_set(MOY_UI_LOOK_RUN, tok);
        s_gen = gen;
    }
    r->c = c;
    r->saved = *c;
    moy_reset_state(c);
    memset(&r->row, 0, sizeof(r->row));
    r->row.px = (uint16_t *)c->pix;
    r->row.cap = (uint32_t)(c->w * c->h);
    r->row.w = (uint16_t)c->w;
    r->row.h = (uint16_t)c->h;
    r->row.st[MOY_ST_CX1] = r->row.st[MOY_ST_W] = c->w;
    r->row.st[MOY_ST_CY1] = r->row.st[MOY_ST_H] = c->h;
    r->row.st[MOY_ST_FONT_SCALE] = fs;
    memcpy(r->row.pal, c->store, MOY_CANVAS_BLOCK * sizeof(uint16_t));
    r->s.fs = (uint8_t)fs;
    r->s.dst = &r->row;
    if (face & MOYCORE_UI_FACE_LOOK) {
        // A responsive app's page is the shell's: the theme's block at
        // 64..127, as every glass row holds it, and outside the boundary.
        moy_ui_theme_pal(&r->row.pal[MOY_CANVAS_BLOCK]);
        r->s.kind = MOY_UI_SINK_ROW;
        r->s.look = MOY_UI_LOOK_APP;
        r->s.cart = 0;
    } else {
        // A cart's colours are MOY64 (its theme imports answer each role's
        // nearest index), so both halves are the canvas's.
        memcpy(&r->row.pal[MOY_CANVAS_BLOCK], c->store, MOY_CANVAS_BLOCK * sizeof(uint16_t));
        r->s.kind = MOY_UI_SINK_RUN;
        r->s.look = MOY_UI_LOOK_RUN;
        r->s.cart = (uint8_t)moy_ui_cart_on();
    }
    r->s.shown = (uint8_t)moy_ui_marks_shown();
    return 0;
}

static int close_run(run_t *r, int rc) {
    *r->c = r->saved;
    return rc == MOY_UI_OK ? 0 : -rc;
}

// -- the run's context ------------------------------------------------------------
//
// One run at a time, so one context: begun lazily by the first frame of each
// tick, over the run's snapshot, and reset when a new run opens. The first
// frame any run draws allocates it (CTX_ALLOC: PSRAM where the board has it)
// and it is kept: a static would hold its size in internal SRAM from boot on
// a console that never runs an app on the UI tree. NULL: none could be had.

static moy_ui_ctx_t *s_ctx;
static uint32_t s_tick, s_serial;
static int s_live;
static uint8_t s_paste[MOY_UI_API_PASTE];  // moy_ui_run_paste's, for the frame begun next
static size_t s_paste_n;
static int32_t s_rep, s_keyrep;            // moy_ui_run_steps', likewise
static int s_taken;                        // moy_ui_run_keys_taken's, likewise

static moy_ui_ctx_t *run_ctx(const void *target) {
    const moy_canvas *c = (const moy_canvas *)target;
    uint32_t tick = 0, serial = 0;
    if (s_ctx == NULL && (s_ctx = CTX_ALLOC(sizeof(*s_ctx))) == NULL) {
        return NULL;
    }
    const int32_t *snap = moycore_ui_snap(&tick, &serial);
    if (!s_live || serial != s_serial) {
        moy_ui_api_reset_in(s_ctx, NULL);
        s_serial = serial;
        s_tick = tick - 1u;
        s_live = 1;
        (void)moycore_ui_dt_take();         // the clock starts with the run
    }
    if (tick != s_tick) {
        int32_t in[MOY_UI_IN_LEN] = {0};
        int flags = 0;
        if (snap != NULL) {
            int32_t face = snap[MOYCORE_UI_SNAP_FACE];
            flags = ((face & MOYCORE_UI_FACE_WINDOW) ? MOY_UI_WINDOW : 0)
                    | ((face & MOYCORE_UI_FACE_DESK) ? MOY_UI_DESK : 0)
                    | ((face & MOYCORE_UI_FACE_TAP) ? MOY_UI_TAP : 0);
            in[MOY_UI_IN_BTN] = snap[MOYCORE_UI_SNAP_BTN];
            in[MOY_UI_IN_BTNP] = snap[MOYCORE_UI_SNAP_BTNP];
            in[MOY_UI_IN_X] = snap[MOYCORE_UI_SNAP_X];
            in[MOY_UI_IN_Y] = snap[MOYCORE_UI_SNAP_Y];
            in[MOY_UI_IN_PTR] = snap[MOYCORE_UI_SNAP_PTR];
            in[MOY_UI_IN_KEY] = snap[MOYCORE_UI_SNAP_KEY];
        }
        in[MOY_UI_IN_REP] = s_rep;
        in[MOY_UI_IN_KEYREP] = s_keyrep;
        s_rep = s_keyrep = 0;
        if (s_taken) {                      // the app's canvas took them
            in[MOY_UI_IN_BTNP] = in[MOY_UI_IN_KEY] = in[MOY_UI_IN_REP] = in[MOY_UI_IN_KEYREP] = 0;
        }
        s_taken = 0;
        in[MOY_UI_IN_DT] = moycore_ui_dt_take();   // the ticks' clock since the last frame
        // an app's frame is its content_rect() (the snapshot's room), a
        // game's the whole canvas
        moy_ui_box_t surf = s_ctx->surface;
        if (c != NULL) {
            surf.x = surf.y = 0;
            surf.w = (int16_t)c->w;
            surf.h = (int16_t)c->h;
            if (snap != NULL && snap[MOYCORE_UI_SNAP_ROOM_W] > 0
                && snap[MOYCORE_UI_SNAP_ROOM_H] > 0) {
                int x = snap[MOYCORE_UI_SNAP_ROOM_X], y = snap[MOYCORE_UI_SNAP_ROOM_Y];
                int x1 = x + snap[MOYCORE_UI_SNAP_ROOM_W], y1 = y + snap[MOYCORE_UI_SNAP_ROOM_H];
                x = x < 0 ? 0 : x;
                y = y < 0 ? 0 : y;
                x1 = x1 > c->w ? c->w : x1;
                y1 = y1 > c->h ? c->h : y1;
                if (x1 > x && y1 > y) {
                    surf.x = (int16_t)x;
                    surf.y = (int16_t)y;
                    surf.w = (int16_t)(x1 - x);
                    surf.h = (int16_t)(y1 - y);
                }
            }
        }
        moy_ui_api_begin(s_ctx, in, surf, flags, face_fs(run_face()));
        if (s_paste_n > 0) {
            moy_ui_api_paste(s_ctx, s_paste, s_paste_n);
            s_paste_n = 0;
        }
        s_tick = tick;
    }
    return s_ctx;
}

void moy_ui_run_keys_taken(void) {
    s_taken = 1;
}

void moy_ui_run_steps(int32_t rep, int32_t keyrep) {
    s_rep = rep;
    s_keyrep = keyrep;
}

void moy_ui_run_paste(const uint8_t *text, size_t n) {
    if (n > sizeof s_paste) {
        n = sizeof s_paste;         // moy_ui_api_paste keeps whole characters
    }
    memcpy(s_paste, text, n);
    s_paste_n = n;
}

int moy_ui_run_back(int take) {
    uint32_t tick = 0, serial = 0;
    (void)moycore_ui_snap(&tick, &serial);
    return s_ctx != NULL && s_live && serial == s_serial ? moy_ui_api_back(s_ctx, take) : 0;
}

int moy_ui_run_way_taken(void) {
    uint32_t tick = 0, serial = 0;
    (void)moycore_ui_snap(&tick, &serial);
    return s_ctx != NULL && s_live && serial == s_serial ? moy_ui_api_way_taken(s_ctx) : 0;
}

int moy_ui_run_cancel(int take) {
    uint32_t tick = 0, serial = 0;
    (void)moycore_ui_snap(&tick, &serial);
    return s_ctx != NULL && s_live && serial == s_serial ? moy_ui_api_cancel(s_ctx, take) : 0;
}

// The run's context while the run that drew in it is the one open, else NULL.
static moy_ui_ctx_t *run_ctx_now(void) {
    uint32_t tick = 0, serial = 0;
    const int32_t *snap = moycore_ui_snap(&tick, &serial);
    return snap != NULL && s_ctx != NULL && s_live && serial == s_serial ? s_ctx : NULL;
}

const char *moy_ui_run_page_title(void) {
    moy_ui_ctx_t *c = run_ctx_now();
    return c == NULL ? NULL : moy_ui_api_page_title(c);
}

int moy_ui_run_typing(void) {
    uint32_t tick = 0, serial = 0;
    (void)moycore_ui_snap(&tick, &serial);
    return s_ctx != NULL && s_live && serial == s_serial ? moy_ui_api_typing(s_ctx) : 0;
}

// A drawing over the run's frame: the RUN sink over `target` and the run's context.
int moy_ui_run_with(void *target, moy_ui_run_fn fn, void *ud) {
    run_t r;
    moy_canvas *t = (moy_canvas *)target;
    if (t == NULL) {
        return -MOY_UI_STALE;
    }
    int rc = open_run(&r, t);
    if (rc != 0) {
        return rc;
    }
    moy_ui_ctx_t *c = run_ctx(t);
    if (c == NULL) {
        return close_run(&r, MOY_UI_NOMEM);
    }
    int v = fn(ud, c, &r.s, c->surface, run_face());
    close_run(&r, MOY_UI_OK);
    return v;
}
