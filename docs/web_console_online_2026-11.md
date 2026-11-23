# The browser console, online (2026-11)

How a browser gets the console for a board whose storage cannot hold it.
A design: §1 is what IS, the rest is PROPOSED unless it carries an owner's
date. The decisions it rests on are the owner's and are dated where they are
recorded; the questions still open are §11.

## 0. Why

The browser console is the wasm build of the whole console
(`firmware/web_runner/`), packed as `moybyte_web.pack` and installed into a
board's store as an add-on cart (`native/moy_net/moy_page.h`). Its size is
the store's to pay, and `tools/store_image.py --check` prints, per board,
what the add-on leaves of its store. Three boards lose that race now: the
ESP32-C3 Zero, whose browser console is its only face (the add-on outgrew
its store), and the two P4s whose internal store holds the add-on but not
their first boot's carts beside it when no card is fitted (the Guition P4,
the Elecrow with an empty TF slot). The S3 consoles are next in line, and
the pack only grows.

**Owner, 2026-11-23:** the C3's console is online: its board.toml says
`[web] console = "online"`, so neither the website's install
(`tools/store_image.py`) nor the cable flash (`tools/board_flash.py`) puts
an add-on in its store. The C3 may sit on `dev` like that, with no browser
console, but the online console lands before the next release (§10, the
gate on phase 1).

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
- **The website** (`site/build.py`, `.github/workflows/pages.yml`) is
  GitHub Pages, which answers `Access-Control-Allow-Origin: *`. It hosts the
  site's own player (a `--site` build, `dist_site`, which is not the boards'
  pack), and the flasher (`site/flash.js`, esptool-js over Web Serial), which
  writes each board's install: the merged image and a store holding the
  add-on that fits (none on an online board).
- **Two web modes, no crossover** (`.claude/rules/web.md`): a page's
  serving host decides where its carts live. The page decides once at boot,
  by probing `GET /sync` on its own origin, before the VFS is seeded.
- **The Zero's setup** is its own open access point and a form on it
  (`device/zero_setup.py`): the network, the board's name and its password.
  The access point serves that form only; a board serves the console or
  hosts the AP, never both. A browser then pairs with the password and keeps
  its device key in the board origin's `localStorage` (`page_tail.js`).

## 2. The shape

Every board serves a **loader**, a page of a few KB, at `/`. The console's
bytes come from wherever they can be had, and the loader runs them only once
their digest matches the one the board's image names:

```
GET /            the loader (in the image)
GET /sync        {"sync":1, "page": <body digest>, "pack": <pack digest>, "local": 0|1}
  1. IndexedDB (this origin)          key = pack digest; verified on every read
  2. the board's own copy             GET /p/<12 hex>/moybyte_web.pack, where "local"
  3. a mirror, by CORS                <site>/console/<body digest>.pack
  4. the relay                        the site's page, offline, hands the bytes by postMessage
  -> sha256 == the pack digest? -> store in IndexedDB -> boot from the bytes
```

The digest is the authority and the sources are not: none of them is
trusted, so any of them can be added (a LAN mirror, a developer's tree)
without touching the trust model.

## 3. The loader

**It is in the image**, gzipped, served `no-cache`. A budget of 4 KiB
gzipped is held by a test, and its cost shows in the image ledger
(`docs/perf/image.md`) like any part's. It is the only page a board's root
serves; the console's page is inside the pack.

**What it reads from the board:** `GET /sync`, already the unsealed mode
marker, grows the digests and whether the board serves a copy of its own.
That reveals nothing new: the page's `/p/<12 hex>/` address already names
the build to anybody who asks for `/`.

**What a board-served origin denies it.** The board is plain `http://`, so
the loader runs in an insecure context: no service worker, no Cache API, no
`crypto.subtle`, no `navigator.storage` (so no `persist()`). What it has is
IndexedDB, `fetch`, `DecompressionStream`, Blob URLs, module workers and
`postMessage`, none of them limited to secure contexts. So:

- the sha256 is the loader's own JavaScript, a small one (the console's wasm
  cannot check the bytes it arrives in);
- the cache is best-effort storage the browser may evict under pressure, a
  miss falling through to the next source;
- **an origin is an address.** `http://192.168.1.57` and
  `http://zero.local` are two origins with two caches, a board that moves
  address starts empty there, and every Zero on its own AP is
  `http://192.168.4.1`. Keys are digests, so boards that share an address
  share a cache harmlessly, and a new address costs one fetch.

**Verify on every read, not only on write.** Another device that later
answers at the same address (DHCP hands it out again, a different board's
AP) can write that origin's IndexedDB; a loader that trusted its cache would
run what it left there under the next genuine board's name. Hashing the
cached pack at each boot costs a JS sha256 over the pack, a cost phase 1
measures and records in its issue.

**The digest covers the whole pack.** The image names the body's digest
(the head carries it, so it cannot cover itself), and the head's entries say
which bytes are which asset. The loader runs those bytes, so the image also
names the sha256 of the whole file, head included (`gen_web_blob`'s
generated C), and `/sync` carries both: the body digest stays the pack's
identity everywhere it is one today (the add-on cart's id, the release
asset's name, the site's file name), the whole-file one is what the loader
checks.

**Booting from bytes.** The pack's assets are pre-gzipped; the loader
inflates each (`DecompressionStream`), makes a Blob URL per asset and hands
the page an asset map. That is the one change the console takes: today the
page starts `worker.js` by a relative URL and the worker imports
`micropython.mjs` and `moy_store.mjs` statically, which a Blob URL cannot
resolve. Proposed: the page creates its worker from `asset("worker.js")`,
the worker takes the map in its first message and imports its two modules
and the wasm's URL (`loadMicroPython`'s `url`) through it, and the relative
names are the default where no loader ran (the site's player, `serve.py`).
The loader writes the pack's `index.html` into its own document
(`document.open`/`write`), its own state in a closure, so the page runs
under the board's origin and its `fetch("/sync")` reaches the board.

**What the cached boot gives up:** the HTTP cache's compiled-code cache. A
wasm served `immutable` from the board compiles once and is cached compiled;
one built from bytes compiles at each boot. Phase 1 measures the boot both
ways on a phone and a PC; if the difference shows, the loader keeps the
inflated wasm as a Blob it serves through `WebAssembly.compileStreaming` of a
`Response`, and the measurement says whether that helps.

**Eviction.** After a boot, the loader keeps the pack it booted and the one
before it (a rollback names the previous image's digest) and deletes the
rest.

## 4. Sources

**The board's own copy** stays on boards whose store (or card) has room for
it (`[web] console` unset: the add-on as today, `AddonStep` and all). It is
served whole, as one asset, and goes through the same check. It is what
makes the console start on a LAN with no internet for a browser that never
saw the site.

**A mirror by CORS.** `<site>/console/<body digest>.pack`, the pack file as
the add-on cart holds it. An `http://` page may fetch `https://` (mixed
content only stops the other way), and Chrome's Local Network Access only
gates a request from a less private address to a more private one, never a
LAN page reaching the internet. The mirror list is baked per build: the
project site for a CI build, and for a worktree build
`firmware/web_runner/serve.py` on the developer's machine (with CORS), so
`tools/board.py` and `tools/web.py shot` reach a C3 whose digest no site
publishes. The digest check makes a mirror's honesty irrelevant.

**The relay.** The site, an https PWA whose service worker keeps the site
and the packs it has handed out, opens the board's loader in a window
(`window.open("http://<board>/?relay")`) and answers its request: the loader
posts `{want: <pack digest>}` to its opener, accepts a reply only from the
site's origin, and only bytes, which it checks like any other. It also runs
the other way, the loader opening the site's relay page when its other
sources failed. The bytes cross by `postMessage` with the buffer
transferred: an https page cannot fetch an `http://` LAN address itself
(mixed content, and Local Network Access in Chrome), but a window on the
board's origin can, and windows talk across origins.

The relay is narrower than it looks: it is needed only when the browsing
device has no internet now, had it when the site last cached the digest, and
this address's cache has no copy. A phone on a network without internet
often still has its mobile data, and then the mirror answers directly.
Where it matters: an offline LAN (a classroom) with a new device or a new
address, and a console served on the board's own access point, which no
board does today (§11).

**Rejected:**

- *The console on the site, talking to the board.* An https page cannot
  reach `http://` LAN addresses but through Chrome's Local Network Access
  (`targetAddressSpace: "local"`, a permission prompt), which no other
  engine has, and it is the crossover the two modes forbid: the site's page
  would edit a board's store.
- *The board as a proxy*, fetching the pack from the release while it
  serves it. No storage needed, but TLS and a serving connection in the
  C3's one internal heap at once, a failure mid-stream the browser sees as a
  broken script, and nothing at all without internet.
- *A smaller console for small boards.* The browser draws what its boards
  draw (owner, 2026-10-20); a reduced build is that divergence, and it would
  outgrow the store again.

## 5. Integrity, signing, provenance

The chain is the image's: a release's manifest is signed with the OTA key
and names the image's sha256 (`device/moy_ota.py`), or the owner put the
image on by cable; the image names the pack's digest; the loader runs only
bytes with that digest. No new key, no new signature, and the OTA key signs
nothing more than it does now. The mirror, the relay, the site and the
browser's cache are carriers, and every one of them can only fail to deliver.

What does not change: the loader itself crosses plain HTTP from the board,
so an active attacker on the LAN can serve a page of their choosing, as
`docs/os_2026-11/threat_model.md` records for the page today; and the device
keys live in the origin's storage, readable by whatever later answers at
that address, as today. What the cache must not add is persistence of such
an attack past the attacker's presence, which verify-on-read prevents.

The relay's listener is a new surface: it checks `event.origin` against the
site the image names, takes only an `ArrayBuffer`, never evaluates a
message, and the digest decides. The board-side install keeps its signed
index (`AddonStep`), untouched.

## 6. Versions: OTA, rollbacks, old images

- **After an OTA** `/sync` names the new digest, the cache misses, the
  board's copy (where kept) may not be installed yet, and the mirror answers.
  "This console needs its page updated" stops being something a browser
  sees: the loader goes to its next source.
- **A rollback** names the previous digest, which the eviction rule keeps.
- **An image older than the loader** serves its add-on as it does now and
  never asks the site for anything; the pack store starts with the first
  loader image's digest.
- **The C3 has no OTA**: its images go on by cable from the site, so its
  users run stable images for a long time, and the site keeps every digest
  a stable release's image names. Beta's packs, one per web build a `dev`
  push publishes, need a window (§11).
- **A worktree build** names a digest no site publishes; its mirror is the
  developer's (§4).

## 7. First boot and Wi-Fi: Improv over the cable

A C3 starts life on a cable: it has no OTA, so it is flashed from the site
(Web Serial) or by `make`. The site's flasher holds the port already, so
the Wi-Fi step is the next thing it does, over the same port, by **Improv
Wi-Fi's serial protocol**, the one ESP Web Tools and its users know: the
board reports its state, its device info and its scan list, takes the
network and its device name (Improv's RPC 0x01, 0x03, 0x04, 0x06), joins,
and answers with the URL to open. Any Improv client (ESP Web Tools, Home
Assistant's) can provision a Moybyte Zero too.

What Improv does not carry is the board's password, and a board with no
password pairs no browser. Typing it into the first console that reaches
the board would hand the board to whoever on the LAN got there first. So
the URL Improv returns carries a **claim**: a random token the board makes
at a boot with no password, holds in RAM, and says only over the cable. The
console the URL opens asks for the new password, makes the record in the
browser (the SPAKE2+ record the board stores, `native/moy_net/moy_seal.h`),
and sends the record with the claim; the board takes it once and forgets
the claim. The password never crosses the network, and a record is no
credential (`firmware/seeed_xiao_esp32s3_zero/README.md`, "The sign-in
gates everything").

**The fallback stays the AP and its form** (`device/zero_setup.py`), for a
board that came pre-flashed, a phone that cannot speak Web Serial, and a
board whose saved networks are gone.

**In the firmware**, Improv is the kernel's: a frame parser on the
USB-Serial/JTAG console's receive path that takes `IMPROV` frames and leaves
every other byte to the REPL, which stays the recovery console. How the
flasher opens the port without resetting the chip is board.toml's `[serial]`
(the C3's lines idle HIGH).

## 8. Browsers

| | Web Serial (flash, Improv) | the loader on `http://` | the relay (https PWA) |
|---|---|---|---|
| Chrome, Edge (desktop) | yes | yes | yes |
| Chrome (Android) | since Chrome 148 (2026) | yes | yes |
| Firefox | no (Nightly experiments only) | yes | yes |
| Safari (macOS, iOS, iPadOS) | no | yes | yes |

- **iOS can never flash or Improv** (no Web Serial, no Web Bluetooth): an
  iPhone-only owner gets the AP form, and a computer for the flash.
- **Safari's 7-day cap** deletes script-written storage of a site not
  interacted with in seven days of Safari use: an iPhone that has not opened
  its board in a week fetches the pack again. A home-screen web app is exempt
  but has storage of its own (one more copy, fetched once).
- **iOS's captive-portal sheet** on the AP keeps no storage and opens no
  windows: it is for the setup form, never the console.
- **Android on a network without internet** may keep mobile data as its
  default route, so `http://192.168.4.1` is reached only once the user tells
  it to stay on the Wi-Fi; that is the AP form's caveat today, unchanged.
- **`.local` names** do not resolve everywhere (Android's browsers are the
  usual gap); the site remembers the address Improv's URL carried.
- **Private windows** keep IndexedDB in memory: every visit fetches.
- **Local Network Access** (Chrome 142 and later) prompts for fetches,
  subresources and subframes from a public page into the LAN. The relay's
  window is a top-level navigation; phase 4's test is what says Chrome lets
  it through without a prompt, on the version current then.

## 9. Two web modes, still

The rule stands and its words get sharper: **the origin a page runs under
decides where its carts live**, not where its bytes came from. A console the
loader boots runs on the board's origin, its `GET /sync` probe finds the
board, and it edits the board's store. The site never runs a board-mode
console and never reaches a board's store: it hands bytes to a window on the
board's origin, which checks them. The site's own player stays a static-host
console on the browser's OPFS (and needs a secure context for it, which a
board's origin never is). No crossover is added; phase 1 rewrites the rule's
"served from" in `.claude/rules/web.md` to "runs under".

**Big boards keep their copy, and everything boots one way.** One boot
path, the loader, on every board (phase 3), with the board's copy one
source among four: that keeps the one way a fresh browser starts a console
on a LAN without internet, which only a local copy gives, and costs nothing
the add-on machinery does not already cost. What changes is that losing the
room is no longer an error a browser sees: a board whose add-on does not fit
records it once (`system/addon_room`, as now) and its loader goes online.
Whether the add-on machinery is worth keeping at all is §11's first
question.

## 10. Phases, and their tests

**Phase 1 — the loader, online, on the online boards. The gate on the next
release (owner, 2026-11-23).**

- The loader page (`+firmware/web_runner/loader.html`), built into every
  image beside the digest; served at `/` on a board whose console is online.
- `gen_web_blob` names the whole pack's digest; `GET /sync` carries both
  digests and `local`.
- The page and the worker take the asset map (§3); `worker.js` imports its
  modules through it.
- The pack store on the site: `site/build.py` publishes
  `console/<body digest>.pack` for every add-on the two rolling releases'
  indexes name, from the same assets boards install from.
- The mirror list per build; `serve.py` serves a worktree's pack with CORS.
- Docs corrected in place: `.claude/rules/web.md` (the add-on bullet, the
  static import, the modes' wording), `native/moy_net/moy_page.h`'s header,
  the C3's README, the Zero's README ("what stays open"), the threat model's
  webhost paragraph.

Tests: a node test of the loader (`+firmware/web_runner/loader_test.mjs`,
the harness's style): a wrong digest refused, a tampered head refused, a
poisoned cache entry refused and fetched again, the source order, eviction;
the loader's gzipped size under its budget; a host test that the digests
`gen_web_blob` names are the pack's; `tests/test_site_channel.py`'s kin
holding that every digest an index names has its file on the site; a smoke
after the Pages deploy that a pack answers with `Access-Control-Allow-Origin`;
on glass, `tools/board.py pass c3_zero` and a headless Chrome
(`browsershot.mjs`) booting the C3's console from a worktree mirror, signing
in and syncing a cart. Its boot cost against a store-served board's goes to
the issue.

**Phase 2 — Wi-Fi by cable.** Improv serial in the kernel; the site's
flasher runs it after the flash and opens the URL; the claim and the
browser-made record (`docs/os_2026-11/system.md` §3 gains it). Tests: the
frame parser in a host harness (every command, a frame split across reads,
REPL bytes passed through untouched); the claim refused twice, refused
without the token, refused once a password exists; a node test of the
flasher's Improv step against a scripted port; on glass, the bench
checklist's Chrome flash of a C3 ending in a signed-in console.

**Phase 3 — one boot path.** Every board's root serves the loader; a board
with its copy serves the pack whole and the per-asset routes and the
"needs its page updated" page go. Tests: the loader suite against a
store-served board (the local source first, no site reached); the web
parity and sync suites on a T-Deck and a P4 through the loader; a board
after an OTA boots its console before `AddonStep` has run.

**Phase 4 — the relay.** The site becomes a PWA (a service worker keeping
the site, the relay page and the packs of the boards it has flashed or
relayed to) and remembers its boards' addresses. Tests: a two-origin
headless test (the site on `localhost`, a secure context; the board's
loader on a LAN address over `http://`): the relay boots the console with
the network off, a message from another origin is ignored, wrong bytes are
refused; on glass, an Android phone and an iPhone on an offline LAN.

## 11. Open questions for the owner

1. **The add-on on boards with room**: keep it as the offline source (this
   doc's recommendation), or delete `AddonStep`'s page half, the install's
   store and the add-on's removal record, and make every board online-only?
2. **A console on the board's own access point** (a field mode, no router)
   is where the relay earns most; no board serves the console on its AP
   today. Wanted?
3. **The beta window** of the pack store: how many `dev` web builds the site
   keeps (stable keeps every one), against Pages' published-site limit;
   or a separate append-only Pages repository for packs.
4. **Improv as well as the AP form**, or the AP form alone for a first
   release, Improv after?
