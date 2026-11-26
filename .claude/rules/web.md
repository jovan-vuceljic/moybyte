---
paths:
  - "firmware/web_runner/**"
  - "runtime/carts/moy_sync.py"
  - "runtime/**/web_*.py"
  - "device/moy_web*.py"
  - "tools/*web*.py"
  - "site/os/**"
  - "tools/os_site.py"
---

<!-- The wasm console, the sync RPC, and the two web modes. -->

### Third target: the web runner + the moy-spec repo (#151/#170)

`firmware/web_runner/` is the MicroPython-WASM build of the same console. Its
build script and `docs/moycore_direction.md` say how it works;
`docs/history/moycore_plan_2026-08.md` is the walked plan. What neither the code
nor those docs will warn you about:

- **The wasm RASTERIZES — the browser is not the GPU** (moycore stage 4). No board
  lever is reimplemented here: bounce pump, DPI ping-pong, GDMA, PPA and PSRAM
  pooling are probe-guarded and simply absent. **`blit_cover` is NOT optional on a
  565 system canvas** — `wallpaper._backdrop_blit` probes for it and otherwise
  expands a palette-INDEX buffer that does not exist, drawing nothing: a black
  desk with correct chrome on top, which is exactly what the first build did.
- **A board serves the bundle from the browser console ADD-ON CART, or
  boots it through the LOADER, and only the pack its image names**
  (2026-11-17; `native/moy_net/moy_page.h` is the authority). Every board's
  build packs the bundle (`moybyte_web.pack`, `tools/gen_web_blob.py
  --pack`) and bakes into the image two sha256s of the pack, its body's
  (its identity) and the whole file's, and the loader page
  (`firmware/web_runner/loader.html`); the release publishes the cart beside
  the payload (`.claude/rules/ota.md`). A board whose board.toml declares its
  console online (`[web] console`, the C3 Zero's since 2026-11-23, whose
  store the add-on outgrew) keeps no add-on and its `/` is the loader;
  every board's `/loader.html` is too. `docs/web_console_online_2026-11.md`
  §3 and §4 are how it picks a source; what bites is that it runs nothing
  whose sha256 is not the whole-file digest `GET /sync` names, a read from
  its own cache included, and that a worktree image's mirror is this
  machine's `serve.py`, which must be serving that tree's dist/ while a
  browser opens the board. EVERY OTHER BOARD HAS THE ADD-ON BY DEFAULT
  (owner, 2026-11-17): the website's install writes it into the board's internal
  store (`tools/store_image.py`; a board on a card moves it there on its
  first boot, `moy_seed.bring_addon`, which takes other pages' add-ons off
  both stores), and `runtime/carts/web_addon.py`'s
  step installs the one that fits after an update and wherever there is
  none -- once a network is saved, never during a game, backing off on
  failure -- unless its owner removed it, and where the pack does not fit
  the store's free space (the Elecrow with no card in its TF slot) it finds
  that out once, records it (`system/addon_room`), keeps the radio down and
  asks again only when the room is there: any removal of it (Get Carts, the
  shelf, `pkg remove`, a page's delete) records the console as one line of
  `system/removed` (`moy_seed.ADDON_LINE`, `native/moy_store/moy_removed.c`),
  which installing one from Get Carts drops. Where the one that fits is
  there, the step takes every other add-on folder off once the image
  confirms itself (`tidy`), housekeeping that records no removal. A Zero honours the record too,
  and its root links the way back (`device/zero_host.py`'s `way_back`). Any
  other pack is "needs its page updated", none is "install it from Get
  Carts", so "which console is this board serving?" is still answered by its
  firmware version alone. Changing a web build means
  `firmware/web_runner/build.sh`, then rebuild, reflash and install the add-on
  that fits (`tools/board.py BOARD addon`). The pack sits in the store beside
  the carts, so its size is the store's to pay: `tools/store_image.py --check`
  (preflight, after the browser console builds) holds it to every board's
  store, and a headless board's to its first boot's carts and the seed's
  reserve too. For that reason the page, the two worker
  modules and the VM's loader ship without their comments (build.sh re-prints
  their scripts with emsdk's terser, nothing renamed or compressed): read
  `page_core.html`, `page_tail.js`, `worker.js` and `moy_store.mjs` in the
  tree, not in `dist/`. The wasm's C is -Os, -O3 on the VM's loop and its
  collector as upstream sets them, and -Oz on the files no frame runs (the
  store, the theme parser, the two compilers; `variant/mpconfigvariant.mk`):
  -Oz over the rest is smaller still and could not be shown free of frame
  cost (2026-10-28). The C no browser reaches is not built at all, and its
  names are ABSENT from the modules, never stubs: `moy_glass`'s compositors
  and `front` (`MOY_GLASS_PRESENT=0`), `moy_net`'s webhost, web console,
  DNS, GPIO route, updater and HTTP client (`MOY_NET_SERVE=0`) and
  `moy_input`'s keyboard, touch, trackball and BLE drivers
  (`MOY_INPUT_DRIVERS=0`; its event rings stay), all set in
  `variant/mpconfigvariant.mk`; Python probes for them (`getattr`).
- **The browser draws what its boards draw: each arrangement on its board's
  metric class, in the theme's fonts and icon set** (owner, 2026-10-20: the
  browser and the boards never diverge). The handheld 320x240 declares no
  glass, as the T-Deck declares none, and so does any page glass below the
  desk's room (a phone, a small window: `web_boot.glass_in`); the desk declares
  the P4's at the P4's pixel density at any page size
  (`layout_base.desk_diagonal_in`), so it lays
  out on the desk's metrics and tap floor as that board does. `build.sh` generates `fonts_data` (`tools/make_font.py module`)
  for board.toml's `font_tier` -- both tiers -- and freezes it into the wasm,
  faces and icon masks together, so they ride the compressed
  `micropython.wasm` in the add-on's pack.
  **A class the image lacks the tier of falls back to petme128 and the
  shell's own icons with nothing failing**: `tests/test_web_look_parity.py`
  holds the image's sets and the desk's glass to the boards' and, under
  `MOYBYTE_WEB_E2E`, the wasm's frames to the host's in each arrangement,
  pixel for pixel; `tests/test_web_fonts.py` names the face a seed theme lost.
  A web-only tweak to what the console draws (web_boot) is a divergence that
  test reports: the page's own chrome is the only look the browser owns.
- **A gamepad held at the browser is a board's pad** (#254): the page polls
  the Gamepad API once a frame (`page_tail.js`, `GP_BTN`: the standard
  mapping by place, bottom A and right B) and holds buttons of its own
  source, `gamepad`, which joins the console's inputs as the `pad` kind
  while one is connected (`web_boot._gamepad`, `Workstation.input_joined`),
  so its focus and its hints show from the moment it connects. So the
  browser's table is the boards' sixteen-name `InputTable`, never the
  simulator's eight: X, Y, Select and Start reach the shell as a board's
  do, and the shoulders type Q and E, the T-Deck's L and R (none while a
  field takes text or a game owns the keys). **A browser shows a pad only
  to a secure context**: Firefox's `getGamepads()` answers none over plain
  HTTP, so a board-served page may see no pad where the site (https) and
  localhost do.
- **The page keeps no bar of its own** (owner, 2026-11-25): what its top
  bar and the cards under the canvas did is the console's
  (`firmware/web_runner/page_link.py`, `Workstation.page`). The system menu
  holds Full screen (where the browser has it) and Add a file, a cart's menu
  Download and, on a page a console serves, Play on the console; Settings'
  Carts row says where the page keeps them; an import's report, a lost link
  and a sign-in wait are the console's cards and notices. A row ASKS and the
  frame carries the ask to the page (`ask`, the worker's `{t:"ask"}`); a
  browser grants full screen and its file chooser only inside a user's
  gesture, so the page does those while the tap that chose the row is
  still active, else arms them for the next pointerup or keydown and the
  console says to tap. What stays HTML is the loader's progress, the
  pairing card before the console boots and a crash's text.
- **An iPhone's full screen is the page saved to its Home Screen** (owner,
  2026-11-25/26): its Safari has no element full screen, and where an
  iPhone's or an iPad's browser has one it keeps its domain strip and Close
  over the page's top, so there, and wherever the browser has none, the
  system menu offers Add to Home Screen, whose card has the steps, beside
  any Full screen, until the page runs as the app (`navigator.standalone`,
  `display-mode`), which shows neither. That strip is why the page's own
  controls keep out of the top corners (the burger and the keyboard summon
  sit at the bottom of a landscape phone's margins) and why an iPhone's
  element full screen takes a 50-pixel top inset (`html.iosfs`). The manifest and Moy's icons are `tools/web_app.py`'s,
  written beside the page by both builds and named in the webhost's ASSETS
  table, so a board serves them too; the page's head carries iOS's tags and
  `viewport-fit=cover`, and its layout keeps out of the safe-area insets
  (`room()` reads them back from the body's padding). No service worker:
  iOS makes a standalone app of a plain-http page on the LAN without one.
  What bites: the app's storage is not Safari's, so it pairs with a board
  once more, by the password, because a code scanned with the camera
  opens Safari, not the app; and a board's page saved at a number breaks
  when its lease moves, so the card says to save it from the board's
  .local name. The page never zooms: no pinch, no double tap, and the play
  surfaces take every touch (no selection or callout).
- **The emscripten is PINNED: `EMSDK_VERSION` in build.sh, held by
  `tools/emsdk_tree.sh` on every full build** (a tree at the pin is a silent
  no-op, another version is moved to it, one that cannot be had fails the
  build). emcc's output is not byte-reproducible across versions and every
  board image names its bundle by digest, so an emsdk cloned under `latest`
  made two machines' bundles differ. The pin is the version moy-spec's preflight builds
  its player in; bump the two together. A move shares its emsdk with every
  worktree (`tools/worktree.py` links it).
- **`worker.js` imports `micropython.mjs` and `moy_store.mjs` BY NAME**:
  from the loader's Blob URLs (init's `assets`, the wasm's URL too) where a
  loader booted the page, else beside itself, and it resolves its own
  requests against the page's address (init's `base`), because a Blob URL
  resolves no relative name. Both must be in the webhost's ASSETS table
  (`native/moy_net/moy_webhost.c`), which is also what the pack holds: a
  board that does not serve one serves a console that cannot boot.
- **THE LINK between the windows** (`docs/web_console_online_2026-11.md`
  §5): My consoles (`site/os/`, os.moybyte.com, built by
  `tools/os_site.py`) opens a board's origin in a window and hands its
  loader the pack by `postMessage`. What bites: the loader's listener dies
  with `document.open`, so `page_tail.js` takes it over from
  `window.moyLink`; the board's end hears only its OPENER at a MIRROR's
  origin, so a site that speaks the link must be one of the build's
  mirrors (serve.py `--loader --mirror`); a `Cross-Origin-Opener-Policy` on
  either page takes the opener, and the link with it; and the site runs no
  console, so it is in neither web mode. `tests/test_web_link_e2e.py`
  drives both ends across two origins.
- **TWO WEB MODES, TOTAL, NO CROSSOVER.** The ORIGIN a page runs under,
  never the host its bytes came from, says where its carts live — a page on a
  board's origin edits the BOARD's store (the loader's too, whatever source
  its pack came from), a page on a static host keeps them in the browser. **The mode is decided ONCE at boot,
  BEFORE the VFS is seeded, because it decides what the VFS is seeded FROM.**
  `GET /sync` is the marker a board serves, and a GET miss falls through to an
  EMPTY-batch POST — because a board running firmware older than that marker
  still ACCEPTS the batch, and reading it as "static host" would quietly strand a
  kid's edits in a browser.
- **The page's JavaScript does I/O; the console's rules are the VM's**
  (owner, 2026-11-08): what is seeded, skipped and named, the root registry
  and the `.moy` archive run in the VM (`moy_sync.seed_store`,
  `moy_sync.roots_json`, `moy_store.skip`, `moy_pack` through `web_boot`),
  and the VM is up before the store is seeded (the worker's `bindStore`). A rule that must
  run before it is exported from the wasm's C, never copied into JavaScript.
  The store holds no rule: what a path, a song, an install's name or a root
  is reaches it through `bind`. `tests/test_web_io_ratchet.py` holds its
  exports to a list that only shrinks, every string it holds to a filed word
  (no file, folder or suffix) and its patterns to the channel's one (the
  audit: `docs/moycore_direction.md` §3).
- **The substrate is OPFS's shape**: the ops ARE file writes at paths, so a
  cart folder stays a cart folder. OPFS is a secure context's, so a page on
  plain http (a dev server on the LAN) keeps the same folders in IndexedDB
  through OPFS's calls (`moy_store.idbNav`, `pageNav`); a page with neither
  (blocked site data, `file://`) runs in memory and **the page says so**,
  once, as a notice that times out; a quota failure requeues, and
  after three gives up ONCE and says that too. A returning browser's shelf is
  OPFS's, never the bundle's -- except the bundle's SYSTEM carts, which reach
  it as a board's built-ins reach its SD (#47), decided in the VM
  (`moy_seed.seed_folders`, the worker's `seedLocal` only moving the bytes):
  one the store has never had (a new app, a new seed game) is seeded whole,
  and one whose bundled manifest `version` is newer replaces the store's copy,
  its `pmem.bin` and `config.json` kept, by the board's own `_make_room`. Without the first, nobody who had visited
  before a system cart shipped would ever see it; without the second, an app
  kept from an older console runs its old manifest on the new one (Notes'
  `files:docs` after the folders took their names: no `files`, a NameError).
- **A channel's site keeps its own storage.** The stable site (`/`) and the
  dev site (`/dev/`, both from `.github/workflows/pages.yml`) share the
  origin os.moybyte.com, so they share its OPFS. So does My consoles
  (`/console/`), which runs no console and touches none of it: its storage
  is its own names (`moy.consoles`, the `moy-packs` and `moy-app-*`
  caches) and a service worker scoped to `/console/`.
  `site/build.py --channel dev` stamps page_tail.js's `MOY_CHANNEL` into the
  dev player, and the worker opens every store through `moy_store.channelNav`,
  which roots it under `channel-dev/`, so a dev store format never touches the
  stable site's carts. A new store opens through the worker's `opfsNav`, never
  `navigator` (`tests/test_site_channel.py` holds the call sites), and a player
  the build cannot stamp is not published at all.
- **What an embedding page can ask of the console, all read at boot and absent
  from a plain visit** (the project site's hero passes them):
  `?scheme=dark|light` (else the browser's `prefers-color-scheme`) is the
  theme VARIANT of a first run, handed to `console.wire_workstation_core(
  first_variant=)` -- the absent-row default of `load_system`, so a saved
  Settings choice always wins and booting on the scheme saves nothing; `?start=1`
  skips the play button; `?edit=<cart>&tab=code` opens that cart in the Editor
  (`web_boot.start_edit`, without the First Steps badge) from whatever the
  browser's store holds, so a visitor's edits are kept, and on the desk as a
  window unless this browser left it full screen; `&play=1` presses its Play,
  which on the desk runs the cart in the Editor's Game pane; `&only=desk`
  applies them only where the console lands on the desk, so in console mode
  (a phone) the visit lands on the home (the site's one embedded console
  passes all four and lays itself out from its frame, the desk's aspect on
  a wide page and the handheld's 4:3 on a phone, with no tiers to pick). The framed player posts
  `{moyChrome}` and, at its first painted frame, `{moyLive}`.
  `tests/test_web_first_run_e2e.py` drives them. The hero's two stills (Night,
  Day) are CAPTURED by `site/build.py` from the player it ships, through
  `browsershot.mjs` (node 22 + Chrome, which pages.yml installs), on a frame
  whose game is not mid catch-flash: a capture that fails fails the build. The
  site's scheme is one attribute, `<html data-scheme>` (the visitor's switch in
  the top bar, else the system's), which the page's colours, the still and the
  console's `?scheme=` all read; a flip restarts a running console.
- **The journal lives with the STORE OF RECORD** (owner call) — there is one
  durable journal per cart, where the cart durably lives, so a kid gets undo on
  both ends without a byte of history on the wire. **The wire predicate itself
  never moves**: `_skip` refuses journal paths and a board-mode batch is
  byte-identical to what it always was.
- **THE SIGN-IN GATES EVERYTHING** (owner call), reversing the earlier
  read-half-open design: handing any device on the WiFi a child's whole cart
  store for the asking was the thing being fixed. Only the boot assets and `GET
  /sync` are open, by necessity. Since 2026-11-07 the gate is a paired
  browser's device key and a sealed session (`docs/os_2026-11/system.md` §3,
  the protocol `native/moy_net/moy_seal.h`): a request names its session and
  sequence number on the query, so the request parser (`moy_http_parse`) keeps
  the query string, and its body is AES-GCM opened in place before a route
  reads it. A route the VM answers (`/run`, `/update`, the system root's
  batches) parks with its body opened, and the C seals what the VM answers.
  **A page never downgrades**: one that holds a key or has signed in treats
  `{"open": true}`, a 404/405/501 from `/auth` and a 2xx in the clear as
  errors; only a keyless page believes a host that says it has no sign-in
  (the dev server). `firmware/web_runner/signin_test.mjs` holds the page's end.
- **The #108 user files ride the same protocol as a SECOND root**, stamped
  `{"v": 2, "root": "files"}` — the bump is what makes a board flashed before it
  REFUSE the batch instead of writing `Pictures/…` into its carts store. A files
  path must start with a shared folder (`moy_store_base.SHARED_FOLDERS`), which
  is the one rule keeping `.history/` and `.Trash/` home in both directions.
- **The console's own documents are a THIRD root** (`moy_sync.SYSTEM_ROOT`,
  owner 2026-10-20): `system/settings` (the theme, every Setting and the
  apps' prefs, the achievements process's badges row among them), the edited
  bar icons and the shared sheet ride the same sweep into a site-mode page's
  OPFS, so a reload comes back on the same
  theme, Settings and badges. Each lands old-or-new (`moy_store.commitFile`),
  because a torn `system/settings` boots the console on its defaults. **On a
  board the root is the VM's, never the C's**: the page seeds from `GET
  /console.json` and pushes `{"v": 2, "root": "system"}` batches, which the C
  parks (its seal checked) for `moy_webhost.ConsoleSystem` (a Zero's
  `StoreSystem` keeps them and applies nothing); the board is of record
  and takes a page's change KEY BY KEY (`moy_sync.SYSTEM_KEYS`: an unknown key
  is LOCAL, so the consent records are never taken; the update channel is
  never sent and never taken, and the badges row crosses whole, the later
  writer's winning). Its directory is the carts folder's
  parent and proves nothing, so the page watches it only when the pull
  answered (the worker's `seeded` list); firmware without it 404s the pull and
  400s the batch, and that page keeps them in the tab. Cart paths in
  `favorites`/`plays`/`desk_mru` cross as folder names and land under each
  side's own carts root.
- **The apps' private folders are a FOURTH root** (`moy_sync.APPS_ROOT`), all
  bytes, with one writer per mode (`docs/os_2026-11/between_apps.md` §2): what
  bites is that `Root.site` is False, so the worker's `initStore` and
  `web_boot._build_watchers` both skip it in site mode, where the keeper owns
  OPFS `apps/`.
- **Get Carts installs in a page that keeps its own carts (#124); a page a
  board serves ASKS that board, which installs into its own store (owner,
  2026-11-24).** In site mode `carts_link.py` gives the console the page's
  fetch (`ws.cart_net`), an OPFS keeper (`ws.cart_keep`) and the page's file
  picker (`ws.cart_pick`). A board-served page gets `ws.cart_home`, and
  `ws.cart_board` (`carts_link.BoardCarts`) where the worker's probe of the
  sealed `/official` answered (`web_boot.official_enable`) -- keyed on that
  answer, never on the board's kind: every board's webhost answers it (a
  Zero's `zero_host.make_official`, a console's
  `moy_webhost.console_official`, both `runtime/carts/web_addon.py`'s
  `OfficialCarts`), and the console's glass is parked while its web console
  serves, so the board is its store's one writer. Get Carts lists the carts
  of the board's indexes (its `system/sources`, else moybyte-org/carts, and
  its own release's): the board names them and the page fetches and reads
  each by the VM's rules (`carts_link.BoardCheck`): its release's from the
  mirror os.moybyte.com keeps of it (`cart_index.index_mirror`), checked
  with the keys the board names, and the board lists one the page cannot
  read or check. A licence, Get or Remove asks the board (a slice per poll
  like `/update`), which reads the one entry as its index streams
  (`cart_index.EntryRead`, so no index is ever whole in a board's heap) and
  fetches and writes its own store,
  the page answering the install prompt over the manifest the board
  checked; once it has, the worker pulls the board's carts again and
  replaces the page's copy of that one folder in one turn of its thread,
  and the watcher adopts it, so nothing the board wrote travels back as an
  edit. Only a board that answers no `/official` (an older image) leaves the
  page saying the board gets its own carts. A console's on-screen Get Carts
  installs as it always has. What bites:
  - **Nothing may wait for the network inside a step.** The VM has no
    ASYNCIFY and the worker delivers bytes only between frames, so every fetch
    is a `cart_index` job that gives the frame back; a Python loop waiting for
    `ready` is a hung tab. A body goes into a spool file in the VFS -- the
    page's memory -- and never through the 16 MB heap.
  - **A page cannot read a release download or Debian's archive** (neither
    sends a CORS header). It reads an asset's `mirror`, and an external
    file's, on the carts repository's Pages site first (moybyte-org/carts'
    scripts/make_index.py names them), and a firmware release's
    `carts-<board>.json` where the Pages deploy mirrors it with the official
    carts' files beside it (`tools/pack_store.py`), which is the release's
    only when its signature verifies.
  - **The site's player lists its channel's release** (owner, 2026-11-25):
    its `indexes.json` (site/build.py) names the mirrored P4 index of
    firmware-latest on `/` and of firmware-beta on `/dev/` as `own`, and the
    page takes it as the release's, its official carts listed and installed
    from the mirror, only when its signature verifies under the release keys
    the bundle bakes in (`release_keys`, `tools/ota_sign.py keys-module`,
    the keys every board trusts) -- never for the address it was read from. An external file it can read from neither is the player's
    own copy, chosen in the browser's file chooser, which a browser opens
    only inside a user's gesture: the page opens it at once while the tap
    that asked is still active (`navigator.userActivation`), else at the
    player's next tap or key (page_core.html, THE ASKS).
  - **The sweep cannot persist an install**: the wire carries text and covers,
    never a module or a WAD. The keeper writes the folder and the record into
    OPFS behind one marker file (`moy_store.commitInstall`), boot rolls an
    interrupted one forward or away before the store is read
    (`recoverInstalls`), and the watcher ADOPTS the landed folder instead of
    shipping it. `store_test.mjs` interrupts an update at every change it
    makes.
  - **The shelves are the serving host's**: an `indexes.json` beside the page
    is read once at boot; its `indexes` replace the defaults, written as the
    console's `system/sources`, and its `own` names the release index
    (`ws.cart_own`, web_boot.site_sources).
  - **A page keeps no compiled module**, so a release asset is read by RANGE
    (`ranges` on the page's transport, `cart_unpack._Ranged`): the zip's
    directory, then the runs of members it keeps -- a cart's modules are most
    of its asset and never cross. Any first range not answered 206 (a host that
    ignores ranges, a refused preflight) reads the asset whole.
    `tests/test_web_wasm_e2e.py` installs a compiled cart this way and plays
    it; `tests/test_web_store_e2e.py` drives the Lua side.
- **A compiled cart runs on the BROWSER'S engine, behind the boards' session
  surface** (`native/moy_wasm_web`, its README). The cart's `main.wasm` is a
  sibling module the worker instantiates (`worker.js`'s cart engine, moy-spec's
  web-player adapters over libmoy's import table); moycore, `WasmRun`, the
  Player and the canvas are the boards'. What bites:
  - **Nothing on a board is reimplemented here, and nothing native applies**:
    no AOT module, key, signature or admission -- `moy_wasm.CHIP` is None,
    so WasmRun opens `main.wasm` and is never "slow" for it.
  - **A hook's catch rethrows anything that is not an `Error`**: the VM's own
    longjmp unwinds as a JavaScript exception through the cart's frames, and
    swallowing it would strand MicroPython's nlr.
  - **A page a board serves gets no `main.wasm`** (the wire carries text and
    covers), so its scan leaves the board's compiled carts off its shelf
    (`moy_carts.load`: no main, no cart); they play on the board.
  - **The site-mode sweep must pass a file it cannot carry by stat**
    (`moy_sync.StoreWatcher`, crc None): when it re-read every binary file on
    every sweep, an installed Doom drew a frame a second.
  - **The sweep re-reads the files of its newest second only for
    `moy_sync.HOT_MS`** after it first saw that second: a browser seeds every
    file in one second, and a hot set with no end re-read and hashed the whole
    store every sweep for as long as nothing wrote a newer file.
- **The site's Terminal runs WASI commands on the BROWSER'S engine, through
  the boards' adapter**, compiled into the site's wasm alone; the README of
  `native/moy_wasm_web` says how ("A WASI command here"). What bites:
  - **A row's pointer is an offset in the module's memory, never one into
    the VM's.** A WASI row reaches it through `moy_wasi_web_reach`; a
    `moybyte.os` row, whose body dereferences what it is handed, gets copies
    of its `*~` spans because the C hands the page its signature. A new WAMR
    call in `moy_wasi.c` needs its twin in `moy_wasi_web.c`:
    `tests/test_wasi_web.py` names it before a `--site` build fails.
  - **Nothing waits inside a command**: the module runs inside the door's
    crossing on the one thread, so stdin from the grid is end of file, a
    `moybyte.os` row that hops (a console call, the door's Python half)
    answers NOSYS, and the first-run question is asked at the prompt and
    answered by the next line (`moy_sh_ask`), never read during the run.
  - The worker's command engine (about 1 KB of script gzipped) rides the
    bundle too; its C does not. `tests/test_web_term_e2e.py` runs
    wasi-sdk's modules in Chrome.
- **Music plays in the browser on the boards' decoder (#251)**: `moy_media`
  is in the wasm with no task and no HTTP client (`moy_media.h`, THE
  BROWSER): the frame's C job decodes, and what the VFS does not hold (a
  URL, a song) the C arms for the face, which feeds it from `ws.media_net`
  (`media_link.py`) in both modes, from the byte a seek asks for (`mget`'s
  `at`). What bites:
  - **A song never enters the VFS.** A site-mode page's songs stay in OPFS
    (`moy_store.readAll` leaves `files/Music/*.mp3` out; a dropped MP3 is
    written there), a board-served page's on the board, read through its
    sealed `GET /media` 32 KiB a request; the worker lists either into
    `web_vfs.LISTING` at boot, which is what Music's folder shows.
  - **A stream's bytes go through spool SEGMENTS** the console removes as it
    reads them, and the worker stops reading while four wait, so a radio
    station costs the page a few segments however long it plays.
  - **The page's frame pulls the mix while a stream plays** (`web_boot`'s
    step ticks `_RunnerPump` when no Player did): a board's feeder task
    pulls it whatever runs, and on the web nothing else would.
  - **A station playing on behind a still desk allocates little a frame**:
    the step leaves the frame's samples as four numbers at `pcm_addr()`
    (`web_boot._PCM`) and returns "" unless it painted, the pull and the
    media face's feed reuse their buffers, and the page's reader finds a
    segment's growth by reading it, not by a stat. `?meter=1` counts the heap's
    allocation each frame (`__moyState().alloc`), and
    `tests/test_web_audio_stream_e2e.py` holds a station's frames and the
    loop around them to a stated bound.
  - **A station without CORS headers cannot be read**, and from the page
    that looks like no network; a `no-cors` fetch that answers tells them
    apart, and the face fails the entry with EACCES. A page on https asks
    for an `http://` station over https (mixed content), and a station whose
    https address redirects to http cannot play there. The fetch names no
    page (`referrerPolicy: "no-referrer"`): SomaFM answers a Referer naming a
    github.io or localhost page with an empty 403.
  - **A station is asked for its ICY metadata as a board asks
    (`Icy-MetaData: 1`), which makes the fetch PREFLIGHTED**, and its
    `icy-metaint` is readable only where the station exposes it
    (Access-Control-Expose-Headers). `media_link.py` decides: a refused
    asking fetch, or an answer with no readable `icy-metaint` (its bytes may
    carry metadata nothing can take out), is read again without asking, so
    a station that played before still plays, with no now-playing text. The
    head reaches the C through `moy_media_feed_icy`, and the feed takes the
    metadata out with the board's own demux. The worker only sends the
    headers it is given and reads back the ones it is named.
- **THE PAGE IS THE SERVING BOARD'S UPDATE SURFACE** (#41/#53, 2026-08-29), and
  what it does depends on whether that board has glass. Headless: the strip IS
  the update screen — two taps, then a polled progress read, because the board
  installs in its own loop. With glass: ONE tap hands the glass back and the
  board's own update screen takes over, so the page installs nothing anywhere.
  Both go through `GET`/`POST /update` on the shared webhost, which is plain
  HTTP: the megabytes never cross this link (the board downloads its own
  firmware), and a persistent socket's idle reaper would have dropped a client
  through a flash write — which is exactly what the old streaming port hit.
  That verdict is why the transport's WebSocket half had no consumer left and
  was deleted in 2026-09 (below). **ONE disconnect surface,
  and the REASON is its point**: an update or a hand-back is "expected" and
  nothing is at risk; a board that vanished is "lost", and only that one carries
  the unsynced-work warning, because board mode keeps no local store. First
  reason wins, so an update nobody needs warning about cannot later be
  re-reported as a loss.
- **A page a Zero serves manages that board's Wi-Fi** (2026-11-25): its
  `ws.wifi` is the board's (`wifi_link.BoardWifi` over the sealed `/wifi`,
  `device/zero_wifi.py`), probed before boot, so the bar, the Settings row and
  the one Wi-Fi panel are the board's; anywhere else the page has none (#324).
  What bites: a join MOVES the board off the network the page reaches it
  over, so Settings asks first (`switch_says`), and from the board's answer
  the worker holds the sync's give-up through the board's two windows
  (worker.js, `wifiMove`); the board found again settles it, and silence to
  the end is a move that worked, said as EXPECTED with an Open to
  `<name>.local`, never as a loss. A cart is never handed this station
  (`CARTS`). `serve.py --wifi` is the twin, and
  `tests/test_web_zero_wifi_e2e.py` drives it.
- **The console's HTTP server is the kernel's** (`native/moy_net/moy_webhost.c`
  over `moy_http.c` and `moy_net_port.c`): a non-blocking listener polled at the
  frame tail with no Python, one-shot serving, the bundle, the pulls and the
  sync apply in C, and a soft reset leaves it serving. `device/moy_webhost.py`
  is its Settings contract and answers the routes the VM owns (`/run`,
  `/update`), which the C parks for the poll to take; the Zero's `/gpio` is
  the C's own route over its pin table, and its setup form rides the same
  webhost with every path parked. The streaming web
  view — the frame push, `device_webview.py`, the recording `TeeCanvas`, stream
  mode, the Settings WEB VIEW row, `ws.web_hook`, the host `tools/web_console.py`
  and its VM recipe — was DELETED in the 2026-08 sunset (owner decision,
  `docs/history/moycore_plan_2026-08.md` §3.2; `tests/test_streaming_sunset.py`
  pins the absences), and the recording stack went at stage 4 (2026-08-12)
  because the wasm head rasterizes. Mirror-of-glass is an accepted loss: a
  screenshot verb on the sync RPC was its recorded successor and was DROPPED
  (owner, 2026-08-25) — the browser IS the console. The WebSocket half went in
  2026-09, because the §3.4 sync RPC shipped as plain HTTP and nothing else
  used it. What survives of the old view is `runtime/shell/web_input.py` (browser
  events → InputState/Pointer, which the sync RPC speaks). The recording-tier
  surface machinery in `wm_windowed` and the kernel's surface table were
  deleted on 2026-10-27 (`docs/surface_model_v1.md` §16).
- **The live socket is a Zero's page's, and the worker's to move** (#256,
  `native/moy_net/moy_live.h`): one sealed WebSocket to `GET /live` (seal
  slot 1), multiplexed by its frames' first byte, served
  on the board's own task. Its terminal channel ('t') is the page's
  Terminal (`native/moy_tty/moy_tty_live.c`): a Zero serves no `GET /term`,
  which the consoles' pages keep (seal slot 0). Its request channel
  (`moy_live.c`, THE REQUESTS) carries the page's sealed requests, the
  pulls, syncs, songs and probes, to the webhost's own routes and answers
  them there: each request is sealed as over HTTP inside the socket's seal,
  so the board serves the page ONE connection (an https page holds one TLS
  connection's RAM, the reason: owner, 2026-11-26). `worker.js`'s
  `boardFetch` is the one wrapper: HTTP where the socket is shut or the
  board names no `req` in its probe, and for the sign-in, the marker, the
  bundle and the sockets' own probes; the webhost still answers every
  route over HTTP too. Its control channel's hints
  (`moy_live.c`, THE HINTS) say when what the page reads from those routes
  changed (the store, `/wifi`, `/update`, `/official`), and while the socket
  is open the worker asks them on a hint, never on its clocks. Its first channel relays the board's ESP-NOW, so
  the page's link (`moy_link_web.c`, the kernel's Match over it) plays a
  console's match, a Python cart's as a Lua one's: the wasm computes floats
  as the boards' do (REPR_C over 32-bit words, single precision,
  `variant/mpconfigvariant.h`), which the lockstep contract requires
  (`docs/netplay_v1.md` §5). So a count, an address or a time the page and
  the VM exchange rides an integer, never a float, which keeps 22 bits:
  `web_boot._PCM` is 64-bit integers, and `time.time()` is whole seconds
  as on a board. Its device channel ('d') relays the board's device APIs
  that have a relay list (`native/moy_kernel/moy_dev_kinds.h`, THE RELAY;
  lora): the probe names them, and the page's handles of them are remote
  rows of its handle table (`moy_dev_web.c`) that never wait on the socket,
  served on the board under the page session's own process, which its end
  sweeps. A Python program holds faces, not handles, so a relayed device is
  absent to it (`app_perms._why_absent`). The worker moves its bytes between
  frames (`liveStep`, `web_boot.live_*`), never inside a step, and reopens a
  dropped socket itself; a console board builds no bridge and 404s the probe.
- **WASM MODE IS A SWITCH, NOT A SESSION** (owner call): no heartbeat, no presence
  detection, no timeout. While WEB CONSOLE is ON the glass PARKS on a connection
  screen — which is how the two-writer collision is **designed out rather than
  detected**. The switch is the kernel's (`native/moy_net/moy_webconsole.c`)
  and **a start never waits**: it returns JOINING, the frame's poll binds once
  the WiFi driver's link has an address (the kernel dials the network it kept)
  and parks the glass then, and a join that outlives `MOY_WC_JOIN_MS` fails
  into the row's label. Only the dev word `web` waits for the outcome. The QR encoder is ours because there is no library on a board and
  the QR's pairing token is minted each time the screen draws it. **The sign-in's
  system folder is read at `start()`, never at construction** — boards build the
  webhost before the store is up.
- **Two Makefile patches are load-bearing and non-obvious.** `-Wno-unknown-pragmas`
  must be appended to the PORT's CFLAGS, not `CFLAGS_USERMOD`: py.mk folds usermod
  flags in at its include and the port adds `-Wall` afterwards, which re-enables
  the warning `-Werror` then makes fatal. And `HEAPU8` is patched INTO the port's
  `EXPORTED_RUNTIME_METHODS_EXTRA`, which is set with `+=` — a command-line
  assignment REPLACES it, dropping `getValue`/`setValue`, and the VM's JS wrapper
  dies at boot.
- **Reach for `node pageshot.mjs` FIRST on any "it looks wrong / it doesn't show
  up" report** — a screenshot is the right evidence for a placement or retention
  bug, and the misplaced FPS chip was invisible in a frame dump and obvious in a
  PNG. When a bug survives that (worker pump, transferable ping-pong, rAF),
  `browsershot.mjs` drives the shipped page in real headless Chrome. **The page
  waits behind a play-button splash unless the scenario passes `?dev=1`**, so a
  scenario that forgets it screenshots a blank canvas and looks like a raster bug.
  For a one-off look at a page, `tools/web.py shot URL` prints the PNG's path
  and the page's errors (`shot /?dev=1` serves this tree's dist for the shot;
  `tools/web.py serve` serves it on a free port until stopped). It drives the
  SYSTEM Chrome through Playwright, the `web` extra: never `playwright install`.
- **The p8 import is UPSTREAM of us, BOTH halves.** SPEC.md says what a
  converted cart MEANS, so corrections are worked out in moy-spec and travel
  HERE — and once they did not: upstream fixed a pitch offset, our hand-copy
  never heard, and **every cart imported through this repo came out two octaves
  flat while `make test` stayed green**, because the tests had pinned the wrong
  model too. `make vendor-p8-import` carries `p8_import.py` (the assets) and,
  since 2026-08-29, `p8_lua_port.py` (the cart's CODE under a generated p8 shim,
  plus the `.moy` folder itself). **Editing either here is a red test.** What
  stays ours is `import_p8.py` (the CLI) and `p8_writer.py` (the input guards,
  the `os.path` shim, the compatibility report) — neither writes a byte of a
  cart. The `view(128, 120)` hint is `p8_writer.P8_CROP` now, passed on every
  tier, so `--zoom` is only the upstream CLI's spelling of it and cannot be
  forgotten here. `ports/celeste.moy` is gitignored on BOTH repos (CC BY-NC-SA)
  — never commit or ship it.
- **The BROWSER imports p8 carts too (#194), by running those same files, and
  the imported cart RUNS.** A dropped or chosen `.p8`/`.p8.png` is converted
  in a wasm VM of its own, a second worker that ends with the cart
  (`worker.js`, THE CONVERTER: a conversion takes an iPhone minutes), while the
  console goes on drawing and its notice says the stage; then the console's
  card shows the compatibility report, its Open playing the cart
  (`page_link.py`'s `offer`): `build.sh` stages `tools/p8_import.py`, `tools/p8_lua_port.py` (both
  hash-pinned) and `tools/p8_writer.py` into the frozen set, plus `shims/zlib.py`,
  four lines over MicroPython's `deflate`. **The browser could skip the inflate
  entirely** (`createImageBitmap` + `getImageData`, then read the low bits in JS)
  and that is exactly what was DECLINED: it would be a second reader of one
  format, the same shape as the hand-copied converter, and it does not generalise
  to a board. Rules the tests pin: the **zoom hint is
  unconditional** here (`p8_writer.P8_CROP`, canvas `128x128`) because on the web
  that footgun would fire on every import; the PNG validation is **explicit**
  because the frozen build is opt=3, which strips the converter's own asserts;
  and the browser and the CLI must write **byte-identical** carts, which is why
  the porter declares its manifest field order (MicroPython dicts are not
  insertion-ordered).
- **A file that only has to be "stdlib Python" is NOT known to run on
  MicroPython — RUN IT.** `p8_lua_port.py` was stdlib-only and did not: its
  `localization_lua` used a **lookbehind, a `(?:...)`, an inline `(?m)` and a
  lookahead**, all four of which MicroPython's `re` rejects at COMPILE time
  ("regex too complex"), so the browser's first import would have died on a line
  that reads fine. Three more followed — `str.isalnum` (absent), `json` with no
  `indent=`, and `os.makedirs`/`os.path.join`. All six were fixed UPSTREAM,
  because unlike `os.path.basename` a regex engine and a str method **cannot be
  injected from out here**. `tests/test_p8_micropython.py` is the lane that found
  them and `tests/test_p8_import_vendor.py` scans a re-vendored file for the six
  statically. **Memory is the other tier fact**: a real BBS cart needs several
  times the fixture's MicroPython heap to import; the browser gives the converter's VM 16MB to start,
  and that import is the bar a device leg has to clear.
- **Trust zepto8 for p8 semantics, not the wiki**: the pattern-length rule is the
  first non-looping channel, and all-looping means the SLOWEST channel — the
  wiki's "all-looping loops forever" is WRONG.
- **Web audio is FINISHED PCM at the page's AudioContext's rate, and the
  samples never ride the frame slot** (page_core.html, THE SINK). The context
  is made as the page loads, so its rate reaches the console before boot: the
  sessions mix at 22.05 kHz as on every board and the C upsamples that mix
  once to it (`moy_aud_render_out`), the MP3 decoder resampling to it too, so
  the page plays the samples one for one and its JS converts nothing. The
  worker posts each frame's samples straight to the sink -- an AudioWorklet
  over a MessageChannel in a secure context, the page's own AudioBufferSource
  schedule on a board-served page over plain HTTP, which has no worklet --
  because the page keeps only the NEWEST frame: samples that rode a frame
  were dropped with every frame a newer one superseded, and the pull, steered
  by a depth that did not count them, drained a live stream faster than real
  time until the decoder starved (the owner's stutter on the P4-served desk,
  2026-11-10). The pull tops the sink's depth up by COUNT (`_RunnerPump`:
  samples sent against the sink's `played`), a station or a song deeper
  than a game's sounds (`_AUDIO_MEDIA_TARGET`, from its first chunk): the
  frames that start one are the console's heaviest, and a slow machine
  outlasted the game's depth over them; a dry sink plays silence and
  counts it (`__moyState().sink`: `under`, `dry`, `gap`, `dup`, `over`),
  and its longest wait between chunks (`lull`) stands beside the worker
  loop's longest frame, step, collect, sweep, send and count
  (`__moyState().loop`), each with the play time it ended at, so an
  underrun names the side that stalled; `tests/test_web_audio_stream_e2e.py`
  plays a live station a minute on both sinks. The loop's own collect waits
  for a stream to end (`worker.js`, IDLE_QUIET_FRAMES): what a playing frame
  allocates the VM's threshold collects, and a pause the worker added would
  come out of the sink's lead. Two URL flags take it apart on a phone, where
  there is no console to read: `?audio=0` makes no context (no sink, no
  samples sent), and `?hud=1` shows the HUD from the load (the page's rate,
  the worker's step report, the sink, http or https, and the page sink's
  calls a second and cost).

