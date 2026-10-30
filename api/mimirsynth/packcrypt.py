"""Password encryption of an exported brain package (#130).

Authenticated and streamed, so a package of several GB never sits in memory:

- The key comes from the password with scrypt (n=2**15, r=8, p=1) and a random salt.
- The content goes in 1 MiB chunks, each sealed with AES-256-GCM. A chunk's nonce is a random prefix plus its number, and its
  associated data binds the header, the number and whether it is the last one: chunks cannot be reordered, dropped or cut short.

Layout: `MAGIC`, a 4-byte big-endian length, the JSON header, then for each chunk a 4-byte length and the sealed bytes.

To decrypt outside the app: `python -m mimirsynth.packcrypt decrypt <in> <out>` (asks for the password, or reads
`MIMIRSYNTH_PACK_PASSWORD`; `-` as output writes to standard output).
"""
import base64
import json
import os
import struct
import sys

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"MSPACK1\n"
CHUNK = 1 << 20
MIN_PASSWORD = 12


class BadPassword(Exception):
    """Wrong password, or a package that was modified or cut short."""


def _key(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(password.encode("utf-8"))


def _aad(header: bytes, i: int, last: bool) -> bytes:
    return header + struct.pack(">QB", i, int(last))


def is_encrypted(path) -> bool:
    with open(path, "rb") as f:
        return f.read(len(MAGIC)) == MAGIC


def encrypt_file(src, dst, password: str, check=lambda: None) -> None:
    """`check` is called between chunks (a job uses it to stop when cancelled)."""
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"the password needs at least {MIN_PASSWORD} characters")
    salt, prefix = os.urandom(16), os.urandom(4)
    header = json.dumps({"kdf": "scrypt", "n": 2 ** 15, "r": 8, "p": 1, "salt": base64.b64encode(salt).decode(),
                         "nonce": base64.b64encode(prefix).decode(), "chunk": CHUNK}, sort_keys=True).encode()
    aes = AESGCM(_key(password, salt, 2 ** 15, 8, 1))
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        fo.write(MAGIC + struct.pack(">I", len(header)) + header)
        i, block = 0, fi.read(CHUNK)
        while True:
            check()
            nxt = fi.read(CHUNK)
            sealed = aes.encrypt(prefix + struct.pack(">Q", i), block, _aad(header, i, not nxt))
            fo.write(struct.pack(">I", len(sealed)) + sealed)
            if not nxt:
                break
            i, block = i + 1, nxt


def decrypt_file(src, dst, password: str) -> None:
    """`dst` is a path or a binary file already open."""
    if hasattr(dst, "write"):
        return _decrypt(src, dst, password)
    with open(dst, "wb") as fo:
        _decrypt(src, fo, password)


def _decrypt(src, fo, password: str) -> None:
    with open(src, "rb") as fi:
        if fi.read(len(MAGIC)) != MAGIC:
            raise ValueError("not an encrypted MimirSynth package")
        (hlen,) = struct.unpack(">I", fi.read(4))
        header = fi.read(hlen)
        h = json.loads(header)
        if h.get("kdf") != "scrypt":
            raise ValueError("unknown key derivation")
        aes = AESGCM(_key(password, base64.b64decode(h["salt"]), h["n"], h["r"], h["p"]))
        prefix = base64.b64decode(h["nonce"])
        i, head = 0, fi.read(4)
        if len(head) < 4:
            raise BadPassword()
        while True:
            (n,) = struct.unpack(">I", head)
            sealed = fi.read(n)
            head = fi.read(4)
            last = len(head) < 4
            try:
                fo.write(aes.decrypt(prefix + struct.pack(">Q", i), sealed, _aad(header, i, last)))
            except InvalidTag:
                raise BadPassword() from None
            if last:
                break
            i += 1


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] != "decrypt":
        print("usage: python -m mimirsynth.packcrypt decrypt <encrypted package> <output .tar.gz, or - for standard output>", file=sys.stderr)
        return 2
    password = os.environ.get("MIMIRSYNTH_PACK_PASSWORD")
    if password is None:
        import getpass
        password = getpass.getpass("Password: ")
    out = sys.stdout.buffer if argv[2] == "-" else argv[2]
    try:
        decrypt_file(argv[1], out, password)
    except BadPassword:
        if out is not sys.stdout.buffer:
            os.unlink(out)
        print("wrong password, or the package was modified or is incomplete", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
