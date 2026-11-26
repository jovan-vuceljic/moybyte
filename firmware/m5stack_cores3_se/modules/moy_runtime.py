"""Moybyte CoreS3 SE device backend: the shared console on the M5Stack CoreS3 SE
with the Faces Bottom3 and the Faces Gamepad3.

The T-Deck's tier (320x240, one canvas, its panel pushed by the shared
native/moy_lcd) with a gamepad for its keys: the shared spine
(`device/desktop_spine.py`) owns the boot, the services and the hand-over to
the kernel's frame loop; what is here is this board's hardware. The rails,
the panel's reset and its light are native/moy_cores3's C, which moy_lcd's
bring-up calls; the Gamepad3 and the FT6336U are the kernel's input drivers;
the card shares the panel's SPI2, so the store is `device/bus_store.py`'s, the
T-Deck's.
"""

from mem_census import mark as _census
from desktop_spine import build_desktop
from bus_store import BusStore
from carts_data import CARTS_Z as CARTS
from device_canvas import SystemCanvas

_census("imports")

# The idle ladder's blank rung (the kernel's): the shared 5 minutes.
POWER_SAVE_MS = 300000          # 0 disables
# The inputs as the hints know them (Workstation.use_inputs): the Gamepad3
# writes "pad", in use from boot; the FT6336U is touch, under which the hints
# keep the pad's keys; a paired BLE keyboard is a desk keyboard.
INPUT_KINDS = (("pad", "pad"), ("touch", "touch"), ("ble", "keys"))
# The store's root without a card, the T-Deck's (its moy_runtime.py has why).
FLASH_CARTS_ROOT = "/moy/carts"
FLASH_UPDATE_DIR = "/moy/update"


class CoreS3Input:
    """Every input source on this board, the kernel's drivers: the Gamepad3
    and the BLE HID keyboard (the console's keyboard, as on the touch-only
    boards) at once, the touch behind the splash."""

    def __init__(self):
        import moy_input
        self.pad = moy_input.gamepad()
        self.ble_keyboard = moy_input.ble()
        self.touch = None

    def build(self, w, h):
        """The FT6336U, mapped onto the w x h system canvas."""
        import moy_input
        self.touch = moy_input.touch(w, h)
        return self.touch


def run_desktop(fps_cap=60):
    """Boot the shared console: launcher + carts, the Gamepad3 and the touch,
    carts on the card or internal flash, the clock from the BM8563."""
    import moy_cores3
    import moy_glass
    import moy_input
    import moy_lcd
    from battery import PmicBattery

    comp = moy_glass.BandedCompositor(moy_lcd, nfbs=2)
    canvas = SystemCanvas(comp)
    _census("panel")
    # The clock chip holds the time across power-off; NTP answers go back to it.
    if not moy_cores3.clock_restore():
        print("Moybyte CoreS3: the clock chip has no time")

    inp = moy_input.kernel()
    pads = CoreS3Input()
    store = BusStore(comp, CARTS, FLASH_CARTS_ROOT, FLASH_UPDATE_DIR)

    def _before_slim(ws):
        ws.with_sd = store.session
        store.ws = ws

    d = build_desktop("Moybyte CoreS3", "cores3", comp, canvas, comp.set_backlight, inp,
                      inputs=lambda: pads.build(canvas.w, canvas.h),
                      keyboard=pads.ble_keyboard, seed_carts=CARTS,
                      power_save_ms=POWER_SAVE_MS,
                      load_carts=store.load, with_sd=store.session,
                      before_slim=_before_slim,
                      input_kinds=INPUT_KINDS, fps_cap=fps_cap)
    d.ws.battery = PmicBattery(moy_cores3.pmic)
    return d.run(kick_at_tail=True)
