"""The C shell (native/moy_sh/) on the host, under the sanitizers.

native/moy_sh/host/sh_main.c is a session over a temporary folder, fed a
script line by line as a face feeds it, printing each prompt and line before
what it ran (a transcript). tests/moy_sh/ holds a script per feature and per
C built-in, each beside the transcript it must produce, and the session's
exit status closes it. MOYBYTE_UPDATE_GOLDENS=1 rewrites the transcripts;
read the diff before committing one.

The harness's OS is a stand-in (its header lists what it serves): installed
commands, a background program, the service roles, /dev and /proc, the log.
"""

import fcntl
import glob
import hashlib
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest

from runtime.host import seal_binding

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SH = os.path.join(ROOT, "native", "moy_sh")
DASH = os.path.join(SH, "dash")
STORE = os.path.join(ROOT, "native", "moy_store")
KERNEL = os.path.join(ROOT, "native", "moy_kernel")
SPINE = os.path.join(ROOT, "native", "moy_spine")
# the console's palette the grid and neofetch read: the toolkit's generated
# tables, which need nothing else of it
UI_TABLES = os.path.join(ROOT, "native", "moy_ui", "moy_ui_tables.c")
SCRIPTS = os.path.join(ROOT, "tests", "moy_sh")
# md5sum's and sha256sum's hashes (moy_sh_cmds.c): the vendored mbedTLS the
# host's library compiles (native/moy_net/mbedtls/README.md), its headers
# under that library's config, its code the seal archive's
# (runtime/host/seal_binding.py), which the harnesses link
NET = os.path.join(ROOT, "native", "moy_net")
MBEDTLS = ["-I", os.path.join(NET, "mbedtls", "include"), "-I", NET,
           '-DMBEDTLS_CONFIG_FILE="moy_seal_mbedtls.h"']

# A pipe's memory a board's without PSRAM (moy_sh_sys.c's MOY_SH_PIPE_MEM), so
# a long pipe spills to the store in every harness, as on the C3 Zero.
CFLAGS = ["-std=gnu99", "-g", "-O1", "-fsanitize=address,undefined",
          "-fno-sanitize-recover=all", "-Wall", "-Werror", "-DMOY_SH_PIPE_MEM=4096u"]


def shell_sources():
    """What the shell compiles: dash's sources, its built-ins, the session."""
    srcs = sorted(glob.glob(os.path.join(DASH, "*.c")))
    srcs += [os.path.join(DASH, "bltin", "printf.c"), os.path.join(DASH, "bltin", "test.c")]
    srcs += [os.path.join(SH, n) for n in ("moy_sh.c", "moy_sh_sys.c", "moy_sh_cmds.c")]
    return srcs


# The board's side, compiled without dash's shim: its host table and the
# serial face, the screen face and its grid.
BOARD_SOURCES = ("moy_sh_board.c", "moy_sh_screen.c", "moy_sh_store.c", "moy_term.c",
                 "moy_sh_app.c", "moy_sh_edit.c", "moy_sh_top.c")
# What the text apps' harness (host/app_main.c) links of them: the apps alone.
APP_SOURCES = ("moy_term.c", "moy_sh_app.c", "moy_sh_edit.c", "moy_sh_top.c")
# The Terminal's face and the recovery floor's screen over it draw through the
# toolkit's engine, so they compile against native/moy_ui and the harnesses,
# which have no toolkit, leave them out.
FACE_SOURCES = ("moy_sh_face.c", "moy_sh_floor.c")
UI_INCLUDES = [a for n in ("moy_ui", "moy_gfx", "moy_glass")
               for a in ("-I", os.path.join(ROOT, "native", n))]


def _objects(cc, out):
    dash_flags = CFLAGS + ["-include", os.path.join(SH, "dash_config.h"),
                           "-I", SH, "-I", DASH, "-I", STORE, "-I", KERNEL] + MBEDTLS
    jobs = [(src, dash_flags) for src in shell_sources()]
    jobs.append((os.path.join(SH, "moy_sh_arena.c"), CFLAGS + ["-I", SH]))
    jobs.append((os.path.join(SH, "moy_sh_fmt.c"), CFLAGS + ["-I", SH, "-I", SPINE]))
    jobs.append((os.path.join(SH, "moy_sh_cands.c"), CFLAGS + ["-I", SH]))
    jobs.append((os.path.join(SH, "host", "sh_main.c"), CFLAGS + ["-I", SH, "-I", KERNEL]))
    board = CFLAGS + ["-I", SH, "-I", KERNEL, "-I", STORE, "-I", SPINE]
    for name in BOARD_SOURCES:
        jobs.append((os.path.join(SH, name), board))
    jobs.append((os.path.join(SH, "host", "board_main.c"), board))
    jobs.append((os.path.join(STORE, "moy_vol.c"), CFLAGS + ["-I", STORE, "-I", KERNEL]))
    jobs.append((os.path.join(STORE, "moy_store_host.c"), CFLAGS + ["-I", STORE, "-I", KERNEL]))
    jobs.append((os.path.join(STORE, "moy_fs.c"), CFLAGS + ["-I", STORE, "-I", KERNEL]))
    for name in ("moy_shelf.c", "moy_cat.c", "moy_files.c", "moy_removed.c"):
        jobs.append((os.path.join(STORE, name), CFLAGS + ["-I", STORE, "-I", SPINE, "-I", KERNEL]))
    jobs.append((os.path.join(SPINE, "moy_settings.c"), CFLAGS + ["-I", SPINE, "-I", KERNEL]))
    jobs.append((os.path.join(SPINE, "moy_json.c"), CFLAGS + ["-I", SPINE, "-I", KERNEL]))
    jobs.append((os.path.join(KERNEL, "moy_log.c"), CFLAGS + ["-I", KERNEL]))
    jobs.append((UI_TABLES, CFLAGS))

    def one(job):
        src, flags = job
        obj = os.path.join(out, os.path.basename(src)[:-2] + ".o")
        r = subprocess.run([cc] + flags + ["-c", src, "-o", obj],
                           capture_output=True, text=True)
        return obj, r

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        done = list(pool.map(one, jobs))
    for _obj, r in done:
        assert r.returncode == 0, r.stderr[-4000:]
    return [obj for obj, _r in done]


@pytest.fixture(scope="session")
def harness(tmp_path_factory):
    """sh_main, built once per source state and shared by xdist's workers."""
    cc = shutil.which(os.environ.get("CC", "cc"))
    if cc is None:
        pytest.skip("no C compiler")
    seal = seal_binding.archive()
    h = hashlib.sha256(seal.encode())
    for d in (SH, STORE, KERNEL, SPINE):
        for path in sorted(glob.glob(os.path.join(d, "**", "*.[ch]"), recursive=True)):
            h.update(path.encode())
            with open(path, "rb") as f:
                h.update(f.read())
    with open(UI_TABLES, "rb") as f:
        h.update(f.read())
    base = tmp_path_factory.getbasetemp().parent / "moy_sh_host" / h.hexdigest()[:16]
    base.mkdir(parents=True, exist_ok=True)
    exes = {name: str(base / name) for name in ("sh_main", "board_main", "app_main")}
    with open(base / "lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not all(os.path.exists(e) for e in exes.values()):
            objs = _objects(cc, str(base))
            # the text apps' harness, which _objects leaves out (test_moy_tty links
            # its objects but the harnesses' mains)
            app = os.path.join(str(base), "app_main.o")
            r = subprocess.run([cc] + CFLAGS + ["-I", SH, "-I", KERNEL, "-I", STORE, "-c",
                                                os.path.join(SH, "host", "app_main.c"), "-o", app],
                               capture_output=True, text=True)
            assert r.returncode == 0, r.stderr[-4000:]
            mains = {name: os.path.join(str(base), name + ".o") for name in exes}
            board = [os.path.join(str(base), n[:-2] + ".o") for n in BOARD_SOURCES]
            apps = [os.path.join(str(base), n[:-2] + ".o") for n in APP_SOURCES]
            shared = [o for o in objs if o not in mains.values() and o not in board]
            for name, exe in exes.items():
                own = [mains[name]] + {"board_main": board, "app_main": apps}.get(name, [])
                r = subprocess.run([cc] + CFLAGS + shared + own + [seal, "-o", exe + ".tmp"],
                                   capture_output=True, text=True)
                assert r.returncode == 0, r.stderr[-4000:]
                os.replace(exe + ".tmp", exe)
    return exes


def run(harness, script, root):
    # one stream, as a terminal shows them: the harness writes each unbuffered
    r = subprocess.run([harness["sh_main"], "-t", str(root), script], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=60, env=dict(os.environ, TZ="UTC"))
    return r.stdout.decode("utf-8", "replace") + "[exit %d]\n" % r.returncode


SCRIPT_NAMES = sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(SCRIPTS, "*.sh")))


@pytest.mark.parametrize("name", SCRIPT_NAMES)
def test_the_script_runs_as_its_transcript_says(harness, tmp_path, name):
    script = os.path.join(SCRIPTS, name + ".sh")
    golden = os.path.join(SCRIPTS, name + ".out")
    root = tmp_path / "root"
    root.mkdir()
    got = run(harness, script, root)
    assert "Sanitizer" not in got and "runtime error" not in got, got
    if os.environ.get("MOYBYTE_UPDATE_GOLDENS"):
        with open(golden, "w", encoding="utf-8") as f:
            f.write(got)
    assert os.path.isfile(golden), "no transcript for %s: run with MOYBYTE_UPDATE_GOLDENS=1" % name
    with open(golden, encoding="utf-8") as f:
        assert got == f.read()


def test_a_walk_takes_the_same_c_stack_at_any_depth(harness, tmp_path):
    """find, du and rm -r walk a tree with no C frame and no arena per folder
    (moy_sh_cmds.c's walk), so the deepest C stack a poll sees is the same
    at 2 levels and 150, in an arena of 24 KB. A frame per level overflowed
    the C3's 12 KB SSH task at 51; the folders kept on the shell's stack ran
    its 12 KB arena out, and the out-of-space message recursed until the
    stack overflowed."""
    def deepest(levels):
        root = tmp_path / ("root%d" % levels)
        root.mkdir()
        script = tmp_path / ("walk%d.sh" % levels)
        script.write_text("p=d; i=0; while [ $i -lt %d ]; do p=$p/a; i=$((i+1)); done\n"
                          "mkdir -p $p; echo x > $p/f\n"
                          "find d -name f; du -s d; rm -r d\n" % levels)
        r = subprocess.run([harness["sh_main"], str(root), str(script)], capture_output=True,
                           timeout=60, env=dict(os.environ, SH_MAIN_MEASURE="1",
                                                SH_MAIN_ARENA="24"))
        assert r.returncode == 0 and not os.listdir(root), r.stdout.decode()[-2000:]
        return int(re.search(rb"c stack (\d+)", r.stderr).group(1))

    shallow, deep = deepest(2), deepest(150)
    assert deep - shallow < 256, "2 levels: %d B, 150 levels: %d B" % (shallow, deep)


def test_a_walk_looks_up_no_entry_by_its_path(harness, tmp_path):
    """find, du and rm -r take each entry's kind and size from its folder's
    listing (moy_sh_cmds.c's walk_names), so a folder of 200 files costs a
    few store calls, not one per file: a lookup by path on littlefs walks
    the path from the root, about 3 ms a part on the C3."""
    def calls(files):
        root = tmp_path / ("root%d" % files)
        (root / "d" / "e").mkdir(parents=True)
        for i in range(files):
            (root / "d" / "e" / ("f%03d" % i)).write_bytes(b"x" * i)
        script = tmp_path / ("wide%d.sh" % files)
        script.write_text("du -s d; find d -name f199; rm -r d\n")
        r = subprocess.run([harness["sh_main"], str(root), str(script)], capture_output=True,
                           timeout=60, env=dict(os.environ, SH_MAIN_MEASURE="1"))
        assert r.returncode == 0 and not os.listdir(root), r.stdout.decode()[-2000:]
        return int(re.search(rb"store calls (\d+)", r.stderr).group(1)), r.stdout

    few, (many, out) = calls(1)[0], calls(200)
    assert b"d/e/f199" in out and out.startswith(b"%d" % ((sum(range(200)) + 1023) // 1024))
    # rm -r still removes each file by its path: one call a file, no more
    assert many - few < 200 + 20, "1 file: %d calls, 200 files: %d" % (few, many)


def _tree(root, files):
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)


def test_rm_r_takes_saved_files_with_their_backups_in_one_pass(harness, tmp_path):
    """A file's remove takes the store's backup of it (moy_sh_cmds.c's vol
    op), which the folder's listing still names: `rm -r` counts that entry
    removed and goes on, one pass leaving nothing and exiting 0. A user's
    own `.bak` goes as any file does."""
    root = tmp_path / "root"
    _tree(root, {"d/f": b"x", "d/.f.moybak": b"#moyfs1 1 1\nx", "d/g.bak": b"mine",
                 "d/e/h": b"y", "d/e/.h.moybak": b"#moyfs1 1 2\ny"})
    script = tmp_path / "rmr.sh"
    script.write_text("rm -r d; echo rc=$?\n")
    out = run(harness, str(script), root)
    assert out.endswith("\nrc=0\n[exit 0]\n") and not os.listdir(root), out


def test_rm_and_mv_take_the_stores_backup_and_never_a_users_bak(harness, tmp_path):
    """`report.bak` beside `report` is the user's: `rm report` and `mv
    notes x` take the store's backup of the file they move or remove, and
    leave every other file."""
    root = tmp_path / "root"
    _tree(root, {"report": b"r", ".report.moybak": b"#moyfs1 1 1\nr", "report.bak": b"mine",
                 "notes": b"n", ".notes.moybak": b"#moyfs1 1 1\nn", "notes.bak": b"also mine"})
    script = tmp_path / "rm.sh"
    script.write_text("rm report; mv notes x; echo rc=$?\n")
    out = run(harness, str(script), root)
    assert out.endswith("\nrc=0\n[exit 0]\n"), out
    assert sorted(os.listdir(root)) == ["notes.bak", "report.bak", "x"], out
    assert (root / "report.bak").read_bytes() == b"mine"


def test_the_stores_backups_never_show_in_ls_find_or_du(harness, tmp_path):
    root = tmp_path / "root"
    _tree(root, {"d/f": b"x" * 2000, "d/.f.moybak": b"x" * 9000, "d/.hidden": b"h"})
    script = tmp_path / "ls.sh"
    script.write_text("ls d; echo --; ls -a d; echo --; find d; echo --; du -s d\n")
    out = run(harness, str(script), root)
    parts = out.split("\n--\n")
    assert "moybak" not in out and len(parts) == 4, out
    assert ".hidden" in parts[1], out
    assert parts[3].split()[0] == "2", out       # the 2 KB file alone, in 1K blocks


def test_an_arena_run_out_is_an_error_not_a_reset(harness, tmp_path):
    """A block the arena refuses is dash's "Out of space", raised bare when
    its own message finds no room (moy_sh.c's refused). Reported again, it
    recursed until the C stack ran out, which reset the C3. Each script runs
    the arenas out at different points as their size moves."""
    scripts = [
        # a deep tree's path and its walk
        "p=t; i=0; while [ $i -lt 200 ]; do p=$p/a; i=$((i+1)); done\n"
        "mkdir -p $p; find t -name zz; du -s t\n",
        # a command substitution's output (the old shell overflowed at most sizes)
        "x=$(i=0; while [ $i -lt 3000 ]; do echo abcdefghij; i=$((i+1)); done)\necho ${#x}\n",
    ]
    for k, text in enumerate(scripts):
        script = tmp_path / ("out%d.sh" % k)
        script.write_text(text + "echo the end\n")
        for kb in range(14, 41):
            root = tmp_path / ("root%d_%d" % (k, kb))
            root.mkdir()
            r = subprocess.run([harness["sh_main"], str(root), str(script)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
                               env=dict(os.environ, SH_MAIN_ARENA=str(kb)))
            out = r.stdout.decode("utf-8", "replace")
            assert "Sanitizer" not in out, "%d KB: %s" % (kb, out[-1500:])


def test_tail_of_a_pipe_holds_its_last_lines_not_the_stream(harness, tmp_path):
    """`grep ... | tail` on the C3 Zero said "tail: Out of space": tail read
    the whole pipe into the session's arena. It holds the lines it prints and
    a read or two, so 140 KB through a 32 KB arena (the host harness's
    session takes more of one than a board's) ends in its last lines or
    bytes, a partial last line counting as one."""
    script = tmp_path / "t.sh"
    script.write_text(
        "gen() { i=0; while [ $i -lt 4000 ]; do echo \"line $i of the stream, padded out\";"
        " i=$((i+1)); done; }\n"
        "gen | tail -n 3\n"
        "gen | tail -c 12\n"
        "gen | tail -n 0 | wc -c\n"
        "(gen; printf 'no newline') | tail -n 2; echo\n"
        "gen | tail -2\n")
    root = tmp_path / "root"
    root.mkdir()
    r = subprocess.run([harness["sh_main"], str(root), str(script)], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=120, env=dict(os.environ, SH_MAIN_ARENA="32"))
    out = r.stdout.decode("utf-8", "replace")
    assert out == ("line 3997 of the stream, padded out\nline 3998 of the stream, padded out\n"
                   "line 3999 of the stream, padded out\n"
                   " padded out\n"
                   "0\n"
                   "line 3999 of the stream, padded out\nno newline\n"
                   "line 3998 of the stream, padded out\nline 3999 of the stream, padded out\n"), out


def test_a_file_written_streams_in_chunks(harness, tmp_path):
    """A redirect and tee send a file to the store a chunk at a time
    (moy_sh_sys.c's streamed FILE), so 64 KB written takes no block near its
    size. Buffered whole, it took one block the file's size, and the C3's
    heap refused the 16 KB step past 8 KB."""
    root = tmp_path / "root"
    root.mkdir()
    script = tmp_path / "write.sh"
    script.write_text("i=0; while [ $i -lt 4096 ]; do echo 0123456789abcde; i=$((i+1)); done > big\n"
                      "echo more >> big; echo again > x; tee -a big < x > /dev/null\n")
    r = subprocess.run([harness["sh_main"], str(root), str(script)], capture_output=True,
                       timeout=60, env=dict(os.environ, SH_MAIN_MEASURE="1"))
    assert r.returncode == 0, r.stderr.decode()
    assert os.path.getsize(root / "big") == 65536 + 5 + 6
    largest = int(re.search(rb"largest block (\d+)", r.stderr).group(1))
    assert largest < 8192, "a block of %d B" % largest



def test_a_file_read_comes_in_chunks(harness, tmp_path):
    """A file opened to read is held and read a chunk at a time
    (moy_sh_sys.c's READ), so a 64 KB file through every reader takes no
    block near its size. Read whole at the open, it took one block the
    file's size, which the C3's heap refused ("Not enough space")."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "big").write_bytes(b"0123456789abcde\n" * 4096)
    (root / "s.sh").write_bytes(b"n=1 # a sourced script of 64 KB\n" * 2048)
    script = tmp_path / "read.sh"
    script.write_text("cat big > /dev/null; md5sum big; sha256sum big; tail -n 1 big\n"
                      "tail -c 3 big; head -n 1 big; grep -c abc big; wc -l < big\n"
                      "cut -c 1-3 big > /dev/null; . ./s.sh; echo n=$n\n")
    r = subprocess.run([harness["sh_main"], str(root), str(script)], capture_output=True,
                       timeout=60, env=dict(os.environ, SH_MAIN_MEASURE="1"))
    assert r.returncode == 0 and b"n=1" in r.stdout and b"4096" in r.stdout, r.stdout.decode()
    largest = int(re.search(rb"largest block (\d+)", r.stderr).group(1))
    assert largest < 8192, "a block of %d B" % largest


def test_a_pipe_holds_its_stream_in_chunks(harness, tmp_path):
    """A pipe's buffer is chunks of the heap (moy_sh_sys.c's PIPE_R/PIPE_W),
    so 64 KB through a pipe takes no block near its size. One buffer
    doubled as it grew took a block of 64 KB, which the C3's heap refused at
    each write ("I/O error" per echo). The largest block left is a fork's
    snapshot of the arena in use (about 14 KB on the host)."""
    root = tmp_path / "root"
    root.mkdir()
    script = tmp_path / "pipe.sh"
    script.write_text("i=0; while [ $i -lt 4096 ]; do echo 0123456789abcde; i=$((i+1)); done"
                      " | tee t | wc -c\n")
    r = subprocess.run([harness["sh_main"], str(root), str(script)], capture_output=True,
                       timeout=60, env=dict(os.environ, SH_MAIN_MEASURE="1"))
    assert r.returncode == 0 and b"65536" in r.stdout, r.stdout.decode()
    largest = int(re.search(rb"largest block (\d+)", r.stderr).group(1))
    assert largest < 16384, "a block of %d B" % largest


def _spill_run(harness, root, text):
    script = root.parent / "spill.sh"
    script.write_text(text)
    return subprocess.run([harness["sh_main"], str(root), str(script)], capture_output=True,
                          timeout=120, env=dict(os.environ, SH_MAIN_MEASURE="1"))


def test_a_pipe_past_its_memory_goes_on_in_a_file_of_the_store(harness, tmp_path):
    """On a board without PSRAM a pipe holds 4 KB in memory (so does every
    host harness, CFLAGS), and the stages
    of a pipeline run one after another, so `grep | tail` printed the last
    lines of the first 4 KB ("pipe: stream over 4 KB"). Past its memory the
    stream goes on in /.pipes/<pipe>.tmp (moy_sh_sys.c's SPILL), the reader
    reads the memory, then the file, through one chunk, and the file and its
    folder go at the pipe's last close."""
    root = tmp_path / "root"
    root.mkdir()
    lines = ["line %d of the stream, padded out" % i for i in range(3000)]
    (root / "big.txt").write_text("".join(x + "\n" for x in lines))
    (root / "z").write_bytes(bytes(range(256)) * 256)
    r = _spill_run(harness, root,
                   "grep 'line 1' big.txt | tail -n 2\n"
                   "cat z | wc -c\n"
                   "cat z | md5sum\n"
                   "cat big.txt | (ls /.pipes | wc -l; wc -l)\n"
                   "cat z | cat | cat | wc -c\n")
    out = r.stdout.decode()
    ones = [x for x in lines if "line 1" in x]
    want = "\n".join(ones[-2:]) + "\n65536\n%s  -\n1\n3000\n65536\n" % (
        hashlib.md5((bytes(range(256)) * 256)).hexdigest())
    assert r.returncode == 0 and out == want, out + r.stderr.decode()[-2000:]
    assert b"pipe:" not in r.stderr, r.stderr.decode()
    assert not (root / ".pipes").exists()
    largest = int(re.search(rb"largest block (\d+)", r.stderr).group(1))
    assert largest < 16384, "a block of %d B" % largest


def test_the_boots_first_spill_sweeps_what_a_reset_left(harness, tmp_path):
    """A reset leaves its spills in the pipes folder; no boot pays to look for
    them. The boot's first spill removes what the folder holds before it makes
    its own (no spill is open before it), and the folder goes with it."""
    root = tmp_path / "root"
    (root / ".pipes").mkdir(parents=True)
    for name in ("3fc8a2b0.tmp", "3fc8a9f0.tmp"):
        (root / ".pipes" / name).write_bytes(b"x" * 2048)
    (root / "z").write_bytes(bytes(range(256)) * 64)
    r = _spill_run(harness, root, "ls /.pipes | wc -l\ncat z | (ls /.pipes | wc -l; wc -c)\n")
    assert r.stdout.decode() == "2\n1\n16384\n", r.stdout.decode() + r.stderr.decode()[-2000:]
    assert not (root / ".pipes").exists()


def test_a_spill_goes_when_its_writer_is_interrupted(harness, tmp_path):
    """A writer Ctrl-C ends mid-spill, a reader that stops early, and an
    interrupted reader each leave no spill behind."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "z").write_bytes(b"0123456789abcde\n" * 4096)
    r = _spill_run(harness, root,
                   "i=0; while [ $i -lt 4000 ]; do echo 0123456789abcde; i=$((i+1));"
                   " [ $i = 1000 ] && echo 1 > /.interrupt; done | wc -c\n"
                   "cat z | head -n 1\n"
                   "cat z | (echo 1 > /.interrupt; while read l; do :; done)\n"
                   "ls -a /\n")
    out = r.stdout.decode()
    assert "0123456789abcde\n" in out and ".pipes" not in out, out
    assert not (root / ".pipes").exists()


def test_a_builtin_ended_midway_leaves_the_heap_as_it_found_it(harness, tmp_path):
    """A built-in ended before it returns -- its writer ended as SIGPIPE would
    by a spill the store has no room for, or interrupted -- longjmps past its
    frees, and its process gives back the blocks it held (moy_sh.c's PROCESS
    BLOCK): three rounds of each leave the session holding what one does."""
    import resource
    import signal

    def limit():
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        resource.setrlimit(resource.RLIMIT_FSIZE, (16384, 16384))
    lines = ["find d | head -n 1", "du d | head -n 1", "sort big.txt | head -n 1",
             "grep line big.txt | head -n 1", "cut -c1-9 big.txt | head -n 1",
             "uniq big.txt | head -n 1", "ls -l d d d d d d d d | head -n 1",
             "echo 40 > /.interrupt; find d -name nothing"]
    held = []
    for rounds in (1, 3):
        root = tmp_path / ("root%d" % rounds)
        deep = root / "d"
        for i in range(150):
            deep = deep / "a"
        deep.mkdir(parents=True)
        (deep / "f").write_text("x\n")
        (root / "big.txt").write_text(
            "".join("line %d of the stream, padded out\n" % i for i in range(3000)))
        script = tmp_path / ("ended%d.sh" % rounds)
        script.write_text("".join(x + "\n" for x in lines) * rounds)
        r = subprocess.run([harness["sh_main"], str(root), str(script)], capture_output=True,
                           timeout=120, preexec_fn=limit, env=dict(os.environ, SH_MAIN_MEASURE="1"))
        err = r.stderr.decode()
        assert "Sanitizer" not in err, err[-3000:]
        assert err.count("pipe: no room to hold") >= 6 * rounds, err[-2000:]
        held.append(int(re.search(r"live blocks (\d+)", err).group(1)))
    assert held[0] == held[1], "%d blocks after one round, %d after three" % tuple(held)


def test_a_spill_the_store_has_no_room_for_says_so(harness, tmp_path):
    """A spill past what the store takes (here a file-size limit, EFBIG) ends
    its writer with "pipe: no room to hold N KB", the reader reads what came
    before, and the file goes."""
    import resource
    import signal

    def limit():
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        resource.setrlimit(resource.RLIMIT_FSIZE, (16384, 16384))
    root = tmp_path / "root"
    root.mkdir()
    script = tmp_path / "full.sh"
    script.write_text("i=0; while [ $i -lt 4096 ]; do echo 0123456789abcde; i=$((i+1)); done"
                      " | wc -c\n")
    r = subprocess.run([harness["sh_main"], str(root), str(script)], capture_output=True,
                       timeout=120, preexec_fn=limit)
    out = r.stdout.decode() + r.stderr.decode()
    assert "pipe: no room to hold 21 KB" in out, out
    assert "20480" in out, out
    assert not (root / ".pipes").exists()


SERIAL = os.path.join(SCRIPTS, "serial")
SERIAL_NAMES = sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(SERIAL, "*.sh")))


def _door(name):
    """board_main's door for a serial script: a `vm_` script's the stand-in
    console, a `zero_` script's the Zero's, the others the VM stopped."""
    return ["-vm"] if name.startswith("vm_") else ["-zero"] if name.startswith("zero_") else []


@pytest.mark.parametrize("name", SERIAL_NAMES)
def test_the_serial_face_answers_as_its_transcript_says(harness, tmp_path, name):
    """The board's host table (moy_sh_board.c) and the serial face, each
    script line fed as the dev channel's `sh` word feeds it, each line the
    face says printed as the channel carries it. A `vm_` script runs with a
    stand-in console behind the ROLE door, a `zero_` script with the Zero's
    door, whose role commands but the store's say "not served here"; the
    others with the VM stopped, where `ps`, `kill` and `log` answer from the
    kernel and the console's commands say "needs the console"."""
    script = os.path.join(SERIAL, name + ".sh")
    golden = os.path.join(SERIAL, name + ".out")
    root = tmp_path / "root"
    root.mkdir()
    _seed_home(root, name)
    args = [harness["board_main"]] + _door(name) + [script]
    r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
                       env=dict(os.environ, TZ="UTC", MOY_SH_ROOT=str(root)))
    got = r.stdout.decode("utf-8", "replace") + "[exit %d]\n" % r.returncode
    assert "Sanitizer" not in got and "runtime error" not in got, got
    if os.environ.get("MOYBYTE_UPDATE_GOLDENS"):
        with open(golden, "w", encoding="utf-8") as f:
            f.write(got)
    assert os.path.isfile(golden), "no transcript for %s: run with MOYBYTE_UPDATE_GOLDENS=1" % name
    with open(golden, encoding="utf-8") as f:
        assert got == f.read()


def _seed_home(root, name):
    """A `home_` script's tree holds a console's store on its card, a
    `nocard_` script's on the internal flash (/moy): its carts and its files
    folder, where the session starts (moy_sh_board_go_home). A `late_`
    script's card holds no store yet: the session starts before it does."""
    if name.startswith("late_"):
        (root / "sd").mkdir()
    store = ("sd/moybyte" if name.startswith("home_")
             else "moy" if name.startswith("nocard_") else None)
    for sub in ("carts", "files") if store else ():
        (root / store / sub).mkdir(parents=True)


def _face(harness, path, root, screen):
    name = os.path.basename(path)
    args = ([harness["board_main"]] + _door(name)
            + (["-screen"] if screen else []) + [path])
    r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
                       env=dict(os.environ, TZ="UTC", MOY_SH_ROOT=str(root)))
    return r.stdout.decode("utf-8", "replace")


# interrupt.sh's Ctrl-C is sh_main's stand-in (/.interrupt), which no face polls;
# neofetch's rows are sh_main's stand-in console's, and the screen face draws
# them in colour where the serial face (TERM=dumb) writes them plain;
# an `app_` script's text app shows on the screen face's own screen, which
# tests/test_terminal.py holds; a `%stop` line (a stopped run's) releases the
# serial face's session, which a screen face's is not.
def _replays(name):
    with open(os.path.join(SERIAL, name + ".sh"), encoding="utf-8") as f:
        return not name.startswith("app_") and "%stop" not in f.read().split("\n")


REPLAYS = ([os.path.join(SERIAL, n + ".sh") for n in SERIAL_NAMES if _replays(n)]
           + [os.path.join(SCRIPTS, n + ".sh") for n in SCRIPT_NAMES
              if n not in ("interrupt", "builtin_neofetch")])


@pytest.mark.parametrize("path", REPLAYS, ids=[os.path.relpath(p, SCRIPTS) for p in REPLAYS])
def test_the_screen_face_replays_the_serial_transcript(harness, tmp_path, path):
    """One transcript, both faces: each serial script's lines fed to the
    screen face (moy_sh_screen.c) give, line for line, what its grid shows,
    the serial face's output with its tabs set at the grid's stops and
    its trailing blanks, which a grid does not hold, dropped. A
    transcript that writes escapes (`clear`) says them raw on serial and
    moves the grid, so it is the grid's own test's. Every script of the
    suite replays so too, over the board's table in place of sh_main's."""
    for side in ("a", "b"):
        (tmp_path / side).mkdir()
        _seed_home(tmp_path / side, os.path.basename(path)[:-3])
    serial = _face(harness, path, tmp_path / "a", False)
    if "\x1b" in serial:
        pytest.skip("escapes: the grid's test reads them")
    screen = _face(harness, path, tmp_path / "b", True)
    assert "Sanitizer" not in screen and "runtime error" not in screen, screen
    want = ["SH " + ln[3:].expandtabs(8).rstrip(" ") if ln.startswith("SH ") else ln
            for ln in serial.split("\n")]
    assert screen.split("\n") == want


# -- the text apps' memory (host/app_main.c) -----------------------------------------

EDIT_BLOCK = 1024       # moy_sh_edit.c's BLK: the most any request for text may be


def _lines(n):
    """`n` bytes of lines of 31 to 70 characters, a newline ending them."""
    out, size, i = [], 0, 0
    while size < n:
        ln = ("%05d " % i + "the quick brown fox jumps over the lazy dog and on" * 2)[:31 + (i * 7) % 40]
        out.append(ln.rstrip() + "\n")
        size += len(out[-1])
        i += 1
    return "".join(out)[:n - 1] + "\n"


def _line_at(text, ln):
    return sum(len(x) for x in text.splitlines(keepends=True)[:ln])


def _edit_session(text, rows):
    """edit's keys: down five lines, a line of 1500 characters typed (past a
    block, into blocks of its own), a page down, a word typed and twenty
    characters deleted there, saved and closed; and the file it leaves."""
    typed = "abcdefghij" * 150
    keys = ["^[[B" * 5, typed + "^M", "^[[6~", "tail", "^[[H", "^[[3~" * 20, "^S", "%meter", "^X"]
    p = _line_at(text, 5)
    t = text[:p] + typed + "\n" + text[p:]
    q = _line_at(t, 6 + rows - 3)
    t = t[:q] + "tail" + t[q:]
    return keys, t[:q] + t[q + 20:]


def _vi_session(text, rows):
    """vi's keys: every line yanked (a register as big as the file) and put
    after the last, undone and done again (the undo step a copy of it), a
    line deleted and a character, saved and closed; and the file it leaves."""
    keys = ["1G", "%dyy" % text.count("\n"), "G", "p", "u", "^R", "5G", "dd", "x", ":w^M",
            "%meter", ":q^M"]
    ls = (text + text).splitlines(keepends=True)
    del ls[4]
    ls[4] = ls[4][1:]
    return keys, "".join(ls)


@pytest.mark.parametrize("size", (4096, 8192, 16384))
@pytest.mark.parametrize("app", ("edit", "vi"))
def test_the_editor_asks_for_no_text_bigger_than_a_block(harness, tmp_path, app, size):
    """#276: a board without PSRAM has its free memory in pieces, so `edit`
    and `vi` hold their text in blocks and no request they make for it, at
    the open, a growth, a register, an undo step or the save, is bigger than
    one block. The app heap here refuses any bigger one, as a heap whose
    largest free piece is a block refuses it; the app's own record and
    screen (moy_sh_app_new's, made before the file is read) are not text.
    A file of 4 to 16 KB opens, grows past a block, saves and reads back
    as written, and the store holds no copy of it on the way."""
    rows = 12
    root = tmp_path / "root"
    root.mkdir()
    text = _lines(size)
    (root / "f.txt").write_text(text)
    keys, want = (_edit_session if app == "edit" else _vi_session)(text, rows)
    script = tmp_path / "keys"
    script.write_text("\n".join(["%%size 40 %d" % rows, "%s /f.txt" % app] + keys) + "\n")
    r = subprocess.run([harness["app_main"], str(root), str(script)], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=60,
                       env=dict(os.environ, TZ="UTC", MOY_SH_APP_ALLOC_MAX=str(EDIT_BLOCK)))
    out = r.stdout.decode("utf-8", "replace")
    assert "Sanitizer" not in out and "runtime error" not in out, out
    assert r.returncode == 0 and "out of memory" not in out, out
    assert re.search(r"^\| saved, %d bytes " % len(want), out, re.M), out
    m = re.search(r"meter largest (\d+) most \d+ live \d+ refused (\d+) store largest (\d+)", out)
    assert m and int(m.group(2)) == 0 and int(m.group(1)) <= EDIT_BLOCK, out
    assert int(m.group(3)) < 2048, out          # the store's own scratch, never the text
    assert out.endswith("end\n"), out
    assert (root / "f.txt").read_text() == want


@pytest.mark.parametrize("cols,rows", ((80, 24), (200, 60)))
@pytest.mark.parametrize("app", ("edit", "vi"))
def test_a_straight_editor_opens_in_its_record_at_any_size(harness, tmp_path, app, cols, rows):
    """The C3 Zero has about 36 KB free beside an SSH session and keeps 16 KB
    of it (MOY_SH_HEAP_RESERVE): `vi` at 200 by 60 asked for a 48 KB screen
    and said "out of memory". The stream face there takes a full-screen app
    straight (moy_sh_app.h), so what the open asks for is the front and the
    record, whatever the terminal's size, and a 20 KB file opens, is edited
    and saved in blocks, the terminal showing what the app wrote."""
    root = tmp_path / "root"
    root.mkdir()
    text = _lines(20 * 1024)
    (root / "f.txt").write_text(text)
    keys, want = (_edit_session if app == "edit" else _vi_session)(text, rows)
    script = tmp_path / "keys"
    script.write_text("\n".join(["%%size %d %d" % (cols, rows), "%straight", "%s /f.txt" % app,
                                 "%meter", "%screen"] + keys) + "\n")
    r = subprocess.run([harness["app_main"], str(root), str(script)], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=60,
                       env=dict(os.environ, TZ="UTC", MOY_SH_APP_ALLOC_MAX=str(EDIT_BLOCK)))
    out = r.stdout.decode("utf-8", "replace")
    assert "Sanitizer" not in out and "runtime error" not in out, out
    assert r.returncode == 0 and "out of memory" not in out, out
    m = re.search(r"meter largest \d+ most \d+ live \d+ refused \d+ store largest -?\d+ most -?\d+"
                  r" fixed (\d+) (\d+) (\d+) (\d+)", out)
    front, record, none = int(m.group(1)), int(m.group(2)), int(m.group(3)) + int(m.group(4))
    assert none == 0 and front + record <= 1536, out      # no screen; the record ~1.3 KB
    assert "| " + text.splitlines()[0] in out, out          # %screen: the terminal's rows
    assert re.search(r"^\| saved, %d bytes " % len(want), out, re.M), out
    assert out.endswith("end\n"), out
    assert (root / "f.txt").read_text() == want


def test_every_core_builtin_has_its_script():
    """A C built-in is tested by tests/moy_sh/builtin_<name>.sh."""
    with open(os.path.join(SH, "moy_sh_cmds.c"), encoding="utf-8") as f:
        table = f.read().split("static const struct builtincmd core[] = {")[1].split("};")[0]
    names = re.findall(r'\{ "([a-z0-9]+)",', table)
    assert names == sorted(names), "the core table is searched by bisection: keep it sorted"
    aliases = {"dmesg": "log", "vim": "vi", "view": "vi", "less": "vi", "more": "vi"}
    missing = [n for n in names if aliases.get(n, n) not in
               {s[len("builtin_"):] for s in SCRIPT_NAMES if s.startswith("builtin_")}]
    assert not missing, "built-ins with no script: %s" % missing


def test_the_shell_keeps_no_writable_data_but_its_state_pointer(tmp_path):
    """Every dash global is a field of the session's record (moy_sh_g.h), in
    the arena: compiled as a board compiles it (no PIC), the shell's objects
    hold one writable word, moy_sh_g, and nothing in .data or .bss besides.
    The board's host table and the serial face (moy_sh_board.c) keep none:
    the serial session is parked in that word (moy_sh_park), and the
    Terminal's face (moy_sh_face.c) keeps everything in its record."""
    cc = shutil.which(os.environ.get("CC", "cc"))
    nm = shutil.which("nm")
    if cc is None or nm is None:
        pytest.skip("no C compiler or nm")
    flags = ["-std=gnu99", "-Os", "-fno-pic", "-fno-pie", "-fno-common",
             "-include", os.path.join(SH, "dash_config.h"), "-I", SH, "-I", DASH, "-I", STORE,
             "-I", KERNEL] + MBEDTLS
    plain = ["-std=gnu99", "-Os", "-fno-pic", "-fno-pie", "-fno-common",
             "-I", SH, "-I", KERNEL, "-I", STORE, "-I", SPINE]
    writable = []
    for src in shell_sources() + [os.path.join(SH, n) for n in ("moy_sh_arena.c", "moy_sh_fmt.c", "moy_sh_cands.c")
                                  + BOARD_SOURCES + FACE_SOURCES]:
        obj = str(tmp_path / (os.path.basename(src)[:-2] + ".o"))
        own = flags if src in shell_sources() else plain + UI_INCLUDES
        r = subprocess.run([cc] + own + ["-c", src, "-o", obj], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-2000:]
        for line in subprocess.check_output([nm, obj], text=True).splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[1] in "bBdDcC":
                writable.append("%s: %s" % (os.path.basename(src), parts[2]))
    assert writable == ["moy_sh.c: moy_sh_g"], writable


def test_no_shell_object_calls_the_c_library_s_descriptors(tmp_path):
    """dash's file calls are the shell's own (moy_sh_posix.h's names over
    moy_sh_sys.c's descriptors): a source that missed the shim called the
    C library's close() on the process's real descriptors -- mkinit's init.c
    did, closing an SSH session's sockets at a command substitution's end."""
    cc = shutil.which(os.environ.get("CC", "cc"))
    nm = shutil.which("nm")
    if cc is None or nm is None:
        pytest.skip("no C compiler or nm")
    flags = ["-std=gnu99", "-Os", "-include", os.path.join(SH, "dash_config.h"),
             "-I", SH, "-I", DASH, "-I", STORE, "-I", KERNEL] + MBEDTLS
    raw = {"open", "read", "write", "close", "dup", "dup2", "fcntl", "pipe", "lseek",
           "open64", "stat", "fstat", "lstat"}
    calls = []
    for src in shell_sources():
        obj = str(tmp_path / (os.path.basename(src)[:-2] + ".o"))
        r = subprocess.run([cc] + flags + ["-c", src, "-o", obj], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-2000:]
        for line in subprocess.check_output([nm, "-u", obj], text=True).splitlines():
            if line.split()[-1] in raw:
                calls.append("%s: %s" % (os.path.basename(src), line.split()[-1]))
    assert calls == [], calls


def test_every_source_keeps_the_const_a_c23_library_preserves(tmp_path):
    """A newer C library's C23 bsearch, strchr, strchrnul ... answer a const
    pointer for a const argument, and CI's compiler refused dash's implicit
    drops of it (exec.c's bsearch over the const builtin table). Every shell
    source compiles here with tests/moy_sh/c23_const.h force-included, which
    defines them so, under -Werror: this machine refuses what CI refuses, and
    a re-vendor of dash cannot bring the error back unseen. Syntax only, in
    parallel: it reads, never generates code."""
    cc = shutil.which(os.environ.get("CC", "cc"))
    if cc is None:
        pytest.skip("no C compiler")
    guard = ["-include", os.path.join(SCRIPTS, "c23_const.h")]
    base = ["-std=gnu99", "-fsyntax-only", "-Wall", "-Werror"] + guard
    dash = base + ["-include", os.path.join(SH, "dash_config.h"), "-I", SH, "-I", DASH,
                   "-I", STORE, "-I", KERNEL] + MBEDTLS
    plain = base + ["-I", SH, "-I", KERNEL, "-I", STORE, "-I", SPINE]
    jobs = [(src, dash) for src in shell_sources()]
    jobs += [(os.path.join(SH, n), plain) for n in ("moy_sh_arena.c", "moy_sh_fmt.c", "moy_sh_cands.c",
                                                     "host/sh_main.c", "host/board_main.c",
                                                     "host/app_main.c")
             + BOARD_SOURCES]
    jobs += [(os.path.join(SH, n), plain + UI_INCLUDES) for n in FACE_SOURCES]

    def one(job):
        src, flags = job
        r = subprocess.run([cc] + flags + [src], capture_output=True, text=True)
        return src, r

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        bad = [(src, r.stderr[-1500:]) for src, r in pool.map(one, jobs) if r.returncode]
    assert not bad, bad
