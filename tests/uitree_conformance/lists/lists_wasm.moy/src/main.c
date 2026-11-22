// Conformance fixture `lists` (level 2), the compiled half: a tab strip bound
// to an enum, rows of links, and the same rows as cards whose card fires an
// action with its row (sdk/include/moybyte/uitree.h). Its Python half is
// ../app.py, its Lua half ../lists.moy.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

enum { F_ID, F_KIND, F_NAME };  // the model's fields, in the engine's order
static int32_t s_items, s_picked;

static void opened(int32_t row) {
    static const char rows[] = "apple\0fruit\0Apples\0bread\0bread\0Bread\0pear\0fruit\0Pears";
    uitree_set_model(s_items, 3, rows, sizeof rows);
}

static void say(const char *what, int32_t row, int32_t f) {
    char msg[64];
    size_t n = strlen(what);
    memcpy(msg, what, n);
    ut_get_cell(s_items, row, f, msg + n, sizeof msg - n);
    ut_set_text(s_picked, msg);
}

static void pick(int32_t row) { say("Picked ", row, F_NAME); }
static void open_(int32_t row) { say("Opened ", row, F_ID); }

static void page(void) {
    ut_page("lists", "Lists") {
        ut_tabs("tab", "TABS");
        ut_group("Things") {
            ut_rows("items", NULL) ut_link("pick", "{.name}");
        }
        ut_group("Shelf") {
            ut_cards("items", "sel", 96, 64) ut_card("open", "{.name}", "{.kind}");
        }
        ut_label("{picked}");
    }
}

EXPORT(_init) void _init(void) {
    s_items = ut_model("items", "id\0kind\0name", F_ID, UT_TEXT, UT_TEXT, UT_TEXT);
    ut_field_enum(s_items, F_KIND, "fruit\0bread");
    s_picked = ut_text("picked", "");
    ut_row_of("sel", s_items);
    ut_enum("tab", "all\0few", "all");
    uitree_labels("TABS", 4, "all\0few", 7, "All\0Few", 7);
    ut_hook("opened", opened);
    ut_action("pick", "Pick", pick);
    ut_action("open", "Open", open_);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
