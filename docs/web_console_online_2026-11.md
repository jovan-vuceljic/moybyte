# The browser console, online (2026-11)

How a person sets up and opens the browser console of a board whose storage
cannot hold it, and the design those steps need. §2 is the user flows the
owner decided (2026-11-23). §1 is what IS. Everything after §2 is PROPOSED
unless it carries an owner's date, and §12 holds the owner's answers to
the questions it raised.

## 0. Why

The browser console is the wasm build of the whole console
(`firmware/web_runner/`), packed as `moybyte_web.pack` and installed into a
board's store as an add-on cart (`native/moy_net/moy_page.h`). Its size is
the store's to pay, and `tools/store_image.py --check` prints, per board,
what the add-on leaves of its store. Three boards are losing that race:

- the ESP32-C3 Zero, whose browser console is its only face. The add-on no
  longer fits its store.
- the Guition P4, whose internal store holds the add-on but not its first
  boot's carts beside it when no card is fitted.
- the Elecrow P4 with an empty TF slot, in the same position.

The S3 consoles are next, and the pack only grows.

**Owner, 2026-11-23:** the C3's console is online. Its board.toml says
`[web] console = "online"`, so neither the website's install
(`tools/store_image.py`) nor the cable flash (`tools/board_flash.py`) puts
an add-on in its store. The C3 may sit on `dev` like that, with no browser
console, but flows 1 and 2 (§2) land before the next release (§11).

**Owner, 2026-11-26:** the XIAO Zero's console is online too ("The store
will probably fill up again"): its app slots grew for the apps' services
(#256), and its 3 MiB store is its carts'. **Its owner may keep the console
on the board all the same**: "Works offline", a row of the browser
console's Settings on a board whose console is online, off by default.
Install fetches the add-on the image fits through the release's signed
index, as a console's step does (`runtime/carts/web_addon.py`'s
`AddonStep`), and the board then serves its own pack, which the loader
prefers (`GET /sync`'s `local`); Remove takes the folder back and the
loader is online again; a store that cannot hold it is refused with both
sizes. The choice is a file of the store (`system/console_offline`), so an
update brings the add-on that fits the new image. The board's half is
`device/zero_offline.py` behind `/official`, the page's
`firmware/web_runner/offline_link.py`; it needs the image's release index,
so the C3, which has no updater, does not offer it.

**Owner, 2026-11-23: the OS site is os.moybyte.com.** That one app holds the
flasher, My consoles, the PWA, the packs and, later, flow 3. moybyte.com
becomes a separate landing page for future hardware. It is a subdomain
rather than a path because storage and permissions belong to an origin: on
a path, the landing page's third-party scripts (a newsletter embed,
analytics) would share them with the page that remembers consoles and will
later sync their files.

## 1. What is there today

- **The image names its page by digest.** Every board's build packs the
  bundle (`tools/gen_web_blob.py --pack`); the image carries the pack body's
  sha256 (`moy_web_want`, `native/moy_web/moy_web_blob.h`), the whole
  file's (`moy_web_pack_sha`) and the loader (§3, `moy_web_loader`).
  The webhost serves a pack only when its head names that digest, from
  `/p/<12 hex>/`, its assets `immutable` and the whole file at
  `/p/<12 hex>/moybyte_web.pack`; `/` is a 302 there, or the sentence
  saying why there is none (`page_root`, `native/moy_net/moy_webhost.c`).
- **The loader is built** (phase 1, §11): a board whose console is online
  (both Zeros) serves it at `/`, every board at `/loader.html`, and `GET
  /sync` names both digests and `local` (`native/moy_net/moy_page.h`, THE
  LOADER). A Zero whose console is online asks its release for an add-on
  only where its owner chose Works offline (`zero_host.make_addon`).
- **The release publishes every add-on it makes** as
  `moybyte_web-<digest>.moy.zip` beside the payload, listed in the board's
  signed carts index (`tools/web_pack.py`): the stable release's every one,
  the beta's those of the last 30 days like the pack store (§12), within
  the index's budget. A board whose console is online (the Zeros) installs
  one only where its owner chose Works offline, and its index lists them
  as any board's does. The beta deletes an add-on no index lists once it is
  older than that (`publish_firmware_release.prune_carts`). A board installs the one that
  fits through the ordinary install, every file checked against the signed
  index (`runtime/carts/web_addon.py`'s `AddonStep`; on a Zero
  `device/zero_host.py`). Those assets are GitHub release downloads, which
  carry no CORS header, so no page can fetch them.
- **My consoles and the link are built** (phase 2, §11): the source is
  `site/os/`, and `tools/os_site.py build` writes os.moybyte.com's
  `/console/` folder, My consoles beside the pack store's packs (§4); the
  link's board end is the loader's and then the console page's
  (`page_tail.js`), §5.
- **First setup over the cable is built** (phase 3, §11): Improv on a
  Zero's USB serial (§7), run by the flasher after a flash and by My
  consoles for a board already flashed, one client for both pages
  (`site/os/improv.js`, `setup.js`); a console with no password takes its
  first by the claim, over the link. A board already on a network is
  managed over the same cable at any time ("Manage by cable", §7): its
  Wi-Fi, its name and a new password. My consoles also adds a console by
  hand by its address, which its first open verifies.
- **os.moybyte.com is GitHub Pages** (owner, 2026-11-24): one deploy
  (`.github/workflows/pages.yml`) on every `dev` and `master` push holds
  the project site at `/`, the dev site at `/dev/` and `/console/`.
  moybyte-org.github.io/moybyte/ redirects there.
- **The project site** (`site/build.py`) hosts the site's own player (a `--site` build,
  `dist_site`, which is not the boards' pack) and the flasher
  (`site/flash.js`, esptool-js over Web Serial). The flasher writes each
  board's install: the merged image, plus a store holding the add-on that
  fits (none on an online board). moybyte.com is the page for kids and
  parents.
- **Two web modes, no crossover** (`.claude/rules/web.md`): a page's
  serving host decides where its carts live. The page decides once at boot,
  by probing `GET /sync` on its own origin, before the VFS is seeded.
- **The Zero's setup** is its own open access point and a form on it
  (`device/zero_setup.py`): the network, the board's name and its password.
  The access point serves that form only: a board either serves the console
  or hosts the AP, never both. A browser then pairs with the password and
  keeps its device key in the board origin's `localStorage` (`page_tail.js`).

## 2. The flows (owner, 2026-11-23)

What the person does. The rest of the doc is what makes each step work, and
the notes under each step point to where that is.

**Flow 1: first setup, once.** Flash, set up and use are one path.

1. On os.moybyte.com, "Get a console": plug the board in by USB and press
   Install. The site flashes it from the browser (`site/flash.js`).
2. The flash ends with "Connect it to Wi-Fi", on the port it flashed
   through: pick the Wi-Fi, type its password, and name the console
   (`kitchen`). This is Improv (§7), and its form is My consoles' own
   (`site/os/setup.js`).
3. The board joins the network and reports its address over the cable. The
   site saves the console under **My consoles**, by the board's id. A board
   with no password yet asks for one next (§7), which the page keeps in
   memory only.
4. The page offers "Open kitchen": the console's window opens over the
   link, takes the password by the board's claim and signs in.
5. A board flashed before has the same setup in My consoles, "Set up a
   board by cable"; one already on a network is managed there instead
   (§7, "Manage by cable").
6. Without Web Serial (an iPhone), flash from a computer, or use the board's
   setup hotspot and its form, then add the console by its address.

**Adding a console by hand**, for a console that never ran the setup here
(a phone's My consoles, a console with a screen): its address, as an IP, a
host name or a `.local` name, with or without `http://` and a port, and a
name or none (the address is the name then). The address is trimmed and
must be http(s) with nothing after the host but `/`; an address the list
has updates that console instead of adding a second. The site cannot check
it (an https page cannot reach an http board), so the first open does: the
board's loader says hello over the link, and the list shows the console
reached and the console its board named, or "not reached yet" with the
address to open by hand.

**Flow 2: every day.**

- **The main entry is My consoles on os.moybyte.com** (owner, 2026-11-23),
  which opens offline once its service worker has cached it. Tap `kitchen`:
  a window opens on the board's origin (the loader, §3), and the site hands
  it the console's bytes by `postMessage` (the link, §5). The console runs
  on the board's origin, so the carts live on the board.
- **The other entry** is typing `http://kitchen.local` or the IP. The loader
  gets the pack from its own cache (IndexedDB), from os.moybyte.com, or from the
  board's own copy on a board that keeps one (§4).
- The site keeps both addresses Improv reported, the IP and `.local`, and
  opens the IP (2026-11-24): every browser reaches it, where `.local` does
  not resolve on some Android phones, and a console's window keeps one
  origin, so its paired key and its cached pack stay where it found them.
  The `.local` name is shown beside it. A board whose IP changed is set up
  again over the cable, which updates its entry by its id. The device
  checklist (§11) decides whether `.local` should be the one opened.

*Note:* on iOS and Android, an INSTALLED web app cannot open that window
with the link intact (§9). There the main entry runs from os.moybyte.com in a
browser tab; the installed app is the desktop's entry.

**Flow 3: managing the console from the website. Later, not in the first
release (owner, 2026-11-23).**

- Back up and sync to the PC: the board-origin window reads the files, and
  the site's window writes them into a folder (File System Access, in
  Chromium browsers) or, elsewhere, saves them as a download.
- Restore, and move carts between consoles.
- Install a store cart to a chosen console.
- Update the firmware of a board with no OTA.
- Edit on the PC and sync back.

The link the first release ships is built so these fit on top of it without
changing it (§5, §10).

## 3. The loader

**Every board's root serves a loader**, a page of a few KB that lives in the
image, gzipped and served `no-cache`. A test holds it to 4 KiB gzipped, and
its cost shows in the image ledger (`docs/perf/image.md`) like any part's.
The console's own page is inside the pack.

**What it asks the board.** `GET /sync` is already the unsealed mode
marker. It grows the pack's digests and says whether the board serves a
copy of its own:

```
GET /sync   {"sync":1, "page": <body digest>, "pack": <whole-pack digest>, "local": 0|1}
```

That reveals nothing new: the page's `/p/<12 hex>/` address already names
the build to anybody who asks for `/`. An image that names no page answers
`"page": null, "pack": null`, and the loader says so. `local` is 1 while the
board's add-on is the one that fits (`MOY_PAGE_READY`).

**Where it is served.** On a board whose console is online `/` is the loader;
every board also serves it at `/loader.html`, which is how a board that
keeps its copy boots through the loader before phase 4 makes it the root of
every board, and how its boot is timed against the store-served one.

**What a plain-http origin denies it.** The board is `http://`, so the
loader runs in an insecure context. It has no service worker, no Cache API,
no `crypto.subtle`, and no `navigator.storage`, so no `persist()`. It does
have IndexedDB, `fetch`, `DecompressionStream`, Blob URLs, module workers
and `postMessage`, none of which need a secure context. So:

- **The sha256 is the loader's own JavaScript.** The console's wasm cannot
  check the bytes it arrives in.
- **The cache is best-effort storage.** The browser may evict it under
  pressure; a miss falls through to the next source.
- **An origin is an address.** `http://192.168.1.57` and
  `http://kitchen.local` are two origins with two caches, and every Zero on
  its own AP is `http://192.168.4.1`. Cache entries are keyed by digest, so
  boards that share an address share a cache harmlessly.

**It verifies on every read, not only on write.** Another device that later
answers at the same address can write that origin's IndexedDB: DHCP hands
the address out again, or a different board's AP comes up. A loader that
trusted its cache would run what that device left there under the next
genuine board's name. Hashing the cached pack at each boot has a cost, which
phase 1 measures and records in its issue.

**The digest covers the whole pack.** The image names the body's digest (the
head carries it, so it cannot cover itself), and the head's entries say
which bytes are which asset. The loader runs those bytes, so the image also
names the sha256 of the whole file, head included, in `gen_web_blob`'s
generated C. The body digest stays the pack's identity everywhere it is one
today: the add-on cart's id, the release asset's name, and the mirror's file
name. The whole-file digest is the one the loader checks.

**Booting from bytes** takes one change in the console:

- The pack's assets are pre-gzipped. The loader inflates each one
  (`DecompressionStream`), makes a Blob URL for it, and hands the page an
  asset map.
- Today the page starts `worker.js` by a relative URL, and the worker
  imports `micropython.mjs` and `moy_store.mjs` statically. A Blob URL
  cannot resolve those.
- So the page creates its worker from `asset("worker.js")`. The worker
  takes the map in its first message and imports its two modules, and the
  wasm's URL (`loadMicroPython`'s `url`), through it. The relative names
  are the default where no loader ran: the site's player and `serve.py`.
- The loader writes the pack's `index.html` into its own document
  (`document.open`/`write`), keeping its own state in a closure. The page
  then runs under the board's origin, and its `fetch("/sync")` reaches the
  board.
- `document.open` erases the window's listeners, so the console page, not
  the loader, owns the link from then on (§5).

**What the cached boot gives up** is the HTTP cache's compiled-code cache. A
wasm served `immutable` from the board compiles once and is kept compiled;
one built from bytes compiles at every boot. Phase 1 times the boot both
ways, on a phone and on a PC.

**Eviction.** After a boot, the loader keeps the pack it booted and the one
before it (a rollback names the previous image's digest) and deletes the
rest. Its IndexedDB (`moy-loader`, store `packs`) holds each pack under its
whole-file digest and the two kept digests, newest first, under `order`.

## 4. Where the bytes come from

The loader tries these in order and runs only bytes whose digest matches:

1. **The site's hand-off**, when the window was opened by My consoles (§5).
2. **IndexedDB** on this origin.
3. **The board's own copy**, on a board whose store or card has room for it
   (`[web] console` unset: the add-on as today, `AddonStep` and all). It is
   served whole as one asset, `/p/<12 hex>/moybyte_web.pack`, and checked
   like the rest. It is the only way
   a browser that never saw the site starts a console on a LAN without
   internet.
4. **os.moybyte.com by CORS**, at `/console/<body digest>.pack`: the pack file
   as the add-on cart holds it. An `http://` page may fetch `https://`;
   mixed content only blocks the other way. Chrome's Local Network Access
   only gates a request from a less private address to a more private one,
   never a LAN page reaching the internet. A worktree build's list names the
   developer's own `firmware/web_runner/serve.py`, served with CORS, so
   `tools/board.py` and `tools/web.py shot` reach a C3 whose digest no site
   publishes. The list is the build's (`tools/gen_web_blob.py`, THE
   MIRRORS): a CI build names os.moybyte.com alone; any other build names
   `http://<its LAN address>:8321/console/` (serve.py's port) and then the
   site; `MOYBYTE_WEB_MIRRORS` or `--mirror` overrides both. serve.py serves
   the pack of the bundle it serves at `/console/<body digest>.pack` in every
   mode, and its `--loader` twin is a board whose console is online.

What a pack passed through decides nothing: the digest does. A LAN mirror
can be added without touching the trust model.

**The packs live on os.moybyte.com** (owner, 2026-11-23), which is GitHub
Pages (owner, 2026-11-24). Pages takes no header file: it sends every file
with `Access-Control-Allow-Origin: *`, which is all the loader needs, and
`max-age=600`, which costs nothing, because the loader keeps a pack under
its digest and asks for it only when its cache has none. Every `dev` and
`master` push publishes, in the same Pages deploy as the project site,
the pack of every add-on cart on the two rolling releases, the assets the
boards install from, read by their names, since the C3's index names none
(`pages.yml`, "Assemble My consoles and the console's packs").
`tools/pack_store.py` is the store: `fetch` takes a release's indexes and
add-on carts, `build` writes `console/<body digest>.pack`, keeping every
pack of the stable release's and the beta's of the last 30 days (§12), each
checked against its name's digest, and its index entry where an index names
it, and `check` asks a host for every digest the indexes
name, as a board's origin, and reads the pack back. `tools/os_site.py
build` runs that `build` and puts My consoles beside the packs, so the
mirror the images name is My consoles' own folder.

## 5. The link between the windows

**The main path, in the first release.** My consoles opens
`http://<address>/` in a window, from the tap, so it is a user gesture and
no popup blocker stops it. The two windows then talk by `postMessage`:

- An https page cannot fetch an `http://` LAN address. Mixed content blocks
  it, and so does Local Network Access in Chrome.
- A window on the board's origin can talk to its own origin, and windows
  talk to each other across origins.
- The bytes cross with their buffer transferred, not copied.

**One envelope, versioned**, so that flow 3 adds message kinds and changes
nothing. Version 1 is built:

```
{moylink: 1, id, kind, ...}      a message; `id` a number its sender picks
{moylink: 1, re: id, kind, ...}  the reply to the request `id`
hello   board -> site   page, pack: the digests /sync gave; local; kinds: the kinds it serves
pack    site -> board   request: bytes, the pack (a transferred ArrayBuffer), or null where
                        the site keeps none; the reply says ok, true or false
state   board -> site   state: booted | sign-in | signed-in | failed, and said: the sentence
unknown                 the reply to a request of a kind its receiver does not serve
claim   site -> board   request: claim, board (its id), password: the password the
                        cable's claim sets (§7); the reply says ok, and said: why not
```

`hello` and `state` are notices, answered by nothing. The site answers a
`hello` at once with a `pack`, so the loader, which has an opener, waits up
to 4 s for one before its next source: that wait is only ever spent on an
opener that is not a site. A second `pack` is refused. `hello` carries no
board id and no name: `/sync` names neither, and the console learns the id
only when it signs in. My consoles keys a console by the board's id where
Improv reported it (§7) and by an id of its own for one added by hand; a
`hello` is what marks a console reached, with the digests it named. The
site sends `claim` once, when a console it holds a claim for says
`sign-in` or `signed-in` (a new password for a console this browser
already pairs with), or at once to a window that said either before.

**Both ends check the origin.** The board's end takes messages only from the
window that opened it, and only at the origin of a mirror the image names
(§4): the site that hands a pack is the one that publishes it, so the image
names it once. It posts `hello` and `state` to each of those origins, so a
window another page opened hears nothing. The site's end (`site/os/link.js`,
My consoles' and the flasher's)
takes messages only from a window it opened, at the origin it opened it at.
Neither end ever evaluates a message; what My consoles shows of one is text.
A `pack` is bytes the loader checks like any source's, and a pack the loader
refuses is one the site drops from its cache.

**The board's end is the console page.** The loader answers `pack` and any
other kind before the boot (`loader.html`). After the boot, the console page
(`page_tail.js`) holds the link, because `document.open` erased the loader's
listener; the loader leaves it the origins (`window.moyLink`), the window
keeps its opener, and in version 1 it refuses a `pack`, takes a `claim`
(the worker makes the record and pairs, `worker.js`'s THE CLAIM), answers
every other kind as unknown, and sends `state`. Every request
that touches the store goes through the console in that window: it runs in
the VM like every rule (`.claude/rules/web.md`), and it travels over the
sync RPC the page already uses. The site never reaches the board itself.
Neither the site nor a board's page may send `Cross-Origin-Opener-Policy`,
which would leave the window with no opener.

**My consoles' window.** A tap opens `http://<address>/` named for that
console; a tap on a console whose window is still open brings it forward
and never loads it again, because its tab may hold work it has not synced.
Where the browser opens no window (`window.open` returns null, as an
installed app on iOS does), My consoles shows the address as a link.

**Flow 3 on top of the link** (later). Each item becomes a set of link
kinds the board's end lists in `hello`, behind a consent the board's
window asks for once per site ("os.moybyte.com may manage kitchen"), recorded
in that origin's storage:

- *Back up*: the board window reads files and streams them to the site
  window. The site writes them into a folder (`showDirectoryPicker`, in
  Chromium browsers) or saves the backup archive
  (`runtime/carts/moy_backup.py`'s format) as a download.
- *Restore, move*: the same in reverse. Moving between two consoles is two
  board windows and the site in between.
- *Install a store cart*: the site fetches the cart and its index entry, and
  the board checks both. The C3 can fetch no https shelf itself
  (`firmware/esp32c3_zero/README.md`), so the browser carries the bytes and
  the board's own signature check decides, as it does for an install.
- *Firmware for a board with no OTA*: the C3 has one app slot, so no
  network update can replace the image it runs. The link tells the site
  which version is running and takes a backup first. The update itself is
  the flasher's merged image over the cable, which keeps the store.
- *Edit on the PC*: File System Access has no change notification, so the
  sync back is a press (or a poll while the window is open), never a watch.

**The site's window lends the console what only a secure context has**
(#254, later). Web Serial, WebUSB, Web Bluetooth, Web MIDI and
`getUserMedia` exist only in a secure context, and the console on the
board's origin is plain http. The site's window is https, so it can hold
the device and carry its traffic over the link: a `device` kind family
the board's end lists in `hello`, behind each device API the boards offer
(the lease or `class` row an app asks for), so one app runs on both. Link
v1 ships none, and its envelope needs no change for them. Two things
follow: a lent device lives as long as the site's window, so closing My
consoles ends it and the console reports the device gone (`None`, never a
stale read); and a grant is a real click in the site's window, never in
the console's.

**The live socket stays the console's** (#256). The console runs on the
board's origin, so its WebSocket to its board is `ws://` from an http page,
as today. An https page cannot open `ws://`, so the site's window never
carries the socket; the link carries what the site
needs. The loader also takes the pack off the board's serving: a C3 sends a
few KB at a page load, not the pack. #256's in-frame serving still applies to
the loader and `/sync`, so phase 1 measures a page load's frame stall on
the C3 and writes it to #256.

## 6. Integrity, signing, provenance

The chain of trust runs through the image:

1. A release's manifest is signed with the OTA key and names the image's
   sha256 (`device/moy_ota.py`); otherwise the owner put the image on by
   cable.
2. The image names the pack's digest.
3. The loader runs only bytes with that digest.

There is no new key and no new signature, and the OTA key signs nothing
more than it does now. The site, its hand-off, its mirror and the browser's
cache only carry the pack; the worst any of them can do is fail to deliver
it.

**What stays as it is:**

- The loader crosses plain HTTP from the board, so an active attacker on the
  LAN can serve a page of their choosing. `docs/os_2026-11/threat_model.md`
  records this for the page today.
- The device keys live in the origin's storage, readable by whatever later
  answers at that address. This is also true today.

What the cache must not add is an attack that lasts after the attacker
leaves, and verifying on every read prevents that. The link's listener is a
new surface, and §5 bounds it. The board's own install keeps its signed
index (`AddonStep`), untouched.

## 7. First setup over the cable: Improv

The C3 has no OTA, so its first image goes on by cable, and the flasher
already holds the port. Step 2 of flow 1 runs over that same port using
**Improv Wi-Fi's serial protocol**, the one ESP Web Tools and its users
know:

- The board reports its state, its device info ("Moybyte", the firmware's
  label, the chip, its name) and the networks it can see (0x02, 0x03,
  0x04), its network state (0x07), and takes a name (0x06; 0x05, the
  hostname, is the same mDNS label).
- It joins a network (0x01), saves it first in `wifi.json` and answers with
  its URL twice, by IP and by `.local`, each carrying the board's id after
  its `#`, and its claim while it has no password:
  `http://192.168.1.57/#id=<32 hex>&claim=<32 hex>`. The fragment never
  crosses the network. A board already on a network joins another the same
  way.
- Moybyte's own command 0xF0 answers the same URLs with a FRESH claim,
  minted whether or not the board has a password (Improv's spec reserves no
  range for a device's own commands; its own count up from 0x01, so this
  one sits at the top, and a client that never sends it never meets it).

Any Improv client, such as ESP Web Tools or Home Assistant's, can set a
Moybyte Zero up too: its "visit device" opens that URL, and the console
page there asks for the console's first password with the claim
(`page_tail.js`). If the address changes later, the site asks again over
the cable (Improv's current state carries the URL), which updates the
console by its id.

**The password.** Improv carries no board password, and typing one into the
first console that reaches the board would hand the board to whoever on the
LAN got there first. So:

1. Once the board answers a claim, the site asks for the console's
   password, and keeps it in memory only.
2. The URL Improv returns carries a **claim**: a random token the board makes
   while it has no password, or on 0xF0's request, and only ever sends over
   the cable. It keeps it in `system/claim` until it is taken, so a reboot
   does not end the link setup gave; a newer claim, a password set another
   way (`passwd`, which signs out) and, for a claim minted over a password,
   the next boot end it.
3. When the site opens the console's first window, it sends the claim and
   the password over the link (`claim`, §5) once the console asks to sign
   in.
4. The console in that window makes the SPAKE2+ record
   (`native/moy_net/moy_seal.h`, `moy_sw_claim`) and sends the board the
   record with the claim (`{"op": "claim"}`, on the board's live socket, or
   `POST /auth` on a board without one). The board takes
   it once and forgets the claim (`native/moy_net/moy_webauth.c`, THE
   CLAIM): a wrong claim counts with the sign-in's backoff, and a board with
   a password and no claim refuses every claim. A failed claim says why in
   the console's pairing prompt, its button live again (or over the link
   alone, to a console that runs signed in).

The password never crosses the network, and a copy of the record pairs no
browser (`firmware/seeed_xiao_esp32s3_zero/README.md`, "The sign-in gates
everything"). The browser that set the password pairs with it in the same
step.

**Manage by cable** (owner, 2026-11-24: "we should be able to set its
wifi/password anytime using my console serial"). Each card in My consoles
has "Manage by cable", and "Set up a board by cable" opens the same panel
for a board already on a network (`site/os/setup.js`, `manage`). Over the
port it offers:

- **Wi-Fi**: Improv's join, which a board on a network takes too; the card
  takes the address it answers. A card added by address becomes the
  board's, under its id.
- **Name**: Improv's name, the card's and the `.local` label.
- **Password**: 0xF0's fresh claim, then the claim path above: the console's
  window makes the record and the board takes it in place of the old one.
  Physical access over the cable is the owner's proof, the same trust as
  the first claim's, and the password crosses neither the cable nor the
  network. The new password signs every browser out, as `passwd` does
  (their keys are kept, so each signs in again), and this one pairs with
  it.
- **The board's log**, as in setup.

A board with no screen pairs only this way or by its password, so the
hello says so (`"cable": true`, which the Zeros' store host sets,
`moy_wa_cable`) and the pairing prompt names Manage by cable in place of
the QR's words. Reached without its claim while it has no password (a
hand-typed address, the `.local` name, a flash whose setup stopped short
of step 3 of flow 1), it says the console has no password yet, that no
browser can pair and SSH is off until one is set, and that Manage by cable
sets it (`firmware/web_runner/page_tail.js`, `NOPW`). Consoles with a screen run no Improv (its frame parser is built
where a board defines `MOY_IMPROV`, the Zeros alone) and set all three in
their own Settings.

**The fallback is the AP and its form** (`device/zero_setup.py`), unchanged:
for a phone that cannot speak Web Serial, a board that came pre-flashed, and
a board whose saved networks are gone. That board then goes into My consoles
by its address.

**In the firmware**, Improv belongs to the kernel: a frame parser on the
USB-Serial/JTAG console's receive path takes `IMPROV` frames and leaves
every other byte to the REPL, which stays the recovery console
(`native/moy_kernel/moy_improv.h`, routed by `tools/patch_usj_improv.py`
where a board defines `MOY_IMPROV`: both Zeros). An RPC's type byte is the
REPL's Ctrl-C, so no byte of a frame reaches the REPL; a header held for
its next byte goes back to the REPL once it is 30 ms stale. The store host
answers the frames from its loop (`device/zero_improv.py`), as it answers
the setup form: a join from the access point ends the access point and the
board serves from there without a reset, so the client waiting on the
cable hears its answer. board.toml's `[serial]` says how the flasher opens the port without
resetting the chip (the C3's lines idle HIGH), and the site's client keeps
that line state (`site/os/improv.js`).

**The board's log.** What a board prints on the cable besides Improv's
frames shows in the setup's "Board log" panel (`site/os/setup.js`): whole
lines, ANSI escapes stripped, the last 500, with a Copy button. The Wi-Fi
password, which the page knows, is blanked in every line it shows or
copies. Improv's errors say only that a join failed; the reason (Wi-Fi's
reason code, a weak antenna) is in the log, so the panel opens by itself
when setup stops.

**Consoles with a screen** set their Wi-Fi on glass, show their address in
Settings, and join My consoles when you type that address.

## 8. Versions: OTA, rollbacks, old images

- **After an OTA**, `/sync` names the new digest. The board's own copy, where
  it keeps one, may not be installed yet, but the hand-off or os.moybyte.com
  answers. A browser no longer sees "this console needs its page updated"; the
  loader just goes to its next source.
- **A rollback** names the previous digest, which the eviction rule keeps.
- **For offline use, the site keeps** the site itself and, in one cache
  (`site/os/packs.js`), the newest pack of the stable and the beta release
  (`packs.json`, which the service worker keeps at install) and the last
  pack each saved console's `hello` named, fetched the first time the site
  has none, each put there only when its body hashes to its name. A pack
  the loader refuses is dropped; any other is pruned. The pack of every
  image the site flashed joins them with phase 3.
- **An image older than the loader** serves its own add-on as it does now and
  never asks the site for anything. The pack store starts with the first
  loader image's digest.
- **The C3 has no OTA.** Its users run a stable image for a long time, so
  os.moybyte.com keeps every pack a stable release's image names. Beta's packs,
  one per web build a `dev` push publishes, are kept for 30 days (§12).
- **A worktree build** names a digest no site publishes, so its mirror is
  the developer's own (§4).

## 9. Browsers and phones

| | Web Serial (flash, Improv) | loader on `http://` | My consoles in a tab | installed My consoles opening the board |
|---|---|---|---|---|
| Chrome, Edge (desktop) | yes | yes | yes | a window with its opener |
| Chrome (Android) | since Chrome 148 (2026) | yes | yes | a Custom Tab; the opener is phase 2's question |
| Firefox | no (Nightly experiments only) | yes | yes | no installed web apps |
| Safari (iOS, iPadOS) | no | yes | yes | no: `window.open` returns null |
| Safari (macOS) | no | yes | yes | phase 2's question |

- **The installed app on a phone.** On iOS and iPadOS, `window.open` from a
  home-screen web app returns null. Pages outside its scope open in a Safari
  view whose storage is separate. On Android, a page outside an installed
  app's scope opens in a Custom Tab.

  So My consoles on a phone runs in a browser tab, and the tab's service
  worker still opens it offline. The installed app offers the board's
  address as a link, which is the other entry. Phase 2's test on real
  phones decides what the site offers on each platform.
- **iOS can never flash or run Improv** (no Web Serial, no Web Bluetooth). An
  iPhone-only owner uses the AP form, or a computer for the flash.
- **Safari's 7-day cap** deletes script-written storage of a site with no
  visit in seven days of Safari use. That covers both the board origin's
  cached pack and os.moybyte.com's service worker cache, so an iPhone away for
  a week fetches again.
- **iOS's captive-portal sheet** on the AP keeps no storage and opens no
  windows. It is for the setup form, never the console.
- **Android on a network without internet** may keep mobile data as its
  default route. `http://192.168.4.1` then answers only once the user tells
  it to stay on the Wi-Fi. That is already the AP form's caveat.
- **`.local` names** do not resolve everywhere, and Android's browsers are
  the usual gap. That is why the site keeps the address.
- **Chrome's HTTPS by default** ("Always Use Secure Connections", default
  for everyone since Chrome 154) does not warn on private addresses or
  single-label names. Phase 1's test settles whether it warns on `.local`.
- **Local Network Access** (Chrome 142 and later) prompts for fetches,
  subresources and subframes from a public page into the LAN. My consoles'
  window is a top-level navigation, and phase 2's test checks it opens
  without a prompt on the Chrome current then.
- **Private windows** keep IndexedDB in memory, so every visit fetches.
- **iOS runs a page from a plain-http address with no JIT** (measured on
  the owner's iPhone, 2026-11-26, Safari and Chrome alike; a window it opens
  and Add to Home Screen inherit it), so the loader on `http://` is slow
  there whatever the pack. A board whose image takes the secure door
  (`MOY_NET_HTTPS`; the C3 Zero) offers its page over https on demand: the
  loader's card "Make it faster on iPhone?" (iOS, or `?fast`, which also
  forgets a remembered answer: About's Fast console on iPhone row) asks
  `POST /tls` and goes to `https://<host>/`, where a self-signed certificate costs one
  warning per board (`native/moy_net/moy_net.h`, HTTPS on demand; the C3
  README says what differs). That origin is a third one: its pack cache
  and its pairing are its own, its loader fetches from https mirrors only
  (os.moybyte.com; a dev image needs an https mirror), and when the door
  closes the page says "The fast console closed" and links back to
  `http://<host>/`.

## 10. Two web modes, still

The rule stands, and its words get sharper: **the origin a page runs under
decides where its carts live**, not where its bytes came from.

- A console the loader boots runs on the board's origin. Its `GET /sync`
  probe finds the board, and it edits the board's store.
- The site never runs a board-mode console and never reaches a board's
  store. It hands bytes to a window on the board's origin, and in flow 3 it
  asks that window's console to act.
- The site's own player stays a static-host console on the browser's OPFS.
  That needs a secure context, which a board's origin never is.

No crossover is added. The rule in `.claude/rules/web.md` says "the origin
a page runs under", not "where it is served from".

**My consoles' source is `site/os/`**, built by `tools/os_site.py` into
`/console/` of the Pages site whose `/` and `/dev/` are the project site
(`site/build.py`), and wears that site's look: its stylesheet, top bar,
footer and scheme switch are `site/build.py`'s, taken from the tree that
builds it. It holds no console, no player and no carts, so it is in
neither web mode, and it shares the origin with the players without
sharing their storage: the players keep OPFS (the dev one under
`channel-dev/`), and register no service worker and open no cache; My
consoles keeps `moy.consoles` in `localStorage`, the `moy-packs` and
`moy-app-*` caches, and a service worker whose scope is `/console/`. The
scheme switch's `moybyte-site-scheme` is every page's. What the origin does share is the
browser's account of it: a `persist()` grant, an eviction, Safari's 7-day
cap and the quota cover the players' carts and My consoles' packs
together. A board-mode console only ever runs on a board's origin.

**No direct path from the site (owner, 2026-11-23).** On Chrome, Local
Network Access would let os.moybyte.com reach the board itself as a paired
browser, with no second window. It is dropped: only Chromium has it, and an
https page cannot open the console's `ws://` socket (#256), so it would be a
second, weaker way to a board beside the link every browser gets.

**Big boards keep their copy, and everything boots one way.** Phase 4 makes
the loader the only boot path, on every board, with the board's copy as one
of its sources. That keeps the one way a fresh browser starts a console on a
LAN without internet, and costs nothing the add-on machinery does not
already cost. Losing the room stops being an error a browser sees: a board
whose add-on does not fit records that once (`system/addon_room`, as now),
and its loader goes online. The add-on machinery stays (§12).

**Rejected:**

- *TLS on the board with a certificate per device.* It needs a backend to
  issue and renew certificates, and TLS serving in the C3's single internal
  heap.
- *A cloud relay* between the site and the board. It is a server to run, and
  it is dead offline.
- *The board as a proxy*, fetching the pack from the release while serving
  it. That means TLS and a serving connection in the C3's heap at once. A
  failure mid-stream reaches the browser as a broken script, and nothing
  works without internet.
- *A smaller console for small boards.* The browser draws what its boards
  draw (owner, 2026-10-20), so a reduced build is that divergence, and it
  would outgrow the store again.

## 11. Phases, and their tests

**Phases 1–3 deliver flows 1 and 2 and are the gate on the next release
(owner, 2026-11-23).**

**Phase 1: the loader.** The other entry works, and a C3 has a console.

- The loader page (`firmware/web_runner/loader.html`), built into every
  image; on a board whose console is online it is what `/` serves, and
  every board serves it at `/loader.html` (§3).
- A board that keeps its copy serves the pack whole (§4, source 3).
- `gen_web_blob` names the whole pack's digest, and `GET /sync` carries both
  digests and `local`.
- The page and the worker take the asset map (§3).
- os.moybyte.com's pack store, with its headers.
- The mirror list per build; `serve.py` serves a worktree's pack with CORS.
- Docs corrected in place:
  - `.claude/rules/web.md`: the add-on bullet, the static import, and the
    modes' wording
  - `native/moy_net/moy_page.h`'s header
  - both Zero READMEs
  - the threat model's webhost paragraph

Tests:

- A node test of the loader (`firmware/web_runner/loader_test.mjs`, in the
  harness's style, run by `tests/test_web_loader.py`): a wrong digest refused, a tampered head refused, a
  poisoned cache entry refused and fetched again, the source order, and
  eviction.
- The loader's gzipped size stays under its budget.
- On glass, a page load's frame stall on the C3, written to #256. A Zero
  draws no frames: its serving loop serves a request whole, so the stall is
  the time it takes to serve the loader and `/sync`
  (`tests/test_zero_on_glass.py` takes both, into the board's perf record).
- A host test that the digests `gen_web_blob` names are the pack's.
- A deploy check that every digest an index names has its file on
  os.moybyte.com, served with `Access-Control-Allow-Origin`.
- On glass: `tools/board.py pass c3_zero` builds, flashes and runs
  `tests/test_zero_on_glass.py`, whose headless Chrome (`browsershot.mjs`)
  boots the C3's console from a worktree mirror, signs in and syncs a cart.
- In Chrome with no board: serve.py's `--loader` twin boots the console
  through the loader, then from the cache (`tests/test_web_loader.py`,
  under `MOYBYTE_WEB_E2E`).
- The boot's cost goes to the issue: cached against store-served, and on
  `.local` against an IP.

**Phase 2: My consoles and the link.** The main entry works. Built on the
host; the real-device matrix below is the owner's to run.

- os.moybyte.com/console/, as files (`site/os/`, `tools/os_site.py build`):
  - My consoles (`consoles.js`): the saved names and addresses, kept in the
    site's `localStorage`, and open, rename and forget
  - a service worker (`sw.js`) that keeps the site and the packs of §8
    (`packs.js`)
  - the link's site end
- The link's board end, version 1 (§5): `hello`, `pack`, `state` in the
  loader (`loader.html`) and the console page (`page_tail.js`).

Tests:

- A two-origin headless test (`tests/test_web_link_e2e.py`, under
  `MOYBYTE_WEB_E2E`). The site is `tools/os_site.py serve` on `localhost`, a
  secure context; the board is the real C webhost with its sign-in (the
  terminal's host harness, naming this tree's pack) behind `serve.py --board
  --loader` on `http://127.0.0.1`, the site its one mirror. It checks that:
  - the hand-off boots the console with the network off: the site is
    stopped, My consoles opens from its service worker, and the loader
    boots from the link
  - a message from another origin is ignored: the same site at
    `127.0.0.1` opens the board, hears nothing, and gets no answer
  - wrong bytes are refused: the site's cached copy is spoiled, the
    loader answers `ok: false` and boots from its cache, and the site
    drops the copy
  - an unknown kind is answered as unknown
  - the console signs in by its password and syncs over the link's
    window: a cart it imports lands in the board's store
- `firmware/web_runner/loader_test.mjs` drives the loader's end in node:
  the hello reaches only the sites, a handed pack boots with nothing
  fetched, other bytes are refused and told, a site with none hands on at
  once, an unknown kind, a second pack, another origin and another window.
- `tests/test_os_site.py`: the `/console/` folder beside the rest of the
  site, the files its service worker keeps, the mirror the images name
  being that folder, and that it evaluates nothing a window sends.
- **On real devices, for the owner.** Each of desktop Chrome (a tab, and
  installed), Android Chrome (a tab, and installed from the menu) and an
  iPhone (Safari, and added to the home screen), against a deployed site
  and a C3 Zero on the LAN:
  1. My consoles opens; add the console by its IP, and again by
     `<name>.local`. Which name resolves?
  2. Online, tap it: does a window open on `http://<address>/`, without a
     Local Network Access prompt (Chrome: note the version)? Does the
     console boot, and does the list say "handed it its console" (the
     hand-off taken), then "asks for its password" and, after it, "signed
     in" (the link's `state` reached the site)?
  3. Tap it again while its window is open: brought forward, not
     reloaded?
  4. Offline: the LAN with no internet (the router's uplink unplugged; on
     a phone, mobile data off). Does My consoles open, and does a tap boot
     the console with "handed it its console"?
  5. Installed: does a tap open a window that keeps its opener (the states
     in step 2 appear), or does the list offer the address as a link
     (`window.open` returned null)? Where a link: does following it boot
     the console, and from which source?
  6. Rename and forget, then reload: the list is as left.
  7. Seven days without a visit on the iPhone (§9, Safari's cap), then
     offline: what is left?

  Depends on its outcome: §9's last column and what My consoles offers in
  an installed app on each platform (today: a window where `window.open`
  gives one, else the address as a link); whether My consoles opens the
  IP or `.local` (it saves both and opens the IP, §2); and the loader's 4 s
  wait for an opener, if a phone's site answers slower.

**Hosting: GitHub Pages** (owner, 2026-11-24). `pages.yml` fetches
firmware-latest and firmware-beta (`tools/pack_store.py fetch`), runs
`tools/os_site.py build _site`, and deploys `/console/` with the rest of the
site; `tools/pack_store.py check https://os.moybyte.com` with both
releases' indexes says whether the deploy holds every pack they name, and
`tools/os_site.py serve` serves a built site on `localhost` as Pages
serves it. What Pages sets for us:

- every file `max-age=600`: the loader's cache is by digest, and the
  service worker fetches its own files with `cache: "reload"`, so a new
  worker is never built from stale ones;
- no response headers of ours, so My consoles' content security policy is
  a `<meta>` tag, which cannot carry `frame-ancestors`;
- a published site of about 1 GB and about 100 GB a month of traffic,
  which the project site, both players and the packs share. The store
  keeps every stable pack for good and 30 days of beta packs, each the
  size of the add-on, and the workflow prints `/console/`'s size and the
  whole site's at every deploy.

**Phase 3: first setup by cable.** Built on the host and on the XIAO Zero;
the real-device checklist below is the owner's to run.

- Improv serial in the kernel (`native/moy_kernel/moy_improv.h`, both
  Zeros), answered by the store host (`device/zero_improv.py`), on its
  access point and while it serves (§7).
- The flasher (os.moybyte.com's `/`, `site/flash.js`) runs Improv after
  the flash on a board that answers it (`site/build.py`'s
  `improv_boards`), saves the console into My consoles and offers to open
  it; My consoles runs the same setup for a board already flashed. One
  client and one form for both (`site/os/improv.js`, `setup.js`), one list
  (`kept.js`) and one link end (`link.js`). The project site's navigation
  links My consoles.
- The claim and the browser-made record (`moy_webauth.c`, THE CLAIM;
  `docs/os_2026-11/system.md` §3).
- My consoles saves what Improv reported, keyed by the board's id, and
  adds a console by hand by its address, verified by its first open (§2).

Tests:

- The frame parser in a host harness (`tests/test_improv.py`): every
  command, a frame split at every point and byte by byte, REPL bytes passed
  through untouched and in order, a held header given back when stale, a
  frame cut short dropped, a bad checksum handed on.
- The board's answers through that parser (`tests/test_zero_improv.py`):
  each command, a join while serving and from the access point (answered
  once the board serves), a network that does not answer, the name and
  hostname, bad frames; the setup loop handing a join to the serving board
  with no reset.
- The claim refused twice, refused without the token, and refused once a
  password exists, a wrong one counted by the backoff, and the browser's
  claim pairing in the same step (`tests/test_web_signin.py`); the worker's
  end in node (`signin_test.mjs`).
- A node test of the site's Improv client against a scripted port, of the
  board's log as lines with the Wi-Fi password blanked, and of the
  addresses a person may type (`site/os/improv_test.mjs`).
- In Chrome (`tests/test_web_setup_e2e.py`, under `MOYBYTE_WEB_E2E`), Web
  Serial a stand-in in the page: added by hand, a bad address refused, a
  duplicate updated, an unreached one said so; set up by cable, saved
  under the board's id, opened, the password taken by the real webhost's
  claim, signed in, and the list showing it reached; a join the board
  refuses opening the Board log on the board's lines, the Wi-Fi password
  on neither the page nor what Copy copies.
- On the XIAO Zero over its USB serial (2026-11-24, a script): the state,
  info, scan, name, a join from the access point and the claim taken over
  HTTP, timed.
- ESP Web Tools sets up a C3 (checklist below).
- **On real devices, for the owner**, a C3 or a XIAO Zero, a desktop
  Chrome and a phone, against a deployed site:
  1. Flash from os.moybyte.com's card: does "Connect it to Wi-Fi" appear,
     answer within its wait (a fresh store seeds first), and list the
     networks?
  2. Name it and join: does it say where it is (by IP and `.local`), ask
     for a password, and save the console in My consoles under that name?
  3. "Open <name>": does the window boot, say "setting its password..."
     then "signed in", without typing anything in the console's window?
  4. Reload My consoles: the console shows "reached" and its console's
     digest; open it again from there: signed in by its key?
  5. My consoles' "Set up a board by cable" on a board already flashed:
     the same, and a second run moves its entry, not a second entry?
  6. ESP Web Tools (or Home Assistant) sets the board up: does "Visit
     device" open a console that asks to choose its password?
  7. Add by address on a phone: the IP, then `<name>.local`, then
     `http://<ip>:80`, with and without a name. Is a duplicate updated,
     and does the first tap mark it reached (or "not reached yet" with
     the address as a link where nothing answers)? Which name resolves?

**Phase 4: one boot path.**

- Every board's root serves the loader.
- The per-asset routes and the "needs its page updated" page go.

Tests:

- The loader suite against a board serving its own copy: the local source
  is used and no site is reached.
- The web parity and sync suites on a T-Deck and a P4, through the loader.
- A board after an OTA boots its console before `AddonStep` has run.

**Phase 5: managing from the website (flow 3).** The link kinds and the
per-site consent (§5): backup and restore, moving carts, installing a store
cart, the C3's cable update with a backup first, and editing on the PC.

Tests:

- Each kind in the two-origin test.
- A backup restored onto a wiped board, byte for byte.
- A store cart whose bytes the site altered is refused by the board.
- A kind refused before the consent.

**Phase 6: the field mode.** A board serves the loader on its own access
point (§12), and My consoles opens it at the access point's address.

Tests: a C3 on its access point booting the console a phone's offline
My consoles hands it, and a T-Deck booting its own copy there; the
phones' "no internet" handling of that network, on Android and iPhone.

## 12. The owner's answers (2026-11-23)

1. **Boards with room keep the add-on** as one source of the pack (§4). It is
   the one way a browser that never saw os.moybyte.com starts a console on a
   LAN with no internet.
2. **A board serves the console on its own access point**, a field mode
   with no router (phase 6). A C3 needs no copy for it: a phone that has
   opened os.moybyte.com before hands its cached pack to the board's window,
   and a board with room serves its own.
3. **os.moybyte.com keeps every stable pack and the `dev` packs of the last
   30 days.** A `dev` board older than that updates its firmware, or boots
   its own copy where it keeps one.
