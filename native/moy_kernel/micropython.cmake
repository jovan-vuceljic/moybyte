# moy_kernel: the kernel's entry and its crash record (moy_kernel.c), its
# recovery floor (moy_recovery_floor.c) and task watchdog (moy_wd.c), its
# first light (moy_boot.c), the board's I2C bus (moy_bus.c), and the frame: the loop,
# the idle ladder, PERF and the dev channel (moy_loop.c, moy_idle.c,
# moy_perf.c, moy_devch.c, the module `moy_loop`), and the OS log (moy_log.c,
# the module `moy_log`), and the scheduler's callback guard (modmoy_guard.c,
# the module `moy_guard`, built where the board's mpconfigboard.h turns on
# MICROPY_ENABLE_VM_ABORT), and the lease table (moy_lease.c, the module
# `moy_lease`, offering the board's MOY_LEASE_ROWS) with a compiled program's
# device handles over it (moy_dev.c, its device APIs moy_dev_kinds.c) and the buses they drive
# (moy_devbus.c, the LEDC channels from moy_ledc.c's book), the writer lock moy_app's seqlock
# takes (moy_lock.c), and the process table
# (moy_proc.c, the Player's rows), and the service model's event queues,
# supervisor and VM call queue (moy_evq.c, moy_super.c, moy_vmq.c, the module
# `moy_evq`), and Improv Wi-Fi's frames on the USB-Serial/JTAG console
# (moy_improv.c, the module `moy_improv`, built where the board's
# mpconfigboard.h defines MOY_IMPROV). A board TAKES it in
# board.toml ([[native.shared.take]]), and taking it is what makes the kernel
# own app_main.
#
# The INTERFACE definitions reach every source of the main component
# (esp32_common.cmake links `usermod` into it), so MICROPY_ESP_IDF_ENTRY renames
# the port's app_main in ports/esp32/main.c; the link option reaches the
# executable through the same chain, and wraps the IDF's panic handler.

add_library(usermod_moy_kernel INTERFACE)

target_sources(usermod_moy_kernel INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/moy_kernel.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_recovery_floor.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_wd.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_kmem.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_platform.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_tasks.c
    ${CMAKE_CURRENT_LIST_DIR}/modmoy_kernel.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_crash.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_recovery.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_boot.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_bus.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_loop.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_idle.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_perf.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_devch.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_log.c
    ${CMAKE_CURRENT_LIST_DIR}/modmoy_log.c
    ${CMAKE_CURRENT_LIST_DIR}/modmoy_loop.c
    ${CMAKE_CURRENT_LIST_DIR}/modmoy_guard.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_loop_board.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_lease.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_dev.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_dev_kinds.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_devbus.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_ledc.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_lock.c
    ${CMAKE_CURRENT_LIST_DIR}/modmoy_lease.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_proc.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_evq.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_super.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_vmq.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_screen_slot.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_status.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_notes.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_items.c
    ${CMAKE_CURRENT_LIST_DIR}/modmoy_evq.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_improv.c
    ${CMAKE_CURRENT_LIST_DIR}/modmoy_improv.c
)

target_include_directories(usermod_moy_kernel INTERFACE ${CMAKE_CURRENT_LIST_DIR})

target_compile_definitions(usermod_moy_kernel INTERFACE
    MICROPY_ESP_IDF_ENTRY=mp_port_app_main
)

target_link_options(usermod_moy_kernel INTERFACE "-Wl,--wrap=esp_panic_handler")

# The float functions every tier computes alike (README.md, THE FLOAT
# FUNCTIONS): MicroPython's lib/libm in place of newlib's, a target of its own
# so -ffp-contract=off reaches its objects alone (a usermod's sources are
# compiled by the micropython.elf target, which no source property reaches).
set(MOY_LIBM math atan2f atanf asinfacosf log1pf asinhf acoshf atanhf
    sf_sin sf_cos sf_tan kf_sin kf_cos kf_tan ef_rem_pio2 kf_rem_pio2
    sf_erf erf_lgamma wf_lgamma wf_tgamma)
list(TRANSFORM MOY_LIBM PREPEND ${MICROPY_DIR}/lib/libm/)
list(TRANSFORM MOY_LIBM APPEND .c)
add_library(moy_libm STATIC ${MOY_LIBM})
idf_build_get_property(_moy_libm_opts COMPILE_OPTIONS GENERATOR_EXPRESSION)
idf_build_get_property(_moy_libm_copts C_COMPILE_OPTIONS GENERATOR_EXPRESSION)
target_compile_options(moy_libm PRIVATE
    "${_moy_libm_opts}" ${_moy_libm_copts} -ffp-contract=off -Wno-sign-compare
    -Wno-maybe-uninitialized)
target_link_libraries(usermod_moy_kernel INTERFACE moy_libm)
# log2 is the math module's own, log(x) times 1/ln 2 (micropython.mk says
# it for the unix and webassembly ports).
target_compile_definitions(usermod_moy_kernel INTERFACE MP_NEED_LOG2=1)

target_link_libraries(usermod INTERFACE usermod_moy_kernel)
