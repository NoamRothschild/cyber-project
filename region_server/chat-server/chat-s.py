from __future__ import annotations
from chat_server import *
import asyncio
from config import CHAT_HOST, CHAT_PORT




async def main() -> None:
    server = await asyncio.start_server(Client.client_handler, CHAT_HOST, CHAT_PORT)

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    YELLOW = '\033[33m'
    RESET = '\033[0m'
    print(YELLOW + f"region server running at {CHAT_HOST}:{CHAT_PORT}. If this is incorrect, please re-run setup_dev.py" + RESET)
    asyncio.run(main())
