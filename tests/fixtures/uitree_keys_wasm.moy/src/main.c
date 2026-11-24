// A compiled app's canvas keys= (tests/test_uitree_api_parity.py, the Lua
// layer's LUA_KEYS in C): while the canvas holds focus its keys are handed
// them first, and what they take the page never sees.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

__attribute__((import_module("moy"), import_name("btnp"))) int32_t btnp_(int32_t b, int32_t player);
enum { DOWN = 3, A = 4 };

static int32_t s_n, n, downed;

static void add(int32_t k) {
    char b[16];
    n += k;
    *ut_digits_(b, n) = 0;
    ut_set_text(s_n, b);
}

static void go(int32_t row) { add(100); }

static void draw(int32_t x, int32_t y, int32_t w, int32_t h) {}

static int32_t keys(void) {
    if (btnp_(A, 0)) {
        add(1);
        return 1;
    }
    if (btnp_(DOWN, 0) && !downed) {
        downed = 1;
        add(10);
        return 1;
    }
    return 0;
}

static void page(void) {
    ut_page("p", "Keys") {
        ut_label("{n}");
        ut_canvas("pad", draw, NULL);
        ut_canvas_keys(keys);
        ut_p_h(20);
        ut_button("go", NULL);
    }
}

EXPORT(_init) void _init(void) {
    s_n = ut_text("n", "0");
    ut_action("go", "Go", go);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
