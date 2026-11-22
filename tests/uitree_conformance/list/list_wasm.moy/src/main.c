// Conformance fixture `list` (level 1), the compiled half: a model filled at
// open, rows with a cursor, a row action and a label it writes, built on the
// UI tree engine through the uitree rows (sdk/include/moybyte/uitree.h). Its
// Python half is ../app.py, its Lua half ../list.moy.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

enum { F_ID, F_NAME };          // the model's fields, in the engine's order
static int32_t s_items, s_msg;

static void opened(int32_t row) {
    static const char rows[] = "a\0Apples\0b\0Bread\0c\0Cheese";
    uitree_set_model(s_items, 3, rows, sizeof rows);
}

static void pick(int32_t row) {
    char msg[64] = "Picked ";
    ut_get_cell(s_items, row, F_NAME, msg + 7, sizeof msg - 7);
    ut_set_text(s_msg, msg);
}

EXPORT(_init) void _init(void) {
    s_items = ut_model("items", "id\0name", F_ID, UT_TEXT, UT_TEXT);
    s_msg = ut_state("msg", UT_TEXT);
    ut_row_of("sel", s_items);
    ut_hook("opened", opened);
    ut_action("pick", "Pick", pick);
    ut_page("shopping", "Shopping") {
        ut_group("Things") {
            ut_rows("items", "sel") ut_link("pick", "{.name}");
            ut_label("{msg}");
        }
    }
    uitree_open();
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
