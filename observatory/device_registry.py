from dataclasses import dataclass
from typing import Callable

from alpaquero.factories.camera import camera_factory
from alpaquero.factories.cover import cover_factory
from alpaquero.factories.dome import dome_factory
from alpaquero.factories.filterwheel import filterwheel_factory
from alpaquero.factories.focuser import focuser_factory
from alpaquero.factories.observing_conditions import observing_conditions_factory
from alpaquero.factories.safety_monitor import safety_monitor_factory
from alpaquero.factories.switch import switch_factory
from alpaquero.factories.telescope import telescope_factory
from alpaquero.updaters.camera import camera_updater
from alpaquero.updaters.cover import cover_updater
from alpaquero.updaters.dome import dome_updater
from alpaquero.updaters.filterwheel import filterwheel_updater
from alpaquero.updaters.focuser import focuser_updater
from alpaquero.updaters.observing_conditions import observing_conditions_updater
from alpaquero.updaters.safety_monitor import safety_monitor_updater
from alpaquero.updaters.switch import switch_updater
from alpaquero.updaters.telescope import telescope_updater
from observatory.devices.camera import AlpaqueroCamera
from observatory.devices.cover import AlpaqueroCover
from observatory.devices.dome import AlpaqueroDome
from observatory.devices.filterwheel import AlpaqueroFilterWheel
from observatory.devices.focuser import AlpaqueroFocuser
from observatory.devices.observing_conditions import AlpaqueroObservingConditions
from observatory.devices.safety_monitor import AlpaqueroSafetyMonitor
from observatory.devices.switch import AlpaqueroSwitch
from observatory.devices.telescope import AlpaqueroTelescope


@dataclass(frozen=True)
class DeviceSpec:
    wrapper: type
    factory: Callable
    updater: Callable
    collection: str
    updater_device_arg: str


DEVICE_SPECS = {
    "dome": DeviceSpec(AlpaqueroDome, dome_factory, dome_updater, "domes", "dome"),
    "telescope": DeviceSpec(
        AlpaqueroTelescope, telescope_factory, telescope_updater, "telescopes", "telescope"
    ),
    "camera": DeviceSpec(AlpaqueroCamera, camera_factory, camera_updater, "cameras", "camera"),
    "observing_conditions": DeviceSpec(
        AlpaqueroObservingConditions,
        observing_conditions_factory,
        observing_conditions_updater,
        "observing_conditions",
        "observing_conditions",
    ),
    "safety_monitor": DeviceSpec(
        AlpaqueroSafetyMonitor,
        safety_monitor_factory,
        safety_monitor_updater,
        "safety_monitors",
        "safety_monitor",
    ),
    "cover": DeviceSpec(AlpaqueroCover, cover_factory, cover_updater, "covers", "cover"),
    "filterwheel": DeviceSpec(
        AlpaqueroFilterWheel,
        filterwheel_factory,
        filterwheel_updater,
        "filterwheels",
        "filterwheel",
    ),
    "switch": DeviceSpec(
        AlpaqueroSwitch, switch_factory, switch_updater, "switches", "switch_device"
    ),
    "focuser": DeviceSpec(
        AlpaqueroFocuser, focuser_factory, focuser_updater, "focusers", "focuser"
    ),
}
