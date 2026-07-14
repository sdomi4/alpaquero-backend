from alpaca import focuser
from time import sleep

from observatory.state import StateManager, FocuserState

class FocuserConnectionError(RuntimeError):
    pass

def focuser_factory(
        address: str,
        id: str,
        device_number: int = 0,
        state: "StateManager" = None,
    ) -> focuser.Focuser:
    try:
        print("connecting to focuser", id, address)
        f = focuser.Focuser(address, device_number)
        timeout = 0
        f.Connect()
        while f.Connecting:
                timeout += 1
                if timeout > 10:
                    print("Focuser connection timed out")
                    raise FocuserConnectionError("Focuser connection timed out")
                sleep(1)
        state.add_device(FocuserState(id=id, connected=True, position=f.Position))
        return f
    except Exception as e:
        print(f"Error connecting to focuser: {e}")
        raise FocuserConnectionError(f"Error connecting to focuser: {e}")