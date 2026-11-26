"""The `leds` device API's driver (native/moy_leds/moy_leds.h) on CPython, by
ctypes: the module `moy_leds` as the boards import it, name for name
(native/moy_leds/face.json has the list). The host has no LEDs: `sim(n)`
makes a bar of n and `shown` reads back what it shows. Every row is
runtime/host/moy_leds_face.py's, generated."""

import os

import native_build
from moy_leds_face import *  # noqa: F401,F403

_LEDS = os.path.join(native_build.ROOT, "native", "moy_leds")
_KERNEL = os.path.join(native_build.ROOT, "native", "moy_kernel")

PART = native_build.Part("leds", ("moy_leds.h", "moy_leds.c", "moy_leds_dev.c"), (_LEDS, _KERNEL))
