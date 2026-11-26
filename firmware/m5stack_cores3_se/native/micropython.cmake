# Moybyte M5Stack CoreS3 SE USER_C_MODULES entry point.
#
#   moy_cores3       -- board-authored, lives here: the board's own chips (the
#                       power manager, the IO expander, the clock chip, the
#                       Faces Bottom3's bar) and the panel's two board hooks.
#   .staged/*        -- the SHARED native modules, staged by build.sh from
#                       native/ per board.toml [native.shared]; the panel
#                       backend among them (native/moy_lcd, the T-Deck's).
include(${CMAKE_CURRENT_LIST_DIR}/moy_cores3/micropython.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/.staged/micropython.cmake)
