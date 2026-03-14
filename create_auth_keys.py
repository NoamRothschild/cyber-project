#!/usr/bin/env python3
"""
Generate RSA key pairs for auth server, chat server, and region server(s); distribute public keys to client:
- auth_server/: auth_keys.pem (private)
- client/: auth_server_public.pem
- chat-server/: chat_keys.pem (private)
- client/: chat_server_public.pem
- region_server/: region_keys_0.pem, region_keys_1.pem, ... (private, one per server id)
- client/: region_server_0_public.pem, region_server_1_public.pem, ...

Number of region server key pairs = len(setup_redis.REGION_SERVERS.keys()).

Run from project root: python create_auth_keys.py

Requires: pip install -r requirements.txt  (cryptography)
Run this script once before first use; re-run to rotate keys.
"""
import sys
from pathlib import Path

# Ensure project root on path for setup_redis / region_server.config
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Paths relative to project root
AUTH_SERVER_DIR = ROOT / "auth_server"
AUTH_KEYS_FILE = AUTH_SERVER_DIR / "auth_keys.pem"
CHAT_SERVER_DIR = ROOT / "chat-server"
CHAT_KEYS_FILE = CHAT_SERVER_DIR / "chat_keys.pem"
REGION_SERVER_DIR = ROOT / "region_server"
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
    import setup_redis
    n_region_servers = len(setup_redis.REGION_SERVERS.keys())
    REGION_SERVER_DIR.mkdir(exist_ok=True)
    for i in range(n_region_servers):
        _write_key_pair(
            REGION_SERVER_DIR,
            REGION_SERVER_DIR / f"region_keys_{i}.pem",
            CLIENT_DIR,
            CLIENT_DIR / f"region_server_{i}_public.pem",
            f"region server {i}",
        )
    print("Done. Run auth server, chat server, region server(s) and client as usual; ensure keys exist before first connect.")


if __name__ == "__main__":
    main()
