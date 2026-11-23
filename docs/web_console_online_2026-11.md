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
  sha256 alone (`moy_web_want`, `native/moy_web/moy_web_blob.h`).
  The webhost serves a pack only when its head names that digest, from
  `/p/<12 hex>/`, its assets `immutable`; `/` is a 302 there, or the sentence
  saying why there is none (`page_root`, `native/moy_net/moy_webhost.c`).
- **The release publishes every add-on ever made** as
  `moybyte_web-<digest>.moy.zip` beside the payload, listed in the board's
  signed carts index (`tools/web_pack.py`). A board installs the one that
  fits through the ordinary install, every file checked against the signed
  index (`runtime/carts/web_addon.py`'s `AddonStep`; on a Zero
  `device/zero_host.py`). Those assets are GitHub release downloads, which
  carry no CORS header, so no page can fetch them.
- **The project site** (`site/build.py`, `.github/workflows/pages.yml`) is
  GitHub Pages. It hosts the site's own player (a `--site` build,
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

**Flow 1: first setup, once.**

1. On os.moybyte.com, "Get a console": plug the board in by USB and press
   Install. The site flashes it from the browser.
2. Over the same cable, pick the Wi-Fi, type its password, and name the
   console (`kitchen`). This is Improv (§7).
3. The board joins the network and reports its address over the cable. The
   site saves the name and the address under **My consoles**.
4. Without Web Serial (an iPhone), flash from a computer, or use the board's
   setup hotspot and its form.

*Note:* the flow as decided sets no password for the board, and a board
with no password pairs no browser. §7 puts the password in step 2's form and
explains how it reaches the board without crossing the network.

**Flow 2: every day.**

- **The main entry is My consoles on os.moybyte.com** (owner, 2026-11-23),
  which opens offline once its service worker has cached it. Tap `kitchen`:
  a window opens on the board's origin (the loader, §3), and the site hands
  it the console's bytes by `postMessage` (the link, §5). The console runs
  on the board's origin, so the carts live on the board.
- **The other entry** is typing `http://kitchen.local` or the IP. The loader
  gets the pack from its own cache (IndexedDB), from os.moybyte.com, or from the
  board's own copy on a board that keeps one (§4).
- The site keeps the address it learned, because `.local` does not resolve
  on some Android phones.

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
the build to anybody who asks for `/`.

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
rest.

## 4. Where the bytes come from

The loader tries these in order and runs only bytes whose digest matches:

1. **The site's hand-off**, when the window was opened by My consoles (§5).
2. **IndexedDB** on this origin.
3. **The board's own copy**, on a board whose store or card has room for it
   (`[web] console` unset: the add-on as today, `AddonStep` and all). It is
   served whole as one asset and checked like the rest. It is the only way
   a browser that never saw the site starts a console on a LAN without
   internet.
4. **os.moybyte.com by CORS**, at `/console/<body digest>.pack`: the pack file
   as the add-on cart holds it. An `http://` page may fetch `https://`;
   mixed content only blocks the other way. Chrome's Local Network Access
   only gates a request from a less private address to a more private one,
   never a LAN page reaching the internet. A worktree build's list names the
   developer's own `firmware/web_runner/serve.py`, served with CORS, so
   `tools/board.py` and `tools/web.py shot` reach a C3 whose digest no site
   publishes.

What a pack passed through decides nothing: the digest does. A LAN mirror
can be added without touching the trust model.

**The packs live on os.moybyte.com** (owner, 2026-11-23), where we set the
headers: `Access-Control-Allow-Origin: *`, and `immutable` on a name that is
a digest. Its deploy publishes every pack named by an add-on in the two
rolling releases' indexes, taken from the same assets the boards install
from.

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
nothing:

```
{moylink: 1, id, kind, ...}     a request; its reply carries the same id
hello   board -> site   the board id, the name, the digests /sync gave, the link kinds it serves
pack    site -> board   the pack's bytes (a transferred ArrayBuffer)
claim   site -> board   the claim token and the new password, once (§7)
state   board -> site   booted / signed in / failed, with the sentence the page shows
```

**Both ends check the origin.** The board's end takes messages only from the
site's origin, which the image names. The site's end takes them only from
the origin it opened. Neither end ever evaluates a message. A `pack` is bytes
the loader checks like any source's.

**The board's end is the console page.** The loader answers `hello`/`pack`
before the boot. After the boot, the console page (`page_tail.js`) holds the
link, because `document.open` erased the loader's listener. Every request
that touches the store goes through the console in that window: it runs in
the VM like every rule (`.claude/rules/web.md`), and it travels over the
sync RPC the page already uses. The site never reaches the board itself.

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
as today. An https page cannot open `ws://`, so the site's window, and the
direct path of §10, never carry the socket; the link carries what the site
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

- The board reports its state, its device info and the networks it can see.
- It takes the network and the console's name (Improv's RPC 0x01, 0x03,
  0x04, 0x06).
- It joins the network and answers with the URL to open, which carries the
  address for My consoles.

Any Improv client, such as ESP Web Tools or Home Assistant's, can set a
Moybyte Zero up too. If the address changes later, the site asks again over
the cable (Improv's current state carries the URL), or learns the new
address from `kitchen.local` where that resolves.

**The password.** Improv carries no board password, and typing one into the
first console that reaches the board would hand the board to whoever on the
LAN got there first. So:

1. Step 2's form also asks for the console's password, and the site keeps it
   in memory only.
2. The URL Improv returns carries a **claim**: a random token the board makes
   at a boot with no password, holds in RAM, and only ever sends over the
   cable.
3. When the site opens the console's first window, it sends the claim and
   the password over the link.
4. The console in that window makes the SPAKE2+ record
   (`native/moy_net/moy_seal.h`) and sends the board the record with the
   claim. The board takes it once and forgets the claim.

The password never crosses the network, and a copy of the record pairs no
browser (`firmware/seeed_xiao_esp32s3_zero/README.md`, "The sign-in gates
everything"). The browser that set the password pairs with it in the same
step.

**The fallback is the AP and its form** (`device/zero_setup.py`), unchanged:
for a phone that cannot speak Web Serial, a board that came pre-flashed, and
a board whose saved networks are gone. That board then goes into My consoles
by its address.

**In the firmware**, Improv belongs to the kernel: a frame parser on the
USB-Serial/JTAG console's receive path takes `IMPROV` frames and leaves
every other byte to the REPL, which stays the recovery console. board.toml's
`[serial]` says how the flasher opens the port without resetting the chip
(the C3's lines idle HIGH).

**Consoles with a screen** set their Wi-Fi on glass, show their address in
Settings, and join My consoles when you type that address.

## 8. Versions: OTA, rollbacks, old images

- **After an OTA**, `/sync` names the new digest. The board's own copy, where
  it keeps one, may not be installed yet, but the hand-off or os.moybyte.com
  answers. A browser no longer sees "this console needs its page updated"; the
  loader just goes to its next source.
- **A rollback** names the previous digest, which the eviction rule keeps.
- **For offline use, the site keeps** in its service worker's cache the pack
  of every image it flashed and the last digest each saved console
  reported, plus the newest stable and beta packs.
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

No crossover is added. Phase 1 rewrites the rule's "serving host" in
`.claude/rules/web.md` as "the origin it runs under".

**Local Network Access is an optional extra path**, never a requirement. On
Chrome, with the user's permission, the site could reach the board directly
(`fetch` with `targetAddressSpace: "local"`) as a paired browser of its own,
with its own key, and do flow 3's work with no second window. It would never
run the console against the board, so the mode rule is untouched. Only
Chromium has it, so the link stays the path every browser gets.

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

- The loader page (`+firmware/web_runner/loader.html`), built into every
  image; on a board whose console is online it is what `/` serves.
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

- A node test of the loader (`+firmware/web_runner/loader_test.mjs`, in the
  harness's style): a wrong digest refused, a tampered head refused, a
  poisoned cache entry refused and fetched again, the source order, and
  eviction.
- The loader's gzipped size stays under its budget.
- On glass, a page load's frame stall on the C3, written to #256.
- A host test that the digests `gen_web_blob` names are the pack's.
- A deploy check that every digest an index names has its file on
  os.moybyte.com, served with `Access-Control-Allow-Origin`.
- On glass: `tools/board.py pass c3_zero`, then a headless Chrome
  (`browsershot.mjs`) that boots the C3's console from a worktree mirror,
  signs in and syncs a cart.
- The boot's cost goes to the issue: cached against store-served, and on
  `.local` against an IP.

**Phase 2: My consoles and the link.** The main entry works.

- os.moybyte.com gains:
  - My consoles: the saved names and addresses, and open, rename and forget
  - a service worker that keeps the site and the packs of §8
  - the link's site end
- The link's board end, in the loader and the console page, version 1:
  `hello`, `pack`, `state`.

Tests:

- A two-origin headless test. The site runs on `localhost`, a secure
  context; the board is `serve.py`'s board twin on `http://127.0.0.1`. It
  checks that:
  - the hand-off boots the console with the network off
  - a message from another origin is ignored
  - wrong bytes are refused
  - an unknown kind is answered as unknown
  - the console signs in and syncs over the link's window
- On real devices, both entries, offline and online: desktop Chrome in a
  tab and installed; Android Chrome in a tab and installed; an iPhone in
  Safari and from the home screen. This matrix decides what the site offers
  on each platform (§9).

**Phase 3: first setup by cable.**

- Improv serial in the kernel.
- The flasher moves to os.moybyte.com and runs Improv after the flash.
- The claim and the browser-made record (`docs/os_2026-11/system.md` §3
  gains it).
- My consoles saves what Improv reported.

Tests:

- The frame parser in a host harness: every command, a frame split across
  reads, and REPL bytes passed through untouched.
- The claim refused twice, refused without the token, and refused once a
  password exists.
- A node test of the flasher's Improv step against a scripted port.
- ESP Web Tools sets up a C3.
- On the bench: a Chrome flash of a C3 that ends in a signed-in console
  opened from My consoles.

**Phase 4: one boot path.**

- Every board's root serves the loader.
- A board that keeps its copy serves the pack whole.
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

**Phase 6, optional: the direct path.** Local Network Access on Chromium
(§10).

Tests: its prompt and its refusal, and the link still used where the
permission is denied.

**Phase 7: the field mode.** A board serves the loader on its own access
point (§12), and My consoles opens it at the access point's address.

Tests: a C3 on its access point booting the console a phone's offline
My consoles hands it, and a T-Deck booting its own copy there; the
phones' "no internet" handling of that network, on Android and iPhone.

## 12. The owner's answers (2026-11-23)

1. **Boards with room keep the add-on** as one source of the pack (§4). It is
   the one way a browser that never saw os.moybyte.com starts a console on a
   LAN with no internet.
2. **A board serves the console on its own access point**, a field mode
   with no router (phase 7). A C3 needs no copy for it: a phone that has
   opened os.moybyte.com before hands its cached pack to the board's window,
   and a board with room serves its own.
3. **os.moybyte.com keeps every stable pack and the `dev` packs of the last
   30 days.** A `dev` board older than that updates its firmware, or boots
   its own copy where it keeps one.
