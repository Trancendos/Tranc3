"""
shamir.py — Shamir's Secret Sharing for the Tranc3 platform.

Pure-Python implementation using GF(prime) with the 521-bit Mersenne prime (2^521 - 1).
Zero external dependencies beyond the standard library.

Used by: The Void (vault unseal), Infinity (master key split)
"""

from __future__ import annotations

import secrets

# ---------------------------------------------------------------------------
# Prime field: GF(p) where p = 2^521 - 1  (Mersenne prime, 521 bits)
# ---------------------------------------------------------------------------
_PRIME: int = (1 << 521) - 1


def _mod_inv(a: int, p: int) -> int:
    """Modular inverse using Fermat's little theorem (p is prime)."""
    return pow(a, p - 2, p)


def _eval_poly(coeffs: list[int], x: int, p: int) -> int:
    """Evaluate polynomial at x in GF(p) using Horner's method."""
    result = 0
    for c in reversed(coeffs):
        result = (result * x + c) % p
    return result


def _lagrange_interpolate(shares: list[tuple[int, int]], p: int) -> int:
    """Lagrange interpolation over GF(p) — recovers the constant term (secret)."""
    k = len(shares)
    secret = 0
    for i in range(k):
        xi, yi = shares[i]
        num = 1
        den = 1
        for j in range(k):
            if i == j:
                continue
            xj = shares[j][0]
            num = (num * (-xj)) % p
            den = (den * (xi - xj)) % p
        secret = (secret + yi * _mod_inv(den, p) % p * num) % p
    return secret


def _int_to_bytes(n: int, length: int) -> bytes:
    return n.to_bytes(length, "big")


def _bytes_to_int(b: bytes) -> int:
    return int.from_bytes(b, "big")


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------


class ShamirSecretSharing:
    """
    Shamir's Secret Sharing over GF(2^521 - 1).

    Example::

        sss = ShamirSecretSharing()
        shares = sss.split(b'my secret', n=5, k=3)
        recovered = sss.combine(shares[:3])
        assert recovered == b'my secret'
    """

    def __init__(self, prime: int = _PRIME) -> None:
        self._prime = prime
        self._prime_bytes = (prime.bit_length() + 7) // 8

    def split(self, secret: bytes, n: int, k: int) -> list[tuple[int, bytes]]:
        """
        Split *secret* into *n* shares, any *k* of which reconstruct it.

        Returns list of (x, share_bytes).
        Raises ValueError for invalid parameters.
        """
        if k < 2:
            raise ValueError("k (threshold) must be >= 2")
        if n < k:
            raise ValueError("n must be >= k")
        if not secret:
            raise ValueError("secret must be non-empty")
        max_bytes = self._prime_bytes - 1
        if len(secret) > max_bytes:
            raise ValueError(f"secret too large: max {max_bytes} bytes, got {len(secret)}")

        # Encode: prepend 0x01 marker so leading-zero secrets survive round-trip
        padded = (b"\x01" + secret).ljust(self._prime_bytes, b"\x00")
        secret_int = _bytes_to_int(padded) % self._prime

        coeffs = [secret_int] + [secrets.randbelow(self._prime) for _ in range(k - 1)]

        return [
            (x, _int_to_bytes(_eval_poly(coeffs, x, self._prime), self._prime_bytes))
            for x in range(1, n + 1)
        ]

    def combine(self, shares: list[tuple[int, bytes]]) -> bytes:
        """
        Reconstruct secret from *k* or more (x, share_bytes) tuples.
        Returns the original secret bytes.
        """
        if len(shares) < 2:
            raise ValueError("Need at least 2 shares")

        x_coords = [x for x, _ in shares]
        if len(set(x_coords)) != len(x_coords):
            raise ValueError("Duplicate shares detected")
        if any(x <= 0 for x in x_coords):
            raise ValueError("Invalid share coordinate: x must be > 0")

        int_shares = [(x, _bytes_to_int(y)) for x, y in shares]
        secret_int = _lagrange_interpolate(int_shares, self._prime)

        padded = _int_to_bytes(secret_int, self._prime_bytes)
        if padded[0:1] != b"\x01":
            raise ValueError("Reconstruction failed: invalid marker (wrong shares?)")
        return padded[1:].rstrip(b"\x00") or b"\x00"

    def split_hex(self, secret_hex: str, n: int, k: int) -> list[str]:
        """Split a hex-encoded secret; return shares as '<x_hex>:<y_hex>' strings."""
        raw = self.split(bytes.fromhex(secret_hex), n, k)
        return [f"{x:04x}:{y.hex()}" for x, y in raw]

    def combine_hex(self, shares_hex: list[str]) -> str:
        """Combine '<x_hex>:<y_hex>' shares and return the hex-encoded secret."""
        parsed = [
            (int(s.split(":", 1)[0], 16), bytes.fromhex(s.split(":", 1)[1])) for s in shares_hex
        ]
        return self.combine(parsed).hex()


# ---------------------------------------------------------------------------
# Convenience helpers for The Void master key
# ---------------------------------------------------------------------------

_SSS = ShamirSecretSharing()


def split_master_key(
    master_key_hex: str,
    total_shares: int = 5,
    threshold: int = 3,
) -> list[str]:
    """Split The Void master key into *total_shares* hex shares (any *threshold* reconstruct)."""
    return _SSS.split_hex(master_key_hex, n=total_shares, k=threshold)


def reconstruct_master_key(shares: list[str]) -> str:
    """Reconstruct The Void master key from *threshold* or more hex shares."""
    return _SSS.combine_hex(shares)


# ---------------------------------------------------------------------------
# Self-test (python -m src.security.shamir  or  python shamir.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Running Shamir Secret Sharing self-test...")

    sss = ShamirSecretSharing()
    secret = b"super_secret_vault_master_key_32"
    shares = sss.split(secret, n=5, k=3)
    assert len(shares) == 5
    assert sss.combine(shares[:3]) == secret
    print("  [PASS] 3-of-5 first-3 reconstruction")

    assert sss.combine([shares[1], shares[3], shares[4]]) == secret
    print("  [PASS] non-contiguous shares")

    mk = secrets.token_hex(32)
    mk_shares = split_master_key(mk, total_shares=5, threshold=3)
    assert reconstruct_master_key(mk_shares[:3]) == mk
    print("  [PASS] master-key helpers")

    print("All self-tests PASSED.")
