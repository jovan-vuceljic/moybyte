"""RSA PKCS#1 v1.5 over SHA-256 in Python arithmetic: whether a signature
signs a digest under a public key, the whole decrypted block rebuilt and
compared, never a padding parser. The kernel's moy_ota_verify_digest
(native/moy_net/moy_ota.c) does it in C on a board and, through its ctypes
twin, on the host; this is where there is no kernel -- a page checking the
index mirror's signature (cart_index.check_signature with `keys`) and
moy_ota.verify_sig's host tools."""

# The ASN.1 DigestInfo header for SHA-256, fixed for the algorithm.
SHA256_DER = b"\x30\x31\x30\x0d\x06\x09\x60\x86\x48\x01\x65" \
             b"\x03\x04\x02\x01\x05\x00\x04\x20"


def verify_digest(digest, sig, keys):
    """True when `sig` (hex) signs the payload whose SHA-256 is `digest`
    under one of `keys`, ((modulus_hex, exponent), ...)."""
    if not sig or not keys:
        return False
    try:
        s = int(sig, 16)
    except (TypeError, ValueError):
        return False
    tail = SHA256_DER + bytes(digest)
    for mod_hex, exp in keys:
        try:
            n = int(mod_hex, 16)
        except (TypeError, ValueError):
            continue
        # From the hex, not n.bit_length(): MicroPython has no bit_length.
        k = (len(mod_hex) + 1) // 2
        if not 0 < s < n or k < len(tail) + 11:
            continue
        want = b"\x00\x01" + b"\xff" * (k - len(tail) - 3) + b"\x00" + tail
        try:
            got = pow(s, exp, n).to_bytes(k, "big")
        except (OverflowError, ValueError):
            continue
        if got == want:
            return True
    return False
