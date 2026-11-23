# Map (grep -n a name to jump there):
#   PAGES           the panes that are a page of their own (editor_part.py)
#   PartHost        such a pane's host: its page's state, the sheet, the actor's verbs
#   PARTS           the panes the desk Editor draws on the verbs
#   sounds          the Sound workspace's list: the song, then a row a sound
#   song            the Song pane: its verbs, then its slots, the current one marked
#   song_do         a Song verb on the core: a slot's sound, add, delete, play
#   palette         the Blocks workspace's palette: the categories, then their blocks
#   made            the code the blocks make, read only
#   ref_sounds      the Reference's Sounds: a pick puts its sfx() at the caret
#   map_view        the Reference's Map: a pick puts its mget() at the caret
#   log             the Reference's Log: the run's and the code's errors, to their line
#   pointer, keys   a press on the map, the arrows over it
"""The desk Editor's own panes (docs/media/look_2026-10/EDITOR_LAYOUT.md's
World, Art, Code and Sound workspaces), over the editor cores the handheld
tabs edit (`SceneEditor`, `MusicEditor`): the Actor, the Sheet, the
Reference's Sprites, the Stamps and the made code are a page each
(editor_part.py, hosted by `PartHost` on the pane's body); the rest draw in
their pane's body inside `EditorDesk`'s frame and answer its taps and keys
through the verbs. A change is the core's own (its undo step), synced to
the running game as the tab's is."""

import ui
import editor_sound as Sound
import blocks as B
from view_host import PageHost, cursor

PAGES = ("actor", "sheet", "sprites", "stamps", "made")
PARTS = ("sounds", "song", "log", "maps", "palette")

_LIST_ROW = 28              # a list's row on the desk (style.json's stack_desk)
_INK, _DIM = {"tone": "ink"}, {"tone": "dim"}


def draw(desk, c, r, u):
    """Part `c` in body rect `r` (the frame is begun)."""
    if c == "sounds":
        if desk.key == "sound":
            sounds(desk, r, u)
        else:
            ref_sounds(desk, r, u)
    elif c == "song":
        song(desk, r, u)
    elif c == "palette":
        palette(desk, r, u)
    elif c == "maps":
        map_foot(desk, r, u)
    elif c == "log":
        log(desk, r, u)


def drawn_before(desk, c, cv, th, r, u):
    """The parts drawn on the canvas before the frame begins: the
    Reference's map."""
    if c == "maps":
        map_view(desk, cv, th, r, u)


def _music(desk):
    mu = desk.ws.music_ui
    if mu.musicedit is None:
        mu.build()
    return mu, mu.musicedit


def sounds(desk, r, u):
    """The Sound workspace's list: the Song and its length, then a row a
    sound, by its number and its name where it has one (moy-spec's optional
    `name`), a sketch of its notes and its play tool."""
    mu, me = _music(desk)
    if me is None:
        return
    ws = desk.ws
    th = ws.theme_colors
    cv = ws.sys_canvas
    items = ["Song"] + [Sound.row_label(me, k) for k in range(len(me.bank.sfx))]
    song = me.view == me.SONG_VIEW
    cur = 0 if song else me.sfx_idx + 1
    x, y, w, h = r
    pad = 6 * u
    cell = 32 * u
    rh = _LIST_ROW * u
    lr = (x + pad, y + 4 * u, w - 2 * pad - cell, h - 8 * u)
    ui.at(*lr)
    got = ui.list("Sounds", items, cur, {"id": "sound list"})
    if got is not None and got != cur and got >= 0:
        if got == 0:
            if not song:
                me.toggle_view()
        else:
            if song:
                me.toggle_view()
            me.sfx_idx = got - 1
            me.step = 0
        ws.mark_dirty()
    if len(items) * rh > lr[3]:
        return                      # the list scrolls in its rect: no sketches over it
    t = me.cur_track()
    n = len(t.pattern) if t is not None else 0
    slots = "1 slot" if n == 1 else "%d slots" % n
    sw = ui.text_size(slots)[0] + 8 * u
    ui.at(lr[0] + lr[2] - sw, lr[1], sw, rh)
    ui.label(slots, {"tone": "dim"})
    playing = mu.music_preview
    for k, s in enumerate(me.bank.sfx):
        ry = lr[1] + (k + 1) * rh
        _sketch(cv, th, s, lr[0] + lr[2] - 52 * u, ry + 6 * u, 44 * u, rh - 12 * u, u)
        ui.at(x + w - pad - cell, ry + (rh - cell) // 2, cell, cell)
        on = playing is not None and playing == ("sfx", k)
        if ui.tool("run", "Play", {"id": "sound play %d" % k, "current": on}):
            if on:
                mu._stop_music_preview()
            else:
                if me.view != me.SFX_VIEW:
                    me.toggle_view()
                me.sfx_idx = k
                mu._play_music_preview()
            ws.mark_dirty()


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


def sounds_header(desk, pid, tx, y, hh, u):
    """The Sounds pane's ＋: a new sound at the end of the bank."""
    _mu, me = _music(desk)
    if me is None:
        return tx
    cell = 32 * u
    tx -= cell
    ui.at(tx, y, cell, hh)
    if ui.tool("new", "New sound", {"id": pid + " new sound"}):
        if me.view != me.SFX_VIEW:
            me.toggle_view()
        me.select_sfx(len(me.bank.sfx) - me.sfx_idx)
        desk.ws.mark_dirty()
    return tx


def song(desk, r, u):
    """The Song (EDITOR_LAYOUT.md's Sound workspace): its line -- what a slot
    is, the current slot's sound back and forward, add and delete a slot,
    play the song -- then its slots four a row, each its sound's number and
    name over a sketch of its notes, the current one on the current plate.
    A tap on a slot edits the song there."""
    mu, me = _music(desk)
    if me is None:
        return
    ws = desk.ws
    x, y, w, h = r
    pad = 10 * u
    cell = 32 * u
    t = me.cur_track()
    pat = t.pattern if t is not None else ()
    tracks = len(me.bank.music)
    on = me.view == me.SONG_VIEW
    playing = mu.music_preview is not None and mu.music_preview[0] == "song"
    tools = [("run", "Stop" if playing else "Play", "play"),
             ("del", "Delete slot", "del"), ("new", "Add slot", "add"),
             ("forward", "Next sound", "slot+"), ("back", "Previous sound", "slot-")]
    if tracks > 1:
        tools += [("forward", "Next song", "song+"), ("back", "Previous song", "song-")]
    tx = x + w - pad
    ty = y + 4 * u
    for icon, word, op in tools:
        tx -= cell
        ui.at(tx, ty, cell, cell)
        if ui.tool(icon, word, {"id": "song " + op, "current": op == "play" and playing,
                                "disabled": op == "del" and len(pat) <= 1}):
            song_do(desk, op)
    ui.at(x + pad, ty, max(0, tx - x - pad), cell)
    ui.label("Song %d of %d" % (me.track_idx + 1, tracks) if tracks > 1
             else "One sound a slot", _DIM)
    if not pat:
        return
    cw, ch = 72 * u, 56 * u
    gap = max(4 * u, (w - 2 * pad - 4 * cw) // 3)
    gy = ty + cell + 6 * u
    fit = max(1, (y + h - gy + 8 * u) // (ch + 8 * u))
    cur = me.slot if 0 <= me.slot < len(pat) else 0
    first = max(0, cur // 4 - fit + 1) * 4      # the rows that show the current slot
    th = ws.theme_colors
    cv = ws.sys_canvas
    lh = max(20 * u, ui.text_size("0")[1] + 4)
    for k in range(first, min(len(pat), first + 4 * fit)):
        cx = x + pad + (k % 4) * (cw + gap)
        cy = gy + ((k - first) // 4) * (ch + 8 * u)
        sid = _slot_sound(pat[k])
        ui.at(cx, cy, cw, ch)
        if ui.button("", "normal", {"id": "slot %d" % k, "current": on and k == cur}):
            if not on:
                me.toggle_view()
            me.select_cursor(k)
            ws.mark_dirty()
        heard = 0 <= sid < len(me.bank.sfx)
        ui.at(cx + 6 * u, cy + 4 * u, cw - 12 * u, lh)
        ui.label(Sound.row_label(me, sid) if heard else "-", _INK if heard else _DIM)
        if heard:
            _sketch(cv, th, me.bank.sfx[sid], cx + 6 * u, cy + ch - 22 * u, cw - 12 * u, 16 * u, u)


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

# The palette's categories (the insert menu's, block_editor_ui._CAT_LABEL)
# in the pictures' order, read across two columns, and the rows heading
# three of them.
_CATS = (("events", "When..."), ("control", "Control"), ("draw", "Draw"),
         ("input", "Buttons"), ("variables", "Variables"), ("lists", "Lists"),
         ("actors", "Sprite"), ("looks", "Looks"), ("operators", "Math"),
         ("sound", "Sound"), ("myblocks", "My Blocks"))
# The palette's two columns: the categories alternately (a board's MicroPython
# slices with no step).
_CAT_SIDES = (tuple(_CATS[i] for i in range(0, len(_CATS), 2)),
              tuple(_CATS[i] for i in range(1, len(_CATS), 2)))
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


def palette(desk, r, u):
    """The Blocks workspace's palette (EDITOR_LAYOUT.md): the eleven
    categories in two columns, each by its colour, then the current one's
    blocks; activating a block puts it at the Blocks pane's cursor."""
    ws = desk.ws
    bu, be = _blocks(desk)
    if be is None:
        ui.at(*r)
        ui.empty("blocks", "No blocks", ("This cart's blocks did not open",))
        return
    th = ws.theme_colors
    cv = ws.sys_canvas
    cols = ws.look.content_colors()
    st = desk.part_state
    cat = st.get("block cat", "actors")
    x, y, w, h = r
    pad = 6 * u
    rh = _LIST_ROW * u
    half = (w - 2 * pad - 4 * u) // 2
    rows = (len(_CATS) + 1) // 2
    for side in (0, 1):
        part = _CAT_SIDES[side]
        cx = x + pad + side * (half + 4 * u)
        names = ["   " + label for _k, label in part]
        cur = [k for k, _l in part].index(cat) if cat in [k for k, _l in part] else -1
        ui.at(cx, y + 6 * u, half, rows * rh)
        got = ui.list("block categories %d" % side, names, cur,
                      {"id": "block categories %d" % side})
        if got is not None and got >= 0 and got != cur:
            cat = st["block cat"] = part[got][0]
            ws.mark_dirty()
        for k, (key, _l) in enumerate(part):
            d = 8 * u
            cv.rrect(cx + 5 * u, y + 6 * u + k * rh + (rh - d) // 2, d, d, 2 * u,
                     cols.get("block_" + key, th["border"]))
    top = y + 6 * u + rows * rh + 8 * u
    ui.at(x + pad, top, w - 2 * pad, 1)
    ui.rule()
    top += 8 * u
    items = palette_items(be, cat)
    room = (y + h - pad) - top
    if not items:
        ui.at(x + pad, top, w - 2 * pad, room)
        ui.label("Every script starts with one: they head the Blocks pane",
                 {"tone": "dim", "wrap": True, "lines": 4})
        return
    if bu.blk_graduated:
        ui.at(x + pad, top, w - 2 * pad, room)
        ui.label("This cart is code now: its blocks only read",
                 {"tone": "dim", "wrap": True, "lines": 4})
        return
    ui.at(x + pad, top, w - 2 * pad, room)
    got = ui.list("blocks of " + cat, ["  " + label for _i, label in items], -1,
                  {"id": "palette blocks"})
    if got is not None and 0 <= got < len(items):
        add_block(desk, items[got][0])
    if len(items) * rh <= room:
        ink = cols.get("block_" + cat, th["border"])
        for k in range(len(items)):
            cv.rect(x + pad + 2 * u, top + k * rh + 4 * u, 3 * u, rh - 8 * u, ink)


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


def scroll(desk, c, d):
    """The wheel over a part that scrolls by rows: `d` notches."""
    st = desk.part_state
    if c == "maps":
        vx, vy = st.get("ref view", (0, 0))
        cx, cy = st.get("ref cell", (0, 0))
        st["ref view"] = (vx, max(0, vy + 3 * d))
        st["ref cell"] = (cx, max(0, cy + 3 * d))
        desk.ws.mark_dirty()
        return True
    return False


# -- the Reference (the Code workspace's context pane) ---------------------------------

_FOOT = 40                      # a Reference tab's foot: the call a pick puts at the caret


def _foot(desk, r, u, call, id):
    """The call a pick puts at the Code pane's caret, and Insert."""
    ws = desk.ws
    x, y, w, h = r
    row = 30 * u
    ui.at(x + 10 * u, y + h - row - 4 * u, w - 110 * u, row)
    ui.label(call, {"tone": "dim"})
    ui.at(x + w - 96 * u, y + h - row - 4 * u, 88 * u, row)
    if ui.button("Insert", "normal", {"id": id}) and ws.editor is not None:
        ws.history.code_burst_open()
        ws.editor.insert_text(call)
        ws.mark_dirty()


def ref_sounds(desk, r, u):
    """The Reference's Sounds (EDITOR_LAYOUT.md): a row a sound, its number,
    name, sketch and play tool; the picked one's `sfx(n)` goes at the caret."""
    mu, me = _music(desk)
    if me is None:
        ui.at(*r)
        ui.empty("music", "No sounds", ("This cart has no sound bank",))
        return
    ws = desk.ws
    th = ws.theme_colors
    cv = ws.sys_canvas
    st = desk.part_state
    n = len(me.bank.sfx)
    cur = max(0, min(n - 1, st.get("ref sound", 0)))
    x, y, w, h = r
    pad = 6 * u
    cell = 32 * u
    rh = _LIST_ROW * u
    lr = (x + pad, y + 4 * u, w - 2 * pad - cell, h - 8 * u - _FOOT * u)
    ui.at(*lr)
    got = ui.list("Sound calls", [Sound.row_label(me, k) for k in range(n)], cur,
                  {"id": "ref sounds"})
    if got is not None and 0 <= got < n and got != cur:
        cur = st["ref sound"] = got
        ws.mark_dirty()
    if n * rh <= lr[3]:
        playing = mu.music_preview
        for k, s in enumerate(me.bank.sfx):
            ry = lr[1] + k * rh
            _sketch(cv, th, s, lr[0] + lr[2] - 52 * u, ry + 6 * u, 44 * u, rh - 12 * u, u)
            ui.at(x + w - pad - cell, ry + (rh - cell) // 2, cell, cell)
            on = playing is not None and playing == ("sfx", k)
            if ui.tool("run", "Play", {"id": "ref play %d" % k, "current": on}):
                if on:
                    mu._stop_music_preview()
                else:
                    au = ws.run.audio
                    if au is not None:
                        au.focus()
                        au.sound_stop()
                        au.sfx(k)
                        mu.music_preview = ("sfx", k)
                ws.mark_dirty()
    _foot(desk, r, u, "sfx(%d)" % cur, "insert sfx")


def _map_rect(desk, r, u):
    x, y, w, h = r
    pad = 6 * u
    tw = 8 * u
    cols = max(1, (w - 2 * pad) // tw)
    rows = max(1, (h - _FOOT * u - pad) // tw)
    return (x + pad, y + pad, cols * tw, rows * tw), cols, rows, tw


def _map_view_at(desk, cols, rows):
    """The picked cell, and the view's corner kept round it."""
    ws = desk.ws
    tm = ws.run.project.tilemap
    st = desk.part_state
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


def _first_cell(tm):
    """Where the Reference's map opens: the first cell holding a tile."""
    for y in range(tm.h):
        for x in range(tm.w):
            if tm.mget(x, y):
                return (x, y)
    return (0, 0)


def map_view(desk, cv, th, r, u):
    """The Reference's Map: the cart's map at 1x from the view's corner, the
    picked cell under the cursor."""
    ws = desk.ws
    tm, sh = ws.run.project.tilemap, ws.sheet
    if tm is None or sh is None:
        return
    (mx, my, mw, mh), cols, rows, tw = _map_rect(desk, r, u)
    cx, cy, vx, vy = _map_view_at(desk, cols, rows)
    cv.rect(mx, my, mw, mh, th["surface_alt"])
    cv.clip(mx, my, mw, mh)
    for row in range(min(rows, tm.h - vy)):
        for col in range(min(cols, tm.w - vx)):
            t = tm.mget(vx + col, vy + row)
            if t:
                img = sh.tile_image(t, 0)
                if img is not None:
                    cv.spr(img, mx + col * tw, my + row * tw, u)
    cv.clip()
    desk._cursors.append((mx + (cx - vx) * tw, my + (cy - vy) * tw, tw, tw))


def map_foot(desk, r, u):
    ws = desk.ws
    if ws.run.project.tilemap is None:
        ui.at(*r)
        ui.empty("map", "No map", ("This cart has no map yet",))
        return
    cx, cy = desk.part_state.get("ref cell", (0, 0))
    _foot(desk, r, u, "mget(%d, %d)" % (cx, cy), "insert mget")


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


def log(desk, r, u):
    """The Reference's Log: each error with its file and line; activating one
    puts the Code pane's caret there."""
    rows = log_rows(desk)
    if not rows:
        ui.at(*r)
        ui.empty("doc", "Nothing logged", ("Your game's errors show here, with their line",))
        return
    x, y, w, h = r
    ui.at(x + 6 * u, y + 4 * u, w - 12 * u, h - 8 * u)
    got = ui.list("Log", [t for t, _f, _r in rows], -1, {"id": "log"})
    if got is not None and 0 <= got < len(rows):
        goto(desk, rows[got][1], rows[got][2])


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


def pointer(desk, c, r, u, px, py, click, down):
    """A press a part takes itself: a cell of the Reference's map. True
    where it took it."""
    if c != "maps" or desk.ws.run.project.tilemap is None or not (click or down):
        return False
    (mx, my, mw, mh), cols, rows, tw = _map_rect(desk, r, u)
    if not (mx <= px < mx + mw and my <= py < my + mh):
        return False
    st = desk.part_state
    vx, vy = st.get("ref view", (0, 0))
    st["ref cell"] = (vx + (px - mx) // tw, vy + (py - my) // tw)
    desk.ws.mark_dirty()
    return True


def keys(desk, c, i):
    """The arrows over the Reference's map move its cell. True where they
    acted."""
    if c != "maps" or desk.ws.run.project.tilemap is None:
        return False
    dx = i.steps("right") - i.steps("left")
    dy = i.steps("down") - i.steps("up")
    if not (dx or dy):
        return False
    st = desk.part_state
    cx, cy = st.get("ref cell", (0, 0))
    st["ref cell"] = (cx + dx, cy + dy)
    desk.ws.mark_dirty()
    return True


# -- the panes that are a page of their own ------------------------------------------

_SHEET_COLS, _SHEET_ROWS = 16, 8    # a sheet page: 16 x 8 tiles


class PartHost(PageHost):
    """Pane content `part`'s page (editor_part.py, one of `PAGES`) on the
    desk `desk`'s pane body: its state from the cores (`_sync`), the sheet
    its canvas draws, picks from and moves along, and the verbs its
    buttons ask for (`act`)."""

    def __init__(self, desk, part):
        import editor_part
        PageHost.__init__(self, desk.ws, None, part, editor_part.part_page)
        self.desk = desk
        self._sheet_at = None           # the sheet's pages as drawn: (x0, y0, page w, page h,
                                        # caption, pages shown, the first, tile px) in its canvas
        self._cv_xy = (0, 0)            # the sheet canvas's corner, as drawn

    def _sync(self):
        ws = self.ws
        part = self.tab
        picked, tag, tags, at, flip, place, stamp, call, made = False, "", (), "", False, "", "thing", "", ""
        roomy = ws.look.effective_font_scale() < 2
        se = ws.scene_ui.sceneedit if part in ("actor", "stamps") else None
        if part == "actor" and se is not None:
            a = se.selected()
            if a is not None:
                picked = True
                tag = str(a.get("tag") or "")
                got = []
                for row in se.rows:
                    t = row.get("tag")
                    if t and str(t) not in got:
                        got.append(str(t))
                tags = tuple(got[:5])
                at = tag if tag in tags else ""
                flip = bool(a.get("flip"))
                gap = "   " if roomy else "  "
                place = gap.join(("Tile %d" % a.get("tile", 0), "x %d" % a.get("x", 0),
                                  "y %d" % a.get("y", 0)))
        elif part == "stamps" and se is not None:
            stamp = getattr(se, "stamp_tag", None) or "thing"
        elif part == "sprites":
            call = "spr(%d, x, y)" % self.desk._cur_sprite()
        elif part == "made":
            _bu, be = _blocks(self.desk)
            made = "\n".join(made_lines(be)) if be is not None else ""
        self.push((part, picked, tag, tags, at, flip, place, stamp, call, made, roomy))

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
        ui.end()
        if not self._host.still():
            ws.request_frame()

    # -- the actor's verbs and the Reference's Insert

    def act(self, verb, *args):
        ws = self.ws
        if verb == "insert":
            if ws.editor is not None:
                ws.history.code_burst_open()
                ws.editor.insert_text("spr(%d, x, y)" % self.desk._cur_sprite())
                ws.mark_dirty()
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
        self.desk._owe_restart("scene")

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
