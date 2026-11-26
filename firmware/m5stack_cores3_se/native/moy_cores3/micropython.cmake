# moy_cores3: the CoreS3 SE's own chips (the AXP2101, the AW9523, the BM8563,
# the Faces Bottom3's bar); modmoy_cores3.c's header says what it serves.

add_library(usermod_moy_cores3 INTERFACE)

target_sources(usermod_moy_cores3 INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/modmoy_cores3.c
)

target_link_libraries(usermod INTERFACE usermod_moy_cores3)
