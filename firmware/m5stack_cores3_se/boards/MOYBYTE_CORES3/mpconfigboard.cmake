# Moybyte M5Stack CoreS3 SE on mainline MicroPython: the T-Deck's one build
# strategy (plain mainline + USER_C_MODULES, no BOARD_VARIANT), with this S3's
# QUAD PSRAM: sdkconfig.spiram_sx alone, without the octal fragment.
set(IDF_TARGET esp32s3)

set(SDKCONFIG_DEFAULTS
    boards/sdkconfig.base
    boards/sdkconfig.ble
    boards/sdkconfig.spiram_sx
    boards/sdkconfig.240mhz
    ${MICROPY_BOARD_DIR}/sdkconfig.board
)

list(APPEND MICROPY_DEF_BOARD
    MICROPY_HW_BOARD_NAME="Moybyte CoreS3 SE (M5Stack CoreS3 SE + Faces Gamepad3)"
)
