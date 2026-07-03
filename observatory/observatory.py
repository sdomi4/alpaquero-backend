from typing import Any, Dict, List
import asyncio
from pathlib import Path

from observatory.action_registry import ActionRegistry
from observatory.error_handler import handle_error
from observatory.devices.camera import AlpaqueroCamera
from alpaquero.factories.camera import camera_factory
from alpaquero.updaters.camera import camera_updater

from observatory.devices.observing_conditions import AlpaqueroObservingConditions
from alpaquero.factories.observing_conditions import observing_conditions_factory
from alpaquero.updaters.observing_conditions import observing_conditions_updater

from observatory.devices.cover import AlpaqueroCover
from alpaquero.factories.cover import cover_factory
from alpaquero.updaters.cover import cover_updater

from observatory.devices.filterwheel import AlpaqueroFilterWheel
from alpaquero.factories.filterwheel import filterwheel_factory
from alpaquero.updaters.filterwheel import filterwheel_updater

from observatory.devices.safety_monitor import AlpaqueroSafetyMonitor
from alpaquero.factories.safety_monitor import safety_monitor_factory
from alpaquero.updaters.safety_monitor import safety_monitor_updater

from observatory.devices.dome import AlpaqueroDome
from alpaquero.factories.dome import dome_factory
from alpaquero.updaters.dome import dome_updater

from observatory.devices.switch import AlpaqueroSwitch
from alpaquero.factories.switch import switch_factory
from alpaquero.updaters.switch import switch_updater

from observatory.devices.telescope import AlpaqueroTelescope
from alpaquero.factories.telescope import telescope_factory
from alpaquero.updaters.telescope import telescope_updater

from observatory.instrument import Instrument, InstrumentRegistry

from observatory.state import StateManager
from observatory.sequence_registry import SequenceRegistry

from observatory.status import observatory_loop
from observatory.utils.config import load_observatory_config
from observatory.preview import CapturePreview, CaptureBuffer

# Imports for ActionRegistry
import observatory.utils.debug
import astro.calib_reduction, astro.astro_catalog, astro.platesolve

class Observatory:
    def __init__(self):
        self.domes: Dict[str, 'AlpaqueroDome'] = {}
        self.telescopes: Dict[str, 'AlpaqueroTelescope'] = {}
        self.observing_conditions: Dict[str, 'AlpaqueroObservingConditions'] = {}
        self.safety_monitors: Dict[str, 'AlpaqueroSafetyMonitor'] = {}
        self.covers: Dict[str, 'AlpaqueroCover'] = {}
        self.cameras: Dict[str, 'AlpaqueroCamera'] = {}
        self.filterwheels: Dict[str, 'AlpaqueroFilterWheel'] = {}
        self.switches: Dict[str, 'AlpaqueroSwitch'] = {}
        self.configured_devices: List[Dict[str, Any]] = []
        self.webcams: List[str] = []
        self.base_path: Path = Path(__file__).resolve().parent
        self.capture_buffer = CaptureBuffer(maxlen=10)

        self.sequence_registry = SequenceRegistry()

        # overwritten from config in startup()
        self.name = "Alpaquero Observatory"
        self.latitude = 0.0
        self.longitude = 0.0

        self.instrument_registry = None  # Will be initialized in startup() after loading config

        self.status = "initializing"

        # Init state
        self.state = StateManager()


    def startup(self):
        config = load_observatory_config()
        self.load_sequence_catalog()
        self.webcams = config.get("webcams", [])
        self.base_path = Path(config.get("base_path", self.base_path))
        # Create all devices discovered in config
        for device in config.get("devices", []):
            print(device)
            device_type = device.get("type")
            device_id = device.get("id")
            name = device.get("name")
            poll_time = device.get("poll_time", 1)
            auto_connect = device.get("auto_connect", False)

            host = device.get("host")
            port = device.get("port")
            device_number = device.get("device_number")

            self.configured_devices.append({
                "type": device_type,
                "id": device_id,
                "name": name
            })
            if device_type == "dome":
                device_alpaquero = AlpaqueroDome(
                    observatory=self,
                    factory=lambda h=host, p=port, did=device_id, dn=device_number: dome_factory(
                        address=f"{h}:{p}",
                        id=did,
                        device_number=dn,
                        state=self.state
                    ),
                    updater=lambda did=device_id: dome_updater(
                        dome=self.domes[did],
                        id=did,
                        state=self.state
                    ),
                    id=device_id,
                    name=name,
                    poll_time=poll_time,
                )
                self.domes[device_id] = device_alpaquero
            elif device_type == "telescope":
                device_alpaquero = AlpaqueroTelescope(
                    observatory=self,
                    factory=lambda h=host, p=port, did=device_id, dn=device_number: telescope_factory(
                        address=f"{h}:{p}",
                        id=did,
                        device_number=dn,
                        state=self.state
                    ),
                    updater=lambda did=device_id: telescope_updater(
                        telescope=self.telescopes[did],
                        id=did,
                        state=self.state
                    ),
                    id=device_id,
                    name=name,
                    poll_time=poll_time,
                )
                self.telescopes[device_id] = device_alpaquero
            elif device_type == "camera":
                device_alpaquero = AlpaqueroCamera(
                    observatory=self,
                    factory=lambda h=host, p=port, did=device_id, dn=device_number: camera_factory(
                        address=f"{h}:{p}",
                        id=did,
                        device_number=dn,
                        state=self.state
                    ),
                    updater=lambda did=device_id: camera_updater(
                        camera=self.cameras[did],
                        id=did,
                        state=self.state
                    ),
                    id=device_id,
                    name=name,
                    poll_time=poll_time,
                )
                self.cameras[device_id] = device_alpaquero
            elif device_type == "observing_conditions":
                device_alpaquero = AlpaqueroObservingConditions(
                    observatory=self,
                    factory=lambda h=host, p=port, did=device_id, dn=device_number: observing_conditions_factory(
                        address=f"{h}:{p}",
                        id=did,
                        device_number=dn,
                        state=self.state
                    ),
                    updater=lambda did=device_id: observing_conditions_updater(
                        observing_conditions=self.observing_conditions[did],
                        id=did,
                        state=self.state
                    ),
                    id=device_id,
                    name=name,
                    poll_time=poll_time,
                )
                self.observing_conditions[device_id] = device_alpaquero
            elif device_type == "safety_monitor":
                device_alpaquero = AlpaqueroSafetyMonitor(
                    observatory=self,
                    factory=lambda h=host, p=port, did=device_id, dn=device_number: safety_monitor_factory(
                        address=f"{h}:{p}",
                        id=did,
                        device_number=dn,
                        state=self.state
                    ),
                    updater=lambda did=device_id: safety_monitor_updater(
                        safety_monitor=self.safety_monitors[did],
                        id=did,
                        state=self.state
                    ),
                    id=device_id,
                    name=name,
                    poll_time=poll_time,
                )
                self.safety_monitors[device_id] = device_alpaquero
            elif device_type == "cover":
                device_alpaquero = AlpaqueroCover(
                    observatory=self,
                    factory=lambda h=host, p=port, did=device_id, dn=device_number: cover_factory(
                        address=f"{h}:{p}",
                        id=did,
                        device_number=dn,
                        state=self.state
                    ),
                    updater=lambda did=device_id: cover_updater(
                        cover=self.covers[did],
                        id=did,
                        state=self.state
                    ),
                    id=device_id,
                    name=name,
                    poll_time=poll_time,
                )
                self.covers[device_id] = device_alpaquero
            elif device_type == "filterwheel":
                device_alpaquero = AlpaqueroFilterWheel(
                    observatory=self,
                    factory=lambda h=host, p=port, did=device_id, dn=device_number: filterwheel_factory(
                        address=f"{h}:{p}",
                        id=did,
                        device_number=dn,
                        state=self.state
                    ),
                    updater=lambda did=device_id: filterwheel_updater(
                        filterwheel=self.filterwheels[did],
                        id=did,
                        state=self.state
                    ),
                    id=device_id,
                    name=name,
                    poll_time=poll_time,
                )
                self.filterwheels[device_id] = device_alpaquero
            elif device_type == "switch":
                device_alpaquero = AlpaqueroSwitch(
                    observatory=self,
                    factory=lambda h=host, p=port, did=device_id, dn=device_number: switch_factory(
                        address=f"{h}:{p}",
                        id=did,
                        device_number=dn,
                        state=self.state
                    ),
                    updater=lambda did=device_id: switch_updater(
                        switch_device=self.switches[did],
                        id=did,
                        state=self.state
                    ),
                    id=device_id,
                    name=name,
                    poll_time=poll_time,
                )
                self.switches[device_id] = device_alpaquero
            else:
                raise ValueError(f"Unknown device type: {device_type}")

            
            if auto_connect:
                print("="*40, "reached auto connect for", device_type, name)
                device_alpaquero.connect()

        observatory_config = config.get("observatory", {})
        self.name = observatory_config.get("name", self.name)
        self.latitude = observatory_config.get("latitude", self.latitude)
        self.longitude = observatory_config.get("longitude", self.longitude)
        

        instruments = []
        for instrument in observatory_config.get("instruments", []):
            instrument_obj = Instrument(
                id=instrument.get("id"),
                name=instrument.get("name"),
                telescope=instrument.get("telescope"),
                focal_length=instrument.get("focal_length"),
                aperture_diameter=instrument.get("aperture_diameter"),
                devices=instrument.get("devices", [])
            )
            instruments.append(instrument_obj)
        self.instrument_registry = InstrumentRegistry(instruments)

        # Start observatory loops
        asyncio.create_task(observatory_loop(self.state, self))

    def load_sequence_catalog(self, catalog_dir: Path | None = None) -> None:
        from observatory.sequence_parser import SequenceParser

        if catalog_dir is None:
            catalog_dir = Path(__file__).resolve().parent / "sequences"
        if not catalog_dir.exists():
            return

        sequence_paths = sorted(
            path
            for pattern in ("*.yaml", "*.yml")
            for path in catalog_dir.glob(pattern)
        )
        for sequence_path in sequence_paths:
            try:
                yaml_string = sequence_path.read_text(encoding="utf-8")
                sequence_builder = SequenceParser(yaml_string, self)
                self.sequence_registry.add_sequence(sequence_builder)
            except Exception as e:
                handle_error(e, f"Skipping invalid sequence file {sequence_path}", level="warning")

    def emergency_shutdown(self):
        print("Performing emergency shutdown procedures")
        for telescope in self.telescopes.values():
            try:
                telescope.park()
            except Exception as e:
                handle_error(e, f"Error parking telescope {telescope.name} during emergency shutdown", level="error")
        for cover in self.covers.values():
            try:
                cover.close(override=True)
            except Exception as e:
                handle_error(e, f"Error closing cover {cover.name} during emergency shutdown", level="error")
        for dome in self.domes.values():
            try:
                dome.close(override=True)
            except Exception as e:
                handle_error(e, f"Error closing dome {dome.name} during emergency shutdown", level="error")

    def emergency_halt(self):
        # TODO stop all sequences
        print("Emergency halt triggered")
        for telescope in self.telescopes.values():
            try:
                telescope.alpaca.AbortSlew()
            except Exception as e:
                handle_error(e, f"Error aborting slew for telescope {telescope.name} during emergency halt", level="error")
        for cover in self.covers.values():
            try:
                cover.alpaca.HaltCover()
            except Exception as e:
                handle_error(e, f"Error halting cover {cover.name} during emergency halt", level="error")
        for dome in self.domes.values():
            try:
                dome.alpaca.AbortSlew()
            except Exception as e:
                handle_error(e, f"Error aborting slew for dome {dome.name} during emergency halt", level="error")

    def get_device(self, device_id: str):
        for device_dict in [self.domes, self.telescopes, self.cameras, self.observing_conditions, self.safety_monitors, self.covers, self.filterwheels, self.switches]:
            if device_id in device_dict:
                return device_dict[device_id]
        raise ValueError(f"Device with id {device_id} not found")
    
    @ActionRegistry.register("set_status", observatory_arg=True, action_type="observatory")
    def set_status(self, status: str):
        self.state.set_status(status)

    def add_capture_preview(self, name: str, img, timestamp):
        preview = CapturePreview(name, img, timestamp)
        self.capture_buffer.push(preview)

    def get_capture_previews(self, n: int):
        return self.capture_buffer.get_previews(n)
    
    def get_full_preview_image(self, name: str):
        return self.capture_buffer.get_full_image(name)
