// A compiled app's canvas under an open dialog (tests/test_uitree_wasm.py):
// while the dialog is up the canvas takes no press.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

static void draw(int32_t x, int32_t y, int32_t w, int32_t h) {}

static void poke(int32_t row) {}

static void shut(int32_t row) {}

static void page(void) {
    ut_page("pad", "Modal") {
        ut_canvas("pad", draw, "poke");
        ut_p_h(400);
        ut_dialog("Held", "open", "close") {
            ut_label("A dialog over the canvas");
        }
    }
}

EXPORT(_init) void _init(void) {
    ut_bool("open", 1);
    ut_action("poke", "Poke", poke);
    ut_action("close", "Close", shut);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
