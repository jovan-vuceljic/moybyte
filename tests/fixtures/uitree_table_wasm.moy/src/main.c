// A compiled app's table of parts (tests/test_uitree_wasm.py): its canvas
// child draws each row, and a press on a row reaches the pointer= action
// with that row, in the row's coordinates.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

static int32_t s_items, s_last;

static void draw(int32_t x, int32_t y, int32_t w, int32_t h) {}

static void opened(int32_t row) {
    static const char rows[] = "a\0b\0c\0d\0e\0f\0g\0h";
    uitree_set_model(s_items, 8, rows, sizeof rows);
}

static void poke(int32_t row) {
    static const char *const what[] = {"", "down", "drag", "up"};
    ut_point_t p = ut_point();
    char b[64], *e = b + strlen(strcpy(b, what[p.kind]));
    *e++ = ' ';
    e = ut_digits_(e, row);
    *e++ = ',';
    e = ut_digits_(e, p.y);
    *e = 0;
    ut_set_text(s_last, b);
}

static void page(void) {
    ut_page("rows", "Rows") {
        ut_table("items", NULL, NULL, NULL) {
            ut_p_row(30);
            ut_canvas("cell", draw, "poke");
        }
    }
}

EXPORT(_init) void _init(void) {
    s_items = ut_model("items", "id", 0, UT_TEXT);
    s_last = ut_text("last", "");
    ut_hook("opened", opened);
    ut_action("poke", "Poke", poke);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
