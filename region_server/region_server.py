from __future__ import annotations
from region_server_extras import *
import asyncio
import aioudp
import signal
from config import ZONE_HOST, ZONE_TCP_PORT, ZONE_UDP_PORT


async def main() -> None:
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    # Gracefully stop on SIGINT / SIGTERM (e.g. Ctrl+C)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # add_signal_handler may not be available on some platforms;
            # in that case KeyboardInterrupt will still stop the process.
            pass

    server = await asyncio.start_server(Client.client_handler_setup, ZONE_HOST, ZONE_TCP_PORT)
    projectile_handler.create_background_task()

    async with aioudp.serve(ZONE_HOST, ZONE_UDP_PORT, Client.udp_handler):
        async with server:
            await stop_event.wait()


if __name__ == "__main__":
    YELLOW = '\033[33m'
    RESET = '\033[0m'
    print(YELLOW + f"region server running at {ZONE_HOST}:{ZONE_TCP_PORT}. If this is incorrect, please re-run setup_dev.py" + RESET)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down region server on Ctrl+C")
