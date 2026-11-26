"""About's Storage row names the store of record's free space (issue 270): a
page a board serves shows the BOARD's, as its last Get Carts check said, and
never the browser VM's own memory, which read "1.9 GB free" on a C3 Zero."""

from ws_helpers import build_ws


class _Board:
    def __init__(self, room):
        self.room = room

    def free(self):
        return self.room


def test_a_board_served_page_shows_the_boards_free_space_or_none(tmp_path):
    ws = build_ws(tmp_path)
    sl = ws.settings_layer
    assert sl._free() is not None, "the host's own store"
    ws.cart_home = "board"
    ws.cart_board = _Board(None)
    assert sl._free() is None, "no check yet: no figure, never the VM's"
    ws.cart_board = _Board((1536 * 1024, 4096))
    assert sl._free() == "1.5 MB free"
    ws.cart_board = None
    assert sl._free() is None


def test_the_storage_row_says_whose_space_it_is(tmp_path):
    """The browser's own storage reads as the browser's, a served board's
    as the board's (issue 270), a console's as its storage."""
    ws = build_ws(tmp_path)
    sl = ws.settings_layer
    assert sl._storage_word() == "Storage"
    ws.cart_keep = object()
    assert sl._storage_word() == "Browser storage"
    ws.cart_home = "board"
    assert sl._storage_word() == "Board storage"


def test_board_carts_keeps_the_free_space_its_check_said():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "firmware" / "web_runner"))
    try:
        import carts_link
    finally:
        sys.path.pop(0)
    b = carts_link.BoardCarts(link=None, root="/moy/carts")
    assert b.free() is None
    b.room = [2048, 4096]
    assert b.free() == (2048, 4096)
