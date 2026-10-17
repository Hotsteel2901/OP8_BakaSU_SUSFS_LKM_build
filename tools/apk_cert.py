#!/usr/bin/env python3
"""Extract the first APK-v2 signer certificate from an APK.

The FinaSU kernel verifies the manager APK's signing certificate (DER size +
SHA-256), not the APK itself.  The CI needs those two values to build the LKM
so that the official FinaSU manager is recognised as the manager:

    KSU_EXPECTED_SIZE2=0x....
    KSU_EXPECTED_HASH2=<sha256>

This mirrors kernel/manager/apk_sign.c: it reads the APK Signing Block, the
v2 block (0x7109871a), the first signer, and the first certificate in that
signer's signed-data.

Usage:
    python3 tools/apk_cert.py path/to/manager.apk [--env]

With --env the result is printed as two KEY=VALUE lines suitable for
$GITHUB_ENV; diagnostics go to stderr.
"""

from __future__ import annotations

import hashlib
import struct
import sys

APK_SIG_BLOCK_MAGIC = b"APK Sig Block 42"
APK_SIGNATURE_SCHEME_V2_BLOCK_ID = 0x7109871A
# kernel/manager/apk_sign.c: #define CERT_MAX_LENGTH 1024
CERT_MAX_LENGTH = 1024


class ApkError(Exception):
    pass


def _u32(buf: bytes, off: int) -> int:
    if off < 0 or off + 4 > len(buf):
        raise ApkError(f"truncated uint32 at offset {off}")
    return struct.unpack_from("<I", buf, off)[0]


def _u64(buf: bytes, off: int) -> int:
    if off < 0 or off + 8 > len(buf):
        raise ApkError(f"truncated uint64 at offset {off}")
    return struct.unpack_from("<Q", buf, off)[0]


def _length_prefixed(buf: bytes, off: int, end: int) -> tuple[bytes, int]:
    """Read a uint32-length-prefixed value, bounded by *end*."""
    if off + 4 > end:
        raise ApkError(f"truncated length prefix at offset {off}")
    size = _u32(buf, off)
    start = off + 4
    stop = start + size
    if size > 0x7FFFFFFF or stop > end:
        raise ApkError(f"length-prefixed value overruns its container at {off}")
    return buf[start:stop], stop


def _find_eocd(buf: bytes) -> int:
    # The EOCD record is at the end, optionally followed by a comment.
    start = max(0, len(buf) - (22 + 0xFFFF))
    pos = buf.rfind(b"PK\x05\x06", start)
    if pos < 0:
        raise ApkError("not a ZIP/APK: end-of-central-directory record not found")
    comment_len = struct.unpack_from("<H", buf, pos + 20)[0]
    if pos + 22 + comment_len != len(buf):
        # Trailing garbage (e.g. a ZIP64 locator/comment) is suspicious.
        raise ApkError("EOCD record is not at the end of the file")
    return pos


def _apk_signing_block(buf: bytes, eocd: int) -> dict[int, bytes]:
    cd_offset = _u32(buf, eocd + 16)
    if cd_offset == 0xFFFFFFFF:
        raise ApkError("ZIP64 APKs are not supported by the Android v2 verifier")

    magic_off = cd_offset - len(APK_SIG_BLOCK_MAGIC)
    if magic_off < 0 or buf[magic_off:cd_offset] != APK_SIG_BLOCK_MAGIC:
        raise ApkError("APK Signing Block magic missing; APK is not v2-signed")

    # [uint64 size][pairs...][uint64 size][16-byte magic]
    tail_size = _u64(buf, magic_off - 8)
    block_start = cd_offset - tail_size - 8
    if block_start < 0 or _u64(buf, block_start) != tail_size:
        raise ApkError("APK Signing Block size fields disagree")

    pairs: dict[int, bytes] = {}
    pos = block_start + 8
    pairs_end = magic_off - 8
    while pos < pairs_end:
        pair_len = _u64(buf, pos)
        pos += 8
        if pair_len < 4 or pos + pair_len > pairs_end:
            raise ApkError("malformed APK Signing Block pair")
        block_id = _u32(buf, pos)
        pairs[block_id] = buf[pos + 4:pos + pair_len]
        pos += pair_len
    if pos != pairs_end:
        raise ApkError("APK Signing Block has trailing bytes")
    return pairs


def extract_v2_certificate(apk: bytes) -> bytes:
    eocd = _find_eocd(apk)
    pairs = _apk_signing_block(apk, eocd)
    v2 = pairs.get(APK_SIGNATURE_SCHEME_V2_BLOCK_ID)
    if v2 is None:
        raise ApkError(
            "APK has no v2 signature (0x7109871a); the FinaSU kernel only reads v2"
        )

    # v2: length-prefixed signers -> first signer -> signed data -> digests,
    # then certificates -> first certificate.  This is exactly the order
    # kernel/manager/apk_sign.c walks.
    signers, _ = _length_prefixed(v2, 0, len(v2))
    signer, _ = _length_prefixed(signers, 0, len(signers))
    signed_data, _ = _length_prefixed(signer, 0, len(signer))
    _digests, pos = _length_prefixed(signed_data, 0, len(signed_data))
    certs, _ = _length_prefixed(signed_data, pos, len(signed_data))
    cert, _ = _length_prefixed(certs, 0, len(certs))

    if not cert:
        raise ApkError("v2 signer has an empty certificate")
    if len(cert) > CERT_MAX_LENGTH:
        raise ApkError(
            f"certificate is {len(cert)} bytes, but the kernel's CERT_MAX_LENGTH is "
            f"{CERT_MAX_LENGTH}"
        )
    return cert


def main(argv: list[str]) -> int:
    env_mode = "--env" in argv
    args = [a for a in argv if a != "--env"]
    if len(args) != 2:
        print(f"usage: {args[0]} PATH_TO_APK [--env]", file=sys.stderr)
        return 2

    try:
        with open(args[1], "rb") as f:
            apk = f.read()
        cert = extract_v2_certificate(apk)
    except (OSError, ApkError) as exc:
        print(f"apk_cert: {exc}", file=sys.stderr)
        return 1

    size = len(cert)
    digest = hashlib.sha256(cert).hexdigest()
    if env_mode:
        print(f"KSU_EXPECTED_SIZE2=0x{size:04x}")
        print(f"KSU_EXPECTED_HASH2={digest}")
    else:
        print(f"certificate: {size} bytes (0x{size:04x})")
        print(f"sha256: {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
