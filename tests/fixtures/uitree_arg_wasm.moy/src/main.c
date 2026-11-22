// A compiled app whose buttons hand their arg= to one action and whose typed
// keys reach another through its chars= (tests/test_uitree_wasm.py).
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

static int32_t s_said;

static void key(int32_t row) { ut_set_text(s_said, ut_arg()); }

static void typed(int32_t row) { ut_set_text(s_said, ut_arg()); }

static void page(void) {
    ut_page("pad", "Keypad") {
        ut_label("{said}");
        ut_button_arg("key", "7", NULL);
        ut_button_arg("key", "+", NULL);
    }
}

EXPORT(_init) void _init(void) {
    s_said = ut_text("said", "");
    ut_action("key", "Press", key);
    ut_action_chars(ut_action("typed", "Type", typed), "0123456789+-");
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
