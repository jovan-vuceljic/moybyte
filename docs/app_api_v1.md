# Writing an app for Moybyte

The one guide to Moybyte's app and OS surface: read it top to bottom and you
can build an app, a background service or a command on any tier. It is the
authority for what makes a cart an APP: the manifest's `moybyte` fields,
permissions, the UI tree an app draws with, files, prefs, intents, services,
messages, alarms, notifications, achievements and what each tier can call.

What it is not: the GAME verbs (drawing, sprites, maps, sound, `btn`) are
moy-spec's (SPEC.md, the console spec any moy host runs) and Moybyte's page
of them is `docs/moy_cart_api.md`; an app calls them too. Where a truth is
generated or held by code, this guide points at it rather than copying it:

| what | its authority |
|---|---|
| every call an app reaches, on every tier | the call table (§10), written from `native/os_calls.json` |
| the UI tree's kinds, props, verbs and error codes | `native/moy_uitree/contract.json` (§3) |
| the immediate `ui` verbs | `docs/history/ui_api_2026-10.md` (§3, "The immediate API") |
| Python's `moybyte` verbs, each with its signature | `runtime/system/moybyte.py`'s header |
| a Python app's globals per permission | `runtime/shell/system_api.py` |
| how the OS runs processes, and why | `docs/os_2026-11/processes.md`, `tiers.md`, `between_apps.md` |
| an app's own service: its `entries` and the calls that start it | §7, `runtime/system/scheduler.py` (AN APP'S OWN SERVICE) |
| which board runs which tier | `docs/os_2026-11.md` §5 |

Two worked examples run in the host suite, `tests/test_app_examples.py`: a
Python app on the UI tree with a list longer than the screen and prefs
(`tests/fixtures/apps/shopping.moy`)
and a Lua service answering a message (`tests/fixtures/apps/echo_lua.moy`).
`system_carts/moybyte.notes.moy` is the full-size app. Moy Mesh, an
installable app in moybyte-org/carts (`carts/moymesh/`, `pkg install
moymesh`), is the whole app in Lua: a UI tree window over a service that holds the
LoRa radio by handle and wakes on it, a Meshtastic node of its own (the
channels and presets a Meshtastic setup names, its NodeInfo under the
console's name from `moybyte.name()`, direct messages under the nodes' X25519
keys, its own pair the console's, `moybyte.key_make`); its copy
`tests/fixtures/apps/moymesh.moy` runs in `tests/test_moymesh_app.py`.

---

## 1. Your first app

An app is a `.moy` folder: `manifest.json` and a main script. No build, no
registration, no firmware. Its interface is a UI tree (§3): it declares its
state and its actions, describes its page once, and the console's engine
draws the page, moves focus and runs an action when a person takes it.

**Python** (`counter.moy/`):

```json
{
  "format": "moy-1",
  "title": "Counter",
  "runtime": "python",
  "main": "main.py",
  "extensions": ["moybyte.uitree"],
  "moybyte": {"type": "app", "permissions": []}
}
```

```python
s = ui.state(count=0, loud=False)
ui.app("Counter", icon="calc")


def add():
    s.count += 1


def reset():
    s.count = 0


ui.action("add", "Add one", add)
ui.action("reset", "Reset", reset, when="count", off="grey")


def build():
    with ui.page("Counter"):
        with ui.group("Count"):
            ui.info("Count", "{count}")
            ui.toggle("Loud", "loud")
            ui.link("add")
            ui.link("reset")
            ui.label("{count|plural press,presses} so far, {loud?loud:quiet}")
```

Read it top down:

- `ui.state` declares the app's state, typed by its first values: an int and
  a bool. Only a handler writes it.
- `ui.app` names the app: its title and its icon.
- `ui.action` names what a person can do: a name, the words every node
  shows for it, and its handler. `when="count"` makes Reset unavailable
  while the count is 0, and `off="grey"` says it stays on the page, dimmed,
  meanwhile.
- `build` is the root page. It runs once, at the open, and reads no state:
  `"{count}"` is a template the engine fills in, and `"loud"` names the
  state the toggle writes. A link fires its action on Enter, A or a tap.

The app defines no `_init`, `_update` or `_draw`: the engine runs the page.

**Lua** is the same app with `"runtime": "lua"` and `"main": "main.lua"`. A
page is a named function, and a node's props go in a table:

```lua
ui.app("Counter", { icon = "calc" })
local s = ui.state { count = 0, loud = false }

ui.action("add", "Add one", function() s.count = s.count + 1 end)
ui.action("reset", "Reset", function() s.count = 0 end, { when = "count", off = "grey" })

ui.page("counter", function()
  ui.group("Count", function()
    ui.info("Count", { value = "{count}" })
    ui.toggle("loud", { label = "Loud" })
    ui.link("add")
    ui.link("reset")
    ui.label("{count|plural press,presses} so far, {loud?loud:quiet}")
  end)
end, { title = "Counter" })
```

Both halves are one conformance fixture (`tests/uitree_conformance/counter/`),
held to one trace and one picture, and its compiled half is §3's C example.

**Start from a template:** `moy app new Counter` writes this folder, its
manifest with an `id` (§2). `--tier lua|wasm|wasi|c` writes the other tiers'
(the Lua app above, §3's compiled counter, a WASI or C command) and
`--service <tier>` an app's own service. `moy app check counter.moy` says
what the console would refuse and which permissions the code uses that the
manifest does not ask for (or asks for and never uses), `moy app build
counter.moy` compiles a wasm or C program from its `src/` for every chip, or for those
`--chip esp32s3|esp32p4|host` names (Python and Lua have nothing to build), and `moy app stubs counter.moy` gives an editor the
tier's names. `moy app` is moy-spec's `moy` running Moybyte's plugin,
`moy-app`, which `make setup` installs (`sdk/README.md`). The UI tree's own
checks are `tools/uitree_check.py counter.moy` (Python) and
`tools/uitree_lua_check.py counter.moy` (Lua): every page built once with
nothing drawn, every mistake reported with its code (§3, Errors).

**Run it in the simulator:** `python tools/simulate_desktop.py --cart counter.moy`
(`--windowed --size 1024x600 --font-scale 2` for a P4's desk). The simulator
copies the folder into its store, `~/.moybyte/projects`, over the copy there
at every launch, so each run is the folder as it is; `moy app push counter.moy`
copies it there without a launch.

**Run it on a board:** `tools/board.py tdeck push counter.moy` (or `moy app
push counter.moy --board tdeck`) copies the folder into the board's store, then
`tools/board.py tdeck run Counter` opens it (any board id from
`tools/board.py ports`; the `on-glass` skill has the rest).
On the console itself, the home's Make tab makes and edits carts, apps
included.

**Start here, per tier.** The same six steps in every tier; the rest of
this guide is each step in full.

| step | Python | Lua | wasm app | WASI program | C program |
|---|---|---|---|---|---|
| the manifest (§2) | `"runtime": "python"` | `"runtime": "lua"` | `"runtime": "wasm"`, `"extensions": ["moybyte.app"]` | `"runtime": "wasm"`, `type` `command` or `service` | `"native": [chips]`, `type` `command` or `service` |
| permissions (§6) | its list; the prompt calls it trusted | its list, enforced | its list, enforced at load | its list | `full_access` and its list |
| entry points (§7, §11) | an app's state, actions and `build` (§3); a service's `moy_start`; a command's `main(argv)` | an app's state, actions and pages (§3); `moy_start` | the exports `_init`, `_update`, `_draw`, an app's `_draw` running `ut_frame()` (§3) | `_start` | `main` |
| messages and timers (§8, §9) | `moybyte.on`, `send`, `every`, `after`, `at` | the same | `moybyte_on`, `moybyte_recv`, `moybyte_every` | `poll_oneoff` on `MOY_EVQ_FD`, `moybyte.os` | `poll` on `MOY_EVQ_FD`, `moy_on` |
| files (§5) | `files` | `files`, `io`, `os` | `files_*` imports | WASI's own and `moybyte.os` `files_*`, in the granted folder | POSIX, in the granted folder |
| build and test on the host (§12) | `tools/simulate_desktop.py --cart`; `tests/test_app_examples.py` | the same | `moy app build`, then the simulator | `moy app build`; the terminal | `moy app build --chip host`; the terminal |
| example | `tests/fixtures/apps/shopping.moy` | `tests/fixtures/apps/echo_lua.moy` | `tests/fixtures/wasm/app_talk.moy` | `tests/fixtures/wasm/wasi_svc.moy` | `tests/fixtures/elf/elf_svc.moy` |

Badges (`award`, `progress`, §9) are a call in every tier and may be called
freely, every frame if need be.

**Which tier for which work.** Every tier reaches the same calls (§10), so
choose by cost and reach, not by what is available:

| the work | the tier | why |
|---|---|---|
| an app with a window, most apps | Python or Lua | the fastest to write and change, and the console's own apps are Python; Lua is sealed to its permissions, Python is trusted (§6) |
| light background work: a reminder, a sync, an alarm, a reply to messages | a Lua service | a small state of its own on its own task, sealed like a Lua app |
| a game, or one binary for every board and the browser | a wasm app | compiled once for every chip, sealed by its imports |
| a command, or heavy work that is portable: a codec, a protocol, a compressor | a WASI program | the same portability, with POSIX-style I/O; each running instance holds its own linear memory, in 64 KiB pages, which a P4 affords and an S3 feels, so prefer a Lua service for light work there |
| work near the hardware, or one chip's full speed | a C program (ELF) | built per chip, and unsealed on the S3s (`full_access`, §6) |

**What a service survives.** A service outlives its app's window on every
tier. On the S3s a game that needs the whole board stops the VM. Python
services pause: they are stopped before it and started again after it, a new
process with fresh timers. Every Lua, wasm or C service keeps running: its pid
and timers carry on and its messages to other services arrive, while a call
that needs the console (a notification, a role the shell serves) waits until
the game ends (`docs/os_2026-11/processes.md` §5). The P4s have no VM stop.

## 2. The manifest

moy-spec's fields sit at the top level (SPEC.md §3.1 is their authority):
`format`, `title`, `id` (`<author>.<name>`, #162: what your grant, prefs,
consent and crash strikes are keyed by; without it, the folder's name less
`.moy`, which is also its name where another folder is named for that id:
the folder `<id>.moy` owns it, `moy_store_base.id_in_folder`), `version` (an integer; bump it when a seed cart changes, #47),
`runtime` (`python`, `lua`, `wasm`), `main`, `canvas` (`320x240`, the default,
`160x120` or `128x128`), `fps`, `extensions`, `input` and `palette`
(`docs/moy_cart_api.md` has how a Moybyte cart reads each).

Moybyte's fields go in ONE object, `"moybyte"`; at the top level they read as
absent (`runtime/carts/moy_store_base.py`, `VENDOR_KEY`):

| field | is | more in |
|---|---|---|
| `type` | `game` (the default), `app`, `service` or `command` | §3, §7, §10 |
| `permissions` | what the app may reach: §6's names | §6 |
| `required` | permissions it cannot run without: absent, its launch is refused by name | §6 |
| `animates` | `true`: draw every frame (a clock, a meter); an app draws on change otherwise | §3 |
| `handles` | the MIME types it opens (`"text/markdown"`, `"image/*"`) | §5 |
| `receives` | the message names another app may send it | §8 |
| `entries` | the cart's entry points beside `main`: `{"service": file}`, its own service's program | §7 |
| `achievements` | the badges a game declares | §9 |
| `native` | the chips a C cart carries a module for (`["esp32s3", "esp32p4"]`) | §10 |
| `wasi` | `true`: an app that is a WASI command the Player runs, drawing its screen whole (`moy_present`) | `runtime/run/wasi_run.py` |
| `audio_ring` | a compiled cart's audio ring depth in frames | `docs/os_2026-11/hardware.md` §2 |
| `config`, `edit` | the "Make it mine" values `cfg(key)` reads and the Editor's rows that change them | `runtime/carts/moy_carts.py`, `NEW_TEMPLATE` |
| `assets` | a cart's scenes, in order | `docs/moy_cart_api.md`, Scenes |
| `glass`, `pictures` | a wallpaper drawn per glass, a picture wallpaper | `docs/theme_and_shell_2026-11.md` §3.9 |
| `graduated` | written by the Editor when blocks become code; never by hand | `runtime/editors/blocks.py` |
| `api` | the console API level the cart needs (an integer); none is the lowest | "The API level", below |
| `system`, `order`, `targets`, `app`, `fixture`, `seed` | the seed carts' (`system_carts/`): a system cart, its place, the targets it ships to, a shipped app's declaration, `true` for a test fixture, which only the host seeds: no console image or browser bundle carries it and no release publishes it as an official cart; and `seed: false` for an official cart no store is seeded with: the release publishes it, Get Carts installs it, and no image, browser bundle or host store carries it | §13 |

### The API level

The console API level is ONE integer, `API_LEVEL` in
`runtime/carts/moy_store_base.py`, that goes up whenever anything an app can
reach grows or changes: a row, role, permission or error code of
`native/os_calls.json` (and with it every tier's names: Python, Lua, `ui`, the
compiled and WASI imports, the ELF table), a manifest field
(`moy_store_base.VENDOR_FIELDS`), the moy-spec format level the console runs
(`runtime/run/player_fit.py`'s `FORMAT_LEVEL`), or the UI tree's contract
(`native/moy_uitree/contract.json`, §3: a kind, prop, word, verb, role,
`takes=` value, retired name or error code, and whether each is built; its
prose is left out). `tools/api_level.py` pins a
fingerprint of those tables on the line below the level, and
`tests/test_api_level.py` fails a table that changes while the level stands; the
fix it names is to bump `API_LEVEL` and re-pin with `tools/api_level.py`.

The level is 1, and until the API is frozen at the first public release
(`API_FROZEN` beside it) the fingerprint is re-pinned freely without a bump;
from then on every change bumps the level and the API is add-only.

A cart names the level it needs as `"moybyte": {"api": N}`, the lowest level
that has everything it uses; a cart that names none needs the lowest, 1. A
console at that level or above runs it and lists it. Below it:

- the launch is refused before any of the cart's code runs, on the "Needs a
  newer console." notice a newer `format` gets (the Player), or with the
  refusal a service, command or install reads (`runtime/shell/app_perms.py`);
- Get Carts still lists it, as "Needs update", saying which level it needs
  and which this console has (`cart_index.newer_why`), and will not get it.

An official cart (a seed cart its release publishes, `tools/web_pack.py`) needs
the level of the build that published it, so a console a release ahead or
behind lists its release's carts by level, whatever its build; only the browser
console add-on is matched to the image's own page (#271).

**The rule, from the first public release (owner, 2026-11-21):** the API is
add-only. A level adds; it never removes or repurposes anything a lower level
had, so a cart that ran at level N runs at every level above it. How a breaking
change is made is decided when there are user apps.

## 3. The UI tree: drawing an app

An app's interface is a UI tree. The app declares typed state and named
actions, and describes each page once; one C engine (`native/moy_uitree`,
the one the console's own apps run on) lays the page out, draws it in the
console's theme, moves focus, routes keys and taps to the actions and
answers the host's Back. Python, Lua and compiled apps share it, each in its
own spelling:

| tier | the API | the manifest |
|---|---|---|
| Python | `ui` is the UI tree (`runtime/uitree/uitree.py`; `runtime/run/player_tree.py` runs a cart) | `"extensions": ["moybyte.uitree"]` |
| Lua | `ui` is the UI tree (`runtime/run/uitree.lua`) | `"extensions": ["moybyte.uitree"]` |
| compiled (wasm) | `ut_*` over the `uitree_*` imports (`sdk/include/moybyte/uitree.h`) | `"extensions": ["moybyte.app"]` |

`native/moy_uitree/contract.json` is the authority on every kind, prop,
verb and error code below; `tests/uitree_contract/known.json` lists where a
tier lacks one, and this guide names only what the Python tier builds.

### The model

**State.** `s = ui.state(...)` declares the app's state once, at the top
level. Each name is typed by its first value, and a write of another type is
an error (S02):

| declared as | holds |
|---|---|
| `0`, `1.5`, `""`, `False` | an int, a number, a text, a bool |
| `ui.enum("a", "b", init="a")` | one of named values |
| `ui.opt(0)` | a value that may be absent: it draws as nothing and is false in a condition |
| `ui.record(field=initial, ...)` | a fixed set of typed fields, written whole (`s.r.set(field=...)` in Python) |
| `ui.model(key="id", id="", name="")` | rows keyed by one field: a list, a table, cards |
| `ui.row_of("items")` | one row of a model, by its key: a list's cursor, the row a page shows |
| `ui.doc("", "markdown")` | a text document the engine owns (Documents, below) |

A handler reads `s.count` and writes `s.count = 3`. A model is written whole
(`s.items = [{...}, ...]`, Lua `s.items:set({...})`) or by its verbs
(`put(row)`, `update(key, field=...)`, `remove(key)`, `get(key)`; Lua's
`s.items:put(row)` and kin), never by index. A row a handler is handed is
read-only.

**The app.** `ui.app(title, icon=...)` declares the app once, at the top
level (D04 without it): its title is a template (the bar's zone, the desk
window's strip and chip), `size=(w, h)` its window in desk units or
fractions of the glass (`"7/8"`), `min=(w, h)` the least a window shrinks to,
and `back=` an action Back runs where no page is left to pop (`"pages"`, the
default, leaves the app). Where a window stands is the console's (D01).

**Actions and hooks.** `ui.action(name, label, handler, ...)` is something a
person can do: the label names it on every node and in the hints band. A
node names an action by its name (`ui.button("add")`). `ui.hook(name,
handler)` is a handler no person sees, named by a node's `on=` or
`changed=`, a timer or a post. Their props:

| prop | does |
|---|---|
| `takes=` | what every site hands the handler: `"none"`, `"row"` (the model row the action came from), `"arg"` (a site's `arg=`), `"char"` (a typed character, with `chars=`), `"pointer"` (a canvas's event) |
| `when=`, `off=` | a condition under which the action is available; `off="hide"` removes its nodes meanwhile, `off="grey"` dims them and takes them out of focus |
| `row=` | the `row_of` whose row the handler gets wherever it is taken (a list's verbs in a band or a menu) |
| `keys=` | key shortcuts: a letter, `"ctrl+d"`, or a role, `"role:search"` (§4) |
| `hint=` | the hints band's words for it (`""` keeps it out of the band) |
| `icon=` | the icon a button or tool shows for it |
| `push=` | a page function the action opens, with no handler |

The commands a handler gives: `ui.push(page)` opens a page over this one,
`ui.pop()` closes it, `ui.focus(key)` moves focus to a node,
`ui.after(ms, name)` runs an action or hook later (`ui.cancel(name)` drops
it), and `ui.post(name, value)` hands a hook a value from outside every
handler (a service's message, a callback), which it runs before the next
frame. The hook named `opened` runs as the app opens: where an app fills its
models and reads its prefs.

A page that shows one row takes it as its argument: a Lua page declares
`arg=` (a `row_of`) and is pushed with its row (`ui.push("thread", row)`), a
compiled one by `ut_push_row`. The push writes the row into that state, and
each page on the stack keeps the row it was pushed with: when the page over
it pops, the state holds that row again (where it still stands), so a page
pushed over itself on another row steps back to its own. A Python page is a
function and carries its argument itself: `ui.push(lambda: thread(key))`.

A page's `shown=` names an action or hook that takes nothing, which runs
each time the page becomes the top page: at its push, and at the Back
that pops the page over it (after its `arg=` holds its row again), before
the frame that draws it; the first page at the open runs `opened` instead.
It is where a page shapes what it shows from its argument, as Moy Mesh's
thread does its messages and draft. Python and Lua pass it with the page
(`ui.page(title, shown="name")`, Lua's `{ shown = "name" }`), a compiled
page as its first prop (`ut_p_shown("name")` after `ut_page`).

**Pages built once.** A page is a function that describes nodes and reads
no state. Python's root page is the function named `build`, and a page opens
`with ui.page(title):`, its containers `with` blocks. Lua registers each
page by name, `ui.page(name, build, { title = ... })`, the first registered
opening, and a container takes its body as its last argument. A page builds
at the open (or at its push), and from then on the engine evaluates its
templates and conditions each frame: a node never rebuilds because a value
changed.

**Templates and conditions.** A text prop is a template: literal text with
`{...}` pieces the engine fills in.

| piece | shows |
|---|---|
| `{count}` | a state's value; `{rec.field}` a record's field, `{doc.line}` a document's |
| `{.name}` | the field of the row a node stands in (a list's body, a card, a column) |
| `{count\|plural press,presses}` | the number and the word that agrees with it |
| `{x\|fmt %.1f}` | a printf spec over an int or a number |
| `{mode\|map MODES}` | an enum's word from a label table, `ui.labels("MODES", {"a": "Apple", ...})` |
| `{items\|count}`, `{n\|bytes}` | a model's row count; an int as a size in bytes |
| `{loud?on:off}` | one of two texts by a condition (a `:` inside a branch is `\:`) |
| `{@desk?28:20}` | a system value: `@desk`, `@handheld`, `@wide`, `@tall`, `@touch`, `@input`, `@focus`, `@current` |

A prop that is a condition (`shown=`, `when=`, `focus=`, `marked=`) is a
name (true where a bool is true, a number non-zero, a text non-empty, a
model holds rows; an enum is compared, `mode=a`), `!name`,
`name=value` or `name!=value`, joined by `&&` or by `||` but never both.
`ui.derive("ok", cond="a && (b || c)")` names a longer one, and
`ui.derive("line", text="...")` a template. Every node takes `shown=`, which
hides it while its condition is false.

**Strict errors.** Every mistake is an error with a code, the app's file and
line, what was expected, what was found and the fix, in one line:
`error[A01] main.py:12: ...; fix: ...`. There are no warnings. A mistake
raises at the call that makes it, a declaration's as the app loads and a
page's as it builds, and the run stops on the stop card (§11). The checkers
find them with nothing drawn: `tools/uitree_check.py` imports a Python app
(a cart by its folder) and builds every page for every size class, and
`tools/uitree_lua_check.py` runs a Lua app's scripts and builds its pages.
The codes are in the table below.

### The kinds

Each kind is `ui.<kind>(...)`; a container is a `with` block in Python and
takes a function last in Lua. The tables spell each kind as Python calls
it; Lua passes the props in a table after the head
(`ui.toggle("loud", { label = "Loud" })`, §1). Every node takes `shown=`; a
row's child takes `grow=`, a grid's `span=`. A kind marked "no Lua" is
Python's alone.

**The page and its regions**

| kind | is | key props |
|---|---|---|
| `page(title)` | a page: its title is the bar's | `status=` the hints band's lead words, `shown=` an action or hook run as it becomes the top page (the model, above) |
| `group(caption)` | a captioned column of rows | `look="card"` on a card, `"rules"` a rule between rows; `gap=`; `close=` |
| `row(key)` | children side by side | `wrap=`, `gap=`, `pad=`, `mid=`, `close=` what Back does while it shows |
| `scroll(key)` | a region that scrolls its children | `follow=` opens at its foot and keeps a new row in view; `snap=` shows whole rows, a "More below" cue where it leaves some out below and, following, an "Older messages" one above |
| `foot()` | the page's docked foot: buttons at its end, a label before them | `look="share"` its buttons share its width, `"band"` an edge-to-edge strip |
| `split(dir, sizes)` | cells along `"row"` or `"col"`, sized in units or weights (`"1*"`) | `gap=`, `pad=` (ints at 1x, 8 each unless given), `align=`, `rule=` |
| `grid(cols, rows)` | a fixed grid of cells | `gap=`, `pad=` (ints at 1x, 6 and 0 unless given), `w=`, `h=` |
| `panel(key)` | a region of its own | |
| `switch(name, cases)` | one of several bodies by an enum's or a bool's value (`"_"` the rest) | |
| `panes(dir)`, `pane(key)` | panes a person resizes by their dividers; one grows (no Lua) | `size=`, `start=`, `min=`, `grow=`; a pane's `tabs=`, `title=` |
| `slot(name)` | a hole another process's window docks in (no Lua) | `min=` |
| `tools(key)`, `lent(key)` | buttons a shown tab lends, and where they draw (no Lua); `lend="bar"` lends them to the shell's bar, after its title | `lend=` |

**Words and pictures** (no stop, but where noted)

| kind | is | key props |
|---|---|---|
| `label(text)` | a line of text | `face=`, `tone=`, `icon=`, `wrap="word"` with `lines=`, `size="fit"`, `size="text"` (in a placed row, as wide as its text and its icon, in the ui face), `align=`, `scale=`, `w=` |
| `info(label, value)` | a label and its value on one row | `icon=`, `tag=` a pill, `signal=` 0 to 4 bars, `tone=` |
| `status(text)` | a status line, cut at its `" · "` fields | |
| `rule()` | a divider | |
| `note(lines)` | a card in the page's flow | `icon=` (`"warn"` in the danger tone) |
| `empty(title)` | what a page with nothing on it says; controls built in it stand under it; its lines wrap at word breaks to the column it stands in (a page, a cell); where its disc would push them past its room (its view, a placed page's stack), its words stand without it | `icon=`, `lines=` |
| `toast(text)` | a pill over the page's foot, or a banner | `icon=`, `sub=`, `burst=`, `look="flat"` `"badge"` `"secret"`, `key=` the name a host's `rect_of` asks by |
| `bubble(text)` | a chat message, a stop | `side="in"`/`"out"`, `head=`, `status=`, `signal=`, `tone="failed"`, `lines=`, `on=`, `cut=` |
| `text_view(name)` | read-only lines of a text state or a model | `wrap=`, `follow=`, `syntax=`, `face=`, `look="well"`, `gutter=` |
| `picture(image)` | one picture | `side=`, `icon=`, `tone=`, `look="tile"`, `on=` makes it a stop |
| `progress(value)` | a bar of an int state | `max=` (required), `label=`, `look="count"` |
| `month()` | a month's calendar | `year=`, `month=`, `today=`, `prev=`, `next=` |
| `hints(model)` | keycap hints, one a row of the model | `keys=`, `label=`, `tail=`, `drop=`, `on=` |

**Controls** (each a stop; a control bound to a state writes it two-way)

| kind | is | key props |
|---|---|---|
| `button(action)` | a button | `kind=` (`normal`, `primary`, `danger`, `tonal`, `bar`), `label=`, `icon=`, `alone=` icon only, `arg=`, `marked=`, `look="hero"`, `w=` |
| `link(action)` | a row that fires its action | `label=`, `value=`, `icon=`, `tag=`, `signal=`, `swatch=`, `sub=`, `count=`, `mark=` |
| `toggle(label, name)` | a bool | `on=`, `hint=`, `when=` with `off=` (below) |
| `slider(label, name, lo, hi)` | an int from lo to hi | `look="steps"`/`"blocks"`, `icon=`, `on=`, `when=` with `off=` (below) |
| `field(label, name, max)` | a line of text | `hint=` shown empty, `commit=True` a draft written on Enter, `edit="open"` its edit open as focus comes onto it (§4), `keys="number"` the on-screen keyboard's layout (#239; draws nothing), `keys="name"` a name's characters alone (a-z 0-9 _ -, a capital typed as its small letter, a space as -, _ and - never first; any other key refused as typed), `secret=`, `grow=`, `on=`, `changed=`, `when=` with `off=` (below) |
| `seg(label, name)` | one of an enum's values, or of a model's rows | `labels=`, `text=`, `icons=` (over a `row_of`, each row's icon before its word), `look=` (`seg`, `cycle`, `swatches`, `pictures`), `on=` |
| `tabs(name, labels)` | a tab strip over an enum, or over a `row_of` a tab a row; a `switch` on the same name is its body | `icons=`, `offered=`, `hint=`, `text=` |
| `stepper(value, prev, next)` | "‹ value ›", its chevrons two actions | `tone="dim"`, `grow=` |
| `cells(name)` | a palette's colour cells over an int state | `count=`, `first=`, `cols=`, `side=`, `gap=`, `clear=`, `edge=`, `pick=` |

**Lists of rows**

| kind | is | key props |
|---|---|---|
| `rows(model)` | a model's rows, each drawing the body (Python `with`, Lua the function) | `cur=` the `row_of` focus writes, `changed=` run with the row where the user moves it from one row to another (focus arriving from elsewhere writes `cur=` alone), `current=` the row marked, `check=`, `empty=`, `by=` with cases, `filter=`, `group=` |
| `cards(model)`, `card(action)` | rows as cards; `card` is the body | `cur=`, `current=`, `w=`, `h=`, `cols=`, `flow=`, `look=` (`carousel`, `shelf`, `icons`, `column`); a card's `label=`, `sub=`, `image=`, `badge=`, `fill=` |
| `table(model)`, `col(text)` | rows as a table, one `col` a column | `cols=` the header, `cur=`, `changed=` (as a rows' list's), `on=`, `empty=`; `row=` (a height, or an int state holding one) with one canvas child that draws each row and, with `pointer=`, takes the press on its row (`ev.row`) |

**Over the page**

| kind | is | key props |
|---|---|---|
| `dialog(title, buttons)` | a modal card; Back takes its first button | `shown=`, `kind=`, `labels=` its buttons' words, `look="keys"` no buttons on the T-Deck |
| `popover(key)` | a card hung from a node | `anchor=`, `w=`, `close=` Back's action, `wash=` |
| `menu(caption)`, `item(action)` | a menu and its items | an item's `icon=`, `label=`, `kind="danger"` |

**Drawing and editing**

| kind | is | key props |
|---|---|---|
| `canvas(key, draw)` | a rect the app draws itself (Canvases, below) | `h=`, `w=`, `reads=`, `pointer=`, `keys=`, `hint=`, `focus=`, `mark=`, `ground=` |
| `text_editor(name)` | the console's text editor over a `ui.doc` (no Lua) | `find=`, `marks=`, `gutter=`, `focus=` |

### Layout

**A flowing page** stacks its nodes down its room. A page whose rows run
past its room scrolls and draws its scrollbar's thumb, as a `ui.scroll`
region does; the engine moves focus into view and keeps each region's
offset. A list, a table, a `scroll` region and a `text_view` scroll on the
engine's one scroll model and get their fast frames from it (shift frames,
`docs/surface_model_v1.md` §14.7): an app keeps no scroll offset or frame
path of its own (owner, 2026-10-29). A long document is a `text_view` or a
`text_editor`; a long list is one `rows` or `table`.

**Rows.** A `row` sets its children side by side on one line of the stack:

- a button at its natural width unless `grow=True`, a field growing, a
  picture beside a `group` column of labels, a `rule()` a line down the row
  between its neighbours, a label after the row's filler at its end;
  children all at their own widths are centred; what they draw ends at
  the page's view, as a stacked row's does;
- `wrap=True` packs its children from its start at their natural widths (a
  group as wide as its widest child), one that does not fit starting a line
  under them (the desk home's buttons); in a group's column the row stands
  at its cell;
- a row of buttons wider than its room closes its gaps, then stands its
  labelled icon buttons as their icons alone, from the end, until it fits;
  a row from a model's cells (`ui.rows(dir="row")`) keep their labels and
  are cut, the widest first, to one width, and dropped from the end where
  even that does not fit;
- `ui.row(key, grow=True)` on a flowing page fills its stack, so the rows
  after it stand at the page's foot and the page fits its room.

**The foot.** `ui.foot()` (the end look) docks its buttons at their natural
widths at the page's end, a status label before them, under what scrolls;
`look="share"` shares its width among them. `ui.toast(text, icon=)` is a
pill over the page above its foot (`look="flat"` in flat fills, filling the
page's room), and with `sub=` a banner: a card at the top centre of the
page, `text` over the `sub` line, `burst=` (0..255) its confetti;
`look="badge"` is an achievement's banner instead, at the foot of the
page's room, ringed in the accent, `burst=` its shine crossing it, and
`look="secret"` the badge's with the confetti too. A dialog lies over the
page.
`ui.page(title, status=)` leads the hints band with its words (a page laid
out in a split, its own or one in a switch's shown case, has the band cut
from its room). A split among a page's other rows, or in a group or a
scroll, stands where they flow instead, as tall as its tallest cell (a
column split its cells' sum), each cell a column.

**Groups and splits.** `ui.group("", look="card")` lays its rows on a card
(as a split's cell, the cell is the card), and `look="rules"` parts its rows
with a rule as a captioned group's are (a `row` among them one of its rows);
`gap=` sets its column's children that far apart. `ui.split(..., rule=True)`
draws a rule between its cells; a row split's fixed sizes that its width
cannot hold share it by their sizes, and a cell that is a row, a group or a
seg widens to what it needs, its neighbours giving up at most half theirs
and never their least (a group's least is its links' labels and icons: a
link's value gives way to its label).
Groups in a `row` stand side by side, each a column of its rows (no
caption), on a flowing page and a placed one.

**Spacing is pixels at 1x (owner, 2026-11-24).** Every `gap=` and `pad=`
(a group's, a row's, a split's, a grid's, cells', cards', panes') is a plain
int, literal or bound, meaning pixels at scale 1. The engine multiplies it by
the chrome scale in force (`layout_base.scale`): a handheld's font scale, its
tap floor's where that stands over it, and the desk's unit, 2 at chrome size
1. A page never scales a spacing itself: `tests/test_uitree_spacing.py`
refuses one multiplied by a scale. Hairlines, borders and rules take no
scale.

A column split's cells that run past its height take the overrun from its
palettes (`ui.cells`), whose cells fit the room left them down to a third
of their side (8 px at least); past that the column scrolls, its cells at
their spans.

**A placed page** gives each region a rect by the engine's one layout rule:
a container gives each shown child its rect, fixed rows their height and
the fills sharing the rest, a text editor whole lines. A `rows` list
standing in a placed stack (no `scroll` round it) is a fill that scrolls
its rows, as a table is; with `dir="col"` its rows' cells stand down the
stack instead, as `dir="row"` stands them along a placed row: a button its
`w=` down the stack, else a square of the stack's width, and a labelled bar
item its own width, centred across. A Python app whose
state holds a `ui.doc` runs on the Editor's kinds (`text_editor`, `panes`),
and its pages are placed; `split` and `grid` place their cells on any page.

**How the kinds look.** What the tables above leave out:

- `label(..., scale=)` draws its face at that whole scale (a display line,
  never under the page's), and `w=` keeps its text that wide at most (a
  measure of prose); `text_view(..., look="well")` lays its prose on a well,
  and `gutter=True` numbers its lines in a gutter before them.
- `button(..., kind="bar")` alone is a flat icon, narrower than a button's,
  the largest its row holds (in the shell's bar every icon alone draws at
  its zone's size, 16 units at the page's scale, centred in its cell), and
  a button's `kind=` may be a template;
  `look="hero"` is the page's lead verb (the desk home's), half again a
  row's height with twice the pads, on a flowing page. On the desk a
  popover anchored at a button or a link hangs under it.
- A link with `sub=` is a list's two-line row (a conversation, a contact):
  its `icon=` leads it (`"@NAME"`: the name's initials on a disc), its value
  sits at the right of its label, `sub=` is the line under them with
  `count=` a badge at its right, and `tag=` (a pill) or `mark=` (an icon)
  follows the label; each a template, empty for none.
- A link's `swatch="#RRGGBB"` (a template, empty for none) draws a chip of
  that colour before its value; a swatches row whose label its dots would
  cut moves them into its right pad where that makes it whole, else shrinks
  them, as far apart, until it is.
- A slider's `look="blocks"` is a meter, its steps' blocks across the whole
  row (with no label, 10 units a step and 12 more wide in a row).
- A field's, a toggle's or a slider's `when=` (a condition) comes with
  `off=`, as an action's does: while the condition fails, `off="grey"` dims
  the control and it is no stop, `off="hide"` takes it off the page; one
  without the other is O01 or O02.
- `stepper(value, prev, next)` is "‹ value ›", the bar's chevrons firing the
  two actions and greyed while either is off (its `when=`), one stop whose
  left and right step it, at its own width (centred where it is stacked) or
  with `grow=True` a fill whose chevrons stand at its ends.
- `seg(label, ".FIELD", text=...)` in a rows' body binds an int field of the
  row, the index of its item, its items the lines `text=` renders over the
  row. A seg's `look="pictures"` shows each item as the picture its word
  names (`own:KEY`) in a tile at the row's right, the current one's on the
  selection plate, left and right wrapping and activation taking the next,
  its label on a line of its own over the tiles where they would cut it;
  `ui.pictures.put(key, render=..., clear=True)` leaves a drawn picture's
  corner colour out, the tile showing there.
- `tabs(name, text=)` bound to a `row_of` is a tab a row of its model, each
  worded by the row template `text=` (the Editor's Blocks objects).
- `cells(name, ..., clear=N)` shows colour N as clear, transparency's grey
  checker under a white stroke corner to corner (the sprite editor's
  colour 0).
- `hints(MODEL, keys=, label=, tail=, drop=, on=)`: one keycap hint a row,
  no stop; the rows `tail=` holds stand at the row's end, the rest from its
  start in order, and where they run into the end the rows `drop=` holds go
  first, then the others, the last first each time; a press on one fires
  `on=` with its row.
- `dialog(..., look="keys")` draws no buttons on the T-Deck, whose band's
  Enter and Esc are its buttons, and a dialog of more than one field names
  the arrows that move between them; its `labels=` (one template a button,
  in the buttons' order) names its buttons where their actions' labels
  would not (one dialog whose verb reads Keep or Replace).
- A card's `badge=` marks its picture and its `label_icon=` stands an icon
  before its label. `cards(..., pad=)` sets the gap its columns are counted
  at, `current=` marks the card whose key a state holds, and `flow=True`
  lays the cards in the page's flow (in a group, between its caption and
  its rows), where they scroll with the page, not in a region of their own
  that takes the rest of it.
- `picture(..., look="tile")` draws the picture as a carousel's tile of its
  own at its place, `side=` across, its shadow round it and its corners
  those of a carousel's centre card (the desk home's hero); `on=` makes a
  picture a stop that a tap or Enter fires.

**The home's bands: `cards` looks.** The engine moves each of them (the
toolkit's table of parts); `tone=` (a theme role or `#RRGGBB`, a template,
empty for the theme's ink) inks their words over a black shadow, and `cur=`
follows the card at rest (a value the app writes there moves the band to
it).

- `look="carousel"`, on a handheld: from where the stack stands to the
  page's foot, one row of tiles at most `w=` a side (the largest that shows
  a whole cover at a clean scale and leaves its words their room), the
  centre card twice that and each tile's size a function of its distance
  from the centre alone. Left and right (the wheel's notches too) glide it a
  card, a drag carries it and a fling or a let-go settles on the nearest
  card; the centre card is lifted by the focus mark at rest, its `label=` in
  the hero face and its `sub=`'s tab-separated items, a dot between each
  two, under the row. Enter or a tap on the centre card at rest fires its
  card's action, and a tap on another card glides it to the centre.
- `look="carousel"`, on the desk: the desk home's shelf, one row of cards
  all `w=` a side (glass pixels), captioned over them with its `label=` (a
  template) and the count of its cards, apart by a dot. The arrows (the
  wheel's notches too) make the next card current in the frame they are
  pressed and the shelf glides to show it with two cards before it; a tap
  on a card makes it current, and a tap on the current card at rest or
  Enter fires its action. The current card wears the focus mark while the
  cards hold the keys and a current mark otherwise, and the cards scrolled
  past the shelf's margin are cut there.
- `look="shelf"`: the cards in the rows its room holds, in columns that
  scroll across (cards of the clean side a carousel's neighbour takes, the
  desk's a whole cover, the columns spaced so the last on the glass stands
  cut by a third or more), each card's `label=` under it.
- `look="icons"`: tiles in the columns its room holds, in rows that scroll
  down, each named under it on the desk and, on the handheld, the current
  card named with its `sub=`'s items in a caption band along the foot.

- `look="column"`: tiles `w=` a side on rows `h=` apart (in pixels; the
  class's desk tile where unset) down the room's left edge, column after
  column, each named under it, the columns as wide as the widest name and
  the tiles shrinking an eighth at a time until every card shows (the
  windowed desk's apps). A card's `fill=` (a theme role or `#RRGGBB`, a
  template; empty for the theme's) is its tile's colour, its picture stands
  on the tile, 24 of its 44 across, and its name is in the theme's desk
  label ink over the theme's label shadow (with `tone=`, over a black one).

In a shelf, icons or column grid the arrows step the current card across it and the
view lands where it shows that card with its margin, the wheel's notches
step it down (Shift's across), a drag scrolls the view and a release flings
it, a tap on a card makes it current and fires its action as Enter does, the
current card grows and wears the focus mark flat while the cards hold the
keys, its label bold, and up from the top row leaves the grid.

**The bar is the host's.** The console draws the bar (its back chevron, your
title, the status) over your app and routes its taps; your app draws none.
The page lays out in the content rect the bar leaves, `content_rect()` (`x,
y, w, h`), wherever the bar sits; `bar_h()` is that rect's `y`. A UI tree
app is responsive with no code of its own: it draws on the whole surface (a
desk window's on the desk) in the shell's faces and theme, and its size
classes (`@desk`, `@wide`, ...) and `ui.app(size=, min=)` say how it fits.

**Drawn on change.** An app paints a frame only when something changed: its
input, a message, a timer, a state a handler wrote. One that moves on its
own says `"animates": true` beside its `type` and is drawn every frame; an
app that lists `audio` is too, since its sound is pulled in the frame.

**Five names with no permission**, because they are how an app draws: `ui`,
`screen()` (the canvas), `theme()` (the live colour tokens),
`content_rect()` and `bar_h()`. Lua holds `ui` and `content_rect()`, which
answers four values.

**The canvas: fixed by default, responsive by opt-in** (a game, and an app
on the immediate API). The manifest's `canvas` is the raster, which the
console centres and integer-scales. A cart that defines `_layout(w, h, fs)`
opts into the whole surface: it draws on the system canvas, is called
before `_init` and again whenever the size or font scale changes, and gets
the responsive bar; a cart that also declares a small `canvas` keeps the
fixed raster and is told so through `_layout`'s arguments. On the desk the
cart gets a window surface of its own, `_layout` and `content_rect()` being
the window's content (`Workstation.app_window_canvas`). A UI tree app is
responsive by its extension (`player_tree.wants`, `lua_ext.wants_layout`).
Each tier defines the callback its own way, and the console finds it before
the cart runs (`Player._wants_layout`):

| tier | `_layout` is | how the console finds it | how it hears a change |
|---|---|---|---|
| Python | a top-level `def _layout(w, h, fs)` | the source, at column 0 (`system_api.wants_layout`) | called by the Player |
| Lua | a global `function _layout(w, h, fs)` (or `_layout = function`) | the scripts, at column 0 (`lua_ext.wants_layout`); called only where the global is a function, as `_init` is | called by the Player (moycore's `layout`) |
| compiled (wasm) | an export `_layout` of three i32 and no result | the module's export section (`moycore_glue.wasm_exports`) | called by the Player (moycore's `layout`, the host's `hw_layout`) |
| WASI and native apps | an exported `void _layout(int32_t w, int32_t h, int32_t fs)` | the module's exports (WASI) or dynamic symbols (`elf_run.elf_defines`) | the frame message's layout words (`MOY_FRAME_LAYOUT_*`), which its frame loop reads (`moybyte/frame.h`) |

A Python, Lua or compiled app hears `_layout` before `_init`; a WASI or
native app, which has no `_init`, before the first frame its loop reads.

### Canvases

What no kind draws, an app draws in a `ui.canvas`. Its draw paints the rect
the engine laid out, inside the frame, and writes no state:

- **Python:** `draw(cv, x, y, w, h)`, `cv` the canvas; `ui.colors()`
  answers the theme's colours there and `ui.text_size(text, scale)` the
  size a text covers through the canvas's `print` at `scale`.
- **Lua:** `draw = function(x, y, w, h) ... end` in the props, drawing with
  the cart's own verbs (`rect`, `print`).
- **C:** `ut_canvas(key, draw, pointer)`, `draw(x, y, w, h)`.

A canvas in a rows' body, or a table's child that draws the table's rows
`row=` tall, is handed the row it stands in: `draw(cv, x, y, w, h, row)`
(Lua `draw(x, y, w, h, row)`, C `ut_canvas_row()`). Its other props:

| prop | does |
|---|---|
| `reads=` | the states its draw reads; the page's shift frames count them, and a read of another state is R01. A canvas that names none draws the frame after it whole |
| `pointer=` | an action or hook `takes="pointer"`, handed a press and its drag and release in the canvas's own coordinates (`ev.kind` `"down"`, `"drag"`, `"up"`; `ev.x`, `ev.y`; `ev.row`); while a popover or a dialog is open only a canvas inside it takes a press. C reads `ut_point()` |
| `keys=` | handed the frame's keys while the canvas holds focus, run as a handler, and answers true for keys it took, which the page then never sees; a canvas with no `keys=` is no stop. Python: `keys(i)` (`keys(i, row)` in a list's body), `i` the input; Lua: `keys = function() ... end` (`function(row)` in a list's body), reading `btnp()` and `keyp()`; C: `ut_canvas_keys(keys)` after `ut_canvas`, `keys()` answering non-zero (its row `ut_canvas_row()`), the module's export `_uitree_keys` |
| `hint=` | the band's confirm word while it holds focus |
| `h=`, `w=` | its size (a template); `ground=` the theme role painted under it |

A foot of `look="band"` lies edge to edge under a rule, its rows as tall as
their tallest canvas: `runtime/apps/music_app.py` draws what plays this way.

### Documents and the text editor

A state that holds `ui.doc(text, lang)` (`lang` one of `plain`, `python`,
`lua`, `json`, `markdown`) is a document the engine owns: its buffer, caret,
selection, undo and view. `ui.text_editor(name)` shows it and takes typed
keys into it with no app code. A handler changes it through its verbs
(`set_text`, `insert`, `go(line, col)`, `place`, `select`, `select_all`,
`find`, `undo`, `redo`, `copy`, `cut`, `paste`, `indent`, `outdent`,
`complete`) and reads `text`, `lines`, `line`, `col`, `sel`, `word`,
`edits`; a template shows `{note.line}`, `{note.can_undo}` and the rest of
its fields. A document is Python's (Lua has no `ui.doc`).

**The editor handle (#112).** `open_editor` hands the cart the console's own
text editor over one document, and the page shows it: `s.note.adopt(ed)`
makes the text editor type into the handle's document and draw it in its
mode, while the handle keeps the text, the caret, the selection, wrap,
undo, the clipboard, the Markdown rendering and the saving. There is no
Save button to build: it writes on an idle pause and again when the cart
exits.

| call | does |
|---|---|
| `open_editor(name)` | an editor over the document `name` in the kind your `files` permission granted. Never a path and never another kind |
| `open_editor()` | the document the console was asked to open (a file tapped in Files, a project's own file on the Editor's Config tab), or `None`. Call it once, in the `opened` hook |

The kind that arrives with `open_editor()` may be one you were never granted:
a person chose that file, not your cart. One of them is a whole project,
`project:<folder>.moy`, a `.moy` folder's own files, reached only through the
Config tab's Files so the cart loader re-reads the folder afterwards. Every
other verb is the handle's:

| call | does |
|---|---|
| `ed.undo()` / `ed.redo()` / `ed.can_undo()` / `ed.can_redo()` | one step, and whether there is one |
| `ed.select_all()` / `ed.copy()` / `ed.cut()` / `ed.paste()` | the console's clipboard with the `clipboard` permission, the document's own otherwise |
| `ed.select_mode(on)` / `ed.selecting()` | SELECT mode: a drag and the trackball extend the selection, the way to mark a range with no shift-arrow |
| `ed.has_selection()` / `ed.can_paste()` | for dimming those buttons |
| `ed.wraps()` | whether the mode soft-wraps (`md`, `text`) or pans sideways (`code`, `json`) |
| `ed.save()` / `ed.save(soft=True)` | write now; the soft one refuses a document its mode cannot parse and badges it |
| `ed.badge()` / `ed.dirty()` | why the last save was refused (`""`: fine); edits no save has taken |
| `ed.can_run()` / `ed.run()` | run a `.py`/`.lua` document on the console's script screen, saved first; your cart opens again on it after, `open_editor()` handing it back |
| `ed.text()` / `ed.set_text(s)` / `ed.caret()` / `ed.scroll(rows, cols)` | the whole text, the caret's `(row, col)`, a pan without moving the caret |
| `ed.name()` / `ed.mode()` / `ed.close()` | the document's name, its mode (`md`, `code`, `json`, `text`), save and let it go |
| `ed.follow()` | what the caret's line holds in a note: a `- [ ]` box it ticked, `("check", row)`; else the `[[link]]` at the caret or the line's first, `("link", name)`; `None` |

A note is Markdown, rendered by the handle: `#` headings, `- [ ]` checkboxes
ticked by a tap, `[[note]]` links and `![[a drawing]]`, one of Paint's
pictures inline by name. Prose wraps; code and JSON pan. In Lua the handle
is a table with the same verbs as methods (`ed:undo()`).
`system_carts/moybyte.notes.moy` is the example: a vault of notes beside the
open one on the desk, one at a time on a handheld, its text editor adopting
the handle.

### Errors

Each code, what it means and its fix (Python's; Lua's or C's where Python
has none), as `native/moy_uitree/contract.json` holds them
(`tests/test_app_guide.py` fails a row that differs).
`tests/test_uitree_mistakes.py` makes each mistake both layers raise once in
Python and once in Lua.

| code | the mistake | the fix |
|---|---|---|
| A01 | a site names no action (the message says when the text given is an action's label) | `ui.action("add", "Add one", add)`, then `ui.button("add")` |
| A02 | a site hands what the action's `takes=` does not take (an `arg=`, a row, a typed char, a timer's or a post's key) | `takes="arg"` on the action, or no `arg=` at the site |
| A03 | a handler's parameter count against its `takes=` | `def choose(row):` for `takes="row"` |
| A07 | a row action reached from rows of another model | a second action, or `row=` naming a `row_of` of this model |
| A08 | an action with an empty label | `ui.hook("scanned", scanned)` |
| A09 | a bad value in an action's declaration: `off`, `takes`, a `row` naming no `row_of`, a name or label not a text, a handler not a function | pass the function: `add`, not `add()` |
| A10 | `after` called outside a handler | call it from a handler or the `opened` hook |
| B01 | a build reads state, a derive, a document's field or a system value, or asks the engine anything | a template `"{count}"`, a condition `shown="busy"`, a switch or rows |
| B02 | a build writes state or issues a command (`push`, `pop`, `focus`, `after`, `post`, `damage`) | name an action the node fires: `on="add"` |
| B03 | a declaration inside a page's or a case's function, or a node outside one | declare at the module's top level; make nodes in a page function, under `with ui.page(TITLE):` |
| C01 | a condition that is a template, neither a text nor a bool, or joined with a single `&` or `\|` (and is `&&`, or is `\|\|`) | `shown="pick"`, not `shown="{pick}"`; `"a && b"`, not `"a & b"` |
| C02 | `&&` and `\|\|` mixed at one bracket level (inline: at all) | `ui.derive("ok", cond="a && (b \|\| c)")` and `shown="ok"` |
| C03 | brackets in an inline condition | a derive, as for C02 |
| D01 | the `app` declaration: an unknown or placement field (`x`, `place`, `tools`...), or a second one | drop `place=`: the shell places windows |
| D02 | `size=` or `min=` not `(w, h)` of desk units or fractions `"a/b"` with `0 < a ≤ b` | `size=("7/8", "9/10")` |
| D04 | an app with no `app` declaration | `ui.app("Counter", icon="calc")` |
| E00 | a kind, a prop or a form the C engine does not draw yet, by name (`uitree_c.EngineGap`), never drawn wrong | run the app on the reference (`uitree`), or build it from what the C engine draws |
| E01 | an enum with no `init=` | `ui.enum("a", "b", init="a")` |
| E02 | `init=` is not one of the enum's values | name one of them |
| E03 | an enum with fewer than two distinct non-empty values | a bool, or a second value |
| G01 | a derive cycle | compute one of them in a handler |
| H01 | a hook where an action belongs (a button, link, tool, item, card, a dialog's `buttons=`) | `ui.action(NAME, "Label", fn)` |
| H03 | a hook with a label, an icon, keys or `when=` | an action, if a person sees it |
| I02 | an action's `icon=` is a template | a site's `icon="{...}"`, or a name |
| K01 | an app names a shell role (`home`, `full`, `system`) | a role of the app's (§13.1) |
| K02 | two actions on one key live together in one unit, or an app action beside a unit action | one key, one action |
| K03 | a bad key: a chord other than `ctrl+LETTER`, an unknown role | `keys=["ctrl+f", "role:search"]` |
| L03 | two shown lenders on one site | lend to two sites |
| N01 | an unknown kind or prop, a bad prop value, a missing required prop (`progress` with no `max=`; a `derive` with neither or both of `cond=` and `text=`), a wrong count of arguments, a function given where its result belongs or the reverse | the near name the message offers |
| N02 | two siblings with one key | a key of its own: `ui.row("find_strip")` |
| N03 | a node or declaration where it may not stand (a `tools` in a `group`, a node after the page's `scroll` outside the `foot`, a label table declared on a unit) | move it: the message names where it may stand |
| N04 | a retired name (§7.9), with its replacement | the replacement |
| N06 | an anchor naming no node, a part the node lacks, or a tab its enum lacks | `anchor="msgs.cur"` |
| N07 | `split`: no weight, or a bare `0`; `panes`: not exactly one child grows | `sizes=[112, "1*"]` |
| N08 | `focus(KEY)` names no node, or more than one, in the handler's unit | a key the unit's nodes have |
| N09 | an app names a kind, prop, word or app field the contract marks the shell's (`slot`, `lent`, `tools lend=`, `card fill=`, `cards look="column"`, `ui.app slots=`) | an app's own: `cards look="icons"` |
| O01 | an action or a control that can be off (`when=` or `row=`) with no `off=` | `off="hide"` |
| O02 | `off=` with neither `when=` nor `row=` | drop `off=` |
| O04 | `when=` or `off=` on a node that is neither an action's site nor a two-way control | `when=` on the action |
| P01 | a push names no page | push the page function: `ui.push(about)`, where `about` opens `with ui.page("About"):` |
| P02 | a `push=` action declares `takes=` | drop `takes=` |
| P03 | a `push=` action has a handler | `ui.action("about_open", "About", None, push=about)` |
| P04 | a push's argument does not fit the page's `arg=`, or `arg=` names no state | `arg=` naming a `row_of` of the pushed row's model |
| P05 | `ui.pop()` on the app's first page (a page its host shows is closed by its host instead) | Back leaves the app; `ui.pop()` closes a page `ui.push()` opened |
| Q01 | Lua: a global name nothing declares | `local` it, or declare it |
| R01 | a canvas draw reads state its `reads=` does not list | `reads=["tape", "fresh"]` |
| S01 | no state with that name | declare it in `ui.state(...)` |
| S02 | a write of the wrong type, of None or nil to a non-optional, or of a key no row has; C: a bool not 0 or 1, an enum index out of range | write the declared type, or declare it `ui.opt(...)` |
| S03 | a write into what is written whole or by verbs: a handed row, a record's field, a document, an event, a model by index, an engine-written field | `s.pick.set(state="failed")`, or the whole record |
| S04 | a read of a field the row or record does not have | a declared field |
| S05 | a row of the wrong shape written to a model: a missing non-optional field, an unknown field, two rows with one key, no row with that key, `order` not a permutation | every declared field, keys unique |
| S06 | a state write outside a handler: in a draw, from a service | `ui.post("indexed", data)` from the service's callback |
| S07 | a model with no key field, a key field not text or int, or a field named `key` | `ui.model(key="id", id="", ...)` |
| S08 | Python: a typed name compared with None | `if s.pick:` |
| S09 | a write to a derive | write the names it reads |
| S11 | a `row_of` naming no model | `ui.row_of("nets")` after `nets=ui.model(...)` |
| S12 | a `doc` with an unknown `lang` | `lang="python"` |
| S13 | a declaration whose initial value has no type: `None` or `nil`, a list, a function | `ui.opt(0)` for a value that may be absent |
| T01 | template syntax (§3.1) | the message shows the column; `\:` for a colon in a branch |
| T02 | a name, field, system value or label table that does not exist, with the near one | the near name |
| T03 | a name of the wrong type at a site | the message names the type the site takes |
| T04 | exhaustiveness: a label table, a switch, rows by kind, a `tabs` or `seg` table | a case or label per value, or `_` |
| T05 | `{.field}` or `@current` outside a row | `{sel.field}` |
| T06 | Python: an enum used as a truth value | `if s.op != "none":` |
| U02 | a name declared twice in one key space (two states; a state and an action; a unit and a document; two pages) | rename one |
| U08 | two units answering one key that some size class shows together | give the key to one of them |
| W01 | a two-way control's `on=` names an action or hook that does not take what the control hands (`none` for a state, `row` for a `.field`) | `takes="none"`, reading the state |
| W02 | a `work` step's `budget=` is not an int of 1 to 16 ms | `budget=4` |
| X01 | an internal assertion: the layer missed a check at build | report it: the layer missed a check |

### One app per tier

**Python**: `tests/fixtures/apps/shopping.moy`, a list longer than the
screen and the row last picked kept in prefs (its manifest asks for
`prefs`), which `tests/test_app_examples.py` drives:

```python
s = ui.state(items=ui.model(key="name", name=""), cur=ui.row_of("items"))
ui.app("Shopping", icon="list")


def opened():
    s.items = [{"name": "Item %d" % n} for n in range(1, 41)]
    s.cur = prefs.get("cur") or "Item 1"    # saved across runs and reboots


def pick(row):
    prefs.set("cur", row.name)


ui.hook("opened", opened)
ui.action("pick", "Pick", pick, takes="row")


def build():
    with ui.page("Shopping"):
        with ui.rows("items", cur="cur"):
            ui.link("pick", label="{.name}")
```

**Lua**: a model filled at the open, rows with a cursor and a row action
(`tests/uitree_conformance/list/list.moy`):

```lua
ui.app("Shopping", { icon = "list" })
local s = ui.state { items = ui.model { key = "id", id = "", name = "" }, sel = ui.row_of("items"), msg = "" }

ui.hook("opened", function()
  s.items:set({ { id = "a", name = "Apples" }, { id = "b", name = "Bread" }, { id = "c", name = "Cheese" } })
end)
ui.action("pick", "Pick", function(row) s.msg = "Picked " .. row.name end, { takes = "row" })

ui.page("shopping", function()
  ui.group("Things", function()
    ui.rows("items", { cur = "sel" }, function()
      ui.link("pick", { label = "{.name}" })
    end)
    ui.label("{msg}")
  end)
end, { title = "Shopping" })
```

**C**, a compiled app built by `moy app build` (§10): the counter of §1
(`tests/uitree_conformance/counter/counter_wasm.moy`). `_init` declares the
state and the actions with their handlers and builds the page;
`uitree_open()` opens it, and `_draw` runs `ut_frame()`, which draws the
page and runs the handler of each action taken:

```c
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
```

### No immediate verbs

An app's interface is a UI tree page on every tier: the immediate verbs
(`ui.page`, `ui.list`, `ui.button` and the rest, called in `_draw()` every
frame) are gone from Python, Lua, compiled, WASI and native apps alike, and
`docs/history/ui_api_2026-10.md` keeps what they were. A Python or Lua app
declares the extension `moybyte.uitree` and is handed the tree as `ui`; a
compiled app imports the `uitree_*` rows.

A responsive app's page draws in the theme's faces, colours, row styles and
selection marks, as a built-in app's does, at the font scale of the canvas
it draws on: a Python app's frame by its Player (`ui_draw.CART_APP`, the
boundary keeping only its `print` and its own colours), a Lua or compiled
run's by the run's context over the word its snapshot carries
(`AppFace.ui_face`, `moy_ui_run.h`'s `MOYCORE_UI_FACE_*`). A fixed app's
page draws as a cart's. Back steps out of its views first there too (§4): a
focused field's open edit, then a popover the last frame drew.

Write an app on the UI tree: the immediate verbs go at the clean cut of
the OS work (#246).

### Stability: what the freeze pins

The UI tree API freezes with the rest of the console API (`API_FROZEN`, §2):
`tools/api_level.py` fingerprints its contract,
`native/moy_uitree/contract.json`, and from the freeze on a kind, prop,
word, verb, role, `takes=` value, retired name or error code that changes
without a bump of the API level is red (`tests/test_api_level.py`). The list
below is that contract's every name, generated from it by
`tools/gen_uitree_schema.py` (`tests/test_uitree_schema.py` fails a stale
one). A word prop is listed with its words; `tpl` is a template, `cond` a
condition, `name` a declared name, `key` a node's key, `fn` a function of
the app's. What a tier lacks of it is `tests/uitree_contract/known.json`'s.

<!-- the freeze list: generated by tools/gen_uitree_schema.py from the contract; never edit it -->

| kind | level | head | props |
|---|---|---|---|
| `page` | 1 | python tpl, lua name, c name | `title` tpl, `arg` name, `status` tpl, `shown` action or hook |
| `group` | 1 | tpl | `close` action or hook, `look` `"card"` `"rules"`, `gap` int |
| `panel` | 1 | key | none |
| `row` | 1 | key, optional | `close` action or hook, `pad` int, `gap` int, `mid` bool, `wrap` bool |
| `scroll` | 1 | key | `follow` bool, `snap` bool |
| `foot` | 1 | none | `look` `"end"` `"share"` `"band"` |
| `switch` | 1 | state | none |
| `case` | 1 | lit, made by its parent | none |
| `tools` | 2 | key | none |
| `label` | 1 | tpl | `tone` tpl, `icon` tpl, `face` `"ui"` `"title"` `"mono"` `"caption"` `"result"`, `size` `"fit"` `"text"`, `wrap` `"cut"` `"word"` `"char"`, `lines` int, `align` `"start"` `"center"` `"end"`, `scale` int, `w` int |
| `rule` | 1 | none | none |
| `info` | 1 | tpl | `value` tpl, `icon` tpl, `signal` int, `tag` tpl, `tone` tpl |
| `status` | 2 | tpl | none |
| `note` | 1 | none | `icon` tpl, `lines` list of tpl |
| `empty` | 1 | tpl | `icon` tpl, `lines` list of tpl |
| `bubble` | 1 | tpl | `side` tpl, `head` tpl, `status` tpl, `signal` int, `tone` tpl, `max` int, `lines` int, `on` action, `cut` action |
| `toast` | 2 | tpl | `icon` tpl, `sub` tpl, `burst` int, `look` `"flat"` `"badge"` `"secret"`, `key` key |
| `stepper` | 2 | tpl | `value` tpl, `prev` action, `next` action, `tone` `"ink"` `"dim"`, `focus` cond |
| `picture` | 2 | state | `side` int, `on` action, `look` `"tile"`, `icon` tpl, `tone` tpl |
| `progress` | 2 | state | `max` int, `label` tpl, `look` `"count"` |
| `text_view` | 2 | state | `wrap` `"cut"` `"word"`, `follow` bool, `gutter` bool, `syntax` `"plain"` `"sgr"` `"python"` `"lua"` `"json"` `"markdown"`, `face` `"ui"` `"title"` `"mono"` `"caption"` `"result"`, `look` `"well"` |
| `month` | 2 | none | `year` int, `month` int, `today` int, `prev` action, `next` action |
| `button` | 1 | action | `kind` `"normal"` `"primary"` `"danger"` `"tonal"` `"bar"`, `label` tpl, `icon` tpl, `arg` lit, `alone` bool, `span` int, `focus` cond, `marked` cond, `w` int, `tone` tpl, `look` `"hero"` |
| `link` | 1 | action | `label` tpl, `value` tpl, `icon` tpl, `signal` int, `tag` tpl, `tone` tpl, `swatch` tpl, `sub` tpl, `count` tpl, `mark` tpl, `focus` cond |
| `toggle` | 1 | state | `on` action or hook, `focus` cond, `when` cond, `off` `"hide"` `"grey"`, `label` tpl, `hint` tpl |
| `slider` | 1 | state | `on` action or hook, `focus` cond, `when` cond, `off` `"hide"` `"grey"`, `label` tpl, `lo` int, `hi` int, `look` `"bar"` `"steps"` `"blocks"`, `icon` tpl |
| `field` | 1 | state | `on` action or hook, `focus` cond, `when` cond, `off` `"hide"` `"grey"`, `label` tpl, `max` int, `secret` bool, `hint` tpl, `grow` bool, `commit` bool, `edit` `"open"` `"stop"`, `keys` `"text"` `"number"` `"name"`, `changed` hook |
| `seg` | 2 | state | `label` tpl, `labels` table, `on` action or hook, `focus` cond, `look` `"seg"` `"cycle"` `"swatches"` `"pictures"`, `text` tpl, `icons` tpl |
| `tabs` | 2 | state | `labels` table, `icons` table, `text` tpl, `on` action or hook, `focus` cond, `offered` conds, `hint` tpl |
| `cells` | 2 | state | `clear` int, `count` int, `first` int, `cols` int, `side` int, `gap` int, `edge` bool, `on` action or hook, `pick` action or hook, `focus` cond |
| `rows` | 1 | model | `cur` name, `current` name, `check` bool, `empty` tpl, `by` name, `filter` name, `changed` hook, `group` tpl, `dir` `"row"` `"col"` |
| `cards` | 2 | model | `cur` name, `current` name, `w` int, `h` int, `cols` int, `new` action, `changed` hook, `pad` int, `group` tpl, `flow` bool, `look` `"carousel"` `"shelf"` `"icons"`, `tone` tpl, `label` tpl |
| `card` | 2 | action | `label` tpl, `sub` tpl, `badge` tpl, `label_icon` tpl, `image` name, `icon` tpl, `tone` tpl |
| `table` | 2 | model | `cols` list, `cur` name, `on` action or hook, `changed` hook, `empty` tpl, `focus` cond, `hint` tpl, `row` int |
| `col` | 2 | tpl | none |
| `dialog` | 1 | tpl | `buttons` list of action, `kind` `"primary"` `"danger"`, `look` `"keys"`, `labels` list of tpl |
| `popover` | 1 | key | `anchor` tpl, `w` int, `close` action or hook, `wash` `"page"` `"view"` `"none"`, `at` tpl |
| `menu` | 2 | tpl, optional | none |
| `item` | 2 | action | `icon` tpl, `label` tpl, `kind` `"danger"` |
| `split` | 1 | none | `dir` `"row"` `"col"`, `sizes` list, `gap` int, `pad` int, `align` `"start"` `"center"` `"end"`, `rule` bool |
| `grid` | 1 | none | `cols` int, `rows` int, `gap` int, `pad` int, `w` int, `h` int |
| `panes` | 2 | key | `dir` `"row"` `"col"`, `size` name, `start` int or name, `min` list, `grow` bool, `gap` int, `focused` name, `grown` name |
| `pane` | 2 | key | `title` tpl, `icon` tpl, `tabs` name, `labels` table, `size` name, `start` int or name, `grow` bool, `min` list or conds, `head` bool, `offered` conds |
| `text_editor` | 2 | state | `find` name, `find_on` cond, `marks` name, `gutter` cond, `focus` cond |
| `canvas` | 1 | key | `draw` fn, `reads` list, `pointer` action or hook, `keys` fn, `mark` lit, `hint` tpl, `focus` cond, `h` int, `ground` name, `w` int |
| `hints` | 2 | model | `keys` tpl, `label` tpl, `tail` cond, `drop` cond, `on` action or hook |

- **Every node but the page:** `shown` cond. **A child of a row or a grid:** `span`, `grow`.
- **An action:** `hint` tpl, `when` cond, `off` `"hide"` `"grey"`, `takes` takes, `row` name, `chars` text, `keys` list, `icon` name, `push` name, `unit` name. **A hook:** `takes` takes, `unit` name.
- **`takes=`:** `none`, `row`, `arg`, `char`, `pointer`. **`off=`:** `hide`, `grey`.
- **Roles an app's keys name:** `confirm`, `back`, `more`, `left`, `right`, `up`, `down`, `search`, `goto`, `complete`, `undo`, `redo`, `play`, `tools`.
- **Verbs** (besides a kind's, its name): `app`, `state`, `enum`, `record`, `model`, `row_of`, `opt`, `labels`, `derive`, `action`, `hook`, `page`, `sys`, `push`, `pop`, `focus`, `after`, `cancel`, `post`, `doc`, `image`, `work`, `pictures`. **Queries:** `about`, `text_size`, `colors`, `fade`.
- **App fields (`ui.app`):** `icon`, `size`, `min`, `back`, `glass`. **System values (`@NAME`):** `desk` bool, `handheld` bool, `wide` bool, `tall` bool, `touch` bool, `input` enum, `focus` text, `current` bool.
- **The shell's own**, kept on the shell's pages: `tools lend=`, kind `lent`, `cards look="column"`, `card fill=`, kind `slot`, app field `slots`, refused in an app (N09); roles `home`, `full`, `system` (K01).
- **Error codes:** A01, A02, A03, A07, A08, A09, A10, B01, B02, B03, C01, C02, C03, D01, D02, D04, E00, E01, E02, E03, G01, H01, H03, I02, K01, K02, K03, L03, N01, N02, N03, N04, N06, N07, N08, N09, O01, O02, O04, P01, P02, P03, P04, P05, Q01, R01, S01, S02, S03, S04, S05, S06, S07, S08, S09, S11, S12, S13, T01, T02, T03, T04, T05, T06, U02, U08, W01, W02, X01.
- **Reserved codes**, never raised: A04, A05, A06, D03, D05, D06, F01, F02, F03, F04, F05, F06, F07, F08, I01, L01, L02, M01, M02, M03, M04, O03, S10, U01, U03, U04, U05, U06, U07, U10, V01, V02, Y01, Y02, Y03, Y04, Y05, Y06.
- **Retired names**, each refused with its replacement (N04): verbs `at`, `cell`, `fmt`, `has_symbols`, `head`, `key`, `peek`, `per`, `rebuild`, `ref`, `scope`; kinds `cell`, `text`; props `below@scroll`, `disabled`, `does@action`, `fixed@split`, `ink`, `key@action`, `keyname@item`, `lit`, `mkind@item`, `paint@cards`, `tools@app`; takes `change`; system values `fs`, `h`, `symbols`, `w`.

<!-- the freeze list ends -->

## 4. Input

**Keyboard first; never keyboard only.** The keyboard is the primary input on
every board, and every surface must also work with a gamepad alone and with
touch alone (#242, #239). The engine gives a UI tree page all three: arrows
(the T-Deck's WASD and trackball, a pad's d-pad) move focus between stops,
Enter, A or a tap fires the focused stop's action, a drag scrolls. The app
writes no focus code: the engine moves focus into view, keeps it across
frames and puts it back on the node that pushed a page when the page pops;
a handler moves it with `ui.focus(key)`. Nothing sets the keyboard's mode
by hand: the console's input policy (`runtime/shell/input_policy.py`)
derives it from what the surface holding the keys has focused, and a menu
over it is game mode. So every action is a stop (a button, a link, a list
row, a menu item), and a key shortcut only ever doubles one.

**A field is edited only after Enter (owner, 2026-11-24).** A focused
`ui.field` is a stop like any other: the arrows, WASD and the trackball move
past it, typing nothing, and its hint is Enter's Edit in the input's own
key. Enter, a tap, a click or a pad's A opens its edit, and while it is
open the field takes the keyboard as text: every key types at its caret,
WASD included, and the directions (the arrows, the trackball, a pad's
d-pad, never WASD) move the caret, left and right a character, up and down
to the line's start and end (a field is one line; `text_editor` is the many
lines, with keys of its own). Enter, or the trackball's press, ends the edit
and commits it (`on=` runs, a `commit=True` draft is written); Esc, B or
the T-Deck's Mic end it and give back the text it began from. Focus stays
on the field either way, and focus leaving it ends the edit too. A field
with `edit="open"` is for a page that exists for typing (a search box a
search key opens, the Terminal's line, a dialog that asks a name): focus
coming onto it opens its edit, and so does `ui.focus` naming it; Enter
commits with the edit going on (the Terminal's next line, the next find, a
name the dialog refused); Esc gives back what was typed and ends the edit,
and on one with nothing to give back it is its page's Back (the dialog,
the popover, the strip closes).

**Shortcuts are an action's `keys=`.** `ui.action("trash", "Move to Trash",
trash, takes="row", row="cur", keys=("t",), ...)` fires on T wherever the
keys do not type into a field, on the row the cursor holds, and the hints
band names it. A key is a letter, `"ctrl+LETTER"` or a role, `"role:NAME"`:
`confirm`, `back`, `more`, `left`, `right`, `up`, `down`, `search`, `goto`,
`complete`, `undo`, `redo`, `play`, `tools`, each the input's own keys for
it. `home`, `full` and `system` are the shell's (K01), and two actions on
one key is K02. A canvas that takes keys of its own does so in its `keys=`
(§3, Canvases).

**Back is the host's, and steps out of your views first.** Esc, B, the
T-Deck's K (its B), the bar's back chevron and a desk window's are the
console's way back; a page never reads them. Back steps out of the app's own
views before it leaves the app, in this order:

1. a focused field's open edit ends and gives back the text it began from
   (a `commit=True` field's draft is dropped, the state keeping its text);
2. else a shown dialog takes its first button, and a shown popover its
   `close=`;
3. else, on a placed page (§3, Layout), a shown row or group with `close=`
   runs it (a find strip's close);
4. else a page `ui.push` opened pops, and focus returns to the node that
   pushed it;
5. else the action with `keys=("role:back",)`, or the one `ui.app(back=)`
   names, runs;
6. else Back leaves the app.

Esc is the same key everywhere, the host's included: a board's keyboard
sends it as `stop` (the console's back) and, on a text surface, as the byte
27, which over a view of the app's own (a field's edit, a dialog) is that
same back and anywhere else the surface's own byte.

A second page is a page function, which a handler opens with
`ui.push(details)` (Lua `ui.push("details")`); the bar shows the back
chevron while it is open, and its title is the bar's (a desk window "Moy
Mesh · Radio"). From `tests/uitree_conformance/pages/`:

```python
def details():
    with ui.page("Details"):
        with ui.group("Now"):
            ui.info("Count", "{count}")
```

A shell app built into the console answers the same back through its
AppHost, then its `back()` and `has_page()` (`InputPolicy.back`, one cascade
for Esc, B and both chevrons); a running app cart's are the Player's, over
its engine. The console's own key (the T-Deck's Mic) opens the system menu
and is never yours.

**Tabs switch themselves.** `ui.tabs("view", "VIEWS")` over an enum takes
the `tabs` keys (Q and E on a keyboard) wherever the keys do not type into
a field's edit, left and right while it holds focus, and a tap; a `ui.switch` on
the same name is its body. The app reads no key for it.

**Hints name actions, not keys.** The band under the page names the focused
stop's action and the page's shortcuts, and the engine shows each input's
own keys for them (`native/moy_ui/moy_ui_parts.c`, `ACT_KEYS`); an action's
`hint=` gives its words, `""` keeps it out. The T-Deck has Enter, K, WASD
and the trackball, Q E, Mic, F V, R, Del, M and Sym G, and no arrows, Tab,
Esc, Ctrl or brackets: a hint or a shortcut naming those does not exist
there.

**A finger's rows come by themselves.** On a board whose tap floor stands
(the Guition S3's 3.5-inch glass), a list row and an info, link, toggle,
slider, seg or tabs row are 36 px tall and a bubble takes larger pads and
faces; the app's code is the same on every board (`docs/history/ui_api_2026-10.md`,
the tap floor).

**Paste is the console's.** The console's Paste (the desk's Ctrl+V) puts its
clipboard into the focused field's open edit, at its caret, as many whole characters as its `max`
leaves room for: the app reads no clipboard and needs no `clipboard`
permission for it, on every tier.

**Reading input yourself.** A game, and a canvas's draw, read the cart API's
`btn`, `btnp`, `key`, `keyp` and `touch` (`docs/moy_cart_api.md`, Input),
`textmode(True)` for typing. A Python process reads raw input records,
timestamped, with `moybyte.on("keys" | "touch" | "pad", fn)` and
`moybyte.events(into)`.

## 5. Storage, files and other apps

**Prefs** (`prefs`): `prefs.get(key)`, `prefs.set(key, value)`,
`prefs.clear(key)`, any value JSON carries, each a row of the console's
settings namespaced under your app's `id`, saved as it is written; `None`
(Lua `nil`) for a key never set. Your app and its service share them. Games
hold the same `prefs` (owner, 2026-11-18, #261) and ask for no permission:
a game's run's grant carries the prefs role alone, under the game's `id`, so a game
that becomes an app keeps its rows; a compiled game imports them from
`"moybyte.prefs"` (`docs/moy_cart_api.md`, "A compiled cart's Moybyte verbs").

**A cart's own files** need no permission either: any cart, app or game,
reads its own folder and writes the paths its manifest declares `writable`
(`read`, `write`, `erase`, `list`; moy-spec SPEC.md §9.1,
`docs/moy_cart_api.md`, Files). They are the cart's private files, never the
user's folders below.

**Files** (`files` / `files:<folder>`): one of the user's shared folders,
the ones the Files app shows: `files:documents` (the default),
`files:pictures`, `files:music`, `files:recordings`; asking for two is a
manifest error, and one the console has none of refuses the launch. The
verbs are `files.list`, `load_text`/`save_text`, `load`/`save`, `rename`,
`delete` (to the trash; `(None, None)`, as `load`, where the name names
nothing), `duplicate`, `new_name(title)` (what a typed name
may be stored as) and `badge(name)` (the row's short label, `MD`, `TXT`,
`JSON`, `PY`, `LUA`). Storage answers `(value, err)` and never raises (Lua:
two results), `err` being `None` or why. In Lua the standard `io` and `os`
libraries work in that one folder: `"notes.txt"` is a document there, a path
that climbs, starts at `/` or names a folder is refused with
`Permission denied`, a file is saved whole at its `flush` or `close`, and
`os.remove` sends it to the trash. A game's own state is `pmem`
(`docs/moy_cart_api.md`). `docs/os_2026-11/between_apps.md` §2 is the files
model.

**Python is trusted, not sandboxed.** A Python app runs in the shell's one VM
with the real builtins, so `open()`, `os` and `socket` reach the whole tree
with or without a grant; the manifest is what the install prompt tells the
user (`docs/os_2026-11/processes.md` §2). What it imports is the app API,
`moybyte` and `ui`, and the language's own library
(`runtime/carts/app_imports.py`): the installer refuses a cart that imports
any other of the console's modules, and names it. Lua and wasm have no names
past their grants.

**Opening with another app.** Your manifest says what your app opens
(`"handles": ["text/markdown", "image/*"]`), and a file is named by its path
in the shared folders, as Files shows it:

```python
import moybyte

moybyte.open_with("Documents/todo.md")            # in the app that opens Markdown
moybyte.open_with("https://moybyte.org", True)    # always ask which app
moybyte.share("a line of text", "text/plain")

def moy_open(h):            # an item routed to this app
    text = h.read()         # h.name, h.mime, h.url, h.mode ("r" or "rw")
    h.write(text + "!")     # a file opened with open_with is "rw"
```

Where several apps open the type, the console asks once with its "open with"
menu and keeps the answer; `True` as the second argument asks again. The
handle reaches one item and ends with your run. `moybyte.pick("image/*")`
asks the user for one of their files of that type in the console's picker,
with no `files` permission; the one picked reaches `moy_open(h)` the same way
(`moybyte.pick(mime, "rw")` to write it back), `None` reaching it on a
cancel, and it answers `False` where no file has the type. A Lua service
holds `open_with` and `share`. `docs/os_2026-11/between_apps.md` §1 has the
routing.

**From the background** (a service, or an app the player left) these verbs
and `open_app` ask first: the player gets a notification ("Wants to open
todo.md in Notes") that does it when opened, and the call answers `True` as
though it went. The `front` permission lets them straight through
(`runtime/system/front.py`). A request that goes through is carried out at
the start of the console's next frame, after your call returns, so one made
from your load or `_init` is safe; the call answers `True` for it, and your
run ends there when the app opened takes its place.

**The clipboard** is the `clipboard` permission: the console's own, at most
4 KiB of text, the global `clipboard` (`put_text(text)`, False for a text
too long; `text()`; `kind()`, "text" or none; `seq()`, which moves at every
put), and what the editor handle's `cut`/`copy`/`paste` use (a compiled app
imports its rows, §10). In a browser the page's clipboard meets it: a paste
there (Ctrl/Cmd+V) is put on the console's clipboard and pressed as its Paste
(the Terminal types it whole), and a copy here goes on the browser's
clipboard where the browser lets a page write it
(`firmware/web_runner/web_boot.py`'s `_paste` and `_clip_out`).

## 6. Permissions and consent

What each permission hands an app, and the tiers that may hold it: the
table is `native/os_calls.json`'s `"permissions"`, written here and into
`runtime/shell/app_perms.py`'s `TABLE` (which the install prompt, the launch
check and Settings read) by `tools/gen_os_table.py`. A permission's tiers are
the tiers that serve what it hands an app; a cart with its own service (§7) is
asked for what its own tier or its service's serves (`app_perms.tiers_of`):
one consent covers both. Of the markers, `editor` names the app the console
opens a text file from Files with (Notes).

<!-- GENERATED by tools/gen_os_table.py from native/os_calls.json: the permissions. Do not edit. -->
| permission | what the app holds | tiers |
|---|---|---|
| `graphics`, `input`, `audio` | nothing extra: the floor every cart has | python, lua, wasm, elf |
| `files`, `files:<folder>` | `files` (§5), `open_editor` (§3), Lua's `io` and `os` in the folder | python, lua, wasm, elf |
| `prefs` | `prefs` (§5) | python, lua, wasm, elf |
| `appearance` | `set_theme(name)`, `themes()` | python, lua, wasm |
| `launch` | `open_app(id)`: another app, by its registered id | python, lua, wasm, elf |
| `clipboard` | `clipboard`, the console's clipboard, which the editor handle uses too (§5) | python, lua, wasm, elf |
| `network` | `wifi` | python, elf |
| `multiplayer` | `net`, `on_net` (`docs/moy_cart_api.md`, Multiplayer) | python, lua, wasm, elf |
| `pins` | `pin_write`, `pin_read` (`docs/moy_cart_api.md`, Pins); by handle on the compiled tiers (§10, Devices by handle) | python, lua, wasm, elf |
| `console` | `print` writes to the text console's scrollback instead of drawing (a script's, the terminal's) | python, lua |
| `notifications` | `moybyte.notify` posts (below) | python, lua, wasm, elf |
| `front` | nothing by name: from the background, `open_app`, `open_with`, `share` and `pick` go straight through (§5) | python, lua, wasm, elf |
| `autostart` | a service starts with the console (§7) | python, lua, wasm, elf |
| `lease:<resource>` | `moybyte.lease(name)`: a board resource (a UART, a pin) as MicroPython's own object (`docs/os_2026-11/hardware.md` §1); by handle on the compiled tiers (§10) | python, lua, wasm, elf |
| `full_access` | what a native (ELF) cart must ask for, and what admits an unsigned compiled module (§10) | wasm, elf |
| `http`, `mic`, `lora`, `ble`, `usb`, `midi`, `camera`, `media`, `media:url` | `moybyte.http` and the other device APIs (Python, `runtime/system/devices.py`); by handle on the compiled tiers too, `lora` with LoRaWAN (§10, Devices by handle) | python, lua, wasm, elf |
| `alarms` | `moybyte.at` (§9) | python, lua, wasm, elf |
| `editor`, `calc`, `terminal`, `getcarts`, `storybook`, `myart`, `artwork`, `music` | nothing: a marker, a shipped app's claim on its own cart (§13) | python |
<!-- END GENERATED -->

**Not asked for, not there.** An ungranted capability has no name: touching
it is a `NameError` (Lua: `nil`), like a typo. A permission the user turned
off in Settings (About → App permissions) has its names bound to `None`
(`nil`), so `if prefs is None:` is how an app copes. A permission naming what
this console lacks (`pins` on a board without them) leaves no name. A
permission none of the cart's tiers serves (its own, and its service's) is the
cart's mistake: the install and the launch refuse it, naming it, and `moy app
check` reports it as an error. `network` is the one an author meets: it hands
Python's `wifi` and a native module's sockets, and the way every tier reaches
the internet is `http` (`moybyte.http`, by handle on the compiled tiers). Only a
`required` one refuses the launch, naming what is missing, at install and
again at launch; an app requiring a device the console lacks shows no run
tile (the home's Games, Mine and Apps, the desk), while Files and Make still
list it to edit. Never grantable, whatever a manifest says: the shell's own
roles (`carts`, `install`, `wallpaper`, `artwork`, `damage`, `surface`,
`notify`, `shell`); `tests/test_user_apps.py` pins it.

**Consent.** A cart installed from Get Carts (or `pkg install`) shows what it
asks for first and installs only on the user's yes, all or nothing; an update
that adds a permission asks again. Any other cart brought in as files (a
card, SFTP, USB, a browser's push) shows those lines when it is first opened,
and runs only on a yes. Your own carts, written on the console, and the
built-ins are never asked about. The record is kept per app id (`runtime/shell/app_perms.py`,
`Consent`); `docs/os_2026-11/processes.md`
§2 has the rules. What a permission, a tier and a signature protect
against, and what they do not (a Python app is trusted, a C module on an S3
is the whole console), is `docs/os_2026-11/threat_model.md`. A Python cart
is trusted only from a reviewed index (moybyte-org/carts, signed under its
review key, or the console's own release); from any other store its prompt
warns that nobody checked it and it can do anything on the console, and
where the console has a password (`passwd`) the yes takes it. An index can
revoke a version: it is refused at install, and an installed copy will not
launch until it is updated or removed (`runtime/carts/cart_index.py`).

**Notifications** (`notifications`): `moybyte.notify(summary, body="",
icon=None, actions=(), urgency=1, replaces_id=0)` answers the notification's
id, or `None` without the permission.

```python
import moybyte

nid = moybyte.notify("Ana: are you coming?", "We start at eight.", "heart",
                     ("default", "Open", "reply", "Reply"), 1)

def moy_action(nid, key):       # the player opened it: "default", or "reply"
    ...
```

The summary is a single line of at most 47 characters and the body at most
200; the icon names one of the console's icons (`None` draws a bubble); the
actions alternate keys and labels, `"default"` meaning a tap on the
notification itself; urgency 0 lists it quietly, 1 shows a banner for 5 s
and 2 for 10 s; `replaces_id` updates a notification you posted before. The
banner draws over whatever is on screen; opening it (the banner, or the task
manager's Notifications tab) brings your app to the front and calls
`moy_action(id, key)`. `docs/os_2026-11/processes.md` §7 has the rules.

**A status item.** `moybyte.status(icon, section, order=0)` puts an item in
the bar for your process, its section's rows listed in the item's menu on the
desk and in the control centre on a handheld; your process's end takes it out
(`runtime/system/status_items.py`). A section is a page or rows. A page is a
small `uitree` page you build with your usual API, a canvas included: the
section's `page` is its build function and `height(desk)` the pixels it
asks at font scale 1 (at most `SECTION_H_MAX`); the shell gives it a slot,
drawn by its own engine and clipped to it, its taps and keys run as your
process, and its module's `changed` hook runs on each `item.changed()`.
Rows are described in the text a Lua or a compiled program gives (§10, a
status item) from `panel()`, read again on each `item.changed()`, and a
row's press is heard as `press(id, value)`, run as your process; a Lua or a
compiled program's section is always rows. An item with no section, or no
rows and no page, has no menu: a tap on it opens your app.

## 7. Services: background work and the one wait

A **service** (`"type": "service"`) has no window: it starts, sleeps on its
wake sources and runs a callback when one fires, whatever is on screen. On
every tier a background program waits in the same single kernel wait, on
its own event queue; Python's wakes, Lua's callbacks and a compiled loop's
poll are three faces of it
(`docs/os_2026-11/processes.md` §1, the service model):

| tier | its shape | its example |
|---|---|---|
| Python | the script runs, then `moy_start()`; wakes are `moybyte.every(ms, fn)`, `after(ms, fn)`, `on(name, fn)`, `at(t, fn)`, or asyncio (`asyncio.run(main())`, `runtime/system/aio.py`) on the shell's one loop; `moy_stop()` on a stop | `system_carts/moybyte.achievements.moy` |
| Lua | `moy_start()` and `moy_stop()`; the `moybyte` table a Lua app holds (§10), and `exit` | `tests/fixtures/apps/echo_lua.moy` |
| wasm (WASI) | `_start` loops in `poll_oneoff` on the event descriptor, `MOY_EVQ_FD` (31), its nearest deadline the timeout; `moybyte.os` imports `send`, `on`, `notify`, `award`, `progress` and `log` | `tests/fixtures/wasm/wasi_svc.moy` |
| C (ELF) | `main` loops in `poll` on `MOY_EVQ_FD`; `moy_send`, `moy_on` | `tests/fixtures/elf/elf_svc.moy` |

A compiled service reads one record per event (its sender's pid and app id,
the name, the arguments as JSON, `moy_evq_ev_t` in `sdk/include/moybyte/os.h`)
and returns when the descriptor reads end of file, its stop. A timer is a
deadline, never a per-frame tick: **no background process gets a frame**.
A Python service with no wakes left has exited (0).

**An app's own service: one cart, one id.** An app (`"type": "app"`) names
its service's program beside its `main`, and the service is the cart's own:
its id, its permissions and its one install prompt, its storage, its
`receives`, its row under the cart's title in the task manager and under its
id in `service` and `ps`; a notification it posts, tapped, opens the app as
well as reaching its `moy_action`:

```json
"moybyte": {"type": "app", "permissions": ["prefs", "autostart"],
            "entries": {"service": "service.lua"}}
```

`entries` is the smallest shape every tier fits: one key, `service`, and a
file in the cart's folder whose extension is its tier, whatever the app's
own: `.py` Python, `.lua` Lua, `.wasm` a WASI program (its `_start` is the
loop, and a board runs its compiled form, `<stem>.<chip>.f<format>.aot`, as
it does a cart's `main.wasm`), `.elf` a native module, which a board runs
as `<stem>.<chip>.elf`, the chips those the folder carries. The app's own
entry is `main`. A Lua app's Lua entry runs after the app's SHARED scripts:
the ones its manifest's `sources` (`docs/moy_cart_api.md`) lists before
`main`, in that order, each its own chunk, as the window runs them. So the
two halves keep one copy of what they share (Moy Mesh's `mesh.lua`: its id,
its regions and presets, the radio's setup and its channel links); what `sources` lists after `main` is the window's alone,
and the entry never runs as a shared script, even where `sources` names it.
A Lua `"type": "service"` cart runs its `sources` in order, as a window
does. An entry that does not read (another key, an absolute or
`..` path, another extension) is absent. A `"type": "service"` cart is still
a service of its own, with its own id. `tools/wasm_cart.py` builds a `.wasm`
entry from `src/<stem>.wat`, `.c` or `.rs`, and `tools/elf_cart.py` an `.elf`
one from `src/<stem>/*.c`, each with its per-chip modules signed as a main's
are; a native entry asks for `full_access`, as a native cart does.

From any process of the app, on every tier (the call table, §10):

| call | answers |
|---|---|
| `moybyte.service_start()` | the service's pid where it runs, else 0 with its start asked |
| `moybyte.service_stop()` | 1 with its stop asked where it runs or its start was asked, else 0 |
| `moybyte.service_running()` | its pid while it runs, else 0 |

A start or a stop is ASKED: the console runs it at its next tick, as the
shell, never inside the caller's call, and the last one asked wins. A
compiled program's stop of a Lua, ELF or WASI service is the kernel's: the
service is hung up (its TERM) on the caller's task, with or without the VM,
and the console ends it as a stop asked (`docs/os_2026-11/processes.md`
§5); a compiled program's start during an S3's VM stop waits for the VM. Each
answers `ABSENT` (`moybyte.ABSENT`, -8) where the caller's app declares no
service: the calls name no app, so no app reaches another's, and a
`"type": "service"` cart's own process is answered ABSENT too. They need no
permission beyond the cart's. A compiled app imports them as
`moybyte_service_start` (`moybyte.app`), a WASI program as
`moybyte.os.service_start`, a C program calls `moy_service_start`
(`sdk/include/moybyte/os.h`), which answers -1 with `errno` `ENOENT` where
the others answer ABSENT, a WASI program and a native module alike.

**Its storage is its app's.** A service holds the roles its permissions
grant, as a foreground run of the same app does: the same files folder, the
same prefs namespace. Each write lands whole or not at all; ordering two
writers is the app's own business.

**Budgets and strikes.** Every tier's callbacks are charged to one
supervisor (`native/moy_kernel/moy_super.h`): a callback over its slice
(`MOY_BG_CALLBACK_US`, 20 ms) is an overrun, the first a warning and every
later one a strike, and `MOY_BG_STRIKES` (3) strikes suspend the process
until it is resumed. Python aborts a callback still running after
`MOY_BG_ABORT_US` (300 ms) and counts a strike; Lua yields a runaway
callback with a count hook; a watchdog strikes and kills a compiled wake
that stops polling. `runtime/system/sched_python.py`'s header is the ladder.

**Start, stop, restart.** A service runs from its start until it is stopped,
exits, crashes, or strikes out. It starts by `autostart` (the permission: at
the console's first drawn frame, which the user can turn off), by its app's
`service_start()`, from the terminal (`service start NAME`, `stop`, `restart`, `status`) or the task
manager. A stop runs `moy_stop()` (a compiled service: end of file) and
kills what is still running after `MOY_SERVICE_STOP_MS` (2 s). The restart
policy is the user's, never the manifest's: `never` (the default),
`on-crash`, `always`, set with `service policy NAME POLICY`, with a back-off
that doubles from 1 s and a cap of 3 ends in a row
(`docs/os_2026-11/processes.md` §5).

**Which boards.** Python services run on every console board, in the
shell's VM; on the S3s they are stopped before a VM stop (a game that needs
the whole board) and started again after it. Lua and WASI services run on
every console board and the host, ELF services on both chips, on core 1 on
the S3s, and they run on through a VM stop: their timers go off and their
messages to other services arrive, while a call that needs the console
(a notification, a role the shell serves) waits until the game ends. The browser's VM has no asyncio. The per-board table is
`docs/os_2026-11.md` §5.

## 8. Messages

Every process has an event queue (`native/moy_kernel/moy_evq.h`), and a
message is a name and arguments, any values JSON carries. The same two names
on every tier:

```python
import moybyte

def pong(sender, score):        # sender: the app id the OS stamped
    print(sender, "says", score)

moybyte.on("pong", pong)                    # listen
moybyte.send("local.pinger", "ping", 42)    # every process of that app that listens
```

`send` answers how many processes took it, the sender apart. Who hears whom
is the kernel's rule (`moy_evq.h`, THE RULE; the table is
`docs/os_2026-11/processes.md` §1): a process of the same app always; another
app only on a name the receiver's manifest lists under `receives`
(`"receives": ["ping"]`), so an app chooses what the world may tell it; the
console, as `"system"`, always. The sender is stamped by the kernel, never
taken from the sender's word. The rule holds both ways: an app that waits
for another app's answer lists the answer's name under its own `receives`
too (`"receives": ["pong"]` beside a `send` of `"ping"`). The tier does not matter: a Lua service
hears a Python app's `send`, and the app hears the service's answer. A process that
does not listen on a name does not take it.

A queue pushes back (`moy_evq.h`, BACKPRESSURE): it holds `MOY_EVQ_SENDER`
(16) unread messages of one sender at most, `MOY_EVQ_DEPTH` (64) in all, and
past that `send` answers FULL (`moybyte.FULL`, `-2`) and queues nothing, so
a flood stops at its sender, which sends again later; the system is never
refused. The receiver takes its senders' messages in turn, each sender's in
its order, `MOY_EVQ_BATCH` (4) a step: a frame's start for a Python process,
a run for a Lua service, a `poll` for a WASI or C service. A second app's
message is served behind a flood's oldest, never behind the whole flood.

A compiled program reads its messages: a WASI or C service from its event
descriptor (§7), a compiled app with `moybyte_recv(buf, cap)`, which it calls
in its `_update` as it reads its buttons. Each read takes the next message
(its senders in turn) as one record: `moy_evq_ev_t` (`sdk/include/moybyte/os.h`: the sender's pid,
the arguments' length, its app id, the name), then the arguments as a JSON
array, then a NUL. A compiled app's read answers the record's length, the NUL
counted, 0 when nothing waits, and FULL (`-2`) where the buffer is short,
the message kept for the next read. `tests/fixtures/wasm/app_talk.moy` is a
C app that pings a service and reads the answer.

## 9. Alarms, connectivity and achievements

**Alarms** (`alarms`): `moybyte.at(t, fn)` calls `fn()` once, no
earlier than `t` in Unix seconds on the wall clock (`moybyte.clock()`, on
every tier: a board's `time.time()` and Lua's `os.time()` count from 2000;
`moybyte.clock_synced()` says whether NTP has set it), answers
an id `moybyte.cancel` takes, refuses without the permission (Python's
`OSError`, a Lua error), and lights the screen if the console had gone dark,
so a background app can wake its player
(`docs/os_2026-11/between_apps.md` §3). A Lua program's alarm is the
kernel's, heard as the system's message `"moybyte.at"` and handed to its
function (`native/moycore/moycore_moybyte.h`), and so is a compiled program's
on every tier (a wasm app's `moybyte_at(t)`, a WASI program's and a C
program's `moy_at`): the call answers the alarm's id on the program's own
task, with or without the VM (`native/moy_kernel/moy_evq.h`, `moy_evq_at`,
under the `alarms` the process's event queue was opened with), and the
program reads `"moybyte.at"` from `"system"` with that id as its one
argument. An alarm keeps its wall time when the clock steps (an NTP answer,
the first one too), on every tier. A compiled program reads the clock as
`moybyte_clock(local)` (a wasm app) and `moy_clock(local)` (a WASI or C
program), a 32-bit number like `moybyte_at`'s `t`: the Unix seconds on the
program's own task with or without the VM (`native/moy_app/moy_app.c`,
`clock_row`), and with `local` 1 the console's local time from the zone the
Python half holds, ABSENT (a WASI or C program's `ENOENT`) while NTP has not
answered.

**Timers** need no permission. Every program's timers and alarms are the
kernel's (`native/moy_kernel/moy_evq.h`, TIMERS), one table and one id
space for every tier. A Python and a Lua program pass a function
(`moybyte.every(ms, fn)`, `moybyte.after(ms, fn)`, §7); a compiled program
asks for the timer (`moybyte_every(ms)` and `moybyte_after(ms)` in a wasm
app, `moy_every` and `moy_after` in a WASI or C program), which answers its
id, and hears each time it goes off as the system's message
`"moybyte.timer"` carrying that id. `cancel` (`moybyte_cancel(id)`,
`moy_cancel(id)`) ends a timer or an alarm of the program's own, answering 1,
or 0 where it has none of that id. A compiled program's and a Lua service's
go off, and are set and cancelled, with no console, so a service's run on
through an S3's VM stop. A program outside the VM listens on those two
names for itself while it holds one, two of the eight names a process may
listen on (`moy_evq.h`, `MOY_EVQ_LISTEN`); a tick its queue cannot take is
dropped. A program holds 16 timers and alarms at once
(`moybyte.TIMERS_MAX`): one more answers FULL (`-2` to a wasm app, `ERANGE`
to a WASI or C program, as a short buffer reads; an OSError in Python, an
error in Lua). Each is its process's, and the process's end cancels what it
left.

```python
import moybyte, time

def ring():
    moybyte.notify("Tea is ready", urgency=2)

moybyte.at(time.time() + 4 * 60, ring)
```

**Connectivity.** The radios are messages from `"system"`:
`moybyte.on("net", fn)` hears WiFi come and go as `fn("system", up, why)`,
and `"ble"` the BLE host, `why` what took it down (0 when it was put down
or came up). A Python service and a Lua service hear them alike
(`docs/os_2026-11/between_apps.md` §4), and so does a compiled app that
listens with `moybyte_on("net", 1)`: its record's arguments are `[up, why]`.
The multiplayer `net` and `on_net` are a game's (moy-spec's netplay), not
these events.

**Achievements.** A game declares its badges and tells the console when it
earns one; the console keeps them, shows the unlock banner ("Harpoon Pop:
badge found!") and lists them in Settings → About → Achievements under the
game's name, where they stay after the game is deleted.

```json
"moybyte": {"achievements": [
  {"id": "first_clear", "title": "Bubble Buster", "icon": "star", "hint": "Clear level 1"},
  {"id": "high_tide", "title": "High Tide", "icon": "run", "hint": "Reach level 5", "goal": 5},
  {"id": "untouchable", "title": "Untouchable", "icon": "heart",
   "hint": "Clear a level without losing a life", "secret": true}]}
```

`id`, `title`, `icon` (a name of the console's icon set) and `hint` are
text, the id at most 32 bytes and unique; `goal` is a whole number of 1 or
more; `secret` keeps the badge "Secret" until it is found. The list is read
strictly: one entry that breaks a rule, or a key it does not know, and the
game declares no badges.

```python
import moybyte

moybyte.award("first_clear")          # found
moybyte.progress("high_tide", level)  # the goal's current value: found once it reaches 5
```

`progress` reports the game's own count, a whole number, which the console
stores as told (the last value, not the best); a fraction counts down to the
whole below it (`2.9` is `2`), as the compiled tiers' `int32` value cannot
carry one. A best or a total is the game's to keep, in `pmem`. Both may be
called freely, every frame or on every kill: the kernel coalesces them per
process and badge, every tier's alike (`native/moy_kernel/moy_notes.h`,
BADGES), so a compiled game's answer on its own task with no VM; a send the
achievements process is not there to take (through a VM stop) waits and
goes in its turn. An `award` of a badge it found already sends
nothing; `progress` keeps each badge's newest value and sends it once a
quarter second (`MOY_NOTES_EVERY_MS`) at most, at once when it reaches the goal the
manifest declares, and at the game's end; an unchanged value sends nothing.
Each answers what its badge's last send answered. Each is a message to the achievements process
(`moybyte.send("moybyte.achievements", "award", id)`), which takes those two
names from every app. Because the kernel stamps the sender, a game unlocks
only its own manifest's badges; the process refuses any other id and logs
the refusal. A Lua
game, app and service hold `moybyte.award` and `moybyte.progress` too, a
compiled app imports `moybyte_award` and `moybyte_progress`, and so does a
compiled game that declares the `moybyte.app` extension (its run then holds
a grant of its own, as an app's does, which its device handles answer under
too: `docs/moy_cart_api.md`, "A compiled cart's Moybyte verbs"), a WASI program
`moybyte.os`'s `award` and `progress`, and a C program calls `moy_award`
and `moy_progress`.
`system_carts/moybyte.harpoon_pop.moy` uses all three kinds;
`docs/os_2026-11/processes.md` §8 is the process.

## 10. Tiers: what each can call

| tier | an app | a service | a command | sealed by |
|---|---|---|---|---|
| Python | yes | yes | yes | nothing: trusted (§5) |
| Lua | yes | yes | — | its state's names |
| wasm | yes (`moybyte.app`) | yes, WASI | yes, WASI | its imports |
| C (ELF) | — | yes | yes | U-mode and PMP on the P4s; nothing on the S3s |

The calls a program reaches on more than one tier, each by its name there
(`docs/os_2026-11/tiers.md` §1; the UI tree's rows and the immediate `ui`
rows are §3's, every app's with no permission):

<!-- GENERATED by tools/gen_os_table.py from native/os_calls.json. Do not edit. -->
| call | permission | Python | Lua | wasm (`moybyte.app`; a WASI program's `moybyte.os`) | C (ELF) |
|---|---|---|---|---|---|
| `moy_term_size` | none |  |  |  | `moy_term_size` |
| `theme.token` | none | `ctx.theme.token` | `theme.token` | `theme_token` |  |
| `theme.gen` | none | `ctx.theme.gen` | `theme.gen` | `theme_gen` |  |
| `theme.light` | none | `ctx.theme.light` | `theme.light` | `theme_light` |  |
| `theme.name` | none | `ctx.theme.name` | `theme.name` | `theme_name` |  |
| `theme.variant` | none | `ctx.theme.variant` | `theme.variant` | `theme_variant` |  |
| `theme.set` | `appearance` | `ctx.theme.set`, `set_theme` | `set_theme` | `theme_set` |  |
| `theme.set_variant` | `appearance` | `ctx.theme.set_variant` |  | `theme_set_variant` |  |
| `theme.edit_file` | `appearance` | `ctx.theme.edit_file` |  | `theme_edit_file` |  |
| `files.readable` | `files` | `ctx.files.readable` |  | `files_readable`, `moybyte.os.files_readable` | `moy_files_readable` |
| `files.ready` | `files` | `ctx.files.ready`, `files.ready` | `files.ready` | `files_ready`, `moybyte.os.files_ready` | `moy_files_ready` |
| `files.list` | `files` | `ctx.files.list`, `files.list` | `files.list` | `files_list`, `moybyte.os.files_list` | `moy_files_list` |
| `files.count` | `files` | `ctx.files.count` |  | `files_count`, `moybyte.os.files_count` | `moy_files_count` |
| `files.load` | `files` | `ctx.files.load`, `files.load`, `files.load_text` | `files.load`, `files.load_text` | `files_load`, `moybyte.os.files_load` | `moy_files_load` |
| `files.save` | `files` | `ctx.files.save`, `files.save`, `files.save_text` | `files.save`, `files.save_text` | `files_save`, `moybyte.os.files_save` | `moy_files_save` |
| `files.delete` | `files` | `ctx.files.delete`, `files.delete` | `files.delete` | `files_delete`, `moybyte.os.files_delete` | `moy_files_delete` |
| `files.duplicate` | `files` | `ctx.files.duplicate`, `files.duplicate` | `files.duplicate` | `files_duplicate`, `moybyte.os.files_duplicate` | `moy_files_duplicate` |
| `files.rename` | `files` | `ctx.files.rename`, `files.rename` | `files.rename` | `files_rename`, `moybyte.os.files_rename` | `moy_files_rename` |
| `files.new_name` | `files` | `ctx.files.new_name`, `files.new_name` | `files.new_name` | `files_new_name`, `moybyte.os.files_new_name` | `moy_files_new_name` |
| `nav.open_app` | `launch`, `front` | `ctx.nav.open_app`, `open_app` | `open_app` | `nav_open_app`, `moybyte.os.nav_open_app` | `moy_nav_open_app` |
| `prefs.get` | `prefs` | `ctx.prefs.get`, `prefs.get` | `prefs.get` | `prefs_get`, `moybyte.os.prefs_get` | `moy_prefs_get` |
| `prefs.set` | `prefs` | `ctx.prefs.set`, `prefs.set` | `prefs.set` | `prefs_set`, `moybyte.os.prefs_set` | `moy_prefs_set` |
| `prefs.clear` | `prefs` | `ctx.prefs.clear`, `prefs.clear` | `prefs.clear` | `prefs_clear`, `moybyte.os.prefs_clear` | `moy_prefs_clear` |
| `clipboard.put_text` | `clipboard` | `ctx.clipboard.put_text`, `clipboard.put_text` | `clipboard.put_text` | `clipboard_put_text`, `moybyte.os.clipboard_put_text` | `moy_clipboard_put_text` |
| `clipboard.text` | `clipboard` | `ctx.clipboard.text`, `clipboard.text` | `clipboard.text` | `clipboard_text`, `moybyte.os.clipboard_text` | `moy_clipboard_text` |
| `clipboard.kind` | `clipboard` | `ctx.clipboard.kind`, `clipboard.kind` | `clipboard.kind` | `clipboard_kind`, `moybyte.os.clipboard_kind` | `moy_clipboard_kind` |
| `clipboard.seq` | `clipboard` | `ctx.clipboard.seq`, `clipboard.seq` | `clipboard.seq` | `clipboard_seq`, `moybyte.os.clipboard_seq` | `moy_clipboard_seq` |
| `moybyte.notify` | `notifications` | `moybyte.notify` | `moybyte.notify` | `moybyte_notify`, `moybyte.os.notify` | `moy_notify` |
| `moybyte.open_with` | `front` | `moybyte.open_with` | `moybyte.open_with` | `moybyte_open_with`, `moybyte.os.open_with` | `moy_open_with` |
| `moybyte.share` | `front` | `moybyte.share` | `moybyte.share` | `moybyte_share`, `moybyte.os.share` | `moy_share` |
| `moybyte.send` | none | `moybyte.send` | `moybyte.send` | `moybyte_send`, `moybyte.os.send` | `moy_send` |
| `moybyte.award` | none | `moybyte.award` | `moybyte.award` | `moybyte_award`, `moybyte.os.award` | `moy_award` |
| `moybyte.progress` | none | `moybyte.progress` | `moybyte.progress` | `moybyte_progress`, `moybyte.os.progress` | `moy_progress` |
| `moybyte.on` | none | `moybyte.on` | `moybyte.on` | `moybyte_on`, `moybyte.os.on` | `moy_on` |
| `moybyte.every` | none | `moybyte.every` | `moybyte.every` | `moybyte_every`, `moybyte.os.every` | `moy_every` |
| `moybyte.after` | none | `moybyte.after` | `moybyte.after` | `moybyte_after`, `moybyte.os.after` | `moy_after` |
| `moybyte.cancel` | none | `moybyte.cancel` | `moybyte.cancel` | `moybyte_cancel`, `moybyte.os.cancel` | `moy_cancel` |
| `moybyte.pick` | `front` | `moybyte.pick` | `moybyte.pick` | `moybyte_pick`, `moybyte.os.pick` | `moy_pick` |
| `moybyte.log` | none | `moybyte.log` | `moybyte.log` | `moybyte_log`, `moybyte.os.log` | `moy_log` |
| `moybyte.recv` | none |  |  | `moybyte_recv` |  |
| `moybyte.item_read` | none |  |  | `moybyte_item_read`, `moybyte.os.item_read` | `moy_item_read` |
| `moybyte.item_write` | none |  |  | `moybyte_item_write`, `moybyte.os.item_write` | `moy_item_write` |
| `net` | `multiplayer` | `net`, `on_net` | `net`, `on_net` |  |  |
| `pins` | `pins` | `pin_write`, `pin_read` | `pin_write`, `pin_read` |  |  |
| `console` | `console` | `print` | `print` |  |  |
| `moybyte.at` | `alarms` | `moybyte.at` | `moybyte.at` | `moybyte_at`, `moybyte.os.at` | `moy_at` |
| `moybyte.service_start` | none | `moybyte.service_start` | `moybyte.service_start` | `moybyte_service_start`, `moybyte.os.service_start` | `moy_service_start` |
| `moybyte.service_stop` | none | `moybyte.service_stop` | `moybyte.service_stop` | `moybyte_service_stop`, `moybyte.os.service_stop` | `moy_service_stop` |
| `moybyte.service_running` | none | `moybyte.service_running` | `moybyte.service_running` | `moybyte_service_running`, `moybyte.os.service_running` | `moy_service_running` |
| `moybyte.random` | none | `moybyte.random` | `moybyte.random` | `moybyte_random`, `moybyte.os.random` | `moy_random` |
| `moybyte.sha256` | none | `moybyte.sha256` | `moybyte.sha256` | `moybyte_sha256`, `moybyte.os.sha256` | `moy_sha256` |
| `moybyte.hmac_sha256` | none | `moybyte.hmac_sha256` | `moybyte.hmac_sha256` | `moybyte_hmac_sha256`, `moybyte.os.hmac_sha256` | `moy_hmac_sha256` |
| `moybyte.aes_gcm_seal` | none | `moybyte.aes_gcm_seal` | `moybyte.aes_gcm_seal` | `moybyte_aes_gcm_seal`, `moybyte.os.aes_gcm_seal` | `moy_aes_gcm_seal` |
| `moybyte.aes_gcm_open` | none | `moybyte.aes_gcm_open` | `moybyte.aes_gcm_open` | `moybyte_aes_gcm_open`, `moybyte.os.aes_gcm_open` | `moy_aes_gcm_open` |
| `moybyte.x25519` | none | `moybyte.x25519` | `moybyte.x25519` | `moybyte_x25519`, `moybyte.os.x25519` | `moy_x25519` |
| `moybyte.dev_open` | `lease`, `http`, `lora`, `mic`, `ble`, `usb`, `midi`, `camera`, `media`, `media:url`, `pins`, `multiplayer` |  | `moybyte.dev_open` | `moybyte_dev_open`, `moybyte.os.dev_open` | `moy_dev_open` |
| `moybyte.dev_close` | `lease`, `http`, `lora`, `mic`, `ble`, `usb`, `midi`, `camera`, `media`, `media:url`, `pins`, `multiplayer` |  | `moybyte.dev_close` | `moybyte_dev_close`, `moybyte.os.dev_close` | `moy_dev_close` |
| `moybyte.dev_read` | `lease`, `http`, `lora`, `mic`, `ble`, `usb`, `midi`, `camera`, `media`, `media:url`, `pins`, `multiplayer` |  | `moybyte.dev_read` | `moybyte_dev_read`, `moybyte.os.dev_read` | `moy_dev_read` |
| `moybyte.dev_write` | `lease`, `http`, `lora`, `mic`, `ble`, `usb`, `midi`, `camera`, `media`, `media:url`, `pins`, `multiplayer` |  | `moybyte.dev_write` | `moybyte_dev_write`, `moybyte.os.dev_write` | `moy_dev_write` |
| `moybyte.dev_xfer` | `lease`, `http`, `lora`, `mic`, `ble`, `usb`, `midi`, `camera`, `media`, `media:url`, `pins`, `multiplayer` |  | `moybyte.dev_xfer` | `moybyte_dev_xfer`, `moybyte.os.dev_xfer` | `moy_dev_xfer` |
| `moybyte.dev_set` | `lease`, `http`, `lora`, `mic`, `ble`, `usb`, `midi`, `camera`, `media`, `media:url`, `pins`, `multiplayer` |  | `moybyte.dev_set` | `moybyte_dev_set`, `moybyte.os.dev_set` | `moy_dev_set` |
| `moybyte.dev_get` | `lease`, `http`, `lora`, `mic`, `ble`, `usb`, `midi`, `camera`, `media`, `media:url`, `pins`, `multiplayer` |  | `moybyte.dev_get` | `moybyte_dev_get`, `moybyte.os.dev_get` | `moy_dev_get` |
| `moybyte.ed25519_public` | none | `moybyte.ed25519_public` | `moybyte.ed25519_public` | `moybyte_ed25519_public`, `moybyte.os.ed25519_public` | `moy_ed25519_public` |
| `moybyte.ed25519_sign` | none | `moybyte.ed25519_sign` | `moybyte.ed25519_sign` | `moybyte_ed25519_sign`, `moybyte.os.ed25519_sign` | `moy_ed25519_sign` |
| `moybyte.ed25519_verify` | none | `moybyte.ed25519_verify` | `moybyte.ed25519_verify` | `moybyte_ed25519_verify`, `moybyte.os.ed25519_verify` | `moy_ed25519_verify` |
| `moybyte.status_show` | none |  | `moybyte.status_show` | `moybyte_status_show`, `moybyte.os.status_show` | `moy_status_show` |
| `moybyte.status_state` | none |  | `moybyte.status_state` | `moybyte_status_state`, `moybyte.os.status_state` | `moy_status_state` |
| `moybyte.status_panel` | none |  | `moybyte.status_panel` | `moybyte_status_panel`, `moybyte.os.status_panel` | `moy_status_panel` |
| `moybyte.status_remove` | none |  | `moybyte.status_remove` | `moybyte_status_remove`, `moybyte.os.status_remove` | `moy_status_remove` |
| `moy_screen` | none |  |  | `moybyte.os.screen` | `moy_screen` |
| `moy_present` | none |  |  | `moybyte.os.present` | `moy_present` |
| `moy_game_data` | none |  |  |  | `moy_game_data` |
| `moy_game_sound` | none |  |  |  | `moy_game_sound` |
| `moy_game_snd` | none |  |  |  | `moy_game_snd` |
| `moy_game_pmem` | none |  |  |  | `moy_game_pmem` |
| `moy_game_read` | none |  |  |  | `moy_game_read` |
| `moy_game_write` | none |  |  |  | `moy_game_write` |
| `moy_game_erase` | none |  |  |  | `moy_game_erase` |
| `moy_game_list` | none |  |  |  | `moy_game_list` |
| `moybyte.aes_ctr` | none | `moybyte.aes_ctr` | `moybyte.aes_ctr` | `moybyte_aes_ctr`, `moybyte.os.aes_ctr` | `moy_aes_ctr` |
| `moybyte.aes_ccm_seal` | none | `moybyte.aes_ccm_seal` | `moybyte.aes_ccm_seal` | `moybyte_aes_ccm_seal`, `moybyte.os.aes_ccm_seal` | `moy_aes_ccm_seal` |
| `moybyte.aes_ccm_open` | none | `moybyte.aes_ccm_open` | `moybyte.aes_ccm_open` | `moybyte_aes_ccm_open`, `moybyte.os.aes_ccm_open` | `moy_aes_ccm_open` |
| `moybyte.name` | none | `moybyte.name` | `moybyte.name` | `moybyte_name`, `moybyte.os.name` | `moy_name` |
| `moybyte.key_make` | none | `moybyte.key_make` | `moybyte.key_make` |  |  |
| `moybyte.key_public` | none | `moybyte.key_public` | `moybyte.key_public` |  |  |
| `moybyte.key_shared` | none | `moybyte.key_shared` | `moybyte.key_shared` |  |  |
| `moybyte.clock` | none | `moybyte.clock` | `moybyte.clock` | `moybyte_clock`, `moybyte.os.clock` | `moy_clock` |
<!-- END GENERATED -->

Reading the table: the Python column names a shipped app's `ctx` role first
and then a user app's global. The Lua column is a Lua app's and a Lua
service's alike, each name under the permission a Python app's is under
(`tests/test_app_examples.py` drives `tests/fixtures/apps/pinger_lua.moy`).
In a Lua app the console calls (`notify`, `open_with`, `share`, `send`,
`award`, `progress`, `pick`, `status_panel`) are the moybyte module's own functions run as
the app's process, their arguments any values JSON carries; a wake
(`on`, `every`, `after`, `at`) is the kernel's under the app's process and
calls its function in the app's state as each of its frames starts, and
`moybyte.log(level, text)` writes the OS log with `moybyte.ERR`, `WARNING`
and `INFO`: the one C table a Lua service holds too
(`native/moycore/moycore_moybyte.h`). The theme's reads (`theme.token(role)`, `gen`, `light`,
`name`, `variant`) are every Lua app's, as Python's `theme()` is; a Lua app
hears `_minimise`, `_restore`, `moy_action(id, key)` and `moy_open(item)`,
the item a table whose `read()` answers its text and whose `write(text)`
writes it back under an `"rw"` grant. Python holds the leases, the device
APIs and a status item as objects (`moybyte.lease`, `moybyte.http` and the
others, `moybyte.status`: `runtime/system/moybyte.py`), so their rows have
no Python name: Lua and the compiled tiers hold the leases and devices by
handle (the `dev_*` rows, below) and a status item as an icon in a state
with a panel the shell draws (`status_show` to `status_remove`, §10, a
status item). The rows with only wasm and C names (`moybyte.recv`,
`item_read`, `item_write`) are what a compiled app or a native module reads
where a Python or a Lua one is called back or handed an object: its
messages (§8; a native module reads them from its event descriptor) and an
item handed to it. Standard names come first on every tier: Python's
`open`, `os`, `time`, `socket`, `requests`, `asyncio` and `logging`; POSIX
in C; WASI preview1 in wasm; Lua's `io` and `os`.

**Crypto** (`docs/os_2026-11/between_apps.md` §5): `moybyte.random(n)`,
`sha256(data)`, `hmac_sha256(key, data)`, `aes_gcm_seal(key, plain)`,
`aes_gcm_open(key, sealed)`, `aes_ctr(key, data)`, `aes_ccm_seal(key, data,
tag)`, `aes_ccm_open(key, sealed, tag)`, `x25519(secret, peer)`,
`ed25519_public(secret)`, `ed25519_sign(secret, msg)` and
`ed25519_verify(pub, msg, sig)` are every
program's, with no permission, one C body on every tier
(`native/moy_net/moy_crypto.h`; Ed25519 is the vendored Monocypher's).
Bytes in and bytes out (a Python `str` is its UTF-8). A seal is a fresh
nonce, the ciphertext and the tag, 28 bytes longer than what it sealed, under
a 16-, 24- or 32-byte key; an open that does not authenticate answers `None`
in Python, `nil` in Lua, FORGED (10) negated to a compiled app and `EBADMSG`
to a native or WASI program. `aes_ctr` and `aes_ccm_*` are for wire formats
that fix their own nonce (Meshtastic's): `aes_ctr`'s `data` is the 16-byte
initial counter block, then the bytes, and it answers the bytes XORed with
the key stream (the same call decrypts); `aes_ccm_seal`'s `data` is the
13-byte nonce, then the plaintext, and it answers the ciphertext and a
`tag`-byte tag (4 to 16, even; no associated data); `aes_ccm_open` takes the
nonce, the ciphertext and the tag and opens as a GCM open does. The nonce is
the caller's to keep unique. `x25519` with no peer answers the secret's
public key, with one the shared secret. Ed25519 is RFC 8032's: a 32-byte
secret (the seed) gives a 32-byte public key and deterministic 64-byte
signatures; `ed25519_verify` answers 1 or 0 (`True` or `False` in Python,
`true` or `false` in Lua), 0 for any signature that does not check, a key or
a signature that does not decode among them. A buffer too small is FULL
(`ERANGE`), a length refused BAD (`EINVAL`; a `ValueError` in Python).

**An app's own key pairs** (`docs/os_2026-11/between_apps.md` §5):
`moybyte.key_make(name)`, `key_public(name)` and `key_shared(name, peer)` are
console calls a Python or a Lua program holds, with no permission. The console keeps an X25519
pair for the calling app under `name` (1 to 32 of a-z, 0-9, `_` and `-`),
whose secret never reaches the app: `key_make` answers the public key,
making the pair the first time; `key_public` answers it, or `None` (`nil`)
where none was made; `key_shared` answers the X25519 shared secret with the
peer's public key `peer`, or `None` where the pair is missing or the peer
is of small order. Keys and secrets cross as 64 hex digits. The pairs go
when the app is removed.

**A compiled app (#224)** is `"runtime": "wasm"` with `"extensions":
["moybyte.app"]`. It reaches its roles through imports from module
`"moybyte.app"` (SPEC.md §16.2's vendor-extension rule), each named
`<role>_<verb>` at the types its row's parameters give
(`native/moy_app/moy_app_wasm.h` is the adapter's contract): a number answers
as an `i32`, text or a blob is written into the caller's buffer and answers
its length, and a negative answer is `moy_app.h`'s code negated. The theme's
reads are every app's; an import from a role its permissions do not name is
refused at load, the import named. Its page is the UI tree's `uitree_*`
rows (`native/moy_uitree/moy_uitree_wasm.h`; `sdk/include/moybyte/uitree.h`
is its header, §3), the engine a Python and a Lua app draw with, every
compiled app's. The console calls
(`moybyte_notify`, `open_with`, `share`, `pick`, `send`, `award`,
`progress`, `on`, `at`, `every`, `after`, `cancel`, `log`) are every
compiled app's to import, each
answered as the app's process under the permission the call names, as a
Python app's is (`notifications`, `alarms`, the front's gate): a refused
`notify` or `at` answers DENIED (`-4`), and `open_with`, `share` and
`pick` answer 0 where Python's answer False. It hears what a Python app is called back for as
messages from `"system"`: `_minimise`, `_restore`, `moy_action` (id, key)
and `moy_open`, which it listens on with `moybyte_on`, and its wakes,
`moybyte.at` and `moybyte.timer` (the wake's id, §9), which it listens on
by asking for one. `moy_open` carries the item's handle, its type, its
mode and its name (a cancelled pick's handle 0), the item read and written by its handle with
`moybyte_item_read(h, buf, cap)` and `moybyte_item_write(h, data)`, on
the app's own task under the store's lock where the item is a user file
(the kernel's table of the items handed, `native/moy_kernel/moy_items.h`)
and through the console otherwise. Each console call runs on the VM's task,
a hop from a board's session thread. The app is
cart-shaped: fullscreen, its loop the cart's, and on the desk a fixed canvas
in its player window, which the WM scales. `tools/wasm_cart.py` builds the
folder (`src/main.wat`, or C or Rust through wasi-sdk or `wasm32-wasip1`; a
C app as a reactor, its memory the manifest's `memory` pages,
`tests/fixtures/wasm/app_talk.moy`), `--chip` adding a board's signed AOT
module; `native/moy_wasm/README.md` is the tier.

**A compiled game** (any `type` but `app`) that declares `"extensions":
["moybyte.app"]` imports from the same module: its run holds a grant of its
own, made from its permissions and their consent as an app's is, so
`moybyte_award`, `moybyte_progress`, `moybyte_notify` and the device
handles below answer it as they answer an app, and an import its
permissions do not grant is refused at load. A game that declares none
holds no grant. Its scenes, paint images and mouse are Moybyte's other
extensions (`docs/moy_cart_api.md`, "A compiled cart's Moybyte verbs").

**Devices by handle.** A compiled program (a compiled app or game, a WASI program,
a native module) and a Lua program (an app or a service) hold a lease or a
device API by a handle where a Python program holds an object (`native/moy_kernel/moy_dev.h` is the authority
on the leases' names, keys and answers, `runtime/system/dev_handles.py` on
the device APIs'). `dev_open(name, cfg)` answers the handle:
`name` a lease row (`"gpio<n>"`, `"uart<n>"`, `"spi<n>"`, `"pwm<n>"`,
`"adc<n>"`, `"i2c"`) or a device (`"http"`, `"lora"`, `"mic"`, `"ble"`, `"usb"`, `"midi"`, `"camera"`, `"media"`), the `pins` permission's
pins (`"pins"`) or a port of the console-to-console radio link (`"net"`), `cfg` words
`key=value` (`"mode=out value=1"`, `"baudrate=9600"`, `"scl=20 sda=21
addr=0x48"`, `"url=http://example.com/ cap=4096"`). On the handle,
`dev_read(h, buf, cap)` takes what waits (0 when nothing does),
`dev_write(h, data, len)` sends, `dev_xfer(h, data, len, buf, cap)` writes
then reads as one transfer (SPI's full duplex, an I²C register read),
`dev_set(h, cfg)` configures it again and `dev_get(h, what)` reads one
number (`"value"`, `"any"`, `"status"`, `"rssi"`, ...); `dev_close(h)` gives
it back, and the process's end closes what it left open. A ring's records
are read through the handle on every tier, never posted as messages: a
pin's edges (`dev_set(h, "edges=both")`, then 8 bytes an edge from
`dev_read`), a packet the radio heard, the microphone's samples, the BLE
face's events. A program polls its handles where it polls its messages: on
a timer (`moybyte.every`), or in a compiled app's `_update`. The radio also says when it has something: the
holder of a `lora` handle that listens on `"lora"` (`moybyte.on("lora",
fn)`, a compiled program's `moy_on`) is posted the system's message
`"lora"` with the event (1 a packet heard, 2 one sent, then LoRaWAN's
joined, join failed, downlink and uplink done) and a length for each, so a
service sleeps until a packet comes; the packet is still read through the
handle.

Lua holds the rows as `moybyte.dev_open(name[, cfg])`,
`dev_close(h)`, `dev_read(h[, cap])`, `dev_write(h, bytes)`,
`dev_xfer(h, bytes[, cap])`, `dev_set(h, cfg)` and `dev_get(h, what)`
(`native/moy_app/moy_app_lua.c`): a read answers the bytes as a string (at
most `cap`, 4096 by default), an error is nil and its name (`"BUSY"`,
`"DENIED"`, `"BAD"`, `"ABSENT"`, `"FULL"`, ...), and `dev_get` answers the
number as the row does. A Lua service calls them on its own task, so its
radio, its pins and its other kernel handles keep working through an S3's
VM stop.

The radios act by `dev_set` words, one action a set, and `dev_write`
carries the bytes to where a word pointed it. A `ble` handle scans
(`"scan=3000"`), connects (`"connect=aa:bb:cc:dd:ee:ff"`, `"connect=off"`),
finds a characteristic (`"find=2a19"`, or the 128-bit UUID), reads it
(`"read=0x20"`), subscribes (`"subscribe=0x10"`, `"unsubscribe=0x10"`) and
advertises (`"advertise=name data=ffff0102"`, `"advertise=off"`);
`"write=0x30"` makes each `dev_write` a write to that characteristic. What
each did comes back from `dev_read` as records, Python's `ble.on` events
with their bytes: a 12-byte head (the event, the bytes after it, `a`,
`b`) then those bytes, an advertisement's address and name, a read's
value, a notification's. A `lora` handle joins a LoRaWAN network with
`"join=otaa dev_eui=... join_eui=... app_key=..."` (the keys in hex as a
network console prints them) and `"send=2"` makes each `dev_write` an
uplink on port 2 (`"send=raw"` a raw packet again); a downlink is read as
a packet is, `dev_get(h, "port")` its port, and `"joined"` and `"busy"`
say where the join stands.

A `usb` handle holds the USB host. Its `dev_read` records have the same
12-byte head, its `a` a device's bus address: the open reads as an ATTACH
for each device already plugged in (its class, kind, vendor and product
ids, then its name), then ATTACH and DETACH as devices come and go, a HID
device's REPORT with the report, a serial device's DATA with the bytes it
sent, SENT once a write went. `"serial=2 baud=9600"` opens a CDC-ACM
device's line and `"write=2"` makes each `dev_write` a write to it (a
serial or a USB-MIDI device).

A `midi` handle is one MIDI port, named when it opens: `"uart=uart1"`
(`"baud=31250"` by default, the row's `lease:uart1` too), `"usb=3"` (a
USB-MIDI device) or `"ble=aa:bb:cc:dd:ee:ff"` (a BLE-MIDI peripheral,
connected, found and subscribed for you; `dev_get(h, "state")` is 1 once
its messages flow). `dev_write` sends whole MIDI messages and `dev_read`
takes the port's messages, 3 bytes each (status, data1, data2). A process
opens as many ports as it needs, and holds the MIDI API from its first to
its last. A `camera` handle's `dev_read` is the latest frame, whole
(`dev_get(h, "w")` by `"h"` RGB565 pixels, big-endian), nothing before the
first.

A `media` handle makes the process a client of the media service's one
stream, the system's (`docs/os_2026-11/hardware.md` §3): `dev_write` plays
the source its bytes name in place of what plays, whoever played it (a file
or a playlist under `media`, an `http://` or `https://` URL under
`media:url` and `http`), and the person is told when it takes over another
app's list. A file plays only from the cart's
own folder and the folder its `files:<folder>` permission names (owner,
2026-11-09), a relative path being the cart folder's: any other, or a
playlist naming one, is DENIED whether it is
there or not, so a refusal tells nothing of what a folder holds, and
`dev_xfer`'s probe refuses the same files. `dev_set` controls it
(`"volume=60"`, `"pause=1"`, `"pause=0"`, `"seek=30"`, `"skip=next"`,
`"skip=prev"`, `"stop=1"`), `dev_get` reads its numbers (`"state"`,
`"paused"`, `"at"`, `"len"`, `"volume"`, `"stamp"`, which moves when they
do, `"mine"`, 1 where this process's write set what plays, ...), `dev_read`
its now-playing text as four lines (title, artist, station, source) and
`dev_xfer` probes a file without playing it (its length in seconds as 4
bytes, then its title and artist on two lines). Closing the handle, or the
process's end, leaves the stream playing: it ends with its list, or a
client's `"stop=1"`.

A `pins` handle is Python's `pin_write` and `pin_read`: `dev_set(h,
"gpio6=1 gpio20=0")` drives each pin it names, `dev_get(h, "gpio5")` reads
one (an input where it was not driven). It takes each pin of the board's
gpio row for the process at its first use, under `pins` alone (no
`lease:gpio`), and its close gives them back, left safe.

A `net` handle is one port of the radio link other consoles hear
(`docs/netplay_v1.md`, Ports), the way a socket is: any process opens it,
whatever runs in front, and each port's messages reach only its holder.
`dev_open("net", "port=7")` takes port 7 (1 to 65535, one holder a port:
port 0 is the game in front's `net.send` and `on_net`), `dev_write` sends
one message of at most 240 bytes to every console in range on that port,
and `dev_read` takes the messages heard on it as records: the sender's MAC
(6 bytes), the port and the length (2 bytes each), then the bytes. Radio
input is untrusted, so the sender is in every record for the program to
judge; `"from=match"` narrows a port to the live match's peer and hears
nothing outside a match. A port keeps four messages unread (`dev_get(h,
"drops")` counts what it dropped while full); a process holds four ports and
the console eight, FULL past either. A port's sends are budgeted so they
cannot crowd a match's inputs off the air (`docs/netplay_v1.md`, Ports): a
write past the budget is BUSY and sends nothing, and `"sent"` and
`"refused"` count both. The radio stays up while any port is
open, and a match's inputs never reach a port.

Each name needs what Python's needs: `lease:<row>` (`lease:gpio` for
anything on the pins: a pin, a PWM, an ADC, an I²C bus), `http`, `lora`,
`mic`, `ble`, `usb`, `midi`, `camera`, `media` (or `media:url`), `pins`,
`multiplayer` (`net`). One holder a lease or a device, whatever the tiers: a
resource a Python program's object holds is BUSY to a handle and the
reverse (`-11` to a compiled app, `EBUSY` to a native or WASI program), and
a process opens a radio, the microphone, the USB host, the camera, the
media service or its pins once. A refused permission is
DENIED (`EACCES`), a name, key or value the console does not take BAD
(`EINVAL`), a handle not open, or a radio verb that needs a connection or a
join, ABSENT (`ENOENT`), a buffer that cannot hold one record FULL
(`ERANGE`).

**A status item** (owner, 2026-11-09, on #246). A compiled program, and a
Lua program (an app or a service), puts an
item in the bar as a Python program does (§6), but it never draws there: its
item is an icon in a state, and its menu is a panel of rows it describes,
which the shell draws (in the item's menu on the desk, in its card of the
control centre on a handheld). `status_show(icon, state, order)` answers
the item's handle (FULL, `ERANGE`, while the bar holds its four), `icon`
a name of the console's icon set and `state` `MOY_STATUS_ON` (0, the
accent), `MOY_STATUS_PAUSED` (1) or `MOY_STATUS_ERROR` (2, the danger ink);
`status_state(h, state)` changes it, `status_remove(h)` takes it out, and
the process's end takes out what it left. `status_panel(h, rows)`
describes the panel, one row a line, eight at most:

```
text <label>[TAB<value>]               a row that shows, no stop
button <id> <label>                    a row that acts
toggle <id> <label> <0|1>              a two-state row
slider <id> <label> <min> <max> <v>    a value from min to max
```

An id is the program's own word, at most 16 bytes; a label runs to the
numbers that end its line. A press, a toggle's change or a slider's step
reaches the program as the system's message `moybyte.status`,
`[item, id, value]` (a button's value 1), which it hears without asking:
its first panel listens on the name for it, one of the eight names a
process listens on (`MOY_EVQ_LISTEN`). A row keeps the value it moved to
until the program describes the panel again, as it does whenever what the
rows say changes. An item with no panel, or an empty description, has no
menu: a tap on it opens the app (its run comes to the front, or its cart
opens). A description no kind reads is BAD (`EINVAL`), a handle not the
process's ABSENT (`ENOENT`). In Lua, `moybyte.status_show(icon[, state[,
order]])`, `status_state`, `status_panel(h[, rows])` and `status_remove`
answer the row's number (the handle, 0, or the code negated: FULL -2, BAD
-7, ABSENT -8), and the press is `moybyte.on("moybyte.status", fn)`'s
`fn(from, item, id, value)`, `from` being `"system"`.
`runtime/system/status_items.py` is the authority (`parse`, `Panel`).

**A command** (`"type": "command"`) is a program the terminal runs by
its id's name (`local.hello` is `hello`): in Python its `main(argv)`, with
`print` and `input` on the session's streams, answering the exit code; in
wasm a WASI program's `_start`; in C an ELF module's `main`
(`runtime/shell/sh_door.py`, `docs/os_2026-11/system.md` §1).

**A WASI program** (a command or a service) is any program wasi-sdk, Rust's
`wasm32-wasip1` or Zig builds: files under its permissions, clocks, args, env,
stdio; it imports `moybyte.os` for its messages (`send`, `on`), its
notifications, badges and log lines (`notify`, `award`, `progress`, `log`),
its wakes (`every`, `after`, `at`, `cancel`, §9), the front's calls
(`open_with`, `share`, `pick`, `nav_open_app`) and a picked item's
(`item_read`, `item_write`), its prefs and the clipboard (`prefs_get`,
`prefs_set`, `prefs_clear`, `clipboard_put_text`, `clipboard_text`,
`clipboard_kind`, `clipboard_seq`), the files role's documents
(`files_list` to `files_new_name`), its leases and devices by handle
(`dev_open` to `dev_get`, above) and its status item (`status_show` to
`status_remove`, above), and `sdk/include/moybyte/os.h` declares
each under its C name, `moy_notify`, `moy_prefs_get` and the rest. A console call waits for
the console's answer: a service's at the scheduler's next poll, a
foreground command's at its job's next step; a background command's answers
AGAIN after 5 s, its door serving nothing while it runs. The files, nav,
prefs, clipboard, device and item rows, and `share`, are the role table's
for a grant its start makes, over the roles its granted permissions name
(`runtime/system/sched_compiled.py`, `compiled_run`), as a C program's are: a
permission it lacks answers ACCES and a buffer too small RANGE. The files
rows reach the store's documents in the folder its `files` permission
names, the folder its WASI files (§5) are rooted at. A WASI program has no
window: its pick reaches it as the message `moy_open` (handle, mime, mode,
name) on its event descriptor, which it listens on, as a C program's does
(below), and the handle is its own process's.

**A C program** is an ELF module built against the OS function table by
`tools/elf_cart.py` with the SDK (`sdk/README.md`): a command's
`main(argc, argv)`, or a service's loop. Its manifest names its chips
(`"native": ["esp32s3", "esp32p4"]`) and asks for `full_access`;
`native/moy_elf/README.md` is the tier and `tests/fixtures/elf/elf_app.moy`
calls the app rows. `moy_pick(mime, mode)` puts the console's picker up for
it as a compiled app's `pick` does (a command holds no `front` unless it asks,
so its pick waits as a notification); the item picked reaches it as the
message `moy_open` on its event descriptor, which it listens on with
`moy_on`: its arguments the handle, the type, the mode and the name (a
cancelled pick's handle 0), the handle what `moy_item_read(h, buf, cap)` and
`moy_item_write(h, data, len)` take until the process ends
(`runtime/system/moybyte.py`, `hand_item`, which hands an item to any
process that is not the app on screen). Its leases and devices are
`moy_dev_open` to `moy_dev_get` (above), each under the `lease:<row>` or
device permission its manifest asks beside `full_access`, and its status
item `moy_status_show` to `moy_status_remove` (above).

## 11. Lifecycle

A UI tree app (§3) declares at its top level, its `opened` hook runs as it
opens, and the engine runs its frames. A game, and an app on the immediate
API, has `_init()` once, then `_update(dt)` and `_draw()` (a game's three, in
`docs/moy_cart_api.md`) and `_layout(w, h, fs)` where it is responsive
(§3). `quit()` leaves. Several apps run at once: an app the user minimises keeps
its `_update` every frame with no `_draw` (a player, a download), hearing
`_minimise()` going in and `_restore()` coming out; a minimised game is
paused (`docs/os_2026-11/processes.md` §1). Closing the app ends its
process, its sound and its wakes.

**Three strikes (#160).** An exception opens the stop card, whose See why
opens your code at the line. What the Player cannot catch (a hang, an
out-of-memory, a native fault) is caught by the crash guard
(`runtime/shell/crash_guard.py`): it marks the app before its code runs and
clears the mark after three painted frames; three opens that never healed
and the console stops running it, the next tap landing on the stop card. The
cart stays on Make, where editing it is how it gets fixed. It arms for
`type: "app"` carts only.

## 12. Debugging

- **The OS log** (`native/moy_kernel/moy_log.h`): every start, exit, crash
  (a Python traceback, a Lua or wasm panel), strike, refusal and service
  line, under its process id. Read it in Settings → About → System log, with
  the terminal's `log`, or over the dev channel's `log [level] [+seq] [name]`
  word (`tools/board.py tdeck tail 3 --send "log err"`). A Python app writes
  to it with `logging`; a cart's `print` draws on the screen, and a service's
  goes to the log.
- **A crash** shows its stop card's See why; a background app's crash posts
  a notification, and the task manager's row offers its details.
- **Services**: `service status` in the terminal, or on a board
  `tools/board.py p4 sh "service status"`.
- **On a board**: `tools/board.py <board> state`, `shot`, `py "..."` (an
  expression against the live console) and `tail`; the `on-glass` skill.
- **On the host**: the console is the same code; `tests/test_app_examples.py`
  drives an app with keys and a service with messages through
  `tests/ws_helpers.py`'s `build_ws`, the way to pin an app's behaviour.

## 13. Shipped apps: the console's own

Everything above is a USER app: a cart, editable on Make. A SHIPPED app
(Settings, Files, Paint, Calc) is a Layer class
in `runtime/`, frozen into the firmware and registered from a manifest; only
the console's own apps take this path. **Calc** (`runtime/apps/calc_app.py`,
`system_carts/moybyte.calc.moy`) is the reference: its screen is one
`uitree` page, and `uitree_app.app_layer(id, title, build)` makes
the Layer class below from it, which its manifest's `entry` names.

**The two files.** An identity cart, `system_carts/moybyte.<slug>.moy`,
gives the app its tile, title and re-seed, and its manifest declares the
app. A built-in is known by where it came from: a folder the firmware's seed
wrote (`moy_store_base.builtin_name`, against the roster the seed records
for its store, `seeded`). Only the seed writes the built-ins' namespace,
and the console's own release index, which publishes the seed carts but
the test fixtures as its official carts, those no store is seeded with
(`seed: false`) among them (a carts index naming a `moybyte.` folder or id is refused
unless it is that index with its signature verified,
`.claude/rules/carts.md`; a cart made under an author of that name is made as
`local.`'s), and an id of that namespace
names a cart only in its own folder (any other id, only where no folder is
named for it, §2), so a cart that copies a built-in's
manifest, its id, title, marker and `"system": true` (which only
`tools/gen_device_carts.py` reads, to pick the seed carts), is an ordinary
user cart with its own grant key (`tests/test_user_apps.py`):

```json
"moybyte": { "app": { "id": "myapp", "entry": "myapp_app:MyAppLayer",
                      "order": 80, "needs": ["surface", "theme", "damage"],
                      "marker": "myapp", "min_size": [200, 120] } }
```

then `python tools/gen_device_carts.py --app-decls` regenerates the frozen
copy (`runtime/shell/app_decls.py`, whose header names every key). The
declaration is what a boot reads: the console registers each app from it
(`app_slot.AppSlot`) and imports the app's module, makes its context
with the roles `needs` names (under `prefs_ns`, else its id) and constructs
it when the app first runs, so a boot holds no app. It claims the identity
cart by its title, the `marker` permission and its folder; its window title
is `name`, else the cart's title; `min_size` is its resize floor; a
`service` (`"module:Class"`) is built at boot over the app's context and
handed to the app as its constructor's third argument (Paint's
`ArtworkService`, the console's `ws.artwork`). The Layer:

```python
class MyAppLayer(AppLayer):      # from layers import AppLayer
    id = "myapp"          # process kind: router, back-stack, window key
    domain = "system"     # draws on the responsive system canvas
    TITLE = "MY APP"      # the windowed WM's title strip: the declaration's `name`

    def __init__(self, ctx, names): ...   # ctx: its AppContext
    def open(self): ...           # (re)enter on every launch
    def relayout(self, w, h, fs): ...
    def close(self): ...          # optional: it is leaving the screen
    def draw(self, dt): ...
    def handle_input(self, i): ...
    def handle_pointer(self, px, py, click): ...
```

That is the whole list: the console registers it from the declaration
(`app_slot.AppSlot`, built at its first run by `ws.spine.built`), and the launcher's claim, the router, the back-stack,
the window and its chip, the resize floor (`min_size`), text mode (what its page has focused) and the exitable
bar all follow; a new `runtime/`
module reaches every board unless a `board.toml` denies it (#161). The shell's
own two, Settings and the task manager, register through the same call with
no cart as their identity: they join the router, the app table and
`ws.app(id)`, not the launcher's claims, and what the frame asks of them is the
`Layer` protocol's (`moved`, `leave`, ...), never their id.
`tests/test_app_registry.py` fails a hand-written app name anywhere else, and
`tests/test_app_api.py` holds the Calc set.

**The AppContext** (`runtime/shell/app_context.py`) carries only the roles
a declaration's `needs` names (a shell surface's, its class's `NEEDS`):

<!-- GENERATED by tools/gen_os_table.py from native/os_calls.json: the roles. Do not edit. -->
| role | what it is | granted by | verbs |
|---|---|---|---|
| `ctx.damage` | whole-surface invalidation: repaint next frame, or ask for one more frame from inside `draw()`; the kernel's flags, folded by the frame gate where it folds the console's dirty flag | the shell | `all()`, `again()` |
| `ctx.surface` | the grant's surface row, which the shell writes wherever it changes (on the desk, the window the app is in): the canvas the app draws on, its size, its scales, the window flag, the content rect the host's exitable strip leaves a running app (`content_rect()`, `(x, y, w, h)`, and `bar_h()`, its `y` -- what a user app's ungated `content_rect()` and `bar_h()` read), the pointer in the surface's coordinates (`x`, `y`, `down`, `click`, `visible`). | the shell | `canvas()`, `size()`, `font_scale()`, `chrome_scale()`, `windowed()`, `bar_h()`, `content_rect()`, `pointer()` |
| `ctx.theme` | the live token table the look writes at every switch, under a generation: the token dict (rebuilt only when the generation moves), one token by its role id, the generation, the light flag, the theme's and variant's names (the reads every app is given, the floor); the verbs that change the look; and the Appearance page's (`docs/history/theming_2026-09.md` §9 phase 6 step 7): a change to the theme (landing in `custom`), what its rows show, CHROME SIZE, EDIT FILE, and NAME… (step 8: `custom` renamed into a theme of its own, and why a name will not do) | `appearance` | `colors()`, `token()`, `gen()`, `light()`, `name()`, `variant()`, `set()`, `set_variant()`, `change()`, `choices()`, `set_chrome_scale()`, `edit_file()`, `name_custom()`, `name_check()` |
| `ctx.files` | the USER-FILES store (#108), C rows over the layer in `native/moy_store/moy_ufiles.h`: named documents (`docs` is plain Markdown — `files/Documents/<name>.md`, the file's body IS the document), the trash, history sidecars, the image, cover and text codecs, provenance stamps; a grant made for a shared folder (a user app's) reaches the kinds in that folder alone | `files` | `readable()`, `ready()`, `begin()`, `end()`, `list()`, `count()`, `load()`, `save()`, `delete()`, `duplicate()`, `rename()`, `new_name()`, `trash_list()`, `restore()`, `empty_trash()`, `history()`, `history_ops()`, `history_commit()`, `encode_image()`, `decode_image()`, `decode_cover()`, `encode_cover()`, `sig()`, `stamp()`, `encode_text()`, `decode_text()`, `provenance()` |
| `ctx.carts` | the CART store: the live cart list, a new cart, a project's undo journal and its images | the shell | `readable()`, `ready()`, `begin()`, `end()`, `all()`, `can_journal()`, `slug()`, `create()`, `journal()`, `rescan()`, `hydrate()`, `images()`, `save_image()`, `encode_image()` |
| `ctx.nav` | where the console goes next: another app, the Editor, a document, a run | `launch` | `open_app()`, `is_system_app()`, `projects()`, `edit()`, `open_image()`, `open_text()`, `edit_file()`, `play()`, `run_script()`, `cover()`, `cover_gen()` |
| `ctx.prefs` | per-app settings on `system/settings`' rows, namespaced per app (the grant's namespace), a write saved as it is made | `prefs` | `get()`, `set()`, `clear()` |
| `ctx.notify` | the console's own badges and every game's, as Settings lists them: one of the console's awarded by its id, the badges by game (each found one's day, each goal's last value), and today's date on the bar's clock as the badges record it | the shell | `award()`, `groups()`, `today()` |
| `ctx.wallpaper` | the desktop backdrop, the theme's (`docs/theme_and_shell_2026-11.md` D6): what is shown, the wallpaper carts, a wallpaper's title, a pick (a change to the theme, landing in `custom`; None is NONE, the theme's `desktop` fill), the live preview, My Art's thumbnail, and Paint's picture as Paint and Files copy a drawing into it (its two rows C, over the user-files layer), which a My Art pick copies into the theme | the shell | `current()`, `carts()`, `id_for()`, `title()`, `select()`, `preview()`, `thumbnail()`, `load_copy()`, `save_copy()` |
| `ctx.artwork` | Paint's open picture, Paint's settings rows: which it is (`(kind, name)`, or None), and following it when its file is renamed under it | the shell | `current()`, `follow()` |
| `ctx.clipboard` | the system cut/copy/paste buffer (#132): at most 4 KiB of text, kernel state, so it outlives a VM stop; a longer `put_text` answers False and keeps the old text | `clipboard` | `put_text()`, `text()`, `kind()`, `seq()` |
| `ctx.install` | carts from outside (#124): the network Get Carts fetches through, its radio lease, one store op of an install (`op(fn)`, inside the bus gate), the engine's sizing, this console's chip and compiled-code format; in the browser, the keeper that makes an install durable in OPFS, the page's file picker, where carts come from on a page a board serves, and the console serving one where it answers `/official`, which installs and removes carts in its own store when asked (`board()`); the Wi-Fi page Get Carts opens when the radio has no network, and whether it is still open; the console's consent records, which the install prompt reads and writes (`runtime/shell/app_perms.py`); whether the console has a password and whether one typed is it, which the unreviewed warning's yes takes (`runtime/shell/pkg.py`'s `gated`) | the shell | `hold()`, `release()`, `fit()`, `memory()`, `chip()`, `runtimes()`, `home()`, `can_pick()`, `pick()`, `root()`, `writable()`, `op()`, `rescan()`, `free()`, `find()`, `net()`, `keep()`, `wifi()`, `wifi_open()`, `consent()`, `own()`, `board()`, `locked()`, `unlock()` |
| `ctx.wifi` | the console's Wi-Fi station, which Settings' Wi-Fi panel scans, joins and forgets through (`station()`), and the radio lease the panel holds while it is open (`hold()`, `release()`, under the grant's app id); never a cart's | the shell | `hold()`, `release()`, `station()` |
| `ctx.bt` | the Bluetooth keyboard service Settings' keyboard picker drives, or None on a board with none: the touch-only boards' keyboard itself, the T-Deck's second one (`keyboard()`); never a cart's | the shell | `keyboard()` |
| `ctx.usb` | the USB drive, which lends the card to a computer (`runtime/system/usb_drive.py`): the drive or None (`drive()`), turning it on and off, and its state as the computer moved it (`poll()`); never a cart's | the shell | `drive()`, `turn_on()`, `turn_off()`, `poll()` |
<!-- END GENERATED -->

Every context holds a grant, a row of `native/moy_app`'s grant table keyed by
the app's id, and every role is that module's role object over it: a C row
reads the kernel's state, a shell row checks the grant and calls the server
the console registers for the role (`runtime/shell/shell_servers.py`).
`notify`'s rows are the achievements process's (`runtime/system/achievements.py`).
A user app's globals (§6) are a filter over the same contexts
(`make_system_api`, `runtime/shell/system_api.py`). Four rules hold:

- **`needs` is a filter.** Reaching an undeclared role raises;
  `tests/test_app_context.py` fails a role named and not declared, and one
  declared and not named.
- **Roles expose methods, never properties**: a descriptor was measured far
  dearer than a plain call on the P4 (`docs/history/ui_refactor_2026-08.md`
  §2.4), and a test asserts there is none.
- **Hoist.** Bind the roles used every frame once in `__init__` and read the
  live values once at the top of `draw()`; `tests/test_roles.py` budgets it.
- **Storage answers `(value, err)` and never raises**; `begin()`/`end()`
  bracket a session for readiness and hold no gate.

No role hands out the console: `tests/test_app_context.py` fails an app
module that names the Workstation.

**What it draws with.** Its UI tree page (§3; `uitree_app.app_layer`, as
Calc's above), into the frame its host, `ctx.ui` (`ui_host.AppHost`),
begins, with `UI = True`; its handlers hand the host the input (`keys`,
`point`). The engine under it, `runtime/toolkit/ui_draw.py`, is the
chrome's.

**The bar contract is the router's** (`runtime/shell/console.py`, `_app_bar_route`):
it paints the strip after `draw()` and routes a tap in its band before
`handle_pointer()`, so an app lays out in its content rect
(`layout_base.content_of`) and never draws a bar. The optional hooks:

- `close()`: leaving the screen, by any route. Change-gated and cheap: a
  write costs more than a frame (#154).
- `commit()`: just before the bar's back or the window's X, for an app that
  persists on an idle debounce (#111).
- `back()`: one page back, answering True, or False on the first page, when
  the host leaves the app; the AppHost's step (a field's edit, a popover)
  comes first.
- `idle_step()` while `idle_owed`: work that must not land in a draw (a
  file read, a decode), run once on a frame with nothing to paint.
- `page_title()`: the open page's name, after the back chevron or as the
  window's title.
- `glass` (true while it holds the whole glass: no strip, its own back),
  `leave_asked` (its own way out, taken as the bar's back), `BACK_MINIMISES`
  (a back on the first page minimises on the desk), `typing()` (True
  where the app types outside a `ui.field`, as the Terminal does; by
  default a field whose edit is open on its `ctx.ui` page), `cancel()` (the T-Deck's
  Mic inside a field's open edit; by default its `ctx.ui` context's,
  `ui_draw.app_cancel`, so a `ui.field` it draws gives its draft back and
  a `ui.popover` it draws is dismissed),
  `DESK_TILE` (False: off the desk's column; an app no cart in the store
  carries is off it too, as on the home). `layers.AppLayer` defaults
  each; the console asks them through its input policy and nowhere else.

**Between apps.** `ctx.nav.open_app(id)` opens another app by its registered
id (a build without it degrades to a status line); the Files router's verbs
are `nav.projects()`, `nav.edit(cart, tab)`, `nav.open_text(name, kind,
mode)` and `nav.open_image(name, kind, cart)`, each "open that, pointed
here". `projects()` is on `nav`, not `ctx.carts`: a list of places to go is
navigation, not the right to author carts.

## Non-goals

- Several instances of one app.
- IPC beyond messages (§8) and "open that, pointed here" (§5).
