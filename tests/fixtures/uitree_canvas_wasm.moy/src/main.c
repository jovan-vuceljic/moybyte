// A compiled app's canvas (tests/test_uitree_wasm.py): drawn by the app's
// own draw inside the frame, its pointer handed to an action as down, drag
// and up in the canvas's coordinates.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

static int32_t s_last, drawn;

static void draw(int32_t x, int32_t y, int32_t w, int32_t h) { drawn++; }

static void poke(int32_t row) {
    static const char *const what[] = {"", "down", "drag", "up"};
    ut_point_t p = ut_point();
    char b[64], *e = b + strlen(strcpy(b, what[p.kind]));
    *e++ = ' ';
    e = ut_digits_(e, p.x);
    *e++ = ',';
    e = ut_digits_(e, p.y);
    strcpy(e, drawn > 0 ? " drawn" : " not drawn");
    ut_set_text(s_last, b);
}

static void page(void) {
    ut_page("pad", "Pad") {
        ut_label("{last}");
        ut_canvas("pad", draw, "poke");
        ut_p_h(400);
    }
}

EXPORT(_init) void _init(void) {
    s_last = ut_text("last", "");
    ut_action("poke", "Poke", poke);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
