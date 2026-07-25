from fastapi import APIRouter, Depends
from observatory.action_registry import ActionRegistry
from observatory.observatory import Observatory
from routes import get_observatory

router = APIRouter(prefix="/observatory", tags=["observatory"])

@router.get("/actions")
async def list_actions():
    return {"actions": ActionRegistry.list_actions()}

@router.get("/devices")
async def list_devices(observatory: Observatory = Depends(get_observatory)):
    # in future, also expose device capabilities
    return observatory.configured_devices

@router.get("/instruments")
async def list_instruments(observatory: Observatory = Depends(get_observatory)):
    return observatory.configured_instruments

@router.get("/state")
async def get_state(observatory: Observatory = Depends(get_observatory)):
    return observatory.state.snapshot()

@router.get("/cameras")
async def list_cameras(observatory: Observatory = Depends(get_observatory)):
    return observatory.webcams

@router.post("/emergency-halt")
async def emergency_halt(observatory: Observatory = Depends(get_observatory)):
    observatory.emergency_halt()
    return {"status": "emergency halt initiated"}
