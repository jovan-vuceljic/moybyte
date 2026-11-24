// My consoles (docs/web_console_online_2026-11.md §2's flow 2, §5): the
// consoles this browser knows, by name and address, each opened in a window
// on its own origin, and the link's site end, which hands that window the
// pack its board names from what this browser keeps (packs.js). The site
// never runs a console and never reaches a board: the window it opens does
// (§10), and what that window sends is text shown as text, never evaluated.
"use strict";
const KEY = "moy.consoles";
const ADDRESS = /^(\[[0-9a-f:.]+\]|[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*)(:\d{1,5})?$/i;
let consoles = read(), newest = null, n = 0;
const wins = new Map();      // console id -> {w, origin}: the windows this page opened
const asked = new Map();     // a pack request's id -> {id, page}
const shown = new Map();     // console id -> [sentence, class, link]

function read() {
    try {
        const v = JSON.parse(localStorage.getItem(KEY) || "[]");
        return Array.isArray(v) ? v.filter((c) => c && typeof c.id == "string"
            && typeof c.name == "string" && ADDRESS.test(c.address || "")) : [];
    } catch (e) { return []; }
}
function write() {
    try { localStorage.setItem(KEY, JSON.stringify(consoles)); }
    catch (e) { say("This browser keeps nothing for this site: the list lasts this visit."); }
}
function say(t) { document.getElementById("said").textContent = t; }
// What a person typed as an address, as host[:port], or null.
function address(text) {
    const a = text.trim().replace(/^https?:\/\//i, "").replace(/\/.*$/, "");
    return ADDRESS.test(a) ? a.toLowerCase() : null;
}
function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
}

function render() {
    const list = document.getElementById("list");
    list.textContent = "";
    document.getElementById("empty").hidden = consoles.length > 0;
    for (const c of consoles) {
        const li = el("li"), open = el("button", "name", c.name);
        open.onclick = () => openConsole(c);
        const st = el("div", "state"), s = shown.get(c.id);
        if (s) {
            st.className = "state " + (s[1] || "");
            st.textContent = s[0];
            if (s[2]) { const a = el("a", "", s[2]); a.href = s[2]; a.target = "_blank"; st.append(" ", a); }
        }
        const rename = el("button", "quiet", "Rename"), forget = el("button", "quiet", "Forget");
        rename.onclick = () => renameConsole(c);
        forget.onclick = () => forgetConsole(c);
        li.append(open, el("div", "addr", "http://" + c.address + "/"), st, rename, " ", forget);
        list.append(li);
    }
}
function show(c, sentence, cls, link) {
    shown.set(c.id, [sentence, cls, link]);
    render();
}

// The tap: a window on the console's origin, which its loader boots (§3).
// One already open is brought forward, never loaded again: its tab may
// hold work it has not synced.
function openConsole(c) {
    const had = wins.get(c.id);
    if (had && !had.w.closed) { had.w.focus(); return; }
    const url = "http://" + c.address + "/";
    const w = window.open(url, "moy-" + c.id);
    if (!w) {
        show(c, "This window cannot open the console's. Open it in the browser:", "bad", url);
        return;
    }
    wins.set(c.id, { w, origin: new URL(url).origin });
    show(c, "opening...");
}
function renameConsole(c) {
    const v = prompt("A new name for " + c.name, c.name);
    if (v && v.trim()) { c.name = v.trim().slice(0, 40); write(); render(); }
}
function forgetConsole(c) {
    if (!confirm("Forget " + c.name + "? Its carts stay on the console.")) return;
    consoles = consoles.filter((x) => x !== c);
    wins.delete(c.id);
    shown.delete(c.id);
    write();
    render();
    tidy();
}

// The packs this browser keeps: each saved console's last, and the newest
// a release names (packs.json), once that is known.
function tidy() {
    if (!newest) return;
    const want = new Set(newest);
    for (const c of consoles) if (c.page) want.add(c.page);
    moyPacks.prune(want).catch(() => { });
}

// ---- the link (§5): messages from the windows this page opened, and only
// from the origin each was opened at.
addEventListener("message", (e) => {
    const m = e.data;
    let c = null;
    for (const [id, x] of wins) {
        if (x.w === e.source && x.origin === e.origin) c = consoles.find((k) => k.id === id);
    }
    if (!c || !m || m.moylink !== 1) return;
    if (typeof m.re == "number") return answered(c, m);
    if (typeof m.id != "number") return;
    if (m.kind == "hello") hand(c, e.source, e.origin, m);
    else if (m.kind == "state") state(c, m);
    else e.source.postMessage({ moylink: 1, re: m.id, kind: "unknown" }, e.origin);
});

// The board's hello names its pack: hand the window the bytes this browser
// keeps, or none, and keep them for the next time.
async function hand(c, w, origin, hello) {
    if (!moyPacks.DIGEST.test(hello.page)) return;
    if (c.page !== hello.page) { c.page = hello.page; write(); }
    let bytes = null;
    try { bytes = await moyPacks.bytes(hello.page); } catch (err) { }
    const id = ++n;
    asked.set(id, { id: c.id, page: hello.page });
    w.postMessage({ moylink: 1, id, kind: "pack", bytes }, origin, bytes ? [bytes] : []);
    show(c, bytes ? "handing it its console..." : "it fetches its console itself");
    if (bytes) tidy();
    else moyPacks.keep(hello.page).catch(() => false).then(tidy);
}
function answered(c, m) {
    const a = asked.get(m.re);
    if (m.kind != "pack" || !a) return;
    asked.delete(m.re);
    if (m.ok) return show(c, "handed it its console");
    moyPacks.drop(a.page).catch(() => { });
    show(c, "it refused the console this browser kept, so that copy is gone", "bad");
}
function state(c, m) {
    const said = typeof m.said == "string" ? m.said.slice(0, 300) : "";
    if (m.state == "failed") show(c, said || "it stopped", "bad");
    else if (m.state == "signed-in") show(c, "signed in", "ok");
    else if (m.state == "sign-in") show(c, "asks for its password" + (said ? ": " + said : ""));
    else if (m.state == "booted") show(c, "running");
}

document.getElementById("add").addEventListener("submit", (e) => {
    e.preventDefault();
    const name = document.getElementById("name").value.trim().slice(0, 40);
    const a = address(document.getElementById("address").value);
    if (!name || !a) { say("That is not an address: type the one the console shows, like kitchen.local or 192.168.1.57."); return; }
    const had = consoles.find((c) => c.address === a);
    if (had) { say("That console is here already, as " + had.name + "."); return; }
    consoles.push({ id: crypto.randomUUID(), name, address: a });
    write();
    render();
    say("");
    e.target.reset();
    if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => { });
});

render();
fetch("packs.json").then((r) => r.json()).then((j) => {
    newest = Array.isArray(j.newest) ? j.newest.filter((d) => moyPacks.DIGEST.test(d)) : [];
    tidy();
}).catch(() => { });
if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch((err) => say("This site will not open offline: " + err.message));
}
