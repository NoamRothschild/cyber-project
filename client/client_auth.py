import os
import socket
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

import protobuf.auth_net_pb2 as auth_net
import auth_crypto
from config import AUTH_HOST, AUTH_PORT

_CLIENT_DIR = Path(__file__).resolve().parent


def _get_client_key_pair():
    """Generate or return cached client RSA key pair (created at first use)."""
    if not hasattr(_get_client_key_pair, "_cached"):
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        _get_client_key_pair._cached = (private_key, private_key.public_key())
    return _get_client_key_pair._cached


def connect(username, password, command):
    # Create a fresh socket every time we click the button
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # FIX 1: Connect exactly ONCE using your config variables
        client.connect((AUTH_HOST, AUTH_PORT))

        client_private_key, client_public_key = _get_client_key_pair()
        server_public_key = auth_crypto.load_public_key_from_dir(_CLIENT_DIR)

        answer = auth_net.RequestLogin()
        if command == "REG":
            answer.mode = auth_net.Mode.REGISTER
        elif command == "LOG":
            answer.mode = auth_net.Mode.LOGIN

        answer.username = username
        answer.password = password
        answer.client_public_key = auth_crypto.public_key_to_bytes(client_public_key)

        # FIX 2: Encrypt the message and send it to the server
        plaintext = answer.SerializeToString()
        client.sendall(auth_crypto.encrypt_and_prefix(plaintext, server_public_key))

        # FIX 3: Receive the encrypted response and decrypt it
        decrypted = auth_crypto.receive_and_decrypt(client.recv, client_private_key)

        response = auth_net.SendAnswer()
        response.ParseFromString(decrypted)

        return response

    except ConnectionRefusedError:
        return "SERVER_OFFLINE"
    except socket.timeout:
        return "TIMEOUT"
    except socket.error as e:
        # Catches other network errors like BrokenPipe
        return f"NET_ERROR: {e}"
    except FileNotFoundError as err:
        return f"CONFIG_ERROR: {err}"
    except ValueError as e:
        return f"DECRYPT_ERROR: {e}"
    finally:
        client.close()  # Always hang up safely