#!/usr/bin/env python3
"""
Generate RSA key pairs for auth server and chat server; distribute public keys to client:
- auth_server/: auth_keys.pem (private)
- client/: auth_server_public.pem
- chat-server/: chat_keys.pem (private)
- client/: chat_server_public.pem

Run from project root: python create_auth_keys.py

Requires: pip install -r requirements.txt  (cryptography)
Run this script once before first use; re-run to rotate keys.
"""
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Paths relative to project root
ROOT = Path(__file__).resolve().parent
AUTH_SERVER_DIR = ROOT / "auth_server"
AUTH_KEYS_FILE = AUTH_SERVER_DIR / "auth_keys.pem"
CHAT_SERVER_DIR = ROOT / "chat-server"
CHAT_KEYS_FILE = CHAT_SERVER_DIR / "chat_keys.pem"
CLIENT_DIR = ROOT / "client"
AUTH_SERVER_PUBLIC_IN_CLIENT = CLIENT_DIR / "auth_server_public.pem"
CHAT_SERVER_PUBLIC_IN_CLIENT = CLIENT_DIR / "chat_server_public.pem"

KEY_SIZE = 2048


def _write_key_pair(server_dir: Path, keys_file: Path, client_dir: Path, public_in_client: Path, label: str):
    server_dir.mkdir(exist_ok=True)
    client_dir.mkdir(exist_ok=True)
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=KEY_SIZE,
        backend=default_backend(),
    )
    public_key = private_key.public_key()
    keys_file.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_in_client.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print(f"Written {label} keys -> {keys_file}")
    print(f"Written {label} public key -> {public_in_client}")


def main():
    CLIENT_DIR.mkdir(exist_ok=True)
    _write_key_pair(
        AUTH_SERVER_DIR, AUTH_KEYS_FILE, CLIENT_DIR, AUTH_SERVER_PUBLIC_IN_CLIENT,
        "auth server",
    )
    _write_key_pair(
        CHAT_SERVER_DIR, CHAT_KEYS_FILE, CLIENT_DIR, CHAT_SERVER_PUBLIC_IN_CLIENT,
        "chat server",
    )
    print("Done. Run auth server, chat server and client as usual; ensure keys exist before first connect.")


if __name__ == "__main__":
    main()
