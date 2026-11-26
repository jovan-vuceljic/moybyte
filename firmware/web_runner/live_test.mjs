// The page's live socket as worker.js has it (THE LIVE SOCKET, THE
// REQUESTS), cut out of the source and run against a scripted socket: a
// request the socket lost is asked again on the next socket and answered
// there, never over HTTP, and the page says it reconnects while the socket
// is down and that it is live once it is back. The host here is an open one
// (no sign-in), so nothing is sealed; the seal's own end is the C's
// (tests/test_live_requests.py). Run from firmware/web_runner:
// node live_test.mjs
import { readFileSync } from "node:fs";

const SRC = readFileSync(new URL("./worker.js", import.meta.url), "utf-8");
function cut(from, to) {
    const a = SRC.indexOf(from), b = SRC.indexOf(to, a);
    if (a < 0 || b < a) { console.log("FAIL: worker.js has no " + from); process.exit(1); }
    return SRC.slice(a, b);
}
const SECTION = cut("// THE SIGN-IN (native/moy_net/moy_seal.h", "// A fatal error as {t:\"error\"}")
    + cut("// THE LIVE SOCKET (#256", "function liveFeedAll(");

// The sockets the page opened, the test playing the board's end of each.
const sockets = [];
class FakeSocket {
    constructor(url) {
        this.url = url;
        this.readyState = 0;
        this.sent = [];
        sockets.push(this);
    }
    send(b) { this.sent.push(new Uint8Array(b)); }
    close() { this.readyState = 3; }
    open() { this.readyState = 1; this.onopen(); }
    drop() { this.readyState = 3; this.onclose({ code: 1006, reason: "" }); }
    say(bytes) { this.onmessage({ data: new Uint8Array(bytes).buffer }); }
    // The last request it carried: [id, "METHOD TARGET\n..."].
    request() {
        const q = this.sent.filter((b) => b[0] === 0x72 && b[1] === 0x51).pop();
        return q ? [q[2] | (q[3] << 8), new TextDecoder().decode(q.subarray(8))] : null;
    }
    answer(id, status, body) {          // one 'W', the whole answer
        const t = new TextEncoder(), ct = t.encode("application/json");
        this.say([0x72, 0x57, id & 255, id >> 8, status & 255, status >> 8, ct.length,
                  ...ct, ...t.encode(body)]);
    }
}

function page() {
    const said = [];
    const make = new Function("mp", "fetch", "self", "store", "say", "WebSocket", "BASE",
        "let termLive = null; const TERM = {}; const termLiveLost = () => {};"
        + "const termLiveIn = () => {}, liveHinted = () => {};"
        + SECTION + `
        return { sealed, liveOpen, state: () => ({ liveWs, liveSealed, LIVE }),
                 set: (o) => { authOpen = o.authOpen; reqPiece = o.reqPiece; liveOn = o.liveOn; } };`);
    const fetch = async (u) => { said.push("HTTP " + u); return { status: 599 }; };
    const w = make({ _module: null }, fetch, { postMessage: () => {} }, {}, (s) => said.push(s),
                   FakeSocket, "http://board/");
    w.said = said;
    return w;
}

let fail = 0;
function ok(name, cond, extra = "") {
    if (cond) console.log("  ok   " + name);
    else { fail++; console.log("  FAIL " + name + (extra ? "  " + extra : "")); }
}
const tick = (ms) => new Promise((r) => setTimeout(r, ms));

{
    const w = page();
    w.set({ authOpen: true, reqPiece: 2024, liveOn: true });
    w.liveOpen();
    sockets[0].open();
    const asked = w.sealed("GET", "/carts.json");
    await tick(20);
    const [id] = sockets[0].request();
    ok("a request goes on the socket", id > 0);
    sockets[0].drop();                  // ...and the socket goes before its answer
    ok("the page says it reconnects", w.said.includes("the console's connection dropped -- reconnecting..."),
       JSON.stringify(w.said));
    await tick(400);                    // the retry's first wait
    ok("it opens the next socket itself", sockets.length === 2, sockets.length);
    sockets[1].open();
    ok("...and says it is live once that socket is up", w.said[w.said.length - 1] === "live",
       JSON.stringify(w.said));
    await tick(100);
    const again = sockets[1].request();
    ok("the lost request is asked again on it", again && again[1].startsWith("GET /carts.json\n"),
       JSON.stringify(again));
    sockets[1].answer(again[0], 200, '{"a.moy/main.py":"x"}');
    const r = await asked;
    ok("...and its answer is the request's", r.status === 200 && r.text === '{"a.moy/main.py":"x"}',
       JSON.stringify(r));
    ok("nothing went over HTTP", !w.said.some((s) => s.startsWith("HTTP")), JSON.stringify(w.said));
}

if (fail) { console.log(fail + " failed"); process.exit(1); }
console.log("all ok");
process.exit(0);
