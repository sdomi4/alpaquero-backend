from __future__ import annotations

from pydantic import BaseModel, Field
import threading
import time
from typing import Annotated, Dict, Literal, Optional, Union


class ObservatoryStatus(BaseModel):
    status: Literal["stopped", "initializing", "running", "error"] = "stopped"
    actions: list[str] = Field(default_factory=list)
    messages: dict[str, str] = Field(default_factory=dict)


class SequenceState(BaseModel):
    context_id: str
    sequence_name: str
    status: str = "running"
    info: Optional[str] = None
    steps: Dict[str, int] = Field(default_factory=dict)  # step id with repetition count

class BaseDeviceState(BaseModel):
    id: str
    device_type: str
    name: Optional[str] = None
    connected: bool = False
    status: str = "unknown"


class DomeState(BaseDeviceState):
    device_type: Literal["dome"] = "dome"
    # status: int, 0 = open, 1 = closed, 2 = opening, 3 = closing, 4 = error
    shutter_status: Optional[int] = None

class TelescopeState(BaseDeviceState):
    device_type: Literal["telescope"] = "telescope"
    booted: bool = False
    tracking: bool = False
    slewing: bool = False
    parked: bool = False
    position: Optional[Dict[str, float]] = None  # e.g., {"ra": 0.0, "dec": 0.0}
    target: Optional[Dict[str, float]] = None  # e.g., {"ra": 0.0, "dec": 0.0}
    side_of_pier: Optional[int] = -1  # 0 = east, 1 = west, -1 = unknown

class ObservingConditionsState(BaseDeviceState):
    device_type: Literal["observing_conditions"] = "observing_conditions"
    sky_ambient: Optional[float] = None  # sky temp minus ambient temp in Celsius
    ambient: Optional[float] = None  # ambient temperature in Celsius
    rain: Optional[float] = None  # rain rate in mm/hr
    wind: Optional[float] = None  # wind speed in m/s
    daylight: Optional[float] = None  # daylight level in lux
    humidity: Optional[float] = None  # relative humidity in %
    dew_point: Optional[float] = None  # dew point in Celsius
    pressure: Optional[float] = None  # atmospheric pressure in hPa

class SafetyMonitorState(BaseDeviceState):
    device_type: Literal["safety_monitor"] = "safety_monitor"
    safe: Optional[bool] = None

class CoverState(BaseDeviceState):
    device_type: Literal["cover"] = "cover"
    # cover status: int, 0 = not present, 1 = closed, 2 = moving, 3 = open, 4 = unknown, 5 = error
    cover_status: Optional[int] = 4
    # calibrator status: int, 0 = not present, 1 = off, 2 = not ready, 3 = ready, 4 = unknown, 5 = error
    calibrator_status: Optional[int] = 4
    brightness: Optional[int] = None  # brightness level of the calibrator 0 - MaxBrightness

class SwitchControlBase(BaseModel):
    id: int
    label: Optional[str] = None
    description: Optional[str] = None
    writeable: bool = True
    can_async: bool = False

class ToggleControl(SwitchControlBase):
    control_type: Literal["toggle"] = "toggle"
    value: bool = False

class RangeControl(SwitchControlBase):
    control_type: Literal["range"] = "range"
    min_value: float = 0.0
    max_value: float = 1.0
    step: float = 1.0
    value: float = 0.0

SwitchControlState = Annotated[
    Union[ToggleControl, RangeControl],
    Field(discriminator="control_type"),
]

class SwitchState(BaseDeviceState):
    device_type: Literal["switch"] = "switch"
    controls: Dict[str, SwitchControlState] = Field(default_factory=dict)

class CameraState(BaseDeviceState):
    device_type: Literal["camera"] = "camera"
    bin_x: Optional[int] = 1
    bin_y: Optional[int] = 1
    ccd_temperature: Optional[float] = None
    camera_state: Optional[int] = None  # 0 = idle, 1 = waiting, 2 = exposing, 3 = reading, 4 = download, 5 = error
    x_size: Optional[int] = None
    y_size: Optional[int] = None
    cooler_on: Optional[bool] = None
    cooler_power: Optional[float] = None  # percentage 0.0
    gain: Optional[int] = None
    image_ready: Optional[bool] = None
    last_exposure_duration: Optional[float] = None  # in seconds
    last_exposure_start_time: Optional[str] = None  # FITS standard format, UTC
    set_ccd_temperature: Optional[float] = None
    percent_completed: Optional[int] = None  # percentage 0-100

class FilterwheelState(BaseDeviceState):
    device_type: Literal["filterwheel"] = "filterwheel"
    names: Optional[list[str]] = None # list of filter names
    position: Optional[int] = None  # current filter position, -1 = moving

class FocuserState(BaseDeviceState):
    device_type: Literal["focuser"] = "focuser"
    position: Optional[int] = None  # current focuser position
    is_moving: Optional[bool] = None  # is the focuser currently moving
    temperature: Optional[float] = None  # current focuser temperature
    step_size: Optional[int] = None  # step size for focuser movement
    max_increment: Optional[int] = None  # maximum increment for focuser movement
    max_step: Optional[int] = None  # maximum step for focuser movement


DeviceState = Annotated[
    Union[DomeState, TelescopeState, ObservingConditionsState, SafetyMonitorState, CoverState, SwitchState, CameraState, FilterwheelState, FocuserState],
    Field(discriminator="device_type"),
]

class Snapshot(BaseModel):
    schema_version: int = 1
    status: ObservatoryStatus = Field(default_factory=ObservatoryStatus)
    devices: Dict[str, DeviceState] = Field(default_factory=dict)
    sequences: Dict[str, SequenceState] = Field(default_factory=dict)

class StateManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot = Snapshot()

    def add_device(self, device: DeviceState):
        with self._lock:
            existing_device = self._snapshot.devices.get(device.id)
            if existing_device is not None and existing_device.connected:
                raise ValueError(f"Device with id {device.id} already exists.")
            self._snapshot.devices[device.id] = device

    def remove_device(self, device_id: str):
        with self._lock:
            if device_id not in self._snapshot.devices:
                raise ValueError(f"Device with id {device_id} does not exist.")
            self._snapshot.devices.pop(device_id, None)
        
    def get_device(self, device_id: str) -> DeviceState:
        with self._lock:
            try:
                return self._snapshot.devices[device_id]
            except KeyError:
                raise ValueError(f"Device with id {device_id} does not exist.")

    def set_device_connected(self, device_id: str, connected: bool) -> None:
        with self._lock:
            try:
                self._snapshot.devices[device_id].connected = connected
            except KeyError:
                raise ValueError(f"Device with id {device_id} does not exist.")
            
    def add_action(self, text: str):
        with self._lock:
            self._snapshot.status.actions.append(text)

    def remove_action(self, text: str) -> None:
        with self._lock:
            try:
                self._snapshot.status.actions.remove(text)
            except ValueError:
                pass

    def add_sequence(self, context_id: str, sequence_name: str, steps: Optional[list[str]] = None):
        with self._lock:
            self._snapshot.sequences[context_id] = SequenceState(
                context_id=context_id,
                sequence_name=sequence_name,
                steps=steps if steps is not None else {},
            )

    def remove_sequence(self, context_id: str):
        with self._lock:
            self._snapshot.sequences.pop(context_id, None)

    def set_sequence_status(self, context_id: str, status: str):
        with self._lock:
            try:
                self._snapshot.sequences[context_id].status = status
            except KeyError:
                raise ValueError(f"Sequence with context_id {context_id} does not exist.")
            
    def set_sequence_info(self, context_id: str, info: str):
        with self._lock:
            try:
                self._snapshot.sequences[context_id].info = info
            except KeyError:
                raise ValueError(f"Sequence with context_id {context_id} does not exist.")

    def update_sequence_steps(self, context_id: str, steps: dict[str, int]):
        with self._lock:
            try:
                self._snapshot.sequences[context_id].steps = steps
            except KeyError:
                raise ValueError(f"Sequence with context_id {context_id} does not exist.")

    def set_message(self, msg_id: str, text: str) -> None:
        with self._lock:
            self._snapshot.status.messages[msg_id] = text

    def clear_message(self, msg_id: str) -> None:
        with self._lock:
            self._snapshot.status.messages.pop(msg_id, None)

    def set_status(self, status: GlobalStatus["status"]) -> None:  # type: ignore[index]
        with self._lock:
            self._snapshot.status.status = status

    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._snapshot.model_copy(deep=True)
        
    def snapshot_json(self) -> str:
        with self._lock:
            return self._snapshot.model_dump_json()
        
    def snapshot_dict(self) -> dict:
        with self._lock:
            return self._snapshot.model_dump()
