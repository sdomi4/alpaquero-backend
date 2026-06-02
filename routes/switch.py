from fastapi import APIRouter, HTTPException, Depends
from observatory.error_handler import handle_error
from observatory.observatory import Observatory
from observatory.state import SwitchState
from routes import get_observatory

router = APIRouter(prefix="/switch", tags=["switch"])

@router.post("/{switch_id}/startup")
async def switch_startup(
    switch_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.switches[switch_id].connect()
    except Exception as e:
        message = handle_error(e, f"Error connecting to switch {switch_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
    
@router.post("/{switch_id}/shutdown")
async def switch_shutdown(
    switch_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.switches[switch_id].disconnect()
    except Exception as e:
        message = handle_error(e, f"Error disconnecting from switch {switch_id}", level="error")
        raise HTTPException(status_code=500, detail=message)

@router.get("/{switch_id}/controls")
async def get_switch_controls(
    switch_id: str,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        device = observatory.state.get_device(switch_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Switch {switch_id} not found")

    if not isinstance(device, SwitchState):
        raise HTTPException(status_code=404, detail=f"Switch {switch_id} not found")

    controls = []
    for key, control in sorted(device.controls.items(), key=lambda item: item[1].id):
        control_info = control.model_dump()
        control_info["key"] = key
        controls.append(control_info)

    return {"switch_id": switch_id, "controls": controls}

@router.post("/{switch_id}/{switch_number}/{setting}")
async def set_switch(
    switch_id: str,
    switch_number: int,
    setting: float,
    observatory: Observatory = Depends(get_observatory)
):
    try:
        observatory.switches[switch_id].set_switch(switch_number, setting)
        return {"message": f"Switch {switch_number} on {switch_id} set to {setting}"}
    except Exception as e:
        message = handle_error(e, f"Error setting switch {switch_number} on {switch_id}", level="error")
        raise HTTPException(status_code=500, detail=message)
