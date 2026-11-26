// The store's crash-safe write and its file verbs, over moy_vol
// (docs/history/kernel_store_2026-10.md section 5).
//
// runtime/carts/moy_fs.py names these on every tier and its header is the crash-safety story;
// this is that story on the medium, byte for byte: the marker line
// "#moyfs1 <chars> <crc32> <path>\n" in `<root>/.publish`, the backup
// `<folder>/.<name>.moybak` led by its stamp line "#moyfs1 <chars> <crc32>\n",
// the file in place; a read that recovers only the prefix case; a spent backup
// claimed by a rename.
//
// THE BACKUP IS THE STORE'S, by a name nobody else's file has (a dot and
// MOY_FS_BAK_EXT), hidden from the shell's listings, Files and the wire: a
// remove of `x` takes x's backup and never a user's `x.bak`, which is a file
// like any other (owner, 2026-11-25: the `<path>.bak` backups older stores
// made are left as files, read as nothing else). A read takes a backup only
// where it is the save the marker names (outside every root, one stamped
// whole), or for a file that is gone the store's unstamped copy the sync's
// rotation leaves, so a file removed with its backup stays gone. A stamp counts code points as Python's len(str) does and takes the
// crc32 of the UTF-8 bytes, so a file one tier stamps reads whole on another.
//
// Paths are absolute (the host resolves each with moy_vol_at). Every call
// returns 0 or an errno value; MOY_FS_NONE is "nothing trustworthy", the
// module's None. A buffer is n bytes and a NUL, freed by moy_buf_free.

#ifndef MOY_FS_H
#define MOY_FS_H

#include <stddef.h>
#include <stdint.h>

#include "moy_vol.h"

#define MOY_FS_NONE (-1)
#define MOY_FS_ROOTS 8

typedef struct {
    char *p;
    size_t n;
} moy_buf_t;

void moy_buf_free(moy_buf_t *b);

uint32_t moy_fs_crc32(uint32_t crc, const void *p, size_t n);
void moy_fs_stamp(const char *data, size_t n, uint32_t *chars, uint32_t *crc);

// The publish marker's roots: set_publish_root, and its cache dropped.
int moy_fs_root(const char *root);
void moy_fs_roots_clear(void);
void moy_fs_unmark(const char *path);

// The plain verbs. moy_fs_read_file refuses a file over `cap` with EFBIG.
int moy_fs_read_file(const char *path, size_t cap, moy_buf_t *out);
int moy_fs_read_vol(const moy_vol_t *v, const char *rest, size_t cap,
                    moy_buf_t *out);
int moy_fs_write(const char *path, const void *data, size_t n);
int moy_fs_write_bytes(const char *path, const void *data, size_t n);
int moy_fs_exists(const char *path);
int moy_fs_stat(const char *path, moy_vol_stat_t *st);
int moy_fs_mkdir(const char *path);
int moy_fs_remove(const char *path);
// os.rename: `dst` must not exist (EEXIST where it does, as on FAT); EXDEV
// across volumes.
int moy_fs_rename(const char *src, const char *dst);

// The crash-safe write and its readers. moy_fs_publish is the three writes
// (the marker, the stamped backup, the file); a caller that gives a frame
// back between store ops makes the same save in two, moy_fs_publish_bak and
// then moy_fs_publish_mark (the marker and the file together), so a save of
// another file between them never leaves this one's publish unmarked
// (runtime/carts/moy_fs.py, _write_atomic_steps). moy_fs_publish_mark makes
// the whole save instead when the backup beside `path` is not this one's
// (another save of the same file between the two, or a reader that dropped
// it as stale).
int moy_fs_publish(const char *path, const char *data, size_t n);
// moy_fs_publish of a text that is not one buffer (the shell's editor holds
// its text in blocks): the same three writes, byte for byte, the stamp taken
// a piece at a time. `next` gives the next piece (its bytes at *p, its length;
// 0 after the last, so no piece is empty) and `rewind` starts it over, as the
// save passes over the text three times: the stamp, the backup and the file.
// moy_fs_publish is this over its one buffer.
typedef struct moy_fs_src {
    size_t (*next)(struct moy_fs_src *s, const char **p);
    void (*rewind)(struct moy_fs_src *s);
} moy_fs_src_t;
int moy_fs_publish_from(const char *path, moy_fs_src_t *src);
int moy_fs_publish_bak(const char *path, const char *data, size_t n);
int moy_fs_publish_mark(const char *path, const char *data, size_t n);
int moy_fs_read(const char *path, const char *at, moy_buf_t *out);
// moy_fs_read with the file opened as `name` in the working folder `here`
// (moy_vol_enter), or by `name` (a path) when `here` is NULL.
int moy_fs_read_in(const char *path, moy_vol_here_t *here, const char *name,
                   moy_buf_t *out);
// moy_fs_read with the text read straight into the caller's memory, a piece
// at a time, and no buffer of the store's that holds it: the same answers,
// the same heals and the same files left, for a reader that cannot spare a
// second copy of a file (the shell's editor, native/moy_sh/moy_sh_edit.c).
// `begin` is told how many bytes come (0, or an errno value the read stops
// with); then `room` lends memory for the next bytes (NULL: none, the read
// stops with MOY_ENOMEM) and `took` says how many were read into it, which
// may be none. A torn publish the read finishes from its backup calls
// `begin` again, and the backup's text follows. A refusal of the sink's is
// answered as it is, never taken for a file that cannot be read; after any
// error what the sink holds is not the file's.
typedef struct moy_fs_sink {
    int (*begin)(struct moy_fs_sink *k, size_t n);
    char *(*room)(struct moy_fs_sink *k, size_t *n);
    void (*took)(struct moy_fs_sink *k, size_t n);
} moy_fs_sink_t;
int moy_fs_read_into(const char *path, moy_fs_sink_t *k);
int moy_fs_read_stamped(const char *path, moy_buf_t *out);
int moy_fs_bak_stamp(const char *path, uint32_t *chars, uint32_t *crc);
int moy_fs_claim(const char *path, const char *dest, uint32_t chars,
                 uint32_t crc);                  // 1 taken, 0 not
void moy_fs_forget_bak(const char *path);
#define MOY_FS_BAK_EXT ".moybak"
// The backup's path for `path`, n bytes allocated (moy_store_free), or NULL;
// moy_fs_bak_into writes it into `out` where its bytes and NUL fit `cap`, and
// says how many those are.
char *moy_fs_bak_path(const char *path, size_t *n);
size_t moy_fs_bak_into(const char *path, char *out, size_t cap);
// Whether a folder entry's `name` (n bytes) is a store backup's.
int moy_fs_bak_name(const char *name, size_t n);

// `_skip`: what never crosses the wire or goes into an archive -- journal/,
// thumbs/, __pycache__/, journal.jsonl, the browser console's
// moybyte_web.pack, and moy_fs's backups and .tmp. With
// `history`, journal/ and journal.jsonl are let through.
int moy_store_skip(const char *name, size_t n, int history);

#endif // MOY_FS_H
