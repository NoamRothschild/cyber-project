# Provides utility functions for the client for easier communication with server
from __future__ import annotations
import asyncio
from random import randint
from typing import Tuple, Set, Dict, Union
import protobuf.region_net_pb2 as region_net

import asyncio

ZONE_HOST = "127.0.0.1"
PORT = 8888

BUFF_SIZE = 1024

# TODO: sorround with a lock as well
clients: Set[Client] = set()


class Client:
    @staticmethod
    async def client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        print("new connection established")

        global clients
        self = Client(reader, writer)
        clients.add(self)

        try:
            await self.handle()
        finally:
            clients.remove(self)

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer
        self.writer_lock = asyncio.Lock()


    async def handle(self):
        while True:
            data = await self.reader.read(1024)
            if not data:
                break

            update = region_net.ChatMessage()
            update.ParseFromString(data)
            print(f"received: {update}")

            payload_type = update.WhichOneof("mas")
            if payload_type == "message":
                await self.broadcast(update.SerializeToString())

    async def write(self, data: bytes):
        async with self.writer_lock:
            self.writer.write(data)
            await self.writer.drain()

    async def broadcast(self, data: bytes):
        global clients
        for client in clients:
            if client == self:
                continue
            await client.write(data)
        print(f"data broadcasted to {len(clients) - 1} clients")
