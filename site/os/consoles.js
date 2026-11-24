// My consoles (docs/web_console_online_2026-11.md §2's flows 1 and 2, §5):
// the consoles this browser knows (kept.js), each opened in a window on its
// own origin over the link (link.js), which hands that window the pack its
// board names from what this browser keeps (packs.js). A board is added by
// its first setup over the cable (setup.js, Improv), or by hand by its
// address, which the first open verifies: the board's loader says hello
// over the link, and the list shows it reached and what it named. The site
// never runs a console and never reaches a board: the window it opens does
// (§10), and what that window sends is text shown as text, never evaluated.
"use strict";
let consoles = moyKept.read(), newest = null;
const shown = new Map();     // console id -> [sentence, class, link]

function write() {
    if (!moyKept.write(consoles)) say("This browser keeps nothing for this site: the list lasts this visit.");
}
function say(t, cls) {
    const s = document.getElementById("said");
    s.textContent = t;
    s.className = cls == "bad" ? "warnbox" : "notice";
    s.hidden = !t;
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
    document.getElementById("more").hidden = consoles.length == 0;
    for (const c of consoles) {
        const li = el("li"), open = el("button", "btn pri open", "Open");
        open.onclick = () => moyLink.open(c);
        const where = el("p", "where", moyKept.url(c));
        if (c.local) where.append(el("span", "local", c.local));
        const st = el("p", "state"), s = shown.get(c.id);
        if (s) {
            st.className = "state " + (s[1] || "");
            st.textContent = s[0];
            if (s[2]) { const a = el("a", "", s[2]); a.href = s[2]; a.target = "_blank"; st.append(" ", a); }
        }
        const rename = el("button", "btn quiet", "Rename"), forget = el("button", "btn quiet", "Forget");
        rename.onclick = () => renameConsole(c);
        forget.onclick = () => forgetConsole(c);
        const act = el("div", "act");
        act.append(open, rename, forget);
        if ("serial" in navigator) {
            const manage = el("button", "btn quiet manage", "Manage by cable");
            manage.onclick = () => byCable(c);
            act.append(manage);
        }
        li.append(el("h3", "name", c.name), where,
                  el("p", c.reached ? "reach ok" : "reach", c.reached
                      ? "reached " + new Date(c.reached).toLocaleString() + "  ·  console " + c.page.slice(0, 12)
                      : "not reached yet"),
                  st, act);
        list.append(li);
    }
}
function show(c, sentence, cls, link) {
    shown.set(c.id, [sentence, cls, link]);
    render();
}
function renameConsole(c) {
    const v = prompt("A new name for " + c.name, c.name);
    if (v && v.trim()) { c.name = v.trim().slice(0, 40); write(); render(); }
}
function forgetConsole(c) {
    if (!confirm("Forget " + c.name + "? Its carts stay on the console.")) return;
    consoles = consoles.filter((x) => x !== c);
    moyLink.forget(c);
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

// A board's hello verifies it: reached, and the digests it named.
moyLink.init({
    show,
    hello(c, hello) {
        c.page = hello.page;
        c.pack = typeof hello.pack == "string" && /^[0-9a-f]{64}$/.test(hello.pack) ? hello.pack : "";
        c.reached = Date.now();
        write();
        render();
        tidy();
    },
});

// By hand: an address, and a name or none (the address is the name then).
// A console at an address the list has is updated, never added twice.
document.getElementById("add").addEventListener("submit", (e) => {
    e.preventDefault();
    const a = moyKept.address(document.getElementById("address").value);
    if (!a) {
        say("That is not an address: type the one the console shows, like kitchen.local, "
            + "192.168.1.57 or http://192.168.1.57:8080. No path after it.", "bad");
        return;
    }
    const name = document.getElementById("name").value.trim().slice(0, 40) || a.address;
    const had = consoles.find((c) => c.address === a.address && !!c.secure === a.secure);
    const c = moyKept.put(consoles, had ? { id: had.id, name, address: a.address }
                                        : { id: crypto.randomUUID(), name, address: a.address });
    if (a.secure) c.secure = true; else delete c.secure;
    write();
    render();
    say(had ? "Updated " + c.name + ". Tap it to open it." : "Added " + c.name + ". Tap it to open it: the first open checks it is there.");
    e.target.reset();
    if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => { });
});

// By cable (setup.js): a board just plugged in is set up over Improv, and
// one already on a network is managed, as any card's "Manage by cable" does
// at any time: its Wi-Fi, its name, its password.
const cable = document.getElementById("cable");
let cabled = false;
async function byCable(card) {
    if (cabled) return;
    let port;
    try { port = await navigator.serial.requestPort(); }
    catch (err) {      // NotFoundError: the chooser was closed with no port
        if (err.name != "NotFoundError") say("No port: " + err.message, "bad");
        return;
    }
    say("");
    cabled = cable.disabled = true;
    const box = document.getElementById("setup");
    box.scrollIntoView({ block: "nearest" });
    const opts = {
        c: card,
        changed() { consoles = moyKept.read(); render(); },
        done(c, secret) {
            consoles = moyKept.read();
            render();
            const k = consoles.find((x) => x.id === c.id) || c;
            for (const b of box.querySelectorAll("button.opener")) b.remove();
            const go = el("button", "btn pri opener", "Open " + k.name);
            go.onclick = () => { moyLink.open(k, secret); go.remove(); };
            box.append(go);
            go.scrollIntoView({ block: "nearest", behavior: "instant" });
        },
    };
    try { await (card ? moySetup.manage(box, port, opts) : moySetup.run(box, port, opts)); }
    catch (err) { /* setup said why */ }
    cabled = cable.disabled = false;
}
if ("serial" in navigator) {
    cable.hidden = false;
    cable.onclick = () => byCable(null);
}

render();
fetch("packs.json").then((r) => r.json()).then((j) => {
    newest = Array.isArray(j.newest) ? j.newest.filter((d) => moyPacks.DIGEST.test(d)) : [];
    tidy();
}).catch(() => { });
if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch((err) => say("This site will not open offline: " + err.message));
}
