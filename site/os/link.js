// The link's site end (docs/web_console_online_2026-11.md §5), shared by My
// consoles and the flasher's first setup: a console opened in a window on
// its own origin, the pack its board names handed from what this browser
// keeps (packs.js, where the page loads it), the window's `state` shown, and
// a board's first password sent over the link (`claim`, §7) once its console
// asks to sign in. Messages are taken only from a window this page opened,
// at the origin it opened it at; what one says is shown as text, never
// evaluated.
//
//   moyLink.init({show(c, sentence, cls, link), hello(c, hello)})
//   moyLink.open(c, secret)   `secret` {claim, password} for a board with none
self.moyLink = (() => {
    const wins = new Map();      // console id -> {w, origin, c, heard, secret}
    const asked = new Map();     // a request's id -> {id, kind, page}
    const REACH_MS = 8000;       // a window that names no pack by then was not reached
    let n = 0, show = () => { }, heard = () => { };

    function init(opts) {
        show = opts.show || show;
        heard = opts.hello || heard;
    }
    // The tap: a window on the console's origin, which its loader boots (§3).
    // One already open is brought forward, never loaded again: its tab may
    // hold work it has not synced.
    function open(c, secret) {
        const had = wins.get(c.id);
        if (had && !had.w.closed) {
            if (secret) had.secret = secret;
            had.w.focus();
            return true;
        }
        const url = moyKept.url(c);
        const w = window.open(url, "moy-" + c.id);
        if (!w) {
            show(c, "This window cannot open the console's. Open it in the browser:", "bad", url);
            return false;
        }
        const x = { w, origin: new URL(url).origin, c, heard: false, secret: secret || null };
        wins.set(c.id, x);
        show(c, "opening...");
        setTimeout(() => {
            if (!x.heard && wins.get(c.id) === x) {
                show(c, "not reached yet: is it on, and on this network? Open it by hand:", "bad", url);
            }
        }, REACH_MS);
        return true;
    }
    function send(x, kind, m, transfer) {
        const id = ++n;
        x.w.postMessage(Object.assign({ moylink: 1, id, kind }, m), x.origin, transfer || []);
        return id;
    }

    addEventListener("message", (e) => {
        const m = e.data;
        let x = null;
        for (const v of wins.values()) if (v.w === e.source && v.origin === e.origin) x = v;
        if (!x || !m || m.moylink !== 1) return;
        if (typeof m.re == "number") return answered(x, m);
        if (typeof m.id != "number") return;
        if (m.kind == "hello") hand(x, m);
        else if (m.kind == "state") state(x, m);
        else e.source.postMessage({ moylink: 1, re: m.id, kind: "unknown" }, e.origin);
    });

    // The board's hello names its pack: hand the window the bytes this browser
    // keeps, or none, and keep them for the next time.
    async function hand(x, hello) {
        const c = x.c, packs = self.moyPacks;
        if (typeof hello.page != "string" || !/^[0-9a-f]{64}$/.test(hello.page)) return;
        x.heard = true;
        heard(c, hello);
        let bytes = null;
        if (packs) { try { bytes = await packs.bytes(hello.page); } catch (err) { } }
        const id = send(x, "pack", { bytes }, bytes ? [bytes] : []);
        asked.set(id, { id: c.id, kind: "pack", page: hello.page });
        show(c, bytes ? "handing it its console..." : "it fetches its console itself");
        if (packs && !bytes) packs.keep(hello.page).catch(() => false);
    }
    function answered(x, m) {
        const a = asked.get(m.re), c = x.c;
        if (!a) return;
        asked.delete(m.re);
        if (a.kind == "pack") {
            if (m.ok) return show(c, "handed it its console");
            if (self.moyPacks) self.moyPacks.drop(a.page).catch(() => { });
            return show(c, "it refused the console this browser kept, so that copy is gone", "bad");
        }
        if (a.kind == "claim") {
            if (m.kind == "unknown") return show(c, "its console cannot take a password from here: type one in its window", "bad");
            const said = typeof m.said == "string" ? m.said.slice(0, 300) : "";
            show(c, m.ok ? "password set; pairing..." : "the password was not set: " + said, m.ok ? "" : "bad");
        }
    }
    function state(x, m) {
        const c = x.c, said = typeof m.said == "string" ? m.said.slice(0, 300) : "";
        if (m.state == "failed") show(c, said || "it stopped", "bad");
        else if (m.state == "signed-in") show(c, "signed in", "ok");
        else if (m.state == "sign-in" && x.secret) {
            const id = send(x, "claim", { claim: x.secret.claim, board: c.id, password: x.secret.password });
            asked.set(id, { id: c.id, kind: "claim" });
            x.secret = null;
            show(c, "setting its password...");
        } else if (m.state == "sign-in") show(c, "asks for its password" + (said ? ": " + said : ""));
        else if (m.state == "booted") show(c, "running");
    }
    function forget(c) { wins.delete(c.id); }
    return { init, open, forget };
})();
