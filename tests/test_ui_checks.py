"""The #272 checks (tests/ui_checks.py) catch what they are for: here, a
band hint that draws a key the board's input does not have."""

import ui_checks


class _Band:
    """What `ui_checks.hints` reads of an engine: its input, its band and
    the band's hints."""

    decl = None
    pages = ()
    band = True

    def __init__(self, input, hints):
        self.input, self._hints = input, hints

    def hints(self):
        return self._hints


def test_an_action_draws_the_keys_of_the_input():
    assert ui_checks.action_keys("keys", "back") == "Esc"
    assert ui_checks.action_keys("tdeck", "back") == "K"
    assert ui_checks.action_keys("tdeck", "cancel") == "Mic"
    assert ui_checks.action_keys("pad", "back") == "B"


def test_the_tdeck_band_names_no_esc():
    assert ui_checks.hints(_Band("tdeck", ("confirm", "Use", "back", "Back")), False) == []
    found = ui_checks.hints(_Band("tdeck", ("back", "Back", "Esc", "Back")), False)
    assert len(found) == 1 and "'Esc'" in found[0], found


def test_every_action_draws_keys_its_input_has():
    for input, have in ui_checks.KEYS.items():
        for act in ui_checks.ACTIONS:
            for k in ui_checks.action_keys(input, act).split():
                assert k in have or k in ui_checks.ACT_BEYOND.get(input, ()), (input, act, k)
