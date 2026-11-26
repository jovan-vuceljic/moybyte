// First setup over the cable (docs/web_console_online_2026-11.md §2, flow 1;
// §7): Improv on a board's USB serial (improv.js) names the console, puts it
// on a Wi-Fi network and reports where it is, and the console goes into My
// consoles (kept.js) under the board's own id. A board with no password yet
// answers a claim with its address, and this page then asks for the
// console's password, which it keeps in memory only and hands the console's
// window over the link (link.js) when it opens. One body for both pages that
// run it: My consoles ("Set up a board by cable") and the flasher, after a
// flash, on the port it flashed through. Under the steps, a "Board log"
// panel shows what the board prints on the cable besides Improv, with the
// Wi-Fi password blanked (moyImprov.Lines); it opens by itself when setup
// stops, since a board says why it could not join only there.
//
// A board already on a network is MANAGED instead, as My consoles' "Manage
// by cable" does at any time: it joins another network (Improv's join, its
// new address saved), takes a new name, and takes a new password. The
// password crosses as the first one does: the board answers its address
// with a fresh claim (improv.js's claim(), Moybyte's own command), and the
// console's window sets the password with it over the link, so the
// password never crosses the cable. Physical access is the proof; the new
// password signs every browser out, and this one pairs with it.
//
//   moySetup.run(box, port, {lines, wait, done(c, secret), changed(c)})
//     wait: ms a board just flashed may take to answer (its first boot
//     seeds its store); done: the console and the secret its window takes
//     ({claim, password}, or null with none to set); changed: the list
//     changed under a managed board
//   moySetup.manage(box, port, {lines, c, done, changed})   the same panel
//     whatever the board's state; `c` the card it was asked from
self.moySetup = (() => {
    const PW_MIN = 8, PW_MAX = 64;

    function el(tag, attrs, text) {
        const e = document.createElement(tag);
        for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
        if (text) e.textContent = text;
        return e;
    }
    function line(box, text, cls) {
        let p = box.querySelector(".setup-said");
        if (!p) { p = el("p", { class: "setup-said" }); box.append(p); }
        p.className = "state setup-said" + (cls ? " " + cls : "");
        p.textContent = text;
    }

    async function run(box, port, opts = {}) {
        return start(box, port, opts, false);
    }
    async function manage(box, port, opts = {}) {
        return start(box, port, opts, true);
    }
    async function start(box, port, opts, always) {
        box.textContent = "";
        box.hidden = false;
        const log = boardLog();
        const imp = new moyImprov.Client(port, { lines: opts.lines, log: (t) => log.lines.feed(t) });
        try {
            line(box, "Talking to the board...");
            box.append(log.el);
            await imp.open();
            const st = await imp.ready(opts.wait || 30000);
            const info = await imp.info();
            const now = st.state === moyImprov.PROVISIONED ? moyImprov.found(st.urls) : null;
            if (always || (now && now.id)) return await panel(box, imp, log, info, now, opts);
            line(box, "Looking for Wi-Fi networks...");
            const nets = await imp.scan().catch(() => []);
            const got = await ask(box, info, nets);
            log.lines.hide(got.password);
            line(box, "Naming it " + got.name + "...");
            const name = got.name ? await imp.name(got.name) : info.name;
            line(box, "Joining " + got.ssid + "...");
            const where = moyImprov.found(await imp.wifi(got.ssid, got.password));
            if (!where || !where.id) throw new Error("the board answered no address");
            const list = moyKept.read();
            const c = moyKept.put(list, { id: where.id, name: got.label || name,
                                          address: where.address, local: where.local || "" });
            delete c.secure;
            if (!moyKept.write(list)) line(box, "This browser keeps nothing for this site: the console is listed this visit only.", "bad");
            let secret = null;
            if (where.claim) {
                secret = { claim: where.claim, password: await choose(box, c.name) };
                log.lines.hide(secret.password);
            }
            box.textContent = "";
            line(box, c.name + " is on the network at http://" + c.address + "/"
                 + (c.local ? " (" + c.local + ")" : "") + ".", "ok");
            // The password is the terminal's too: the board serves SSH once
            // its window sets it, and with none it serves no SSH until `passwd`.
            box.append(el("p", { class: "note ssh" }, secret
                ? "Its terminal: ssh " + (c.local || c.address) + ", with that password, once its window has set it."
                : "Its terminal: ssh " + (c.local || c.address) + ", with its password (passwd in its terminal sets one)."));
            if (opts.done) opts.done(c, secret);
            box.append(log.el);
            return { c, secret };
        } catch (e) {
            line(box, "Setup stopped: " + (e && e.message || e), "bad");
            log.lines.flush();
            log.el.open = true;
            log.end();
            throw e;
        } finally {
            await imp.close();
        }
    }

    // The card a managed board is kept under: its own id's, else the card it
    // was asked from when that one was added by hand (it is this board's from
    // now on), else the one at its address. `got` what the board answered.
    function keep(box, info, got, from) {
        const list = moyKept.read();
        const byHand = from && !/^[0-9a-f]{32}$/.test(from.id) && list.find((x) => x.id === from.id);
        if (byHand && !list.find((x) => x.id === got.id)) byHand.id = got.id;
        const c = moyKept.put(list, { id: got.id, address: got.address, local: got.local || "" });
        if (!c.name) c.name = info.name || got.address;
        delete c.secure;
        if (!moyKept.write(list)) line(box, "This browser keeps nothing for this site: the console is listed this visit only.", "bad");
        return c;
    }

    // The managed board's panel: Wi-Fi, its name, its password, and Done,
    // which ends it. One request at a time; each says how it went, and a
    // refusal opens the board's log.
    function panel(box, imp, log, info, where, opts) {
        return new Promise((resolve) => {
            let c = where && where.id ? keep(box, info, where, opts.c) : null;
            if (c && opts.changed) opts.changed(c);
            if (c && opts.c && /^[0-9a-f]{32}$/.test(opts.c.id) && opts.c.id !== c.id) {
                line(box, "This board is " + c.name + ", not " + opts.c.name + ".", "bad");
            }
            const head = el("p", { class: "note" });
            const said = () => {
                head.textContent = (c ? c.name : info.name || "The board") + " runs " + (info.firmware || "Moybyte")
                    + " " + info.version + (c ? ", at http://" + c.address + "/" + (c.local ? " (" + c.local + ")" : "")
                                              : ", on no network yet") + ".";
            };
            said();
            let busy = false;
            const act = (form, fn) => {
                form.onsubmit = async (e) => {
                    e.preventDefault();
                    if (busy) return;
                    busy = true;
                    const b = form.querySelector("button");
                    b.disabled = true;
                    try { await fn(); }
                    catch (err) {
                        line(box, (err && err.message || String(err)), "bad");
                        log.lines.flush();
                        log.el.open = true;
                        log.end();
                    }
                    b.disabled = false;
                    busy = false;
                };
            };
            // Wi-Fi: another network, or the same one again.
            const wifi = el("form", { class: "setup", name: "wifi" });
            const pick = el("select", { class: "field", name: "net" });
            pick.append(el("option", { value: "" }, "Another network..."));
            const other = el("input", { class: "field", name: "ssid", placeholder: "Network name", autocomplete: "off", maxlength: "32" });
            const wpw = el("input", { class: "field", name: "wifi", type: "password", placeholder: "Wi-Fi password", autocomplete: "off" });
            pick.onchange = () => { other.hidden = pick.value !== ""; };
            wifi.append(el("p", { class: "note" }, "Wi-Fi"), pick, other, wpw, el("button", { class: "btn" }, "Join"));
            busy = true;
            line(box, "Looking for Wi-Fi networks...");
            imp.scan().then((nets) => {
                for (const n of nets.slice().reverse()) pick.prepend(el("option", { value: n.ssid }, n.ssid + (n.locked ? "" : " (open)")));
                pick.value = nets.length ? nets[0].ssid : "";
            }).catch(() => { }).finally(() => {
                pick.onchange();
                busy = false;
                line(box, "");
            });
            act(wifi, async () => {
                const ssid = pick.value || other.value.trim();
                if (!ssid) throw new Error("It needs a network.");
                log.lines.hide(wpw.value);
                line(box, "Joining " + ssid + "...");
                const got = moyImprov.found(await imp.wifi(ssid, wpw.value));
                if (!got || !got.id) throw new Error("the board answered no address");
                c = keep(box, info, got, c || opts.c);
                wpw.value = "";
                said();
                line(box, c.name + " joined " + ssid + ", at http://" + c.address + "/.", "ok");
                if (opts.changed) opts.changed(c);
            });
            // The name: the card's, and the board's mDNS label.
            const naming = el("form", { class: "setup", name: "rename" });
            const name = el("input", { class: "field", name: "name", placeholder: "Name (kitchen)", autocomplete: "off", maxlength: "24", required: "" });
            name.value = c ? c.name : info.name || "";
            naming.append(el("p", { class: "note" }, "Name"), name, el("button", { class: "btn" }, "Rename"));
            act(naming, async () => {
                const label = name.value.trim().slice(0, 40);
                if (!label) throw new Error("It needs a name.");
                const took = await imp.name(label.toLowerCase().replace(/[^a-z0-9-]/g, ""));
                info.name = took;
                const now = (await imp.state()).urls;
                const got = moyImprov.found(now);
                if (got && got.id) {
                    c = keep(box, info, got, c || opts.c);
                    const list = moyKept.read(), k = list.find((x) => x.id === c.id);
                    if (k) { k.name = label; moyKept.write(list); c = k; }
                }
                said();
                line(box, "Named " + label + (took ? " (" + took + ".local)" : "") + ".", "ok");
                if (opts.changed && c) opts.changed(c);
            });
            // The password: a fresh claim over the cable, set by the window.
            const pass = el("form", { class: "setup", name: "password" });
            const a = el("input", { class: "field", type: "password", placeholder: "New password", autocomplete: "new-password" });
            const b = el("input", { class: "field", type: "password", placeholder: "Again", autocomplete: "new-password" });
            pass.append(el("p", { class: "note" }, "Console password, " + PW_MIN + " to " + PW_MAX
                + " characters. Setting it signs every browser out; each pairs again with it."), a, b,
                el("button", { class: "btn" }, "Set it"));
            act(pass, async () => {
                if (a.value.length < PW_MIN || a.value.length > PW_MAX) throw new Error("A password is " + PW_MIN + " to " + PW_MAX + " characters.");
                if (a.value !== b.value) throw new Error("The two do not match.");
                let got;
                try { got = moyImprov.found(await imp.claim()); }
                catch (err) {
                    if (err.code === 2) throw new Error("This board's firmware cannot set a password over the cable: update it first.");
                    throw err;
                }
                if (!got || !got.id || !got.claim) throw new Error("The board is on no network: join one first.");
                c = keep(box, info, got, c || opts.c);
                const secret = { claim: got.claim, password: a.value };
                log.lines.hide(secret.password);
                a.value = b.value = "";
                line(box, "Open " + c.name + " to set it: its window takes the password and pairs this browser.", "ok");
                if (opts.done) opts.done(c, secret);
            });
            const done = el("button", { class: "btn", type: "button", name: "done" }, "Done");
            done.onclick = () => {
                box.textContent = "";
                box.hidden = true;
                resolve({ c, secret: null });
            };
            box.prepend(head, wifi, naming, pass, done);
        });
    }

    // The board's lines as they come, the last 500, in a closed <details>:
    // {el, lines (moyImprov.Lines), end() (scrolled to its last line)}.
    function boardLog() {
        const box = el("details", { class: "boardlog" });
        const pre = el("pre");
        const copy = el("button", { class: "btn", type: "button" }, "Copy");
        box.append(el("summary", {}, "Board log"), pre, copy);
        let n = 0;
        const end = () => { pre.scrollTop = pre.scrollHeight; };
        const lines = new moyImprov.Lines((l) => {
            const pinned = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 4;
            pre.append(l + "\n");
            if (++n > lines.keep) { pre.firstChild.remove(); n--; }
            if (pinned) end();
        });
        copy.onclick = async () => {
            try { await navigator.clipboard.writeText(lines.text()); copy.textContent = "Copied"; }
            catch (e) { copy.textContent = "Copy failed"; }
            setTimeout(() => { copy.textContent = "Copy"; }, 1500);
        };
        box.ontoggle = end;
        return { el: box, lines, end };
    }

    // The form: the console's name, a network the board sees (or one typed)
    // and its password. -> {name, label, ssid, password}
    function ask(box, info, nets) {
        return new Promise((resolve) => {
            const f = el("form", { class: "setup" });
            f.append(el("p", { class: "note" }, "Found " + (info.chip || "a board") + " running "
                + (info.firmware || "Moybyte") + " " + info.version + "."));
            const name = el("input", { class: "field", name: "name", placeholder: "Name (kitchen)", autocomplete: "off",
                                       maxlength: "24", required: "" });
            name.value = info.name && !/^moybyte-zero(-[0-9a-f]{4})?$/.test(info.name) ? info.name : "";
            const pick = el("select", { class: "field", name: "net" });
            for (const n of nets) pick.append(el("option", { value: n.ssid }, n.ssid + (n.locked ? "" : " (open)")));
            pick.append(el("option", { value: "" }, "Another network..."));
            const other = el("input", { class: "field", name: "ssid", placeholder: "Network name", autocomplete: "off",
                                        maxlength: "32" });
            other.hidden = nets.length > 0;
            pick.onchange = () => { other.hidden = pick.value !== ""; };
            const pw = el("input", { class: "field", name: "wifi", type: "password", placeholder: "Wi-Fi password",
                                     autocomplete: "off" });
            f.append(name, pick, other, pw, el("button", { class: "btn pri" }, "Connect it"));
            f.onsubmit = (e) => {
                e.preventDefault();
                const ssid = pick.value || other.value.trim();
                const label = name.value.trim().slice(0, 40);
                if (!label || !ssid) { line(box, "It needs a name and a network.", "bad"); return; }
                f.remove();
                resolve({ name: label.toLowerCase().replace(/[^a-z0-9-]/g, ""), label, ssid,
                          password: pw.value });
            };
            box.prepend(f);
            line(box, "Name the console and pick its Wi-Fi.");
            name.focus();
        });
    }

    // A board with no password: the console's own, typed twice. Kept in
    // memory only, for the window the console opens in.
    function choose(box, name) {
        return new Promise((resolve) => {
            const f = el("form", { class: "setup" });
            const a = el("input", { class: "field", type: "password", placeholder: name + "'s password", autocomplete: "new-password" });
            const b = el("input", { class: "field", type: "password", placeholder: "Again", autocomplete: "new-password" });
            f.append(el("p", { class: "note" }, name + " has no password yet. Choose one, "
                + PW_MIN + " to " + PW_MAX + " characters: every browser pairs with it."), a, b,
                el("button", { class: "btn pri" }, "Set it"));
            f.onsubmit = (e) => {
                e.preventDefault();
                if (a.value.length < PW_MIN || a.value.length > PW_MAX) { line(box, "A password is " + PW_MIN + " to " + PW_MAX + " characters.", "bad"); return; }
                if (a.value !== b.value) { line(box, "The two do not match.", "bad"); return; }
                f.remove();
                resolve(a.value);
            };
            box.prepend(f);
            line(box, "");
            a.focus();
        });
    }
    return { run, manage };
})();
