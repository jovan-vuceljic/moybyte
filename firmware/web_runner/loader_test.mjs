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

// The window that opened the loader's, at `origin`: a message the loader
// posts reaches it only when its target is that origin, as a browser
// delivers one, and `answer(m, send)` replies through `send(data, from)`,
// `from` the origin and source the loader sees (this window's by default).
// A pack's bytes arrive as an ArrayBuffer of the loader's realm, as a
// browser's structured clone delivers them.
function opener(origin, answer = () => { }) {
    const w = { got: [], dropped: [], listeners: [] };
    w.send = (data, from = {}) => setTimeout(() => {
        if (data.bytes) data = Object.assign({}, data, { bytes: w.clone(new Uint8Array(data.bytes)) });
        w.listeners.forEach((f) => f({ data, origin: from.origin || origin, source: from.source || w.win }));
    }, 0);
    w.win = {
        postMessage(m, target) {
            if (target != origin) { w.dropped.push(target); return; }
            w.got.push(m);
            answer(m, w.send);
        },
    };
    return w;
}

// One page load: `sync` is the board's /sync, `net` {url: bytes or status},
// `idb` the origin's store, `site` the opener (opener()), `ua` the browser's
// user agent, `store` its localStorage as a Map ("throw": one that throws),
// `search` the address's query, `pick` the fast console card's answer
// [button, remember]. Returns what the loader did.
async function load({ sync, net = {}, idb = fakeIDB(), mirrors = [DEV, SITE], site = null,
                      ua = "node", store = new Map(), search = "", pick = null }) {
    const asked = [], status = { textContent: "", card: null,
        set innerHTML(h) {
            this.card = h.replace(/<style>.*<\/style>/, "").replace(/<[^>]*>/g, "");
            const box = this.box = { checked: false };
            this.btns = [...h.matchAll(/<button>([^<]*)/g)].map((m) => ({ textContent: m[1] }));
            if (!pick) throw new Error("the card asked and the test picks nothing");
            setTimeout(() => { box.checked = pick[1]; this.btns.find((b) => b.textContent == pick[0]).onclick(); }, 0);
        },
        querySelectorAll() { return this.btns; },
        querySelector() { return this.box; },
    };
    const no = () => { throw new Error("SecurityError"); };
    const localStorage = store == "throw" ? { getItem: no, setItem: no, removeItem: no } : {
        getItem: (k) => store.has(k) ? store.get(k) : null,
        setItem: (k, v) => store.set(k, String(v)),
        removeItem: (k) => store.delete(k),
    };
    let written = null;
    const fetch = async (url) => {
        url = String(url);
        if (url.startsWith("blob:")) return new Response(resolveObjectURL(url));
        asked.push(url);
        if (url == "/sync") return new Response(JSON.stringify(sync));
        if (url == "/tls") return new Response(JSON.stringify({ tls: 2, port: 443 }));
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
        DecompressionStream, Response, Blob, TextDecoder, URL, setTimeout,
        location: { href: "http://192.168.1.57/" + search, protocol: "http:", hostname: "192.168.1.57", search },
        navigator: { userAgent: ua, platform: "", maxTouchPoints: 0 }, localStorage,
        addEventListener: (t, f) => { if (t == "message" && site) site.listeners.push(f); } });
    ctx.self = ctx.window = ctx;
    ctx.opener = site ? site.win : null;
    if (site) site.clone = vm.runInContext("(u) => new Uint8Array(u).buffer", ctx);
    await vm.runInContext(SCRIPT.replace("@MIRRORS@", JSON.stringify(mirrors)), ctx);
    return { asked, written, said: status.textContent, assets: ctx.moyAssets, boot: ctx.moyBoot, idb,
             link: ctx.moyLink, card: status.card, went: ctx.location.href, fast: ctx.moyFast };
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

// The link (§5): My consoles opened this window and hands it the pack.
const SITE_ORIGIN = "https://os.example";
const handing = (bytes) => (m, send) => {
    if (m.kind == "hello") send({ moylink: 1, id: 7, kind: "pack", bytes });
};
{
    const site = opener(SITE_ORIGIN, handing(buf(good.data)));
    const r = await load({ sync: syncOf(good, 1), site });
    const hello = site.got.find((m) => m.kind == "hello");
    ok("the hello reaches the site, and names the digests and the kinds",
       hello && hello.moylink == 1 && hello.page == good.page && hello.pack == good.pack
       && hello.kinds.join() == "hello,pack,state", JSON.stringify(hello));
    ok("...posted to no other origin's window", site.dropped.join() == "http://192.168.1.9:8321",
       site.dropped.join());
    ok("the site's pack boots the console, and nothing is fetched",
       r.written == PAGE && r.boot.from == "link" && r.asked.join() == "/sync", r.asked.join());
    ok("...its bytes are answered as taken", site.got.some((m) => m.re == 7 && m.kind == "pack" && m.ok));
    ok("...and kept under their digest", r.idb.rows.has(good.pack));
    ok("the console page holds the link to the sites the build names",
       r.link && r.link.join() == ["http://192.168.1.9:8321", SITE_ORIGIN].join());
}
{
    const site = opener(SITE_ORIGIN, handing(buf(other.data)));
    const r = await load({ sync: syncOf(good), net: { [SITE + good.page + ".pack"]: good.data }, site });
    ok("bytes of another digest from the site are refused, and it is told",
       site.got.some((m) => m.re == 7 && m.kind == "pack" && m.ok === false), JSON.stringify(site.got));
    ok("...and the next source boots the console", r.boot.from == SITE && r.written == PAGE);
}
{
    const site = opener(SITE_ORIGIN, handing(null));
    const t = Date.now();
    const r = await load({ sync: syncOf(good), net: { [SITE + good.page + ".pack"]: good.data }, site });
    ok("a site that keeps no pack hands on at once", r.boot.from == SITE && Date.now() - t < 2000);
}
{
    const site = opener(SITE_ORIGIN, (m, send) => {
        if (m.kind != "hello") return;
        send({ moylink: 1, id: 3, kind: "backup" });
        send({ moylink: 1, id: 4, kind: "pack", bytes: buf(good.data) });
        send({ moylink: 1, id: 5, kind: "pack", bytes: buf(good.data) });
    });
    await load({ sync: syncOf(good), site });
    ok("an unknown kind is answered as unknown", site.got.some((m) => m.re == 3 && m.kind == "unknown"));
    ok("a second pack is refused", site.got.some((m) => m.re == 5 && m.kind == "pack" && m.ok === false));
}
{
    // Another origin's window opened this one: it hears nothing, and what it
    // sends, a good pack among it, is neither taken nor answered.
    const evil = opener("https://evil.example");
    const site = opener(SITE_ORIGIN);
    const t0 = Date.now();
    setTimeout(() => evil.send({ moylink: 1, id: 1, kind: "pack", bytes: buf(good.data) }), 50);
    let r = await load({ sync: syncOf(good), net: { [SITE + good.page + ".pack"]: good.data }, site: evil });
    ok("another origin's window hears no hello", evil.got.length == 0 && evil.dropped.length == 2);
    evil.send({ moylink: 1, id: 2, kind: "backup" });
    await new Promise((f) => setTimeout(f, 10));
    ok("...its messages are not answered, and the console boots from a mirror",
       evil.got.length == 0 && r.boot.from == SITE, r.boot && r.boot.from);
    ok("...after the link's wait", Date.now() - t0 >= 3900);
    // The site's origin from a window that is not the opener is ignored too.
    r = await load({ sync: syncOf(good), net: { [SITE + good.page + ".pack"]: good.data },
                    site: opener(SITE_ORIGIN, (m, send) => {
                        if (m.kind == "hello") send({ moylink: 1, id: 1, kind: "pack", bytes: buf(good.data) },
                                                    { source: site.win });
                    }) });
    ok("a message from a window other than the opener is ignored", r.boot.from == SITE);
}
{
    const site = opener(SITE_ORIGIN);
    await load({ sync: null, site });
    ok("a board with no answer tells the site it failed",
       site.got.some((m) => m.kind == "state" && m.state == "failed" && /did not answer/.test(m.said)));
}

// A board that names no console, and one that does not answer.
{
    let r = await load({ sync: { sync: 1, page: null, pack: null, local: 0 } });
    ok("an image that names no console says so", r.written === null && /names no/.test(r.said));
    r = await load({ sync: null });
    ok("a board with no answer says so", r.written === null && /did not answer/.test(r.said), r.said);
}

// The fast console (HTTPS on demand): an iPhone is asked once; a remembered
// answer is gone to at once; ?fast forgets it and asks any browser again.
{
    const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)";
    const sync = Object.assign(syncOf(good), { tls: 1 }), net = { [SITE + good.page + ".pack"]: good.data };
    const HTTPS = "https://192.168.1.57/";
    let store = new Map();
    let r = await load({ sync, net, ua: IPHONE, store, pick: ["Make it fast", false] });
    ok("an iPhone is asked in the owner's words", /^Make it faster on iPhone\?/.test(r.card || "")
       && /tap Show Details, then visit this website\. You only do this once\./.test(r.card)
       && /Remember my choice/.test(r.card), r.card);
    ok("Make it fast opens the door and goes to the https origin",
       r.asked.includes("/tls") && r.went == HTTPS && r.written === null, r.went);
    ok("an answer not asked to be remembered is not kept", store.size == 0);
    r = await load({ sync, net, ua: IPHONE, store, pick: ["Not now", true] });
    ok("Not now boots the console here", r.written == PAGE && !r.asked.includes("/tls"));
    ok("Remember my choice keeps the answer", store.get("moy.fast") == "0");
    r = await load({ sync, net, ua: IPHONE, store });
    ok("a remembered Not now skips the card", r.card === null && r.written == PAGE);
    store.set("moy.fast", "1");
    r = await load({ sync, net, ua: IPHONE, store });
    ok("a remembered Make it fast goes at once", r.card === null && r.went == HTTPS);
    r = await load({ sync, net, store, search: "?fast", pick: ["Not now", false] });
    ok("?fast forgets the choice and asks any browser", r.card !== null && r.written == PAGE && store.size == 0);
    r = await load({ sync, net });
    ok("a browser not asked boots here and tells the page the board has the door",
       r.card === null && r.written == PAGE && r.fast == 1);
    r = await load({ sync, net, ua: IPHONE, store: "throw", pick: ["Make it fast", true] });
    ok("a browser that keeps nothing is still asked and goes", r.went == HTTPS);
    r = await load({ sync: syncOf(good), net, ua: IPHONE });
    ok("a board without the door asks nothing", r.card === null && r.written == PAGE && r.fast == 0);
}

if (fail) { console.log(fail + " failed"); process.exit(1); }
console.log("loader: all passed");
