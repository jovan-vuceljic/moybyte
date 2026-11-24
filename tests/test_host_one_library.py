"""The host's native modules are ONE loaded library, as a board's are one image
(runtime/host/host_native.py): the shell's `moy_ui`, a Lua run and a compiled run
read the same theme, depth, fonts and cart-text boundary.
"""

import ctypes
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _addr(lib, name):
    return ctypes.cast(getattr(lib, name), ctypes.c_void_p).value


def test_every_host_binding_loads_the_one_library():
    from runtime import (gfx_binding, glass_binding, host_native, lua_binding,
                         moy_input, moy_loop, moy_play, net_binding)
    from runtime import native_parts as spike
    path = host_native.build()
    assert path is not None
    libs = {"gfx": gfx_binding._lib(), "glass": glass_binding._lib(),
            "lua": lua_binding._lib(), "input": moy_input._lib(),
            "loop": moy_loop._lib(), "play": moy_play._lib(), "net": net_binding._lib()}
    for comp in (spike.SPINE, spike.FS, spike.INDEX):
        assert spike.host_library("c", False, comp) == path, comp.name
    want = _addr(libs["glass"], "moy_ui_cart_text")
    for name, lib in libs.items():
        assert lib._name == path, name
        assert _addr(lib, "moy_ui_cart_text") == want, name


def test_the_shells_moy_ui_state_is_the_lua_runs():
    """The boundary the Player sets through the shell's module is the one the
    library a Lua run draws in reads (moy_ui_cart_text answers what it was)."""
    from runtime import lua_binding
    from runtime import moy_ui_binding
    ui = moy_ui_binding.binding()
    lib = lua_binding._lib()
    lib.moy_ui_cart_text.argtypes = [ctypes.c_int]
    lib.moy_ui_cart_text.restype = ctypes.c_int
    was = ui.cart_text(True)
    try:
        assert lib.moy_ui_cart_text(1) == 1, "the run's library saw the shell's boundary"
        ui.cart_text(False)
        assert lib.moy_ui_cart_text(0) == 0
    finally:
        ui.cart_text(was)
