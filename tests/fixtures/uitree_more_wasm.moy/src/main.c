// A compiled app whose page holds the more role (tests/test_uitree_wasm.py):
// the `m` key runs it on the page, and not while a field is focused.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

static int32_t s_said, s_note;

static void more(int32_t row) { ut_set_text(s_said, "more"); }

static void go(int32_t row) {}

static void page(void) {
    ut_page("tools", "Tools") {
        ut_label("{said}");
        ut_button("go", NULL);
        ut_field("note", "Note");
    }
}

EXPORT(_init) void _init(void) {
    s_said = ut_text("said", "");
    s_note = ut_text("note", "");
    ut_action("go", "Go", go);
    ut_action_more("more", "More", more);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
