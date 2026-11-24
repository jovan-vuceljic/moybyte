// A compiled app's page that takes a row (tests/test_uitree_wasm.py): a
// row's link pushes the details of its row, which the cursor names, and
// focus is moved by the app. Other pushes the details of the first row over
// them, and Back shows the row they were pushed with again.
#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

enum { F_ID, F_NAME };
static int32_t s_items, s_sel;

static void details(void) {
    ut_page("details", "Details") {
        ut_link("other", NULL);
        ut_label("{sel.name}");
    }
}

static void opened(int32_t row) {
    static const char rows[] = "a\0Apples\0b\0Bread";
    uitree_set_model(s_items, 2, rows, sizeof rows);
    ut_focus("b/open");
}

static void open_(int32_t row) { ut_push_row(details, s_sel, s_items, F_ID, row); }

static void other(int32_t row) { ut_push_row(details, s_sel, s_items, F_ID, 0); }

static void page(void) {
    ut_page("shelf", "Shelf") {
        ut_rows("items", NULL) ut_link("open", "{.name}");
    }
}

EXPORT(_init) void _init(void) {
    s_items = ut_model("items", "id\0name", F_ID, UT_TEXT, UT_TEXT);
    s_sel = ut_row_of("sel", s_items);
    ut_hook("opened", opened);
    ut_action("open", "Open", open_);
    ut_action("other", "Other", other);
    ut_open(page);
}

// A responsive app: it draws in the shell's look on its window's surface.
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
