# Map (grep -n a name to jump there):
#   PartHost        the host of a desk pane's own page (editor_part.py)
#   PartHost._sync  each part's state from the cores
#   PartHost.act    what the page's handlers ask: a pick, a verb, Insert
#   song_do         a Song verb on the core: a slot's sound, add, delete, play
#   palette_items   a blocks category's rows in the palette
#   add_block       a palette row activated: its block at the Blocks pane's cursor
#   made_lines      the code the blocks make, as the made pane's lines
#   log_rows        the Reference's Log: the run's and the code's errors, to their line
#   goto            the Code pane on a file and line, with the keys
"""The desk Editor's own panes (docs/media/look_2026-10/EDITOR_LAYOUT.md's
World, Art, Code and Sound workspaces), over the editor cores the handheld
tabs edit (`SceneEditor`, `MusicEditor`, the blocks): each a part of
editor_part.py's page, hosted by `PartHost` on the pane's body -- the
Actor, the Sheet, the Reference's Sprites, Sounds, Map and Log, the
Stamps, the made code, a blocks cart's palette, and the Sound workspace's
list and Song. A change is the core's own (its undo step), synced to the
running game as the tab's is."""

import editor_sound as Sound
import blocks as B
import view_host as _V


def _lines_of(text, w, fs):
    """`text` in the lines it takes `w` wide in the UI face at `fs`,
    broken at its words (a word wider than `w` alone on its line)."""
    out, cur = [], ""
    for word in text.split(" "):
        t = word if not cur else cur + " " + word
        if cur and _V.text_w(t, fs) > w:
            out.append(cur)
            cur = word
        else:
            cur = t
    out.append(cur)
    return out
from view_host import PageHost, cursor

_LIST_ROW = 28              # a list's row on the desk (style.json's stack_desk)

# Pane contents that are a part of the page, and the part each shows (the
# Sounds content is the Reference's outside the Sound workspace).
PAGES = ("actor", "sheet", "sprites", "stamps", "made", "palette", "sounds", "song", "maps", "log")


def part_of(desk, c):
    """The part pane content `c` shows on `desk`."""
    if c == "sounds" and desk.key != "sound":
        return "ref_sounds"
    return c


def _music(desk):
    mu = desk.ws.music_ui
    if mu.musicedit is None:
        mu.build()
    return mu, mu.musicedit


def _sketch(cv, th, s, x, y, w, h, u):
    """A sound's sketch: a bar a step at its pitch in its first wave's ink,
    a rest none."""
    steps = s.steps
    heard = [st[0] for st in steps if st[0] >= 0 and st[2]]
    if not heard:
        cv.rect(x, y + h - 1 * u, w, 1 * u, th["border"])
        return
    lo, hi = min(heard) - 2, max(heard) + 2
    bw = max(2 * u, w // max(8, len(steps)))
    ink = Sound.wave_ink(th, steps[0][1])
    for i, st in enumerate(steps[: w // bw]):
        if st[0] >= 0 and st[2]:
            bh = max(2 * u, (st[0] - lo) * h // max(1, hi - lo))
            cv.rect(x + i * bw, y + h - bh, bw - 1 * u, bh, ink)


def new_sound(desk):
    """The Sounds pane's ＋: a new sound at the end of the bank."""
    _mu, me = _music(desk)
    if me is None:
        return
    if me.view != me.SFX_VIEW:
        me.toggle_view()
    me.select_sfx(len(me.bank.sfx) - me.sfx_idx)
    desk.ws.mark_dirty()


def _slot_sound(row):
    """A slot's sound: its channel-0 SFX id (a multi-channel row's first), -1 silent."""
    if isinstance(row, list):
        return row[0] if row else -1
    return row


def song_do(desk, op):
    """One of the Song's verbs on the core (each edit an undo step): the
    slot's sound back or forward, add or delete a slot, the next or
    previous song, play or stop. An edit is the song's, so it puts the core
    in the song view."""
    mu, me = _music(desk)
    if me is None:
        return
    if op == "play":
        if mu.music_preview is not None:
            mu._stop_music_preview()
            return
        if me.view != me.SONG_VIEW:
            me.toggle_view()
        mu._play_music_preview()
        return
    if me.view != me.SONG_VIEW:
        me.toggle_view()
    if op == "slot-":
        me.nudge_slot(-1)
    elif op == "slot+":
        me.nudge_slot(1)
    elif op == "add":
        me.add_slot()
    elif op == "del":
        me.del_slot()
    elif op == "song-":
        me.select_track(-1)
    elif op == "song+" and me.track_idx + 1 < len(me.bank.music):
        me.select_track(1)
    desk.ws.mark_dirty()


# -- the block palette ---------------------------------------------------------------

_NEW = {"variables": ("\x00new_var", "+ new variable"),
        "lists": ("\x00new_list", "+ new list"),
        "myblocks": ("\x00new_proc", "+ new block")}
_CALL = "\x00call:"


def _blocks(desk):
    bu = desk.ws.block_ui
    if bu.blocks_ed is None:
        bu.build()
    return bu, bu.blocks_ed


def palette_items(be, cat):
    """(item, label) for the blocks category `cat` offers: the catalog's,
    headed by its make-one row; My Blocks' calls; none for the events,
    which head every script already."""
    if cat == "events":
        return []
    out = []
    if cat in _NEW:
        out.append(_NEW[cat])
    if cat == "myblocks":
        for n in (be.proc_names() if be is not None else []):
            out.append((_CALL + n, "call " + n))
        return out
    for t in B.blocks_in_category(cat):
        d = B.block_def(t)
        out.append((t, _filled(d) if d else t))
    return out


def _filled(d):
    """A catalog block's label as a new block reads: each slot its default,
    one with none its name ("move by {dx} {dy}" reads "move by 2 0")."""
    label = d["label"]
    for slot in d.get("slots", ()):
        v = slot.get("default")
        if v is not None:
            label = label.replace("{%s}" % slot["name"], str(v))
    label = label.replace("{", "").replace("}", "")
    while "  " in label:
        label = label.replace("  ", " ")
    return label.strip()


def add_block(desk, item):
    """A palette row activated: the block at the Blocks pane's cursor (on a
    block, the next "+ add block" after it), or the category's make-one row."""
    bu, be = _blocks(desk)
    if be is None or bu.blk_graduated:
        return
    if not item.startswith("\x00new") and not be.at_insert():
        for k in range(be.cur + 1, len(be.rows)):
            if be.rows[k].kind == "insert":
                be.cur = k
                break
    if item == _NEW["variables"][0]:
        bu._blk_new_variable()
    elif item == _NEW["lists"][0]:
        bu._blk_new_list()
    elif item == _NEW["myblocks"][0]:
        bu._blk_new_proc()
    elif item.startswith(_CALL):
        bu._blk_insert_call(item[len(_CALL):])
    else:
        bu._blk_insert_chosen(item)
    desk.ws.mark_dirty()


# -- the code the blocks make ----------------------------------------------------------

_made = [None, None]            # [the program's text it was made from, its lines]


def made_lines(be):
    """The blocks' code as lines, made again only when the program moved."""
    key = repr(be.program)
    if _made[0] != key:
        try:
            src = B.compile_blocks(be.program)
        except B.BlockError as e:
            src = "# " + str(e)
        _made[0] = key
        _made[1] = src.rstrip("\n").split("\n")
    return _made[1]


# -- the Reference (the Code workspace's context pane) ---------------------------------

def _first_cell(tm):
    """Where the Reference's map opens: the first cell holding a tile."""
    for y in range(tm.h):
        for x in range(tm.w):
            if tm.mget(x, y):
                return (x, y)
    return (0, 0)


def log_rows(desk):
    """(text, file, row) for each error the Log names: the run's crash at its
    line, the code's own error."""
    ws = desk.ws
    out = []
    err, line = ws.cart_error, ws.run.player.crash_line
    if err:
        f = ws.run.player.crash_file or ws.text.code_file_name()
        if line:
            out.append(("%s:%d  %s" % (f, line, err), f, line - 1))
        else:
            out.append((str(err), None, None))
    if ws.code_err and ws.code_err_row is not None:
        f = ws.text.code_file_name()
        out.append(("%s:%d  %s" % (f, ws.code_err_row + 1, ws.code_err), f, ws.code_err_row))
    return out


def goto(desk, name, row):
    """The Code pane on file `name`, its caret on `row`, and the keys."""
    ws = desk.ws
    if row is None:
        return
    if name and name != ws.text.code_file_name():
        ws.text.open_code_file(name)
    ed = ws.editor
    if ed is not None:
        ed.goto_row(row)
    for n, (pane, _r, _p) in enumerate(desk.panes()):
        if "code" in pane:
            desk.focus_pane(n)
    ws.mark_dirty()


# -- the panes that are a page of their own ------------------------------------------

_SHEET_COLS, _SHEET_ROWS = 16, 8    # a sheet page: 16 x 8 tiles


class PartHost(PageHost):
    """Part `part`'s page (editor_part.py) on the desk `desk`'s pane body,
    the pane showing content `c`: its state from the cores (`_sync`), the
    canvases it draws, picks from and moves along (the sheet, the song's
    slots, the Reference's map, a sound's sketch), and the verbs its rows and
    buttons ask for (`act`)."""

    def __init__(self, desk, c, part):
        import editor_part
        PageHost.__init__(self, desk.ws, None, part, editor_part.part_page)
        self.desk = desk
        self.part = part
        self.tab = c                    # the pane content: whether the keys are in it
        self._sheet_at = None           # the sheet's pages as drawn: (x0, y0, page w, page h,
                                        # caption, pages shown, the first, tile px) in its canvas
        self._cv_xy = (0, 0)            # the sheet canvas's corner, as drawn
        self._slots_at = None           # the slots as drawn: (x0, y0, cell w, cell h, gap, first, n)
        self._map_at = None             # the map as drawn: (x0, y0, cols, rows, tile px)
        self._items = ()                # the palette's blocks: (item, label)
        self._names = [None, 0, 0, ()]  # their names in lines: for the items, width, scale
        self._item_w = 0                # the width a palette row last drew
        self._cats_at = None            # the categories as drawn: (x0, y0, cell w, row h)
        self._snd_w = 0                 # a sounds row's width, as drawn

    def _sync(self):
        part = self.part
        fn = getattr(self, "_sync_" + part, None)
        self.push((part, fn() if fn is not None else None))

    def _sync_actor(self):
        ws = self.ws
        roomy = ws.look.effective_font_scale() < 2
        se = ws.scene_ui.sceneedit
        a = se.selected() if se is not None else None
        if a is None:
            return (False, "", (), "", False, "", roomy)
        tag = str(a.get("tag") or "")
        got = []
        for row in se.rows:
            t = row.get("tag")
            if t and str(t) not in got:
                got.append(str(t))
        tags = tuple(got[:5])
        gap = "   " if roomy else "  "
        place = gap.join(("Tile %d" % a.get("tile", 0), "x %d" % a.get("x", 0), "y %d" % a.get("y", 0)))
        return (True, tag, tags, tag if tag in tags else "", bool(a.get("flip")), place, roomy)

    def _sync_stamps(self):
        se = self.ws.scene_ui.sceneedit
        return (getattr(se, "stamp_tag", None) if se is not None else None) or "thing"

    def _sync_sprites(self):
        return "spr(%d, x, y)" % self.desk._cur_sprite()

    def _sync_made(self):
        _bu, be = _blocks(self.desk)
        return "\n".join(made_lines(be)) if be is not None else ""

    def _sync_palette(self):
        d = self.desk
        bu, be = _blocks(d)
        if be is None:
            return (False, "", 0, False, self._row_h(), 0, "")
        cat = d.part_state.get("block cat", "actors")
        items = self._items = palette_items(be, cat)
        note = ("Every script starts with one: they head the Blocks pane" if not items
                else "This cart is code now: its blocks only read" if bu.blk_graduated else "")
        rh = self._row_h()
        fold = self._cats_fold(self._rect[2] if self._rect is not None else 0)
        u = d._unit()
        w = self._item_w or ((self._rect[2] if self._rect is not None else 0) - 16 * u)
        lines = max([len(n) for n in self._names_in(w - 26 * u)] or [1])
        ih = rh if lines < 2 else max(rh, lines * self._line_h() + 8 * u)
        return (True, cat, 6 * rh + 12 * u, fold, ih, 0 if note else len(items), note)

    def _line_h(self):
        """A wrapped palette name's line pitch: the UI face's ascent at the
        scale and a gap."""
        return _V.ui_line() * self.ws.look.effective_font_scale() + 2 * self.desk._unit()

    def _names_in(self, w):
        """The palette's names, each in the lines it takes `w` wide in the
        UI face: a name too long for one row wraps at its words. Kept while
        the names, `w` and the scale stand."""
        fs = self.ws.look.effective_font_scale()
        k = self._names
        if k[0] is not self._items or k[1] != w or k[2] != fs:
            k[0], k[1], k[2] = self._items, w, fs
            k[3] = [_lines_of(label, w, fs) for _i, label in self._items]
        return k[3]

    def _cats_fold(self, w):
        """Whether the categories fold into a cycle of them on a page `w`
        wide: where a name would not fit its half of two columns beside
        its colour (`draw_cats`)."""
        import editor_part
        u = self.desk._unit()
        fs = self.ws.look.effective_font_scale()
        need = 20 * u + max(_V.text_w(label, fs) for _k, label in editor_part.CATS)
        return bool(w) and 2 * need + 16 * u > w

    def _row_h(self):
        """A list's row: 28 desk units, taller where the text is (Large and
        Largest)."""
        fs = self.ws.look.effective_font_scale()
        return max(_LIST_ROW * self.desk._unit(), _V.ui_line() * fs + 8)

    def _snd_cur(self, me):
        """The key of the sounds row that is current: the Song's or a sound's."""
        if self.part == "ref_sounds":
            return str(self.desk.part_state.get("ref sound", 0))
        return "song" if me.view == me.SONG_VIEW else str(me.sfx_idx)

    def _sync_sounds(self):
        _mu, me = _music(self.desk)
        if me is None:
            return (False, 0, (), "", "")
        cur = self._snd_cur(me)
        rows = (("song", cur == "song"),) if self.part == "sounds" else ()
        rows += tuple((str(k), cur == str(k)) for k in range(len(me.bank.sfx)))
        return (True, self._row_h(), rows, cur, "")

    def _sync_ref_sounds(self):
        _mu, me = _music(self.desk)
        if me is None:
            return (False, 0, (), "", "")
        st = self.desk.part_state
        st["ref sound"] = max(0, min(len(me.bank.sfx) - 1, st.get("ref sound", 0)))
        got = self._sync_sounds()
        return got[:4] + ("sfx(%d)" % st["ref sound"],)

    def _sync_song(self):
        mu, me = _music(self.desk)
        if me is None:
            return (False, "", False, False, False, True)
        t = me.cur_track()
        pat = t.pattern if t is not None else ()
        tracks = len(me.bank.music)
        line = "Song %d of %d" % (me.track_idx + 1, tracks) if tracks > 1 else "One sound a slot"
        playing = mu.music_preview is not None and mu.music_preview[0] == "song"
        return (True, line, len(pat) > 1, playing, tracks > 1, self.ws.look.effective_font_scale() < 2)

    def _sync_maps(self):
        if self.ws.run.project.tilemap is None:
            return (False, "")
        self._map_view(1, 1)
        cx, cy = self.desk.part_state["ref cell"]
        return (True, "mget(%d, %d)" % (cx, cy))

    def _sync_log(self):
        return tuple(t for t, _f, _r in log_rows(self.desk))

    def draw(self, r, dt):
        """The page on body rect `r`, on the pane's card (its ground)."""
        ws = self.ws
        cv = ws.sys_canvas
        th = ws.theme_colors
        pg = self._page()
        if self._rect != r:
            self._rect = r
        d = self.desk
        away = d.tab_of(d.focused()[0]) != self.tab
        self._host.begin(cv, th, r, True, False, away)
        self._sync()
        pg.paint(dt, cv, th, r, True)
        self._host.end()
        if not self._host.still():
            ws.request_frame()

    # -- what the handlers ask

    def act(self, verb, *args):
        ws = self.ws
        d = self.desk
        if verb == "insert":
            if ws.editor is not None:
                ws.history.code_burst_open()
                ws.editor.insert_text(self._shown[1][-1] if self.part != "sprites" else self._shown[1])
                ws.mark_dirty()
            return
        if verb == "cat":
            d.part_state["block cat"] = args[0]
            ws.mark_dirty()
            return
        if verb == "block":
            if args[0].isdigit() and int(args[0]) < len(self._items):
                add_block(d, self._items[int(args[0])][0])
            return
        if verb == "goto":
            rows = log_rows(d)
            if 0 <= args[0] < len(rows):
                goto(d, rows[args[0]][1], rows[args[0]][2])
            return
        if verb in ("sound", "play"):
            self._sound(verb, args[0])
            return
        if verb == "song":
            song_do(d, args[0])
            return
        su = ws.scene_ui
        se = su.sceneedit
        if se is None or se.selected() is None:
            return
        if verb == "tag":
            if not args[0] or args[0] == se.selected().get("tag") or not se.set_tag(args[0]):
                return
        elif verb == "flip":
            se.toggle_flip()
        elif verb == "front":
            se.front_sel()
        elif verb == "back":
            se.back_sel()
        elif verb == "remove":
            se.delete_sel()
        su._sync_live()
        ws.mark_dirty()
        d._owe_restart("scene")

    def _sound(self, verb, k):
        """A sounds row picked (`sound`: the Song or a sound to edit; the
        Reference's the one whose call Insert puts) or its play tool."""
        ws = self.ws
        mu, me = _music(self.desk)
        if me is None:
            return
        if self.part == "ref_sounds":
            if verb == "sound":
                self.desk.part_state["ref sound"] = int(k)
            elif mu.music_preview == ("sfx", int(k)):
                mu._stop_music_preview()
            else:
                au = ws.run.audio
                if au is not None:
                    au.focus()
                    au.sound_stop()
                    au.sfx(int(k))
                    mu.music_preview = ("sfx", int(k))
            ws.mark_dirty()
            return
        if verb == "sound":
            if k == "song":
                if me.view != me.SONG_VIEW:
                    me.toggle_view()
            else:
                if me.view == me.SONG_VIEW:
                    me.toggle_view()
                me.sfx_idx = int(k)
                me.step = 0
        elif mu.music_preview == ("sfx", int(k)):
            mu._stop_music_preview()
        else:
            if me.view != me.SFX_VIEW:
                me.toggle_view()
            me.sfx_idx = int(k)
            mu._play_music_preview()
        ws.mark_dirty()

    # -- the sounds' rows

    def draw_snd(self, cv, x, y, w, h, k):
        """Sounds row `k`: the Song and its length; a sound, its number and
        its name where it has one (moy-spec's optional `name`), a sketch of
        its notes and its play tool, marked while it plays."""
        mu, me = _music(self.desk)
        if me is None:
            return
        th = self.ws.theme_colors
        u = self.desk._unit()
        self._snd_w = w
        ink = th["ink"]
        if k == self._snd_cur(me):
            got = _V.current(cv, th, (x, y, w, h), 4 * u, item="row")
            ink = got if got is not None else ink
        cell = 32 * u
        if k == "song":
            t = me.cur_track()
            n = len(t.pattern) if t is not None else 0
            right = "1 slot" if n == 1 else "%d slots" % n
            _V.label(cv, (x + 10 * u, y, w - 20 * u, h), "Song", ink)
            _V.label(cv, (x + 10 * u, y, w - 20 * u, h), right, th["ink_dim"], _V.ALIGN_RIGHT)
            return
        if not k.isdigit() or int(k) >= len(me.bank.sfx):
            return
        n = int(k)
        _V.label(cv, (x + 10 * u, y, w - cell - 70 * u, h), Sound.row_label(me, n), ink)
        _sketch(cv, th, me.bank.sfx[n], x + w - cell - 56 * u, y + 6 * u, 44 * u, h - 12 * u, u)
        tr = (x + w - cell, y + (h - cell) // 2, cell, cell)
        tink = th["ink"]
        if mu.music_preview == ("sfx", n):
            got = _V.current(cv, th, tr, 4 * u, item="cell")
            tink = got if got is not None else tink
        g = 18 * u
        gr = (tr[0] + (cell - g) // 2, tr[1] + (cell - g) // 2, g, g)
        if not self.ws.draw_icon("run", gr, tink, cv):
            _V.glyph(cv, "run", gr, tink)

    def snd_pointer(self, kind, x, y, k):
        """A tap on a row picks it; on a sound's play tool, plays it or
        stops it playing."""
        if kind != "up":
            return
        if k.isdigit() and x >= self._snd_w - 32 * self.desk._unit():
            self._sound("play", k)
        else:
            self._sound("sound", k)

    # -- the palette

    def draw_item(self, cv, x, y, w, h, k):
        """A block of the palette's category: its category's bar, its label."""
        if not k.isdigit() or int(k) >= len(self._items):
            return
        th = self.ws.theme_colors
        u = self.desk._unit()
        cat = self.desk.part_state.get("block cat", "actors")
        ink = self.ws.look.content_colors().get("block_" + cat, th["border"])
        cv.rect(x + 8 * u, y + 4 * u, 3 * u, h - 8 * u, ink)
        if w != self._item_w:
            self._item_w = w                # the next sync's rows take its lines
            self.ws.mark_dirty()
        lines = self._names_in(w - 26 * u)[int(k)]
        lh = self._line_h()
        ly = y + (h - len(lines) * lh) // 2
        for i in range(len(lines)):
            _V.label(cv, (x + 18 * u, ly + i * lh, w - 26 * u, lh), lines[i], th["ink"])

    def draw_cats(self, cv, x, y, w, h):
        """The eleven categories in two columns, each by its colour, the
        current one marked."""
        import editor_part
        th = self.ws.theme_colors
        u = self.desk._unit()
        cols = self.ws.look.content_colors()
        cat = self.desk.part_state.get("block cat", "actors")
        pad = 6 * u
        cw = (w - 2 * pad - 4 * u) // 2
        rh = self._row_h()
        self._cats_at = (pad, pad, cw, rh)
        for n, (k, label) in enumerate(editor_part.CATS):
            cx = x + pad + (n % 2) * (cw + 4 * u)
            cy = y + pad + (n // 2) * rh
            ink = th["ink"]
            if k == cat:
                got = _V.current(cv, th, (cx, cy, cw, rh), 4 * u, item="row")
                ink = got if got is not None else ink
            d = 8 * u
            cv.rrect(cx + 5 * u, cy + (rh - d) // 2, d, d, 2 * u, cols.get("block_" + k, th["border"]))
            _V.label(cv, (cx + 18 * u, cy, cw - 20 * u, rh), label, ink)

    def _cat(self, n):
        import editor_part
        k = editor_part.CATS[n][0]
        st = self.desk.part_state
        if st.get("block cat") != k:
            st["block cat"] = k
            self.ws.mark_dirty()

    def cats_pointer(self, kind, x, y):
        """A press on a category opens its blocks."""
        g = self._cats_at
        if g is None or kind != "down":
            return
        x0, y0, cw, rh = g
        col, row = (x - x0) // (cw + 4 * self.desk._unit()), (y - y0) // rh
        if x >= x0 and y >= y0 and col < 2 and 0 <= row * 2 + col < 11:
            self._cat(row * 2 + col)

    def cats_keys(self, i):
        """The arrows across the two columns open the next category; one
        past the grid's edge is not taken."""
        import editor_part
        dx = i.steps("right") - i.steps("left")
        dy = i.steps("down") - i.steps("up")
        if not (dx or dy):
            return False
        keys = [k for k, _l in editor_part.CATS]
        cur = self.desk.part_state.get("block cat", "actors")
        n = keys.index(cur) if cur in keys else 0
        m = n + dx + 2 * dy
        if not 0 <= m < len(keys) or (dx and m // 2 != n // 2):
            return False
        self._cat(m)
        return True

    # -- the Song's slots

    def draw_slots(self, cv, x, y, w, h, lh):
        """The song's slots four a row, each its sound's number and name
        over a sketch of its notes on a plate, the current one's on the
        current plate; the rows that show the current slot."""
        self._slots_at = None
        mu, me = _music(self.desk)
        if me is None:
            return
        t = me.cur_track()
        pat = t.pattern if t is not None else ()
        if not pat:
            return
        th = self.ws.theme_colors
        u = self.desk._unit()
        pad = 10 * u
        lh = max(20 * u, lh)            # the name's line, the sketch under it
        cw, ch = 72 * u, lh + 36 * u
        gap = max(4 * u, (w - 2 * pad - 4 * cw) // 3)
        fit = max(1, (h - 4 * u + 8 * u) // (ch + 8 * u))
        on = me.view == me.SONG_VIEW
        cur = me.slot if 0 <= me.slot < len(pat) else 0
        first = max(0, cur // 4 - fit + 1) * 4
        x0, y0 = x + pad, y + 4 * u
        self._slots_at = (x0 - x, y0 - y, cw, ch, gap, first, min(len(pat), first + 4 * fit))
        for k in range(first, min(len(pat), first + 4 * fit)):
            cx = x0 + (k % 4) * (cw + gap)
            cy = y0 + ((k - first) // 4) * (ch + 8 * u)
            sid = _slot_sound(pat[k])
            _V.plate(cv, th, (cx, cy, cw, ch), "", "normal", on=on and k == cur)
            heard = 0 <= sid < len(me.bank.sfx)
            _V.label(cv, (cx + 6 * u, cy + 4 * u, cw - 12 * u, lh),
                           Sound.row_label(me, sid) if heard else "-",
                           th["ink"] if heard else th["ink_dim"])
            if heard:
                _sketch(cv, th, me.bank.sfx[sid], cx + 6 * u, cy + ch - 22 * u, cw - 12 * u, 16 * u, u)

    def _slot_at(self, x, y):
        g = self._slots_at
        if g is None:
            return -1
        x0, y0, cw, ch, gap, first, last = g
        col, ax = (x - x0) // (cw + gap), (x - x0) % (cw + gap)
        u = self.desk._unit()
        row, ay = (y - y0) // (ch + 8 * u), (y - y0) % (ch + 8 * u)
        k = first + row * 4 + col
        if x < x0 or y < y0 or col > 3 or ax >= cw or ay >= ch or not first <= k < last:
            return -1
        return k

    def _pick_slot(self, k):
        mu, me = _music(self.desk)
        if me is None:
            return
        if me.view != me.SONG_VIEW:
            me.toggle_view()
        me.select_cursor(k)
        self.ws.mark_dirty()

    def slots_pointer(self, kind, x, y):
        """A tap on a slot edits the song there."""
        if kind == "down":
            k = self._slot_at(x, y)
            if k >= 0:
                self._pick_slot(k)

    def slots_keys(self, i):
        """The arrows along the slots, four a row; one past the song's end
        is not taken."""
        mu, me = _music(self.desk)
        if me is None:
            return False
        t = me.cur_track()
        n = len(t.pattern) if t is not None else 0
        dx = i.steps("right") - i.steps("left")
        dy = i.steps("down") - i.steps("up")
        if not (dx or dy) or not n:
            return False
        cur = me.slot if 0 <= me.slot < n else 0
        k = cur + dx + 4 * dy
        if not 0 <= k < n or (dx and k // 4 != cur // 4):
            return False
        self._pick_slot(k)
        return True

    # -- the Reference's map

    def _map_view(self, cols, rows):
        """The picked cell, and the view's corner kept round it, `cols` x
        `rows` cells shown."""
        tm = self.ws.run.project.tilemap
        st = self.desk.part_state
        if "ref cell" not in st:
            st["ref cell"] = _first_cell(tm)
        cx, cy = st["ref cell"]
        cx = max(0, min(tm.w - 1, cx))
        cy = max(0, min(tm.h - 1, cy))
        vx, vy = st.get("ref view", (0, 0))
        vx = max(min(vx, cx), cx - cols + 1)
        vy = max(min(vy, cy), cy - rows + 1)
        vx = max(0, min(vx, max(0, tm.w - cols)))
        vy = max(0, min(vy, max(0, tm.h - rows)))
        st["ref cell"] = (cx, cy)
        st["ref view"] = (vx, vy)
        return cx, cy, vx, vy

    def draw_map(self, cv, x, y, w, h):
        """The Reference's Map: the cart's map at 1x from the view's corner,
        the picked cell ringed."""
        ws = self.ws
        tm, sh = ws.run.project.tilemap, ws.sheet
        self._map_at = None
        if tm is None or sh is None:
            return
        th = ws.theme_colors
        u = self.desk._unit()
        pad = 6 * u
        tw = 8 * u
        cols = max(1, (w - 2 * pad) // tw)
        rows = max(1, (h - pad) // tw)
        mx, my, mw, mh = x + pad, y + pad, cols * tw, rows * tw
        self._map_at = (pad, pad, cols, rows, tw)
        cx, cy, vx, vy = self._map_view(cols, rows)
        cv.rect(mx, my, mw, mh, th["surface_alt"])
        cv.clip(mx, my, mw, mh)
        for row in range(min(rows, tm.h - vy)):
            for col in range(min(cols, tm.w - vx)):
                t = tm.mget(vx + col, vy + row)
                if t:
                    img = sh.tile_image(t, 0)
                    if img is not None:
                        cv.spr(img, mx + col * tw, my + row * tw, u)
        self.desk.unclip(cv)
        cursor(cv, (mx + (cx - vx) * tw, my + (cy - vy) * tw, tw, tw))

    def map_pointer(self, kind, x, y):
        """A press on the map picks its cell."""
        g = self._map_at
        if g is None or kind == "up":
            return
        x0, y0, cols, rows, tw = g
        if not (x0 <= x < x0 + cols * tw and y0 <= y < y0 + rows * tw):
            return
        st = self.desk.part_state
        vx, vy = st.get("ref view", (0, 0))
        st["ref cell"] = (vx + (x - x0) // tw, vy + (y - y0) // tw)
        self.ws.mark_dirty()

    def map_keys(self, i):
        """The arrows move the map's cell."""
        if self.ws.run.project.tilemap is None:
            return False
        dx = i.steps("right") - i.steps("left")
        dy = i.steps("down") - i.steps("up")
        if not (dx or dy):
            return False
        st = self.desk.part_state
        cx, cy = st.get("ref cell", (0, 0))
        st["ref cell"] = (cx + dx, cy + dy)
        self.ws.mark_dirty()
        return True

    def map_wheel(self, d):
        """The wheel over the map: `d` notches, three rows each."""
        st = self.desk.part_state
        vx, vy = st.get("ref view", (0, 0))
        cx, cy = st.get("ref cell", (0, 0))
        st["ref view"] = (vx, max(0, vy + 3 * d))
        st["ref cell"] = (cx, max(0, cy + 3 * d))
        self.ws.mark_dirty()

    # -- the sheet

    def _cur(self):
        """The tile the sheet rings: the Stamps' brush, else the sprite."""
        if self.tab == "stamps":
            se = self.ws.scene_ui.sceneedit
            return se.n if se is not None else -1
        return self.desk._cur_sprite()

    def draw_sheet(self, cv, x, y, w, h):
        """Two pages of the sprite sheet at 2x side by side (a page 16 x 8
        tiles) where the canvas holds them, centred down it, each captioned
        with its number; the current tile ringed by the cursor."""
        ws = self.ws
        sh = ws.sheet
        self._sheet_at = None
        if sh is None:
            return
        th = ws.theme_colors
        u = self.desk._unit()
        pages = max(1, sh.rows // _SHEET_ROWS)
        tw = 16 * u
        pw, ph = _SHEET_COLS * tw, _SHEET_ROWS * tw
        cap = 20 * u
        n = max(1, min(2, (w - cap) // (pw + cap)))
        first = min(self.desk._sheet_page, max(0, pages - n))
        top = y + max(0, (h - ph) // 2)
        self._cv_xy = (x, y)
        self._sheet_at = (cap, top - y, pw, ph, cap, n, first, tw)
        cur = self._cur()
        px = x + cap
        ring = None
        for k in range(n):
            pg = first + k
            if k:
                cv.rect(px - cap, top, cap, ph, th["surface"])
            cv.print(str(pg + 1), px - cap + 6 * u, top, th["ink_dim"], 1)
            cv.rect(px, top, pw, ph, th["surface_alt"])
            cv.sspr(sh, 0, pg * _SHEET_ROWS * 8, _SHEET_COLS * 8, _SHEET_ROWS * 8, px, top, pw, ph, 0)
            t = cur - pg * _SHEET_ROWS * _SHEET_COLS
            if 0 <= t < _SHEET_ROWS * _SHEET_COLS:
                ring = (px + (t % _SHEET_COLS) * tw, top + (t // _SHEET_COLS) * tw, tw, tw)
            px += pw + cap
        if ring is not None:
            cursor(cv, ring)

    def _tile_at(self, x, y):
        """The tile under (x, y) in the canvas, or -1."""
        g = self._sheet_at
        if g is None:
            return -1
        x0, y0, pw, ph, cap, n, first, tw = g
        k = (x - x0) // (pw + cap) if x >= x0 else -1
        ax, ay = x - x0 - k * (pw + cap), y - y0
        if not (0 <= k < n and 0 <= ax < pw and 0 <= ay < ph):
            return -1
        return ((first + k) * _SHEET_ROWS + ay // tw) * _SHEET_COLS + ax // tw

    def sheet_pointer(self, kind, x, y):
        """A press on the sheet, its slide and its release: the tile under
        it picked (`_pick_tile`), its loupe over the finger while held."""
        d = self.desk
        if kind == "up":
            d._loupe = None
            self.ws.mark_dirty()
            return
        t = self._tile_at(x, y)
        if t < 0:
            return
        self._pick_tile(t)
        d._loupe = (t, self._cv_xy[0] + x, self._cv_xy[1] + y)
        self.ws.mark_dirty()

    def _pick_tile(self, t):
        """Tile `t` picked: the Stamps' brush, else the sprite (`EditorDesk._pick`)."""
        ws = self.ws
        if self.tab == "stamps":
            se = ws.scene_ui.sceneedit
            if se is None or se.n == t:
                return
            se.set_brush(t)
        elif self.desk._cur_sprite() == t:
            return
        else:
            self.desk._pick(t)
        ws.request_frame()

    def sheet_keys(self, i):
        """The arrows along the sheet: the next tile picked, the pages shown
        following it; one past the sheet's edge is not taken."""
        ws = self.ws
        sh = ws.sheet
        if sh is None:
            return False
        dx = i.steps("right") - i.steps("left")
        dy = i.steps("down") - i.steps("up")
        if not (dx or dy):
            return False
        cur = self._cur()
        n = cur + dx + dy * _SHEET_COLS
        if not 0 <= n < sh.cols * sh.rows or (dx and n // _SHEET_COLS != cur // _SHEET_COLS):
            return False
        self._pick_tile(n)
        page = _SHEET_COLS * _SHEET_ROWS
        d = self.desk
        d._sheet_page = min(d._sheet_page, n // page)
        if n // page > d._sheet_page + 1:
            d._sheet_page = n // page - 1
        ws.mark_dirty()
        return True
