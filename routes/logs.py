import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from observatory.log_broker import log_broker
from routes.websocket_utils import run_until_websocket_disconnect


logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/logs")
async def logs_websocket(websocket: WebSocket):
    await websocket.accept()
    subscription, snapshot = log_broker.subscribe()

    try:
        await websocket.send_json({"type": "snapshot", "entries": snapshot})

        async def send_log_updates():
            while True:
                await websocket.send_json(await log_broker.next_event(subscription))

        await run_until_websocket_disconnect(websocket, send_log_updates)
    except WebSocketDisconnect:
        pass
    except Exception:
        log_broker.unsubscribe(subscription)
        logger.exception("Error in log websocket")
        try:
            await websocket.close(code=1011, reason="Log stream failed")
        except Exception:
            pass
    finally:
        log_broker.unsubscribe(subscription)
