import gc
import sys

# Frozen modules first. Every import walks sys.path in order, and MicroPython's
# default (['', '.frozen', '/lib']) stats the flash root for each name before
# the frozen table -- a failed stat per probe, milliseconds a module on the
# T-Deck (#224). So a .py on the flash no longer overrides a frozen module of
# the same name (owner, 2026-10-05); one that is only on the flash still loads.
sys.path.remove(".frozen")
sys.path.insert(0, ".frozen")

print("Moybyte CoreS3 SE boot")
# The Faces Bottom3's bar keeps whatever it was last sent (the factory
# firmware leaves it lit): dark before anything else.
try:
    import moy_cores3
    moy_cores3.leds(b"")
except Exception as exc:  # noqa: BLE001 -- a bar that stays lit never stops the boot
    print("bar:", exc)
gc.collect()
