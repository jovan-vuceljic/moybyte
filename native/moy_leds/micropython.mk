# Makefile-port glue for moy_leds -- the twin of micropython.cmake, for the
# unix port (tests) and the webassembly runner, neither of which has LEDs.

MOY_LEDS_MOD_DIR := $(USERMOD_DIR)

SRC_USERMOD_C += $(MOY_LEDS_MOD_DIR)/modmoy_leds.c
SRC_USERMOD_LIB_C += $(MOY_LEDS_MOD_DIR)/moy_leds.c $(MOY_LEDS_MOD_DIR)/moy_leds_dev.c
CFLAGS_USERMOD += -I$(MOY_LEDS_MOD_DIR) -I$(MOY_LEDS_MOD_DIR)/../moy_kernel
