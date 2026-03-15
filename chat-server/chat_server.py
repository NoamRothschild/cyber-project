# Provides utility functions for the client for easier communication with server
from __future__ import annotations
import asyncio
from pathlib import Path
from random import randint
from typing import Set

import protobuf.chat_net_pb2 as chat_net
import redis
import auth_crypto

# TODO: protect with a lock as well if access patterns change
clients: Set["Client"] = set()
message_history = ["hii player"]
MESSAGE_HISTORY_LIMIT = 18
IP = "127.0.0.1"
REDIS_PORT = 6379

_CHAT_SERVER_DIR = Path(__file__).resolve().parent


def _get_server_private_key():
    if not hasattr(_get_server_private_key, "_cached"):
        _get_server_private_key._cached = auth_crypto.load_private_key_from_dir(
            _CHAT_SERVER_DIR, "chat_keys.pem"
        )
    return _get_server_private_key._cached


try:
    r = redis.Redis(host=IP, port=REDIS_PORT, decode_responses=True)
except Exception as e:
    print(f"Error connecting to Redis: {e}")


def _build_history_payload() -> str:
    return "".join(m + "\r\n" for m in message_history)


async def close_writer(writer: asyncio.StreamWriter):
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass


class Client:
    @staticmethod
    async def client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        print("new connection established")
        server_private_key = _get_server_private_key()

        try:
            handshake_plain = await auth_crypto.async_receive_and_decrypt(reader, server_private_key)

            handshake = chat_net.HandshakeStart()
            handshake.ParseFromString(handshake_plain)

            session_id = handshake.session_id
            if not handshake.client_public_key:
                await close_writer(writer)
                return
            
            client_public_key = auth_crypto.public_key_from_bytes(handshake.client_public_key)

            resp = chat_net.HandshakeStart(kind=chat_net.HandshakeStart.SERVER_OK)
            encrypted = auth_crypto.encrypt_and_prefix(resp.SerializeToString(), client_public_key)
            writer.write(encrypted)
            await writer.drain()

            self = Client(reader, writer, session_id, client_public_key)
            clients.add(self)
            try:
                await self.handle()
            finally:
                clients.remove(self)
        except Exception as e:
            print(f"Error in client_handler: {e}")
            await close_writer(writer)

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_id: int, client_public_key) -> None:
        self.reader = reader
        self.writer = writer
        self.writer_lock = asyncio.Lock()
        self.session_id = session_id
        self.client_public_key = client_public_key
        self.username = "Unknown"
    
    def fetch_username(self) -> None:
        try:
            self.username = r.get(f"session:{self.session_id}:username")
            if self.username is None:
                self.username = "Unknown"
        except Exception as e:
            print(f"Warning: Redis error getting username: {e}")
            self.username = "Unknown"

    def add_to_history(self, message: str) -> None:
        message_history.append(message)
        if len(message_history) > MESSAGE_HISTORY_LIMIT:
            message_history.pop(0)

    async def handle(self):
        server_private_key = _get_server_private_key()
        self.fetch_username()

        try:
            history_payload = _build_history_payload()
            update = chat_net.ChatMessage()
            update.message = history_payload
            encrypted = auth_crypto.encrypt_and_prefix(update.SerializeToString(), self.client_public_key)
            await self.write(encrypted)
        except Exception as e:
            print(f"error sending last messages: {e}")

        while True:
            try:
                plaintext = await auth_crypto.async_receive_and_decrypt(self.reader, server_private_key)
            except ValueError:
                break

            update = chat_net.ChatMessage()
            update.ParseFromString(plaintext)
            print(str(self.username) + f": {update}")
            payload_type = update.WhichOneof("mas")
            if payload_type == "message":
                update.message = str(self.username) + f": {update.message}"
                self.add_to_history(update.message)
                await self.broadcast(update.SerializeToString())

    async def write(self, data: bytes):
        async with self.writer_lock:
            self.writer.write(data)
            await self.writer.drain()

    async def broadcast(self, serialized_message: bytes):
        for client in list(clients):
            if client is self:
                continue
            try:
                encrypted = auth_crypto.encrypt_and_prefix(serialized_message, client.client_public_key)
                await client.write(encrypted)
            except Exception as e:
                print(f"Broadcast error to a client: {e}")
        print(f"data broadcasted to {len(clients) - 1} clients")
