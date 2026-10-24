from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Iterator


async def iterate_in_thread(factory: Callable[[], Iterator], should_stop: Callable[[], bool] | None = None):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def produce() -> None:
        iterator = factory()
        try:
            for item in iterator:
                if should_stop is not None and should_stop():
                    iterator.close()
                    break
                loop.call_soon_threadsafe(queue.put_nowait, ("item", item))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, ("end", None))

    threading.Thread(target=produce, daemon=True).start()
    while True:
        kind, payload = await queue.get()
        if kind == "end":
            break
        if kind == "error":
            raise payload
        yield payload
