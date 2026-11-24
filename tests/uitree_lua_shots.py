"""Moy Mesh's thread and Radio screens as UI tree fixtures over a stand-in
radio (tests/fixtures/uitree_lua/mesh_thread.part, mesh_radio.part), staged
on the host console and driven by one input script, a shot at each named
step. tests/test_uitree_lua.py pins the shots by their hashes; run this by
hand to see them:

    .venv/bin/python tests/uitree_lua_shots.py OUT_DIR [screen ...]
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path[:0] = [ROOT, HERE]

FIX = os.path.join(HERE, "fixtures", "uitree_lua")


def fixture(name):
    """A fixture's folder: NAME.moy is a whole cart; NAME.part is a cart's
    half, staged with files from elsewhere (SCREENS), which no scan of
    tests/**/*.moy may take for a cart."""
    whole = os.path.join(FIX, name + ".moy")
    return whole if os.path.isdir(whole) else os.path.join(FIX, name + ".part")

MESH = os.path.join(HERE, "fixtures", "apps", "moymesh.moy")
# A frame is a whole number of ms. The host kernel loop's driver clock is one
# microsecond count for the process, which the loop reads in whole ms, so at
# 1/30 s a frame's ms step is 33 or 34 by where earlier runs left that count,
# and a glide integrated over those steps ended elsewhere every third run.
DT = 0.033
CLOCK = 1763553600 + 8 * 3600 + 20 * 60

# a size: the console's (320x240 full screen) and the desk's (a 1024x600 window)
SIZES = {"320": dict(sys_size=None, font_scale=1, windowed=False),
         "1024": dict(sys_size=(1024, 600), font_scale=2, windowed=True)}

# a screen: (its cart, its files from elsewhere, script). A step is a key
# ("up", "a"), "type:TEXT", "enter", "key:CODE", "wait:N", "tap:X,Y",
# "drag:X0,Y0,X1,Y1" or "shot:NAME"; DESK moves a 320 point into the desk
# window.
THREAD_SCRIPT = ["shot:thread", "tap:150,206", "wait:2", "shot:field", "type:hello mesh", "shot:typed",
                 "enter", "wait:4", "shot:sent", "wait:40", "shot:failed", "up", "wait:20", "shot:up"] + \
                ["drag:160,70,160,200"] * 4 + ["wait:30", "shot:top", "a", "wait:20", "shot:details"]
RADIO_SCRIPT = ["shot:radio", "down", "wait:10", "shot:region_link", "a", "wait:10", "shot:region",
                "down", "a", "wait:10", "shot:chosen", "b", "wait:10", "shot:back"]
SCREENS = {
    "radio": ("mesh_radio", [(MESH, "mesh.lua"), ("mesh_thread", "data.lua")], RADIO_SCRIPT),
    "thread": ("mesh_thread", [(MESH, "mesh.lua")], THREAD_SCRIPT),
}
DESK = {"drag:160,70,160,200": "drag:700,150,700,480", "tap:150,206": "tap:650,545"}


def _stage(carts, name, extra):
    dst = os.path.join(carts, name + ".moy")
    shutil.copytree(fixture(name), dst)
    for where, f in extra:
        src = where if os.path.isabs(where) else fixture(where)
        shutil.copy(os.path.join(src, f), dst)
    import json
    with open(os.path.join(dst, "manifest.json")) as fh:
        return json.load(fh)["title"]


def play(name, extra, script, size, launch=None):
    """Run cart `name` at `size` through `script`: {shot name: RGB bytes},
    the run's cart errors and its log lines."""
    from runtime import host_app
    from ws_helpers import open_cart, quiesce
    from runtime.host import moy_log
    root = tempfile.mkdtemp(prefix="uitree_lua_")
    carts = os.path.join(root, "carts")
    host_app.moy_carts.ensure_dirs(carts)
    title = _stage(carts, name, extra)
    ws = host_app.build_workstation(carts, **SIZES[size])
    # the bar's clock reads one minute, so a run crossing a minute matches
    wcs = {getattr(m, "_wc", None) for n, m in list(sys.modules.items()) if n.endswith("bar_layer")} - {None}
    kept = [(wc, wc.localtime) for wc in wcs]
    for wc, lt in kept:
        wc.localtime = lambda t=None, _lt=lt: _lt(CLOCK if t is None else t)
    ws.look.set_theme("moy", persist=False, variant="dark")
    ws.pointer.visible = False
    seq0 = moy_log.next()
    open_cart(ws, title)
    drv = host_app.ConsoleDriver(ws)
    shots, errors = {}, []

    def frame():
        quiesce(ws)
        ws.mark_dirty()
        drv.frame(DT)

    for _ in range(4):
        frame()
    for step in script:
        if size == "1024":
            step = DESK.get(step, step)
        kind, _, arg = step.partition(":")
        if kind == "shot":
            shots[arg] = bytes(drv.rgb888())
            continue
        if kind == "wait":
            for _ in range(int(arg)):
                frame()
            continue
        if kind == "type":
            for ch in arg:
                drv.type_char(ord(ch))
                frame()
            continue
        if kind == "drag":
            x0, y0, x1, y1 = (int(v) for v in arg.split(","))
            drv.touch(x0, y0)
            frame()
            for k in range(1, 5):
                drv.touch_drag(x0 + (x1 - x0) * k // 4, y0 + (y1 - y0) * k // 4)
                frame()
            drv.touch_up()
        elif kind == "tap":
            x, y = (int(v) for v in arg.split(","))
            drv.click(x, y)
        elif kind == "key":
            drv.key_down(int(arg))
            frame()
            drv.key_up(int(arg))
        elif kind == "enter":
            drv.type_char(13)
        else:
            drv.press(kind)
        frame()
        frame()
        err = ws.run.player.cart_error if ws.run and ws.run.player else None
        if err and err not in errors:
            errors.append(err)
    cv = drv.current_canvas()
    logs = [r[4] for r in moy_log.read(seq0, 4000)]
    ws.home.go_home()
    ws.spine.exit()
    for wc, lt in kept:
        wc.localtime = lt
    shutil.rmtree(root, ignore_errors=True)
    return (cv.w, cv.h), shots, errors, logs


def main():
    from PIL import Image
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for name in sys.argv[2:] or sorted(SCREENS):
        cart, extra, script = SCREENS[name]
        for size in SIZES:
            wh, shots, errors, _logs = play(cart, extra, script, size)
            for e in errors:
                print("  ERROR", e)
            for shot, img in shots.items():
                Image.frombytes("RGB", wh, img).save(os.path.join(out, "%s_%s_%s.png" % (name, size, shot)))


if __name__ == "__main__":
    main()
