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
// and the bar's Back (or ut_pop) builds the one under it again.
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
enum { UT_A_HOOK = 1, UT_A_ROLE_CONFIRM = 2, UT_A_ROLE_BACK = 4, UT_A_ROW = 8, UT_A_SHIFT_ENTER = 16 };
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

// A handler: `row` is the row of the model the action came from, else -1.
typedef void (*ut_fn)(int32_t row);
// A page: its build, a ut_page block.
typedef void (*ut_page_fn)(void);

// The build's place and the handlers: one copy for every unit that includes this.
struct ut_ {
    int32_t at[UT_DEPTH], kids[UT_DEPTH];   // each open container, its children so far
    int32_t depth, last;                    // ...how many; the node made last
    const char *names[UT_ACTIONS];          // each action's name and handler, by its index
    ut_fn fns[UT_ACTIONS];
    ut_page_fn pages[UT_PAGES];             // the page stack, its top last
    int32_t npages;
    int32_t ev[5];                          // the running action's model slot, row, and a pointer's kind, x, y
};
__attribute__((weak)) struct ut_ ut_;

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
    ut_.npages = 1;
    page();
    return uitree_open();
}

// From a handler: the page `page` pushed (built) over this one, which Back pops.
static inline void ut_push(ut_page_fn page) {
    if (ut_.npages < UT_PAGES) {
        ut_.pages[ut_.npages++] = page;
        page();
    }
}

// The page under this one built again, the focus back where it was.
static inline void ut_pop(void) {
    if (ut_.npages > 1) {
        ut_.npages--;
        ut_.pages[ut_.npages - 1]();
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

// A seg bound to enum state `state`, labelled `label`, its values worded by the labels table `labels` (or NULL).
static inline int32_t ut_seg(const char *state, const char *label, const char *labels) {
    int32_t n = ut_node(UT_SEG, state);
    ut_prop_("bind", state);
    if (labels != NULL) {
        ut_prop_("labels", labels);
    }
    ut_prop_("label", label);
    ut_prop_("look", UT_LOOK_SEG);
    return n;
}

// Tabs bound to enum state `state`, worded by the labels table `labels`.
static inline int32_t ut_tabs(const char *state, const char *labels) {
    int32_t n = ut_node(UT_TABS, state);
    ut_prop_("bind", state);
    ut_prop_("labels", labels);
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

#ifdef __cplusplus
}
#endif

#endif // MOYBYTE_UITREE_H
