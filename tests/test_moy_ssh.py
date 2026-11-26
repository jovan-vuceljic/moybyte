"""The SSH server (native/moy_ssh) on the host: the board's server, its face
and shell (native/moy_tty over native/moy_sh's board table, the VM stopped) built
with the host's compiler (host/ssh_main.c), and a real OpenSSH client and
ssh-copy-id against it.

What it holds (docs/os_2026-11.md phase 4, item 1): a session that signs in
by neither a password nor a key is refused, and so is every session while no
password is set; a password signs in and a wrong one is refused; a key that
ssh-copy-id installed signs in; `password_auth = no` in system/ssh refuses
the password and still takes the key. Past the sign-in: an `exec` runs on the
shell with the channel as its stdin and ends with its status; a terminal
session is the face's line discipline; `top` and `edit` run on the
alternate screen; an exec that leaves its stdin unread still sends its
output whole; and a session's every allocation goes when it ends. The
run (moy_ssh_run.c): `passwd -d` over SSH stops the server once its session
ends, its tasks report parked only after it, and `passwd x` in the same
session withdraws that stop. A new connection that signs in ends the
session served, whose terminal reads why, and is served in turn; a wrong
password or a connection that never signs in ends nothing. While the web
terminal holds the face, a session reads why and ends with status 1.
"""

import fcntl
import os
import re
import select
import shutil
import socket
import struct
import subprocess
import termios
import time

import pytest

import test_moy_sh as SH
from runtime.host import seal_binding

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "native", "moy_ssh")
DB = os.path.join(MOD, "dropbear")
TTY = os.path.join(ROOT, "native", "moy_tty")
TTY_SOURCES = ("moy_tty.c", "moy_tty_sys.c", "moy_tty_sh.c", "moy_tty_ws.c", "moy_tty_live.c",
               "moy_tty_sftp.c")
PASSWORD = "moybyte-test"
SALT = "00112233445566778899aabbccddeeff"
FILES = "sd/moybyte/files"

pytestmark = pytest.mark.skipif(
    shutil.which("cc") is None or shutil.which("ssh") is None
    or shutil.which("ssh-keygen") is None,
    reason="needs a C compiler and OpenSSH's client")


def _cflags():
    """The flags the board's build gives Dropbear and the face."""
    native = os.path.join(ROOT, "native")
    return ["-Os", "-ffunction-sections", "-fdata-sections", "-w", "-g",
            "-include", os.path.join(MOD, "port", "moy_ssh_names.h"),
            "-I" + os.path.join(MOD, "port"), "-I" + MOD,
            "-I" + os.path.join(DB, "src"),
            "-I" + os.path.join(DB, "libtomcrypt", "src", "headers"),
            "-I" + os.path.join(DB, "libtommath"),
            "-I" + TTY, "-I" + os.path.join(native, "moy_net"),
            "-I" + os.path.join(native, "moy_sh"), "-I" + os.path.join(native, "moy_store"),
            "-I" + os.path.join(native, "moy_kernel"),
            "-DDROPBEAR_SERVER", "-DLOCALOPTIONS_H_EXISTS", "-DLTC_SOURCE",
            "-D_GNU_SOURCE", "-U_FORTIFY_SOURCE", "-D_FORTIFY_SOURCE=0"]


def _build(out, face=()):
    """The server (ssh_main), `face` the flags its face's shell (moy_tty_sh.c)
    adds, and beside it ssh_main_plain: a board's with no
    toolkit (the Zeros'), the console's palette its own file
    (moy_sh_palette.c). (Their face's 12 KiB arena is a 32-bit board's:
    dash's blocks on this 64-bit host need 14.)"""
    cc = shutil.which("cc")
    shell = [o for o in SH._objects(cc, str(out))
             if os.path.basename(o) not in ("sh_main.o", "board_main.o")]
    srcs = [os.path.join(d, f) for top in ("src", "libtommath", "libtomcrypt")
            for d, _dirs, files in os.walk(os.path.join(DB, top))
            for f in files if f.endswith(".c")]
    srcs += [os.path.join(MOD, f) for f in ("moy_ssh.c", "moy_ssh_run.c", "host/ssh_main.c")]
    srcs += [os.path.join(TTY, f) for f in TTY_SOURCES]
    flags = _cflags()
    objs, procs = [], []
    for i, src in enumerate(srcs):
        obj = str(out / ("ssh%d.o" % i))
        f = list(flags)
        if "/libtomcrypt/" not in src:
            f.remove("-DLTC_SOURCE")
        if src.endswith("moy_tty_sh.c"):
            f += list(face)
        procs.append(subprocess.Popen([cc] + f + ["-c", src, "-o", obj]))
        objs.append(obj)
    palette = str(out / "ssh_palette.o")
    procs.append(subprocess.Popen([cc, "-c", os.path.join(SH.SH, "moy_sh_palette.c"),
                                   "-o", palette]))
    assert all(p.wait() == 0 for p in procs)
    link = [cc] + SH.CFLAGS + ["-Wl,--gc-sections", "-Wl,--wrap=moy_tty_pair", "-Wl,--wrap=send"]
    exe = str(out / "ssh_main")
    subprocess.run(link + ["-o", exe] + objs + shell
                   + [seal_binding.archive(), "-lpthread"], check=True)
    subprocess.run(link + ["-o", exe + "_plain"] + objs + [palette]
                   + [o for o in shell if os.path.basename(o) != "moy_ui_tables.o"]
                   + [seal_binding.archive(), "-lpthread"], check=True)
    return exe


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("moy_ssh")
    return out, _build(out)


@pytest.fixture(scope="module")
def straight(tmp_path_factory):
    """A server whose face shows a full-screen app straight, as a board without
    PSRAM builds it (native/moy_tty/moy_tty_sh.c's MOY_TTY_STRAIGHT)."""
    out = tmp_path_factory.mktemp("moy_ssh_straight")
    h = serve(_build(out, face=["-DMOY_TTY_STRAIGHT=1"]), out / "main")
    yield h
    end(h)


def serve(exe, out, store="sd/moybyte"):
    """A server of its own over a fresh tree whose console keeps its store in
    `store` (the card's, or "moy": the internal flash's), its password
    PASSWORD."""
    tree = out / "tree"
    system = tree / store / "system"
    system.mkdir(parents=True)
    for sub in ("carts", "files"):
        (tree / store / sub).mkdir(parents=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "server.log", "w+")
    env = dict(os.environ, MOY_SH_ROOT=str(tree), ASAN_OPTIONS="detect_leaks=0")
    server = subprocess.Popen([exe, str(port), str(system)], stdin=subprocess.PIPE, stdout=log,
                              stderr=subprocess.STDOUT, env=env)
    for _ in range(200):
        log.seek(0)
        if "listening" in log.read():
            break
        time.sleep(0.05)
    home = out / "home"
    (home / ".ssh").mkdir(parents=True)
    askpass = out / "askpass.sh"
    askpass.write_text("#!/bin/sh\necho \"$MOY_SSH_PW\"\n")
    askpass.chmod(0o700)
    key = home / ".ssh" / "id_ed25519"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    h = {"port": port, "askpass": askpass, "log": log, "system": system, "home": home,
         "key": key, "out": out, "server": server}
    set_password(h, PASSWORD)
    return h


def end(h):
    h["server"].kill()
    h["server"].wait()
    h["server"].stdin.close()
    h["log"].close()


def say(h, line, answer, wait=10.0):
    """`line` to the harness's standard input; its `answer` line, once the
    log has it. The log is read through a handle of its own: the server
    writes at the offset of the one it was given."""
    def log():
        with open(h["log"].name) as f:
            return f.read()
    seen = log().count(answer)
    h["server"].stdin.write(line.encode() + b"\n")
    h["server"].stdin.flush()
    deadline = time.time() + wait
    while time.time() < deadline:
        text = log()
        if text.count(answer) > seen:
            return text[text.rindex(answer):].split("\n", 1)[0]
        time.sleep(0.05)
    raise AssertionError("the harness never answered %r to %r" % (answer, line))


@pytest.fixture(scope="module")
def harness(built):
    out, exe = built
    h = serve(exe, out / "main")
    yield h
    end(h)


def hashed(password):
    """The password's record (moy_seal.h's THE PASSWORD), as passwd writes it."""
    from runtime.host import net_binding
    return net_binding.pw_hash(password, SALT)


def set_password(h, password):
    p = h["system"] / "password"
    if password is None:
        if p.exists():
            p.unlink()
    else:
        p.write_text(hashed(password) + "\n")


def options(h):
    return ["-p", str(h["port"]), "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
            "-o", "NumberOfPasswordPrompts=1", "-F", "/dev/null"]


def env_of(h, password):
    return dict(os.environ, SSH_ASKPASS=str(h["askpass"]), SSH_ASKPASS_REQUIRE="force",
                DISPLAY="moy", MOY_SSH_PW=password or "", HOME=str(h["home"]))


def ssh(h, password, *args, key=False, methods=None, stdin=None, timeout=30):
    auth = ["-o", "PubkeyAuthentication=no", "-o", "PreferredAuthentications=password"]
    if key:
        auth = ["-i", str(h["key"]), "-o", "IdentitiesOnly=yes",
                "-o", "PreferredAuthentications=publickey"]
    if methods is not None:
        auth = ["-o", "PubkeyAuthentication=no", "-o", "PreferredAuthentications=" + methods]
    cmd = ["ssh"] + options(h) + auth + list(args)
    return subprocess.run(cmd, env=env_of(h, password), input=stdin, capture_output=True,
                          timeout=timeout,
                          stdin=None if stdin is not None else subprocess.DEVNULL)


def stats(h):
    h["log"].seek(0)
    lines = [l for l in h["log"].read().splitlines() if l.startswith("STATS ")]
    return dict(kv.split("=") for kv in lines[-1].split()[1:]) if lines else {}


def test_a_session_that_does_not_sign_in_is_refused(harness):
    r = ssh(harness, None, "moy@127.0.0.1", "ls", methods="none,keyboard-interactive")
    assert r.returncode == 255
    assert b"Permission denied" in r.stderr
    r = ssh(harness, "not-it", "moy@127.0.0.1", "ls")
    assert r.returncode == 255
    assert b"Permission denied" in r.stderr


def test_a_connection_that_does_not_sign_in_is_closed_within_thirty_seconds(tmp_path):
    """The server serves one session at a time and lets one more sign in
    beside it, so one that never signs in holds its place until Dropbear's
    AUTH_TIMEOUT; the port's options set it, and Dropbear's own default
    (300 s) must not win."""
    src = tmp_path / "t.c"
    src.write_text('#include "includes.h"\n')
    flags = [f for f in _cflags() if f != "-DLTC_SOURCE"]
    r = subprocess.run([shutil.which("cc")] + flags + ["-E", "-dM", str(src)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    got = [ln.split()[2] for ln in r.stdout.splitlines()
           if ln.startswith("#define AUTH_TIMEOUT ")]
    assert got and 0 < int(got[0]) <= 30


def test_with_no_password_set_there_is_no_ssh(harness):
    set_password(harness, None)
    try:
        r = ssh(harness, PASSWORD, "moy@127.0.0.1", "echo in")
        assert r.returncode == 255
        assert b"in" not in r.stdout
    finally:
        set_password(harness, PASSWORD)


def test_a_password_signs_in_and_an_exec_runs_on_the_shell(harness):
    r = ssh(harness, PASSWORD, "moy@127.0.0.1", "ls /")
    assert r.returncode == 0, r.stderr
    assert b"etc/" in r.stdout.split()
    r = ssh(harness, PASSWORD, "moy@127.0.0.1", "exit 3")
    assert r.returncode == 3


def test_an_exec_reads_the_channel_as_its_stdin(harness):
    r = ssh(harness, PASSWORD, "moy@127.0.0.1", "cat > /etc/note && wc -l /etc/note",
            stdin=b"one\ntwo\n")
    assert r.returncode == 0, r.stderr
    assert (harness["system"] / "note").read_bytes() == b"one\ntwo\n"
    assert b"2" in r.stdout


def test_a_large_exec_s_output_arrives_whole_to_a_fast_and_a_slow_reader(harness):
    """The status is reaped while the output's tail is still crossing the
    pair (ssh_main.c's loopback): the channel reads it to the face's close."""
    data = os.urandom(1 << 20)
    (harness["system"] / "big").write_bytes(data)
    for _ in range(3):
        r = ssh(harness, PASSWORD, "moy@127.0.0.1", "cat /etc/big")
        assert r.returncode == 0, r.stderr
        assert len(r.stdout) == len(data) and r.stdout == data
    cmd = ["ssh"] + options(harness) + ["-o", "PubkeyAuthentication=no",
                                        "moy@127.0.0.1", "cat /etc/big"]
    slow = " ".join("'%s'" % c for c in cmd) + " | (sleep 0.5; cat)"
    r = subprocess.run(["sh", "-c", slow], env=env_of(harness, PASSWORD), capture_output=True,
                       timeout=60, stdin=subprocess.DEVNULL)
    assert r.stdout == data, len(r.stdout)
    (harness["system"] / "big").unlink()


def test_an_exec_that_leaves_its_stdin_unread_still_sends_its_output_whole(harness):
    """`ssh host 'cat /etc/big' < bigfile`: the client's bytes the command
    never read are still in the face's end when it ends. lwIP answers a close
    with bytes unread with a reset that drops the output not yet sent (the
    harness's pair does too), so the face drains to Dropbear's half-close."""
    junk = os.urandom(1 << 20)
    for size in (1 << 20, 20000):
        data = os.urandom(size)
        (harness["system"] / "big").write_bytes(data)
        for _ in range(3):
            r = ssh(harness, PASSWORD, "moy@127.0.0.1", "cat /etc/big", stdin=junk, timeout=60)
            assert r.returncode == 0, r.stderr
            assert len(r.stdout) == len(data) and r.stdout == data, len(r.stdout)
    (harness["system"] / "big").unlink()


def test_ssh_copy_id_installs_a_key_that_signs_in(harness):
    keys = harness["system"] / "authorized_keys"
    if keys.exists():
        keys.unlink()
    assert ssh(harness, "", "moy@127.0.0.1", "echo in", key=True).returncode == 255
    r = subprocess.run(["ssh-copy-id", "-i", str(harness["key"]) + ".pub"] + options(harness)
                       + ["moy@127.0.0.1"], env=env_of(harness, PASSWORD),
                       capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stdout + r.stderr
    pub = (harness["key"].parent / "id_ed25519.pub").read_text().strip()
    assert keys.read_text().strip() == pub
    r = ssh(harness, "", "moy@127.0.0.1", "echo in", key=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout == b"in\n"


# What a current ssh-copy-id (OpenSSH 9.x and later) runs on the server: no
# Dropbear case, the home's .ssh/authorized_keys, found through uname, dirname
# and tail's byte count. Kept as text so the test needs no particular client.
CURRENT_INSTALL = (
    "exec sh -c 'cd; umask 077; AUTH_KEY_FILE=\".ssh/authorized_keys\"; "
    "[ -f /etc/openwrt_release ] && [ \"$LOGNAME\" = \"root\" ] && "
    "AUTH_KEY_FILE=/etc/dropbear/authorized_keys; "
    "[ \"`uname -s`\" = \"Haiku\" ] && AUTH_KEY_FILE=config/settings/ssh/authorized_keys; "
    "AUTH_KEY_DIR=`dirname \"${AUTH_KEY_FILE}\"`; "
    "mkdir -p \"${AUTH_KEY_DIR}\" && "
    "{ [ -z \"`tail -1c \"${AUTH_KEY_FILE}\" 2>/dev/null`\" ] || "
    "echo >> \"${AUTH_KEY_FILE}\" || exit 1; } && "
    "cat >> \"${AUTH_KEY_FILE}\" || exit 1; "
    "if type restorecon >/dev/null 2>&1; then restorecon -F \"${AUTH_KEY_DIR}\" \"${AUTH_KEY_FILE}\"; fi'"
)


def test_a_current_ssh_copy_id_installs_its_key_where_the_server_reads(harness):
    keys = harness["system"] / "authorized_keys"
    keys.write_text("ssh-ed25519 AAAAold old@laptop")     # no trailing newline
    pub = (harness["key"].parent / "id_ed25519.pub").read_text().strip()
    r = ssh(harness, PASSWORD, "moy@127.0.0.1", CURRENT_INSTALL, stdin=(pub + "\n").encode())
    assert r.returncode == 0, r.stdout + r.stderr
    assert keys.read_text() == "ssh-ed25519 AAAAold old@laptop\n" + pub + "\n"
    r = ssh(harness, "", "moy@127.0.0.1", "echo in", key=True)
    assert r.returncode == 0, r.stderr
    keys.unlink()


def test_a_session_starts_in_the_files_folder_and_the_root_lists_what_is_there(harness):
    (harness["out"] / "tree" / "asdf.txt").write_text("hi\n")
    r = ssh(harness, PASSWORD, "moy@127.0.0.1", "pwd; echo $HOME; ls /")
    assert r.returncode == 0, r.stderr
    assert r.stdout.decode().split("\n")[:3] == ["/" + FILES, "/" + FILES,
                                                  "asdf.txt  bin/  dev/  etc/  proc/  sd/"]


def test_with_no_card_the_session_and_ssh_copy_id_use_the_internal_store(built, tmp_path):
    """No card: the console's store is the internal flash's (/moy), so a
    session starts in /moy/files, /etc is /moy/system, and ssh-copy-id's key
    lands in the folder the server signs in from."""
    _out, exe = built
    h = serve(exe, tmp_path, store="moy")
    try:
        assert h["system"] == tmp_path / "tree" / "moy" / "system"
        r = ssh(h, PASSWORD, "moy@127.0.0.1", "pwd; grep -c moy2 /etc/password")
        assert r.returncode == 0, r.stderr
        assert r.stdout.decode().split("\n")[:2] == ["/moy/files", "1"]
        pub = (h["key"].parent / "id_ed25519.pub").read_text().strip()
        r = ssh(h, PASSWORD, "moy@127.0.0.1", CURRENT_INSTALL, stdin=(pub + "\n").encode())
        assert r.returncode == 0, r.stdout + r.stderr
        assert (h["system"] / "authorized_keys").read_text() == pub + "\n"
        r = ssh(h, "", "moy@127.0.0.1", "echo in", key=True)
        assert r.returncode == 0 and r.stdout == b"in\n", r.stderr
    finally:
        end(h)


def test_password_auth_no_refuses_the_password_and_keeps_the_key(harness):
    keys = harness["system"] / "authorized_keys"
    keys.write_text((harness["key"].parent / "id_ed25519.pub").read_text())
    conf = harness["system"] / "ssh"
    conf.write_text("# sshd_config-like\npassword_auth = no\n")
    try:
        r = ssh(harness, PASSWORD, "moy@127.0.0.1", "echo in")
        assert r.returncode == 255
        assert b"Permission denied" in r.stderr
        r = ssh(harness, "", "moy@127.0.0.1", "echo in", key=True)
        assert r.returncode == 0, r.stderr
    finally:
        conf.write_text("password_auth = yes\n")
    assert ssh(harness, PASSWORD, "moy@127.0.0.1", "echo in").returncode == 0


def terminal(h, chunks):
    """A `-tt` session fed `chunks`, each (bytes, seconds to wait after)."""
    r = subprocess.Popen(["ssh"] + options(h) + [
        "-o", "PubkeyAuthentication=no", "-o", "PreferredAuthentications=password",
        "-tt", "moy@127.0.0.1"], env=env_of(h, PASSWORD), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1.0)
    for chunk, wait in chunks:
        r.stdin.write(chunk)
        r.stdin.flush()
        time.sleep(wait)
    out, _err = r.communicate(timeout=20)
    return out


def sized_terminal(h, cols, rows, chunks):
    """terminal()'s session from a terminal of `cols` x `rows` (a pty), which
    the client's pty-req names; the session ends at its `exit`."""
    master, slave = os.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    r = subprocess.Popen(["ssh"] + options(h) + [
        "-o", "PubkeyAuthentication=no", "-o", "PreferredAuthentications=password",
        "-tt", "moy@127.0.0.1"], env=env_of(h, PASSWORD), stdin=slave, stdout=slave,
        stderr=slave, start_new_session=True)
    os.close(slave)
    out = b""

    def read_for(secs):
        nonlocal out
        end = time.monotonic() + secs
        while time.monotonic() < end:
            if select.select([master], [], [], 0.05)[0]:
                try:
                    out += os.read(master, 65536)
                except OSError:         # the client has gone: its pty is closed
                    return
    try:
        read_for(1.0)
        for chunk, wait in chunks:
            os.write(master, chunk)
            read_for(wait)
        r.wait(timeout=20)
        read_for(0.2)
    finally:
        r.kill()
        os.close(master)
    return out


def beside(out):
    """neofetch's lines with the SGR left out, and the one that says Board."""
    shown = re.sub(r"\x1b\[[0-9;]*m", "", out.decode("utf-8", "replace")).split("\r\n")
    return shown, next(ln for ln in shown if "Board: " in ln)


def test_neofetch_draws_moy_in_colour_beside_the_rows_from_44_columns(harness):
    """Moy is 15 columns, three more to the rows: from 44 columns (the
    T-Deck's Terminal) he stands beside them, as the client's pty-req sizes
    the face; on 43 the rows go alone."""
    out = sized_terminal(harness, 44, 30, [(b"neofetch\r", 1.0), (b"exit\r", 0.5)])
    shown, board = beside(out)
    assert board.index("Board: ") == 18 and "\u2588" in board[:15], shown
    assert b"\x1b[38;2;" in out
    out = sized_terminal(harness, 43, 30, [(b"neofetch\r", 1.0), (b"exit\r", 0.5)])
    shown, board = beside(out)
    assert board.startswith("Board: "), shown


def test_without_a_toolkit_neofetch_draws_moy_in_colour_beside_the_rows(built, tmp_path):
    """The Zeros' build (ssh_main_plain): no toolkit, the palette its own
    file, so Moy is drawn in the console's colours as on every console."""
    _out, exe = built
    h = serve(exe + "_plain", tmp_path)
    try:
        out = sized_terminal(h, 80, 30, [(b"neofetch\r", 1.0), (b"exit\r", 0.5)])
    finally:
        end(h)
    shown, board = beside(out)
    assert board.index("Board: ") == 18 and "\u2588" in board[:15], shown
    assert b"\x1b[38;2;131;118;156m" in out          # his body, the palette's 13


def test_a_terminal_session_is_the_face_s_line_discipline(harness):
    out = terminal(harness, ((b"echo hi\r", 0.4), (b"ech\x7fho abd\r", 0.4),
                             (b"sleep 5\r", 0.4), (b"\x03", 0.4), (b"exit\r", 0.3)))
    assert b"echo hi\r\nhi\r\n" in out, out
    assert b"ech\b \bho abd\r\nabd\r\n" in out, out
    assert b"^C\r\n" in out, out


def test_a_secret_question_is_answered_unseen_and_kept_from_the_history(harness):
    """A role's secret question (the harness's `pkg ask`, pkg's password's
    stand-in) is a terminal session's prompt; what is typed to it is echoed by nothing, its
    erase moves nothing, Up while it is asked brings nothing back, and the
    line that asked runs again with the answer -- which Up after it does not
    bring back either."""
    out = terminal(harness, ((b"pkg ask\r", 0.6), (b"hunter22", 0.2), (b"\x1b[A", 0.2),
                             (b"\x7f", 0.1), (b"2\r", 0.8), (b"\x1b[A", 0.4),
                             (b"\x03", 0.3), (b"exit\r", 0.3)))
    assert b"hunter2" not in out, out
    assert b"Password: \r\n" in out and b"\b \b" not in out, out
    assert out.count(b"pkg ask") == 2, "the line typed, and Up's line after the answer: %r" % out
    harness["log"].seek(0)
    assert "ANSWER hunter22\n" in harness["log"].read()
    r = ssh(harness, PASSWORD, "moy@127.0.0.1", "pkg ask")
    assert r.returncode == 1 and b"Password" not in r.stdout, \
        "an exec asks no questions: its command reads its answers from stdin"


def test_an_exec_with_a_terminal_answers_its_command_s_question_there(harness):
    """`ssh -t host CMD`: a question CMD asks is the terminal's prompt, its
    answer typed unseen, and the session ends once the line asks nothing."""
    r = subprocess.Popen(["ssh"] + options(harness) + [
        "-o", "PubkeyAuthentication=no", "-o", "PreferredAuthentications=password",
        "-tt", "moy@127.0.0.1", "pkg ask"], env=env_of(harness, PASSWORD),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1.2)
    r.stdin.write(b"sesame42\r")
    r.stdin.flush()
    time.sleep(1.0)                     # the session ends by itself, its stdin still open
    out, _err = r.communicate(timeout=20)
    assert r.returncode == 0, out
    assert b"Password: " in out and b"sesame" not in out, out
    harness["log"].seek(0)
    assert "ANSWER sesame42\n" in harness["log"].read()


def test_tab_completes_a_command_and_a_path_and_lists_what_it_cannot_choose(harness):
    """Tab is the Terminal's completion (moy_sh_cands): a command's name, a
    path's from its folder, and with nothing more to share the names listed
    under the line, the prompt and the line drawn again."""
    tree = harness["out"] / "tree" / FILES
    (tree / "tabby.txt").write_text("purr\n")
    (tree / "tabs").mkdir(exist_ok=True)
    (tree / "tabs" / "one.txt").write_text("1\n")
    (tree / "tabs" / "two.txt").write_text("2\n")
    try:
        out = terminal(harness, ((b"neofe\t\r", 0.6), (b"cat tabb\t\r", 0.4),
                                 (b"ls tabs/\t", 0.4), (b"\x03", 0.3), (b"exit\r", 0.3)))
        assert b"neofetch \r\n" in out, out
        assert b"cat tabby.txt \r\npurr\r\n" in out, out
        assert b"one.txt  two.txt\r\n" in out, out
    finally:
        (tree / "tabby.txt").unlink()
        for n in ("one.txt", "two.txt"):
            (tree / "tabs" / n).unlink()
        (tree / "tabs").rmdir()


def test_a_command_s_output_leaves_the_face_in_few_segments_run_after_run(harness):
    """Each send on the face's end is a segment on a board's loopback (TCP_NODELAY),
    which queues at most LWIP_LOOPBACK_MAX_PBUFS (8) and drops the rest: neofetch
    written a few bytes at a time stopped after 379 bytes the second time it ran
    in one session. The face gathers a command's output and sends it in pieces of
    up to OUT_BYTES."""
    n = int(stats(harness)["ended"])
    sends = int(stats(harness).get("face_sends", 0))
    lines = (b"neofetch\r", b"neofetch\r", b"exit\r")
    out = terminal(harness, [(line, 1.0) for line in lines])
    s = ended(harness, n + 1)
    assert out.count(b"lab (192.168.1.2)") == 2, out
    assert out.count(b"moy_sh (dash)") == 2, out
    # the client sends a key a packet, and each key's echo is a send of its own
    keys = sum(len(line) for line in lines)
    used = int(s["face_sends"]) - sends - keys
    assert used <= 8, "%d sends for two neofetches (about 2 KB each) and their prompts" % used


def _sends_for(h, chunks):
    n = int(stats(h)["ended"])
    before = int(stats(h).get("face_sends", 0))
    out = terminal(h, chunks)
    return out, int(ended(h, n + 1)["face_sends"]) - before


def test_a_still_full_screen_app_sends_nothing_while_it_waits(harness):
    """The face shows a full-screen app each 250 ms tick: its changed rows,
    then its cursor only where the cursor moved."""
    (harness["system"] / "still").write_text("hello\n")
    short, n_short = _sends_for(harness, ((b"edit /etc/still\r", 1.0), (b"\x18", 0.5),
                                          (b"exit\r", 0.3)))
    long_, n_long = _sends_for(harness, ((b"edit /etc/still\r", 3.0), (b"\x18", 0.5),
                                         (b"exit\r", 0.3)))
    assert b"hello" in short and b"hello" in long_
    assert n_long - n_short <= 1, "%d sends over two idle seconds" % (n_long - n_short)


def test_top_and_edit_run_on_the_alternate_screen(harness):
    (harness["system"] / "memo").write_text("hello\n")
    out = terminal(harness, ((b"top\r", 1.5), (b"q", 0.8), (b"edit /etc/memo\r", 1.0),
                             (b"X", 0.3), (b"\x13", 0.8), (b"\x18", 0.5), (b"exit\r", 0.5)))
    assert out.count(b"\x1b[?1049h") >= 2, out
    assert out.count(b"\x1b[?1049l") >= 2, out
    assert b"PID" in out or b"pid" in out, out
    assert (harness["system"] / "memo").read_text() == "Xhello\n"
    # their titles in the palette's accent (base 12), never an ANSI ink
    assert out.count(b"\x1b[38;2;41;173;255m") >= 2, out
    assert not re.search(rb"\x1b\[[0-9;]*\b(3[0-7]|9[0-7])m", out), out


def test_a_straight_face_shows_its_apps_as_they_write_and_they_save(straight):
    """Where there is no PSRAM the face keeps no grid (moy_tty_sh.c,
    MOY_TTY_STRAIGHT): `edit`, `vi` and `top` open on the alternate screen
    and leave it, each step's writes inside a synchronized update that ends,
    and what is typed saves."""
    memo = straight["system"] / "memo"
    memo.write_text("hello\n")
    out = terminal(straight, ((b"edit /etc/memo\r", 1.0), (b"X", 0.3), (b"\x13", 0.8),
                              (b"\x18", 0.5), (b"vi /etc/memo\r", 1.0), (b"A!", 0.3),
                              (b"\x1b", 0.5), (b":wq\r", 0.8), (b"top\r", 1.5), (b"q", 0.8),
                              (b"exit\r", 0.5)))
    assert out.count(b"\x1b[?1049h") == 3 and out.count(b"\x1b[?1049l") == 3, out
    begun, ended_ = out.count(b"\x1b[?2026h"), out.count(b"\x1b[?2026l")
    assert begun == ended_ and begun >= 6, out
    assert b"Xhello" in out and b"PID" in out, out
    assert memo.read_text() == "Xhello!\n"


def ended(h, n, wait=10.0):
    """The STATS line once the server has ended `n` connections: a client
    returns at the channel's close, before the server has let its session
    go."""
    deadline = time.time() + wait
    while time.time() < deadline:
        s = stats(h)
        if int(s.get("ended", -1)) >= n:
            return s
        time.sleep(0.05)
    raise AssertionError("the server ended %s connections, not %d" % (stats(h).get("ended"), n))


def settled(h, quiet=0.5, wait=10.0):
    """The STATS line once no connection has ended for `quiet` seconds: the
    harness prints one per event, and a connection an earlier test left
    closing can end after a count was read."""
    deadline = time.time() + wait
    last, since = stats(h), time.time()
    while time.time() < deadline:
        time.sleep(0.05)
        s = stats(h)
        if s != last:
            last, since = s, time.time()
        elif time.time() - since >= quiet:
            return s
    return last


def test_every_session_gives_back_what_it_took(harness):
    n = int(settled(harness)["ended"])
    for i in range(3):
        assert ssh(harness, PASSWORD, "moy@127.0.0.1", "echo %d" % i).returncode == 0
    ended(harness, n + 3)
    held = int(settled(harness)["heap_now"])
    for i in range(3):
        assert ssh(harness, PASSWORD, "moy@127.0.0.1", "ls / | wc -l").returncode == 0
    ended(harness, n + 6)
    s = settled(harness)
    assert int(s["heap_now"]) == held
    assert int(s["session_peak"]) > 0


def opened(h):
    """A `-tt` session left open: its process, stdin still the test's."""
    p = subprocess.Popen(["ssh"] + options(h) + [
        "-o", "PubkeyAuthentication=no", "-o", "PreferredAuthentications=password",
        "-tt", "moy@127.0.0.1"], env=env_of(h, PASSWORD), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(1.5)
    assert p.poll() is None, p.communicate()[0]
    return p


TAKEN = b"another session signed in; this one is closing"


def test_a_new_sign_in_ends_the_session_served_and_tells_its_terminal_why(harness):
    n = int(settled(harness)["ended"])
    held = int(settled(harness)["heap_now"])
    first = opened(harness)
    try:
        r = ssh(harness, PASSWORD, "moy@127.0.0.1", "echo second")
        assert r.returncode == 0, r.stderr
        assert b"second" in r.stdout
        out, _ = first.communicate(timeout=10)
    finally:
        if first.poll() is None:
            first.kill()
    assert TAKEN in out, out
    ended(harness, n + 2)
    assert int(settled(harness)["heap_now"]) == held


def test_a_wrong_password_or_a_silent_connection_ends_nobody(harness):
    first = opened(harness)
    try:
        r = ssh(harness, "not-it", "moy@127.0.0.1", "echo second")
        assert r.returncode == 255 and b"Permission denied" in r.stderr
        with socket.create_connection(("127.0.0.1", harness["port"]), timeout=5) as c:
            c.recv(64)                  # its banner: the server took it beside the first
            time.sleep(1.0)
        assert first.poll() is None
        first.stdin.write(b"echo still here\r")
        first.stdin.flush()
        time.sleep(0.5)
        first.stdin.write(b"exit\r")
        first.stdin.flush()
        out, _ = first.communicate(timeout=10)
    finally:
        if first.poll() is None:
            first.kill()
    assert b"still here" in out and TAKEN not in out, out


def test_the_session_that_took_over_is_taken_over_in_turn(harness):
    first = opened(harness)
    second = opened(harness)
    try:
        out, _ = first.communicate(timeout=10)
        assert TAKEN in out, out
        r = ssh(harness, PASSWORD, "moy@127.0.0.1", "echo third")
        assert r.returncode == 0 and b"third" in r.stdout, r.stderr
        out, _ = second.communicate(timeout=10)
        assert TAKEN in out, out
    finally:
        for p in (first, second):
            if p.poll() is None:
                p.kill()


BUSY = b"the terminal is open in a browser; close it there and try again"


def test_a_face_the_web_terminal_holds_tells_the_ssh_client_why(harness):
    """One face at a time (native/moy_tty/moy_tty.h): while the browser
    console's Terminal holds it, an exec and a terminal session each read
    why on their stderr, a terminal's line ending CR LF, and end with status
    1, the channel closed; once the page lets it go the next session runs,
    and the refused ones took nothing."""
    n = int(settled(harness)["ended"])
    held = int(settled(harness)["heap_now"])
    assert say(harness, "web", "WEB ") == "WEB 0"
    try:
        r = ssh(harness, PASSWORD, "moy@127.0.0.1", "echo in")
        assert (r.returncode, r.stdout, r.stderr) == (1, b"", BUSY + b"\n"), r
        r = ssh(harness, PASSWORD, "-tt", "moy@127.0.0.1")
        assert (r.returncode, r.stdout, r.stderr) == (1, b"", BUSY + b"\r\n"), r
    finally:
        assert say(harness, "noweb", "NOWEB") == "NOWEB"
    r = ssh(harness, PASSWORD, "moy@127.0.0.1", "echo in")
    assert (r.returncode, r.stdout) == (0, b"in\n"), r
    ended(harness, n + 3)
    assert int(settled(harness)["heap_now"]) == held


def _spilling(h):
    """A `-tt` session whose pipe has gone on in a file of the store
    (native/moy_sh/moy_sh_sys.c's SPILL, past the 4 KB of memory the shell's
    harness builds it with), its writer asleep; and the folder the spill is
    in."""
    files = h["system"].parent / "files"
    (files / "z").write_bytes(b"0123456789abcde\n" * 4096)
    pipes = h["system"] / "pipes"
    p = opened(h)
    p.stdin.write(b"{ cat z; sleep 30; } | wc -c\r")
    p.stdin.flush()
    deadline = time.time() + 10
    while time.time() < deadline and not (pipes.is_dir() and any(pipes.iterdir())):
        time.sleep(0.05)
    if not (pipes.is_dir() and any(pipes.iterdir())):
        p.kill()
        raise AssertionError("no spill: %r" % p.communicate()[0])
    return p, pipes


def _gone(path, wait=10.0):
    deadline = time.time() + wait
    while time.time() < deadline and path.exists():
        time.sleep(0.05)
    return not path.exists()


def test_a_spill_goes_when_its_session_is_closed_or_taken_over(harness):
    n = int(settled(harness)["ended"])
    first, pipes = _spilling(harness)
    try:
        r = ssh(harness, PASSWORD, "moy@127.0.0.1", "echo second")
        assert r.returncode == 0 and b"second" in r.stdout, r.stderr
        out, _ = first.communicate(timeout=10)
        assert TAKEN in out, out
    finally:
        if first.poll() is None:
            first.kill()
    ended(harness, n + 2)
    assert _gone(pipes)
    first, pipes = _spilling(harness)
    first.kill()
    first.wait()
    ended(harness, n + 3)
    assert _gone(pipes)


def refused(h, wait=3.0):
    """Whether the port refuses a connection within `wait` seconds."""
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", h["port"]), timeout=1).close()
        except ConnectionRefusedError:
            return True
        except (ConnectionResetError, TimeoutError):
            pass                    # closed under this connect, or a busy listener: ask again
        time.sleep(0.1)
    return False


def test_passwd_in_a_session_stops_the_server_after_it_and_a_new_one_withdraws_the_stop(
        built, tmp_path):
    """`passwd -d` asked over SSH (inside a hop) cannot wait for the session
    it runs in, so the server stops when that session ends; `passwd x` in the
    same session withdraws the stop, and the server serves on (moy_ssh.h, THE
    RUN). The harness's VM answers `passwd` as ssh_service does."""
    _out, exe = built
    h = serve(exe, tmp_path)
    try:
        r = ssh(h, PASSWORD, "moy@127.0.0.1", "passwd -d; passwd other-pw; echo done")
        assert r.returncode == 0, r.stderr
        assert b"done" in r.stdout
        assert not refused(h, wait=1.5)
        r = ssh(h, "other-pw", "moy@127.0.0.1", "echo in")
        assert r.returncode == 0 and r.stdout == b"in\n", r.stderr
        assert stats(h)["listening"] == "1"
        r = ssh(h, "other-pw", "moy@127.0.0.1", "passwd -d")
        assert r.returncode == 0, r.stderr
        assert refused(h)
        # the harness prints its figures every 20 ms: the refusal can come first
        deadline = time.time() + 5
        while stats(h)["listening"] != "0" and time.time() < deadline:
            time.sleep(0.05)
        assert stats(h)["listening"] == "0"
    finally:
        end(h)


def test_a_stop_from_a_session_parks_only_once_that_session_has_ended(built, tmp_path):
    """The run reports the tasks parked (what ssh_service waits on to let the
    radio and the mDNS name go) only after the session that ran `passwd -d`
    has written its last byte and closed."""
    _out, exe = built
    h = serve(exe, tmp_path)
    try:
        assert stats(h)["parked"] == "0"
        cmd = ["ssh"] + options(h) + ["-o", "PubkeyAuthentication=no",
                                      "-o", "PreferredAuthentications=password",
                                      "moy@127.0.0.1", "passwd -d; cat; echo done"]
        p = subprocess.Popen(cmd, env=env_of(h, PASSWORD), stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.time() + 20
            while stats(h).get("listening") != "0" and time.time() < deadline:
                time.sleep(0.05)
            assert stats(h)["listening"] == "0"
            time.sleep(0.5)
            assert stats(h)["parked"] == "0"
            out, err = p.communicate(b"last\n", timeout=30)
        finally:
            p.kill()
        assert p.returncode == 0, err
        assert out == b"last\ndone\n"
        deadline = time.time() + 5
        while stats(h)["parked"] != "1" and time.time() < deadline:
            time.sleep(0.05)
        assert stats(h)["parked"] == "1"
        assert refused(h)
    finally:
        end(h)


ARROWS = {"up": (b"\x1b[A", b"\x1bOA"), "right": (b"\x1b[C", b"\x1bOC")}


def test_the_arrows_move_the_editor_s_caret_in_both_spellings_and_split(harness):
    """Right in `edit` moves the caret one character along the line, as
    `ESC [ C`, as the application-cursor `ESC O C`, and split across writes;
    the terminal's cursor is put at the caret's row, then its column (the
    title on row 1, the text from row 2)."""
    (harness["system"] / "memo").write_text("hello\nworld\n")
    csi, ss3 = ARROWS["right"]
    out = terminal(harness, ((b"edit /etc/memo\r", 1.0), (csi, 0.3), (b"X", 0.3), (ss3, 0.3),
                       (b"Y", 0.3), (b"\x1b", 0.1), (b"[", 0.1), (b"C", 0.3), (b"Z", 0.3),
                       (b"\x13", 0.8), (b"\x18", 0.5), (b"exit\r", 0.5)))
    assert (harness["system"] / "memo").read_text() == "hXeYlZlo\nworld\n"
    opened = out.index(b"\x1b[?1049h")
    assert out.index(b"\x1b[2;1H\x1b[?25h", opened) < out.index(b"\x1b[2;3H\x1b[?25h", opened), out


def test_up_at_the_prompt_walks_the_lines_run_before(harness):
    csi, ss3 = ARROWS["up"]
    out = terminal(harness, ((b"echo one\r", 0.4), (b"echo two\r", 0.4), (csi, 0.3),
                             (b"\r", 0.4), (ss3 + ss3, 0.3), (b"\r", 0.4), (b"\x1b", 0.1),
                             (b"[A", 0.3), (b"\x1b[D\x1b[D", 0.3), (b"_\r", 0.4),
                             (b"exit\r", 0.3)))
    lines = [ln for ln in out.replace(b"\r", b"").split(b"\n") if ln in (b"one", b"two", b"o_ne")]
    assert lines == [b"one", b"two", b"two", b"one", b"o_ne"], out


def test_the_consoles_fingerprint_is_the_one_ssh_sees(harness, monkeypatch):
    """`passwd` and Settings show the host key's fingerprint
    (ssh_service.fingerprint, read from the key file the server wrote) so a
    person can check a first connection reached this console: it is the one
    OpenSSH computes from the key the server offers."""
    from runtime.system import ssh_service
    r = ssh(harness, PASSWORD, "moy@127.0.0.1", "echo in")
    assert r.returncode == 0, r.stderr
    monkeypatch.setattr(ssh_service, "system_dir", lambda ws: str(harness["system"]))
    mine = ssh_service.fingerprint(None)
    scan = subprocess.run(["ssh-keyscan", "-t", "ed25519", "-p", str(harness["port"]),
                           "127.0.0.1"], capture_output=True, timeout=30)
    seen = subprocess.run(["ssh-keygen", "-lf", "-"], input=scan.stdout,
                          capture_output=True, timeout=30).stdout.decode()
    assert mine and mine.startswith("SHA256:") and mine in seen, (mine, seen)
