"""The Terminal (runtime/apps/terminal_app.py's TerminalAppLayer): the C
shell's screen face in the console, over the host binding of the session
(runtime/host/moy_sh.py) and the console's own ROLE door. What a typed line
does, Tab, the history, Ctrl-C at the prompt and inside a run, and that an
idle frame makes nothing."""

import os
import sys
import time

import pytest

from runtime import native_build

if native_build.cc() is None:
    pytest.skip("no C compiler", allow_module_level=True)


@pytest.fixture
def term(tmp_path):
    from runtime.host_app import build_workstation
    ws = build_workstation(str(tmp_path / "carts"))
    app = ws.app("terminal")
    app.open()
    app.draw(0)                         # the first frame sizes the grid
    yield ws, app
    app.close_session()


def run(app, text):
    app.face.set_line(text)
    app.face.submit()
    settle(app)


def settle(app, limit=10.0):
    """The frames' tails until the line's run ends: a run that waits parks
    (native/moy_sh/moy_sh_board.h) and the loop's job resumes it."""
    from runtime import moy_sh
    t0 = time.monotonic()
    while app.face.busy() and time.monotonic() - t0 < limit:
        moy_sh.jobs()
        time.sleep(0.002)


def plain(app):
    import re
    app.face.take()
    return [re.sub("\x1b\\[[0-9;]*m", "", ln) for ln in app.face.lines()]


def test_the_terminal_is_a_system_app_on_its_identity_cart(term):
    ws, app = term
    cart = [c for c in ws.carts.all if c.get("title") == "Terminal"]
    assert cart and app.is_app(cart[0])
    assert ws.app("terminal") is app


def test_a_line_is_echoed_and_run_in_the_session(term):
    _ws, app = term
    run(app, "echo hello; mkdir /made; cd /made; pwd")
    assert plain(app) == ["$ echo hello; mkdir /made; cd /made; pwd", "hello", "/made"]
    assert app.face.lines()[0] == ("\x1b[2m$ \x1b[38;2;41;173;255m"
                                   "echo hello; mkdir /made; cd /made; pwd\x1b[0m")


def test_a_command_that_goes_on_takes_the_continuation_prompt(term):
    _ws, app = term
    run(app, "for i in 1 2")
    assert app.face.more() and app.face.prompt() == "> "
    run(app, "do echo $i; done")
    assert not app.face.more() and plain(app)[-2:] == ["1", "2"]
    run(app, "if true")
    app.face.key(3)                     # Ctrl-C drops what `more` held
    assert not app.face.more() and plain(app)[-1] == "> ^C"
    run(app, "echo after")
    assert plain(app)[-1] == "after"


def _command(root, cid, perms):
    import json
    d = root / (cid + ".moy")
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({
        "format": "moy-1", "title": cid, "id": cid, "runtime": "python", "main": "main.py",
        "moybyte": {"type": "command", "permissions": list(perms)}}))
    (d / "main.py").write_text("def main(argv):\n    print('ran', *argv[1:])\n")


@pytest.mark.first_run
def test_a_first_run_asks_at_the_prompt_and_the_next_line_answers(tmp_path):
    """A command nobody consented to asks as the shell's prompt, the rest of
    its line held; the next line typed answers, and the line runs again with
    it (all of it: dash parses a line as one command), showing only what
    follows the answer. No run waits on the terminal for it."""
    from runtime.host_app import build_workstation
    root = tmp_path / "carts"
    _command(root, "local.greet", ["http"])
    _command(root, "local.other", ["http"])
    ws = build_workstation(str(root))
    app = ws.app("terminal")
    app.open()
    app.draw(0)                         # the first frame sizes the grid
    try:
        run(app, "echo before; greet one; echo after")
        got = plain(app)
        assert got[1] == "before" and "after" not in got and "ran one" not in got, got
        assert app.face.prompt() == "Open it? [y/N] " and not app.face.busy()
        assert ws.consent.get("local.greet") is None
        run(app, "y")
        got = plain(app)
        assert got[-3:] == ["Open it? [y/N] y", "ran one", "after"], got
        assert got.count("before") == 1, "the re-run's output before its answer was shown"
        assert app.face.prompt() == "$ "
        assert ws.consent.get("local.greet") == {"perms": ["http"], "off": []}
        run(app, "greet two")
        assert plain(app)[-1] == "ran two"
        run(app, "other")
        run(app, "")                    # Enter alone is a no
        got = plain(app)
        assert got[-1] == "other: needs your OK - open it to say yes", got
        assert ws.consent.get("local.other") is None and app.face.prompt() == "$ "
        run(app, "other")
        app.face.key(3)                 # Ctrl-C drops the question
        assert app.face.prompt() == "$ "
        run(app, "echo fine")
        assert plain(app)[-1] == "fine"
    finally:
        app.close_session()


def test_tab_completes_a_command_and_a_path(term, tmp_path):
    ws, app = term
    f = app.face
    f.set_line("ech")
    f.key(9)
    assert f.line() == "echo "
    f.set_line("e")
    f.key(9)
    assert f.line() == "e" and f.cands() == ["echo", "edit", "eval", "exec", "exit", "export"]
    assert plain(app)[-1] == "echo  edit  eval  exec  exit  export"
    f.pick(4)
    assert f.line() == "exit " and f.cands() == []
    run(app, "mkdir /tree; mkdir /tree/alpha; mkdir /tree/apex; touch /tree/beta")
    f.set_line("ls /tree/al")
    f.key(9)
    assert f.line() == "ls /tree/alpha/"
    f.set_line("ls /tree/a")
    f.key(9)
    assert f.line() == "ls /tree/a" and f.cands() == ["alpha/", "apex/"]


def test_tab_completes_an_argument_with_no_folder_from_the_working_one(term):
    """An argument with no `/` names the working folder: `cat <Tab>` lists it
    and `cat asd<Tab>` completes from it (a word with no slash once read the
    folder's end from strrchr's NULL and took the console down)."""
    _ws, app = term
    run(app, "mkdir /w; cd /w; touch asdf.txt; mkdir apex; touch beta")
    for n in range(40):
        run(app, f"touch long_name_of_a_file_that_runs_past_the_row_{n:02}")
    f = app.face
    f.set_line("cat asd")
    f.key(9)
    assert f.line() == "cat asdf.txt "
    f.set_line("cat a")
    f.key(9)
    assert f.line() == "cat a" and f.cands() == ["apex/", "asdf.txt"]
    f.set_line("cat ")
    f.key(9)
    assert f.line() == "cat " and len(f.cands()) == 24
    assert "apex/  asdf.txt  beta  long_name" in "".join(plain(app))
    f.set_line("cat zz")
    f.key(9)
    assert f.line() == "cat zz"
    run(app, "cd /")
    f.set_line("cat ")
    f.key(9)
    assert f.line() == "cat " and "w/" in f.cands()


def _type(app, text):
    for ch in text:
        app.face.key(ord(ch))


def test_pkg_asks_the_console_s_password_unseen_and_its_install_question_at_the_prompt(tmp_path):
    """An unreviewed Python cart on a console with a password: `pkg install`
    asks for the password as the shell's prompt, a secret question whose
    answer the prompt row shows a `*` a character and the grid and the
    history never hold; the line runs again with it and asks `Install?`,
    whose `y` installs the cart. The build is downloaded once, kept from
    run to run of the line, and the transcript holds each line once."""
    from cart_store_fixtures import MemNet
    from test_python_trust import _python_repo
    from runtime import cart_index as ci, ssh_service
    from runtime.host_app import build_workstation
    ws = build_workstation(str(tmp_path / "carts"))
    repo = _python_repo()
    ci.save_sources(ws.carts_root, [repo.url("index.json")])
    ws.cart_net = MemNet(repo.routes())
    system = ssh_service.system_dir(ws)
    os.makedirs(system, exist_ok=True)
    with open(system + "/" + ssh_service.PASSWORD, "w") as f:
        f.write(ssh_service.hashed("hunter22", "ab" * 16) + "\n")
    app = ws.app("terminal")
    app.open()
    app.draw(0)                         # the first frame sizes the grid
    f = app.face
    try:
        run(app, "pkg install snake")
        assert f.prompt() == "The console's password: " and not f.busy(), plain(app)
        _type(app, "hunter22")
        f.key(0x08)
        _type(app, "2")
        assert f.prompt_row() == ("\x1b[2mThe console's password: \x1b[0m\x1b[38;2;41;173;255m"
                                  "********\x1b[0m")
        f.key(9)
        f.recall(-1)
        assert f.line() == "hunter22", "no completion, no history while it is asked"
        f.key(0x0D)
        settle(app)
        assert f.prompt() == "Install? [y/N] ", plain(app)
        assert "The console's password:" in [ln.rstrip() for ln in plain(app)], plain(app)
        run(app, "y")
        got = plain(app)
        assert any(ln.startswith("snake 1 installed") for ln in got), got
        assert not any("hunter2" in ln for ln in got), got
        assert not any("hunter2" in ln for ln in f.history()), f.history()
        assert [u.endswith(".zip") for u in ws.cart_net.opened].count(True) == 1, \
            ws.cart_net.opened
        assert got.count("Getting snake 1 (1 KB)") == 1, got
        assert got.count("Moybyte has not checked this cart.") == 1, got
        assert got.index("The console's password:") < got.index("Install? [y/N] y"), got
        assert os.path.exists(ws.carts_root + "/snake.moy/manifest.json")
        f.recall(-1)
        assert f.line() == "y" and f.prompt() == "$ "
    finally:
        app.close_session()


def test_ctrl_c_at_pkg_s_question_drops_the_build_it_kept(tmp_path):
    """The build a gated install checked waits for the line's next run; a
    Ctrl-C at the question (the question over: moy_sh.h's `unask`) deletes
    it, so the next `pkg install` downloads it afresh."""
    from cart_store_fixtures import MemNet
    from test_python_trust import _python_repo
    from runtime import cart_index as ci, pkg, ssh_service
    from runtime.host_app import build_workstation
    ws = build_workstation(str(tmp_path / "carts"))
    repo = _python_repo()
    ci.save_sources(ws.carts_root, [repo.url("index.json")])
    ws.cart_net = MemNet(repo.routes())
    system = ssh_service.system_dir(ws)
    os.makedirs(system, exist_ok=True)
    with open(system + "/" + ssh_service.PASSWORD, "w") as f:
        f.write(ssh_service.hashed("hunter22", "ab" * 16) + "\n")
    app = ws.app("terminal")
    app.open()
    app.draw(0)                         # the first frame sizes the grid
    try:
        run(app, "pkg install snake")
        assert app.face.prompt() == "The console's password: " and len(pkg._KEPT) == 1
        app.face.key(3)
        assert pkg._KEPT == {} and app.face.prompt() == "$ "
        run(app, "pkg install snake")
        assert [u.endswith(".zip") for u in ws.cart_net.opened].count(True) == 2
        app.face.key(3)
        assert pkg._KEPT == {}
    finally:
        app.close_session()


def test_up_and_down_walk_the_lines_run_before(term):
    _ws, app = term
    run(app, "echo one")
    run(app, "echo two")
    f = app.face
    f.recall(-1)
    assert f.line() == "echo two"
    f.recall(-1)
    f.recall(-1)
    assert f.line() == "echo one"
    f.recall(1)
    f.recall(1)
    assert f.line() == "" and f.history() == ["echo one", "echo two"]


def test_exit_starts_a_new_session(term):
    _ws, app = term
    run(app, "x=5; exit 3")
    assert plain(app)[-1] == "[the shell exited 3]"
    run(app, "echo ${x:-gone}")
    assert plain(app)[-1] == "gone"


def test_leaving_the_board_s_shell_gives_it_back_and_a_console_keeps_its_own(term,
                                                                            monkeypatch):
    """Left by any route (`leave_surface`: the window's X, the back, home):
    a console's own session is kept, and on a page a board serves, whose
    face is the board's shell's (`_LINKED`), the session is given back, so
    the board's face ends and SSH can open one; the next open starts anew."""
    ws, app = term
    run(app, "x=5")
    ws.leave_surface("terminal")
    app.open()
    app.draw(0)
    run(app, "echo ${x:-gone}")
    assert plain(app)[-1] == "5"
    monkeypatch.setattr(sys.modules[type(app).__module__], "_LINKED", True)
    ws.leave_surface("terminal")
    app.open()
    app.draw(0)
    run(app, "echo ${x:-gone}")
    assert plain(app)[-1] == "gone"


def test_ctrl_c_stops_a_running_built_in(term):
    """The screen face's poll answers its Ctrl-C inside the run, and the
    rest of the line goes; the latched key is not a second Ctrl-C after."""
    _ws, app = term
    app.face.interrupt()
    t0 = time.monotonic()
    run(app, "sleep 5; echo not-after")
    assert time.monotonic() - t0 < 2
    assert "not-after" not in plain(app) and app.face.status() == 130
    app.face.key(3)
    assert plain(app)[-1] != "$ ^C"


def test_ctrl_c_ends_a_role_command_waiting_on_its_device(term, monkeypatch):
    """`http get` waits in Python across the door; the screen face's
    Ctrl-C reaches it through moy_sh.interrupted and it gives the request
    back (runtime/shell/sh_roles.py)."""
    from runtime import devices, sh_roles
    held = []

    class Http:
        CAP_MAX = 65536

        def get(self, url, cap):
            held.append(1)

            class R:
                def state(self):
                    return None

                def close(self):
                    held.pop()
            return R()
    monkeypatch.setattr(devices, "api", lambda name: Http() if name == "http" else None)
    _ws, app = term
    polls = []
    real = sh_roles.stopped

    def stopped(d):
        polls.append(1)
        if len(polls) == 3:
            app.face.interrupt()
        return real(d)
    monkeypatch.setattr(sh_roles, "stopped", stopped)
    t0 = time.monotonic()
    run(app, "http get http://x/; echo not-after")
    assert time.monotonic() - t0 < 2
    assert held == [] and app.face.status() == 130
    assert "not-after" not in plain(app)


def _slow_role(monkeypatch, steps=3, ms=30):
    """`lease` as a role command that waits: a line, then `ms`, `steps`
    times (runtime/shell/sh_roles.py's generators); `ended` once its
    `finally` ran."""
    from runtime import sh_roles
    ended = []

    def slow(d, a):
        try:
            for i in range(steps):
                d.out("step %d\n" % i)
                if (yield from sh_roles._wait(d, ms)):
                    return sh_roles.INTERRUPTED
            return 0
        finally:
            ended.append(1)
    monkeypatch.setattr(sh_roles, "r_lease", slow)
    return ended


def test_media_play_names_a_file_by_the_sessions_folder(term, monkeypatch):
    """`media play SRC` crosses the door with a file's path made the store's
    against the session's folder (native/moy_sh/moy_sh_board.c, media_src):
    the VM has no session folder. A URL crosses as it is, and a path the
    store has no file for is refused before it crosses."""
    import os
    from runtime import sh_roles
    got = []

    def media(d, a):
        got.append(list(a))
        return 0
    monkeypatch.setattr(sh_roles, "r_media", media)
    _ws, app = term
    run(app, "mkdir /tunes; cd /tunes; touch a.mp3; media play a.mp3; "
             "media play ../tunes/a.mp3; media play http://radio.example/live")
    assert len(got) == 3 and got[0][0] == "play" and got[0][1] == got[1][1]
    assert got[0][1].endswith("/tunes/a.mp3") and os.path.isfile(got[0][1])
    assert got[2] == ["play", "http://radio.example/live"]
    run(app, "media play /proc/x.mp3")
    said = "".join(plain(app)[-2:])                    # the grid wraps the line
    assert len(got) == 3 and said.endswith("media: /proc/x.mp3: not a file in the store")


def test_a_waiting_role_command_parks_and_its_output_streams(term, monkeypatch):
    """A role command that waits is stepped across the door a frame at a
    time: Enter returns while it waits (the run parks on the session's
    runner, native/moy_sh/moy_sh_board.h), its lines reach the grid as they
    come, the prompt stays down until it ends, and the line goes on after."""
    from runtime import moy_sh
    ended = _slow_role(monkeypatch)
    _ws, app = term
    app.face.set_line("lease; echo after")
    t0 = time.monotonic()
    app.face.submit()
    assert time.monotonic() - t0 < 0.025
    assert app.face.busy() and app.face.prompt() == ""
    assert plain(app)[-1] == "step 0"
    app.face.set_line("echo typed ahead")
    app.face.submit()                   # Enter while it runs does nothing
    t0 = time.monotonic()
    while "step 1" not in plain(app) and time.monotonic() - t0 < 2:
        moy_sh.jobs()
        time.sleep(0.005)
    assert "step 1" in plain(app) and app.face.busy() and "after" not in plain(app)
    settle(app)
    assert not app.face.busy() and ended == [1] and app.face.status() == 0
    assert plain(app)[-4:] == ["step 0", "step 1", "step 2", "after"]
    assert app.face.prompt() == "$ " and app.face.line() == "echo typed ahead"


def test_ctrl_c_stops_a_parked_role_command(term, monkeypatch):
    """Ctrl-C while the run is parked is the run's: the role command is
    stopped at its next turn (its `finally` gives back what it took), the
    rest of the line goes, and the prompt is back."""
    ended = _slow_role(monkeypatch, steps=50)
    _ws, app = term
    app.face.set_line("lease; echo not-after")
    app.face.submit()
    assert app.face.busy()
    app.face.key(3)
    settle(app, limit=2)
    assert not app.face.busy() and ended == [1] and app.face.status() == 130
    assert "not-after" not in plain(app) and "step 49" not in plain(app)
    run(app, "echo next")
    assert plain(app)[-1] == "next"


def test_b_while_a_run_is_parked_stops_the_run_and_keeps_the_terminal(term, monkeypatch):
    """The gamepad's B is the console's back: while a run is parked it is the
    run's cancel, as Ctrl-C is, and the Terminal stays open; at the prompt it
    leaves the Terminal as before."""
    ended = _slow_role(monkeypatch, steps=50)
    ws, app = term
    drv = _frame(ws)
    app.face.set_line("lease; echo not-after")
    app.face.submit()
    assert app.face.busy()
    drv.press("b")
    for _ in range(3):
        drv.frame(1 / 30)
    settle(app, limit=2)
    assert ws.wm.top_kind() == "terminal"
    assert not app.face.busy() and ended == [1] and app.face.status() == 130
    assert "not-after" not in plain(app)
    run(app, "echo next")
    assert plain(app)[-1] == "next", "the B stopped that run and no other"
    drv.press("b")
    for _ in range(3):
        drv.frame(1 / 30)
    assert ws.wm.top_kind() != "terminal"


def test_the_console_s_frames_go_on_while_a_command_waits(term, monkeypatch):
    """The kernel's frame (moy_loop_step, the host's driver tier) runs the
    parked run's turn at its tail: frames keep their pace while `sleep` and
    a waiting role command go on, and the run ends on the frames alone."""
    from runtime import moy_loop as _loop
    _slow_role(monkeypatch, steps=2, ms=40)
    _ws, app = term
    app.face.set_line("sleep 0.1; lease; echo done")
    app.face.submit()
    assert app.face.busy()
    worst, t_end = 0.0, time.monotonic() + 3
    while app.face.busy() and time.monotonic() < t_end:
        t0 = time.monotonic()
        _loop.drive(lambda: 0, lambda: 0, lambda dt: 1, 1 / 30)
        worst = max(worst, time.monotonic() - t0)
        time.sleep(1 / 60)
    assert not app.face.busy() and plain(app)[-1] == "done"
    assert worst < 0.025, worst


def test_an_idle_frame_makes_no_line(term):
    """The grid's lines are taken when its generation moves: an idle frame
    takes none."""
    ws, app = term
    run(app, "echo a")
    app.draw(0)
    app.draw(0)
    assert not app.face.take()
    app.draw(0)
    assert not app.face.take()


def test_the_grid_follows_the_view(term):
    """The session's grid takes the log view's columns and rows."""
    _ws, app = term
    app.draw(0)
    app.draw(0)
    run(app, "printf '%0100d\\n' 0")
    assert max(len(x) for x in plain(app)) == app.face.size()[0]


# -- the key row ------------------------------------------------------------------

SHELL_SYMBOLS = "|><&;$~/-*\"'\\{}[]()=!#?:"


def _tdeck_types():
    """The bytes the T-Deck's keyboard types, plain and with Sym (its matrix
    as native/moy_input/moy_kbd.c's RAW_KEYS decodes it)."""
    import os
    import re
    src = open(os.path.join(os.path.dirname(__file__), "..", "native", "moy_input",
                            "moy_kbd.c")).read()
    table = src[src.index("RAW_KEYS[][4] = {"):]
    table = table[:table.index("};")]
    out = set()
    for m in re.finditer(r"\{\d+, 0x[0-9a-fA-F]+, ('(?:\\.|[^'])'|0x[0-9A-Fa-f]+|\d+), "
                         r"('(?:\\.|[^'])'|0x[0-9A-Fa-f]+|\d+)\}", table):
        for v in m.groups():
            if v.startswith("'"):
                out.add(v[1:-1].replace("\\'", "'").replace("\\\\", "\\"))
    return out


def test_the_tdeck_row_holds_the_shell_symbols_its_keyboard_lacks():
    from runtime import moy_sh
    typed = _tdeck_types()
    assert "$" in typed and "/" in typed and ";" in typed       # the parse reads the table
    assert moy_sh.tdeck_row() == "".join(c for c in SHELL_SYMBOLS if c not in typed)
    assert moy_sh.tdeck_row() == "|><&~\\{}[]="


def test_a_desk_draws_no_key_row(tmp_path):
    from runtime import ui_draw
    from test_shell_goldens import CONFIGS, _build
    ws = _build(CONFIGS["p4_1024x600_cs2_fs1_windowed"], tmp_path)
    app = ws.app("terminal")
    kind = ui_draw.input_kind()
    try:
        for k in ("keys", "touch", "pad", "tdeck"):
            ui_draw.input_kind(k)
            assert app.row_kind() is None, k
    finally:
        ui_draw.input_kind(kind)
        app.close_session()


def test_the_trackball_walks_the_tdeck_row_and_back(tmp_path):
    """On the T-Deck the trackball moves the caret and walks the history; down
    past the newest line enters the key row, along it a roll moves, Enter
    presses the key, and up goes back to the prompt."""
    from runtime import ui_draw
    from runtime.host_app import build_workstation, ConsoleDriver
    ws = build_workstation(str(tmp_path / "carts"))
    drv = ConsoleDriver(ws)
    ws.spine.open_app(ws.app("terminal"))
    drv.frame(1 / 30)
    app = ws.app("terminal")
    kinds = ui_draw.input_kind(), ui_draw.hint_kind()
    ws.use_inputs([("local", "tdeck")])     # the keys typed below are the T-Deck's
    ui_draw.input_kind("tdeck")
    ui_draw.hint_kind("tdeck")

    def roll(dx, dy):
        time.sleep(0.16)                # a hand's pause: the roll's axis is forgotten
        drv.pan(dx, dy)
        drv.frame(1 / 30)
        drv.frame(1 / 30)
        drv.pan(0, 0)
        drv.frame(1 / 30)

    def enter():
        drv.ball_click()
        drv.frame(1 / 30)
        drv.frame(1 / 30)

    try:
        assert app.row_kind() == "tdeck"
        run(app, "echo one")
        for ch in "ls":
            drv.type_char(ord(ch))
            drv.frame(1 / 30)
        roll(-1, 0)
        assert app.face.col() == 1                    # the caret, left
        roll(0, -1)
        assert app.face.line() == "echo one"        # the history, up
        roll(0, 1)
        assert app.face.line() == "" and not app.face.in_row()
        roll(0, 1)
        assert app.face.in_row()                         # down past the newest line
        roll(1, 0)
        roll(1, 0)
        enter()                                   # the trackball's click
        assert app.face.line() == ">" and app.face.in_row()
        roll(1, 0)
        drv.type_char(13)                         # the keyboard's Enter
        drv.frame(1 / 30)
        drv.frame(1 / 30)
        assert app.face.line() == "><" and app.face.in_row()
        roll(0, -1)
        assert not app.face.in_row()
        drv.type_char(ord("x"))
        drv.frame(1 / 30)
        assert app.face.line() == "><x"
        roll(0, 1)
        assert app.face.in_row()
        drv.type_char(ord("y"))                   # a typed key goes back to the prompt
        drv.frame(1 / 30)
        assert app.face.line() == "><xy" and not app.face.in_row()
    finally:
        ui_draw.input_kind(kinds[0])
        ui_draw.hint_kind(kinds[1])
        app.close_session()


# -- the text apps (native/moy_sh/moy_sh_app.h) ----------------------------------------


def _frame(ws):
    from runtime.host_app import ConsoleDriver
    drv = ConsoleDriver(ws)
    if ws.wm.top_kind() != "terminal":
        ws.spine.open_app(ws.app("terminal"))
    drv.frame(1 / 30)
    drv.frame(1 / 30)
    return drv


def _keys(app, data):
    for b in data:
        app.face.key(b)


def _arrow(app, d, n=1):
    steps = {"left": (n, 0, 0, 0), "right": (0, n, 0, 0), "up": (0, 0, n, 0), "down": (0, 0, 0, n)}
    app.face.input(app.layout.desk, 0, 0, 0, *steps[d])


def test_the_app_screen_is_sized_to_the_page(term):
    """A full-screen app's screen is the page's rows and columns, the prompt
    row gone: a resize is the app's own."""
    ws, app = term
    cols0, rows0 = app.face.size()
    run(app, "top")
    _frame(ws)
    assert len(plain(app)) > rows0
    _keys(app, b"q")
    assert app.face.app() is None and app.face.size() == (cols0, rows0)


def test_top_shows_the_process_table_and_quits(term):
    """`top` reads what `ps` reads, the task manager's rows across the door,
    a row picked with the arrows; q gives the shell back."""
    ws, app = term
    run(app, "top")
    assert app.face.app() == "top"
    _frame(ws)
    shown = plain(app)
    assert shown[0].startswith("top ") and any(ln.startswith(">") for ln in shown)
    assert any(ln.rstrip().endswith("shell") for ln in shown)
    _arrow(app, "down")
    assert plain(app)[3].startswith(" ") and plain(app)[4].startswith(">")
    _keys(app, b"q")
    assert app.face.app() is None and plain(app)[-1] == "$ top"


def test_edit_opens_full_screen_saves_and_gives_the_grid_back(term, tmp_path):
    """`edit FILE` takes the face's whole page with a screen of its own; the
    keys edit, ^S saves through the store's crash-safe write, ^X with a
    change asks first, and the shell's grid is back as it was."""
    ws, app = term
    run(app, "mkdir -p /sd/moybyte/system")
    run(app, "printf 'theme = \"dusk\"\\n' > /sd/moybyte/system/settings")
    before = plain(app)
    run(app, "edit /sd/moybyte/system/settings")
    assert app.face.app() == "edit" and app.face.full()
    _frame(ws)
    shown = plain(app)
    assert shown[0] == "edit settings" and shown[1] == 'theme = "dusk"'
    _arrow(app, "down")
    _keys(app, b"volume = 3")
    _keys(app, b"\x13")                                 # ^S
    path = tmp_path / "sd" / "moybyte" / "system" / "settings"
    assert path.read_text() == 'theme = "dusk"\nvolume = 3'
    _keys(app, b"!\x18")                                # a change, then ^X
    assert app.face.app() == "edit" and "Save the changes?" in plain(app)[-1]
    _keys(app, b"n")
    assert app.face.app() is None
    assert path.read_text() == 'theme = "dusk"\nvolume = 3'
    assert plain(app)[:len(before)] == before
    assert plain(app)[-1] == "$ edit /sd/moybyte/system/settings"


def test_vi_s_key_row_leaves_insert_saves_and_quits_on_the_tdeck(term, tmp_path):
    """The T-Deck's keyboard has no Esc, so vi's key row carries it: Esc
    leaves INSERT, Save writes from INSERT, and Quit gives the shell back;
    view's row is Quit alone."""
    from runtime import ui_draw
    ws, app = term
    kinds = ui_draw.input_kind(), ui_draw.hint_kind()
    ui_draw.input_kind("tdeck")
    ui_draw.hint_kind("tdeck")
    try:
        run(app, "mkdir -p /sd/moybyte")
        run(app, "vi /sd/moybyte/v.txt")
        _frame(ws)
        assert app.face.app() == "vi"
        _keys(app, b"ihi")
        assert "-- INSERT --" in plain(app)[-1]
        app.face.press("Esc")
        assert "-- INSERT --" not in plain(app)[-1]
        _keys(app, b"A there")
        app.face.press("Save")
        path = tmp_path / "sd" / "moybyte" / "v.txt"
        assert path.read_text() == "hi there\n" and app.face.app() == "vi"
        app.face.press("Quit")
        assert app.face.app() is None
        run(app, "view /sd/moybyte/v.txt")
        _frame(ws)
        assert app.face.app() == "view"
        app.face.press("Quit")
        assert app.face.app() is None
    finally:
        ui_draw.input_kind(kinds[0])
        ui_draw.hint_kind(kinds[1])


def _reversed(row):
    """A screen row's text, and under it `^` for each reversed cell."""
    import re
    text, mask, rev = [], [], False
    for m in re.finditer("\x1b\\[([0-9;]*)m|([^\x1b])", row):
        if m.group(2) is not None:
            text.append(m.group(2))
            mask.append("^" if rev else " ")
            continue
        for p in m.group(1).split(";"):
            rev = True if p == "7" else False if p in ("", "0", "27") else rev
    return "".join(text), "".join(mask).rstrip()


def test_vi_s_visual_selection_is_drawn_in_reverse_video(term):
    """vi's VISUAL draws its selection in reverse video, which the grid
    keeps (SGR 7, then 27 or a reset): as far as each line shows, a long
    line's sideways cut and its `$` marks included, a selected line break
    as one cell; the status line names the mode, and Esc leaves it."""
    ws, app = term
    words = " ".join("w%02d" % i for i in range(1, 31))
    run(app, "mkdir -p /sd/moybyte")
    run(app, "printf 'one two\\n\\n%s\\nend\\n' > /sd/moybyte/v.txt" % words)
    run(app, "vi /sd/moybyte/v.txt")
    _frame(ws)
    cols = app.face.size()[0]
    assert len(words) > cols

    def screen():
        app.face.take()
        return [_reversed(ln) for ln in app.face.lines()]
    _keys(app, b"wv")
    assert app.face.lines()[0] == "one \x1b[7mt\x1b[27mwo"
    assert plain(app)[-1].startswith("-- VISUAL --")
    _keys(app, b"jj")                       # down to the long line's fifth column
    shown = screen()
    assert shown[0] == ("one two ", "    ^^^^")
    assert shown[1] == (" ", "^")
    assert shown[2] == (words[:cols - 1] + "$", "^" * 5)
    _keys(app, b"$")                        # its end: the view scrolls sideways
    left = len(words) - cols // 2
    assert screen()[2] == ("$" + words[left:] + " ", " " + "^" * (len(words) - left + 1))
    _keys(app, b"o")                        # the other end: the line cut at the right
    assert screen()[2] == (words[:cols - 1] + "$", "^" * (cols - 1))
    _keys(app, b"V")
    assert screen()[:4] == [("one two ", "^" * 8), (" ", "^"), (words[:cols - 1] + "$", "^" * (cols - 1)),
                            ("end", "")]
    assert plain(app)[-1].startswith("-- VISUAL LINE --")
    _keys(app, b"\x1b")
    assert all(mask == "" for _text, mask in screen())
    assert not plain(app)[-1].startswith("--")
    _keys(app, b":q\r")
    assert app.face.app() is None


def test_python_runs_a_file_by_the_sessions_path(term):
    """`python FILE [ARG...]`: the file named by the session's path, read
    from the store's, `sys.argv` its name as typed and its ARGs, its exit
    status the program's; a file the store has none of is said, status 2;
    the console's own `sys.argv` is put back."""
    import sys
    was = list(sys.argv)
    _ws, app = term
    run(app, "mkdir /p; cd /p; printf 'import sys\\nprint(sys.argv)\\n"
             "raise SystemExit(len(sys.argv))\\n' > hi.py; python hi.py a 'b c'; echo $?")
    assert plain(app)[-2:] == ["['hi.py', 'a', 'b c']", "3"]
    assert sys.argv == was
    run(app, "cd /; python p/hi.py; echo $?")
    assert plain(app)[-2:] == ["['p/hi.py']", "1"]
    run(app, "python nope.py; echo $?")
    said = "".join(plain(app)[-3:])                    # the grid wraps the line
    assert "python: nope.py: " in said and plain(app)[-1] == "2"
    run(app, "printf '1 / 0\\n' > /p/bad.py; python /p/bad.py; echo $?")
    assert "ZeroDivisionError" in "".join(plain(app)[-3:]) and plain(app)[-1] == "1"


def test_a_file_whose_hash_bang_names_python_runs_as_a_command(term):
    """`./hi.py` whose first line is `#!` naming python (directly or
    through env) is `python ./hi.py`; one naming sh, or none, is a shell
    script, as before."""
    _ws, app = term
    run(app, "mkdir /p; cd /p; printf '#!/usr/bin/env python3\\nimport sys\\n"
             "print(sys.argv)\\n' > hi.py; ./hi.py x; echo $?")
    assert plain(app)[-2:] == ["['./hi.py', 'x']", "0"]
    run(app, "printf '#!python\\nprint(6 * 7)\\n' > two.py; ./two.py")
    assert plain(app)[-1] == "42"
    run(app, "printf '#!/bin/sh\\necho shell $1\\n' > s; ./s y")
    assert plain(app)[-1] == "shell y"


def test_python_is_a_line_app_over_the_prompt(term):
    """`python` with the terminal for its stdin keeps the prompt line, its
    prompt the REPL's: a line at a time into the console's VM, a block held
    until it ends, Ctrl-D on an empty line back to the shell."""
    _ws, app = term
    run(app, "python")
    assert app.face.app() == "python" and not app.face.full()
    assert app.face.prompt() == ">>> "
    run(app, "6 * 7")
    assert plain(app)[-2:] == [">>> 6 * 7", "42"]
    run(app, "def f(x):")
    assert app.face.prompt() == "... "
    app.face.set_line("")
    app.face.key(9)                                     # Tab: four spaces
    app.face.set_line(app.face.line() + "return x + 1")
    app.face.submit()
    run(app, "")
    run(app, "print(f(1))")
    assert plain(app)[-1] == "2" and app.face.prompt() == ">>> "
    app.face.key(4)
    assert app.face.app() is None and app.face.prompt() == "$ "
    run(app, "echo $?")
    assert plain(app)[-1] == "0"


def test_mic_enters_the_app_key_row_on_the_tdeck(term):
    """On the T-Deck the board's cancel (Mic) goes to a full-screen app's key
    row, whose Quit ends it; with no app in front Mic stays the console's."""
    from runtime import ui_draw
    ws, app = term
    kinds = ui_draw.input_kind(), ui_draw.hint_kind()
    ui_draw.input_kind("tdeck")
    ui_draw.hint_kind("tdeck")
    try:
        assert not app.cancel()
        run(app, "top")
        _frame(ws)
        assert app.cancel() and app.face.in_row()
        assert app.cancel() and not app.face.in_row()
        app.face.press("Quit")
        assert app.face.app() is None
    finally:
        ui_draw.input_kind(kinds[0])
        ui_draw.hint_kind(kinds[1])


def test_a_session_starts_in_the_user_files_folder_beside_the_carts(term, tmp_path):
    """The host's files tree is the carts folder's parent, so the user's
    files folder is its `/files`; a session starts there and `cd` returns
    there, and `/` still lists the tree's root."""
    _ws, app = term
    (tmp_path / "files").mkdir(exist_ok=True)
    run(app, "exit")
    run(app, "pwd; echo $HOME; cd /; cd; pwd")
    assert plain(app)[-3:] == ["/files", "/files", "/files"]
    run(app, "ls -1 /")
    listed = plain(app)
    assert {"bin", "carts", "files"} <= set(listed[listed.index("files$ ls -1 /") + 1:])


def test_neofetch_reads_the_console_s_own_rows_from_its_proc_file(term):
    """/proc/console is the door's: the rows only the console knows, which
    neofetch (C) shows beside its own; on the screen face in colour, Moy
    beside the rows on the T-Deck's 44 columns and the palette under them
    on its 13 rows."""
    ws, app = term
    run(app, "cat /proc/console")
    rows = dict(ln.split(": ", 1) for ln in plain(app)[1:] if ": " in ln)
    assert rows["name"].startswith("moybyte-")
    assert rows["display"] == "%dx%d" % (ws.glass_canvas.w, ws.glass_canvas.h)
    run(app, "ls /proc")
    assert "console" in plain(app)[-1].split()
    assert app.face.size() == (44, 13)
    run(app, "clear; neofetch")
    shown = plain(app)
    assert any("Shell: moy_sh" in ln for ln in shown)
    # the title first, Moy's top row beside it, his body beside the rows
    title = shown.index(next(ln for ln in shown if ln.endswith(rows["name"] + "@moybyte")))
    assert shown[title].startswith("   \u2584\u2584\u2584\u2584\u2584\u2584\u2584 ")
    board = next(ln for ln in shown if "Board: " in ln)
    assert board.index("Board: ") == 18 and "\u2588" in board[:15], shown
    lines = app.face.lines()
    assert any("\x1b[38;2;255;119;168mDisplay\x1b[0m" in ln for ln in lines)
    # the palette's two rows of eight grounds under them
    assert sum(ln.count("\x1b[48;2;") == 8 for ln in lines) == 2


def test_a_line_run_before_the_first_frame_waits_for_the_grid_it_sizes(tmp_path):
    """The face's grid starts at 40 x 12, a size no screen has: a line
    submitted before the first frame lays the page out runs at that frame,
    so neofetch as the first command has the T-Deck's 44 columns and
    draws Moy beside its rows."""
    from runtime.host_app import build_workstation
    ws = build_workstation(str(tmp_path / "carts"))
    app = ws.app("terminal")
    app.open()
    try:
        run(app, "neofetch")
        assert plain(app) == [""] and not app.face.busy()
        app.draw(0)
        settle(app)
        assert app.face.size() == (44, 13)
        shown = plain(app)
        assert shown[0] == "$ neofetch", shown
        board = next(ln for ln in shown if "Board: " in ln)
        assert board.index("Board: ") == 18 and "\u2588" in board[:15], shown
    finally:
        app.close_session()


def test_wait_reads_a_background_command_s_exit_code(term, tmp_path):
    """`wait` turns the door's exit code (runtime/shell/sh_door.py's
    `status`) into the code `$?` reads, not a signal's number."""
    import json
    ws, app = term
    d = tmp_path / "carts" / "exits.moy"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({
        "format": "moy-1", "title": "exits", "id": "local.exits", "runtime": "python",
        "main": "main.py", "moybyte": {"type": "command"}}))
    (d / "main.py").write_text("def main(argv):\n    return 5\n")
    ws.carts.synced()
    run(app, "exits & wait $!; echo status $?")
    assert "status 5" in plain(app)


def test_a_console_with_no_shell_says_so(tmp_path, monkeypatch):
    """With no C shell (the desktop MicroPython) the Terminal opens on its
    one line, a page of its own, and draws without a face."""
    from runtime import terminal_app
    from runtime.host_app import build_workstation
    monkeypatch.setattr(terminal_app, "_sh", None)
    ws = build_workstation(str(tmp_path / "carts"))
    app = ws.app("terminal")
    assert ws.spine.open_app(app)
    ws.frame(1 / 30)
    assert app.face is None and app._none is not None
    assert app._none.root is not None


# -- Esc and the clipboard ---------------------------------------------------------


def _vi_open(ws, drv, app, tmp_path):
    """vi on a new file in INSERT, "hi" typed through the driver."""
    run(app, "mkdir -p /sd/moybyte")
    run(app, "vi /sd/moybyte/v.txt")
    for _ in range(2):
        drv.frame(1 / 30)
    for c in b"ihi":
        drv.type_char(c)
        drv.frame(1 / 30)
    assert app.face.app() == "vi" and "-- INSERT --" in plain(app)[-1]
    return tmp_path / "sd" / "moybyte" / "v.txt"


def _desk_or_console(tmp_path, desk):
    from ws_helpers import build_ws, build_desktop_ws
    from runtime.host_app import ConsoleDriver
    ws = build_desktop_ws(tmp_path) if desk else build_ws(tmp_path)
    if desk:
        ws.home.open_desk()
    app = ws.app("terminal")
    drv = ConsoleDriver(ws)
    ws.spine.open_app(app)
    for _ in range(3):
        drv.frame(1 / 30)
    assert ws.input.text_mode and ws.wm.input_kind() == "terminal"
    return ws, app, drv


@pytest.mark.parametrize("desk", [False, True], ids=["console", "desk"])
def test_esc_is_vi_s_and_the_terminal_stays(tmp_path, desk):
    """Esc is a key the Terminal's apps read: a page's Esc (ConsoleDriver.escape,
    the typed 27 on a text surface) leaves vi's INSERT, and `:wq` saves; the
    Terminal stays, at the prompt as in vi. A board keyboard's Esc presses
    `stop` with the byte (moy_hid.c), which the Terminal does not take as the
    console's back either (`takes_stop`). Its ways out are the window's X,
    the bar's back and the system key."""
    ws, app, drv = _desk_or_console(tmp_path / "ws", desk)
    try:
        assert not ws.input_policy.takes_stop(app)
        path = _vi_open(ws, drv, app, tmp_path / "ws")

        def esc():
            drv.escape()
            drv.frame(1 / 30)
            drv.frame(1 / 30)
        esc()
        assert ws.wm.input_kind() == "terminal" and app.face.app() == "vi"
        assert "-- INSERT --" not in plain(app)[-1]
        for c in b":wq\r":
            drv.type_char(c)
            drv.frame(1 / 30)
        assert app.face.app() is None and path.read_text() == "hi\n"
        esc()
        assert ws.wm.input_kind() == "terminal", "Esc at the prompt keeps the Terminal"
    finally:
        app.close_session()


def test_a_paste_types_whole_into_the_prompt_and_into_vi(tmp_path):
    """A paste (ConsoleDriver.paste, the page's clipboard) types its text at
    once, a line break as Enter: two lines run in turn, and in vi's INSERT
    the lines land as typed. The console's clipboard holds it too."""
    ws, app, drv = _desk_or_console(tmp_path / "ws", True)
    try:
        drv.paste("echo one\r\necho two\n")
        drv.frame(1 / 30)
        shown = [ln for ln in plain(app) if ln.strip()]
        assert shown[-4:] == ["$ echo one", "one", "$ echo two", "two"]
        assert ws.clipboard.text() == "echo one\r\necho two\n"
        path = _vi_open(ws, drv, app, tmp_path / "ws")
        drv.paste(" there\nsecond line")
        drv.frame(1 / 30)
        drv.escape()
        drv.frame(1 / 30)
        for c in b":wq\r":
            drv.type_char(c)
            drv.frame(1 / 30)
        assert path.read_text() == "hi there\nsecond line\n"
    finally:
        app.close_session()


def _cells(app, ui_draw):
    """Where each log cell lies in the app's coordinates, as the last frame drew it."""
    at = {}
    lay = app.layout
    for y in range(0, lay.h, 2):
        for x in range(0, lay.w, 2):
            a = ui_draw.text_at(app._ui, "log", x, y)
            if a is not None and a not in at:
                at[a] = (x, y)
    return at


def test_a_reversed_cell_is_filled_with_its_ink(term):
    """SGR 7 (vi's selection draws in it) reaches the Terminal's page: the
    grid says the reversed cells back as `ESC [7m` and the text view fills
    them with their ink, a reversed blank included, where a plain blank
    shows the page."""
    from runtime import ui_draw
    ws, app = term
    run(app, "printf 'ab\\033[7m  \\033[0m\\n'")
    _frame(ws)
    app.face.take()
    rows = list(app.face.lines())
    r = rows.index("ab\x1b[7m  \x1b[0m")
    at = _cells(app, ui_draw)
    cv = app._surf.canvas()
    rgb = cv.to_rgb888()

    def px(cell, dx=0, dy=0):
        x, y = at[cell]
        i = ((y + dy) * cv.w + x + dx) * 3
        return rgb[i:i + 3]
    rev, plain_ = px((r, 2)), px((r, 5))
    assert rev != plain_
    assert px((r, 3), 2, 2) == rev and px((r, 6), 2, 2) == plain_


def test_a_mouse_drag_selects_and_ctrl_c_copies_it(tmp_path):
    """A mouse's drag over the log selects its cells, drawn; Ctrl+C over a
    selection copies its text to the console's clipboard (no interrupt),
    Ctrl+Shift+C too, and Ctrl+C with none is the shell's again."""
    from runtime import ui_draw
    ws, app, drv = _desk_or_console(tmp_path / "ws", True)
    try:
        drv.paste("echo one\necho two\n")
        drv.frame(1 / 30)
        r = plain(app).index("one")
        ws.pointer.hovers = True                       # a mouse
        cx, cy, _w, _h = ws.wm.windows["terminal"].content_rect()
        at = _cells(app, ui_draw)
        x0, y0 = at[(r - 1, 2)]
        x1, y1 = at[(r, 3)]
        drv.touch(cx + x0, cy + y0)
        drv.frame(1 / 30)
        drv.touch_drag(cx + x1, cy + y1)
        drv.frame(1 / 30)
        drv.touch_up()
        drv.frame(1 / 30)
        assert app.face.selection() == (r - 1, 2, r, 3)
        app.face.set_line("kept")
        drv.key_down(ord("c"), 1)
        drv.frame(1 / 30)
        drv.frame(1 / 30)
        drv.key_up(ord("c"), 0)
        drv.frame(1 / 30)
        assert ws.clipboard.text() == "echo one\none"
        assert app.face.selection() is None and app.face.line() == "kept", "no interrupt"
        app.face.select(r + 1, 0, r + 2, 3)
        drv.key_down(ord("C"), 3)                     # Ctrl+Shift+C
        drv.frame(1 / 30)
        drv.key_up(ord("C"), 0)
        drv.frame(1 / 30)
        assert ws.clipboard.text() == "$ echo two\ntwo"
        drv.key_down(ord("c"), 1)
        drv.frame(1 / 30)
        drv.key_up(ord("c"), 0)
        drv.frame(1 / 30)
        assert app.face.line() == "", "Ctrl+C with no selection drops the line"
    finally:
        app.close_session()


def test_a_finger_s_drag_scrolls_and_selects_nothing(tmp_path):
    from runtime import ui_draw
    ws, app, drv = _desk_or_console(tmp_path / "ws", False)
    try:
        drv.paste("echo one\n")
        drv.frame(1 / 30)
        ws.pointer.hovers = False
        at = _cells(app, ui_draw)
        x, y = at[(0, 2)]
        drv.touch(x, y)
        drv.frame(1 / 30)
        drv.touch_drag(x + 20, y)
        drv.frame(1 / 30)
        drv.touch_up()
        drv.frame(1 / 30)
        assert app.face.selection() is None
    finally:
        app.close_session()
