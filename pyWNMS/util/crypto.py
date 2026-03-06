"""Password encryption / obfuscation.

Ports the Java ``Cryptography`` (DES) and ``CryptographyWnmsClassic``
(substitution cipher) classes.  The classic cipher is needed for
backward compatibility when importing R2 project files.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ---- DES-based cryptography (Java ``Cryptography``) --------------------

# Fixed DES key from the Java source
_DES_KEY = bytes([0xF1, 0x03, 0x5F, 0xE3, 0x09, 0x32, 0x89, 0xC1])

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as sym_padding
    _HAS_CRYPTO_LIB = True
except ImportError:
    _HAS_CRYPTO_LIB = False


class Cryptography:
    """DES/ECB/PKCS5 encryption matching the Java ``Cryptography`` class.

    Requires the ``cryptography`` package.  Falls back to plaintext
    passthrough if not installed.
    """

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string.

        :returns: Cipher-text as a latin-1 decoded string (raw bytes).
        """
        if not _HAS_CRYPTO_LIB:
            logger.warning("cryptography lib not available — no encryption")
            return plaintext
        padder = sym_padding.PKCS7(64).padder()
        padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
        cipher = Cipher(algorithms.TripleDES(_DES_KEY), modes.ECB())
        enc = cipher.encryptor()
        ct = enc.update(padded) + enc.finalize()
        return ct.decode("latin-1")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a cipher-text string back to plaintext."""
        if not _HAS_CRYPTO_LIB:
            return ciphertext
        cipher = Cipher(algorithms.TripleDES(_DES_KEY), modes.ECB())
        dec = cipher.decryptor()
        padded = dec.update(ciphertext.encode("latin-1")) + dec.finalize()
        unpadder = sym_padding.PKCS7(64).unpadder()
        return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")


# ---- Classic substitution cipher (``CryptographyWnmsClassic``) ---------

_ALLOWED = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    " !\"#¤%&/()=?+\\}][{@£$€|"
    "^~*'-_.:,;<>§½"
)

_CRYPT = (
    "QWERTYUIOPASDFGHJKLZXCVBNMqwertyui"
    "opasdfghjklzxcvbnm1234567890"
    " !\"#¤%&/()=?+\\}][{@£$€|"
    "^~*'-_.:,;<>§½"
)


class CryptographyWnmsClassic:
    """Legacy substitution cipher for R2 backward compatibility.

    This is NOT secure — it is simple obfuscation using fixed seeds and
    character-set rotation.  Ported from the Java source as-is.
    """

    def __init__(self) -> None:
        self._seed = 123456 % len(_ALLOWED)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt using the classic substitution cipher."""
        n = len(_ALLOWED)
        seed = self._seed

        # Encode seed and length
        result = ["="]
        result.append(_encode_int(seed, n))
        result.append(_encode_int(len(plaintext), n))

        for ch in plaintext:
            idx = _ALLOWED.find(ch)
            if idx < 0:
                # Character not in allowed set — emit unchanged
                result.append(ch)
            else:
                ci = (idx + seed) % n
                result.append(_CRYPT[ci])
            seed = (seed + 1) % n

        return "".join(result)

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt from the classic substitution cipher."""
        if not ciphertext or ciphertext[0] != "=":
            # Legacy format — not prefixed
            return ciphertext

        n = len(_ALLOWED)
        pos = 1
        seed, pos = _decode_int(ciphertext, pos, n)
        length, pos = _decode_int(ciphertext, pos, n)

        chars = []
        for i in range(length):
            if pos >= len(ciphertext):
                break
            ch = ciphertext[pos]
            pos += 1
            ci = _CRYPT.find(ch)
            if ci < 0:
                chars.append(ch)
            else:
                idx = (ci - seed) % n
                chars.append(_ALLOWED[idx])
            seed = (seed + 1) % n

        return "".join(chars)


def _encode_int(value: int, modulus: int) -> str:
    """Encode an integer as two substitution-cipher characters."""
    high = value // modulus
    low = value % modulus
    return _CRYPT[high] + _CRYPT[low]


def _decode_int(text: str, pos: int, modulus: int) -> tuple:
    """Decode two characters back to an integer."""
    high = _CRYPT.find(text[pos])
    low = _CRYPT.find(text[pos + 1])
    return high * modulus + low, pos + 2
