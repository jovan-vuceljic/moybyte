# Map (grep -n a name to jump there):
#   SceneLayout          the scene editor's geometry: the handheld page's or a desk pane's
#   SceneEditorUI        the Scene page's host: the world view, its gestures and keys
#   SceneEditorUI.build  build the SceneEditor over a scene
#   SceneEditorUI.save   persist the edited scene
"""The scene (placed-actor) placement editor's UI (#85 Stage 2): a panned
WYSIWYG view of the WORLD -- the tilemap as the backdrop, the fixed 320x240
game viewport as a frame, every placed actor as its sprite -- and the
gestures over it. The page round it is `runtime/editors/editor_scene.py`'s,
on the handheld the picked actor's props or the stamps, the tools and the
foot; in a desk Editor's Scene pane the view fills the pane, the stamps are
the Stamps pane's, the props the Actor pane's and the tools the pane
header's (`runtime/editors/editor_desk.py`). `SceneEditorUI` hosts the page
(`view_host.ViewHost`): the editor's state into the page's, the view, the
actor's sprite and the stamps drawn in its canvases with their presses and
keys.

The map editor's gesture grammar, over objects:

  * tap empty world                   -> place ONE actor there (selects it)
  * tap an existing actor             -> select it (topmost wins)
  * drag an actor                     -> move it (live, one undo step)
  * drag empty world                  -> pan the view (map-editor gesture)

Coordinates are WORLD-SPACE pixels (#85 Section 7): the editor shows a viewport
frame at world (0,0)-(320,240) over a pannable world, so screen-space carts just
never pan. Zoom only goes IN (1x/2x/3x -- sprites only ever UPscale, the map
editor's rule). Every committed gesture is (a) one in-editor undo step and (b)
synced into the LIVE widgets.Scenes via Scenes.put, so PLAY without an explicit
SAVE runs the freshest placement -- the exact live-edit semantics the shared
TileMap gives the map tab. SAVE persists through Project.commit_scene (atomic
write + the durable undo journal, Stage 1). The editor manages the cart's
DEFAULT scene (multi-scene UX is a deferred follow-up, #85 decision log 4)."""

import ui_font as _ui_font
import ui_draw as _ui_draw
from widgets import rect_in as _in   # one hit-test

import editor_scene
from editors_scene import SceneEditor
from layout_base import BASE_W as _BASE_W, BASE_H as _BASE_H
from view_host import ViewHost, ViewLayout, BRUSH_PAD, checker

# The arrows pan an empty pick this many world pixels.
_PAN_STEP = 8


class SceneLayout(ViewLayout):
    """The scene editor's geometry (`view_host.ViewLayout`): its zooms are
    SCALES, world px to view px; 1x shows the most world and 2x and 3x zoom
    IN for fine placement (sprites only ever upscale). `roomy`: the
    column holds the picked actor's verbs as a menu under its tag and
    place (else they stand as a row of their icons)."""

    ZOOMS = (1, 2, 3)

    def __init__(self, w=_BASE_W, h=_BASE_H, font_scale=1, chrome_scale=None):
        ViewLayout.__init__(self, w, h, font_scale, chrome_scale=chrome_scale)
        item = 48 if self.desk else 20 * self.fs
        self.roomy = self.view_h >= (48 if self.desk else 50 * self.fs) + 5 * item


class SceneEditorUI(ViewHost):
    """The placement editor's UI: the Scene page's host (editor_scene.py)
    -- the world view, the actor's sprite and the stamps its canvases,
    their gestures and keys, and the page's actions over the SceneEditor.
    One instance lives on Workstation (`self.scene_ui`), built at its first
    use; `ws.scene_ui.build()` is called lazily from set_menu_view("scene")
    the first time a cart's scene tab is opened -- exactly the MapEditorUI
    lifecycle."""

    def __init__(self, ws, names):
        ViewHost.__init__(self, ws, names, "scene", editor_scene.scene_page, SceneLayout)
        self.sceneedit = None          # SceneEditor while menu_view == "scene"
        self.scene_name = None         # the DEFAULT scene this editor manages
        self.scene_zoom = 0            # index into layout.zooms (0 = 1x)
        self.tool = "pick"             # the handheld's foot tool: pick | stamp (a tap places)
        self._pop = None               # "tag" or "stamp" while its popover is open
        self._mode = None              # open gesture: "move" (an actor) or "pan"
        self._grab = (0, 0)            # world offset actor-origin - press (a drag
                                       # holds the sprite where the finger picked it)

    # -- the page ------------------------------------------------------------

    def _sync(self):
        """The editor's state the page shows, handed to its `sync` hook
        where it moved."""
        lay = self.layout
        se = self.sceneedit
        u = lay.unit
        first, last, words = self.pager()
        if se is None or self.ws.run.project.sheet is None:
            vals = (True, lay.pane, "pick", "nothing", "none", False, "", "", first, last, words,
                    "", "", "", lay.view_w, lay.brushes_h, lay.lines, lay.roomy, lay.pitch, BRUSH_PAD,
                    150 * u)
        else:
            r = se.selected()
            side = "stamps" if self.tool == "stamp" else "nothing" if r is None else "actor"
            vals = (False, lay.pane, self.tool, side, self._pop or "none", bool(se.snap),
                    "" if r is None else str(r.get("tag") or "thing"),
                    "" if r is None else "x %d  y %d" % (r.get("x", 0), r.get("y", 0)),
                    first, last, words, str(se.stamp_tag or "thing"), self.zoom_word(),
                    str(self.scene_name or ""), lay.view_w, lay.brushes_h, lay.lines, lay.roomy,
                    lay.pitch, BRUSH_PAD, 150 * u)
        self.push(vals)

    def zoom_word(self):
        x = "\u00d7" if _ui_font.print_symbols() else "x"
        return "%d%s" % (self._sv_metrics()[2], x)

    def set_tool(self, tool):
        """The foot's tool: "pick" or "stamp" (a tap on empty world places)."""
        self.tool = tool
        self._due = "home"             # the keys go back to the view
        self.ws.mark_dirty()

    def act(self, verb):
        """One of the page's actions: a tool, Snap, the zoom, an actor verb
        on the picked actor, the stamps' page before or after, a tag's
        popover opened, or the popover closed."""
        se = self.sceneedit
        if se is None:
            return
        changed = False
        if verb in ("pick", "stamp"):
            self.set_tool(verb)
        elif verb == "snap":
            se.snap = not se.snap
        elif verb == "zoom":
            self.cycle_zoom()
        elif verb == "tag":
            r = se.selected()
            self.open_tag("tag", r.get("tag", "") if r is not None else "")
        elif verb == "stamp_tag":
            self.open_tag("stamp", se.stamp_tag or "")
        elif verb == "flip":
            changed = se.toggle_flip()
        elif verb == "front":
            changed = se.front_sel()
        elif verb == "back":
            changed = se.back_sel()
        elif verb == "remove":
            changed = se.delete_sel()
        elif verb == "sprev":
            self.page_step(-1)
        elif verb == "snext":
            self.page_step(1)
        elif verb == "close":
            self.close_pop()
        if changed:
            self._sync_live()
        self.ws.mark_dirty()

    def open_tag(self, which, text):
        """Type the picked actor's tag (`which` "tag") or the stamp's
        ("stamp") in a popover, its field holding the keys."""
        self._pop = which
        self._sync()
        self.run("typing", str(text))
        self.ws.mark_dirty()

    def tagged(self, text):
        """The typed tag, given to the actor or the stamp."""
        se = self.sceneedit
        if se is not None and text:
            if self._pop == "tag":
                if se.set_tag(text):
                    self._sync_live()
            else:
                se.stamp_tag = text[:se.TAG_MAX]
        self.close_pop()

    def popover(self):
        return self._pop is not None

    def close_pop(self):
        if self._pop is not None:
            self._pop = None
            self._due = "home"
            self.ws.mark_dirty()

    def build(self):
        """Build the SceneEditor over the open cart's DEFAULT scene (the
        manifest's element 0; a cart with none starts an empty "main"). Called
        from Text.set_menu_view("scene")."""
        ws = self.ws
        if self.sceneedit is not None or ws.run.project.sheet is None:
            return
        scenes = ws.run.project.scenes
        names = getattr(scenes, "names", None) if scenes is not None else None
        self.scene_name = names[0] if names else "main"
        raw = scenes.raw(self.scene_name) if scenes is not None else None
        self.sceneedit = SceneEditor(raw or "")

    def reset(self):
        """Drop the active editor (a stale one must never leak into an unrelated
        cart). Called from Workstation.open()/go_home()/_reload_after_walk."""
        self.sceneedit = None
        self.scene_name = None

    def on_open(self):
        """Reset gesture/zoom/props state -- called from EditorApp.open_scene
        before set_menu_view("scene") (re)builds the editor."""
        self.scene_zoom = 0
        self.brush_page = 0
        self._press = None
        self._mode = None
        self._panning = False
        self._drag = None
        self._pop = None

    # -- live sync + persistence ---------------------------------------------

    def _sync_live(self):
        """Push the edited rows into the LIVE widgets.Scenes so the next PLAY's
        _init sees them (the run copies them, `ProjectStore.play_world`). Called after
        every committed gesture and after undo/redo."""
        se = self.sceneedit
        scenes = self.ws.run.project.scenes
        if se is None or scenes is None or self.scene_name is None:
            return
        scenes.put(self.scene_name, se.serialize())

    def save(self):
        """SAVE: persist the edited scene through Project.commit_scene (atomic
        write + manifest registration + the durable undo journal, Stage 1).
        The ws entry point Saves.save_scene forwards here."""
        ws = self.ws
        se = self.sceneedit
        if se is None or self.scene_name is None:
            return
        self._sync_live()                       # the store text == the live text
        if ws.run.project.commit_scene(self.scene_name, se.serialize()):
            se.dirty = False

    # -- view metrics ---------------------------------------------------------

    def _sv_metrics(self):
        """The LIVE view metrics: (x0, y0, scale, view_w, view_h). `scale` is
        view px per world px at the current zoom; view_w/h are the WORLD span
        (px) the view shows, in the rect the page placed it at."""
        lay = self.layout
        idx = self.scene_zoom
        if idx < 0:
            idx = 0
        elif idx >= len(lay.zooms):
            idx = len(lay.zooms) - 1
        scale = lay.zooms[idx]
        r = self._view_r
        if r is None:
            r = (lay.view_x0, lay.view_y0, lay.view_w, lay.view_h)
        return (r[0], r[1], scale, r[2] // scale, r[3] // scale)

    def _sv_area(self):
        """The current view rectangle (x, y, w, h) for _in() hit-tests."""
        x0, y0, scale, vw, vh = self._sv_metrics()
        return (x0, y0, vw * scale, vh * scale)

    def _world_at(self, px, py):
        """World coords under pointer (px, py), or None outside the view."""
        se = self.sceneedit
        if se is None or not _in(px, py, self._sv_area()):
            return None
        x0, y0, scale, vw, vh = self._sv_metrics()
        return (se.cam_x + (px - x0) // scale, se.cam_y + (py - y0) // scale)

    def clamp_cam(self):
        """Clamp the camera so the view never scrolls far past the world's
        content extents (viewport + tilemap + actors, editors_scene.world_size)."""
        se = self.sceneedit
        if se is None:
            return
        x0, y0, scale, vw, vh = self._sv_metrics()
        ww, wh = se.world_size(self.ws.run.project.tilemap)
        se.cam_x = max(0, min(max(0, ww - vw), se.cam_x))
        se.cam_y = max(0, min(max(0, wh - vh), se.cam_y))

    def wheel_zoom(self, px, py, d):
        """A wheel notch at (px, py): the next zoom in (`d` < 0) or out, a
        whole step, the world point under the pointer kept under it."""
        se = self.sceneedit
        if se is None:
            return
        z = max(0, min(len(self.layout.zooms) - 1, self.scene_zoom - d))
        if z == self.scene_zoom:
            return
        x0, y0, scale, _w, _h = self._sv_metrics()
        wx = se.cam_x + (px - x0) // scale
        wy = se.cam_y + (py - y0) // scale
        self.scene_zoom = z
        x0, y0, scale, _w, _h = self._sv_metrics()
        se.cam_x = wx - (px - x0) // scale
        se.cam_y = wy - (py - y0) // scale
        self.clamp_cam()

    def cycle_zoom(self):
        self.scene_zoom = (self.scene_zoom + 1) % len(self.layout.zooms)
        self.clamp_cam()

    def step(self):
        """View pixels a world pixel."""
        return self._sv_metrics()[2]

    def pan(self, dx, dy):
        """Pan the camera by (dx, dy) world px, clamped to the world."""
        se = self.sceneedit
        if se is None:
            return
        se.cam_x += dx
        se.cam_y += dy
        self.clamp_cam()

    # -- the view's keys and gestures ------------------------------------------

    def ready(self):
        return self.sceneedit is not None

    def brush(self):
        return self.sceneedit.n

    def set_brush(self, t):
        self.sceneedit.set_brush(t)

    def view_top(self):
        se = self.sceneedit
        return se is not None and se.selected() is None and se.cam_y <= 0

    def arrows(self, dx, dy):
        """The view's arrows: they nudge the picked actor, else pan the
        world. Whether they moved it."""
        se = self.sceneedit
        if se.selected() is not None:
            if not se.nudge_sel(dx, dy):
                return False
            self._sync_live()
            self.clamp_cam()
            return True
        was = (se.cam_x, se.cam_y)
        self.pan(dx * _PAN_STEP, dy * _PAN_STEP)
        return (se.cam_x, se.cam_y) != was

    def press(self, px, py):
        """A press in the view: an actor under it is picked and the press
        MOVES it; on empty world the press PANS (a release inside the tap's
        dead zone places there instead, under the stamp tool)."""
        se = self.sceneedit
        w = self._world_at(px, py)
        if se is None or w is None:
            self._mode = None
            return
        if se.select_at(w[0], w[1]) is not None:
            self._mode = "move"
            r = se.selected()
            self._grab = (r["x"] - w[0], r["y"] - w[1])
            se.begin_edit()
        else:
            self._mode = "pan"

    def drag(self, px, py):
        """Held-drag: a MOVE tracks the actor under the finger (live,
        snapped); a PAN past the dead zone scrolls the camera by the drag
        (content follows the finger, the map editor's #37 rule)."""
        se = self.sceneedit
        if se is None:
            return
        if self._mode == "move":
            x0, y0, scale, vw, vh = self._sv_metrics()
            se.move_sel(se.cam_x + (px - x0) // scale + self._grab[0],
                        se.cam_y + (py - y0) // scale + self._grab[1])
        elif self._mode == "pan":
            self.pan_drag(px, py, self.step())

    def release(self, px, py):
        """Pointer up: a MOVE commits (one undo step iff it moved); a PAN
        that never crossed the dead zone was a TAP on empty world, which
        under the stamp tool (and in a desk's pane) PLACES an actor there."""
        se = self.sceneedit
        if se is not None and self._press is not None:
            if self._mode == "move":
                if se.end_edit():
                    self._sync_live()
                    self.clamp_cam()
            elif (self._mode == "pan" and not self._panning
                  and (self.tool == "stamp" or self.layout.pane)):
                w = self._world_at(*self._press)
                if w is not None:
                    se.place(w[0], w[1])
                    self._sync_live()
        self._mode = None

    # -- drawing ---------------------------------------------------------------

    def draw_sprite(self, cv, x, y, w, h):
        """The picked actor's sprite on the grey checker."""
        se = self.sceneedit
        sheet = self.ws.run.project.sheet
        r = se.selected() if se is not None else None
        if r is None or sheet is None:
            return
        dark, light = self.ws.look.live.fixed[:2]
        checker(cv, x, y, w, h, 4, dark, light)
        t = r.get("tile", 0)
        k = min(w, h) // sheet.TILE
        if 0 <= t < sheet.count and k > 0:
            ox, oy = sheet.tile_origin(t)
            d = k * sheet.TILE
            cv.sspr(sheet, ox, oy, sheet.TILE, sheet.TILE, x + (w - d) // 2, y + (h - d) // 2,
                    d, d, 0)

    def draw_view(self, cv, x, y, w, h):
        """The view, the page's canvas at (x, y, w, h): the dark field, the
        tilemap backdrop, the game viewport's frame and the placed actors,
        each boxed, the picked one in white -- on the handheld ringed by the
        canvas cursor instead."""
        self.view_at(x, y, w, h)
        ws = self.ws
        NAMES = self._NAMES
        se = self.sceneedit
        sheet = ws.run.project.sheet
        if se is None or sheet is None:
            return
        boxes = self.layout.pane
        x0, y0, scale, vw, vh = self._sv_metrics()
        tm = ws.run.project.tilemap
        # -- the world view: dark field, tilemap backdrop, viewport frame, actors.
        va = self._sv_area()
        cv.rect(va[0], va[1], va[2], va[3], NAMES["dark_blue"])
        g = sheet.TILE
        if tm is not None:
            # Visible map cells, drawn at the zoom scale (the scene draws OVER
            # the tilemap, #85 Section 4). Via spr_tile (#163): a contiguous
            # run coalesces into ONE native blit_batch, where the old
            # tile_image + spr pair paid an Image blit crossing PER CELL that
            # no batch could collect (pixel parity pinned by the #63 suite).
            c0 = se.cam_x // g
            r0 = se.cam_y // g
            c1 = (se.cam_x + vw - 1) // g
            r1 = (se.cam_y + vh - 1) // g
            spr_tile = cv.spr_tile
            for cy in range(r0, r1 + 1):
                if cy < 0 or cy >= tm.h:
                    continue
                for cx in range(c0, c1 + 1):
                    if cx < 0 or cx >= tm.w:
                        continue
                    vx = x0 + (cx * g - se.cam_x) * scale
                    vy = y0 + (cy * g - se.cam_y) * scale
                    if (vx < x0 or vy < y0 or vx + g * scale > x0 + va[2]
                            or vy + g * scale > y0 + va[3]):
                        continue              # only whole cells (no clip bleed)
                    tid = tm.mget(cx, cy)
                    if tid >= 0:
                        spr_tile(sheet, tid, vx, vy, -1, scale, 0)
        # The fixed game viewport's frame at world (0,0)-(320,240): what a
        # non-panning cart shows. Each edge clamped to the view rectangle.
        self._frame_world(cv, 0, 0, 320, 240, NAMES["yellow"])
        # Placed actors, list order = draw order; box every actor so a blank
        # tile (a pure tag marker, e.g. a spawn point) stays visible.
        for i, r in enumerate(se.rows):
            vx = x0 + (r["x"] - se.cam_x) * scale
            vy = y0 + (r["y"] - se.cam_y) * scale
            side = g * scale
            if (vx + side <= x0 or vy + side <= y0
                    or vx >= x0 + va[2] or vy >= y0 + va[3]):
                continue
            if (vx >= x0 and vy >= y0 and vx + side <= x0 + va[2]
                    and vy + side <= y0 + va[3]):
                img = sheet.tile_image(r["tile"], 0)
                if img is not None:
                    cv.spr(img, vx, vy, scale)
                if not boxes and i == se.sel:
                    continue
                cv.rectb(vx, vy, side, side,
                         NAMES["white"] if i == se.sel else NAMES["dark_grey"])
                if i == se.sel and side > 4:
                    cv.rectb(vx + 1, vy + 1, side - 2, side - 2, NAMES["white"])
        r = se.selected()
        if not boxes and r is not None:
            vx = x0 + (r["x"] - se.cam_x) * scale
            vy = y0 + (r["y"] - se.cam_y) * scale
            side = g * scale
            if vx >= x0 and vy >= y0 and vx + side <= x0 + va[2] and vy + side <= y0 + va[3]:
                _ui_draw.cursor(cv, (vx, vy, side, side))

    def _frame_world(self, cv, wx, wy, ww, wh, color):
        """Outline the world rect (wx, wy, ww, wh) in view coords, each edge
        clamped to the view rectangle (the canvas has no clip region, and an
        unclamped rectb would bleed over the palette column)."""
        se = self.sceneedit
        x0, y0, scale, vw, vh = self._sv_metrics()
        va = self._sv_area()
        vx1 = x0 + va[2]
        vy1 = y0 + va[3]

        def to_vx(w):
            return x0 + (w - se.cam_x) * scale

        def to_vy(w):
            return y0 + (w - se.cam_y) * scale

        left, top = to_vx(wx), to_vy(wy)
        right, bottom = to_vx(wx + ww), to_vy(wy + wh)
        cl = max(left, x0)
        ct = max(top, y0)
        cr = min(right, vx1)
        cb = min(bottom, vy1)
        if cr <= cl or cb <= ct:
            return
        if y0 <= top < vy1:
            cv.rect(cl, top, cr - cl, 1, color)
        if y0 < bottom <= vy1:
            cv.rect(cl, bottom - 1, cr - cl, 1, color)
        if x0 <= left < vx1:
            cv.rect(left, ct, 1, cb - ct, color)
        if x0 < right <= vx1:
            cv.rect(right - 1, ct, 1, cb - ct, color)
