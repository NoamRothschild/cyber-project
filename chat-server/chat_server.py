# Provides utility functions for the client for easier communication with server
from __future__ import annotations
import asyncio
from pathlib import Path
from random import randint
from typing import Set

import protobuf.chat_net_pb2 as chat_net
import auth_crypto

ZONE_HOST = "127.0.0.1"
PORT = 8888

_CHAT_SERVER_DIR = Path(__file__).resolve().parent


def _get_server_private_key():
    if not hasattr(_get_server_private_key, "_cached"):
        _get_server_private_key._cached = auth_crypto.load_private_key_from_dir(
            _CHAT_SERVER_DIR, "chat_keys.pem"
        )
    return _get_server_private_key._cached


# TODO: surround with a lock as well
clients: Set[Client] = set()
last_mess = ["hii player"]


class Client:
    @staticmethod
    async def client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        print("new connection established")
        server_private_key = _get_server_private_key()

        try:
            handshake_plain = await auth_crypto.async_receive_and_decrypt(reader, server_private_key)
        except ValueError:
            writer.close()
            await writer.wait_closed()
            return
        handshake = chat_net.HandshakeStart()
        handshake.ParseFromString(handshake_plain)
        # TODO: verify the session id with the auth server && cache it
        session_id = handshake.session_id
        if not handshake.client_public_key:
            writer.close()
            await writer.wait_closed()
            return
        client_public_key = auth_crypto.public_key_from_bytes(handshake.client_public_key)

        # TODO: get this one from the auth server
        user_id = randint(0, 2**31 - 1)
        resp = chat_net.HandshakeStart(kind=chat_net.HandshakeStart.SERVER_OK, user_id=user_id)
        encrypted = auth_crypto.encrypt_and_prefix(resp.SerializeToString(), client_public_key)
        writer.write(encrypted)
        await writer.drain()

        global clients
        self = Client(reader, writer, session_id, user_id, client_public_key)
        clients.add(self)

        try:
            await self.handle()
        finally:
            clients.remove(self)

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        session_id: int,
        user_id: int,
        client_public_key,
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.writer_lock = asyncio.Lock()
        self.session_id = session_id
        self.user_id = user_id
        self.client_public_key = client_public_key

    def add_to_mas_stack(self, mas: str):
        global last_mess
        last_mess.append(mas)
        if len(last_mess) > 18:
            last_mess.pop(0)

    async def handle(self):
        server_private_key = _get_server_private_key()
        try:
            masss = ""
            for mas in last_mess:
                masss += mas + "\r\n"
            update = chat_net.ChatMessage()
            update.message = masss
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
            print(str(self.user_id) + f": {update}")
            payload_type = update.WhichOneof("mas")
            if payload_type == "message":
                update.message = str(self.user_id) + f": {update.message}"
                self.add_to_mas_stack(update.message)
                await self.broadcast(update.SerializeToString())

    async def write(self, data: bytes):
        async with self.writer_lock:
            self.writer.write(data)
            await self.writer.drain()

    async def broadcast(self, serialized_message: bytes):
        global clients
        for client in clients:
            if client is self:
                continue
            encrypted = auth_crypto.encrypt_and_prefix(serialized_message, client.client_public_key)
            await client.write(encrypted)
        print(f"data broadcasted to {len(clients) - 1} clients")
