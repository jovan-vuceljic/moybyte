/* The browser console this image names.
 *
 * The console is not in the image. It is the add-on cart's `moybyte_web.pack`
 * (native/moy_net/moy_page.h, THE PACK), and the image carries the sha256
 * of the pack's body it serves (moy_web_want) and of the whole pack
 * (moy_web_pack_sha), the stamp of the bundle that pack was made from, and
 * the loader page (moy_page.h, THE LOADER). Both are GENERATED (moy_web_blob.gen.c, by
 * tools/gen_web_blob.py, which writes the pack too); this header is the
 * contract between that file and its readers, and the only part a human
 * edits. */
#ifndef MOY_WEB_BLOB_H
#define MOY_WEB_BLOB_H

#include <stddef.h>
#include <stdint.h>

/* 1 when this image names a page (a bundle was built with it), else 0. */
extern const unsigned char moy_web_named;
extern const unsigned char moy_web_want[32];
/* The sha256 of the whole pack file (head included): what the loader checks. */
extern const unsigned char moy_web_pack_sha[32];
/* "<count> <total bytes> <12 hex of the bundle digest>", or "0 0 none". */
extern const char moy_web_stamp[];
/* 1 where board.toml's `[web] console` is "online": the root serves the loader. */
extern const unsigned char moy_web_online;
/* The loader page (firmware/web_runner/loader.html), gzipped. */
extern const unsigned char moy_web_loader[];
extern const unsigned int moy_web_loader_len;

#endif /* MOY_WEB_BLOB_H */
