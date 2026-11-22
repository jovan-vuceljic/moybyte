// The UI engine's wasm rows: the `uitree` rows of native/os_calls.json a
// compiled app imports from `moybyte.app` (`uitree_<verb>`, named by
// native/moy_app/moy_app_wasm.c's table; the app's header is
// sdk/include/moybyte/uitree.h). A compiled app is its own front end: it
// declares its states and actions, builds its page with the engine's generic
// build calls, draws it each frame on the run's canvas and runs a handler for
// each action the engine hands it -- the same store, walk and trace a Python
// or Lua app's pages reach (moy_uitree.h).
//
// One store a run, made by the run's first row and dropped when the run ends
// (moy_uitree_wasm_end) or the next run opens (moycore_ui_snap's serial), as
// the toolkit's RUN face keeps one context a run (moy_ui_run.h).
//
// Every text, list and model crosses by value at the call (a pointer and a
// length; a list's items NUL-separated in one text), and the engine keeps
// nothing that points into the module's memory. A read is copied into the
// buffer the app hands with its capacity and answers the whole length.
//
// The rows, beyond the uit_* call each makes:
//   build(page)   the page's id is "N NAME", N its depth on the app's page
//                 stack (the SDK keeps the stack: a push or a pop is a build
//                 of the page now on top). A deeper build after `open` is
//                 traced as a push and remembers the focused key; a
//                 shallower one is traced as Back and puts the focus back on
//                 the key its page had, as the layers trace and focus them.
//   frame(flags)  the frame as the Lua layer's back end runs it: a press on
//                 a canvas with pointer= owes its action down, each drag and
//                 up (in the canvas's coordinates, at the rect the last frame
//                 drew it at; the press holds the canvas), a typed key an
//                 action's chars= holds or a letter it declares (uit_letter,
//                 the key its arg) and the confirm role's
//                 key (A, Enter, with nothing focused and no dialog) owe
//                 their actions; the host's bar is lent with no title, its
//                 way back shown where a dialog or popover shows, a page is
//                 pushed or an action holds the back role, and its Back owes
//                 the dialog's first button, the popover's close=, a pop of
//                 the page, or the back role's action; then uit_run_frame on
//                 the run's canvas with the hints band, the trace and the
//                 page depth, and the engine's actions owed after those.
//                 Each canvas the walk draws calls the module's export
//                 `_uitree_draw(node, x, y, w, h)` (moycore_ui_draw_call,
//                 the driving module's), and a trap there is refused.
//                 After the frame, the `m` key (the more role,
//                 UIT_A_ROLE_MORE) with no field focused owes the focused
//                 row's action where the role's action hangs from a rows
//                 list's node, else the page's, as the Lua layer's ROLE_KEYS.
//                 `flags` is 0 (no flag is defined yet). The engine's trace
//                 lines go to the OS log as "[trace] " lines, the Python and
//                 Lua layers' format.
//   field_enum(slot, f, values)  a model's text field f made an enum of the
//                 NUL-separated values (uit_field_enum), as a Python
//                 ui.enum field or a Lua one is.
//   open()        the visit opens (uit_open): the values set before it are
//                 the app's start and are not traced, every write after is.
//                 An action declared as the hook `opened` (UIT_A_HOOK) is
//                 the first one `next` hands out after it.
//   next(ev)      the next action owed, its index (-1: none; 0x10000: the
//                 bar's Back pops the page, which the app builds): ev[0] its
//                 model slot, ev[1] its row (-1 each where it acts on none),
//                 and where ev holds five words a pointer's kind (1 down,
//                 2 drag, 3 up), x and y.
//                 An action that is off now is traced as skipped and not
//                 handed out; a control's write is not an event here (the
//                 slot holds it: read it with get_*). Every set_* until the
//                 next `next` or `frame` is traced as the action's write
//                 (a model's as the layers trace a set: rows added, gone,
//                 changed and moved).
//   action_chars(a, chars)  action `a` is handed each typed key `chars` holds
//                 (uit_action_chars): `frame` owes it for such a key, as it
//                 owes a declared letter's action.
//   arg(out)      what the handler `next` handed out last was handed: the
//                 arg= of the button or link that fired it (an int's
//                 digits), or the typed key that owed it; the length 0 where
//                 it was handed none or no handler runs.
//   set_text, get_text  a number state's value crosses as text: set_text
//                 takes a number's digits (strtod's, all of the text), and
//                 get_text answers them as the trace spells the value.
//   error(out)    the first refusal of the run as one line,
//                 "CODE uitree_<row>(<where>): <message>". A refusal is
//                 latched: every later row of the run answers it again,
//                 and it is logged once.
//
// An answer below 0 is moy_uitree.h's UIT_E_*.

#ifndef MOY_UITREE_WASM_H
#define MOY_UITREE_WASM_H

#include <stdint.h>

#include "moy_uitree_wasm_rows.h"

// The run is over: its store and what the app kept beside it are freed. The
// module that drives a compiled run calls it as the run ends (weak there: an
// image without this engine has none).
void moy_uitree_wasm_end(void);

#endif
