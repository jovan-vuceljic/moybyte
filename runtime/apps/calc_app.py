"""Calc -- the reference SYSTEM APP for the app API (docs/app_api_v1.md): a
`uitree` page (runtime/uitree/uitree.py) the C engine lays out and paints.

  * a cartridge IDENTITY (system_carts/moybyte.calc.moy: manifest + a fallback
    main.py an older shell runs as a plain cart) whose manifest carries the
    `app` block the shell registers from -- there is no per-app line in
    console.py;
  * one page: the display (the tape's earlier sums, the sum or the operand
    banked, the result in the theme's `result` face where it draws it) over
    the keypad, beside it on a wide page, the keys a `ui.grid` of buttons of
    their kinds; `uitree_app.app_layer` makes the app's Layer from it, and
    the engine owns focus, the arrows, Enter and taps.

Kid-facing behavior: a plain integer calculator. Digits build the entry, an
operator banks it, "=" computes and writes the sum on the tape, "C" clears
the entry, the backspace key drops its last digit; division is integer
division, % its remainder, and dividing by zero just says OOPS (no crash,
kid-friendly). The keyboard types the same digits and operators. State and
tape persist while the app stays open, and reset on a fresh open.
"""

import uitree as ui
import uitree_app

# The keypad, 4 x 5, row by row; "0" spans two cells. A key is its
# operation: digits, the operators, "C", "<" (backspace), "." and "=".
KEYS = ("C", "<", "%", "/", "7", "8", "9", "*", "4", "5", "6", "-",
        "1", "2", "3", "+", "0", ".", "=")
# The sign an operator's key wears.
SIGNS = {"/": "÷", "*": "×", "-": "−"}
TAPE_KEEP = 8           # the sums the tape holds
DIGITS = 12             # the entry's longest


def kind_of(key):
    """Calc's one per-key decision (DESIGN.md, "Button kinds")."""
    if key == "=":
        return "primary"
    if key == "C":
        return "danger"
    if key in "/*-+%":
        return "tonal"
    return "normal"


s = ui.state(entry="0", result="0", expr="", acc=0, op="", shown=False, whole=True,
             tape=ui.model(key="n", n=0, line=""), taped=False)


def _sign(op):
    return SIGNS.get(op, op)


def _sum(a, op, b):
    """A sum as the tape's mono face writes it: its operator in ASCII."""
    return "%d %s %d" % (a, op, b)


def _value():
    try:
        return int(s.entry)
    except ValueError:
        return 0


def _show():
    """The display's lines: the entry, and the operand banked."""
    s.result = s.entry.replace("-", SIGNS["-"])
    s.expr = "%d %s" % (s.acc, _sign(s.op)) if s.op else ""


def _compute():
    if not s.op:
        return
    a, op, b = s.acc, s.op, _value()
    s.op = ""
    if op in "/%" and b == 0:            # division by zero: kid-friendly
        s.entry = "OOPS"
        return
    out = a + b if op == "+" else a - b if op == "-" else a * b if op == "*" else \
        a // b if op == "/" else a % b
    s.entry = str(out)
    rows = [{"n": r.n, "line": r.line} for r in s.tape][1 - TAPE_KEEP:]
    n = rows[-1]["n"] + 1 if rows else 0
    s.tape = rows + [{"n": n, "line": "%s = %s" % (_sum(a, op, b), s.entry)}]
    s.shown = s.taped = True


def press(key):
    """One key: the keypad's, or one the keyboard typed."""
    fresh = s.shown                      # a digit after a sum starts a new entry
    s.shown = False
    entry = s.entry
    if key == "C":
        s.entry, s.op = "0", ""
    elif key == "<":
        s.entry = entry[:-1] if len(entry) > 1 and entry != "OOPS" else "0"
    elif key.isdigit():
        if fresh or entry in ("0", "OOPS"):
            s.entry = key
        elif len(entry) < DIGITS:
            s.entry = entry + key
    elif key in "+-*/%":
        s.acc, s.op, s.entry = _value(), key, "0"
    elif key == "=":
        _compute()
    _show()


def typed(c):
    """A key the keyboard typed: its key, backspace the delete key."""
    press("<" if c in "\b\x7f" else c)


def opened():
    s.entry, s.acc, s.op, s.shown, s.tape, s.taped = "0", 0, "", False, [], False
    _show()
    ui.focus("key/5")


def _dot():
    pass


ui.app("Calc", icon="calc")
ui.hook("opened", opened)
ui.action("key", "Press", press, takes="arg")
ui.action("typed", "Type", typed, takes="char", chars="0123456789+-*/%=\b\x7f")
# Calc counts in whole numbers, so its point key is there and never activates.
ui.action("dot", ".", _dot, when="!whole", off="grey")


def calc_page():
    with ui.page(""):
        with ui.split("{@wide?row:col}", sizes="{@wide?2 3:2 5}", gap=8):
            with ui.group(""):
                ui.label("{expr}", tone="dim", align="end")
                ui.label("{result}", face="result", size="fit", align="end")
                ui.text_view("tape", follow=True, shown="taped")
            with ui.grid(4, 5, gap=6):
                for key in KEYS:
                    if key == "<":
                        ui.button("key", arg=key, icon="backspace", label="")
                    elif key == ".":
                        ui.button("dot", kind_of(key))
                    else:
                        ui.button("key", kind_of(key), arg=key, label=_sign(key), span=2 if key == "0" else 1)


CalcAppLayer = uitree_app.app_layer("calc", "Calc", calc_page)
