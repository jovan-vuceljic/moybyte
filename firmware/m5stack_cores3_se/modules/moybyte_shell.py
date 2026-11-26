"""Moybyte CoreS3 SE boot shell: pick a boot mode and run it.

The ladder is `device/boot_shell.py`'s, shared by every console board; the
smokes are `cores3_smoke`'s, each self-terminating, reachable from the REPL:

    import moybyte_shell as s; s.MODE = "panel"; s.main()
"""

import boot_shell

BOARD = "CoreS3 SE"
SMOKE = "cores3_smoke"

MODE = "desktop"

MODES = ("panel", "touch", "pad", "desktop")


def main():
    boot_shell.main(BOARD, MODE, MODES, SMOKE)
