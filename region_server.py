from __future__ import annotations
import asyncio
from typing import Set
from connection_handler import SERVER_ADDR, region_net

# TODO: sorround with a lock as well
clients: Set[Client] = set()

class Client:
    @staticmethod
    async def client_handler_setup(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
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

            update = region_net.RegionUpdate()
            update.ParseFromString(data)
            print(f"received: {update}")

            payload_type = update.WhichOneof("payload")
            if payload_type == "location_block":
                pos = (update.location_block.x, update.location_block.y)

                resp = region_net.ServerResponse()
                resp.other_data.new_location.CopyFrom(region_net.LocationBlock(x=pos[0], y=pos[1]))
                await self.broadcast(resp.SerializeToString())

    async def write(self, data: bytes):
        async with self.writer_lock:
            self.writer.write(data)
            await self.writer.drain()

    async def broadcast(self, data: bytes):
        global clients
        for client in clients:
            if client == self:
                continue
            async with client.writer_lock:
                self.writer.write(data)
                await self.writer.drain()
        print(f"data broadcasted to {len(clients) - 1} clients")


async def main() -> None:
    server = await asyncio.start_server(Client.client_handler_setup, SERVER_ADDR[0], SERVER_ADDR[1])

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
