// Conformance fixture `counter` (level 1), the compiled half: a count, an
// action, an action that is off while the count is 0, a toggle and the
// templates that show them, built on the UI tree engine through the uitree
// rows (sdk/include/moybyte/uitree.h). Its Python half is ../app.py, its Lua
// half ../counter.moy.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

static int32_t s_count;

static void add(int32_t row) { uitree_set_int(s_count, uitree_get_int(s_count) + 1); }
static void reset(int32_t row) { uitree_set_int(s_count, 0); }

EXPORT(_init) void _init(void) {
    s_count = ut_int("count", 0);
    ut_bool("loud", 0);
    ut_action("add", "Add one", add);
    ut_action_when("reset", "Reset", "count", UT_OFF_GREY, reset);
    ut_page("counter", "Counter") {
        ut_group("Count") {
            ut_info("Count", "{count}");
            ut_toggle("loud", "Loud");
            ut_link("add", NULL);
            ut_link("reset", NULL);
            ut_label("{count|plural press,presses} so far, {loud?loud:quiet}");
        }
    }
    uitree_open();
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
