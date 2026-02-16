from __future__ import annotations
import asyncio
import signal
import aioudp
from config import ZONE_HOST, ZONE_TCP_PORT, ZONE_UDP_PORT
from region_server_extras import Client
from state import start_global_tick_loop


async def main() -> None:
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    server = await asyncio.start_server(
        Client.client_handler_setup, ZONE_HOST, ZONE_TCP_PORT
    )
    start_global_tick_loop()

    async with aioudp.serve(ZONE_HOST, ZONE_UDP_PORT, Client.udp_handler):
        async with server:
            await stop_event.wait()


if __name__ == "__main__":
    YELLOW = "\033[33m"
    RESET = "\033[0m"
    print(
        YELLOW
        + f"region server running at {ZONE_HOST}:{ZONE_TCP_PORT}. If this is incorrect, please re-run setup_dev.py"
        + RESET
    )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down region server on Ctrl+C")
