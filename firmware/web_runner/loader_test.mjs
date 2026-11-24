// Drive loader.html's script (docs/web_console_online_2026-11.md §3, §4) in
// node with the browser's pieces it uses faked: the board's /sync, its own
// copy and the mirrors as a scripted fetch, and an IndexedDB in memory. Run
// from firmware/web_runner: `node loader_test.mjs`.
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";
import { resolveObjectURL } from "node:buffer";
import vm from "node:vm";

const HTML = readFileSync(new URL("./loader.html", import.meta.url), "utf-8");
const SCRIPT = HTML.slice(HTML.indexOf("<script>") + 8, HTML.indexOf("</script>"));
const SITE = "https://os.example/console/", DEV = "http://192.168.1.9:8321/console/";

const sha = (u) => createHash("sha256").update(u).digest("hex");

// A pack as tools/gen_web_blob.py writes it (native/moy_net/moy_page.h, THE PACK).
function makePack(items) {
    const enc = new TextEncoder(), parts = [];
    let at = 4096;
    const entries = items.map(([name, bytes]) => {
        at += -at & 3;
        const e = [name, at, bytes.length];
        parts.push([at, bytes]);
        at += bytes.length;
        return e;
    });
    at += -at & 3;
    const u = new Uint8Array(at), v = new DataView(u.buffer);
    for (const [o, b] of parts) u.set(b, o);
    u.set(enc.encode("MOYWEB01"), 0);
    v.setUint32(8, entries.length, true);
    v.setUint32(12, at, true);
    u.set(Buffer.from(sha(u.subarray(4096)), "hex"), 16);
    entries.forEach(([name, off, len], i) => {
        u.set(enc.encode(name), 48 + 48 * i);
        v.setUint32(48 + 48 * i + 40, off, true);
        v.setUint32(48 + 48 * i + 44, len, true);
    });
    return { data: u, page: sha(u.subarray(4096)), pack: sha(u) };
}

const enc = (s) => new TextEncoder().encode(s);
const PAGE = "<!doctype html><p>the console</p>";
const WORKER = "self.onmessage = () => {};";
const good = makePack([["index.html.gz", gzipSync(enc(PAGE))],
                       ["worker.js.gz", gzipSync(enc(WORKER))],
                       ["micropython.wasm", new Uint8Array([0, 97, 115, 109])]]);
const other = makePack([["index.html.gz", gzipSync(enc("<p>another console</p>"))]]);

// An IndexedDB in memory: open, one object store, get/put/delete/getAllKeys,
// each answered on a later turn, and a transaction complete once its last
// request (one made in another's onsuccess too) has been answered.
function fakeIDB(rows = new Map()) {
    const later = (f) => setTimeout(f, 0);
    const db = {
        createObjectStore() { },
        transaction() {
            let pending = 0, done = false;
            const t = {};
            const ask = (f) => {
                const q = {};
                pending++;
                later(() => {
                    q.result = f();
                    if (q.onsuccess) q.onsuccess();
                    if (--pending == 0) later(() => {
                        if (pending == 0 && !done) { done = true; if (t.oncomplete) t.oncomplete(); }
                    });
                });
                return q;
            };
            const copy = (x) => x instanceof ArrayBuffer ? x.slice(0) : Array.isArray(x) ? x.slice() : x;
            t.objectStore = () => ({
                get: (k) => ask(() => copy(rows.get(k))),
                put: (x, k) => ask(() => { rows.set(k, copy(x)); return k; }),
                delete: (k) => ask(() => { rows.delete(k); }),
                getAllKeys: () => ask(() => [...rows.keys()]),
            });
            return t;
        },
    };
    let made = false;
    return {
        rows,
        open() {
            const q = {};
            later(() => {
                q.result = db;
                if (!made) { made = true; if (q.onupgradeneeded) q.onupgradeneeded(); }
                q.onsuccess();
            });
            return q;
        },
    };
}

const buf = (u) => u.slice().buffer;

// One page load: `sync` is the board's /sync, `net` {url: bytes or status},
// `idb` the origin's store. Returns what the loader did.
async function load({ sync, net = {}, idb = fakeIDB(), mirrors = [DEV, SITE] }) {
    const asked = [], status = { textContent: "" };
    let written = null;
    const fetch = async (url) => {
        url = String(url);
        if (url.startsWith("blob:")) return new Response(resolveObjectURL(url));
        asked.push(url);
        if (url == "/sync") return new Response(JSON.stringify(sync));
        const got = net[url];
        if (got === undefined) throw new TypeError("unreachable");
        return typeof got == "number" ? new Response("", { status: got }) : new Response(got);
    };
    const document = {
        getElementById: () => status,
        open() { }, close() { },
        write(h) { written = h; },
    };
    const ctx = vm.createContext({ document, fetch, indexedDB: idb, performance, console,
        DecompressionStream, Response, Blob, TextDecoder, URL, setTimeout });
    ctx.self = ctx;
    await vm.runInContext(SCRIPT.replace("@MIRRORS@", JSON.stringify(mirrors)), ctx);
    return { asked, written, said: status.textContent, assets: ctx.moyAssets, boot: ctx.moyBoot, idb };
}

const syncOf = (p, local = 0) => ({ sync: 1, page: p.page, pack: p.pack, local });
const boardUrl = (p) => "/p/" + p.page.slice(0, 12) + "/moybyte_web.pack";

let fail = 0;
function ok(name, cond, extra = "") {
    if (cond) console.log("  ok   " + name);
    else { fail++; console.log("  FAIL " + name + (extra ? "  " + extra : "")); }
}

// Booting from a mirror: the page written, the assets inflated, the pack kept.
{
    const r = await load({ sync: syncOf(good), net: { [SITE + good.page + ".pack"]: good.data } });
    ok("a mirror's pack boots the console", r.written == PAGE, r.said);
    const w = r.assets && await new Response(resolveObjectURL(r.assets["worker.js"])).text();
    ok("a gzipped asset is inflated", w == WORKER);
    ok("an asset is typed by its name", resolveObjectURL(r.assets["micropython.wasm"]).type == "application/wasm");
    ok("the boot names its source", r.boot.from == SITE);
    ok("the pack is kept under its digest", sha(new Uint8Array(r.idb.rows.get(good.pack))) == good.pack);
}

// The source order (§4): the cache, then the board's own copy, then the mirrors in order.
{
    const idb = fakeIDB(new Map([[good.pack, buf(good.data)]]));
    const all = { [boardUrl(good)]: good.data, [DEV + good.page + ".pack"]: good.data,
                  [SITE + good.page + ".pack"]: good.data };
    let r = await load({ sync: syncOf(good, 1), net: all, idb });
    ok("the cache is the first source", r.written == PAGE && r.boot.from == "cache"
       && r.asked.join() == "/sync", r.asked.join());
    r = await load({ sync: syncOf(good, 1), net: all });
    ok("the board's own copy comes before the mirrors", r.boot.from == "board"
       && r.asked.join() == "/sync," + boardUrl(good), r.asked.join());
    r = await load({ sync: syncOf(good, 0), net: all });
    ok("a board that keeps no copy is not asked for one", r.boot.from == DEV
       && !r.asked.includes(boardUrl(good)), r.asked.join());
    r = await load({ sync: syncOf(good), net: { [DEV + good.page + ".pack"]: 404,
                                                [SITE + good.page + ".pack"]: good.data } });
    ok("a mirror that fails hands on to the next", r.boot.from == SITE, r.asked.join());
}

// A wrong digest is refused, whoever serves it.
{
    let r = await load({ sync: syncOf(good, 1), net: { [boardUrl(good)]: other.data,
                                                       [DEV + good.page + ".pack"]: other.data,
                                                       [SITE + good.page + ".pack"]: good.data } });
    ok("bytes of another digest are passed over", r.boot.from == SITE && r.written == PAGE);
    ok("...and never kept", r.idb.rows.size == 2 && !r.idb.rows.has(other.pack));
    r = await load({ sync: syncOf(good), net: { [DEV + good.page + ".pack"]: other.data,
                                                [SITE + good.page + ".pack"]: other.data } });
    ok("no source with the digest boots nothing", r.written === null && r.assets === undefined);
    ok("...and says why", /could not be loaded/.test(r.said) && /other bytes/.test(r.said), r.said);
    const t = good.data.slice();
    t[t.length - 1] ^= 1;                // the wasm's last byte, under an intact head
    r = await load({ sync: syncOf(good), net: { [SITE + good.page + ".pack"]: t }, mirrors: [SITE] });
    ok("a body changed under its head is refused", r.written === null, r.said);
}

// A tampered head is refused: one byte of an entry, and a head that hashes
// to what /sync names but carries another body digest.
{
    const t = good.data.slice();
    t[48 + 40] ^= 4;                     // the first entry's offset
    let r = await load({ sync: syncOf(good), net: { [SITE + good.page + ".pack"]: t }, mirrors: [SITE] });
    ok("a head with one byte changed is refused", r.written === null);
    const u = good.data.slice();
    u[16] ^= 1;                          // the head's body digest
    r = await load({ sync: { sync: 1, page: good.page, pack: sha(u), local: 0 },
                    net: { [SITE + good.page + ".pack"]: u }, mirrors: [SITE] });
    ok("a head naming another body is refused, whatever /sync says", r.written === null, r.said);
}

// A poisoned cache entry (another device at this address wrote it) is
// refused, deleted, and the pack fetched again.
{
    const idb = fakeIDB(new Map([[good.pack, buf(other.data)], ["order", [good.pack]]]));
    const r = await load({ sync: syncOf(good), net: { [SITE + good.page + ".pack"]: good.data }, idb });
    ok("a cache entry with other bytes is refused", r.boot.from == SITE && r.written == PAGE);
    ok("...and replaced by the pack fetched again",
       sha(new Uint8Array(idb.rows.get(good.pack))) == good.pack);
}

// Eviction (§3): the pack booted and the one booted before it stay.
{
    const a = makePack([["index.html", enc("a")]]), b = makePack([["index.html", enc("b")]]);
    const c = makePack([["index.html", enc("c")]]);
    const idb = fakeIDB(new Map([[a.pack, buf(a.data)], [b.pack, buf(b.data)], [c.pack, buf(c.data)],
                                 ["order", [b.pack, c.pack]]]));
    await load({ sync: syncOf(good), net: { [SITE + good.page + ".pack"]: good.data }, idb });
    ok("the booted pack and the one before it are kept",
       [...idb.rows.keys()].sort().join() == [good.pack, b.pack, "order"].sort().join(),
       [...idb.rows.keys()].join());
    ok("...in the order a rollback reads", idb.rows.get("order").join() == [good.pack, b.pack].join());
    await load({ sync: syncOf(b), net: {}, idb });
    ok("a rollback boots the pack before from the cache",
       idb.rows.get("order").join() == [b.pack, good.pack].join() && idb.rows.has(good.pack));
}

// A board that names no console, and one that does not answer.
{
    let r = await load({ sync: { sync: 1, page: null, pack: null, local: 0 } });
    ok("an image that names no console says so", r.written === null && /names no/.test(r.said));
    r = await load({ sync: null });
    ok("a board with no answer says so", r.written === null && /did not answer/.test(r.said), r.said);
}

if (fail) { console.log(fail + " failed"); process.exit(1); }
console.log("loader: all passed");
