from __future__ import annotations
import asyncio
import signal
import sys
import aioudp
import aioudp.server
from config import ZONE_TCP_PORT, ZONE_UDP_PORT
from region_server_extras import Client
from state import start_global_tick_loop, create_initial_nodes
from servers_communication import start_redis_listener
ZONE_HOST = '0.0.0.0'

# aioudp's error_received raises unconditionally, which kills the UDP
# transport's read loop on Windows when a client crashes (ICMP unreachable).
# Even if we suppress the raise, Python's _ProactorDatagramTransport only
# reschedules _loop_reading in the try/else branch — which doesn't run after
# an OSError. We must manually restart the read loop.
_KNOWN_UDP_ERRORS = {1234, 10054, 10053}  # WinError codes from dead endpoints
def _safe_error_received(self, exc: Exception) -> None:
    if not (isinstance(exc, OSError) and exc.winerror in _KNOWN_UDP_ERRORS):
        print(f"[WARN] UDP transport error (suppressed): {exc}")
    if self.transport is not None and not self.transport.is_closing():
        asyncio.get_running_loop().call_soon(self.transport._loop_reading)
aioudp.server._ServerProtocol.error_received = _safe_error_received


async def _docker_friendly_stdio_flush_loop(interval_s: float = 0.25) -> None:
    """Flush stdout/stderr on a timer so container logs update without huge buffers (non-TTY)."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except (BrokenPipeError, ValueError, OSError):
            pass


async def main() -> None:
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    asyncio.create_task(_docker_friendly_stdio_flush_loop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    server = await asyncio.start_server(
        Client.client_handler_setup, ZONE_HOST, ZONE_TCP_PORT
    )
    start_global_tick_loop()
    await create_initial_nodes()
    start_redis_listener()

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
