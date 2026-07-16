import asyncio
from contextlib import suppress
from typing import Awaitable, Callable

from fastapi import WebSocket, WebSocketDisconnect


async def run_until_websocket_disconnect(
    websocket: WebSocket,
    sender: Callable[[], Awaitable[None]],
) -> None:
    sender_task = asyncio.create_task(sender())
    receiver_task = asyncio.create_task(_consume_until_disconnect(websocket))
    tasks = {sender_task, receiver_task}

    try:
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
    except BaseException:
        for task in tasks:
            task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.gather(*tasks, return_exceptions=True)
        raise

    for task in pending:
        task.cancel()

    with suppress(asyncio.CancelledError):
        await asyncio.gather(*pending, return_exceptions=True)

    for task in done:
        try:
            task.result()
        except WebSocketDisconnect:
            pass


async def _consume_until_disconnect(websocket: WebSocket) -> None:
    while True:
        await websocket.receive_text()
