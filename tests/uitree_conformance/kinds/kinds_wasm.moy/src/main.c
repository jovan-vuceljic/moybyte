// Conformance fixture `kinds` (level 2), the compiled half: a seg over an enum
// worded by a label table, a progress bar, a menu and its item, a table with
// its columns, a lines view, and an action a table's row fires
// (sdk/include/moybyte/uitree.h). Its Python half is ../app.py, its Lua half
// ../kinds.moy.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

enum { F_ID, F_NAME, F_SIZE };  // the model's fields, in the engine's order
static int32_t s_items, s_done, s_picked;

static void opened(int32_t row) {
    static const char rows[] = "a\0Apples\0" "3\0b\0Bread\0" "1";
    uitree_set_model(s_items, 2, rows, sizeof rows);
}

static void pick(int32_t row) {
    char msg[64] = "Picked ";
    ut_get_cell(s_items, row, F_NAME, msg + 7, sizeof msg - 7);
    ut_set_text(s_picked, msg);
}

static void bump(int32_t row) { uitree_set_int(s_done, uitree_get_int(s_done) + 1); }

static void page(void) {
    ut_page("kinds", "Kinds") {
        ut_seg("mode", "Mode", "MODES");
        ut_progress("{done}", "Done", 5);
        ut_menu("Do") ut_item("bump");
        ut_table("items", "sel", "pick", "Name", "Size") {
            ut_col("{.name}");
            ut_col("{.size}");
        }
        ut_text_view("log");
        ut_label("{picked}");
    }
}

EXPORT(_init) void _init(void) {
    s_done = ut_int("done", 2);
    s_items = ut_model("items", "id\0name\0size", F_ID, UT_TEXT, UT_TEXT, UT_INT);
    ut_text("log", "one\ntwo");
    ut_enum("mode", "a\0b\0c", "a");
    s_picked = ut_text("picked", "");
    ut_row_of("sel", s_items);
    uitree_labels("MODES", 5, "a\0b\0c", 5, "Apple\0Bean\0Corn", 15);
    ut_hook("opened", opened);
    ut_action("pick", "Pick", pick);
    ut_action("bump", "More", bump);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
