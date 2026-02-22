from __future__ import annotations

import asyncio

from config import ZONE_HOST, ZONE_TCP_PORT
from region_server_extras import *


async def main() -> None:
    server = await asyncio.start_server(Client.client_handler_setup, ZONE_HOST, ZONE_TCP_PORT)
    projectile_handler.create_background_task()
    enemy_handler.create_background_task()

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    YELLOW = '\033[33m'
    RESET = '\033[0m'
    print(YELLOW + f"region server running at {ZONE_HOST}:{ZONE_TCP_PORT}. If this is incorrect, please re-run setup_dev.py" + RESET)
    asyncio.run(main())
