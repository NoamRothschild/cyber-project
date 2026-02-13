from __future__ import annotations
from region_server.region_server_extras import *
import asyncio
from config import ZONE_HOST, ZONE_TCP_PORT

async def main() -> None:
    server = await asyncio.start_server(Client.client_handler_setup, ZONE_HOST, ZONE_TCP_PORT)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
