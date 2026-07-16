from typing import TYPE_CHECKING, Any, Dict, List
import asyncio
from contextlib import suppress
from pathlib import Path

from observatory.action_registry import ActionRegistry
from observatory.error_handler import handle_error
from observatory.device_registry import DEVICE_SPECS

from observatory.instrument import Instrument, InstrumentRegistry

from observatory.state import StateManager
from observatory.sequence_registry import SequenceRegistry

from observatory.status import observatory_loop
from observatory.utils.config import load_observatory_config
from observatory.preview import CapturePreview, CaptureBuffer

# Imports for ActionRegistry
import observatory.utils.debug
import astro.calib_reduction, astro.astro_catalog, astro.platesolve

if TYPE_CHECKING:
    from observatory.devices.camera import AlpaqueroCamera
    from observatory.devices.cover import AlpaqueroCover
    from observatory.devices.dome import AlpaqueroDome
    from observatory.devices.filterwheel import AlpaqueroFilterWheel
    from observatory.devices.focuser import AlpaqueroFocuser
    from observatory.devices.observing_conditions import AlpaqueroObservingConditions
    from observatory.devices.safety_monitor import AlpaqueroSafetyMonitor
    from observatory.devices.switch import AlpaqueroSwitch
    from observatory.devices.telescope import AlpaqueroTelescope

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
        self.focusers: Dict[str, 'AlpaqueroFocuser'] = {}
        self.configured_devices: List[Dict[str, Any]] = []
        self.configured_instruments: List[Dict[str, Any]] = []
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
        self._observatory_task: asyncio.Task | None = None


    def startup(self):
        config = load_observatory_config()
        self.load_sequence_catalog()
        self.webcams = config.get("webcams", [])
        self.base_path = Path(config.get("base_path", self.base_path))
        for device in config.get("devices", []):
            device_alpaquero = self._load_device(device)
            self.configured_devices.append({
                "type": device.get("type"),
                "id": device.get("id"),
                "name": device.get("name"),
            })

            if device.get("auto_connect", False):
                device_alpaquero.connect()

        observatory_config = config.get("observatory", {})
        self.name = observatory_config.get("name", self.name)
        self.latitude = observatory_config.get("sitelat", self.latitude)
        self.longitude = observatory_config.get("sitelon", self.longitude)
        

        instruments = []
        for instrument in observatory_config.get("instruments", []):
            print("Loading instrument:", instrument)
            instrument_obj = Instrument(
                id=instrument.get("id"),
                name=instrument.get("name"),
                telescope=instrument.get("telescope"),
                focal_length=instrument.get("focal_length"),
                aperture_diameter=instrument.get("aperture_diameter"),
                devices=instrument.get("devices", [])
            )
            instruments.append(instrument_obj)

            self.configured_instruments.append({
                "id": instrument_obj.id,
                "name": instrument_obj.name,
                "devices": instrument_obj.devices
            })
        print("Loaded instruments:", [instr.name for instr in instruments])
        self.instrument_registry = InstrumentRegistry(instruments)

        # Start observatory loops
        self._observatory_task = asyncio.create_task(observatory_loop(self.state, self))

    def _load_device(self, config: Dict[str, Any]):
        device_type = config.get("type")
        device_id = config.get("id")

        try:
            spec = DEVICE_SPECS[device_type]
        except KeyError:
            raise ValueError(f"Unknown device type: {device_type!r}") from None

        devices = getattr(self, spec.collection)
        address = f"{config.get('host')}:{config.get('port')}"
        device_number = config.get("device_number")

        def create_alpaca_device():
            return spec.factory(
                address=address,
                id=device_id,
                device_number=device_number,
                state=self.state,
            )

        def update_device():
            return spec.updater(
                **{spec.updater_device_arg: devices[device_id]},
                id=device_id,
                state=self.state,
            )

        instance = spec.wrapper(
            observatory=self,
            factory=create_alpaca_device,
            updater=update_device,
            id=device_id,
            name=config.get("name"),
            poll_time=config.get("poll_time", 1),
        )
        devices[device_id] = instance
        return instance

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
    
    def refresh_sequence_catalog(self):
        self.sequence_registry.clear()
        self.load_sequence_catalog()

    def _iter_devices(self):
        for spec in DEVICE_SPECS.values():
            yield from getattr(self, spec.collection).values()

    async def shutdown(self, *, timeout: float = 10) -> None:
        print("Shutting down observatory services...")
        self.status = "shutting_down"

        if self._observatory_task and not self._observatory_task.done():
            self._observatory_task.cancel()
            with suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(self._observatory_task, timeout=timeout)
        self._observatory_task = None

        await self.sequence_registry.shutdown(timeout=timeout)

        devices = list(self._iter_devices())
        if devices:
            shutdown_pairs = [
                (device, device.shutdown(timeout=timeout))
                for device in devices
                if hasattr(device, "shutdown")
            ]
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(
                        *(shutdown for _, shutdown in shutdown_pairs),
                        return_exceptions=True,
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                handle_error("Timed out while shutting down devices", level="warning")
            else:
                for (device, _), result in zip(shutdown_pairs, results):
                    if isinstance(result, Exception):
                        handle_error(
                            result,
                            f"Error shutting down device {device.name}",
                            level="warning",
                        )

        self.status = "shutdown"

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
        for spec in DEVICE_SPECS.values():
            devices = getattr(self, spec.collection)
            if device_id in devices:
                return devices[device_id]
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
    

