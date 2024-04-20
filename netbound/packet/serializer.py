from __future__ import annotations
from abc import ABC, abstractmethod
from netbound.packet import BasePacket, MalformedPacketError, UnknownPacketError
from pydantic import ValidationError
from typing import Any, Type
import base64
import msgpack

class BaseSerializer(ABC):
    @abstractmethod
    def serialize(self, packet: BasePacket) -> bytes:
        """
        Converts the packet to bytes to be sent over the network.
        """
        pass

    @abstractmethod
    def deserialize(self, data: bytes) -> BasePacket:
        """
        Converts bytes to a packet object. The returned object will be an instance of the specific
        packet class that the packet data corresponds to. Raises `MalformedPacketError` if the 
        packet data is invalid. Raises `UnknownPacketError` if the packet class is not defined. 
        """
        pass

class MessagePackSerializer(BaseSerializer):
    def serialize(self, packet: BasePacket) -> bytes:
        """
        Converts the packet to a MessagePack-encoded byte string to be sent over the network. The 
        PID values are sent as base64-encoded strings.
        """
        data = {}
        packet_name = packet.__class__.__name__.removesuffix("Packet").title()
        m_dump = packet.model_dump()

        data[packet_name] = m_dump
        return msgpack.packb(data, use_bin_type=True)
    
    def deserialize(self, packet: bytes) -> BasePacket:
        """
        Converts a MessagePack-encoded byte string to a packet object. The returned object will be an 
        instance of the specific packet class that the packet data corresponds to.
        """
        try:
            packet_dict: dict[str, Any] = msgpack.unpackb(packet, raw=False)
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
        
        # PIDs are sent as b64-encoded strings, but we need them as bytes
        for _pid_key in ["to_pid", "from_pid"]:
            if _pid_key in packet_data:
                packet_data[_pid_key] = base64.b64decode(packet_data[_pid_key])


        class_name: str = packet_name.lower() + "packet"
        packet_class = None
        for _name, _class in globals().items():
            if _name.lower() == class_name:
                packet_class = _class
                break
        if packet_class is None:
            raise UnknownPacketError(f"Packet name not recognized: {packet_name}")
        
        try:
            packet_class.model_validate(packet_data)
        except ValidationError as e:
            raise MalformedPacketError(f"Packet data {packet_data} does not match expected schema: {e}")

        try:
            return packet_class(**packet_data)
        except TypeError as e:
            raise MalformedPacketError(f"Packet data does not match expected signature: {e}")

def register_packet(packet: Type[BasePacket]) -> None:
    """
    Injects a user-defined packet into the engine's global namespace so that it can be deserialized.
    """
    globals()[packet.__name__] = packet