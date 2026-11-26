# moy_leds: a board's RGB LEDs as the `leds` device API -- the driver
# (moy_leds.c, over the board's weak hooks), a compiled program's handles
# (moy_leds_dev.c) and the module `moy_leds` (modmoy_leds.c). moy_leds.h has
# the contract. The Makefile-port twin is micropython.mk.

add_library(usermod_moy_leds INTERFACE)

target_sources(usermod_moy_leds INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/moy_leds.c
    ${CMAKE_CURRENT_LIST_DIR}/moy_leds_dev.c
    ${CMAKE_CURRENT_LIST_DIR}/modmoy_leds.c
)

target_include_directories(usermod_moy_leds INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
    ${CMAKE_CURRENT_LIST_DIR}/../moy_kernel
)

target_link_libraries(usermod INTERFACE usermod_moy_leds)
