# BaseController

A controller adds runtime behavior - connections, caching, state machines - to a data model. oold-python keeps these concerns separate: the data model is a pure `LinkedBaseModel`, and the controller is a mixin that inherits from both `BaseController` and the data model.

---

## Why a controller?

| Data model | Controller |
|---|---|
| Serializable, version-controlled | Lives only at runtime |
| Stored in the backend | Never persisted |
| Passed between systems | Machine- or session-local |
| e.g. `Robot.joint_count` | e.g. `RobotController._socket` |

Keeping them separate means `to_json()` / `to_jsonld()` always produces clean, controller-free documents - and the backend type registry always resolves to the pure data class.

---

## Basic pattern

```python
from oold.model import BaseController, LinkedBaseModel

class Robot(LinkedBaseModel):
    id: str
    name: str
    joint_count: int = 6
    connection_url: str = ""

class RobotController(BaseController, Robot):
    _connected: bool = False   # controller-only state (underscore prefix)

    def connect(self) -> None:
        self._connected = True
        print(f"Connected to {self.connection_url}")

    def move(self, joint: int, angle: float) -> None:
        if not self._connected:
            raise RuntimeError("Not connected")
        print(f"Joint {joint} → {angle}°")

ctrl = RobotController(
    id="ex:robot-1",
    name="arm-1",
    connection_url="tcp://192.168.1.10:5000",
)
ctrl.connect()
ctrl.move(1, 45.0)
```

---

## Serialization

`to_json()` and `to_jsonld()` on a controller instance only include fields defined on the underlying data model. Controller state (private `_` attributes and non-model fields) is stripped automatically.

```python
print(ctrl.to_json())
```

```json
{
  "id": "ex:robot-1",
  "name": "arm-1",
  "joint_count": 6,
  "connection_url": "tcp://192.168.1.10:5000"
}
```

`_connected` does not appear in the output.

---

## Type registry behavior

A controller is kept out of `_types`, the data model registry, and collected in `_controller_types` instead. The data model therefore stays the class a type IRI maps to, and `to_json()` keeps producing controller-free documents.

Resolution still hands out the controller: `from_json()`, `from_jsonld()` and anything else going through `resolve_type()` return `RobotController` for `"ex:robot-1"`, so behaviour is available wherever a model is read back. Pass `prefer_controller=False` to `resolve_type()` to get the pure `Robot` class.

When several controllers answer to the same IRI, the one registered **last** wins - a package imported later overrides an implementation without the earlier one knowing about it. Every registration is logged at `INFO` under the `oold.model` logger, and an override at `WARNING`, so an unexpected winner is visible:

```python
import logging
logging.getLogger("oold.model").setLevel(logging.INFO)
```

Resolution never crosses pydantic versions: `oold.model` and `oold.model.v1` keep separate registries, and a lookup is answered from the one the model registry belongs to.

To pick a controller explicitly, construct it from the data model:

```python
ctrl = RobotController(robot, connection_url="tcp://192.168.1.10:5000")
```

---

## Multi-model controller

A controller can extend multiple data models. Type arrays from all parent models are merged:

```python
class Sensor(LinkedBaseModel):
    id: str
    sensor_type: str = "temperature"

class RobotWithSensor(BaseController, Robot, Sensor):
    _calibrated: bool = False

    def calibrate(self) -> None:
        self._calibrated = True
        print(f"Sensor calibrated: {self.sensor_type}")

combined = RobotWithSensor(
    id="ex:robot-sensor-1",
    name="arm-2",
    sensor_type="force",
)
combined.calibrate()
print(combined.to_json())
# includes fields from both Robot and Sensor, no controller state
```

---

## Archiving and state persistence

While the controller itself is not persisted, you can explicitly archive the data model portion at any time:

```python
# Store only the data model fields
ctrl.store_jsonld()   # writes to the registered backend for ctrl.id's prefix
```

This is useful for checkpointing state (e.g. saving `joint_count` after a calibration) without persisting the live connection handle.

---

## Guidelines

- Prefix controller-only attributes with `_` to make the distinction explicit
- Keep `__init__` arguments limited to data model fields - controllers should be constructed from data, not from runtime handles
- If a controller needs runtime resources (sockets, threads), initialize them in a dedicated `connect()` / `start()` method, not in `__init__`
