// The site's Improv client (improv.js) against a scripted port, and the
// list's addresses (kept.js): the frames it writes are Improv's (the spec's
// own example), a board that answers only after its boot is waited for, a
// frame split across reads and the REPL's lines around frames are read, a
// join answers the board's URLs with its id and claim, a refusal is the
// board's sentence; the board's log reaches a person as whole lines with
// the Wi-Fi password blanked. Run from site/os: node improv_test.mjs
import { createRequire } from "node:module";

globalThis.self = globalThis;
const require = createRequire(import.meta.url);
const imp = require("./improv.js");
const kept = require("./kept.js");

let fail = 0;
function ok(name, cond, extra = "") {
    if (cond) console.log("  ok   " + name);
    else { fail++; console.log("  FAIL " + name + (extra ? "  " + extra : "")); }
}
const hex = (b) => Buffer.from(b).toString("hex");
const enc = new TextEncoder();

// A board on a Web Serial port: `answer(cmd, data)` -> [[type, data]...]
// for each RPC it is written; `chunk` cuts what it sends into pieces.
function port(answer, { silentFor = 0, chunk = 0, noise = "" } = {}) {
    let queue = [], wake = null, closed = false, writes = 0;
    const push = (bytes) => {
        if (!chunk) queue.push(bytes);
        else for (let i = 0; i < bytes.length; i += chunk) queue.push(bytes.slice(i, i + chunk));
        if (wake) { wake(); wake = null; }
    };
    const p = {
        opened: null, signals: null, writes: [],
        readable: null, writable: null,
        async open(o) {
            p.opened = o;
            p.readable = { getReader: () => ({
                async read() {
                    while (!queue.length && !closed) await new Promise((r) => { wake = r; });
                    if (closed) return { done: true };
                    return { value: queue.shift(), done: false };
                },
                async cancel() { closed = true; if (wake) wake(); },
                releaseLock() { },
            }) };
            p.writable = { getWriter: () => ({
                async write(b) {
                    p.writes.push(hex(b));
                    if (++writes <= silentFor) return;
                    const n = b[8], data = Array.from(b.slice(9, 9 + n));
                    const out = [];
                    if (noise) out.push(...enc.encode(noise));
                    for (const [t, d] of answer(data[0], data.slice(2))) out.push(...imp.frame(t, d));
                    push(new Uint8Array(out));
                },
                releaseLock() { },
            }) };
        },
        async setSignals(s) { p.signals = s; },
        async close() { closed = true; },
    };
    return p;
}
const strs = (cmd, ...ss) => {
    const body = [];
    for (const s of ss) { const b = enc.encode(s); body.push(b.length, ...b); }
    return [cmd, body.length, ...body];
};
const ID = "ab".repeat(16), CLAIM = "cd".repeat(16);

ok("a frame is the spec's example, checksum and newline",
   hex(imp.rpc(1, [12, ...enc.encode("MyWirelessAP"), 16, ...enc.encode("mysecurepassword")]))
   .startsWith("494d50524f56" + "01" + "03" + "20" + "011e0c" + hex(enc.encode("MyWirelessAP")) + "10"));
{
    const f = imp.frame(3, [1, 30]);
    const sum = [...f.slice(0, -2)].reduce((s, x) => s + x, 0) & 0xff;
    ok("...its checksum is the low byte of the sum, then a newline", f[f.length - 2] === sum && f[f.length - 1] === 10);
}

const BOARD = (cmd, data) => {
    if (cmd === 2) return [[2, [0]], [1, [2]]];
    if (cmd === 3) return [[2, [0]], [4, strs(3, "Moybyte", "v0.16", "ESP32-C3", "moybyte-zero")]];
    if (cmd === 4) return [[2, [0]], [4, strs(4, "home", "-40", "YES")], [4, strs(4, "cafe", "-70", "NO")], [4, [4, 0]]];
    if (cmd === 6) return [[2, [0]], [4, strs(6, data.length ? new TextDecoder().decode(new Uint8Array(data.slice(1))) : "moybyte-zero")]];
    if (cmd === 1) {
        const ssid = new TextDecoder().decode(new Uint8Array(data.slice(1, 1 + data[0])));
        if (ssid !== "home") return [[2, [0]], [1, [3]], [2, [3]], [1, [2]]];
        return [[2, [0]], [1, [3]], [1, [4]], [4, strs(1, "http://192.168.1.57/#id=" + ID + "&claim=" + CLAIM,
                                                     "http://kitchen.local/#id=" + ID + "&claim=" + CLAIM)]];
    }
    if (cmd === 0xF0) return [[2, [0]], [4, strs(0xF0, "http://192.168.1.57/#id=" + ID + "&claim=" + "ef".repeat(16))]];
    return [[2, [2]]];
};

{
    const p = port(BOARD, { chunk: 3, noise: "ZERO serving\r\n" });
    const logged = [];
    const c = new imp.Client(p, { lines: { dtr: true, rts: true }, log: (t) => logged.push(t) });
    await c.open();
    ok("the port opens at 115200 with the board's resting lines", p.opened.baudRate === 115200
       && p.signals.dataTerminalReady === true && p.signals.requestToSend === true);
    const st = await c.state();
    ok("a frame cut into 3-byte reads is read whole", st.state === imp.READY, JSON.stringify(st));
    ok("...and the REPL's line around it reaches the log, not a frame", logged.join("").includes("ZERO serving"));
    const info = await c.info();
    ok("the device's strings", info.firmware === "Moybyte" && info.chip === "ESP32-C3" && info.name === "moybyte-zero");
    const nets = await c.scan();
    ok("the scan's networks, to its empty end", nets.length === 2 && nets[0].ssid === "home" && nets[0].locked
       && !nets[1].locked, JSON.stringify(nets));
    ok("a name set comes back as the board took it", (await c.name("kitchen")) === "kitchen");
    const urls = await c.wifi("home", "its password");
    const w = imp.found(urls);
    ok("a join answers the board by IP and .local, its id and its claim",
       w.address === "192.168.1.57" && w.local === "kitchen.local" && w.id === ID && w.claim === CLAIM,
       JSON.stringify(w));
    const fresh = imp.found(await c.claim());
    ok("the cable's claim is the board's address with a fresh one", fresh.id === ID
       && fresh.claim === "ef".repeat(16) && fresh.address === "192.168.1.57", JSON.stringify(fresh));
    let e = null;
    try { await c.wifi("elsewhere", "nope"); } catch (err) { e = err; }
    ok("a network it cannot join is the board's sentence", e && e.code === 3 && /could not join/.test(e.message));
    e = null;
    try { await c.ask(0x42, [], () => false, 1000); } catch (err) { e = err; }
    ok("an unknown command is refused, not waited on", e && e.code === 2);
    await c.close();
}
{
    const p = port(BOARD, { silentFor: 3 });
    const c = new imp.Client(p);
    await c.open();
    const t0 = Date.now();
    const st = await c.ready(10000);
    ok("a board still booting is asked again until it answers", st.state === imp.READY && p.writes.length === 4,
       p.writes.length + " writes in " + (Date.now() - t0) + " ms");
    await c.close();
}
{
    const got = [];
    const L = new imp.Lines((l) => got.push(l), 3);
    L.feed("I (12) boot: ESP-IDF v5\r\nI (13) wi");
    ok("the log is lines: a partial one is held until its end, CRs dropped",
       got.length === 1 && got[0] === "I (12) boot: ESP-IDF v5", JSON.stringify(got));
    L.feed("fi: start\n\x1b[0;33mW (40) wifi: reason 2\x1b[0m\n");
    ok("...and ANSI colours are stripped", got[1] === "I (13) wifi: start" && got[2] === "W (40) wifi: reason 2",
       JSON.stringify(got));
    L.feed("a\nb\n");
    ok("only the last `keep` are kept", L.text() === "W (40) wifi: reason 2\na\nb", JSON.stringify(L.text()));
    L.feed("no end");
    L.flush();
    ok("a flush gives the held line", got[got.length - 1] === "no end" && L.part === "");
}
{
    const got = [];
    const L = new imp.Lines((l) => got.push(l));
    L.hide("");
    L.feed("open network\n");
    ok("an empty password hides nothing", got[0] === "open network");
    L.feed("join home pw=hunter2-before-hide\n");
    L.hide("hunter2-before-hide");
    L.hide("s3cret pass");
    L.feed("join home pw=s3cr");
    L.feed("et pass, again s3cret pass\n");
    L.feed("\x1b[1ms3cret\x1b[0m pass\n");
    ok("the password is blanked, cut across reads or wrapped in escapes",
       got[2] === "join home pw=********, again ********" && got[3] === "********", JSON.stringify(got));
    ok("...and a line logged before it was known is blanked when copied",
       !L.text().includes("hunter2") && !L.text().includes("s3cret"), L.text());
    L.feed("x".repeat(5000) + "s3cret pass" + "y".repeat(10));
    ok("a line with no end goes out in pieces with the password still whole",
       !got.join("").includes("s3cret") && (L.part + got.join("")).length > 5000, L.part.slice(-30));
}
{
    const got = [];
    const L = new imp.Lines((l) => got.push(l));
    const p = port(BOARD, { chunk: 4, noise: "W (5) wifi:caf\u00e9 reason 2\r\n" });
    const c = new imp.Client(p, { log: (t) => L.feed(t) });
    await c.open();
    await c.state();
    await c.info();
    await c.close();
    ok("the board's lines between frames reach Lines whole, a character cut between reads too",
       got.length === 2 && got.every((l) => l === "W (5) wifi:caf\u00e9 reason 2"), JSON.stringify(got));
}
ok("a URL with a password set carries no claim", (() => {
    const w = imp.found(["http://10.0.0.9/#id=" + ID]);
    return w.address === "10.0.0.9" && w.claim === "" && w.id === ID;
})());
ok("no http URL is no console", imp.found(["javascript:alert(1)", "ftp://x/"]) === null);

// kept.js: what a person types as an address.
const A = (t) => JSON.stringify(kept.address(t));
ok("an IP", A(" 192.168.1.57 ") === '{"address":"192.168.1.57","secure":false}');
ok("a .local name, upper case and a trailing slash", A("Kitchen.LOCAL/") === '{"address":"kitchen.local","secure":false}');
ok("with http:// and a port", A("http://192.168.1.57:8080") === '{"address":"192.168.1.57:8080","secure":false}');
ok("https stays https", A("https://board.example") === '{"address":"board.example","secure":true}');
ok("an IPv6 address", A("http://[fe80::1]:81/") === '{"address":"[fe80::1]:81","secure":false}');
for (const bad of ["", "ftp://192.168.1.5", "http://192.168.1.5/console", "kitchen.local/x",
                   "http://a/?q=1", "javascript:alert(1)", "http://user@host/", "a b"]) {
    ok("refused: " + JSON.stringify(bad), kept.address(bad) === null, A(bad));
}
{
    const list = [{ id: "u1", name: "by hand", address: "192.168.1.57" }];
    kept.put(list, { id: ID, name: "kitchen", address: "192.168.1.57", local: "kitchen.local" });
    ok("a board set up at an address the list has takes that entry, under its own id",
       list.length === 1 && list[0].id === ID && list[0].name === "kitchen");
    kept.put(list, { id: ID, name: "kitchen", address: "192.168.1.80", local: "kitchen.local" });
    ok("...and its new address after another setup", list.length === 1 && list[0].address === "192.168.1.80");
}

if (fail) { console.log(fail + " failed"); process.exit(1); }
console.log("all ok");
