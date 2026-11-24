// The radio link's host half (moy_link.h) for a board twin built on the host
// (tests/test_live_link.py): ESP-NOW is a UDP "air" a test runs, which
// carries each frame to the twins and consoles on it, and drops or delays
// what the test says.
//
//   MOY_AIR        the air's UDP port on 127.0.0.1 (no air: the link refuses to start)
//   MOY_AIR_MAC    this twin's station MAC, 12 hex digits
//   MOY_AIR_CH     the channel its station is associated on (default 1)
//
// A twin's datagram to the air is its MAC, the destination's and the
// payload; the air's to a twin is the sender's MAC and the payload. A start
// says "REG" and the twin's MAC, so the air knows where the twin listens.

#if defined(MOY_NET_LINK) && MOY_NET_LINK && !defined(ESP_PLATFORM)

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include "moy_link.h"

static int s_fd = -1;
static int s_up;
static struct sockaddr_in s_air;
static uint32_t s_rx, s_drops;

static void env_mac(uint8_t mac[6]) {
    const char *h = getenv("MOY_AIR_MAC");
    memset(mac, 0, 6);
    for (int i = 0; h != NULL && i < 6 && h[2 * i] && h[2 * i + 1]; i++) {
        char b[3] = {h[2 * i], h[2 * i + 1], 0};
        mac[i] = (uint8_t)strtoul(b, NULL, 16);
    }
}

void moy_link_mac(uint8_t mac[6]) {
    env_mac(mac);
}

int moy_link_start(uint32_t rxbuf) {
    (void)rxbuf;
    if (s_up) {
        return 0;
    }
    const char *port = getenv("MOY_AIR");
    if (port == NULL) {
        return -1;
    }
    if (s_fd < 0) {
        s_fd = socket(AF_INET, SOCK_DGRAM, 0);
        if (s_fd < 0) {
            return -1;
        }
        fcntl(s_fd, F_SETFL, fcntl(s_fd, F_GETFL) | O_NONBLOCK);
        memset(&s_air, 0, sizeof s_air);
        s_air.sin_family = AF_INET;
        s_air.sin_port = htons((uint16_t)atoi(port));
        s_air.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    }
    uint8_t reg[9] = {'R', 'E', 'G'};
    env_mac(reg + 3);
    sendto(s_fd, reg, sizeof reg, 0, (struct sockaddr *)&s_air, sizeof s_air);
    s_up = 1;
    return 0;
}

void moy_link_stop(void) {
    if (s_up && s_fd >= 0) {
        uint8_t bye[9] = {'B', 'Y', 'E'};
        env_mac(bye + 3);
        sendto(s_fd, bye, sizeof bye, 0, (struct sockaddr *)&s_air, sizeof s_air);
    }
    s_up = 0;
}

int moy_link_rate(int rate) {
    (void)rate;
    return 0;
}

int moy_link_channel(int set) {
    (void)set;
    const char *c = getenv("MOY_AIR_CH");
    int ch = c != NULL ? atoi(c) : 1;
    return -ch;
}

int moy_link_add_peer(const uint8_t mac[6]) {
    (void)mac;
    return 0;
}

uint32_t moy_link_frame_max(void) {
    return MOY_LINK_MAX;
}

int moy_link_send(const uint8_t mac[6], const uint8_t *data, size_t len) {
    if (!s_up || len > MOY_LINK_MAX) {
        return -1;
    }
    uint8_t b[12 + MOY_LINK_MAX];
    env_mac(b);
    memcpy(b + 6, mac, 6);
    memcpy(b + 12, data, len);
    return sendto(s_fd, b, 12 + len, 0, (struct sockaddr *)&s_air, sizeof s_air) < 0 ? -1 : 0;
}

int moy_link_recv(uint8_t mac[6], uint8_t *data, uint32_t cap) {
    if (!s_up) {
        return -1;
    }
    uint8_t b[6 + MOY_LINK_MAX];
    ssize_t n = recv(s_fd, b, sizeof b, 0);
    if (n < 6) {
        return -1;
    }
    s_rx++;
    memcpy(mac, b, 6);
    size_t len = (size_t)n - 6;
    memcpy(data, b + 6, len < cap ? len : cap);
    return (int)(len < cap ? len : cap);
}

void moy_link_stats(moy_link_stats_t *s) {
    memset(s, 0, sizeof *s);
    s->rx = s_rx;
    s->drops = s_drops;
    s->up = s_up;
}

#endif
