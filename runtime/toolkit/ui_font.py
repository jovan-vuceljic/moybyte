"""The print font: the font a canvas's `print` draws in now (native/moy_gfx/moy_text.h),
what it measures and draws, and the theme's faces it can be switched to.
A canvas's draw that prints text measures it here; ui_draw re-exports these
names.

    was = ui_font.print_face("ui")      # print in the theme's UI face
    w, h = ui_font.print_size(label, fs)
    ui_font.print_font(was)             # and back
"""

import moy_ui as _C


def print_font(fid=None):
    """Draw a canvas's `print` in font `fid` (0 for petme128): the font the
    shell's own text draws in. Answers the font it replaced, or None, and
    installs nothing, for a font that is not loaded. While a cart's code
    runs (`cart_text`) prints are petme128's and this names the font they
    come back to. With no `fid`, the font prints draw in now."""
    if fid is None:
        return _C.print_font()
    return _C.print_font(fid)


def print_width(s, scale=1):
    """The pixels `s` draws at `scale` through a canvas's `print` now: in the
    print font (`print_font`)."""
    if type(s) is not str:
        s = str(s)
    return _C.text_width(s, scale, _C.print_font())


def print_size(s, scale=1):
    """`(w, h)`: the pixels `s` covers through a canvas's `print` now, at
    the whole-number `scale` -- `h` is the print font's line."""
    if type(s) is not str:
        s = str(s)
    f = _C.print_font()
    info = _C.font_info(f)
    return (_C.text_width(s, scale, f), (info[2] if info else 8) * scale)


def print_symbols():
    """Whether the print font draws Latin-1 and the symbols `− × ÷ … ← → ↑ ↓ •`
    (a version 2 font, native/moy_gfx/moy_text.h); petme128 and a version 1
    font draw ASCII alone."""
    info = _C.font_info(_C.print_font())
    return info is not None and info[4] == 0


def face_draws(role, s):
    """Whether the theme installs a face for `role` (`font`) that draws
    every character of `s`: False in a pixel theme, which has none."""
    f = _C.font(role)[0]
    return f != 0 and _C.text_covers(s if type(s) is str else str(s), f)


def print_face(role):
    """A canvas's `print` (and `print_size`) draw in the theme's `role` face
    (`font`): answers the font it replaced, which `print_font` puts back, or
    None, changing nothing, where the theme installs no face for `role` (a
    pixel theme, and a cart's run, print in their print font)."""
    f = _C.font(role)[0]
    if f == 0:
        return None
    return _C.print_font(f)
