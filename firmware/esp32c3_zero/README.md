# Moybyte Zero on an ESP32-C3 (`c3_zero`)

The Zero — the screenless cart store a browser console runs against — on the
smallest chip that holds it: an ESP32-C3 with 4 MB of flash in the package
(the ESP32-C3FH4 of the "Super Mini" boards and their kin), USB-Serial/JTAG on
the chip, WiFi, and no PSRAM.

It is a **variant** of the XIAO Zero, not a second design. Both boards take
the same store host (`device/zero_host.py`, `device/zero_setup.py`,
`device/zero_shell.py`) and the same module sets, so how
the Zero is set up, paired, synced and signed into is
`firmware/seeed_xiao_esp32s3_zero/README.md`, and is not repeated here:
its first setup over the cable (Improv) included, which matters most here,
where the cable is the only way an image goes on. This file is what the
chip changes.

## What the chip changes

- **No PSRAM.** Every block the kernel places in PSRAM is the one internal
  heap's on a build without it (`native/moy_kernel/moy_platform.h`,
  `MOY_HAS_PSRAM`), a task stack the table puts in PSRAM is internal, and the
  kernel keeps no small-block pool (`native/moy_kernel/moy_kernel.h`) and a
  half-size log ring (`native/moy_kernel/moy_log.h`). WiFi, the VM's heap and
  the native tier share the chip's internal SRAM, so the Python heap is one
  block of 64 KB, made at boot and never grown
  (`boards/MOYBYTE_C3_ZERO/mpconfigboard.h`, `moybyte_patch_gc_split_reserve`):
  the Zero's Python drives the C that does the work, and what is outside
  that block is the room that C takes while it works. The store host holds
  about two thirds of the block for good, and three rules keep the rest in
  one run (`device/zero_host.py`, THE HEAP'S SHAPE): everything that lives
  for good is made at the host's start, the heap collects every `GC_STEP`
  bytes, and a request gives back what its session cached.
  `tests/test_zero_heap.py` holds them on a host, with the board's own start
  and loop in the free heap this board has, and the suite's soak reads both
  heaps on the board after every round. A sync batch is the largest of the C's room: the
  webhost reads an upload longer than its kept head into a buffer of its
  own, up to `MOY_HTTP_REQ_MAX`, and gives it back when the request ends
  (`native/moy_net/moy_webhost.c`, `HEAD_CAP`), so the room is there between
  requests rather than held. The WiFi/lwIP window set the XIAO takes is left
  out for the same reason (`boards/MOYBYTE_C3_ZERO/sdkconfig.board`).
- **One app slot, no OTA** (owner, 2026-11-17). The table is a factory slot
  and the store (`boards/MOYBYTE_C3_ZERO/partitions-moybyte-c3-zero.csv`).
  The updater reports itself unavailable (`moy_ota.OtaUpdater.available()`),
  so the console's update screen shows no update to offer, and a new image
  goes on by cable. The store is the space after the slot. The website's
  card offers the install, the merged image and an empty store
  (`tools/store_image.py`), and, as the C3's only update, the merged image
  as it is, which keeps the store while the table stays. The slot grew by
  64 KB for the fast console (below; owner, 2026-11-26, at the store's
  expense), and the flash that brings that table formats the store once.
- **The browser console is not in its install** (owner, 2026-11-23): the
  add-on cart outgrew this store, so board.toml declares the console online
  (`[web] console = "online"`): the website's install lays down an empty
  store and the cable flash installs no add-on (`tools/board_flash.py`),
  and `tools/store_image.py --check` holds the store to the first boot's
  carts and the seed's reserve instead, which keeps no room for an add-on
  (`zero_host.addon_room`). Its root serves the loader
  (`native/moy_net/moy_page.h`, THE LOADER;
  `docs/web_console_online_2026-11.md` §3), a page of a few KB in the image
  that boots the pack whose whole-file digest the image names, from the
  browser's cache or a mirror (os.moybyte.com, and a worktree build's
  `serve.py` first), so a page load costs the board the loader and `/sync`,
  not the pack. The board asks its release for no add-on
  (`zero_host.make_addon` is None where `moy_web.online()`).
- **The fast console: its page over https, on demand.** iOS runs a page
  that came from a plain-http address with no JIT, in every browser there,
  and a window or a home-screen app opened from it inherits that. So the
  loader asks an iPhone or iPad (and any browser with `?fast` in the
  address) "Make it faster on iPhone?" (the owner's words, 2026-11-26).
  Make it fast asks `POST /tls`, which opens the board's TLS door on port
  443, and goes to `https://<the same host>/`; Remember my choice keeps the
  answer in the http origin's storage, and the loader skips the card for
  it after. About's Fast console on iPhone row goes to `?fast`, which
  forgets the answer and asks again
  (`native/moy_net/moy_net.h`, HTTPS on demand; `moy_tls_srv.c`). Joining
  the board stays plain http; the door holds RAM only while it is open, and
  closes itself two minutes after its last connection ends (a page waiting
  at the pairing prompt holds none). Behind it is the webhost, over
  loopback, so every route, the live socket (wss) and the Terminal work as
  over http, and the sign-in's backoff counts each browser by its own
  address. A Terminal there opens only while the internal heap has 56 KB
  free and a 16 KB block (`MOY_TLS_TERM_FREE`): a session on top of the
  door and the page's burst through it took the heap under 3 KB, so below
  that the Terminal says so and Enter asks again; over http it opens as
  ever. The certificate is the board's own, self-signed, made the first
  time and kept in `system/` (`tls.der`, `tls.key`), so Safari's one
  warning (Show Details, then visit this website) is once per board. What
  differs from http:
  - **Pairing is per origin.** A browser paired on `http://` pairs again on
    `https://`: its key lives in the origin's storage.
  - **A mirror must be https.** From the fast console the loader cannot
    fetch an `http://` mirror (mixed content), so it boots from
    os.moybyte.com, which holds the published packs, or the browser's cache.
    A worktree build's `serve.py` mirror is http: a dev image needs an https
    mirror named in its build (`MOYBYTE_WEB_MIRRORS`) for a phone.
  - **When the door closes** (a phone locked past the grace, a reboot), the
    page cannot fall back to http: it says "The fast console closed" and
    links `http://<host>/`, where the button opens it again.
  The Zero suite's `test_the_fast_console_runs_through_the_secure_door` runs
  it on this board and reads its RAM.
- **The image carries the core carts alone** (owner, 2026-11-17;
  `moy_seed.CORE`, board.toml's `[roster] image`), under the XIAO's seed
  rule (`zero_host.seed_carts`): the app slot has no room for more. The
  store gets the apps (Terminal, Notes, Calc, Music, My Art) and Brick Siege
  at flash time instead (owner, 2026-11-24; board.toml's `[roster]
  install`): the website's install writes them into its new store
  (`tools/store_image.py`), and a cable flash into a store that lacks one
  whose removal it did not record (`tools/board_flash.py`'s `install_carts`),
  which also brings every official cart the store holds to the image's
  release, as this board has no OTA. Pin Light is not among them. The
  release publishes the other system carts, all but the test fixtures, as
  official carts in `carts-c3_zero.json`. The page this board
  serves adds and removes the rest, and the carts of moybyte-org/carts (or
  of its `system/sources`), as the XIAO's does (its README), the install's
  modules frozen here for it. The page lists the shelves itself: the board
  names them and the page fetches and reads each index
  (`carts_link.BoardCheck`), since a Python heap that cannot grow past its
  reserve has no room to parse one; the board lists only an index the page
  cannot read. An install reads only its cart's own entry from the streamed
  index, and of it only the members the install reads
  (`cart_index.EntryRead`); its buffers are made for it, smaller where
  the heap has no block for them (`cart_index.chunk_buffer`), and given
  back once its last file is in, before the install prompt's manifest and
  the record are parsed (a running-out logs its frames and the heap free,
  `cart_index.where`), and a cart its store has no room for is refused with the
  sizes before anything is fetched. Those fetches are https, and its image
  carries a CA bundle of its own (`boards/MOYBYTE_C3_ZERO/ca_roots.pem`)
  where the XIAO takes ESP-IDF's common one: the roots the hosts it fetches
  from chain to (the release's index and assets on GitHub, moybyte-org/carts
  on GitHub Pages, the site's mirror), with a backup per CA family. An https
  host outside those families fails its handshake; its root goes in that
  file. A handshake needs one block for the 16 KB record a server may send
  whole, beside the page's live socket and the WiFi driver's receive
  buffers, so what an https fetch holds of its own is kept small: the http
  client's head buffer grows from `MOY_HTTPC_HEAD_FIRST` only while a head
  needs it (`native/moy_net/moy_ota.h`), and TLS writes through a 2 KB
  out-buffer (`boards/MOYBYTE_C3_ZERO/sdkconfig.board`).
- **SSH, without SFTP.** The server and the shell's face run in the same
  internal heap, so a build without PSRAM sizes them to what a session was
  measured to use there: the server's and the face's stacks, the session's
  arena (`native/moy_ssh/moy_ssh_run.c`, `native/moy_tty/moy_tty_sys.c`,
  `native/moy_tty/moy_tty_sh.c`), the channel's receive window, whose
  buffer is made whole at the client's first key, and the packets the server
  sends, at most 2 KB each (`native/moy_ssh/port/localoptions.h`). A full-screen
  text app (`edit`, `vi`, `top`) keeps no screen of its own there: its
  writes go straight to the client (`native/moy_sh/moy_sh_app.h`), so it
  opens at any terminal size in its record, and an editor's text, in 1 KB
  blocks, takes what the session leaves above the shell's reserve
  (`MOY_SH_HEAP_RESERVE`). The face task is made when the server
  starts, beside the other long-lived blocks, because made at a session's
  start it stayed in the middle of the free heap and cut the block an upload
  needs. The `sftp` subsystem is refused (`native/moy_ssh/moy_ssh.c`): its
  buffers do not fit beside a session, and a client reports a refusal where
  running out would cut a transfer short. While a session runs, an upload
  that finds no room is answered 503 and the page sends it again. A new
  sign-in takes over from the session served (`native/moy_ssh/moy_ssh.c`, THE
  TAKEOVER), its handshake beside that session in the same heap: under
  `NEXT_ROOM` free (and a `NEXT_BLOCK` block) the new connection is closed
  unanswered and the session served goes on, so a second sign-in never takes
  the heap WiFi needs. A PSRAM board has no such floor.
- **Local multiplayer, as the XIAO's** (2026-11-24, its README's section):
  the page this board serves plays a match on its radio through the live
  socket (`native/moy_net/moy_live.h`), sized for no PSRAM
  (`boards/MOYBYTE_C3_ZERO/mpconfigboard.h`). Between pages the bridge holds
  only its statics: its task and its buffers (the page's frames waiting to
  be whole, `MOY_LIVE_IN`, half the XIAO's; one frame down; one radio frame)
  are made when the webhost hands it a page's socket and given back at its
  end. The page signs in on the socket and asks every sealed route there
  alone (`moy_live.c`, THE SIGN-IN and THE REQUESTS; over HTTP they are
  refused 410), and a socket signing in is the webhost's until it is
  sealed, its frames in one 1 KB buffer (`moy_webhost.c`, THE SIGN-IN ON
  THE LIVE SOCKET). A request the page asks on the socket
  is pieced together in a block of its own length, and its answer leaves
  through one of `LIVE_PIECE` bytes (`native/moy_net/moy_webhost.c`), both
  given back once it is answered, as an HTTP request's upload buffer is.
  The radio's receive ring (`MOY_LIVE_RING`, a quarter of the XIAO's)
  is the kernel link's, made at the first match and kept, as the link keeps
  it on every board (`native/moy_net/moy_link.c`). A socket whose buffers do
  not fit is refused like a second page's, and the page tries again. The
  whole protocol is wired; what the C3 leaves out is room, not a feature: a
  match beside an SSH session competes for the internal heap that session
  leaves (#276). What a match costs here is on #256.
- **Single core, RISC-V.** Every task the native tier starts runs on core 0
  (`native/moy_kernel/moy_tasks.h`).
- **One I2C controller.** The kernel's device bus takes port 0, so this board
  declares no kernel bus beside it (`native/moy_kernel/moy_devbus.c`).

## Hardware facts

- USB id `303a:1001` (USB-Serial/JTAG). It opens with both lines HIGH, like
  the XIAO's (`[serial]` in `board.toml`): both LOW is a chip reset under the
  open handle. esptool's default reset reaches the ROM loader and its default
  `hard_reset` (an RTS pulse) leaves it into the app; nothing has to be held.
- **Recovery:** hold BOOT (GPIO9) while plugging in, then flash. Ctrl-C on
  the serial port stops the store host at the REPL and Ctrl-D starts it again.
  A main.py written to the store's root does not replace the frozen one:
  MicroPython runs a frozen `main.py` before it looks at the filesystem.
- The UART0 REPL (TX GPIO21, RX GPIO20) stays on as the recovery console for
  an image whose USB has wedged.
- On a Super Mini the LED is GPIO8 (active LOW), a strapping pin.
- **A Super Mini's antenna is mismatched on many boards**: at full transmit
  power the access point never answers its authentication, and a join fails
  with reason 2 (`AUTH_EXPIRE`) where a lower power joins. The kernel's WiFi
  driver steps the power down by itself after such a refusal and remembers,
  per network, the power that got an address, so a board pays the search once
  (`native/moy_net/moy_net.h`, the station's transmit power). A board whose
  antenna is fine joins at full power as any other does.

## Free pins

The `/gpio` allowlist is the `gpio` lease row in `board.toml`, which the build
emits as `MOY_LEASE_GPIO_PINS`: GPIO0, GPIO1, GPIO3, GPIO4, GPIO5, GPIO6, GPIO7
and GPIO10. `machine.I2C(0)`
defaults to SDA GPIO5 and SCL GPIO6. Held back: the strapping pins 2, 8 and 9,
UART0's 20 and 21, the flash's 11–17 and USB's 18 and 19.

## Build, flash, look

```bash
make firmware-build-c3-zero
make firmware-flash-c3-zero PORT=/dev/ttyACM0
make firmware-monitor-c3-zero PORT=/dev/ttyACM0
```

`build.sh` runs from a worktree like every board's (`tools/worktree.py`), and
the browser console its image names is that tree's own (`firmware/web_runner/`),
which its loader fetches from that tree's `firmware/web_runner/serve.py` on
this machine's LAN address (`tools/gen_web_blob.py`, THE MIRRORS): run it
while a browser opens the board. `tools/board.py pass c3_zero` builds,
flashes and runs both Zeros' suite, `tests/test_zero_on_glass.py`, which
serves that pack and boots the console in headless Chrome. The
build fails when the image outgrows the factory slot (the #168 guard reads the
slot from this board's CSV). A flash that changes the table formats the store.
