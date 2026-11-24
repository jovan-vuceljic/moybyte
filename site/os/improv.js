// Improv Wi-Fi over Web Serial (improv-wifi.com/serial): the site's one
// client, which My consoles and the flasher both drive through setup.js
// (docs/web_console_online_2026-11.md §7). A Zero answers it from the
// kernel's frame parser (native/moy_kernel/moy_improv.h) and its store host
// (device/zero_improv.py). What the board sends is read as frames and
// strings, never evaluated.
self.moyImprov = (() => {
    const HEADER = [73, 77, 80, 82, 79, 86], VERSION = 1;
    const STATE = 1, ERROR = 2, RPC = 3, RESULT = 4;
    const WIFI = 1, CURRENT = 2, INFO = 3, SCAN = 4, NAME = 6;
    // Moybyte's own (device/zero_improv.py): the address with a fresh claim,
    // which sets a new password even on a board that has one.
    const CLAIM = 0xF0;
    const READY = 2, PROVISIONED = 4;
    const SAYS = {
        1: "the board did not understand the request",
        2: "the board does not know that request",
        3: "the board could not join that network: check its name and password, and if they are right, move the board closer to the router",
        5: "that is not a name a network can carry",
        255: "the board failed",
    };
    const enc = new TextEncoder(), dec = new TextDecoder();

    function frame(type, data) {
        const b = [...HEADER, VERSION, type, data.length, ...data];
        b.push(b.reduce((s, x) => s + x, 0) & 0xff, 10);
        return new Uint8Array(b);
    }
    function field(s) {
        const b = enc.encode(s);
        if (b.length > 255) throw new Error("too long: " + s.slice(0, 20));
        return [b.length, ...b];
    }
    function rpc(cmd, data = []) {
        return frame(RPC, [cmd, data.length, ...data]);
    }
    // An RPC result's strings.
    function strings(d) {
        const out = [];
        for (let at = 2; at < d.length;) {
            const n = d[at];
            out.push(dec.decode(new Uint8Array(d.slice(at + 1, at + 1 + n))));
            at += 1 + n;
        }
        return out;
    }
    // What a board's URLs say: {address, local, id, claim} (claim "" once the
    // board has a password), or null for a URL no console answers at.
    function found(urls) {
        const out = { address: "", local: "", id: "", claim: "" };
        for (const u of urls || []) {
            let p;
            try { p = new URL(u); } catch (e) { continue; }
            if (p.protocol != "http:") continue;
            const h = new URLSearchParams(p.hash.replace(/^#/, ""));
            if (/^[0-9a-f]{32}$/.test(h.get("id") || "")) out.id = h.get("id");
            if (/^[0-9a-f]{32}$/.test(h.get("claim") || "")) out.claim = h.get("claim");
            if (p.hostname.endsWith(".local")) out.local = out.local || p.host;
            else out.address = out.address || p.host;
        }
        if (!out.address) out.address = out.local;
        return out.address ? out : null;
    }

    class Client {
        // `port` a Web Serial port; `lines` the board's resting line state
        // ({dtr, rts}, board.toml's [serial]: both high on a Zero).
        constructor(port, opts = {}) {
            this.port = port;
            this.lines = opts.lines || { dtr: true, rts: true };
            this.log = opts.log || (() => { });
            this.text = new TextDecoder();
            this.buf = [];
            this.frames = [];
            this.wake = null;
            this.reader = null;
        }
        async open() {
            if (!this.port.readable) await this.port.open({ baudRate: 115200 });
            try {
                await this.port.setSignals({ dataTerminalReady: !!this.lines.dtr,
                                             requestToSend: !!this.lines.rts });
            } catch (e) { /* a port with no lines */ }
            this.reader = this.port.readable.getReader();
            this.writer = this.port.writable.getWriter();
            this.pump();
        }
        async close() {
            try { if (this.reader) await this.reader.cancel(); } catch (e) { }
            try { if (this.reader) this.reader.releaseLock(); } catch (e) { }
            try { if (this.writer) this.writer.releaseLock(); } catch (e) { }
            try { await this.port.close(); } catch (e) { }
            this.reader = this.writer = null;
        }
        async pump() {
            try {
                for (;;) {
                    const { value, done } = await this.reader.read();
                    if (done) break;
                    for (const b of value) this.buf.push(b);
                    this.parse();
                }
            } catch (e) { this.log("the port closed: " + e.message); }
        }
        // The board's own bytes between frames, to `log` as text (a character
        // cut between reads is held for the next).
        said(bytes) {
            this.log(this.text.decode(new Uint8Array(bytes), { stream: true }));
        }
        parse() {
            for (;;) {
                let at = -1;
                for (let i = 0; i + 6 <= this.buf.length; i++) {
                    if (HEADER.every((h, k) => this.buf[i + k] === h)) { at = i; break; }
                }
                if (at < 0) {
                    const keep = Math.min(this.buf.length, 5);
                    if (this.buf.length > keep) this.said(this.buf.slice(0, -keep));
                    this.buf = this.buf.slice(-keep);
                    return;
                }
                if (at > 0) this.said(this.buf.slice(0, at));
                this.buf = this.buf.slice(at);
                if (this.buf.length < 9) return;
                const n = this.buf[8];
                if (this.buf.length < 10 + n) return;
                const sum = this.buf.slice(0, 9 + n).reduce((s, x) => s + x, 0) & 0xff;
                if (this.buf[6] === VERSION && this.buf[9 + n] === sum) {
                    this.frames.push({ type: this.buf[7], data: this.buf.slice(9, 9 + n) });
                }
                this.buf = this.buf.slice(10 + n);
                if (this.wake) this.wake();
            }
        }
        // Send `cmd` and collect frames until `done(frames)`; an error state
        // other than none rejects with the board's sentence.
        async ask(cmd, data, done, ms) {
            this.frames = [];
            await this.writer.write(rpc(cmd, data));
            const until = Date.now() + ms;
            const got = [];
            for (;;) {
                while (this.frames.length) {
                    const f = this.frames.shift();
                    if (f.type === ERROR && f.data[0] !== 0) {
                        const e = new Error(SAYS[f.data[0]] || "the board refused it");
                        e.code = f.data[0];
                        throw e;
                    }
                    got.push(f);
                    if (done(got)) return got;
                }
                const left = until - Date.now();
                if (left <= 0) {
                    const e = new Error("the board did not answer");
                    e.code = 0;
                    throw e;
                }
                await new Promise((r) => { this.wake = r; setTimeout(r, Math.min(left, 100)); });
                this.wake = null;
            }
        }
        // {state: READY | PROVISIONING | PROVISIONED, urls}.
        async state(ms = 1500) {
            const got = await this.ask(CURRENT, [], (g) => g.some((f) => f.type === STATE)
                && (g.find((f) => f.type === STATE).data[0] !== PROVISIONED
                    || g.some((f) => f.type === RESULT)), ms);
            const st = got.find((f) => f.type === STATE).data[0];
            const r = got.find((f) => f.type === RESULT);
            return { state: st, urls: r ? strings(r.data) : [] };
        }
        // The state, asked until a board that is still starting answers.
        async ready(ms = 30000) {
            const until = Date.now() + ms;
            for (;;) {
                try { return await this.state(1000); }
                catch (e) { if (e.code !== 0 || Date.now() > until) throw e; }
            }
        }
        async info() {
            const s = strings((await this.ask(INFO, [], (g) => g.some((f) => f.type === RESULT), 3000))
                .find((f) => f.type === RESULT).data);
            return { firmware: s[0] || "", version: s[1] || "", chip: s[2] || "", name: s[3] || "" };
        }
        // [{ssid, rssi, locked}], strongest first.
        async scan() {
            const got = await this.ask(SCAN, [], (g) => g.some((f) => f.type === RESULT && f.data[1] === 0), 20000);
            return got.filter((f) => f.type === RESULT && f.data[1] > 0).map((f) => strings(f.data))
                .map((s) => ({ ssid: s[0], rssi: +s[1], locked: s[2] === "YES" }));
        }
        // The board's name, set first when `name` is given: the name it took.
        async name(name) {
            const got = await this.ask(NAME, name ? field(name) : [], (g) => g.some((f) => f.type === RESULT), 3000);
            return strings(got.find((f) => f.type === RESULT).data)[0] || "";
        }
        // The URLs with a fresh claim (found() reads it), [] while the board
        // is on no network. Firmware without it rejects with code 2.
        async claim() {
            const got = await this.ask(CLAIM, [], (g) => g.some((f) => f.type === RESULT), 3000);
            return strings(got.find((f) => f.type === RESULT).data);
        }
        // Join `ssid`: the URLs the board answers once it serves on it.
        async wifi(ssid, password) {
            const got = await this.ask(WIFI, [...field(ssid), ...field(password)],
                (g) => g.some((f) => f.type === RESULT), 60000);
            return strings(got.find((f) => f.type === RESULT).data);
        }
    }
    // The board's log as lines, for a person to read: `feed` takes what
    // Client hands `log`, a partial line is held until its end, ANSI escapes
    // and other control characters are stripped, and every string given to
    // `hide` is blanked in each line before `each(line)` sees it or `text()`
    // copies it. Blank lines are dropped; the last `keep` lines are kept.
    const ANSI = /\x1b(?:\[[0-?]*[ -\/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-_])/g;
    const BLANK = "********", LONG = 4096;
    class Lines {
        constructor(each = () => { }, keep = 500) {
            this.each = each;
            this.keep = keep;
            this.lines = [];
            this.part = "";
            this.secrets = [];
        }
        hide(secret) {
            if (secret && !this.secrets.includes(secret)) this.secrets.push(secret);
        }
        clean(line) {
            line = line.replace(ANSI, "").replace(/[\x00-\x08\x0b-\x1f\x7f]/g, "");
            for (const s of this.secrets) line = line.split(s).join(BLANK);
            return line;
        }
        feed(text) {
            const cut = (this.part + text).split("\n");
            this.part = cut.pop();
            for (const l of cut) this.add(l);
            if (this.part.length > LONG) {
                // A line with no end in sight goes out but for a tail that a
                // secret could still be cut across.
                const hold = Math.max(0, ...this.secrets.map((s) => s.length - 1));
                this.add(this.part.slice(0, this.part.length - hold));
                this.part = this.part.slice(this.part.length - hold);
            }
        }
        // The held partial line, as a line: what a board said last before it
        // stopped answering.
        flush() {
            if (this.part) this.add(this.part);
            this.part = "";
        }
        add(raw) {
            const line = this.clean(raw);
            if (!line.trim()) return;      // a frame's own newline, a blank
            this.lines.push(line);
            if (this.lines.length > this.keep) this.lines.shift();
            this.each(line);
        }
        text() {
            return this.lines.map((l) => this.clean(l)).join("\n");
        }
    }
    return { Client, Lines, found, frame, rpc, strings, READY, PROVISIONED };
})();
if (typeof module != "undefined") module.exports = self.moyImprov;
