// First setup over the cable (docs/web_console_online_2026-11.md §2, flow 1;
// §7): Improv on a board's USB serial (improv.js) names the console, puts it
// on a Wi-Fi network and reports where it is, and the console goes into My
// consoles (kept.js) under the board's own id. A board with no password yet
// answers a claim with its address, and this page then asks for the
// console's password, which it keeps in memory only and hands the console's
// window over the link (link.js) when it opens. One body for both pages that
// run it: My consoles ("Set up a board by cable") and the flasher, after a
// flash, on the port it flashed through.
//
//   moySetup.run(box, port, {lines, wait, done(c, secret)})   wait: ms a
//   board just flashed may take to answer (its first boot seeds its store)
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
        p.className = "setup-said" + (cls ? " " + cls : "");
        p.textContent = text;
    }

    async function run(box, port, opts = {}) {
        box.textContent = "";
        box.hidden = false;
        const imp = new moyImprov.Client(port, { lines: opts.lines });
        try {
            line(box, "Talking to the board...");
            await imp.open();
            await imp.ready(opts.wait || 30000);
            const info = await imp.info();
            line(box, "Looking for Wi-Fi networks...");
            const nets = await imp.scan().catch(() => []);
            const got = await ask(box, info, nets);
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
            if (where.claim) secret = { claim: where.claim, password: await choose(box, c.name) };
            box.textContent = "";
            line(box, c.name + " is on the network at http://" + c.address + "/"
                 + (c.local ? " (" + c.local + ")" : "") + ".", "ok");
            if (opts.done) opts.done(c, secret);
            return { c, secret };
        } catch (e) {
            line(box, "Setup stopped: " + (e && e.message || e), "bad");
            throw e;
        } finally {
            await imp.close();
        }
    }

    // The form: the console's name, a network the board sees (or one typed)
    // and its password. -> {name, label, ssid, password}
    function ask(box, info, nets) {
        return new Promise((resolve) => {
            const f = el("form", { class: "setup" });
            f.append(el("p", { class: "note" }, "Found " + (info.chip || "a board") + " running "
                + (info.firmware || "Moybyte") + " " + info.version + "."));
            const name = el("input", { name: "name", placeholder: "Name (kitchen)", autocomplete: "off",
                                       maxlength: "24", required: "" });
            name.value = info.name && info.name != "moybyte-zero" ? info.name : "";
            const pick = el("select", { name: "net" });
            for (const n of nets) pick.append(el("option", { value: n.ssid }, n.ssid + (n.locked ? "" : " (open)")));
            pick.append(el("option", { value: "" }, "Another network..."));
            const other = el("input", { name: "ssid", placeholder: "Network name", autocomplete: "off",
                                        maxlength: "32" });
            other.hidden = nets.length > 0;
            pick.onchange = () => { other.hidden = pick.value !== ""; };
            const pw = el("input", { name: "wifi", type: "password", placeholder: "Wi-Fi password",
                                     autocomplete: "off" });
            f.append(name, pick, other, pw, el("button", {}, "Connect it"));
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
            const a = el("input", { type: "password", placeholder: name + "'s password", autocomplete: "new-password" });
            const b = el("input", { type: "password", placeholder: "Again", autocomplete: "new-password" });
            f.append(el("p", { class: "note" }, name + " has no password yet. Choose one, "
                + PW_MIN + " to " + PW_MAX + " characters: every browser pairs with it."), a, b,
                el("button", {}, "Set it"));
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
    return { run };
})();
