import asyncio
from typing import List

_listeners: List[asyncio.Queue] = []

async def register_queue() -> asyncio.Queue:
    q = asyncio.Queue()
    _listeners.append(q)
    return q

async def unregister_queue(q: asyncio.Queue) -> None:
    try:
        _listeners.remove(q)
    except ValueError:
        pass

async def broadcast(message: str) -> None:
    for q in list(_listeners):
        try:
            q.put_nowait(message)
        except Exception:
            # if queue broken, ignore
            pass
