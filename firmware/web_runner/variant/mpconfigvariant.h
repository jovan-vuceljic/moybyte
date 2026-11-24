// Moybyte web runner variant (#151), modeled on the pyscript variant (the
// production browser deployment shape):
//  - SPLIT_HEAP_AUTO: gc collections DEFER to the JS<->Python call boundary
//    (external_call_depth == 0), so no emscripten_scan_registers -> no ASYNCIFY.
//    For the runner that lands collections between FRAMES -- the same
//    frame-boundary pattern the device loop uses.
//  - no periodic mp_js_hook (node REPL Ctrl-C plumbing; a call every 10 VM ops).
#define MICROPY_CONFIG_ROM_LEVEL                (MICROPY_CONFIG_ROM_LEVEL_FULL_FEATURES)
#define MICROPY_GC_SPLIT_HEAP                   (1)
#define MICROPY_GC_SPLIT_HEAP_AUTO              (1)
#define MICROPY_PY_WEAKREF                      (1)
#define MICROPY_VARIANT_ENABLE_JS_HOOK          (0)
// The object model every board that can hold a link runs (#256): REPR_C over
// wasm32's 32-bit word with single-precision floats, so a float is folded into
// the object word as the boards fold it and a page computes the same 30-bit
// results a board does. Float width is part of the lockstep contract
// (docs/netplay_v1.md section 5). The port states its float width unguarded;
// build.sh puts that line under #ifndef so this one decides.
#define MICROPY_OBJ_REPR                        (MICROPY_OBJ_REPR_C)
#define MICROPY_FLOAT_IMPL                      (MICROPY_FLOAT_IMPL_FLOAT)
