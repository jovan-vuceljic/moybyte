// Conformance fixture `gates` (level 1), the compiled half: an action hidden
// while a toggle is off, one greyed while a count is 0, and a node shown by a
// condition (sdk/include/moybyte/uitree.h). Its Python half is ../app.py, its
// Lua half ../gates.moy.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

static int32_t s_n;

static void add(int32_t row) { uitree_set_int(s_n, uitree_get_int(s_n) + 1); }
static void take(int32_t row) { uitree_set_int(s_n, uitree_get_int(s_n) - 1); }

static void page(void) {
    ut_page("gates", "Gates") {
        ut_group("Gate") {
            ut_toggle("open", "Open");
            ut_link("add", NULL);
            ut_link("take", NULL);
            ut_label("{n} inside");
            ut_p_shown("open");
        }
    }
}

EXPORT(_init) void _init(void) {
    s_n = ut_int("n", 0);
    ut_bool("open", 0);
    ut_action_when("add", "Add one", "open", UT_OFF_HIDE, add);
    ut_action_when("take", "Take one", "n", UT_OFF_GREY, take);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
