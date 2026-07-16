from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
import asyncio
from observatory.observatory import Observatory 
from observatory.error_handler import connect_error_websocket, disconnect_error_websocket, handle_error_async
from routes import get_observatory_ws
from routes.websocket_utils import run_until_websocket_disconnect

router = APIRouter()

@router.websocket("/ws/state")
async def state_websocket(websocket: WebSocket, observatory: Observatory = Depends(get_observatory_ws)):
    await websocket.accept()
    try:
        async def send_state_updates():
            while True:
                await websocket.send_json(observatory.state.snapshot_dict())
                await asyncio.sleep(1)

        await run_until_websocket_disconnect(websocket, send_state_updates)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await handle_error_async(e, "Error sending observatory state", level="error")
        await websocket.close(code=1011, reason=str(e))

@router.websocket("/ws/errors")
async def error_websocket(websocket: WebSocket):
    await websocket.accept()
    connect_error_websocket(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await handle_error_async(e, "Error in error websocket", level="warning")
    finally:
        disconnect_error_websocket(websocket)
