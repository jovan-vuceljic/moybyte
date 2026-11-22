// A compiled app whose row action holds the more role (tests/test_uitree_wasm.py):
// the `m` key runs it on the focused row, and on no row where none is focused.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

enum { F_ID, F_NAME };
static int32_t s_items, s_said;

static void opened(int32_t row) {
    static const char rows[] = "a\0Apples\0b\0Bread";
    uitree_set_model(s_items, 2, rows, sizeof rows);
    ut_focus("b/open");
}

static void open_(int32_t row) {
    char msg[32] = "more ";
    ut_get_cell(s_items, row, F_ID, msg + 5, sizeof msg - 5);
    ut_set_text(s_said, msg);
}

static void page(void) {
    ut_page("shelf", "Shelf") {
        ut_label("{said}");
        ut_rows("items", NULL) ut_link("open", "{.name}");
    }
}

EXPORT(_init) void _init(void) {
    s_items = ut_model("items", "id\0name", F_ID, UT_TEXT, UT_TEXT);
    s_said = ut_text("said", "");
    ut_hook("opened", opened);
    ut_action_more("open", "Open", open_);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
