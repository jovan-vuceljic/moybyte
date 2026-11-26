// The harnesses' stand-in network: the kernel's station and lwIP as the
// shell's network commands reach them on a board (native/moy_net/moy_net.h,
// the shell's network commands), and the kernel's clock (moy_sh_now_us),
// linked into sh_main and board_main in their place, so a transcript holds
// the same lines on every run.
//
//   the station   its mode is the word in the files tree's /.net (under
//                 MOY_SH_ROOT), read at each look: with none it is up and
//                 connected to "home" (10.0.0.20/24, gateway and DNS
//                 10.0.0.1) whoever holds it, as a Zero's own station or a
//                 console's that SSH holds; `off`, down until held, then
//                 dialling "home" and connected from its third look; `alone`,
//                 down until held, then up with no network to dial
//   the hold      written to /.radio at each change: 1 held, 0 let go
//   names         router.lan (and every name that ends so) 10.0.0.1 and
//                 lossy.lan 10.0.0.3 answer at the second look, slow.lan
//                 10.0.0.1 at the tenth, a dotted quad at the first; every
//                 other is no such name
//   echoes        10.0.0.1 answers each at the second look, ttl 64; 10.0.0.3
//                 the odd ones; every other address none
//   the clock     3 days 4:05 after boot, 10 ms on at each look at the network

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define UP_US ((((3ull * 24u + 4u) * 60u) + 5u) * 60u * 1000000u)
#define LOOK_US 10000u

static uint64_t s_clock = UP_US;
static int s_held, s_dial;
static int s_q, s_q_looks, s_q_need;
static uint32_t s_q_ip;
static int s_echo, s_echo_looks;
static uint16_t s_echo_seq, s_echo_id;

static uint32_t ip4(unsigned a, unsigned b, unsigned c, unsigned d) {
    return a | b << 8 | c << 16 | (uint32_t)d << 24;
}

static FILE *open_at(const char *name, const char *how) {
    char p[1024];
    const char *root = getenv("MOY_SH_ROOT");
    snprintf(p, sizeof p, "%s/%s", root != NULL ? root : ".", name);
    return fopen(p, how);
}

// 0 up whoever holds it, 1 `off`, 2 `alone`
static int mode(void) {
    char w[16] = "";
    FILE *f = open_at(".net", "r");
    if (f != NULL) {
        if (fscanf(f, "%15s", w) != 1) {
            w[0] = '\0';
        }
        fclose(f);
    }
    return !strcmp(w, "off") ? 1 : !strcmp(w, "alone") ? 2 : 0;
}

long long moy_sh_now_us(void) {
    return (long long)s_clock;
}

int moy_wifi_shell_hold(int on) {
    s_held = on;
    s_dial = 0;
    FILE *f = open_at(".radio", "w");
    if (f != NULL) {
        fprintf(f, "%d\n", on);
        fclose(f);
    }
    return 0;
}

int moy_wifi_info(char ssid[33], uint32_t addr[4], uint8_t mac[6]) {
    static const uint8_t m[6] = { 0x02, 0x00, 0x00, 0x00, 0x1a, 0x2b };
    s_clock += LOOK_US;
    memcpy(mac, m, sizeof m);
    memset(addr, 0, 4 * sizeof addr[0]);
    snprintf(ssid, 33, "home");
    int md = mode();
    int st = md == 0 ? 3 : !s_held ? 0 : md == 2 ? 1 : ++s_dial >= 3 ? 3 : 2;
    if (st == 3) {
        addr[0] = ip4(10, 0, 0, 20);
        addr[1] = ip4(255, 255, 255, 0);
        addr[2] = addr[3] = ip4(10, 0, 0, 1);
    }
    return st;
}

int moy_net_resolve(const char *name) {
    unsigned a, b, c, d;
    char more;
    size_t n = strlen(name);
    s_q++;
    s_q_looks = 0;
    s_q_need = 2;
    s_q_ip = 0;
    if (sscanf(name, "%u.%u.%u.%u%c", &a, &b, &c, &d, &more) == 4 && (a | b | c | d) < 256u) {
        s_q_ip = ip4(a, b, c, d);
        s_q_need = 1;
    } else if (n >= 10 && !strcmp(name + n - 10, "router.lan")) {
        s_q_ip = ip4(10, 0, 0, 1);
    } else if (!strcmp(name, "slow.lan")) {
        s_q_ip = ip4(10, 0, 0, 1);
        s_q_need = 10;
    } else if (!strcmp(name, "lossy.lan")) {
        s_q_ip = ip4(10, 0, 0, 3);
    }
    return s_q;
}

int moy_net_resolved(int q, uint32_t *ip) {
    s_clock += LOOK_US;
    if (q != s_q) {
        return -EBUSY;
    }
    if (++s_q_looks < s_q_need) {
        return 0;
    }
    if (s_q_ip == 0) {
        return -ENOENT;
    }
    *ip = s_q_ip;
    return 1;
}

int moy_net_echo_open(void) {
    return 7;
}

int moy_net_echo_send(int fd, uint32_t ip, uint16_t id, uint16_t seq) {
    (void)fd;
    s_echo = ip == ip4(10, 0, 0, 1) || (ip == ip4(10, 0, 0, 3) && (seq & 1u));
    s_echo_seq = seq;
    s_echo_id = id;
    s_echo_looks = 0;
    return 0;
}

int moy_net_echo_recv(int fd, uint32_t ip, uint16_t id, uint16_t *seq, uint8_t *ttl) {
    (void)fd;
    (void)ip;
    s_clock += LOOK_US;
    if (!s_echo || id != s_echo_id || ++s_echo_looks < 2) {
        return 0;
    }
    s_echo = 0;
    *seq = s_echo_seq;
    *ttl = 64;
    return 64;
}

void moy_net_echo_close(int fd) {
    (void)fd;
}
