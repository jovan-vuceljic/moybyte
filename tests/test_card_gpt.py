"""A card partitioned GPT is the store's volume (native/moy_store/moy_card.c,
GPT_FIND): oofatfs finds a FAT volume only at sector 0 or in an MBR entry,
and many cards ship GPT, so the card volume finds the first partition whose
first sector is a FAT boot sector and reads from there. Run in the desktop
MicroPython built in the boards' model, over a card that is a bytearray behind
a fake `moy_sd`, as tests/test_store_on_vfs.py drives it."""

import subprocess

from unix_mp import require_unix_mp

SECTORS = 32768                     # a 16 MB card
FIRST = 2048                        # the partition's first sector, as gdisk aligns it

FAKE_MOY_SD = '''
SECTOR_SIZE = 512
disk = bytearray(%d * 512)
def read(block, buf, n):
    buf[:] = memoryview(disk)[block * 512:(block + n) * 512]
def write(block, buf, n):
    memoryview(disk)[block * 512:(block + n) * 512] = buf
''' % SECTORS

SCRIPT = '''
import sys, struct, vfs
sys.path.insert(0, @STAGE@)
import moy_sd, moy_store

SECTORS, FIRST = @SECTORS@, @FIRST@
LAST = SECTORS - 34


class Part:
    """The partition alone, as a computer formats it."""
    def readblocks(self, block, buf):
        moy_sd.read(FIRST + block, buf, len(buf) // 512)

    def writeblocks(self, block, buf):
        moy_sd.write(FIRST + block, buf, len(buf) // 512)

    def ioctl(self, op, arg):
        return LAST - FIRST + 1 if op == 4 else (512 if op == 5 else 0)


d = moy_sd.disk
# the protective MBR: one entry of type 0xEE over the whole card
d[446 + 4] = 0xEE
d[446 + 8:446 + 16] = struct.pack("<II", 1, SECTORS - 1)
d[510:512] = b"\\x55\\xaa"
# the header at sector 1, its entries from sector 2
h = 512
d[h:h + 8] = b"EFI PART"
d[h + 72:h + 88] = struct.pack("<QII", 2, 128, 128)
e = 1024 + 128          # the SECOND entry: the first is left unused
d[e:e + 16] = bytes(range(1, 17))                   # a basic data type GUID stand-in
d[e + 32:e + 48] = struct.pack("<QQ", FIRST, LAST)

vfs.VfsFat.mkfs(Part())
v = vfs.VfsFat(Part())
vfs.mount(v, "/p")
with open("/p/hello.txt", "w") as f:
    f.write("from the computer")
vfs.umount("/p")

vfs.mount(moy_store.card(SECTORS, moy_sd), "/sd")
print("READ", open("/sd/hello.txt").read())
with open("/sd/back.txt", "w") as f:
    f.write("from the console")
vfs.umount("/sd")

vfs.mount(vfs.VfsFat(Part()), "/p")
print("BACK", open("/p/back.txt").read())
print("MBR", bytes(d[446 + 4:446 + 5]).hex())
'''


def test_a_gpt_card_mounts_its_fat_partition(tmp_path):
    exe = require_unix_mp(board_model=True, why="the card volume's GPT partition")
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "moy_sd.py").write_text(FAKE_MOY_SD)
    script = stage / "gpt.py"
    script.write_text(SCRIPT.replace("@STAGE@", repr(str(stage)))
                      .replace("@SECTORS@", str(SECTORS)).replace("@FIRST@", str(FIRST)))
    out = subprocess.run([exe, "-X", "heapsize=64m", str(script)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    lines = dict(ln.split(" ", 1) for ln in out.stdout.splitlines() if " " in ln)
    assert lines["READ"] == "from the computer"
    assert lines["BACK"] == "from the console"
    assert lines["MBR"] == "ee", "the protective MBR was written over"
