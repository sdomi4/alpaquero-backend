from observatory.state import StateManager, ObservingConditionsState
from observatory.devices.observing_conditions import AlpaqueroObservingConditions
from observatory.error_handler import handle_error

def observing_conditions_updater(observing_conditions: "AlpaqueroObservingConditions", id, state: "StateManager" = None):
    if not observing_conditions.alpaca.Connected:
        raise ConnectionError("Observing conditions not connected")
    
    try:
        device = state.get_device(id)
        device.connected = observing_conditions.alpaca.Connected
        device.sky_ambient = observing_conditions.alpaca.SkyTemperature - observing_conditions.alpaca.Temperature
        device.ambient = observing_conditions.alpaca.Temperature
        device.rain = observing_conditions.alpaca.RainRate
        device.wind = observing_conditions.alpaca.WindSpeed
        device.humidity = observing_conditions.alpaca.Humidity
        device.dew_point = observing_conditions.alpaca.DewPoint
        device.pressure = observing_conditions.alpaca.Pressure
        device.daylight = observing_conditions.alpaca.SkyBrightness

    except Exception as e:
        handle_error(e, "Error updating observing conditions state", level="warning")
