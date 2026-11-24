// The service worker of os.moybyte.com (docs/web_console_online_2026-11.md §8):
// it keeps the site, so My consoles opens offline, and answers a pack from
// what this browser keeps before the network. tools/os_site.py stamps the
// build's version and the files it keeps; a new build is a new worker.
importScripts("packs.js");
const VERSION = "@VERSION@", SHELL = @SHELL@, APP = "moy-app-" + VERSION;

// The site whole, then the newest packs (packs.json): a pack that does not
// come now is fetched when a console names it.
self.addEventListener("install", (e) => e.waitUntil((async () => {
    const app = await caches.open(APP);
    await app.addAll(SHELL.map((u) => new Request(u, { cache: "reload" })));
    const newest = await (await app.match("packs.json")).json();
    for (const d of newest.newest || []) {
        try { await moyPacks.keep(d); } catch (err) { }
    }
    await self.skipWaiting();
})()));

self.addEventListener("activate", (e) => e.waitUntil((async () => {
    for (const k of await caches.keys()) {
        if (k.startsWith("moy-app-") && k != APP) await caches.delete(k);
    }
    await self.clients.claim();
})()));

self.addEventListener("fetch", (e) => {
    const u = new URL(e.request.url);
    if (e.request.method != "GET" || u.origin != location.origin) return;
    const pack = /\/console\/([0-9a-f]{64})\.pack$/.exec(u.pathname);
    e.respondWith((async () => {
        const kept = pack ? await (await caches.open(moyPacks.CACHE)).match(u.href)
                          : await (await caches.open(APP)).match(e.request, { ignoreSearch: true });
        if (kept) return kept;
        try {
            return await fetch(e.request);
        } catch (err) {
            if (e.request.mode == "navigate") return (await caches.open(APP)).match("./");
            throw err;
        }
    })());
});
