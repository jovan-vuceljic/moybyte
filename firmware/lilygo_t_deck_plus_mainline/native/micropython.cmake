# Moybyte T-Deck (mainline) USER_C_MODULES entry point.
#
# Every module this board compiles is SHARED -- its panel backend too
# (native/moy_lcd, one body with the CoreS3's) -- copied by build.sh from
# native/, which stays their single source of truth; .staged/ is gitignored.
#
# Stage 1 (panel bring-up) stages moy_gfx + moy_alloc only: the pixel kernel and
# the off-gc-heap DMA allocator are what a framebuffer needs, and everything
# else (moy_sd, moy_audio, moy_lua, moycore) rides the later stages. build.sh
# generates .staged/micropython.cmake listing whatever it staged, so this file
# does not have to be edited when a stage lands.
include(${CMAKE_CURRENT_LIST_DIR}/.staged/micropython.cmake)
