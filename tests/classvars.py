from pprint import pprint
from typing import ClassVar, Optional

from pydantic import BaseModel


class Physical(BaseModel):
    location: Optional[str]
    some_clsvar: ClassVar[str] = "Test"


class Manufacturer(BaseModel):
    name: Optional[str]


manuX = Manufacturer(name="ManuX")


class Device(Physical):
    manufacturer_name: ClassVar[Optional[str]]


class Spectro123(Device):
    manufacturer: ClassVar[Manufacturer] = manuX
    manufacturer_name: ClassVar[str] = "ManuX"


d = Device(location="Room 123")
# print(d.manufacturer_name) # is None
d2 = Spectro123(location="Room 1234")
print(d2.manufacturer_name)
# d2.manufacturer_name = "ManuX" # Not allowed

schema = Spectro123.model_json_schema()
pprint(schema)

jsonstr = Spectro123.model_dump_json(d2)
pprint(jsonstr)


def dump_clsvars(cls):
    for clsvar in cls.__class_vars__:
        # clsvar = "manufacturer_name"
        # value = cls.__dict__.get(clsvar, "") # only works for own classbars
        value = cls.__class__.__getattribute__(cls, clsvar)
        print(f"{clsvar}: {value}")


dump_clsvars(Spectro123)
print(Spectro123.__class__.__getattribute__(Spectro123, "manufacturer_name"))
