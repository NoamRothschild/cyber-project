# Provides utility functions for the client for easier communication with server
from __future__ import annotations
import asyncio
from random import randint
from typing import Tuple, Set, Dict, Union
import protobuf.region_net_pb2 as region_net
import redis
import asyncio

BUFF_SIZE = 1024

# TODO: sorround with a lock as well
clients: Set[Client] = set()
last_mess = ["hii player"]
PORT = 9999
IP = '127.0.0.1'
REDIS_PORT = 6379

# Try-except לחיבור הראשוני לרדיס
try:
    r = redis.Redis(host=IP, port=REDIS_PORT, decode_responses=True)
except Exception as e:
    print(f"Error connecting to Redis: {e}")


class Client:
    @staticmethod
    async def client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        print("new connection established")
        try:
            handshake_raw = await reader.read(1024)
            handshake = region_net.HandshakeStart()
            handshake.ParseFromString(handshake_raw)
            # TODO: verify the session id with the auth server && cache it
            session_id = handshake.session_id

            # TODO: get this one from the auth server
            user_id = randint(0, 2 ** 31 - 1)
            handshake.Clear()
            handshake.CopyFrom(region_net.HandshakeStart(
                kind=region_net.HandshakeStart.SERVER_OK,
                user_id=user_id,
            ))

            writer.write(handshake.SerializeToString())
            await writer.drain()
            global clients
            self = Client(reader, writer, session_id, user_id)
            clients.add(self)

            try:
                await self.handle()
            finally:
                clients.remove(self)
        except Exception as e:
            print(f"Error in client_handler: {e}")
            writer.close()
            await writer.wait_closed()

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_id: int,
                 user_id: int) -> None:
        self.reader = reader
        self.writer = writer
        self.writer_lock = asyncio.Lock()
        self.session_id = session_id
        self.user_id = user_id

    def add_to_mas_stack(self, mas: str):
        global last_mess
        last_mess.append(mas)
        if len(last_mess) > 18:
            last_mess.pop(0)

    async def handle(self):
        username = "Unknown"
        try:
            username = r.get(f"session:{self.session_id}:username")
        except Exception as e:
            print(f"Redis error getting username: {e}")
        try:
            masss = ""
            for mas in last_mess:
                masss += mas + "\r\n"
            update = region_net.ChatMessage()
            print(masss)
            update.message = masss
            await self.write(update.SerializeToString())
        except Exception as e:
            print(f"error sending last messages: {e}")

        while True:
            try:
                data = await self.reader.read(1024)
                if not data:
                    break

                update = region_net.ChatMessage()
                update.ParseFromString(data)


                print(str(username) + f": {update}")
                payload_type = update.WhichOneof("mas")
                if payload_type == "message":
                    update.message = str(username) + f": {update.message}"
                    self.add_to_mas_stack(update.message)
                    await self.broadcast(update.SerializeToString())
            except Exception as e:
                print(f"Error handling message: {e}")
                break

    async def write(self, data: bytes):
        try:
            async with self.writer_lock:
                self.writer.write(data)
                await self.writer.drain()
        except Exception as e:
            print(f"Write error: {e}")

    async def broadcast(self, data: bytes):
        global clients
        for client in clients:
            if client == self:
                continue
            try:
                await client.write(data)
            except Exception as e:
                print(f"Broadcast error to a client: {e}")
        print(f"data broadcasted to {len(clients) - 1} clients")