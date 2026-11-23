"""The host of a desk Editor pane's header page (editor_head.py): one
`HeadHost` a shown pane, by its index, on the pane's rect (the header its
page's top row, a more menu hung over the pane under it). The desk hands
it the pane's state each frame it draws (`EditorDesk.head_vals`); what
its buttons ask goes back to the desk (`EditorDesk.head_act`)."""
from view_host import PageHost


class HeadHost(PageHost):
    """Pane `n`'s header on the desk `desk`."""

    def __init__(self, desk, n):
        import editor_head
        PageHost.__init__(self, desk.ws, None, "head %d" % n, editor_head.head_page)
        self.desk = desk
        self.n = n
        self.pane = None                # the pane it heads, as drawn last
        self.vals = None                # its state, as the desk handed it last
        self.pop = False                # a more menu of its is open

    def _sync(self):
        if self.vals is not None:
            self.push(self.vals)

    def draw(self, pane, r, vals, keys, dt):
        """The header of `pane` at its rect `r` with state `vals`; `keys`
        whether the keys are in it (its focus shows)."""
        ws = self.ws
        cv = ws.sys_canvas
        th = ws.theme_colors
        self.pane = pane
        self.vals = vals
        pg = self._page()
        if self._rect != r:
            self._rect = r
        self._host.begin(cv, th, r, True, False, not keys)
        self._sync()
        pg.paint(dt, cv, th, r, True)
        self._end()
        if not self._host.still():
            ws.request_frame()

    def open_pop(self, which):
        """Its more menu ("more", "code") opened by the host."""
        self.run("open_pop", which)
        self.pop = True

    def close_pop(self):
        if self.pop:
            self.run("close_pop")

    def box(self, key):
        """Where the last frame drew its stop `key` (None before it drew)."""
        return self._host.box(key)

    def act(self, verb, *args):
        if verb == "opened":
            self.pop = True
        elif verb == "closed":
            self.pop = False
        self.desk.head_act(self, verb, *args)
