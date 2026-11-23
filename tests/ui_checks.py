"""The checks every settled screen of a UI tree page answers (#272 §2):
plain functions over what the C engine reports after a frame -- the texts
its walk drew as the toolkit measured and fitted them (`CEngine.fits`), its
stops and where the toolkit placed them, its focus, its dialog and its
band's hints. None reads pixels.

`check(eng, content, desk)` answers the findings of the frame the engine
drew last into `content`, each a line naming the app, the page and the
node. The host suite runs it after every frame a test draws (conftest's
`_ui_checks`), where a finding fails the test; the walker and the monkey
run the same functions.

What a rule lets pass is written beside it, so a finding is a new
violation and a decision is made once. The issue's last rule -- one
action, one label, key and icon across the graph -- needs the graph, so it
is the walker's.
"""

WHOLE, ELLIPSIS, CUT = 0, 1, 2          # moy_ui.h's MOY_UI_FIT_*

# The keys an input has, spelled as a hint spells a key out (moy_ui.h's
# moy_ui_hints): any key of the desk keyboard; the T-Deck's keyboard (its
# letters, Shift, Sym, Alt, Mic, Del, Space, enter and the trackball); the
# browser's on-screen gamepad (the stick, A, B and its menu key, Start;
# docs/ui_api_2026-10.md, "Hints"). A hint that spells another out names a
# key the board does not have.
_TDECK = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") | {
    "Shift", "Sym", "Alt", "Mic", "Del", "Space", "space", "enter", "left", "right", "up", "down",
    "ball", "ball_lr", "WASD"}
_PAD = {"A", "B", "Start", "left", "right", "up", "down", "dpad_lr"}
KEYS = {"tdeck": _TDECK, "pad": _PAD}

# The hint actions, in moy_ui.h's MOY_UI_ACT_* order: each draws the keys
# the input in use does it with (moy_ui_hint_keys), which the check reads
# as the band spells them.
ACTIONS = ("confirm", "back", "change", "tabs", "menu", "cancel", "flip", "rotate", "shift", "clear",
           "copy", "more", "search", "move", "scroll")
INPUTS = ("keys", "tdeck", "pad", "touch")     # moy_ui.h's MOY_UI_INPUT_*

# The keys an action's row names that its input lacks, each with why: the
# gamepad column is a physical pad's, whose shoulders (tabs) and Y (more)
# the browser's on-screen pad has none of (docs/ui_api_2026-10.md, "Hints";
# no board declares a physical pad, #98).
ACT_BEYOND = {"pad": {"L", "R", "Y"}}

# Stops that hold other stops: one's box over another's is nesting, not
# overlap.
HOLDERS = {"rows", "scroll", "text_view", "cards", "table", "panes", "pane", "split", "group",
           "text_editor", "canvas", "legacy", "lent"}

# The surfaces not checked yet, each named with why: a page whose body is
# still drawn by the toolkit's verbs beside the engine (a `legacy` or
# `lent` node), whose texts and stops the engine does not report. The
# clean cut empties it. Keyed by the app's module (`name`'s first word).
EXEMPT = {}

# The smallest stop a finger takes under touch, at the font scale: a
# handheld's rows are 18 to 22 px, its metrics' (#272's own example of a
# decision made once), and its smallest row a slider's 16.
TAP_MIN = 16

# Pages whose taps a host resolves by a hit of its own rather than their
# stops' boxes, each with why: the app's module.
OWN_HIT = {
    "runtime.bar_ui":
        "the bar layer resolves a bar tap by its cells (BarLayer._tap_bar), a handheld's status "
        "cluster one target across its icons and the gaps between them",
    "runtime.wm_strip_ui":
        "the window manager resolves a strip tap by its fat-finger hit, at least 32 px a button "
        "(WindowChrome._strip_button_hit)",
}


def name(eng):
    """The app and the page a finding names."""
    app = getattr(getattr(eng, "decl", None), "module", None) or type(eng).__name__
    pages = getattr(eng, "pages", None) or ()
    page = getattr(pages[-1], "__name__", "page") if pages else "page"
    return "%s %s" % (app, page)


def fits(eng, content):
    """A node's text fits its room by the toolkit's measure, or is cut with
    an ellipsis that leaves some of it; one the toolkit fitted to no room
    lies inside the frame's columns, past which the window cuts it."""
    out = []
    x0, x1 = content[0], content[0] + content[2]
    for key, kind, how, x, y, w, room, text in set(eng.fits()):
        if how == CUT:
            out.append("%s %r: %r is %d px in a room of %d, cut with no ellipsis"
                       % (kind, key, text, w, room))
        elif how == ELLIPSIS and x == 0 and y == 0:
            out.append("%s %r: %r is %d px in a room of %d, cut to its ellipsis alone"
                       % (kind, key, text, w, room))
        elif room < 0 and (x < x0 or x + w > x1):
            out.append("%s %r: %r drawn at x %d..%d, past the frame's %d..%d"
                       % (kind, key, text, x, x + w, x0, x1))
    return out


def stop_boxes(eng):
    """Each stop the last frame drew where it shows: (id, kind, box, whole),
    `box` the part of its box a press takes as the toolkit's context that
    frame drew into placed it (`api_hit_box`: inside its page's view),
    `whole` whether that is all of it."""
    import ui_draw
    ctx, C = ui_draw.UI_TARGET[0], ui_draw._C
    out = []
    for sid, kind in eng.stop_kinds().items():
        b = C.api_hit_box(ctx, sid)
        if b is not None and b[2] > 0 and b[3] > 0:
            out.append((sid, kind, b, b == C.api_box(ctx, sid)))
    return out


def _meets(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def stops(eng, content, st):
    """Two stops of one layer (the page, or a dialog or popover over it) do
    not overlap, none lies past the frame's columns, and under touch each
    is at least TAP_MIN at the scale both ways."""
    out = []
    over = eng.over_stops()
    x0, x1 = content[0], content[0] + content[2]
    own = name(eng).split(" ", 1)[0] in OWN_HIT
    tap = TAP_MIN * max(1, getattr(eng, "fs", 1)) if eng.input == "touch" and not own else 0
    for i, (sid, k, b, whole) in enumerate(st):
        if b[0] < x0 or b[0] + b[2] > x1:
            out.append("%s %r at %r lies past the frame's columns %d..%d" % (k, sid, b, x0, x1))
        if k in HOLDERS:
            continue
        if whole and (b[2] < tap or b[3] < tap):
            out.append("%s %r at %r is under the %d px a finger takes" % (k, sid, b, tap))
        for sid2, k2, b2, _w in st[i + 1:]:
            if k2 not in HOLDERS and (sid in over) == (sid2 in over) and _meets(b, b2):
                out.append("%s %r at %r overlaps %s %r at %r" % (k, sid, b, k2, sid2, b2))
    return out


def focus(eng):
    """Focus, where the frame put it, is on a stop the frame drew: the
    page's, or a button of the dialog the toolkit draws. A pointer's scroll
    may leave it out of view, as a wheel leaves a desktop list's, and the
    next key brings it back; a stop its own action turned grey keeps the
    focus until a key moves it (moy-spec's conformance fixture `counter`
    pins that). Under touch no focus draws, and the first key lands it."""
    f = eng.focus_key
    if not f or eng.input == "touch":
        return []
    import ui_draw
    b = ui_draw._C.api_hit_box(ui_draw.UI_TARGET[0], f)
    if b is None:
        if any(("'%s'" % f) in ln and "(off:" in ln for ln in eng.dump().splitlines()):
            return []
        return ["focus is on %r, which the frame drew no stop for" % f]
    return []


def overlays(eng, st):
    """No stop lies under the hints band: a dialog's or a popover's, nor
    one of the page's a control placed past its view (an empty's button).
    A holder meets it where its view runs under the band's edge. Nor does
    any part the page draws show over it, a stop or not (a row's progress
    placed past the view): the toolkit notes the first that did."""
    band = eng.band_rect()
    if band is None:
        return []
    out = ["%s %r at %r lies under the hints band at %r" % (k, sid, b, band)
           for sid, k, b, _w in st if k not in HOLDERS and _meets(b, band)]
    import ui_draw
    over = ui_draw._C.api_over_band(ui_draw.UI_TARGET[0])
    if over is not None:
        out.append("a part of the page shows at %r, over the hints band at %r" % (over, band))
    return out


# Pages whose band names another way out than back, each with why: (the
# app's module, the page's build).
WAY_OUT = {
    ("runtime.settings_ui", "usb_page"):
        "the page holds while the drive is on, Turn off its way out (settings_ui.usb_back)",
}


def action_keys(input, act):
    """The keys input `input` draws hint action `act` with (moy_ui_parts.c's
    ACT_KEYS)."""
    import ui_draw
    return ui_draw._C.lib.moy_ui_hint_keys(INPUTS.index(input), ACTIONS.index(act)).decode()


def hints(eng, desk):
    """Where the band shows, it names the way back (or a field's cancel);
    and every key it draws, spelled out or an action's, is one the input in
    use has."""
    have = KEYS.get(eng.input)
    if eng.input == "touch" or not eng.band:
        return []
    h = eng.hints()
    out = []
    pairs = [(h[i], h[i + 1]) for i in range(0, len(h) - 1, 2)]
    if (pairs and not desk and not any(k in ("back", "cancel") for k, _t in pairs)
            and tuple(name(eng).split(" ", 1)) not in WAY_OUT):
        out.append("the band %r names no way back" % (h,))
    if have is None:
        return out
    for keys, what in pairs:
        act = keys in ACTIONS
        drawn = action_keys(eng.input, keys) if act else keys
        for k in drawn.replace("+", " ").split():
            if k not in have and not (act and k in ACT_BEYOND.get(eng.input, ())):
                out.append("hint %r names %r, a key the %s input does not have" % ((keys, what), k, eng.input))
    return out


def settled(eng):
    """Whether the frame drawn last is a settled screen: neither the engine
    nor the toolkit owes the next frame (a focus that lands there, a scroll
    or a page still moving)."""
    import ui_draw
    ctx, C = ui_draw.UI_TARGET[0], ui_draw._C
    return not (eng.owes or eng.q or C.api_owes(ctx) or C.api_moving(ctx) or C.api_moved(ctx))


def check(eng, content, desk):
    """Every finding of the frame `eng` drew last into `content`: the texts
    on every frame, the rest on a settled one. The console's surfaces are
    checked (their builds' modules under runtime/); a page a test builds
    for itself (a fixture pinning one of the engine's edges, a cut or a
    narrow cell among them) is that test's subject, not a surface."""
    at = name(eng)
    mod = at.split(" ", 1)[0]
    if not mod.startswith("runtime.") or mod in EXEMPT:
        return []
    found = fits(eng, content)
    if settled(eng):
        st = stop_boxes(eng)
        found += stops(eng, content, st) + focus(eng) + overlays(eng, st) + hints(eng, desk)
    return ["%s: %s" % (at, f) for f in found]
