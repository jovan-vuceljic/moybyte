"""The CoreS3 SE's input hardware, EXECUTED: the Faces Gamepad3's driver
(native/moy_input/moy_pad3.c) and the FT6336U's (moy_touchdev.c's FT6X36
kind), driven through the host's binding (runtime/host/moy_input.py) over I2C
fakes; one `pass_()` is one pass of the input task and the table is the real
one, so a `held()` after `begin_frame` is what a cart would see.
"""

from runtime import moy_input as mi


class _Pad3:
    """The Gamepad3 at 0x08: its model at 0xD0, its keys at 0x00."""

    def __init__(self, states, model=0x03):
        self.states = list(states)
        self.model = model
        self.t = 1000

    def ms(self):
        return self.t

    def us(self):
        return self.t * 1000

    def sleep_ms(self, n):
        self.t += n

    def readfrom_mem(self, _a, reg, n, addrsize=8):
        if reg == 0xD0:
            return bytes([self.model])
        assert reg == 0x00
        return bytes([self.states.pop(0) if len(self.states) > 1 else self.states[0]])

    def writeto(self, _a, data):
        pass


def test_the_pads_byte_maps_onto_the_tables_buttons():
    """Active low, bit 0 up .. 7 Start: the browser gamepad's names."""
    assert mi.pad3_buttons(0xFF) == ()
    for bit, name in enumerate(("up", "down", "left", "right", "a", "b", "select", "start")):
        assert mi.pad3_buttons(0xFF & ~(1 << bit)) == (name,)
    assert set(mi.pad3_buttons(0x00)) == {"up", "down", "left", "right", "a", "b",
                                          "select", "start"}


def test_a_pass_holds_what_the_pad_holds_and_lets_go():
    table = mi.InputTable()
    pad = mi.Pad3Driver(table, _Pad3([0xFF & ~0x10 & ~0x08, 0xFF]))
    pad.probe()
    pad.pass_()
    table.begin_frame()
    assert table.held("a") and table.held("right") and not table.held("b")
    pad.pass_()
    table.begin_frame()
    assert not table.held("a") and not table.held("right")


def test_a_face_that_is_not_a_gamepad3_holds_nothing():
    table = mi.InputTable()
    pad = mi.Pad3Driver(table, _Pad3([0x00], model=0x01))     # a Calculator3
    pad.probe()
    pad.pass_()
    table.begin_frame()
    assert not table.held("a")


class _FT:
    """An FT6336U at 0x38: TD_STATUS and the first point at 0x02."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.t = 1000

    def ms(self):
        return self.t

    def us(self):
        return self.t * 1000

    def sleep_ms(self, n):
        self.t += n

    def readfrom_mem(self, _a, reg, n, addrsize=8):
        assert reg == 0x02
        f = self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]
        return bytes(f[:n])

    def writeto(self, _a, data):
        pass


def _ft(touches, x, y, event=2):
    return bytes([touches, (event << 6) | (x >> 8), x & 0xFF, y >> 8, y & 0xFF])


def test_the_ft6336_reports_a_point_in_the_panels_coordinates():
    t = mi.TouchDriver(_FT([_ft(1, 0, 0), _ft(1, 300, 200), _ft(0, 0, 0)]), mi.FT6X36,
                       320, 240, raw_w=320, raw_h=240)
    t.probe()
    assert t.available and t.addr == 0x38
    t.pass_()
    t.pass_()
    x, y, _edge = t.poll()
    assert (x, y) == (300, 200)


def _down(*names):
    bits = {"up": 0, "down": 1, "left": 2, "right": 3, "a": 4, "b": 5, "select": 6, "start": 7}
    raw = 0xFF
    for n in names:
        raw &= ~(1 << bits[n])
    return raw


def test_select_is_the_shift_for_x_y_and_the_tabs():
    """Two face buttons and no shoulders: Select+A is x, Select+B is y, and
    Select+left/right type the tab keys Q and E instead of moving."""
    assert set(mi.pad3_held(_down("select", "a"))) == {"select", "x"}
    assert set(mi.pad3_held(_down("select", "b"))) == {"select", "y"}
    assert set(mi.pad3_held(_down("select", "left"))) == {"select"}
    assert mi.pad3_typed(_down("select"), _down("select", "left")) == "q"
    assert mi.pad3_typed(_down("select"), _down("select", "right")) == "e"
    assert mi.pad3_typed(_down("select", "right"), _down("select", "right")) == ""
    assert mi.pad3_typed(0xFF, _down("left")) == ""
    assert set(mi.pad3_held(_down("select", "start"))) == {"select", "start"}


def test_a_game_keeps_its_directions_under_select_and_types_nothing():
    assert set(mi.pad3_held(_down("select", "left"), game=True)) == {"select", "left"}
    assert mi.pad3_typed(_down("select"), _down("select", "left"), quiet=True) == ""
