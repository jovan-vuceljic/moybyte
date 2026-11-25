// moy_strtof: the Lua VM's number reader (luaconf.h's lua_str2number and
// lua_strx2number), correctly rounded on every tier.
//
// A Lua cart's numerals and `tonumber` reach the C library's strtof, and the
// C libraries part: newlib's (the boards') reads a double and rounds that to a
// float, so a literal near a float's halfway point rounds twice and can land
// one bit from musl's (the wasm) and glibc's (the R32 build), which round
// once. A match's two sides must hold the same bits (docs/netplay_v1.md §5),
// so every tier reads numbers here instead: integer arithmetic only, the
// exact value D * 10^e10 * 2^p2 divided out to 25 bits and a sticky bit, then
// rounded half to even.
//
// It reads what strtof reads but for infinities and NaNs, which Lua refuses
// before it calls (lobject.c, l_str2d): leading space, a sign, decimal digits
// with a point and an e exponent, or 0x hex digits with a point and a p
// exponent. Out of range it gives an infinity or a zero, as strtof does, and
// leaves errno alone, which Lua does not read.

#include <stdint.h>
#include <string.h>

#define KEEP 128        // significant digits kept; a float's halfway point has fewer
#define WORDS 28        // 896 bits: the widest dividend is ~610

typedef struct {
    uint32_t w[WORDS];
    int n;              // words in use, the top one nonzero (0: the value 0)
} big_t;

static void big_set(big_t *b, uint32_t v)
{
    memset(b->w, 0, sizeof b->w);
    b->w[0] = v;
    b->n = v != 0;
}

static void big_mul_add(big_t *b, uint32_t m, uint32_t a)
{
    uint64_t carry = a;
    for (int i = 0; i < b->n; i++) {
        carry += (uint64_t)b->w[i] * m;
        b->w[i] = (uint32_t)carry;
        carry >>= 32;
    }
    if (carry) b->w[b->n++] = (uint32_t)carry;
}

static void big_pow10(big_t *b, int e)
{
    for (; e >= 9; e -= 9) big_mul_add(b, 1000000000u, 0);
    static const uint32_t p10[9] = {1, 10, 100, 1000, 10000, 100000, 1000000,
                                    10000000, 100000000};
    if (e > 0) big_mul_add(b, p10[e], 0);
}

static int big_bits(const big_t *b)
{
    if (b->n == 0) return 0;
    uint32_t top = b->w[b->n - 1];
    int k = 0;
    while (top) { k++; top >>= 1; }
    return (b->n - 1) * 32 + k;
}

static void big_shl(big_t *b, int s)
{
    if (b->n == 0 || s == 0) return;
    int ws = s / 32, bs = s % 32;
    for (int i = b->n - 1 + ws + 1; i >= 0; i--) {
        uint32_t hi = (i - ws >= 0 && i - ws < b->n) ? b->w[i - ws] : 0;
        uint32_t lo = (i - ws - 1 >= 0 && i - ws - 1 < b->n) ? b->w[i - ws - 1] : 0;
        b->w[i] = bs ? (hi << bs) | (lo >> (32 - bs)) : hi;
    }
    b->n += ws + 1;
    while (b->n && b->w[b->n - 1] == 0) b->n--;
}

static void big_shr1(big_t *b)
{
    for (int i = 0; i < b->n; i++)
        b->w[i] = (b->w[i] >> 1) | (i + 1 < b->n ? b->w[i + 1] << 31 : 0);
    while (b->n && b->w[b->n - 1] == 0) b->n--;
}

static int big_cmp(const big_t *a, const big_t *b)
{
    if (a->n != b->n) return a->n < b->n ? -1 : 1;
    for (int i = a->n - 1; i >= 0; i--)
        if (a->w[i] != b->w[i]) return a->w[i] < b->w[i] ? -1 : 1;
    return 0;
}

static void big_sub(big_t *a, const big_t *b)      // a -= b, a >= b
{
    int64_t borrow = 0;
    for (int i = 0; i < a->n; i++) {
        int64_t d = (int64_t)a->w[i] - (i < b->n ? b->w[i] : 0) - borrow;
        borrow = d < 0;
        a->w[i] = (uint32_t)d;
    }
    while (a->n && a->w[a->n - 1] == 0) a->n--;
}

static int digit(int c, int hex)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (hex && c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (hex && c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

float moy_strtof(const char *s, char **end)
{
    const char *p = s;
    while (*p == ' ' || (*p >= '\t' && *p <= '\r')) p++;
    int neg = 0;
    if (*p == '+' || *p == '-') neg = *p++ == '-';
    int hex = p[0] == '0' && (p[1] == 'x' || p[1] == 'X')
              && (digit(p[2], 1) >= 0 || (p[2] == '.' && digit(p[3], 1) >= 0));
    if (hex) p += 2;
    int base = hex ? 16 : 10;

    // value = D * base^e (e counts digits) * 2^p2; D keeps KEEP digits.
    big_t num, den;
    big_set(&num, 0);
    int nd = 0, e = 0, any = 0, point = 0, sticky = 0;
    uint32_t chunk = 0, scale = 1;
    for (;; p++) {
        if (*p == '.' && !point) { point = 1; continue; }
        int d = digit(*p, hex);
        if (d < 0) break;
        any = 1;
        if (nd == 0 && d == 0) {
            e -= point;
        } else if (nd < KEEP) {
            chunk = chunk * base + d;
            scale *= base;
            if (scale >= 100000000u) { big_mul_add(&num, scale, chunk); chunk = 0; scale = 1; }
            nd++;
            e -= point;
        } else {
            e += !point;
            sticky |= d != 0;
        }
    }
    if (!any) {
        if (end) *end = (char *)s;
        return 0.0f;
    }
    if (sticky) {               // past the kept digits: a nonzero tail, as one more digit
        chunk = chunk * base + 1;
        scale *= base;
        nd++;
        e--;
    }
    big_mul_add(&num, scale, chunk);

    int x = 0;
    char ec = hex ? 'p' : 'e';
    if ((*p | 0x20) == ec) {
        const char *q = p + 1;
        int xneg = 0;
        if (*q == '+' || *q == '-') xneg = *q++ == '-';
        if (digit(*q, 0) >= 0) {
            for (; digit(*q, 0) >= 0; q++)
                if (x < 100000) x = x * 10 + digit(*q, 0);
            if (xneg) x = -x;
            p = q;
        }
    }
    if (end) *end = (char *)p;

    union { uint32_t u; float f; } out;
    out.u = (uint32_t)neg << 31;
    if (num.n == 0) return out.f;

    int p2 = 0, e10 = 0;
    if (hex) p2 = 4 * e + x;
    else e10 = e + x;
    // The value's size, from its digits: past either end of the floats.
    int mag = hex ? 4 * nd + p2 : nd + e10;
    if (hex ? mag > 129 + 4 : mag > 39) { out.u |= 0x7f800000u; return out.f; }
    if (hex ? mag < -151 : mag < -46) return out.f;

    big_set(&den, 1);
    if (e10 > 0) big_pow10(&num, e10);
    if (e10 < 0) big_pow10(&den, -e10);

    // q = floor(value * 2^k): 25 bits, the float's 24 and a round bit, or
    // fewer at k = 150, where the float is subnormal.
    int k = 25 - (big_bits(&num) - big_bits(&den) + p2);
    if (k > 150) k = 150;
    uint32_t q;
    big_t n, d;
    for (;;) {
        n = num;
        d = den;
        int sh = k + p2;
        if (sh > 0) big_shl(&n, sh);
        else big_shl(&d, -sh);
        big_shl(&d, 26);
        q = 0;
        for (int b = 26; b >= 0; b--) {
            if (big_cmp(&n, &d) >= 0) { big_sub(&n, &d); q |= 1u << b; }
            big_shr1(&d);
        }
        if (q >= 1u << 25) { k--; continue; }
        if (q < 1u << 24 && k < 150) { k++; continue; }
        break;
    }
    uint32_t mant = q >> 1;
    if ((q & 1) && (n.n != 0 || (mant & 1))) mant++;
    // value = mant * 2^(1 - k). A normal mant's hidden bit, 2^23, adds the
    // last one to the exponent field (151 - k); a subnormal's (k = 150, mant
    // under 2^23) leaves it 0; a rounding that carries mant to 2^24 carries
    // into the exponent, up to the infinity's.
    uint32_t bits = ((uint32_t)(150 - k) << 23) + mant;
    if (bits >= 0x7f800000u) bits = 0x7f800000u;
    out.u |= bits;
    return out.f;
}
