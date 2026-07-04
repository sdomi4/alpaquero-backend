



from collections import defaultdict


class Instrument:
    def __init__(self,
        id: str,
        name: str,
        telescope: str,
        focal_length: float,
        aperture_diameter: float,
        devices: list
    ):
        self.id = id
        self.name = name
        self.telescope = telescope
        self.focal_length = focal_length
        self.aperture_diameter = aperture_diameter
    
        
        self.devices = devices

    @property
    def aperture_area(self) -> float:
        radius = self.aperture_diameter / 2
        return 3.141592653589793 * radius**2
    
    def __str__(self):
        return f"Instrument: {self.name}, Devices: {self.devices}"

class InstrumentRegistry:
    def __init__(self, instruments: list["Instrument"]):
        self.instruments = {instrument.id: instrument for instrument in instruments}
        self._by_device: dict[str, set[str]] = defaultdict(set)

        for instrument in instruments:
            for device in instrument.devices:
                for _, device_id in device.items():
                    self._by_device[device_id].add(instrument.id)

    def __str__(self):
        return f"InstrumentRegistry: {list(self.instruments.keys())}"
    
    def get_by_device(self, device_id: str) -> list["Instrument"]:
        return [
            self.instruments[instrument_id]
            for instrument_id in self._by_device.get(device_id, set())
        ]