import json
from pydantic import BaseModel, ValidationError
from typing import Any, Type, Optional

DEFINITIONS_FILE: str = "shared/packet/definitions.json"

class BasePacket(BaseModel):
    from_pid: int
    to_pid: int | list[int]

    def serialize(self) -> bytes:
        type_str: str = self.__class__.__name__.removesuffix("Packet").lower()
        return json.dumps({
            type_str: self.__dict__ 
        }).encode("utf-8")
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.__dict__})"
    
    def __str__(self) -> str:
        return self.__repr__()

class OkPacket(BasePacket):
    ...

class DenyPacket(BasePacket):
    reason: Optional[str] = None

class PIDPacket(BasePacket):
    pid: int

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

def deserialize(packet_: str | bytes) -> BasePacket:
    try:
        packet_dict: dict = json.loads(packet_)
    except json.JSONDecodeError:
        raise MalformedPacketError("Invalid JSON")

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