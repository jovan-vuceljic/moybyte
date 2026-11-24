// The UI tree for a compiled app in C (native/moy_uitree/moy_uitree_wasm.h
// states each row's contract): the engine's numbers and a typed layer over
// app.h's `uitree_*` imports, header-only, so no row of its own. An app
// declares its states and its actions, each action with its handler, builds
// its page once, and runs ut_frame() each frame; the engine draws the page
// and ut_frame runs the handler of each action a person takes:
//
//     static int32_t s_count;
//     static void add(int32_t row) { uitree_set_int(s_count, uitree_get_int(s_count) + 1); }
//     static void page(void) {
//         ut_page("counter", "Counter") {
//             ut_group("Count") {
//                 ut_info("Count", "{count}");
//                 ut_link("add", NULL);
//             }
//         }
//     }
//     EXPORT(_init) void _init(void) {
//         s_count = ut_int("count", 0);
//         ut_action("add", "Add one", add);
//         ut_open(page);
//     }
//     EXPORT(_draw) void _draw(void) { ut_frame(); }
//
// A page is a function: ut_push(fn) from a handler builds it over this one,
// and the bar's Back (or ut_pop) builds the one under it again. A page that
// takes a row (ut_push_row) keeps it: the Back onto it sets its cursor again.
// A page's shown= action (ut_p_shown, its first prop) runs when the page
// becomes the top page, by a push or by Back, before the frame that draws it.
//
// A node goes under the open container (ut_page, ut_group, ut_rows, ut_in);
// one with no key of its own is keyed by its kind and its place among its
// siblings (`info#0`), as the Python and Lua layers key it. A prop goes on
// the node made last: ut_p_<prop> (uitree_schema.h, generated from the
// contract) takes an int prop as an int, a bool as a truth, any other as its
// source. A `break` out of a container's body leaves it open. Any refusal is
// the engine's, latched for the run: uitree_error says which and where.
//
// The numbers are moy_uitree.h's, held equal to it by tests/test_uitree_wasm.py.

#ifndef MOYBYTE_UITREE_H
#define MOYBYTE_UITREE_H

#include <stdint.h>
#include <string.h>

#include "moybyte/app.h"

#ifdef __cplusplus
extern "C" {
#endif

// A state's type (uitree_state).
enum { UT_BOOL = 1, UT_INT, UT_NUM, UT_TEXT, UT_ENUM, UT_ROWOF, UT_MODEL };

// An action's flags and how its nodes look while it is off (uitree_action).
enum { UT_A_HOOK = 1, UT_A_ROLE_CONFIRM = 2, UT_A_ROLE_BACK = 4, UT_A_ROW = 8, UT_A_SHIFT_ENTER = 16, UT_A_ROLE_MORE = 32,
       UT_A_ARROWS_V = 64, UT_A_ARROWS_H = 128, UT_A_APP_BACK = 256 };
enum { UT_OFF_NONE = 0, UT_OFF_HIDE = 1, UT_OFF_GREY = 2 };

// The refusals every uitree_* call may answer (uitree_error says which and where).
enum {
    UT_E_NAME = -1, UT_E_LANG = -2, UT_E_KIND = -3, UT_E_NOMEM = -4, UT_E_ARG = -5,
    UT_E_CHECK = -6, UT_E_BLOB = -7,
};

#define UT_DEPTH 16             // containers open at once (a node deeper is refused)
#define UT_ACTIONS 64           // actions with a handler
#define UT_PAGES 8              // pages on the stack
#define UT_BACK 0x10000         // uitree_next's answer for the bar's back: pop the page
#define UT_CANVASES 8           // canvases with a draw on a page
#define UT_ARG 64               // the longest arg a handler reads whole (ut_arg)

// A handler: `row` is the row of the model the action came from, else -1.
typedef void (*ut_fn)(int32_t row);
// A page: its build, a ut_page block.
typedef void (*ut_page_fn)(void);
// A canvas's draw, called inside the frame with the rect it draws in.
typedef void (*ut_draw_fn)(int32_t x, int32_t y, int32_t w, int32_t h);
// A canvas's keys=, called before the frame while it holds focus, reading btnp() and keyp():
// non-zero where it took the tick's keys, which the page then never sees.
typedef int32_t (*ut_keys_fn)(void);

// The build's place and the handlers: one copy for every unit that includes this.
struct ut_ {
    int32_t at[UT_DEPTH], kids[UT_DEPTH];   // each open container, its children so far
    int32_t depth, last;                    // ...how many; the node made last
    const char *names[UT_ACTIONS];          // each action's name and handler, by its index
    ut_fn fns[UT_ACTIONS];
    ut_page_fn pages[UT_PAGES];             // the page stack, its top last
    int32_t cursors[UT_PAGES];              // ...each page's cursor (ut_push_row), -1 none
    char rows[UT_PAGES][UT_ARG + 1];        // ...and the key of the row it was pushed with
    int32_t npages;
    int32_t ev[5];                          // the running action's model slot, row, and a pointer's kind, x, y
    int32_t canvas[UT_CANVASES];            // the page's canvases with a draw, and each draw
    ut_draw_fn draws[UT_CANVASES];
    int32_t ncanvas;
    int32_t keyed[UT_CANVASES];             // the page's canvases with a keys=, and each keys
    ut_keys_fn keys[UT_CANVASES];
    int32_t nkeyed;
    char arg[UT_ARG + 1];                   // the running handler's arg (ut_arg)
};
__attribute__((weak)) struct ut_ ut_;

// The module's `_uitree_draw` (the face calls it for each canvas the frame draws): the canvas's draw.
__attribute__((weak, export_name("_uitree_draw"))) void ut_draw_(int32_t node, int32_t x, int32_t y, int32_t w,
                                                                 int32_t h) {
    for (int32_t i = 0; i < ut_.ncanvas; i++) {
        if (ut_.canvas[i] == node) {
            ut_.draws[i](x, y, w, h);
        }
    }
}

// The module's `_uitree_keys` (the face calls it before the frame while a canvas with a keys=
// holds focus): that canvas's keys, non-zero where it took the tick's keys.
__attribute__((weak, export_name("_uitree_keys"))) int32_t ut_keys_(int32_t node) {
    for (int32_t i = 0; i < ut_.nkeyed; i++) {
        if (ut_.keyed[i] == node) {
            return ut_.keys[i]() != 0;
        }
    }
    return 0;
}

// A pointer action's event: down, drag or up, at x, y in its canvas.
#define UT_DOWN 1
#define UT_DRAG 2
#define UT_UP 3
typedef struct {
    int32_t kind, x, y;
} ut_point_t;

static inline ut_point_t ut_point(void) {
    ut_point_t p = {ut_.ev[2], ut_.ev[3], ut_.ev[4]};
    return p;
}

static inline uint32_t ut_len_(const char *s) {
    return s != NULL ? (uint32_t)strlen(s) : 0u;
}

// `v`'s digits at `b`, NUL-ended: the end.
static inline char *ut_digits_(char *b, int32_t v) {
    char t[11];
    int n = 0;
    uint32_t u = v < 0 ? 0u - (uint32_t)v : (uint32_t)v;
    if (v < 0) {
        *b++ = '-';
    }
    do {
        t[n++] = (char)('0' + u % 10);
    } while ((u /= 10) != 0);
    while (n) {
        *b++ = t[--n];
    }
    *b = 0;
    return b;
}

// -- state -----------------------------------------------------------------------

// A state of `type` named `name`: its slot.
static inline int32_t ut_state(const char *name, int32_t type) {
    return uitree_state(name, ut_len_(name), type, NULL, 0);
}

// An int (a bool) state holding `v`: its slot.
static inline int32_t ut_int(const char *name, int32_t v) {
    int32_t s = ut_state(name, UT_INT);
    uitree_set_int(s, v);
    return s;
}

// A text state holding `v`: its slot.
static inline int32_t ut_text(const char *name, const char *v) {
    int32_t s = ut_state(name, UT_TEXT);
    uitree_set_text(s, v, ut_len_(v));
    return s;
}

// A number state holding `v`, given as its digits ("2.5"): its slot. A number
// crosses as text both ways: uitree_set_text writes it, uitree_get_text reads it.
static inline int32_t ut_num(const char *name, const char *v) {
    int32_t s = ut_state(name, UT_NUM);
    uitree_set_text(s, v, ut_len_(v));
    return s;
}

// An enum state: its values NUL-separated, holding `v`: its slot.
#define ut_enum(name, values, v) ut_enum_((name), (values), sizeof(values) - 1, (v))

static inline int32_t ut_enum_(const char *name, const char *values, uint32_t values_n, const char *v) {
    int32_t s = uitree_state(name, ut_len_(name), UT_ENUM, values, values_n);
    uitree_set_text(s, v, ut_len_(v));
    return s;
}

static inline int32_t ut_bool(const char *name, int v) {
    int32_t s = ut_state(name, UT_BOOL);
    uitree_set_int(s, v != 0);
    return s;
}

// A model state: its fields' names NUL-separated in the engine's (sorted)
// order, its key field's index, then each field's type:
// ut_model("items", "id\0name", 0, UT_TEXT, UT_TEXT). Its slot.
#define ut_model(name, fields, key, ...)                                                          \
    ut_model_((name), (fields), sizeof(fields) - 1, (const uint8_t[]){__VA_ARGS__},               \
              sizeof((const uint8_t[]){__VA_ARGS__}), (key))

static inline int32_t ut_model_(const char *name, const char *fields, uint32_t fields_n, const uint8_t *types,
                                uint32_t types_n, int32_t key) {
    int32_t s = ut_state(name, UT_MODEL);
    uitree_model(s, fields, fields_n, types, types_n, key);
    return s;
}

// A model's text field (its index f in the model's field order) made an enum
// of the NUL-separated `values`: ut_field_enum(m, 1, "fruit\0bread").
#define ut_field_enum(model, f, values) uitree_field_enum((model), (f), (values), sizeof(values) - 1)

// A cursor over the model at slot `model`: its slot.
static inline int32_t ut_row_of(const char *name, int32_t model) {
    int32_t s = ut_state(name, UT_ROWOF);
    uitree_row_of(s, model);
    return s;
}

static inline int32_t ut_set_text(int32_t slot, const char *s) {
    return uitree_set_text(slot, s, ut_len_(s));
}

// A text state's value (a model's cell) into `buf`, cut to fit and NUL-ended: its whole length.
static inline int32_t ut_get_text(int32_t slot, char *buf, uint32_t cap) {
    int32_t n = uitree_get_text(slot, buf, cap - 1);
    buf[n < 0 ? 0 : (uint32_t)n < cap - 1 ? (uint32_t)n : cap - 1] = 0;
    return n;
}

static inline int32_t ut_get_cell(int32_t model, int32_t row, int32_t field, char *buf, uint32_t cap) {
    int32_t n = uitree_get_cell(model, row, field, buf, cap - 1);
    buf[n < 0 ? 0 : (uint32_t)n < cap - 1 ? (uint32_t)n : cap - 1] = 0;
    return n;
}

// -- actions ---------------------------------------------------------------------

static inline int32_t ut_on_(int32_t a, const char *name, ut_fn fn) {
    if (a >= 0 && a < UT_ACTIONS) {
        ut_.names[a] = name;
        ut_.fns[a] = fn;
    }
    return a;
}

// An action a person sees, named `name`, labelled `label`, run by `fn`: its index.
static inline int32_t ut_action(const char *name, const char *label, ut_fn fn) {
    return ut_on_(uitree_action(name, ut_len_(name), label, ut_len_(label), NULL, 0, NULL, 0, UT_OFF_NONE, 0,
                                NULL, 0, NULL, 0), name, fn);
}

// ...that is off while the condition `when` is false, looking as `off` says.
static inline int32_t ut_action_when(const char *name, const char *label, const char *when, int32_t off, ut_fn fn) {
    return ut_on_(uitree_action(name, ut_len_(name), label, ut_len_(label), NULL, 0, when, ut_len_(when), off, 0,
                                NULL, 0, NULL, 0), name, fn);
}

// ...that takes the more role: the `m` key, where no field is focused, runs it
// on the focused row when it hangs from a row's node, else on the page.
static inline int32_t ut_action_more(const char *name, const char *label, ut_fn fn) {
    return ut_on_(uitree_action(name, ut_len_(name), label, ut_len_(label), NULL, 0, NULL, 0, UT_OFF_NONE,
                                UT_A_ROLE_MORE, NULL, 0, NULL, 0), name, fn);
}

// ...that is handed each typed key `chars` holds (chars=), as ut_arg(), where
// no field takes it: `a` the action's index.
static inline int32_t ut_action_chars(int32_t a, const char *chars) {
    return uitree_action_chars(a, chars, ut_len_(chars));
}

// What the running handler was handed: the arg= of the button or link that
// fired it (an int's digits), or the typed key its chars= holds; "" none.
static inline const char *ut_arg(void) {
    int32_t n = uitree_arg(ut_.arg, UT_ARG);
    ut_.arg[n < 0 ? 0 : n > UT_ARG ? UT_ARG : n] = 0;
    return ut_.arg;
}

// A handler no person sees, named `name` (`opened`: the engine's, run as the visit opens): its index.
static inline int32_t ut_hook(const char *name, ut_fn fn) {
    return ut_on_(uitree_action(name, ut_len_(name), "", 0, NULL, 0, NULL, 0, UT_OFF_NONE, UT_A_HOOK, NULL, 0,
                                NULL, 0), name, fn);
}

// The index of the action named `name`, -1 where there is none (the engine refuses it).
static inline int32_t ut_action_of_(const char *name) {
    for (int32_t a = 0; a < UT_ACTIONS; a++) {
        if (ut_.names[a] != NULL && !strcmp(ut_.names[a], name)) {
            return a;
        }
    }
    return -1;
}

static inline void ut_pop(void);

// Each action the engine hands out, its handler run; the bar's back pops the page.
static inline void ut_run(void) {
    for (int32_t a; (a = uitree_next(ut_.ev, sizeof ut_.ev)) >= 0;) {
        if (a == UT_BACK) {
            ut_pop();
        } else if (a < UT_ACTIONS && ut_.fns[a] != NULL) {
            ut_.fns[a](ut_.ev[1]);
        }
    }
}

// The frame: the handlers, the bar and the page (uitree_frame), and the handlers of what it took.
static inline int32_t ut_frame(void) {
    ut_run();
    int32_t r = uitree_frame(0);
    ut_run();
    return r;
}

// -- the page --------------------------------------------------------------------

// Prop `name` of node `node`, its value's source `src` (ut_p_<prop>: the node made last's).
static inline int32_t ut_prop(int32_t node, const char *name, const char *src) {
    return uitree_prop(node, name, ut_len_(name), src, ut_len_(src));
}

static inline int32_t ut_prop_(const char *name, const char *src) {
    return ut_prop(ut_.last, name, src);
}

static inline int32_t ut_prop_int_(const char *name, int32_t v) {
    char b[12];
    ut_digits_(b, v);
    return ut_prop_(name, b);
}

#include "moybyte/uitree_schema.h"

// A node of `kind` under the open container, keyed `key` (NULL: its kind#place): its index.
static inline int32_t ut_node(int32_t kind, const char *key) {
    char k[32];
    int32_t d = ut_.depth, in = d > 0 && d <= UT_DEPTH, place = in ? ut_.kids[d - 1]++ : 0;
    if (key == NULL) {
        const char *name = kind > 0 && kind < (int32_t)(sizeof ut_kind_names_ / sizeof *ut_kind_names_)
                               ? ut_kind_names_[kind] : "?";
        size_t n = strlen(name);
        memcpy(k, name, n);
        k[n] = '#';
        ut_digits_(k + n + 1, place);
        key = k;
    }
    return ut_.last = uitree_node(kind, key, ut_len_(key), in ? ut_.at[d - 1] : d > 0 ? -2 : -1);
}

static inline int ut_open_(int32_t node) {
    if (ut_.depth < UT_DEPTH) {
        ut_.at[ut_.depth] = node;
        ut_.kids[ut_.depth] = 0;
    }
    ut_.depth++;
    return 1;
}

static inline int ut_close_(void) {
    ut_.depth--;
    return 0;
}

// The body that follows holds node `node`'s children: ut_in(ut_node(UT_SCROLL, "list")) { ... }.
#define ut_in(node) for (int ut_o_ = ut_open_(node); ut_o_; ut_o_ = ut_close_())

static inline int ut_page_(const char *id, const char *title) {
    char b[32];
    char *e = ut_digits_(b, ut_.npages > 1 ? ut_.npages : 1);
    size_t n = strlen(id) < (size_t)(b + sizeof b - 2 - e) ? strlen(id) : (size_t)(b + sizeof b - 2 - e);
    *e++ = ' ';
    memcpy(e, id, n);
    uitree_build(b, (uint32_t)(e + n - b));
    ut_.depth = 0;
    ut_.ncanvas = ut_.nkeyed = 0;
    ut_node(UT_PAGE, "page");
    if (title != NULL) {
        ut_prop_("title", title);
    }
    return ut_open_(ut_.last);
}

static inline int ut_page_end_(void) {
    ut_close_();
    uitree_build_end();
    return 0;
}

// The page `id`, titled `title` (or NULL), built by the body that follows
// (the build of a page function: a page's id is its place on the stack and `id`).
#define ut_page(id, title) for (int ut_o_ = ut_page_(id, title); ut_o_; ut_o_ = ut_page_end_())

// The app's first page, built by `page`, and the visit opened.
static inline int32_t ut_open(ut_page_fn page) {
    ut_.pages[0] = page;
    ut_.cursors[0] = -1;
    ut_.npages = 1;
    page();
    return uitree_open();
}

static inline void ut_push_(ut_page_fn page, int32_t cursor) {
    if (ut_.npages < UT_PAGES) {
        ut_.cursors[ut_.npages] = cursor;
        ut_.pages[ut_.npages++] = page;
        page();
    }
}

// From a handler: the page `page` pushed (built) over this one, which Back pops.
static inline void ut_push(ut_page_fn page) {
    ut_push_(page, -1);
}

// ...a page that takes a row: the cursor `cursor` (a row_of over the model
// at slot `model`, whose key is field `key`) set to row `row` first, and
// set to it again when a page over this one pops.
static inline void ut_push_row(ut_page_fn page, int32_t cursor, int32_t model, int32_t key, int32_t row) {
    char full[UT_ARG + 1];
    char *k = ut_.npages < UT_PAGES ? ut_.rows[ut_.npages] : full;
    ut_get_cell(model, row, key, k, sizeof full);
    ut_set_text(cursor, k);
    ut_push_(page, cursor);
}

// The focus put on the node keyed `key` (a row's part: "ROWKEY/KEY") at the next frame.
static inline int32_t ut_focus(const char *key) {
    return uitree_focus(key, ut_len_(key));
}

// In a canvas's draw or keys: the model row it stands in (a table's row its canvas
// child draws, a row of a rows list's body), from 0; -1 for a canvas of its own.
static inline int32_t ut_canvas_row(void) {
    return uitree_draw_row();
}

// The page under this one built again on the row it was pushed with, the
// focus back where it was.
static inline void ut_pop(void) {
    if (ut_.npages > 1) {
        int32_t at = --ut_.npages - 1;
        if (ut_.cursors[at] >= 0) {
            ut_set_text(ut_.cursors[at], ut_.rows[at]);
        }
        ut_.pages[at]();
    }
}

static inline int32_t ut_group_(const char *caption) {
    int32_t n = ut_node(UT_GROUP, NULL);
    ut_prop_("caption", caption);
    return n;
}

// A group captioned `caption`, holding the body that follows.
#define ut_group(caption) ut_in(ut_group_(caption))

static inline int32_t ut_dialog_(const char *title, const char *shown, const char *const *buttons) {
    int32_t n = ut_node(UT_DIALOG, NULL);
    if (shown != NULL) {
        ut_prop_("shown", shown);
    }
    ut_prop_("title", title);
    for (; *buttons != NULL; buttons++) {
        uitree_node_action(n, ut_action_of_(*buttons));
    }
    return n;
}

// A dialog titled `title`, shown while the condition `shown` holds (NULL:
// always), its buttons the actions named after it, holding the body that follows.
#define ut_dialog(title, shown, ...) ut_in(ut_dialog_(title, shown, (const char *const[]){__VA_ARGS__, NULL}))

static inline int32_t ut_rows_(const char *model, const char *cur) {
    int32_t n = ut_node(UT_ROWS, model);
    ut_prop_("bind", model);
    if (cur != NULL) {
        ut_prop_("cur", cur);
    }
    return n;
}

// The rows of model `model`, its cursor `cur` (or NULL), each row the body that follows.
#define ut_rows(model, cur) ut_in(ut_rows_(model, cur))

static inline int32_t ut_label(const char *text) {
    int32_t n = ut_node(UT_LABEL, NULL);
    ut_prop_("text", text);
    return n;
}

static inline int32_t ut_info(const char *label, const char *value) {
    int32_t n = ut_node(UT_INFO, NULL);
    ut_prop_("label", label);
    ut_prop_("value", value != NULL ? value : "");
    return n;
}

// A link that runs action `action`, labelled `label` (NULL: the action's label).
static inline int32_t ut_link(const char *action, const char *label) {
    int32_t n = ut_node(UT_LINK, action);
    if (label != NULL) {
        ut_prop_("label", label);
    }
    ut_prop_("value", "");
    uitree_node_action(n, ut_action_of_(action));
    return n;
}

// A button that runs action `action`, of kind `kind` (UT_KIND_*; NULL: normal).
static inline int32_t ut_button(const char *action, const char *kind) {
    int32_t n = ut_node(UT_BUTTON, action);
    ut_prop_("kind", kind != NULL ? kind : UT_KIND_NORMAL);
    uitree_node_action(n, ut_action_of_(action));
    return n;
}

// ...that hands its action `arg` (arg=, read by ut_arg), keyed "ACTION/ARG"
// as the Python and Lua layers key it.
static inline int32_t ut_button_arg(const char *action, const char *arg, const char *kind) {
    char k[64];
    size_t a = strlen(action), g = strlen(arg);
    a = a < sizeof k - 2 ? a : sizeof k - 2;
    g = g < sizeof k - 2 - a ? g : sizeof k - 2 - a;
    memcpy(k, action, a);
    k[a] = '/';
    memcpy(k + a + 1, arg, g);
    k[a + 1 + g] = 0;
    int32_t n = ut_node(UT_BUTTON, k);
    ut_prop_("kind", kind != NULL ? kind : UT_KIND_NORMAL);
    ut_prop_("arg", arg);
    uitree_node_action(n, ut_action_of_(action));
    return n;
}

// A toggle (a field) bound to state `state`, labelled `label`.
static inline int32_t ut_toggle(const char *state, const char *label) {
    int32_t n = ut_node(UT_TOGGLE, state);
    ut_prop_("bind", state);
    ut_prop_("label", label);
    return n;
}

static inline int32_t ut_field(const char *state, const char *label) {
    int32_t n = ut_node(UT_FIELD, state);
    ut_prop_("bind", state);
    ut_prop_("label", label);
    ut_prop_("max", "32");
    return n;
}

// A seg bound to enum state `state`, labelled `label`, its values worded by the labels table
// `labels` (or NULL), of look `look` (UT_LOOK_SEG, _CYCLE, _SWATCHES, _PICTURES: each word an
// image's text, `own:KEY`).
static inline int32_t ut_seg_look(const char *state, const char *label, const char *labels,
                                  const char *look) {
    int32_t n = ut_node(UT_SEG, state);
    ut_prop_("bind", state);
    if (labels != NULL) {
        ut_prop_("labels", labels);
    }
    ut_prop_("label", label);
    ut_prop_("look", look);
    return n;
}

// A seg of the seg look (ut_seg_look).
static inline int32_t ut_seg(const char *state, const char *label, const char *labels) {
    return ut_seg_look(state, label, labels, UT_LOOK_SEG);
}

// Tabs bound to enum state `state`, worded by the labels table `labels`.
static inline int32_t ut_tabs(const char *state, const char *labels) {
    int32_t n = ut_node(UT_TABS, state);
    ut_prop_("bind", state);
    ut_prop_("labels", labels);
    return n;
}

// Tabs bound to row_of state `state`: a tab a row of its model, each worded by the row
// template `text` ("{.name}").
static inline int32_t ut_tabs_rows(const char *state, const char *text) {
    int32_t n = ut_node(UT_TABS, state);
    ut_prop_("bind", state);
    ut_prop_("text", text);
    return n;
}

// A progress bar showing `value` (a template) of `max`, labelled `label`.
static inline int32_t ut_progress(const char *value, const char *label, int32_t max) {
    int32_t n = ut_node(UT_PROGRESS, NULL);
    ut_prop_("label", label);
    ut_prop_int_("max", max);
    ut_prop_("value", value);
    return n;
}

// A toast keyed `key` (NULL: its kind#place), the name a host asks its
// rect by: `text` (a template) in a pill over the page's body, above its
// foot; its icon is ut_p_icon's, "check" where it has none. It draws over
// the nodes before it.
static inline int32_t ut_toast_keyed(const char *key, const char *text) {
    int32_t n = ut_node(UT_TOAST, key);
    ut_prop_("text", text);
    return n;
}

// A toast keyed by its kind and place (ut_toast_keyed).
static inline int32_t ut_toast(const char *text) {
    return ut_toast_keyed(NULL, text);
}

// A stepper: `value` (a template) between two chevrons, the back one firing
// action `prev` and the forward one `next`, each greyed while its action is
// off; left and right step it while focused.
static inline int32_t ut_stepper(const char *value, const char *prev, const char *next) {
    int32_t n = ut_node(UT_STEPPER, NULL);
    ut_prop_("value", value);
    ut_prop_("prev", prev);
    ut_prop_("next", next);
    return n;
}

// A view of text state `state`'s lines.
static inline int32_t ut_text_view(const char *state) {
    int32_t n = ut_node(UT_TEXT_VIEW, state);
    ut_prop_("bind", state);
    return n;
}

static inline int32_t ut_menu_(const char *caption) {
    int32_t n = ut_node(UT_MENU, NULL);
    ut_prop_("caption", caption);
    return n;
}

// A menu captioned `caption`, its items (ut_item) the body that follows.
#define ut_menu(caption) ut_in(ut_menu_(caption))

static inline int32_t ut_item(const char *action) {
    int32_t n = ut_node(UT_ITEM, action);
    uitree_node_action(n, ut_action_of_(action));
    return n;
}

static inline int32_t ut_table_(const char *model, const char *cur, const char *on, const char *const *cols) {
    int32_t n = ut_node(UT_TABLE, model);
    ut_prop_("bind", model);
    for (; *cols != NULL; cols++) {
        ut_prop_("cols", *cols);
    }
    if (cur != NULL) {
        ut_prop_("cur", cur);
    }
    if (on != NULL) {
        ut_prop_("on", on);
    }
    return n;
}

// A table of model `model`, its cursor `cur`, its row's action `on` (each NULL
// for none), headed by the columns named after them; its cells (ut_col) the body.
#define ut_table(model, cur, on, ...) ut_in(ut_table_(model, cur, on, (const char *const[]){__VA_ARGS__, NULL}))

static inline int32_t ut_col(const char *text) {
    int32_t n = ut_node(UT_COL, NULL);
    ut_prop_("text", text);
    return n;
}

static inline int32_t ut_cards_(const char *model, const char *cur, int32_t w, int32_t h) {
    int32_t n = ut_node(UT_CARDS, model);
    ut_prop_("bind", model);
    if (cur != NULL) {
        ut_prop_("cur", cur);
    }
    ut_prop_int_("w", w);
    ut_prop_int_("h", h);
    return n;
}

// A carousel (`ui.cards(look="carousel")`): one row of tiles at most `w` px a side off the
// centre, the centre card's twice that, its label and sub line under the row; `cur` the
// row_of it keeps its centre card in.
static inline int32_t ut_carousel_(const char *model, const char *cur, int32_t w) {
    int32_t n = ut_cards_(model, cur, w, w);
    ut_prop_("look", "carousel");
    return n;
}

// Cards of model `model`, `w` x `h` each, its cursor `cur` (or NULL), each card (ut_card) the body.
#define ut_cards(model, cur, w, h) ut_in(ut_cards_(model, cur, w, h))

// A card that runs action `action`, labelled `label`, `sub` under it (or NULL).
static inline int32_t ut_card(const char *action, const char *label, const char *sub) {
    int32_t n = ut_node(UT_CARD, action);
    ut_prop_("label", label);
    if (sub != NULL) {
        ut_prop_("sub", sub);
    }
    uitree_node_action(n, ut_action_of_(action));
    return n;
}

// A canvas keyed `key`, drawn by `draw` (or NULL), its pointer handed to
// the action `pointer` (or NULL), whose handler reads ut_point(). Its size:
// ut_p_h, ut_p_w, ut_p_size after it.
static inline int32_t ut_canvas(const char *key, ut_draw_fn draw, const char *pointer) {
    int32_t n = ut_node(UT_CANVAS, key);
    if (draw != NULL && ut_.ncanvas < UT_CANVASES) {
        ut_.canvas[ut_.ncanvas] = n;
        ut_.draws[ut_.ncanvas++] = draw;
    }
    ut_prop_("draw", "draw");
    if (pointer != NULL) {
        ut_prop_("pointer", pointer);
    }
    return n;
}

// The canvas made last takes the keys while it holds focus: `keys` is handed them before the
// frame (its row, in a list's body, ut_canvas_row()) and answers non-zero for keys it took. A
// canvas with keys is a stop.
static inline int32_t ut_canvas_keys(ut_keys_fn keys) {
    if (ut_.nkeyed == UT_CANVASES) {
        return UT_E_NOMEM;
    }
    ut_.keyed[ut_.nkeyed] = ut_.last;
    ut_.keys[ut_.nkeyed++] = keys;
    return ut_prop_("keys", "keys");
}

#ifdef __cplusplus
}
#endif

#endif // MOYBYTE_UITREE_H
