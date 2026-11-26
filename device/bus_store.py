"""The cart store of a board whose TF card SHARES the panel's SPI host (the
T-Deck's and the CoreS3's): the card when it takes the store, internal flash
when it does not, and the bracket every store write goes through.

A board constructs one `BusStore(comp, carts, flash_root, flash_update)` over
its compositor (whose `sd_bracket` is native/moy_lcd's SD guard) and hands
`load` and `session` to the spine (`device/desktop_spine.py`'s `load_carts` and
`with_sd`).
"""

from device_util import _ticks_ms, _ticks_diff


class BusStore:
    """This boot's store -- the TF card when it takes the store, internal
    flash when it does not -- and the SESSION every store write goes through.

    Every SD session on this board is drained first and the panel SERIALIZED
    for the session's whole span (comp.sd_bracket -> moy_lcd's sd_guard). The
    bracket exists because the seed/scan PAINTS a progress frame per cart
    INSIDE the session, and since the core-0 feeder (2026-08-21) an
    unbracketed paint queues panel bands from core 0 while the VM sits inside
    an sdspi transaction on the same SPI host -- measured as a Cache/MMU panic
    at "loading cartridges 1/35". `comp.sync()` is load-bearing now that the
    flush overlaps: a frame's bands can still be in flight, and an SD op that
    overlaps a panel DMA on the shared host is the documented way to hang
    this board.

    The TRACE is the diagnostic (#183). An editor commit can wedge this board
    with nothing on serial, so each phase says its name and whichever line is
    LAST before the silence identifies the op:
      "SD > sync" -- the pre-op drain
      "SD > op"   -- the SD write itself
      "SD < op"   -- the NEXT PANEL FLUSH, i.e. the shared-bus corruption;
                     "SD = panel ok" (the frame tail) is what says it did not
                     happen.
    It prints only under PERF DIAG (`ws`, handed over once the console
    exists): a compiled cart streaming its data file opens several sessions a
    second.
    """

    def __init__(self, comp, carts, flash_root, flash_update, trace=True):
        self._comp = comp
        self._carts = carts
        self._flash_root = flash_root
        self._flash_update = flash_update
        self._trace = trace
        self.on_sd = False      # did the card take the store this boot
        self.traced = False     # a traced session awaits its "panel ok"
        self.ws = None          # the console, whose diag_live gates the trace

    def _bracketed(self, fn, trace=False):
        # Allocation-free on purpose: a compiled cart streaming its data file
        # comes through here several times a second, so the trace prints its
        # numbers as print() arguments rather than formatted strings, and the
        # bracket is called as a method rather than fetched as a bound one.
        if trace:
            print("SD > sync")
        t = _ticks_ms()
        comp = self._comp
        comp.sync()
        if trace:
            print("SD > op (sync ", _ticks_diff(_ticks_ms(), t), "ms)", sep="")
            t = _ticks_ms()
        bracket = hasattr(comp, "sd_bracket")
        if bracket:
            comp.sd_bracket(True)
        try:
            import moybyte_sd
            return moybyte_sd.with_sd_live(fn)
        finally:
            if bracket:
                comp.sd_bracket(False)
            if trace:
                print("SD < op ", _ticks_diff(_ticks_ms(), t), "ms", sep="")
                self.traced = True

    def load(self, boot, store):
        """The cart store: seed + scan on the card, bracketed (`with_sd_live`
        attaches once and keeps the card resident); internal flash when there
        is no card. The OTA directory goes wherever the store went -- an
        updater aimed at /sd/update on a card-less board would look on a card
        that is not there."""
        carts, root = boot.load_carts(store, self._carts, session=self._bracketed,
                                      media="SD",
                                      fallback_root=self._flash_root)
        self.on_sd = root is not None and root.startswith("/sd")
        return carts, root, (None if self.on_sd else self._flash_update)

    def session(self, fn):
        """Every store op: the bracket while the card is the store; a plain
        call while internal flash is -- it shares no bus with the panel, and
        routing it through the bracket would fail every write."""
        if not self.on_sd:
            return fn()
        return self._bracketed(fn, self._trace and bool(
            getattr(self.ws, "diag_live", False)))
