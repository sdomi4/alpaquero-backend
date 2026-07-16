from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
import asyncio
from fastapi.responses import StreamingResponse
from observatory.observatory import Observatory 
from observatory.error_handler import connect_error_websocket, disconnect_error_websocket, handle_error_async
from routes import get_observatory_ws, get_observatory
from routes.websocket_utils import run_until_websocket_disconnect

router = APIRouter()

@router.websocket("/ws/previews")
async def preview_websocket(websocket: WebSocket, observatory: Observatory = Depends(get_observatory_ws)):
    await websocket.accept()
    try:
        async def send_preview_updates():
            last_previews = None
            while True:
                previews = observatory.get_capture_previews(3)
                if previews != last_previews:
                    await websocket.send_json(previews)
                    last_previews = previews
                await asyncio.sleep(1)

        await run_until_websocket_disconnect(websocket, send_preview_updates)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await handle_error_async(e, "Error sending capture previews", level="error")
        await websocket.close(code=1011, reason=str(e))

@router.get("/previews/full/{name}")
async def get_full_preview_image(name: str, observatory: Observatory = Depends(get_observatory)):
    try:
        image_buffer = observatory.get_full_preview_image(name)
        if image_buffer is None:
            return {"error": "Image not found"}
        return StreamingResponse(image_buffer, media_type="image/jpeg")
    except Exception as e:
        await handle_error_async(e, f"Error retrieving full preview image: {name}", level="error")
        return {"error": str(e)}
