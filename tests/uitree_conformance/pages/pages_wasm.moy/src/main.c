// Conformance fixture `pages` (level 1), the compiled half: a dialog shown by
// a state, its two buttons, and a pushed page Back pops
// (sdk/include/moybyte/uitree.h). Its Python half is ../app.py, its Lua half
// ../pages.moy.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

static int32_t s_count, s_asking;

static void details(void) {
    ut_page("details", "Details") {
        ut_group("Now") ut_info("Count", "{count}");
    }
}

static void add(int32_t row) { uitree_set_int(s_count, uitree_get_int(s_count) + 1); }
static void ask(int32_t row) { uitree_set_int(s_asking, 1); }
static void keep(int32_t row) { uitree_set_int(s_asking, 0); }
static void more(int32_t row) { ut_push(details); }

static void reset(int32_t row) {
    uitree_set_int(s_count, 0);
    uitree_set_int(s_asking, 0);
}

static void page(void) {
    ut_page("pages", "Pages") {
        ut_group("Count") {
            ut_info("Count", "{count}");
            ut_link("add", NULL);
            ut_link("ask", NULL);
            ut_link("more", NULL);
        }
        ut_dialog("Reset the count?", "asking", "keep", "reset") ut_label("It goes back to 0.");
    }
}

EXPORT(_init) void _init(void) {
    s_count = ut_int("count", 0);
    s_asking = ut_bool("asking", 0);
    ut_action("add", "Add one", add);
    ut_action("ask", "Reset", ask);
    ut_action("keep", "Keep", keep);
    ut_action("reset", "Reset", reset);
    ut_action("more", "Details", more);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
