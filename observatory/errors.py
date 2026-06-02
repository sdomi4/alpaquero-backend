from dataclasses import dataclass

@dataclass(slots=True)
class ObservatoryError(Exception):
    code: str
    message: str
    detail: str | None = None
    component: str | None = None
    severity: str = "error" # info/warning/error/critical

class DomeError(ObservatoryError):
    component: str = "dome"

class TelescopeError(ObservatoryError):
    component: str = "telescope"


class CoverError(ObservatoryError):
    component: str = "covers"

class SwitchError(ObservatoryError):
    component: str = "switch"

class StateError(ObservatoryError):
    component: str = "state"

class CameraError(ObservatoryError):
    component: str = "camera"

class FilterWheelError(ObservatoryError):
    component: str = "filterwheel"
