"""The one per-run isolation value.

A cache is keyed on the bytes of the prefix. Seeded, reproducible prefix bytes therefore collide with
whatever an earlier run left behind: a scramble control rerun inside the cache's lifetime reads the
entry the first run wrote, and an identity control's first request becomes a read instead of a write.
Every run draws one nonce here, records it, and places it ahead of everything it caches.

This is the ONLY source of non-seeded randomness in `src/`; `rng.make_rng` stays the only seeded
generator. tests/test_nonce.py greps for any other use of the OS source.
"""
import secrets


def new_nonce(n_bytes: int) -> str:
    """`n_bytes` of OS randomness as lowercase hex. The length comes from config, never from code."""
    if isinstance(n_bytes, bool) or not isinstance(n_bytes, int):
        raise TypeError(f"nonce length must be an int from config, got {type(n_bytes).__name__}")
    if n_bytes <= 0:
        raise ValueError(f"nonce length must be positive, got {n_bytes}; a run without a nonce is not isolated")
    return secrets.token_hex(n_bytes)
