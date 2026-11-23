// Conformance fixture `rowtabs` (level 2), the compiled half: tabs over a
// row_of, a tab a row of its model worded by the row template text=, and a
// label of the picked row (sdk/include/moybyte/uitree.h). Its Python half is
// ../app.py, its Lua half ../rowtabs.moy.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

static int32_t s_objs, s_obj, s_said;

static void opened(int32_t row) {
    static const char rows[] = "0\0Stage\0" "1\0player\0" "2\0coin";
    uitree_set_model(s_objs, 3, rows, sizeof rows);
}

static void chose(int32_t row) {
    char msg[64] = "On ";
    ut_get_text(s_obj, msg + 3, sizeof msg - 3);
    ut_set_text(s_said, msg);
}

static void page(void) {
    ut_page("rowtabs", "Tabs") {
        ut_tabs_rows("obj", "{.name}");
        ut_p_on("chose");
        ut_label("{said}");
    }
}

EXPORT(_init) void _init(void) {
    s_objs = ut_model("objs", "k\0name", 0, UT_TEXT, UT_TEXT);
    s_obj = ut_row_of("obj", s_objs);
    s_said = ut_text("said", "");
    ut_hook("opened", opened);
    ut_hook("chose", chose);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
