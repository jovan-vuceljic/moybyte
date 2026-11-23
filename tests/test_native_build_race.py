"""Processes that ask for one host library at the same moment build it once.

pytest-xdist's workers all bind their native twins while they collect, and on a
cold cache N compilers wrote one output path and the later renames found their
file gone (FileNotFoundError at collection). runtime/native_build serialises the
build on a lock beside the library: this starts several processes together on an
empty cache and wants every one to get the same finished library.
"""

import os
import subprocess
import sys

import pytest

from runtime import native_build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHILD = '''
import sys
sys.path.insert(0, %(root)r)
from runtime import native_build
print(native_build.build("race", %(shim)r, [], %(cache)r, cflags=["-std=c99", "-O1", "-fPIC", "-shared"]))
'''


def test_concurrent_builds_of_one_library_share_one_result(tmp_path):
    if native_build.cc() is None:
        pytest.skip("no C compiler here")
    shim = tmp_path / "race.c"
    # enough code that the compile is not instantaneous
    shim.write_text("int race(int x) { return x; }\n" + "".join(
        "int f%d(int x) { return x * %d + f%d(x - 1); }\n" % (i, i, i - 1)
        if i else "int f0(int x) { return x; }\n" for i in range(1500)))
    cache = tmp_path / "cache"
    code = CHILD % {"root": ROOT, "shim": str(shim), "cache": str(cache)}
    procs = [subprocess.Popen([sys.executable, "-c", code],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True) for _ in range(8)]
    outs = [p.communicate() for p in procs]
    for p, (out, err) in zip(procs, outs):
        assert p.returncode == 0, err
    paths = {out.strip() for out, _ in outs}
    assert len(paths) == 1 and os.path.exists(paths.pop())
    assert [f for f in os.listdir(cache) if f.endswith(".tmp")] == []


def test_a_build_prunes_the_cache_past_its_newest_and_its_last_day(tmp_path):
    """Every worktree shares one cache, and each change to the C builds a new
    library: the old ones go once they are past the newest few and a day old."""
    import os
    import native_build
    now = 1_000_000_000.0
    for i in range(6):
        so = tmp_path / ("moyhost-%02d.so" % i)
        so.write_bytes(b"x")
        (tmp_path / ("moyhost-%02d.so.lock" % i)).write_bytes(b"")
        (tmp_path / ("moyhost-%02d.src" % i)).mkdir()
        age = 3 * 86400 if i < 4 else 60          # 0-3 old, 4-5 fresh
        os.utime(so, (now - age + i, now - age + i))
    (tmp_path / "other-00.so").write_bytes(b"x")
    os.utime(tmp_path / "other-00.so", (0, 0))
    native_build.prune("moyhost", str(tmp_path), keep=3, age=86400, now=now)
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["moyhost-03.so", "moyhost-03.so.lock", "moyhost-03.src",
                    "moyhost-04.so", "moyhost-04.so.lock", "moyhost-04.src",
                    "moyhost-05.so", "moyhost-05.so.lock", "moyhost-05.src",
                    "other-00.so"], left
