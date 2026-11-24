# Map (grep -n a name to jump there):
#   BlockLayout                     the page's geometry: the outline's rows and the foot
#   BlockEditorUI                   the structured-outline UI over a cart's block program
#   BlockEditorUI.build             build the BlockEditor over the cart's program
#   BlockEditorUI.save_blocks       compile-on-save to the cart's source
#   BlockEditorUI.graduate_to_code  the one-way graduation to code
"""The block editor's UI layer (issue #29 Part 2): the structured outline of a
cart's block program, its insert menu, and the number/name/text prompts.

Two layers, the same split as the console's other sub-editors:
  * BlockEditor (runtime/editors/editors_block.py) -- the pure tree-edit core: flattens the
    program into cursor-addressable rows, inserts/deletes/moves blocks, sets
    slot values. No canvas, no input.
  * BlockEditorUI (here) -- the UI: the host of the `uitree` page
    `runtime/editors/editor_blocks.py` (the handheld's tab and a desk Editor's
    Blocks pane alike), which draws the outline, the menus and the prompts:
    it writes the core's state into the page's, draws the outline's rows,
    takes the outline's keys and does what the page's handlers ask --
    the menus' and the prompts' state, save and graduation.

One instance lives on Workstation (`ws.block_ui`), with a back-reference to
it for the primitives it shares with the rest of the console (canvas, input,
cart, carts_store, _with_sd, set_menu_view, _leave_or_home,
_btn, editor, pointer, sys_canvas). `NAMES` / `_err_text` are injected at
construction instead of imported back from console.py, which would be a
circular import.
"""

import ui_draw as _ui_draw
import ui_font as _ui_font
import uitree_editor
import editor_blocks

from editors_block import BlockEditor, _clone_tree
from editors_base import TextEntry, text_key as _text_key
# The block vocabulary/compiler (#29). Mirrors console.py's own import (see its
# comment there): bare `blocks` on the device (frozen top-level) and once
# host_app has aliased it on the host, or `runtime.blocks` when a test loads
# this module directly without that alias.
import blocks as _blocks_mod
from layout_base import LayoutBase, BASE_W as _BASE_W, BASE_H as _BASE_H
import layout_base as _layout_base

# An outline row's pitch and a depth's indent, at the font scale: the page's
# table rows are ROW tall (`BlockEditorUI.row_h`), or the text's height.
ROW = 22
INDENT = 14

# A block's label cells are the print font's glyph box, never under this.
_FONT_W = 8

# The insert menu (category list, then the block list for the chosen category,
# then for some slots a small option picker) is the page's popover, its keys the
# engine's; B backs out one level.
_BLK_MENU_ROWS = 10

# The menu's caption by its mode.
MENU_TITLES = {"cat": "Pick a kind", "blk": "Pick a block", "dropdown": "Pick one",
               "variable": "Pick a variable", "list": "Pick a list",
               "expr": "Pick a value", "actions": "Block actions",
               "proc": "Edit this block"}

# The entry prompts (the page's dialog): their titles by kind and the field's
# caption by kind (a number's is its slot's); a name's says the rule for one.
_KBD_TITLES = {"num": "Type a number", "text": "Type some text", "proc": "Name your block",
               "param": "Name an input"}
_KBD_CAPTIONS = {"text": "Text"}
# In-row slot editing: tapping/right-step on a selected block cycles to its NEXT
# editable slot; that slot is highlighted, and A opens its editor (number bump,
# variable/dropdown picker, expr -> a nested expression insert).
# Kid-facing category names for the insert menu (the catalog ids are terse keys).
_CAT_LABEL = {
    "events": "When...", "control": "Control", "draw": "Draw", "input": "Buttons",
    "variables": "Variables", "lists": "Lists", "actors": "Sprite", "looks": "Looks",
    "operators": "Math", "sound": "Sound", "myblocks": "My Blocks",
}

# Sentinel menu row: "make a brand-new variable + name it". It heads the Variables
# block list AND the variable-slot picker, so a kid can always create + name a
# variable with just ▲▼ + A (no dragging) and then use it everywhere (#29 Bug 2).
_NEW_VAR_ITEM = "\x00new_var"
_NEW_VAR_LABEL = "+ new variable"

# The list analogue (#48): heads the Lists block list AND the list-slot picker, so a
# kid creates + names a list the same way they make a variable.
_NEW_LIST_ITEM = "\x00new_list"
_NEW_LIST_LABEL = "+ new list"

# Custom blocks (#48: My Blocks / procedures). "+ new block" heads the My Blocks
# category (create + name a proc), then one "call NAME" row per defined proc --
# encoded as the _CALL_PREFIX + the proc name so a menu item stays a plain string.
_NEW_PROC_ITEM = "\x00new_proc"
_NEW_PROC_LABEL = "+ new block"
_CALL_PREFIX = "\x00call:"
# The PROC ACTIONS menu (opened with A on a define-hat): add/remove an input, rename
# or delete the whole block. Sentinels so they never collide with a real block id.
_PROC_ADD = "\x00proc_add"
_PROC_RENAME = "\x00proc_rename"
_PROC_DELP = "\x00proc_delp"
_PROC_DEL = "\x00proc_del"
_PROC_LABELS = {
    _PROC_ADD: "Add an input",
    _PROC_RENAME: "Rename block",
    _PROC_DELP: "Remove last input",
    _PROC_DEL: "Delete this block",
}

# Sentinel menu row in the expr-slot chooser: "type a number" -- the Scratch white
# editable oval. It heads the reporter list so a typed literal (the common case:
# `set score to 0`, `> 100`) is the first, obvious choice; picking it opens the
# number keypad instead of dropping a block (#29).
_NUM_LITERAL_ITEM = "\x00num_lit"
_NUM_LITERAL_LABEL = "123 type a number"

# The #93 BLOCK ACTIONS menu items (context-sensitive rows, built by
# _blk_open_actions). Sentinels so they never collide with a real block id.
_ACT_COPY = "\x00act_copy"
_ACT_DUP = "\x00act_dup"
_ACT_PASTE = "\x00act_paste"
_ACT_MOVE = "\x00act_move"
_ACT_LABELS = {
    _ACT_COPY: "Copy",
    _ACT_DUP: "Duplicate",
    _ACT_PASTE: "Paste here",
    _ACT_MOVE: "Move to...",
}


def _blk_plain_label(label):
    """A block's display label with the {slot} placeholders stripped to bare names,
    so a menu/row reads like 'repeat times' or 'if cond'. The renderer fills the
    real slot values inline; this is the human template without the braces."""
    out = ""
    for ch in str(label):
        if ch == "{":
            out += ""              # drop the brace; keep the slot name that follows
        elif ch == "}":
            out += ""
        else:
            out += ch
    return out


def _blk_num_allow(c, text):
    """A number literal: digits, one leading '-' and at most one '.'
    (parse_number_literal tolerates more; the filter keeps the buffer honest)."""
    return c.isdigit() or (c == "-" and not text) or (c == "." and "." not in text)


def _blk_name_allow(c, text):
    """A variable / list / block / input name: name-legal characters only."""
    return c.isalpha() or c.isdigit() or c in ("_", " ", "-")


# Which characters each prompt kind types; a kind not listed is a NAME.
_BLK_KBD_ALLOW = {"num": _blk_num_allow, "text": None}

class BlockLayout(LayoutBase):
    """The block editor's geometry, from the SYSTEM canvas size (w, h) and
    font scale: the content rect the page lays out in, on the handheld and
    in a desk Editor's Blocks pane alike, and a block's label cells, the
    print font's glyph box (a tap on a row finds its slot by them)."""

    def __init__(self, w=_BASE_W, h=_BASE_H, font_scale=1,
                 chrome_scale=None):
        LayoutBase.__init__(self, w, h, font_scale,
                            chrome_scale=chrome_scale)
        self.cell = max(_FONT_W, _ui_draw.font("ui")[1]) * self.fs


class _Damage:
    def __init__(self, ws):
        self.ws = ws

    def all(self):
        self.ws.mark_dirty()


class BlockEditorUI:
    """The structured-outline UI over a cart's block program: cursor + insert menu
    + inline prompts (draw + input/pointer). One instance lives on Workstation
    (`self.block_ui`), built once in Workstation.__init__; `ws.block_ui.build()` is
    called lazily from `set_menu_view("blocks")` the first time a cart's block
    editor is opened, exactly like the pre-extraction code did inline."""

    def __init__(self, ws, names, err_text, clamp_scroll):
        self.ws = ws
        # Injected instead of imported back from console.py (see module docstring):
        # console.py builds this instance, so `import console` here would be a real
        # circular import at BlockEditorUI's own module-load time. `clamp_scroll` is
        # the tiny shared scrolloff helper (#dedup, stage 1) chrome holds --
        # injected here instead of duplicated.
        self._NAMES = names
        self._err_text = err_text
        self._clamp_scroll = clamp_scroll
        # Block editor (#29 Part 2): a BlockEditor over the cart's block program +
        # the structured-outline UI state. `blocks_ed` is built lazily on first open.
        self.blocks_ed = None         # BlockEditor while menu_view == "blocks"
        self.blk_slot = 0             # which slot of the selected block is highlighted
        self.blk_menu = None          # active insert menu state dict, or None
        self.blk_status = None        # last block-editor SAVE result text
        self.blk_protect = False      # block editor opened on a hand-written-code cart
        self.blk_graduated = False    # cart has GRADUATED (Stage 8): blocks read-only
        self.blk_kbd = None           # inline name-entry prompt state dict, or None
        self.block_layout = BlockLayout()
        self._page = None             # the page's engine (editor_blocks.py), made at its first use
        self._host = _ui_draw.AppHost("editor_blocks", self)
        self._rect = None               # the page's rect, as the layout last placed it
        self._kbd_gen = 0             # the prompts opened, each its number
        self._asked = 0               # the prompt the page's dialog shows (0 none)
        self._px = 0                  # the last press's x (a row's slot is found by it)
        self._ox = 0                  # the outline's left, as its rows were last drawn
        self._made = [None] * 13      # what the page's values were made from (`_sync`)
        self._shown = None            # what `_sync` wrote last
        self._at_shown = None         # the cursor's row and slot `_sync` wrote last
        self._slot_shown = None
        self._rows = []               # the outline's rows, made with `_made`
        self._looks = []              # each row's look, made at its first draw
        self._tags = []               # the objects' tabs after the Stage's: their tags
        self._caret = [None, 0, 0, 0]     # (block, slot) -> its x off and width

    def page(self):
        """The page's engine, made and opened at its first use."""
        if self._page is None:
            self._page = uitree_editor.page(editor_blocks.blocks_page, self._host,
                                            _Damage(self.ws), gen=True)
            self._page.env = self           # what its handlers reach (`uitree_app.env()`)
            self._page.band = False         # the keys are the host's: no hints band
            self._page.open(hook="none")
        return self._page

    @property
    def s(self):
        """The page's state."""
        self.page()._bind()
        return editor_blocks.s

    def run(self, name, *args):
        """Run the page's action or hook `name` now."""
        pg = self.page()
        pg._bind()
        pg.run_action(pg.actions[name], args, "host")

    def relayout(self, w, h, fs, cs=None):
        """Rebuild the responsive layout from the live system-canvas size + the
        effective font scale (mirrors Workstation._relayout)."""
        self.block_layout = BlockLayout(w, h, fs, chrome_scale=cs)

    # -- Blocks + Scene side-by-side workspace (#93/#85) ----------------------

    def _selected_scene_tag(self):
        """The tag of the currently-selected scene actor, or None (Stage)."""
        se = self.ws.scene_ui.sceneedit
        if se is not None:
            sel = getattr(se, "sel", None)
            if sel is not None and 0 <= sel < len(se.rows):
                tag = se.rows[sel].get("tag")
                if tag:
                    return str(tag)
        return None

    def _sync_target_from_scene(self):
        """Point the block outline at the selected object's scripts. Selecting/placing
        an object focuses its scripts; a tag change is followed too. No selection keeps
        whatever target is active (so a stray tap doesn't yank the kid back to Stage)."""
        be = self.blocks_ed
        if be is None:
            return
        tag = self._selected_scene_tag()
        if tag is not None:
            be.set_target(tag)

    def _roster_tags(self):
        """The ordered, distinct list of sprite tags -- every object placed in the
        scene PLUS any object that has scripts (so a sprite shows in the list whether
        or not it's on the stage yet). Scene-placement order first."""
        tags = []
        seen = {}
        se = self.ws.scene_ui.sceneedit
        if se is not None:
            for r in se.rows:
                t = r.get("tag")
                if t and t not in seen:
                    seen[t] = True
                    tags.append(t)
        be = self.blocks_ed
        if be is not None:
            for o in (be.program.get("objects", []) or []):
                t = o.get("tag")
                if t and t not in seen:
                    seen[t] = True
                    tags.append(t)
        return tags

    def _select_sprite(self, tag):
        """Edit a sprite's scripts (tag) or the global Stage (tag None), and mirror the
        pick onto the stage -- selecting the first actor of that tag, like Scratch
        highlighting the chosen sprite. The two-way twin of _sync_target_from_scene."""
        be = self.blocks_ed
        if be is None:
            return
        be.set_target(tag)
        se = self.ws.scene_ui.sceneedit
        if tag is not None and se is not None:
            for i, r in enumerate(se.rows):
                if r.get("tag") == tag:
                    se.sel = i
                    se.n = r.get("tile", se.n)
                    se.stamp_tag = tag
                    break

    def build(self):
        """Build the BlockEditor over the cart's block program (#29), lazily --
        called from Text.set_menu_view("blocks"). A cart authored from
        blocks carries blocks.json (cart["blocks"]); a code-only cart starts a
        fresh empty program -- saving it makes the cart block-authored from then
        on. The Part-1 `blocks` module is injected so the editor core stays
        dependency-free."""
        ws = self.ws
        if self.blocks_ed is not None or ws.run.project.cart is None:
            return
        prog = None
        if ws.carts_store is not None and ws.run.project.cart.get("path"):
            try:
                prog = ws.with_sd(
                    lambda: ws.carts_store.load_blocks(ws.run.project.cart))
            except Exception as exc:  # noqa: BLE001
                print("Moybyte load blocks failed:", self._err_text(exc))
        if prog is None:
            # A DEEP COPY, never the cart's own tree (#93): the editor mutates its
            # program in place and undo/redo rebinds it -- editing an aliased
            # cart["blocks"] would drift the cart's snapshot away from both the
            # disk file and the editor (save_blocks re-syncs it with a fresh copy).
            prog = _clone_tree(ws.run.project.cart.get("blocks"))
        # DATA-LOSS GUARD (#29): a cart whose main.py is hand-written code (no
        # blocks.json, and main.py wasn't emitted by the block compiler) must
        # NEVER have that code clobbered by saving an empty block program. When
        # that's the case, run the block editor in PROTECTED mode: the outline
        # still opens (read-only-ish), but SAVE / graduate refuse to overwrite
        # main.py and tell the kid why. A genuinely block-authored cart (has
        # blocks.json) -- or an empty/new-template cart with no real code -- is
        # unprotected and round-trips exactly as before.
        self.blk_protect = (prog is None and ws.text.cart_has_handwritten_code())
        # GRADUATION (Stage 8, spec Section 8): a STORED, one-way project fact (read
        # from the manifest via cart["graduated"]), NOT the re-derived blk_protect
        # heuristic. A graduated cart's blocks.json is FROZEN -- it still opens (so the
        # kid sees the last-good program), but renders read-only + celebrates, and
        # SAVE/graduate refuse to overwrite the diverged main.py (see save_blocks).
        self.blk_graduated = bool(ws.run.project.cart.get("graduated"))
        self.blocks_ed = BlockEditor(_blocks_mod, prog)
        self.blk_slot = 0
        self.blk_menu = None
        if self.blk_graduated:
            self.blk_status = None            # the celebration banner carries the message
        elif self.blk_protect:
            self.blk_status = "CODE LOCKED"
        else:
            self.blk_status = None

    def reset(self):
        """Drop the active editor + any open menu/prompt (a stale one must never
        leak into an unrelated cart or back to the launcher). Called from both
        Workstation.open() (switching carts) and Home.go_home()."""
        self.blocks_ed = None
        self.blk_menu = None
        self.blk_kbd = None
        self.blk_protect = False
        self.blk_graduated = False

    def on_leave(self):
        """Called from Text._leave_menu() when menu_view == "blocks"."""
        self.blk_menu = None
        self.blk_kbd = None
        # #93: don't leave a half-started MOVE armed when the kid steps away.
        if self.blocks_ed is not None:
            self.blocks_ed.cancel_move()

    def commit_workspace_scene(self):
        """Persist the scene pane if it was edited in the combined workspace
        (#93/#85). Called from EditorApp.save_current when leaving the Blocks tab --
        the scene has its OWN commit path (save_scene -> Project.commit_scene),
        separate from save_blocks. No-op unless a scene editor is built AND dirty,
        so a blocks-only cart / an untouched scene never writes."""
        su = self.ws.scene_ui
        se = getattr(su, "sceneedit", None)
        if se is not None and getattr(se, "dirty", False):
            self.ws.saves.save_scene()

    # -- block editor (#29 Part 2) -------------------------------------------
    #
    # The structured outline. The cursor moves over the flattened script (block rows
    # + the `+` insert points between them); A inserts (at an insert point) or steps
    # through / edits the selected block's slots. No dragging -- the decided
    # device-friendly interaction. The vocabulary/compiler is Part 1's blocks module;
    # the BlockEditor core (runtime/editors/editors_block.py) owns the tree edits, this owns the UI.

    def _blk_move_cursor(self, d):
        be = self.blocks_ed
        if be is None:
            return
        be.move(d)
        self.blk_slot = 0          # a new selection resets the slot highlight

    def _blk_a(self):
        """The A/primary action in the outline: open the insert menu on a `+` row,
        or edit the highlighted slot of the selected block (a c-block with no slots
        falls back to opening the insert menu for its body's first gap)."""
        be = self.blocks_ed
        if be is None:
            return
        if be.moving():
            # MOVE in progress (#93): the next insert point is the destination.
            if be.at_insert():
                if be.complete_move():
                    self.blk_slot = 0
                    self.blk_status = "MOVED"
                else:
                    self.blk_status = "CAN'T MOVE THERE"
            return
        if be.at_insert():
            self._blk_open_categories()
            return
        b = be.selected_block()
        if b is None:
            return
        if b.get("t") == _blocks_mod.PROC_DEF:
            # A define-hat (#48): A opens the PROC ACTIONS menu (add/remove input,
            # rename, delete) instead of a slot editor -- its name/params aren't slots.
            self._blk_open_proc_menu(b)
            return
        slots = be.slots(b)
        if slots:
            self._blk_edit_slot(b, slots[self.blk_slot % len(slots)])

    def _blk_next_slot(self):
        """Step the slot highlight to the selected block's next slot (wraps)."""
        be = self.blocks_ed
        if be is None:
            return
        slots = be.slots()
        if slots:
            self.blk_slot = (self.blk_slot + 1) % len(slots)

    # -- the insert menu (category -> block, plus slot pickers) --------------
    def _blk_open_categories(self):
        """Open the modal insert menu at the category level."""
        self.blk_menu = {"mode": "cat", "sel": 0, "top": 0,
                         "items": _blocks_mod.categories()}

    # -- copy / paste / duplicate / move + undo (#93) ------------------------
    def _blk_open_actions(self):
        """Open the modal BLOCK ACTIONS menu (copy / duplicate / paste here / move
        to...). Context-sensitive: a selected block offers Copy/Duplicate/Move; an
        insert point with a filled clipboard offers Paste here. Reuses the shared
        modal-menu machinery (up/down + A, B backs out, tap-outside dismisses)."""
        be = self.blocks_ed
        if be is None:
            return
        items = []
        if be.selected_block() is not None:
            items.append(_ACT_COPY)
            items.append(_ACT_DUP)
            items.append(_ACT_MOVE)
        if be.at_insert() and be.has_clipboard():
            items.append(_ACT_PASTE)
        if not items:
            # nothing applies here -- point the kid at what to do rather than open
            # an empty menu (an insert point with nothing copied, say).
            self.blk_status = "COPY A BLOCK FIRST" if be.at_insert() \
                else "SELECT A BLOCK"
            return
        self.blk_menu = {"mode": "actions", "sel": 0, "top": 0, "items": items}

    def _blk_do_action(self, item):
        """Run a chosen BLOCK ACTIONS item and close the menu."""
        be = self.blocks_ed
        self.blk_menu = None
        if be is None:
            return
        if item == _ACT_COPY:
            self.blk_status = "COPIED" if be.copy_block() else "CAN'T COPY THAT"
        elif item == _ACT_DUP:
            if be.duplicate() is not None:
                self.blk_slot = 0
                self.blk_status = "DUPLICATED"
        elif item == _ACT_PASTE:
            if be.paste() is not None:
                self.blk_slot = 0
                self.blk_status = "PASTED"
            else:
                self.blk_status = "CAN'T PASTE HERE"
        elif item == _ACT_MOVE:
            if be.start_move():
                self.blk_status = "TAP A + SPOT"

    def _blk_open_blocks(self, category):
        ids = _blocks_mod.blocks_in_category(category)
        # Events are the lifecycle hats -- they live at the top level and the empty
        # program already has all three, so they're not insertable into a body.
        if category == _blocks_mod.CAT_EVENTS:
            ids = []
        # Variables: head the list with "+ new variable" so creating + naming one is
        # the first, obvious thing in the category (#29 Bug 2).
        if category == _blocks_mod.CAT_VARIABLES:
            ids = [_NEW_VAR_ITEM] + list(ids)
        # Lists: the same affordance -- "+ new list" heads the category (#48).
        if category == _blocks_mod.CAT_LISTS:
            ids = [_NEW_LIST_ITEM] + list(ids)
        # My Blocks (#48): "+ new block" heads the category, then one "call NAME" row
        # per defined proc (the catalog's own proc_def/call ids never list here).
        if category == _blocks_mod.CAT_PROCS:
            be = self.blocks_ed
            names = be.proc_names() if be is not None else []
            ids = [_NEW_PROC_ITEM] + [_CALL_PREFIX + n for n in names]
        self.blk_menu = {"mode": "blk", "cat": category, "sel": 0, "top": 0,
                         "items": ids}

    def _blk_menu_label(self, i):
        """The display label for menu item i (a category name or a block label)."""
        m = self.blk_menu
        if not m:
            return ""
        item = m["items"][i]
        if item == _NEW_VAR_ITEM:
            return _NEW_VAR_LABEL
        if item == _NEW_LIST_ITEM:
            return _NEW_LIST_LABEL
        if item == _NUM_LITERAL_ITEM:
            return _NUM_LITERAL_LABEL
        if item == _NEW_PROC_ITEM:
            return _NEW_PROC_LABEL
        if item[:len(_CALL_PREFIX)] == _CALL_PREFIX:      # a "call NAME" palette row
            return "call " + item[len(_CALL_PREFIX):]
        if item in _ACT_LABELS:
            return _ACT_LABELS[item]
        if item in _PROC_LABELS:
            return _PROC_LABELS[item]
        if m["mode"] == "cat":
            return _CAT_LABEL.get(item, item).upper()
        if m["mode"] == "blk":
            d = _blocks_mod.block_def(item)
            return _blk_plain_label(d["label"]) if d else item
        if m["mode"] in ("dropdown", "variable", "list"):
            return str(item)
        return str(item)

    def _blk_menu_select(self):
        """Activate the highlighted menu item (drill in or commit)."""
        m = self.blk_menu
        if not m or not m["items"]:
            return
        item = m["items"][m["sel"]]
        if item == _NEW_VAR_ITEM:
            # "+ new variable": create one with a default name and immediately open
            # the on-screen-keyboard name prompt so the kid names it (#29 Bug 2).
            self._blk_new_variable()
            return
        if item == _NEW_LIST_ITEM:
            # "+ new list": same flow, for lists (#48).
            self._blk_new_list()
            return
        if item == _NEW_PROC_ITEM:
            # "+ new block": create a custom block + name it (#48).
            self._blk_new_proc()
            return
        if item == _NUM_LITERAL_ITEM:
            # "type a number": close the chooser and open the number keypad on this
            # expr slot (the Scratch white oval -- a literal instead of a block).
            blk, name = m["block"], m["slot"]
            self.blk_menu = None
            self._blk_open_number_prompt(blk, name, None)
            return
        if m["mode"] == "actions":
            self._blk_do_action(item)
        elif m["mode"] == "proc":
            self._blk_do_proc_action(item)
        elif m["mode"] == "cat":
            self._blk_open_blocks(item)
        elif m["mode"] == "blk":
            if item[:len(_CALL_PREFIX)] == _CALL_PREFIX:   # "call NAME" (#48)
                self._blk_insert_call(item[len(_CALL_PREFIX):])
            else:
                self._blk_insert_chosen(item)
        elif m["mode"] == "dropdown":
            self.blocks_ed.set_slot(m["slot"], item, m["block"])
            self.blk_menu = None
        elif m["mode"] in ("variable", "list"):
            self.blocks_ed.set_slot(m["slot"], item, m["block"])
            self.blk_menu = None
        elif m["mode"] == "expr":
            self._blk_insert_expr(item)

    def _blk_menu_back(self):
        """Back out one menu level (block list -> categories), or close the menu."""
        m = self.blk_menu
        if not m:
            return
        if m["mode"] == "blk":
            self._blk_open_categories()
        else:
            self.blk_menu = None

    def _blk_insert_chosen(self, type_id):
        """Insert the chosen block type at the cursor and close the menu."""
        be = self.blocks_ed
        be.insert_block(type_id)
        self.blk_slot = 0
        self.blk_menu = None

    # -- custom blocks (#48: My Blocks / procedures) -------------------------
    def _blk_insert_call(self, name):
        """Insert a call to custom block `name` (args pre-filled with 0s) and close."""
        be = self.blocks_ed
        if be is not None:
            be.insert_call(name)
        self.blk_slot = 0
        self.blk_menu = None

    def _blk_new_proc(self):
        """Create a fresh custom block and open the name prompt so the kid names it
        (mirrors _blk_new_variable). The define-hat + empty body appear in the outline;
        confirming renames the default. `proc` carries the just-created proc_def."""
        be = self.blocks_ed
        if be is None:
            return
        pd = be.new_proc("block")
        self.blk_menu = None
        self._blk_open_kbd("proc", var=_blocks_mod.proc_name(pd), proc=pd,
                           slot_target=None)

    def _blk_open_proc_menu(self, pd):
        """Open the PROC ACTIONS menu on a define-hat: add/remove an input, rename or
        delete the whole custom block. `proc` is the target proc_def block."""
        items = [_PROC_ADD, _PROC_RENAME]
        if _blocks_mod.proc_params(pd):
            items.append(_PROC_DELP)
        items.append(_PROC_DEL)
        self.blk_menu = {"mode": "proc", "sel": 0, "top": 0, "items": items,
                         "proc": pd}

    def _blk_do_proc_action(self, item):
        """Run a chosen PROC ACTIONS item. Add/rename open a name prompt; remove-input
        and delete apply immediately."""
        be = self.blocks_ed
        m = self.blk_menu
        pd = m.get("proc") if m else None
        self.blk_menu = None
        if be is None or pd is None:
            return
        if item == _PROC_ADD:
            # name the new input, then add_param on confirm.
            self._blk_open_kbd("param", var="", proc=pd, slot_target=None)
        elif item == _PROC_RENAME:
            self._blk_open_kbd("proc", var=_blocks_mod.proc_name(pd), proc=pd,
                               slot_target=None)
        elif item == _PROC_DELP:
            self.blk_status = "INPUT REMOVED" if be.remove_last_param(pd) \
                else "NO INPUTS"
        elif item == _PROC_DEL:
            if be.delete_proc(pd):
                self.blk_slot = 0
                self.blk_status = "BLOCK DELETED"

    # -- slot editors --------------------------------------------------------
    def _blk_edit_slot(self, block, slot):
        """Open the right editor for a slot's type: a number slot (and an expr slot
        holding a literal) opens the on-screen number pad so the kid TYPES the value;
        an expr slot is the Scratch white oval -- type a number OR drop in a reporter
        block; variable + dropdown open a picker; text opens the keyboard."""
        t = slot["type"]
        name = slot["name"]
        if t == _blocks_mod.SLOT_DROPDOWN:
            # A dropdown opens its option list (16 colors is a lot to cycle through);
            # left/right still cycle it in place for a quick one-step tweak.
            self._blk_open_dropdown_picker(block, slot)
        elif t == _blocks_mod.SLOT_NUMBER:
            # Type the number directly (the +/- bump still lives on left/right).
            self._blk_open_number_prompt(block, name, slot)
        elif t == _blocks_mod.SLOT_TEXT:
            cur = str((block.get("p", {}) or {}).get(name, ""))
            self._blk_open_text_prompt(block, name, cur)
        elif t == _blocks_mod.SLOT_VARIABLE:
            self._blk_open_variable_picker(block, name)
        elif t == _blocks_mod.SLOT_LIST:
            self._blk_open_list_picker(block, name)
        elif t == _blocks_mod.SLOT_EXPR:
            # Scratch's editable oval: a literal opens the number pad (with an
            # "insert a block" escape hatch); a slot already holding a reporter block
            # re-opens the block chooser so the kid can swap/clear it.
            val = (block.get("p", {}) or {}).get(name)
            if _blocks_mod.is_literal_value(val):
                self._blk_open_number_prompt(block, name, slot)
            else:
                self._blk_open_expr_menu(block, name)

    def _blk_bump_number(self, block, name, d):
        # +/- nudge of a numeric slot (left/right in the outline). Works on a number
        # slot AND on an expr slot holding a numeric literal -- a quick tweak without
        # the keypad. A float keeps its fraction (e.g. 4.5 -> 5.5).
        be = self.blocks_ed
        cur = (block.get("p", {}) or {}).get(name, 0)
        if isinstance(cur, float):
            val = cur + d
        else:
            try:
                val = int(cur) + d
            except (TypeError, ValueError):
                val = d
        be.set_slot(name, val, block)

    # -- the entry prompts (name / number / text), one on-screen keypad -------
    def _blk_open_kbd(self, kind, text="", **fields):
        """Open an entry prompt as `self.blk_kbd`: `kind` routes the keypad
        (num / text / var / list / proc / param) and picks which characters
        its TextEntry accepts; `fields` are the prompt's own facts (the slot or
        variable it edits). The page's dialog shows it, its field starting
        empty (the key that opened it types nothing)."""
        entry = TextEntry(16, _BLK_KBD_ALLOW.get(kind, _blk_name_allow))
        entry.open(text)
        self._kbd_gen += 1
        fields["gen"] = self._kbd_gen
        fields["kind"] = kind
        fields["entry"] = entry
        self.blk_kbd = fields

    def cancel_prompt(self):
        """Close the open entry prompt as its Cancel does (the T-Deck's Mic,
        `InputPolicy.cancel`); False where none is open."""
        if self.blk_kbd is None:
            return False
        self._blk_kbd_cancel()
        return True

    def _blk_open_number_prompt(self, block, name, slot):
        """Open the on-screen number pad to TYPE a literal into a number / expr slot
        (#29 blocking gap: you can now set `score to 0`, `x to 50`, compare `> 100`).
        `slot` is the catalog slot (or None when reopened from the expr chooser): an
        expr slot can ALSO hold a reporter, so the pad offers a "BLOCK" escape hatch
        for it. The pad starts EMPTY (default-on-OK is the slot's current value), so
        the kid types a fresh number."""
        cur = (block.get("p", {}) or {}).get(name)
        allow_block = self._blk_slot_is_expr(block, name, slot)
        self.blk_menu = None
        self._blk_open_kbd("num", cur=cur, block=block, slot=name,
                           allow_block=allow_block)

    def _blk_slot_is_expr(self, block, name, slot):
        """True if the named slot on `block` is an expr slot (so the number pad can
        offer 'BLOCK' to drop a reporter instead). Uses `slot` when given; else looks
        the slot up in the catalog by name."""
        if slot is not None:
            return slot["type"] == _blocks_mod.SLOT_EXPR
        d = _blocks_mod.block_def(block.get("t"))
        if d is None:
            return False
        for s in d["slots"]:
            if s["name"] == name:
                return s["type"] == _blocks_mod.SLOT_EXPR
        return False

    def _blk_open_text_prompt(self, block, name, cur):
        """Open the on-screen keyboard to TYPE a text literal into a text slot."""
        self.blk_menu = None
        self._blk_open_kbd("text", str(cur or ""), block=block, slot=name)

    def _blk_open_variable_picker(self, block, name):
        # The variable-slot picker: "+ new variable" first (so a kid can create +
        # name one right here and have the slot use it), then the enclosing custom
        # block's PARAMETERS (#48, if the cursor is inside one -- they read like
        # variables in its body), then every declared variable.
        be = self.blocks_ed
        params = be.current_params()
        items = [_NEW_VAR_ITEM] + params + [v for v in be.variables()
                                            if v not in params]
        self.blk_menu = {"mode": "variable", "sel": 0, "top": 0, "items": items,
                         "block": block, "slot": name}

    def _blk_open_list_picker(self, block, name):
        # The list-slot picker (#48): "+ new list" first, then every declared list.
        be = self.blocks_ed
        items = [_NEW_LIST_ITEM] + be.lists()
        self.blk_menu = {"mode": "list", "sel": 0, "top": 0, "items": items,
                         "block": block, "slot": name}

    # -- variable create + name (on-screen keyboard) -------------------------
    def _blk_new_variable(self):
        """Create a fresh variable (default name) and open the name-entry prompt so
        the kid types its name with the on-screen keyboard. Remembers the menu that
        was open (variable-slot picker) so that slot gets filled with the named var
        once the kid confirms (#29 Bug 2)."""
        be = self.blocks_ed
        if be is None:
            return
        m = self.blk_menu
        slot_target = None
        if m is not None and m.get("mode") == "variable":
            slot_target = (m.get("block"), m.get("slot"))
        name = be.new_var("var")
        self.blk_menu = None
        # The entry starts EMPTY so the kid types a fresh name instead of
        # appending to the default; `var` is the just-created variable's CURRENT
        # name: confirm renames it old->typed, and a blank/invalid entry keeps
        # the default. `slot_target`, if set, is the (block, slot) to fill with
        # the final name.
        self._blk_open_kbd("var", var=name, slot_target=slot_target)

    def _blk_new_list(self):
        """Create a fresh list (default name) and open the name-entry prompt (#48).
        Mirrors _blk_new_variable: if a list-slot picker was open, that slot gets
        filled with the named list on confirm; the `list` prompt kind renames it."""
        be = self.blocks_ed
        if be is None:
            return
        m = self.blk_menu
        slot_target = None
        if m is not None and m.get("mode") == "list":
            slot_target = (m.get("block"), m.get("slot"))
        name = be.new_list("list")
        self.blk_menu = None
        self._blk_open_kbd("list", var=name, slot_target=slot_target)

    def _blk_kbd_commit(self):
        """Confirm a prompt: a name prompt renames the var; a number prompt parses the
        typed text into a numeric literal and writes it to the slot; a text prompt
        stores the string. Falls back to the slot's current value on a blank entry."""
        be = self.blocks_ed
        k = self.blk_kbd
        if be is None or k is None:
            self.blk_kbd = None
            return
        kind = k.get("kind", "var")
        if kind == "num":
            cur = k.get("cur")
            default = cur if _blocks_mod.is_literal_value(cur) and cur is not None else 0
            val = _blocks_mod.parse_number_literal(k["entry"].text, default)
            be.set_slot(k["slot"], val, k["block"])
            self.blk_status = "= " + str(val)
        elif kind == "text":
            be.set_slot(k["slot"], k["entry"].text, k["block"])
            self.blk_status = "TEXT SET"
        elif kind == "list":                   # "list": rename the freshly-created list
            old = k["var"]
            applied = be.rename_list(old, k["entry"].text)
            final = applied if applied else old
            bt = k.get("slot_target")
            if bt is not None and bt[0] is not None:
                be.set_slot(bt[1], final, bt[0])
            self.blk_status = "LIST: " + final[:12]
        elif kind == "proc":                   # "proc": rename the custom block (#48)
            old = k["var"]
            applied = be.rename_proc(old, k["entry"].text)
            self.blk_status = "BLOCK: " + (applied if applied else old)[:12]
        elif kind == "param":                  # "param": add an input to the block (#48)
            applied = be.add_param(k.get("proc"), k["entry"].text)
            self.blk_status = ("input: " + applied[:12]) if applied \
                else "bad input name"
        else:                                  # "var": rename the freshly-created var
            old = k["var"]
            applied = be.rename_var(old, k["entry"].text)
            final = applied if applied else old   # blank/dup/invalid keeps the default
            bt = k.get("slot_target")
            if bt is not None and bt[0] is not None:
                be.set_slot(bt[1], final, bt[0])
            self.blk_status = "VAR: " + final[:12]
        self.blk_kbd = None

    def _blk_kbd_cancel(self):
        """Cancel a prompt: a number/text prompt just discards the edit (the slot keeps
        its old value); a name prompt keeps the default-named variable/list (it's already
        declared and usable) and fills the slot with that default."""
        be = self.blocks_ed
        k = self.blk_kbd
        if be is not None and k is not None and k.get("kind", "var") in ("var", "list"):
            bt = k.get("slot_target")
            if bt is not None and bt[0] is not None:
                be.set_slot(bt[1], k["var"], bt[0])
        self.blk_kbd = None

    def _blk_open_dropdown_picker(self, block, slot):
        opts = _blocks_mod.slot_options(slot)
        self.blk_menu = {"mode": "dropdown", "sel": 0, "top": 0, "items": opts,
                         "block": block, "slot": slot["name"]}

    def _blk_open_expr_menu(self, block, name):
        """Open the expression chooser for an expr slot. Heads the list with "type a
        number" (the Scratch white oval -- a typed literal is the DEFAULT a kid wants),
        then every reporter block (operator / input / variable -- everything with an
        `expr` shape). Selecting "type a number" opens the number pad; selecting a
        block writes a fresh nested reporter into the slot."""
        ids = [_NUM_LITERAL_ITEM]
        for cat in _blocks_mod.categories():
            for bid in _blocks_mod.blocks_in_category(cat):
                if _blocks_mod.is_expr(bid):
                    ids.append(bid)
        self.blk_menu = {"mode": "expr", "sel": 0, "top": 0, "items": ids,
                         "block": block, "slot": name}

    def _blk_insert_expr(self, type_id):
        """Write a fresh expression block of `type_id` into the target expr slot."""
        m = self.blk_menu
        self.blocks_ed.set_slot(m["slot"], _blocks_mod.make_block(type_id), m["block"])
        self.blk_menu = None

    # -- save / graduate -----------------------------------------------------
    def save_blocks(self):
        """Compile-on-save the block program to blocks.json + main.py, surfacing
        SAVE_OK / a syntax problem like save_code does. Returns True on success.
        A non-SD/embedded cart just validates + applies in RAM."""
        ws = self.ws
        be = self.blocks_ed
        if not (be and ws.run.project.cart):
            return False
        if not ws.text.takes_blocks():
            # Blocks compile to Python: a Lua or compiled cart's code is never
            # theirs to write (moy_carts.is_python).
            self.blk_status = "BLOCKS ARE PYTHON -- NOT SAVED"
            return False
        if self.blk_graduated:
            # GRADUATED (Stage 8, spec Section 8): the kid has leveled up to code; the
            # blocks are a FROZEN, read-only render. Regenerating from them would
            # discard the diverged main.py, so SAVE refuses (the one-way door). The
            # only way back is undoing past the graduating commit (Stage 7 journal).
            self.blk_status = "LEVELED UP TO CODE"
            return False
        if self.blk_protect:
            # DATA-LOSS GUARD (#29): this cart's main.py is hand-written code that a
            # block save would replace. Refuse and tell the kid -- their code stays.
            self.blk_status = "CART HAS CODE -- NOT SAVED"
            return False
        # Drop scene objects the kid selected but never gave a block (#85/#93), so
        # blocks.json stays clean and an empty object never forces a draw_scene(). The
        # live editor keeps its entries (prune returns a copy), so the outline is
        # unchanged; a program with no objects is returned as-is (byte-identical).
        prog = _blocks_mod.prune_empty_objects(be.program)
        # Always compile-check first so the kid sees a problem before it persists.
        try:
            src = _blocks_mod.compile_blocks(prog)
        except Exception as exc:  # noqa: BLE001 -- BlockError on a corrupt tree
            self.blk_status = "BAD: " + self._err_text(exc)
            return False
        ok, msg = ws.carts_store.compile_check(src) if ws.carts_store else (True, "")
        if not ok:
            self.blk_status = "SYNTAX " + msg
            return False
        if not (ws.run.project.cart.get("path") and ws.can_manage and ws.carts_store):
            # nothing to persist (embedded / writes deferred): apply in RAM so RUN
            # works. A DEEP COPY, never the live tree (#93) -- the editor keeps
            # mutating `prog` in place and undo/redo rebinds it, so an aliased
            # cart["blocks"] would drift from what this save captured (mirrors
            # moy_carts.save_blocks' own snapshot copy).
            ws.run.project.cart["src"] = src
            ws.run.project.cart["blocks"] = _clone_tree(prog)
            be.dirty = False
            self.blk_status = None        # save is invisible (#111): no "SAVED"
            ws.ach.award("first_code")
            return True
        try:
            status, smsg = ws.with_sd(
                lambda: ws.carts_store.save_blocks(ws.run.project.cart, prog))
            if status != ws.carts_store.SAVE_OK:
                self.blk_status = "CAN'T SAVE " + str(smsg)
                return False
            be.dirty = False
            self.blk_status = None        # save is invisible (#111): no "SAVED"
            ws.ach.award("first_code")        # Code Wizard: a program saved
            ws.cart_error = None
            return True
        except Exception as exc:  # noqa: BLE001
            self.blk_status = "CAN'T SAVE"
            print("Moybyte save blocks failed:", self._err_text(exc))
            return False

    def graduate_to_code(self):
        """The one-way 'graduate to code' rung: compile the block program and open
        the generated main.py in the code editor, so a kid moves from blocks to text
        on the same cart. Saves first (so blocks.json + main.py are in lockstep), then
        switches to the code view on the freshly compiled source."""
        ws = self.ws
        be = self.blocks_ed
        if not (be and ws.run.project.cart):
            return
        if self.blk_protect or self.blk_graduated:
            # Protected (hand-written main.py) OR already GRADUATED (Stage 8): don't
            # recompile the blocks over the kid's real/diverged main.py. Just open the
            # code editor on the EXISTING source -- "graduate" here means "go edit the
            # code you already have" (for a graduated cart, that door is one-way).
            ws.editor = None
            self.blk_menu = None
            ws.text.set_menu_view("code")
            return
        try:
            src = _blocks_mod.compile_blocks(be.program)
        except Exception as exc:  # noqa: BLE001
            self.blk_status = "BAD: " + self._err_text(exc)
            return
        self.save_blocks()                       # persist (best-effort) before leaving
        ws.run.project.cart["src"] = src                     # ensure the editor opens the latest
        ws.editor = None                         # rebuild on the new source
        self.blk_menu = None
        ws.text.set_menu_view("code")

    # -- block-editor input / pointer ----------------------------------------
    def _blocks_input(self):
        """The outline's keys: up and down the cursor, right the slot, left a
        number's nudge, A acts, Enter saves; while a block moves, A drops it
        and B cancels. While the menu or a prompt is up the keys are the
        page's (the engine's), B backing the menu out a level and the
        console's cancel key closing a prompt."""
        ws = self.ws
        i = ws.input
        if self.blk_menu is not None or self.blk_kbd is not None:
            if self.blk_kbd is None and i.pressed("b"):
                self._blk_menu_back()
                ws.mark_dirty()
                return
            if self.blk_kbd is not None and i.pressed("stop"):
                self._blk_kbd_cancel()
                ws.mark_dirty()
                return
            self._sync()
            self.page().keys(i)
            return
        be = self.blocks_ed
        if be is not None and be.moving():
            # MOVE mode (#93) is modal: nav to a destination, A drops it at an insert
            # point, B cancels. (A/complete + the cancel are the only exits, so
            # BACKSPACE/B doesn't leave the editor mid-move.)
            if i.steps("up"):
                self._blk_move_cursor(-1)
            if i.steps("down"):
                self._blk_move_cursor(1)
            if i.pressed("a"):
                self._blk_a()
            elif i.pressed("b"):
                be.cancel_move()
                self.blk_status = "MOVE OFF"
            return
        if i.steps("up"):
            self._blk_move_cursor(-1)
        if i.steps("down"):
            self._blk_move_cursor(1)
        if i.steps("right"):
            self._blk_next_slot()                # step the highlighted slot
        if i.steps("left"):
            # left on a number slot decrements it (a quick tweak without the menu)
            self._blk_left()
        if i.pressed("a"):
            self._blk_a()
        elif i.pressed("run"):
            self.save_blocks()
        else:
            ws.home.leave_or_home(ws.spine.exit)

    def _blk_left(self):
        be = self.blocks_ed
        if be is None:
            return
        b = be.selected_block()
        slots = be.slots(b)
        if not slots:
            return
        slot = slots[self.blk_slot % len(slots)]
        if slot["type"] == _blocks_mod.SLOT_NUMBER:
            self._blk_bump_number(b, slot["name"], -1)
        elif slot["type"] == _blocks_mod.SLOT_DROPDOWN:
            be.cycle_dropdown(slot["name"], -1, b)
        elif slot["type"] == _blocks_mod.SLOT_EXPR:
            # quick -1 nudge on an expr slot holding a numeric literal (a block in the
            # slot is left alone -- you can't decrement an expression).
            cur = (b.get("p", {}) or {}).get(slot["name"])
            if _blocks_mod.is_literal_value(cur) and isinstance(cur, (int, float)) \
                    and not isinstance(cur, bool):
                self._blk_bump_number(b, slot["name"], -1)

    def _blocks_pointer(self, px, py, click):
        """A pointer sample on the tab, in SYSTEM coords: the bar's first,
        then the page's (a row's tap finds its slot by the press's x)."""
        ws = self.ws
        if click:
            self._px = px
            if self.blk_kbd is None and ws.bar_layer.handle_bar_tap("menu", px, py):
                return
        self._sync()
        self.page().point(px, py, click)

    def pointer(self):
        """The pointer, where the page's host reads whether it is held."""
        return self.ws.pointer

    def _blk_tap_row(self, ridx, px, again):
        """A tap on outline row `ridx` at x `px` (the page's table answers
        it): a first selects the row and the slot tapped, so the next tap
        edits that argument; `again`, a tap on the selected row, acts on it
        (insert / edit) -- the A action. While a block moves, a tap re-homes
        the cursor, and on an insert point drops the block there."""
        be = self.blocks_ed
        if be is None or not 0 <= ridx < len(be.rows):
            return
        row = be.rows[ridx]
        if be.moving():
            be.cur = ridx
            self.blk_slot = 0
            if row.kind == "insert":
                self._blk_a()
            return
        if not again:
            be.cur = ridx
            self.blk_slot = 0
        if row.kind == "block" and not row.is_else:
            si = self._blk_slot_at_x(row.block, self._row_x(row), px)
            if si is not None:
                self.blk_slot = si
        if again:
            self._blk_a()
        self.ws.mark_dirty()

    def _blk_num_to_block(self):
        """From the number pad, switch to dropping a reporter BLOCK into the slot
        (the Scratch white-oval -> drop-a-block move). Discards the typed number and
        opens the expr chooser on the same slot."""
        k = self.blk_kbd
        if k is None:
            return
        block, name = k["block"], k["slot"]
        self.blk_kbd = None
        self._blk_open_expr_menu(block, name)

    # -- the page ----------------------------------------------------------------

    def _draw_blocks(self, dt=0):
        """The Blocks tab: the page in the content rect, no stop holding
        focus but the menu's and a prompt's, and the bar's strip."""
        ws = self.ws
        lay = self.block_layout
        r = self._rect
        if r is None or r[0] != lay.cx or r[1] != lay.cy or r[2] != lay.cw or r[3] != lay.ch:
            r = self._rect = (lay.cx, lay.cy, lay.cw, lay.ch)
        desk = _layout_base.metric_class() == _layout_base.DESK
        cv = ws.sys_canvas
        pg = self.page()
        up = self.blk_menu is not None or self.blk_kbd is not None
        pg.band = self.blk_kbd is not None          # a prompt's keys in the band
        self._host.begin(cv, ws.theme_colors, r, desk, False, not up)
        self._sync()
        pg.paint(dt, cv, ws.theme_colors, r, desk)
        self._host.end()
        ws.bar_layer.draw_status_strip("menu")
        if not self._host.still():
            ws.request_frame()

    def _sync(self):
        """The core's state the page shows, handed to its `sync` hook where
        it moved, and a prompt opened or closed by the host."""
        be = self.blocks_ed
        m = self.blk_menu
        k = self.blk_kbd
        if k is not None and k["gen"] != self._asked:
            self._asked = k["gen"]
            self.run("ask", self._ask_vals(k))
        elif k is None and self._asked:
            self._asked = 0
            if self.s.asking:
                self.run("asked")
        if be is None:
            vals = (True, False, "", [], "", [], "", False, False, "", [], 0, self.row_h())
            if vals != self._shown:
                self._shown = vals
                self.run("sync", vals)
            return
        g = self._made
        lay = self.block_layout
        st = self.blk_status
        se = self.ws.scene_ui.sceneedit
        sg = se._hist.gen if se is not None else -1
        lg = self.ws.look.look_gen
        mode = m["mode"] if m is not None else None
        if not (g[0] is be and g[1] == be._hist.gen and g[2] == be.target and g[3] == len(be.rows)
                and g[4] == be.moving() and g[5] is st and g[6] == self.blk_graduated
                and g[7] is m and g[8] == mode and g[9] is se and g[10] == sg and g[11] == lg
                and g[12] is lay):
            g[0], g[1], g[2], g[3], g[4] = be, be._hist.gen, be.target, len(be.rows), be.moving()
            g[5], g[6], g[7], g[8], g[9] = st, self.blk_graduated, m, mode, se
            g[10], g[11], g[12] = sg, lg, lay
            status = ""
            if st:
                status = st[:1].upper() + st[1:].lower()
            objs, obj = self._objects(be, status)
            lines = self._lines(be)
            vals = (False, self.blk_graduated, status, objs, obj, lines, self._at(be),
                    be.moving(), m is not None, MENU_TITLES.get(mode, "Pick") if m else "",
                    [dict(k=str(i), label=self.menu_word(i)) for i in range(len(m["items"]))] if m else [],
                    min(m["sel"], len(m["items"]) - 1) if m and m["items"] else 0, self.row_h())
            if vals != self._shown:
                was = self._shown or (None,) * 13
                self._shown = vals
                # the models the page holds already left out
                self.run("sync", tuple(None if i in (3, 5, 10) and vals[i] == was[i] else vals[i]
                                       for i in range(13)))
                self._at_shown = None           # the rows made again: the cursor's marked anew
        # a move of the cursor or its slot alone: the rows it left and it is on
        at = self._at(be)
        if at is not self._at_shown or self.blk_slot != self._slot_shown:
            self.run("marked", (self._at_shown, at, self.blk_slot + 1))
            self._at_shown = at
            self._slot_shown = self.blk_slot

    def row_h(self):
        """An outline row's height in pixels: ROW in the page's unit (the
        font scale on a handheld, 1 on the desk), taller where the text is
        (a desk's Large and Largest)."""
        fs = self.block_layout.fs
        desk = _layout_base.metric_class() == _layout_base.DESK
        return max(ROW * (1 if desk else fs), _ui_draw.font("ui")[3] * fs + 6)

    def _at(self, be):
        """The cursor's row's key, the one its row was made with."""
        rows = self._rows
        return rows[be.cur]["k"] if 0 <= be.cur < len(rows) else ""

    def _ask_vals(self, k):
        """The page's dialog for prompt `k`: (its title, the name rule
        shown, the field's caption, its placeholder, Use a block offered)."""
        kind = k.get("kind")
        if kind == "num":
            cur = k.get("cur")
            hint = str(cur) if _blocks_mod.is_literal_value(cur) and cur is not None else "0"
            cap = str(k.get("slot") or "Number").replace("_", " ")
            cap = cap[:1].upper() + cap[1:]
        else:
            hint = "" if kind == "text" else str(k.get("var", ""))
            cap = _KBD_CAPTIONS.get(kind, "Name")
        return (_KBD_TITLES.get(kind, "Name your variable"), kind not in ("num", "text"), cap,
                hint[:24], bool(kind == "num" and k.get("allow_block")))

    def _objects(self, be, status):
        """The objects' tabs: the Stage, then each object with scripts or on
        the stage while the head holds them beside the status word; and the
        picked one's key (an index)."""
        w = self.block_layout.cw
        fs = self.block_layout.fs
        was = _ui_font.print_face("ui")
        sw = min(_ui_font.print_size(status, fs)[0] + 4 * fs, w // 2) if status else 0
        room = w - 16 * fs - sw - 8 * fs - (_ui_font.print_size("Stage", fs)[0] + 20 * fs)
        tags = self._tags
        del tags[:]
        cur = 0
        for t in self._roster_tags():
            tw = _ui_font.print_size(t, fs)[0] + 20 * fs
            if tw > room:
                break
            room -= tw
            tags.append(t)
            if t == be.target:
                cur = len(tags)
        _ui_font.print_font(was)
        objs = [dict(k="0", name="Stage")] + [dict(k=str(i + 1), name=t) for i, t in enumerate(tags)]
        return objs, str(cur)

    def _lines(self, be):
        """The outline's rows: each its index and what it shows -- its kind,
        depth and label -- so a frame draws the rows that changed."""
        rows = []
        for i in range(len(be.rows)):
            row = be.rows[i]
            if row.kind == "insert":
                sig = "+%d" % row.depth
            else:
                sig = "%d %d %s" % (row.depth, row.is_else, self._blk_row_text(row.block, row.is_else))
            rows.append(dict(k=str(i), sig=sig, on=0))
        self._rows = rows
        self._looks = [None] * len(rows)
        return rows

    def _row_x(self, row):
        """Outline row `row`'s left edge on the canvas, by its depth."""
        fs = self.block_layout.fs
        return self._ox + 8 * fs + row.depth * INDENT * fs

    def _look(self, i, row):
        """Row `i`'s look, made at its first draw: [label, plate width,
        fill, ink, hat, label height] (None for an insert point)."""
        lk = self._looks[i]
        if lk is None and row.kind != "insert":
            b = row.block
            fs = self.block_layout.fs
            label = self._blk_row_text(b, row.is_else)
            fill = self._cat_color("control" if row.is_else else self._blk_block_cat(b))
            hat = not row.is_else and self._is_hat_block(b)
            tw, lh = _ui_font.print_size(label, fs)
            lk = self._looks[i] = [label, tw + (20 if hat else 22) * fs, fill,
                                   self._blk_ink(fill) if hat else None, hat, lh]
        return lk

    def draw_row(self, cv, i, x, y, w, h):
        """Outline row `i` in its part: a hat on its category's colour, a
        statement on a plate with its category's bar (the cursor's slot
        underlined), or an insert point (the cursor's as "add block")."""
        be = self.blocks_ed
        if be is None or not 0 <= i < len(be.rows) or i >= len(self._looks):
            return
        self._ox = x
        th = self.ws.theme_colors
        fs = self.block_layout.fs
        row = be.rows[i]
        cursor = i == be.cur
        rx = self._row_x(row)
        rw = x + w - 8 * fs - rx
        was = _ui_font.print_face("ui")
        look = self._look(i, row)
        if look is None:
            if cursor:
                aw = _ui_font.print_size("add block", fs)[0] + 40 * fs
                _ui_draw.button(cv, th, (rx, y + fs, min(rw, aw), h - 2 * fs), "add block",
                                "tonal", glyph="plus", glyph_draw=self._add_icon)
            else:
                cv.rect(rx + 2 * fs, y + h // 2 - fs, 10 * fs, 2 * fs, th["border"])
            _ui_font.print_font(was)
            return
        label, fill = look[0], look[2]
        tw = min(rw, look[1])
        ph = h - 2 * fs
        py = y + fs
        if look[4]:
            cv.rrect(rx, py, tw, ph, 6 * fs, fill)
            ink = look[3]
            tx = rx + 10 * fs
        else:
            cv.rrect(rx, py, tw, ph, 5 * fs, th["surface_alt"])
            cv.rrect(rx, py, 3 * fs, ph, fs, fill)
            ink = th["ink"]
            tx = rx + 9 * fs
        ty = py + (ph - look[5]) // 2
        cv.print(label, tx, ty, ink, 1)
        if cursor and not row.is_else:
            self._draw_caret(cv, th, row.block, label, tx, ty + look[5])
        _ui_font.print_font(was)

    def _add_icon(self, kind, rect, ink, cv):
        """"add block"'s icon: the theme's icon set's `new`, else the plus glyph."""
        if not self.ws.draw_icon("new", rect, ink, cv):
            _ui_draw.glyph(cv, kind, rect, ink)

    def _draw_caret(self, cv, th, b, label, tx, y):
        """The selected slot's value underlined, what A and left and right
        change."""
        c = self._caret
        if c[0] is not b or c[1] != self.blk_slot:
            c[0] = b
            c[1] = self.blk_slot
            c[2] = None
            slots = self.blocks_ed.slots(b)
            if slots:
                si = self.blk_slot % len(slots)
                col = self._blk_slot_text_col(b, si)
                if col is not None:
                    val = self._blk_slot_display(b, slots[si])
                    fs = self.block_layout.fs
                    c[2] = _ui_font.print_size(label[:col], fs)[0]
                    c[3] = max(4 * fs, _ui_font.print_size(val, fs)[0])
        if c[2] is not None:
            cv.rect(tx + c[2], y, c[3], 2 * self.block_layout.fs, th["value"])

    def menu_word(self, k):
        """The menu's row `k` as it reads: the item's label, a category's in
        sentence case."""
        word = self._blk_menu_label(k)
        if word.isupper():
            word = word[:1] + word[1:].lower()
        return word

    # -- the page's handlers -----------------------------------------------------------

    def pick_row(self, i):
        """A tap moved the outline's cursor to row `i`: it and the slot under
        the press."""
        self._blk_tap_row(i, self._px, False)

    def open_row(self, i):
        """A tap on the cursor's row: it acts (insert, edit its slot)."""
        self._blk_tap_row(i, self._px, True)

    def pick_object(self, key):
        """An object's tab taken: its scripts."""
        n = int(key) if key else 0
        self._select_sprite(None if n == 0 or n > len(self._tags) else self._tags[n - 1])
        self.blk_slot = 0
        self.ws.mark_dirty()

    def menu_pick(self, i):
        m = self.blk_menu
        if m is not None and 0 <= i < len(m["items"]):
            m["sel"] = i
            self._blk_menu_select()
        self.ws.mark_dirty()

    def menu_back(self):
        self._blk_menu_back()
        self.ws.mark_dirty()

    def typed(self, text):
        """What the open prompt takes of `text` (a number's digits, a name's
        letters), its entry's text."""
        k = self.blk_kbd
        if k is None:
            return text
        entry = k["entry"]
        t = ""
        for ch in text:
            t, _ev = _text_key(t, ord(ch), entry.cap, entry.allow)
        entry.text = t
        return t

    def ask_done(self, how, text):
        """The prompt's dialog let go: "ok" commits what was typed, "cancel"
        drops it, "block" puts a reporter block in its slot instead."""
        if self.blk_kbd is None:
            return
        self.typed(text)
        self._asked = 0
        if how == "block":
            self._blk_num_to_block()
        elif how == "ok":
            self._blk_kbd_commit()
        else:
            self._blk_kbd_cancel()
        self.ws.mark_dirty()

    def act(self, verb):
        """A foot tool's verb: add, delete, up, down, more, or code (See
        code)."""
        be = self.blocks_ed
        if be is None:
            return
        if verb == "add":
            self._blk_open_categories()
        elif verb == "delete":
            be.delete()
            self.blk_slot = 0
        elif verb in ("up", "down"):
            be.move_block(-1 if verb == "up" else 1)
        elif verb == "more":
            self._blk_open_actions()
        elif verb == "code":
            self.ws.defer(self.graduate_to_code)
        self.ws.mark_dirty()

    def _blk_ink(self, fill_idx):
        """Black or white text, whichever reads on the fill colour (luminance)."""
        try:
            r, g, b = self.ws.sys_canvas.palette[fill_idx]
        except Exception:  # noqa: BLE001 - a non-RGB palette entry
            return self._NAMES["white"]
        return self._NAMES["black"] if (r * 30 + g * 59 + b * 11) > 13000 \
            else self._NAMES["white"]

    def _is_hat_block(self, b):
        d = _blocks_mod.block_def(b.get("t"))
        return bool(d) and d.get("shape") == _blocks_mod.SHAPE_HAT

    def _cat_color(self, cat):
        """A block category's colour: the theme's `block_<category>` content
        role (the Scratch look by default), dark grey for no category."""
        c = self.ws.look.content_colors().get("block_" + str(cat))
        return self._NAMES["dark_grey"] if c is None else c

    def _blk_block_cat(self, b):
        d = _blocks_mod.block_def(b.get("t"))
        return d["category"] if d else "control"

    def _blk_row_text(self, b, is_else=False):
        """Render a block's inline label: the catalog template with each {slot}
        replaced by its value's compact display (a literal, a color/button name, a
        variable, or a compact expression). Mirrors the Scratch-style inline look."""
        if is_else or b.get("t") == _blocks_mod.ELSE_MARKER:
            return "else"
        d = _blocks_mod.block_def(b.get("t"))
        if d is None:
            return str(b.get("t"))
        # Program-aware label + slots (#48): proc_def reads "define NAME p1 p2" and a
        # call reads "NAME {arg0} {arg1}" (one hole per proc parameter); every other
        # block is its static catalog label. The rest of the inline fill is unchanged.
        prog = self.blocks_ed.program if self.blocks_ed is not None else {}
        out = ""
        tmpl = _blocks_mod.block_label(prog, b)
        i = 0
        n = len(tmpl)
        slot_by_name = {}
        for s in _blocks_mod.block_slots(prog, b):
            slot_by_name[s["name"]] = s
        while i < n:
            ch = tmpl[i]
            if ch == "{":
                j = tmpl.find("}", i)
                if j < 0:
                    out += ch
                    i += 1
                    continue
                name = tmpl[i + 1:j]
                slot = slot_by_name.get(name)
                out += self._blk_slot_display(b, slot) if slot else name
                i = j + 1
            else:
                out += ch
                i += 1
        return out

    def _blk_slot_text_col(self, b, si):
        """The character column where slot `si`'s value starts in the rendered row
        label (so the caret underlines the right run). None if it can't be found."""
        prog = self.blocks_ed.program if self.blocks_ed is not None else {}
        bslots = _blocks_mod.block_slots(prog, b)
        if si >= len(bslots):
            return None
        target = bslots[si]["name"]
        tmpl = _blocks_mod.block_label(prog, b)
        col = 0
        i = 0
        n = len(tmpl)
        while i < n:
            ch = tmpl[i]
            if ch == "{":
                j = tmpl.find("}", i)
                if j < 0:
                    col += 1
                    i += 1
                    continue
                name = tmpl[i + 1:j]
                slot = None
                for s in bslots:
                    if s["name"] == name:
                        slot = s
                        break
                disp = self._blk_slot_display(b, slot) if slot else name
                if name == target:
                    return col
                col += len(disp)
                i = j + 1
            else:
                col += 1
                i += 1
        return None

    def _blk_slot_at_x(self, b, row_x, px):
        """Which slot of block `b` the tap `px` falls on (its value's character run in
        the rendered row), or None if the tap missed every slot. Lets a kid tap the
        SECOND argument (or any) directly, Scratch-style, instead of stepping with the
        right-arrow. `row_x` is the row's left edge; the label prints at row_x + 3*fs."""
        lay = self.block_layout
        be = self.blocks_ed
        if be is None:
            return None
        slots = be.slots(b)
        if not slots:
            return None
        col = (px - (row_x + 3 * lay.fs)) // lay.cell
        if col < 0:
            return None
        for si in range(len(slots)):
            c0 = self._blk_slot_text_col(b, si)
            if c0 is None:
                continue
            disp = self._blk_slot_display(b, slots[si])
            if c0 <= col < c0 + max(1, len(disp)):
                return si
        return None

    def _blk_slot_display(self, b, slot):
        """A compact string for one slot's current value (for the inline row)."""
        name = slot["name"]
        val = (b.get("p", {}) or {}).get(name)
        t = slot["type"]
        if t == _blocks_mod.SLOT_EXPR:
            return self._blk_expr_display(val)
        if t == _blocks_mod.SLOT_TEXT:
            return '"' + str(val) + '"'
        if val is None:
            return "0" if t == _blocks_mod.SLOT_NUMBER else "?"
        return str(val)

    def _blk_expr_display(self, val):
        """A compact, brace-free rendering of an expression slot value: a literal
        stays itself; an expression block renders its own label recursively (so a
        nested `(x + 1)` reads inline)."""
        if val is None:
            return "0"
        if isinstance(val, dict):
            return self._blk_row_text(val)
        if isinstance(val, str):
            return '"' + val + '"'
        return str(val)
