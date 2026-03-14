#!/usr/bin/env python3
"""
Generate RSA key pair for the auth server and distribute keys:
- auth_server/: private + public (auth_keys.pem contains private; public is derivable)
- client/: auth server's public key only (auth_server_public.pem)

Run from project root: python create_auth_keys.py

Requires: pip install -r requirements.txt  (cryptography)
Run this script once before first use of encrypted auth; re-run to rotate keys.
"""
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Paths relative to project root
ROOT = Path(__file__).resolve().parent
AUTH_SERVER_DIR = ROOT / "auth_server"
AUTH_KEYS_FILE = AUTH_SERVER_DIR / "auth_keys.pem"
CLIENT_DIR = ROOT / "client"
SERVER_PUBLIC_IN_CLIENT = CLIENT_DIR / "auth_server_public.pem"

KEY_SIZE = 2048


def main():
    AUTH_SERVER_DIR.mkdir(exist_ok=True)
    CLIENT_DIR.mkdir(exist_ok=True)

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=KEY_SIZE,
        backend=default_backend(),
    )
    public_key = private_key.public_key()

    # Auth server: store private key (PEM with both; server can load and derive public)
    auth_keys_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    AUTH_KEYS_FILE.write_bytes(auth_keys_pem)
    print(f"Written auth server keys (private) -> {AUTH_KEYS_FILE}")

    # Client: store only auth server's public key
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    SERVER_PUBLIC_IN_CLIENT.write_bytes(public_pem)
    print(f"Written auth server public key -> {SERVER_PUBLIC_IN_CLIENT}")
    print("Done. Run auth server and client as usual; ensure keys exist before first connect.")


if __name__ == "__main__":
    main()
