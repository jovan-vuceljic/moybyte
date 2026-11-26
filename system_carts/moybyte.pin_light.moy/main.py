# Pin Light -- tap the button, the board's LED changes (#9), and the LED bar
# lights in the colour A cycles where a console has one (the `leds` device
# API, runtime/system/dev_leds.py). The bar is this cart's while it runs and
# goes dark when it lets go or ends (the console's sweep).
#
# This cart is not "for the Zero". It is for ANY console that has pins, and it
# asks that question the only honest way: whether the verb has a name. The
# console injects pin_write/pin_read only when the thing serving this page
# answered the GPIO probe (runtime/run/cart_api.py), exactly like wifi and net --
# a verb that cannot work must not exist, because a pin_write that quietly does
# nothing is the worst answer a kid can get: the cart looks right and the light
# never moves.
#
# So: no pins, no crash. The cart says what is missing and stays usable.
try:
    pin_write
    HAS_PINS = True
except NameError:
    HAS_PINS = False

try:
    import moybyte
    BAR = moybyte.leds              # None where the console has no LEDs
except ImportError:                 # a host with no console OS
    BAR = None
COLOURS = (("green", 0x00FF00), ("red", 0xFF0000), ("blue", 0x0000FF), ("white", 0xFFFFFF))
colour = 0

# The XIAO's own little light is GPIO 21 and it is ACTIVE-LOW -- confirmed by
# blinking it on a real board, 2026-08-30. So 0 is ON. `cfg("pin")` makes that
# editable in the cards editor, because the next board's LED will be elsewhere.
on = False
flash = 0.0


def _pin():
    return int(cfg("pin", 21))


def _apply():
    # ACTIVE-LOW: 0 lights it.
    if HAS_PINS:
        pin_write(_pin(), 0 if on else 1)
    if BAR is not None:
        if on:
            BAR.fill(COLOURS[colour][1])
        else:
            BAR.close()


def _init():
    global on, flash, colour
    on = False
    flash = 0.0
    colour = 0
    _apply()


def _button():
    return (80, 96, 160, 64)


def _update(dt):
    global on, flash, colour
    if flash > 0:
        flash = max(0.0, flash - dt)
    if btnp("b") and BAR is not None:
        colour = (colour + 1) % len(COLOURS)
        _apply()
    hit = btnp("a")
    tp = touch()
    if tp is not None and tp[2]:
        x, y, w, h = _button()
        if x <= tp[0] < x + w and y <= tp[1] < y + h:
            hit = True
    if hit:
        on = not on
        flash = 0.12
        _apply()


# Colours go through col(): the draw verbs take a palette INDEX and mask it, so
# a bare name reaches them as a string and raises `unsupported operand & for
# str and int`. And the greys are spelled the British way -- `col()` answers an
# unknown name with white rather than failing, so `dark_gray` would have drawn
# silently wrong instead of crashing, which is worse.
def _draw():
    cls(col("dark_blue"))
    print("PIN LIGHT", 116, 24, col("white"))
    if not HAS_PINS and BAR is None:
        print("this console has no pins", 60, 104, col("orange"))
        print("open it from a board that does", 36, 120, col("light_grey"))
        return
    x, y, w, h = _button()
    face = (COLOURS[colour][0] if BAR is not None else "green") if on else "dark_grey"
    if flash > 0:
        face = "white"
    rect(x, y, w, h, col(face))
    rectb(x, y, w, h, col("white"))
    print("ON" if on else "OFF", x + (66 if on else 62), y + 28,
          col("black" if on else "white"))
    if HAS_PINS:
        # What the board reads back from the pin, not what this cart asked:
        # None until its first answer.
        lv = pin_read(_pin())
        said = "..." if lv is None else "LOW (lit)" if lv == 0 else "HIGH (dark)"
        print("pin %d reads %s" % (_pin(), said), 64, 184, col("light_grey"))
    if BAR is not None:
        print("B: the bar's colour", 88, 184 if not HAS_PINS else 194, col("light_grey"))
    print("tap it, or press A", 96, 210, col("dark_grey"))
