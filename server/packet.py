import json
import msgpack
from pydantic import BaseModel, ValidationError
from typing import Any, Type, Optional

DEFINITIONS_FILE: str = "shared/packet/definitions.json"

class BasePacket(BaseModel):
    from_pid: bytes
    to_pid: bytes | list[bytes]

    def serialize(self) -> bytes:
        data = {}
        packet_name = self.__class__.__name__.removesuffix("Packet").title()
        m_dump = self.model_dump()
        data[packet_name] = m_dump
        return msgpack.packb(data, use_bin_type=True)
    
    def __repr__(self) -> str:
        d: dict[str, Any] = self.__dict__.copy()
        d["from_pid"] = d["from_pid"].hex()
        if isinstance(self.to_pid, list):
            d["to_pid"] = [x.hex() for x in d["to_pid"]]
        else:
            d["to_pid"] = d["to_pid"].hex()
        return f"{self.__class__.__name__}{d}"
    
    def __str__(self) -> str:
        return self.__repr__()

class OkPacket(BasePacket):
    ...

class DenyPacket(BasePacket):
    reason: Optional[str] = None

class PIDPacket(BasePacket):
    pid: bytes

class LoginPacket(BasePacket):
    username: str
    password: str

class RegisterPacket(BasePacket):
    username: str
    password: str

class DisconnectPacket(BasePacket):
    reason: str

class MalformedPacketError(ValueError):
    pass

class UnknownPacketError(ValueError):
    pass

def deserialize(packet_: bytes) -> BasePacket:
    try:
        packet_dict: dict[str, Any] = msgpack.unpackb(packet_, raw=False)
    except msgpack.StackError:
        raise MalformedPacketError("Packet too nested to unpack")
    except msgpack.ExtraData:
        raise MalformedPacketError("Extra data was sent with the packet")
    except msgpack.FormatError:
        raise MalformedPacketError("Packet is malformed")
    except msgpack.UnpackValueError:
        raise MalformedPacketError("Packet has missing data")

    if len(packet_dict) == 0:
        raise MalformedPacketError("Empty packet")

    packet_name: Any = list(packet_dict.keys())[0]
    if not isinstance(packet_name, str):
        raise MalformedPacketError(f"Invalid packet name (not a string): {packet_name}")

    packet_data: dict = packet_dict[packet_name]

    class_name: str = packet_name.title() + "Packet"

    try:
        packet_class: Type[BasePacket] = globals()[class_name]
    except KeyError:
        raise UnknownPacketError(f"Packet name not recognized: {packet_name}")
    
    try:
        packet_class.model_validate(packet_data)
    except ValidationError as e:
        raise MalformedPacketError(f"Packet data does not match expected schema: {e}")

    try:
        return packet_class(**packet_data)
    except TypeError as e:
        raise MalformedPacketError(f"Packet data does not match expected signature: {e}")


schema: dict[str, Any] = {}
for item, type_ in globals().copy().items():
    if isinstance(type_, type) and issubclass(type_, BasePacket):
        schema[item] = type_.model_json_schema()
        schema[item].pop("title")

with open(DEFINITIONS_FILE, "w") as f:
    json.dump(schema, f, indent=4)