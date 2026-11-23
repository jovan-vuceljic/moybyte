# Map (grep -n a name to jump there):
#   IconHome                     the icons arrangement: tiles that scroll down, a caption band
"""The home's ICONS arrangement (docs/history/look_2026-10.md step 33), the
layout's `home: icons`: each cart's icon -- its cover's reduction -- in a
tile, as many columns as the glass holds across, scrolling down. On the
handheld the focused cart is named in one caption band at the grid's foot;
on the desk every tile is named under it. A `Launcher` (home_grid.py): the
same selection model over the engine's icons (`ui.cards(look="icons")`,
`home_ui.icons`).
"""

from home_grid import _cover_div_for, _COVER_HALF, Launcher, PSEUDO_TILE_TYPES


class IconHome(Launcher):
    """The home's icons arrangement (docs/history/look_2026-10.md step 33): each
    cart's icon -- its cover's reduction -- in a tile with the card radius,
    as many columns as the glass holds across, scrolling down; focus grows
    a tile and rings it flat, as the shelf's does. On the handheld no tile
    carries a label: the focused cart's name and its line sit in one
    caption band at the grid's foot, over the hint strip, which clips the
    top of the next row so the grid reads as scrolling. On the desk every
    tile is named in full under it, the focused one bold. Its geometry, its
    motion and its words are the engine's; its faces the home's."""

    arrangement = "icons"
    horizontal = False
    page_fn = "icons"

    def _face_div(self, n):
        """A handheld tile's picture is its cover's half decode."""
        return _cover_div_for(n) if self._cells().desk else _COVER_HALF

    def cover_specs(self):
        return [(it, _COVER_HALF) for it in self.items
                if it.get("path") and it.get("type") not in PSEUDO_TILE_TYPES]
