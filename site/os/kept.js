// The consoles this browser knows (docs/web_console_online_2026-11.md §2):
// My consoles' list in the origin's localStorage, `moy.consoles`, which My
// consoles (consoles.js) and the flasher's first setup (setup.js) both
// write. A console is {id, name, address, local?, secure?, page?, pack?,
// reached?}: `id` the board's own (32 hex, what Improv reported) or one made
// here for a console added by hand, `address` host[:port] (opened as
// http://, or https:// where `secure`), `local` its .local name where Improv
// reported one, `page` and `pack` the digests its last hello named and
// `reached` when that was (ms).
self.moyKept = (() => {
    const KEY = "moy.consoles";
    const HOST = /^(\[[0-9a-f:.]+\]|[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*)(:\d{1,5})?$/i;
    const okHost = (a) => typeof a == "string" && HOST.test(a);

    function read() {
        try {
            const v = JSON.parse(localStorage.getItem(KEY) || "[]");
            return Array.isArray(v) ? v.filter((c) => c && typeof c.id == "string"
                && typeof c.name == "string" && okHost(c.address)) : [];
        } catch (e) { return []; }
    }
    // false where this browser keeps nothing for the site.
    function write(list) {
        try { localStorage.setItem(KEY, JSON.stringify(list)); return true; }
        catch (e) { return false; }
    }
    // What a person typed as a console's address: an IP, a host name or a
    // .local name, with or without http(s):// and a port, and nothing after
    // the host but a "/". {address, secure} or null.
    function address(text) {
        let t = String(text || "").trim();
        if (!t) return null;
        if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(t)) t = "http://" + t;
        let u;
        try { u = new URL(t); } catch (e) { return null; }
        if (u.protocol != "http:" && u.protocol != "https:") return null;
        if (u.pathname != "/" || u.search || u.hash || u.username || u.password) return null;
        const a = u.host.toLowerCase();
        return okHost(a) ? { address: a, secure: u.protocol == "https:" } : null;
    }
    // The URL a console's window opens.
    function url(c) {
        return (c.secure ? "https://" : "http://") + c.address + "/";
    }
    // `c` into the list: the console with its id, else its address, is
    // updated in place; else it is added. The entry kept.
    function put(list, c) {
        const had = list.find((k) => k.id === c.id)
            || list.find((k) => k.address === c.address && !!k.secure === !!c.secure)
            || (c.local ? list.find((k) => k.address === c.local || k.local === c.local) : null);
        if (!had) { list.push(c); return c; }
        Object.assign(had, c);
        return had;
    }
    return { KEY, read, write, address, url, put };
})();
if (typeof module != "undefined") module.exports = self.moyKept;
