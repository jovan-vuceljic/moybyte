// The packs this browser keeps for its consoles (docs/web_console_online_2026-11.md
// §8), shared by the page and its service worker: one cache, each pack under
// the address the site serves it at, `<body digest>.pack` beside the page
// (os.moybyte.com/console/, the mirror the images name), and put
// there only when its body hashes to that digest. The loader on the board's
// origin checks the whole file again before it runs a byte.
self.moyPacks = (() => {
    const CACHE = "moy-packs", HEAD = 4096, DIGEST = /^[0-9a-f]{64}$/;
    const url = (d) => new URL(d + ".pack", self.registration
        ? self.registration.scope : document.baseURI).href;
    const hex = (b) => Array.from(new Uint8Array(b), (x) => x.toString(16).padStart(2, "0")).join("");
    // The body digest of `bytes`, or null where they are no pack.
    async function digest(bytes) {
        return bytes.byteLength > HEAD ? hex(await crypto.subtle.digest("SHA-256", bytes.slice(HEAD))) : null;
    }
    // Fetch the pack `d` from the site and keep it: true once it is kept.
    async function keep(d) {
        if (!DIGEST.test(d)) return false;
        const cache = await caches.open(CACHE);
        if (await cache.match(url(d))) return true;
        const r = await fetch(url(d));
        if (!r.ok) return false;
        const bytes = await r.arrayBuffer();
        if (await digest(bytes) !== d) return false;
        await cache.put(url(d), new Response(bytes, { headers: { "Content-Type": "application/octet-stream" } }));
        return true;
    }
    // The bytes of the pack `d` this browser keeps, or null.
    async function bytes(d) {
        if (!DIGEST.test(d)) return null;
        const r = await (await caches.open(CACHE)).match(url(d));
        return r ? r.arrayBuffer() : null;
    }
    async function drop(d) {
        await (await caches.open(CACHE)).delete(url(d));
    }
    // Keep only the packs whose digests `wanted` holds.
    async function prune(wanted) {
        const cache = await caches.open(CACHE);
        for (const q of await cache.keys()) {
            const m = /([0-9a-f]{64})\.pack$/.exec(q.url);
            if (!m || !wanted.has(m[1])) await cache.delete(q);
        }
    }
    return { CACHE, DIGEST, url, keep, bytes, drop, prune };
})();
