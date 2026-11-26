# moy_net for the unix and webassembly ports: the twin of micropython.cmake.
# Its JSON scanner is native/moy_spine/moy_json.c and its store
# native/moy_store, both of which moy_store compiles. A port that sets
# MOY_NET_SERVE=0 (the browser's variant) builds the sync codec and apply
# alone, with moy_http.c's UTF-8 check they share (modmoy_net.c's header).

MOY_NET_DIR := $(USERMOD_DIR)

SRC_USERMOD_C += $(MOY_NET_DIR)/modmoy_net.c
SRC_USERMOD_LIB_C += $(MOY_NET_DIR)/moy_http.c $(MOY_NET_DIR)/moy_sync.c $(MOY_NET_DIR)/moy_sync_apply.c
# The sign-in's crypto over the vendored mbedTLS (mbedtls/README.md): the
# browser's client end (moy_seal_web.c) on every port, the board's end with
# the webhost; and the crypto rows' body (moy_crypto.c), which native/moy_app's
# door calls, its Ed25519 the vendored Monocypher's (monocypher/README.md).
SRC_USERMOD_LIB_C += $(MOY_NET_DIR)/moy_seal.c $(MOY_NET_DIR)/moy_seal_web.c $(MOY_NET_DIR)/moy_crypto.c \
    $(wildcard $(MOY_NET_DIR)/mbedtls/library/*.c) \
    $(MOY_NET_DIR)/monocypher/monocypher.c $(MOY_NET_DIR)/monocypher/monocypher-ed25519.c
CFLAGS_USERMOD += -I$(MOY_NET_DIR)/mbedtls/include -I$(MOY_NET_DIR)/monocypher -DMBEDTLS_CONFIG_FILE='"moy_seal_mbedtls.h"'
ifeq ($(MOY_NET_SERVE),0)
CFLAGS_USERMOD += -DMOY_NET_SERVE=0
# The browser's radio is its board's, over the live socket (moy_link_web.c):
# the kernel's link (native/moy_play/moy_match_kernel.c) rides it.
CFLAGS_USERMOD += -DMOY_NET_LINK=1 -DMOY_NET_LIVE_PAGE=1
SRC_USERMOD_LIB_C += $(MOY_NET_DIR)/moy_link_web.c $(MOY_NET_DIR)/moy_dev_web.c $(MOY_NET_DIR)/moy_svc_web.c
else
SRC_USERMOD_LIB_C += $(MOY_NET_DIR)/moy_net_port.c $(MOY_NET_DIR)/moy_wifi.c $(MOY_NET_DIR)/moy_link.c \
    $(MOY_NET_DIR)/moy_webhost.c $(MOY_NET_DIR)/moy_webauth.c $(MOY_NET_DIR)/moy_live.c $(MOY_NET_DIR)/moy_live_dev.c $(MOY_NET_DIR)/moy_live_svc.c $(MOY_NET_DIR)/moy_ota.c $(MOY_NET_DIR)/moy_page.c $(MOY_NET_DIR)/moy_webconsole.c $(MOY_NET_DIR)/moy_gpio.c $(MOY_NET_DIR)/moy_dns.c \
    $(MOY_NET_DIR)/moy_fetch.c $(MOY_NET_DIR)/moy_fetch_dev.c $(MOY_NET_DIR)/moy_aes.c $(MOY_NET_DIR)/moy_lorawan.c $(MOY_NET_DIR)/moy_lora.c \
    $(MOY_NET_DIR)/moy_lora_dev.c
SRC_USERMOD_C += $(MOY_NET_DIR)/modmoy_http.c $(MOY_NET_DIR)/modmoy_lora.c
endif
CFLAGS_USERMOD += -I$(MOY_NET_DIR) -I$(MOY_NET_DIR)/../moy_spine -I$(MOY_NET_DIR)/../moy_store -I$(MOY_NET_DIR)/../moy_web -I$(MOY_NET_DIR)/../moy_input
# A generated face (gen_os, *_face.h) holds names only its includer uses, and
# the qstr pass re-scans a source only when that source changed: a face that
# changes alone re-scans every source, as a QSTR_GLOBAL_DEPENDENCIES entry.
QSTR_GLOBAL_DEPENDENCIES += $(wildcard $(MOY_NET_DIR)/*_face.h)
