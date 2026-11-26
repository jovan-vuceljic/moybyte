"""Browser input decode: the batch a browser event stream ships becomes
console input.

Transport-shaped, not raster-shaped: both the wasm head and the plan's 3.4
sync/controller RPC speak this same `{"events":[...]}` format, so the decode
is its own module with no draw path beside it.

The edge cases it carries: the hover-without-button rule and the held-key
latch that stops browser autorepeat flapping key() at 60fps. Backspace is a
plain typed 0x08; the console's key is the `super` event.
"""

import json

from moy_input import InputTable

# The console's button set, as the wire names them: the board's table, all
# sixteen, since a gamepad held at the page presses X, Y, Select and Start
# as a board's does.
BUTTON_NAMES = InputTable.BUTTONS
# The input source a page's on-screen gamepad writes (a hold's "src"); every
# other hold is the page keyboard's, the table's "local".
PAD_SOURCE = "pad"
# The source a gamepad held at the browser writes (the Gamepad API): it is
# an input while one is connected (the `gamepad` event).
GAMEPAD_SOURCE = "gamepad"
PAD_SOURCES = (PAD_SOURCE, GAMEPAD_SOURCE)


def apply_ws_text(payload, apply):
    """Decode one inbound WS text payload ({"events":[...]}) and feed the event list
    to `apply` -- the ONE input-decode path every WS consumer shares (the wasm
    head's worker pump today; the 3.4 controller role rides the same format), so
    the wire can't drift. A malformed message just yields no input (never raises)."""
    try:
        data = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        obj = json.loads(data)
        events = obj.get("events", []) if isinstance(obj, dict) else obj
        if isinstance(events, list):
            apply(events)
    except Exception:  # noqa: BLE001 -- a bad message just yields no input
        pass


def frame_cut(events):
    """How many of `events`, in order, one frame takes. The pointer is read
    once a frame, so a frame takes at most one change of it: a press, the
    held pointer's moves, or the release. A slow frame lets a whole gesture
    reach the next one in one batch, and taking it whole would lose what
    lies between -- a double click's second press merges into the first, a
    drag's last place is never seen held -- so the frame stops before a
    second press, before a move after its press (the press keeps its own
    place), and before a release after a move; the rest waits for the next
    frame. A press and its release together stay one frame: a click. A held
    button is a level the frame reads, so the frame also stops before a
    button's release whose press it took: the press is seen."""
    pressed = moved = False
    downs = None
    i = 0
    for ev in events:
        t = ev.get("type") if isinstance(ev, dict) else None
        if t == "down":
            if pressed:
                return i
            pressed = True
        elif t == "move":
            if pressed:
                return i
            moved = True
        elif t == "up" and moved:
            return i
        elif t == "hold":
            k = (ev.get("name"), ev.get("src"))
            if ev.get("down"):
                downs = [k] if downs is None else downs + [k]
            elif downs is not None and k in downs:
                return i
        i += 1
    return i


def apply_events(events, input, pointer, on_press=None, on_pan=None,
                 on_key=None, on_esc=None, on_hold=None, on_key_hold=None,
                 on_super=None, on_full=None, on_key_down=None, on_key_up=None,
                 on_mods=None, on_wheel=None, on_middle=None, on_gamepad=None,
                 on_paste=None, on_glass=None, on_page=None):
    """Inject a batch of browser events into an InputState + Pointer. Each event is fully
    guarded (a malformed one is skipped, never raised) so a buggy client can't crash the loop.

      {"type":"down","x":..,"y":..}  -> pointer tap (place + click + down)
      {"type":"move","x":..,"y":..}  -> pointer drag (place, down, no tap)
      {"type":"up"}                  -> release (pointer up)
      {"type":"pan","dx":..,"dy":..} -> trackball nudge (on_pan)
      {"type":"press","name":..}     -> one-shot button press (on_press)
      {"type":"hold","name":..,"down":bool} -> held button (on_hold, else input.set_button)
      {"type":"hold",...,"src":"pad"} -> the same from the page's on-screen
                                        gamepad, written to the "pad" source;
                                        "src":"gamepad" from a gamepad held at
                                        the browser, to that source
      {"type":"kd","code":..,"mods":..} -> a desk keyboard's key down: its
                                        code and modifiers (on_key_down)
      {"type":"kd",...,"rep":1}      -> the browser's repeat of a key held
                                        (on_key_down's `repeat`)
      {"type":"ku","code":..,"mods":..} -> ...and up (on_key_up)
      {"type":"mods","mods":..}      -> the modifiers it holds now (on_mods)
      {"type":"mods",...,"lost":1}   -> ...let go as the page lost the
                                        keyboard (on_mods' `tap` False)
      {"type":"wheel","dx":..,"dy":..,"mods":..} -> wheel notches (on_wheel)
      {"type":"mdown"|"mup","x":..,"y":..} -> the middle button (on_middle)
      a "down" with "mods" says the modifiers held as it went down
      {"type":"key","code":<ascii>}  -> typed key (on_key)
      {"type":"key",...,"src":"gamepad"} -> a key the pad types (its
                                        shoulders' Q and E) into that source;
                                        none while a field takes text or a
                                        game owns the keys
      {"type":"gamepad","on":bool}   -> a gamepad connected, or the last one
                                        gone (on_gamepad)
      {"type":"esc"}                 -> Esc (on_esc): a menu closes, a page
                                        steps back, a fullscreen game pauses
      {"type":"full"}                -> F11 (on_full): a desk window full
                                        screen, and back
      {"type":"super"}               -> the system key (on_super): the system
                                        menu, or the pause menu in play
      {"type":"glass","w","h","zoom","zooms"} -> the page's viewport moved
                                        (on_glass): the glass resized, the
                                        UI scale and the ones it offers
      {"type":"page",..}             -> the page's word (on_page): full
                                        screen, where it keeps the carts,
                                        what it has to say (page_link.py)
      {"type":"paste","text":..}     -> the browser's clipboard pasted
                                        (on_paste): the text whole; with no
                                        text, the console's own Paste
    """
    for ev in events:
        try:
            t = ev.get("type")
            if t == "down":
                if isinstance(ev.get("mods"), int) and on_mods is not None:
                    on_mods(ev["mods"] & 0xFF)
                pointer.place(int(ev.get("x", 0)), int(ev.get("y", 0)))
                pointer.down = True
                pointer.click = True
            elif t == "move":
                pointer.place(int(ev.get("x", 0)), int(ev.get("y", 0)))
                pointer.down = True
            elif t == "hover":
                # POINTER POSITION WITHOUT A BUTTON: the shell has real hover
                # feedback (the desk icon highlight `_lhover`, the cards grid's
                # msel), so a browser mouse reports its position between
                # clicks too, as ConsoleDriver.hover does for the sim.
                # Deliberately NOT "move": that one asserts `down`, which would
                # fake a drag out of an idle mouse (drag-scrolling grids, moving
                # windows).
                pointer.place(int(ev.get("x", 0)), int(ev.get("y", 0)))
                pointer.hovers = True   # a browser mouse has a position always
            elif t == "up":
                pointer.down = False
            elif t == "pan":
                if on_pan is not None:
                    on_pan(int(ev.get("dx", 0)), int(ev.get("dy", 0)))
            elif t == "press":
                name = ev.get("name")
                if name in BUTTON_NAMES and on_press is not None:
                    on_press(name)
            elif t == "hold":
                name = ev.get("name")
                if name in BUTTON_NAMES:
                    # Route to on_hold when wired (the device's keyboard.poll clears buttons,
                    # so a hold must be re-asserted AFTER the poll); else a direct set.
                    # A hold from a gamepad names its source, so the pad,
                    # not the keyboard, becomes the input in use.
                    down = bool(ev.get("down"))
                    src = ev.get("src")
                    src = src if src in PAD_SOURCES else None
                    if on_hold is not None:
                        if src is None:
                            on_hold(name, down)
                        else:
                            on_hold(name, down, src)
                    elif src is not None and hasattr(input, "source"):
                        input.source(src).set_button(name, down)
                    else:
                        input.set_button(name, down)
            elif t == "key":
                code = ev.get("code")
                src = ev.get("src")
                if not (isinstance(code, int) and 0 <= code <= 0xFF):
                    pass
                elif src in PAD_SOURCES:
                    if not (getattr(input, "text_mode", False)
                            or getattr(input, "cart_keys", False)):
                        input.source(src).key(code)
                elif on_key is not None:
                    on_key(code)
            elif t == "gamepad":
                if on_gamepad is not None:
                    on_gamepad(bool(ev.get("on")))
            elif t == "kd" or t == "ku":
                code = ev.get("code")
                mods = ev.get("mods", 0)
                fn = on_key_down if t == "kd" else on_key_up
                if (isinstance(code, int) and 0 < code <= 0xFFFF and isinstance(mods, int)
                        and fn is not None):
                    if t == "kd" and ev.get("rep"):
                        fn(code, mods & 0xFF, True)
                    else:
                        fn(code, mods & 0xFF)
            elif t == "wheel":
                if on_wheel is not None:
                    on_wheel(int(ev.get("dx", 0)), int(ev.get("dy", 0)),
                             int(ev.get("mods", 0)) & 0xFF)
            elif t == "mdown" or t == "mup":
                if on_middle is not None:
                    on_middle(int(ev.get("x", 0)), int(ev.get("y", 0)), t == "mdown")
            elif t == "mods":
                mods = ev.get("mods", 0)
                if isinstance(mods, int) and on_mods is not None:
                    if ev.get("lost"):
                        on_mods(mods & 0xFF, False)
                    else:
                        on_mods(mods & 0xFF)
            elif t == "khold":
                # A physically HELD printable key (browser keydown/keyup edges):
                # outside text mode the driver latches it so key() streams every
                # frame, matching the device raw matrix -- browser autorepeat is
                # ~30Hz and made key() flap code/0/code at 60fps. Text mode
                # ignores the down (typing is the queued-byte path) but always
                # takes the release, so leaving text mode can't strand a latch.
                down = bool(ev.get("down"))
                if down and getattr(input, "text_mode", False):
                    pass
                elif on_key_hold is not None:
                    on_key_hold(ev.get("code"), down)
            elif t == "esc":
                if on_esc is not None:
                    on_esc()
            elif t == "super":
                if on_super is not None:
                    on_super()
            elif t == "full":
                if on_full is not None:
                    on_full()
            elif t == "glass":
                if on_glass is not None:
                    on_glass(int(ev["w"]), int(ev["h"]), int(ev.get("zoom", 1)),
                             ev.get("zooms") or (1,))
            elif t == "page":
                if on_page is not None:
                    on_page(ev)
            elif t == "paste":
                text = ev.get("text", "")
                if isinstance(text, str) and on_paste is not None:
                    on_paste(text)
        except Exception:  # noqa: BLE001 -- one bad event must not drop the batch
            pass


def effective_input_kinds(ws):
    """The manifest input hint (#42 Thread 3), but only while the RUNNING cart
    actually owns the keyboard (wm.keys_to_cart: fullscreen play / the focused
    game window). Any system surface -- Editor, launcher, Settings -- needs
    the FULL control set: the Code tab is exactly where the phone's soft-
    keyboard summon matters, and gating it by the open cart's hint hid the
    ⌨ button the moment a buttons-only game was opened for CHANGE. Shared by
    both web transports so host and device can't drift."""
    try:
        if ws is not None and ws.wm.keys_to_cart():
            cart = getattr(ws, "cart", None)
            return cart.get("input") if cart else None
    except Exception:  # noqa: BLE001 -- a hint failure just shows every control
        pass
    return None