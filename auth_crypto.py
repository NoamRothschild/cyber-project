"""
Hybrid RSA + AES-GCM encryption for secure channels between clients and servers.
Use from any directory: load keys by path, encrypt/decrypt with key objects.
"""
from __future__ import annotations

import os
import struct
from pathlib import Path
from typing import Callable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend

# Wire format: [2 bytes big-endian len(encrypted_key)][encrypted_aes_key][12 bytes nonce][aes_gcm_ciphertext]
_NONCE_SIZE = 12
_LEN_ENC_KEY_SIZE = 2


def load_private_key(path: Path):
    """Load an RSA private key from a PEM file. path: full path to the .pem file."""
    data = path.read_bytes()
    return serialization.load_pem_private_key(data, password=None, backend=default_backend())


def load_public_key(path: Path):
    """Load an RSA public key from a PEM file. path: full path to the .pem file."""
    data = path.read_bytes()
    return serialization.load_pem_public_key(data, backend=default_backend())


def encrypt_for_recipient(plaintext: bytes, recipient_public_key) -> bytes:
    """Encrypt plaintext with a one-time AES key, then encrypt that key with recipient's RSA public key."""
    aes_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(aes_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    encrypted_key = recipient_public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return struct.pack(">H", len(encrypted_key)) + encrypted_key + nonce + ciphertext


def decrypt_from_sender(ciphertext: bytes, our_private_key) -> bytes:
    """Decrypt hybrid ciphertext using our RSA private key."""
    if len(ciphertext) < _LEN_ENC_KEY_SIZE:
        raise ValueError("ciphertext too short")
    (enc_key_len,) = struct.unpack(">H", ciphertext[: _LEN_ENC_KEY_SIZE])
    offset = _LEN_ENC_KEY_SIZE
    enc_key = ciphertext[offset : offset + enc_key_len]
    offset += enc_key_len
    nonce = ciphertext[offset : offset + _NONCE_SIZE]
    offset += _NONCE_SIZE
    aes_ciphertext = ciphertext[offset:]

    aes_key = our_private_key.decrypt(
        enc_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    aesgcm = AESGCM(aes_key)
    return aesgcm.decrypt(nonce, aes_ciphertext, None)


def receive_and_decrypt(
    recv: Callable[[int], bytes],
    our_private_key,
    *,
    length_prefix_bytes: int = 4,
) -> bytes:
    """
    Read a length-prefixed encrypted message and return the decrypted payload.

    Uses recv(n) to read bytes (e.g. sock.recv). Reads length_prefix_bytes to get
    the payload length (big-endian), then reads that many bytes (handles short
    reads), then decrypts with our_private_key and returns plaintext.

    Raises ValueError if the stream ends before the full message is read.
    """
    length_prefix = b""
    while len(length_prefix) < length_prefix_bytes:
        chunk = recv(length_prefix_bytes - len(length_prefix))
        if not chunk:
            raise ValueError("stream ended before length prefix")
        length_prefix += chunk
    msg_len = int.from_bytes(length_prefix, "big")

    raw = b""
    while len(raw) < msg_len:
        chunk = recv(min(msg_len - len(raw), 65536))
        if not chunk:
            raise ValueError("stream ended before full message")
        raw += chunk
    return decrypt_from_sender(raw, our_private_key)


def encrypt_and_prefix(
    plaintext: bytes,
    recipient_public_key,
    *,
    length_prefix_bytes: int = 4,
) -> bytes:
    """
    Encrypt plaintext for the recipient and prefix with a length (big-endian).
    Returns the full blob to send (length + ciphertext). Use with sendall() or UDP sendto().
    """
    ciphertext = encrypt_for_recipient(plaintext, recipient_public_key)
    return len(ciphertext).to_bytes(length_prefix_bytes, "big") + ciphertext


def decrypt_length_prefixed(
    packet: bytes,
    our_private_key,
    *,
    length_prefix_bytes: int = 4,
) -> bytes:
    """
    Decrypt a full packet that is length-prefixed + ciphertext (e.g. one UDP datagram).
    Use when you have the entire message in a single buffer.
    """
    if len(packet) < length_prefix_bytes:
        raise ValueError("packet too short for length prefix")
    msg_len = int.from_bytes(packet[:length_prefix_bytes], "big")
    if len(packet) != length_prefix_bytes + msg_len:
        raise ValueError("packet length mismatch")
    return decrypt_from_sender(packet[length_prefix_bytes:], our_private_key)


async def async_receive_and_decrypt(
    reader,
    our_private_key,
    *,
    length_prefix_bytes: int = 4,
) -> bytes:
    """
    Async version: read length-prefixed encrypted message from an asyncio StreamReader
    and return the decrypted payload. Use with await.
    """
    import asyncio
    length_prefix = b""
    while len(length_prefix) < length_prefix_bytes:
        chunk = await reader.read(length_prefix_bytes - len(length_prefix))
        if not chunk:
            raise ValueError("stream ended before length prefix")
        length_prefix += chunk
    msg_len = int.from_bytes(length_prefix, "big")
    raw = b""
    while len(raw) < msg_len:
        chunk = await reader.read(min(msg_len - len(raw), 65536))
        if not chunk:
            raise ValueError("stream ended before full message")
        raw += chunk
    return decrypt_from_sender(raw, our_private_key)


def load_private_key_from_dir(directory: Path, filename: str = "auth_keys.pem"):
    """Load a server's RSA private key from directory/filename."""
    return load_private_key(directory / filename)


def load_public_key_from_dir(directory: Path, filename: str = "auth_server_public.pem"):
    """Load a server's RSA public key from directory/filename (e.g. for clients)."""
    return load_public_key(directory / filename)


def public_key_to_bytes(public_key) -> bytes:
    """Serialize RSA public key for sending in proto (SubjectPublicKeyInfo)."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def public_key_from_bytes(data: bytes):
    """Deserialize RSA public key from proto bytes."""
    return serialization.load_pem_public_key(data, backend=default_backend())
