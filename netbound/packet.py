import msgpack
from netbound.constants import EVERYONE
from pydantic import BaseModel, ValidationError
from typing import *
import base64
from abc import ABC

Recipient = Optional[bytes]
Recipients = Optional[Union[List[Recipient], KeysView[Recipient], Set[Recipient], Tuple[Recipient, ...]]]

class BasePacket(BaseModel, ABC):
    class Config:
        arbitrary_types_allowed = True

    """
    The base packet class. All user-defined packets must inherit from this class.
    """

    from_pid: bytes
    """
    The PID of the protocol that sent this packet.
    """

    to_pid: Recipient | Recipients = None
    """
    The PID, or PIDs, of the protocol(s) that this packet is intended for. If left as `None`, it 
    the packet will be sent to the sender's own client (if the sender is a protocol) or to the 
    sender's own protocol (if the sender is a client).
    """

    exclude_sender: Optional[bool] = False
    """
    If `to_pid` is the special PID `EVERYONE`, this flag can be set to `True` to exclude the sender 
    from the list of recipients. This can be useful to avoid infinite loops when broadcasting 
    packets.
    """
    def serialize(self) -> bytes:
        """
        Converts the packet to a MessagePack-encoded byte string to be sent over the network. The 
        PID values are sent as base64-encoded strings.
        """
        data = {}
        packet_name = self.__class__.__name__.removesuffix("Packet").title()
        m_dump = self.model_dump()

        data[packet_name] = m_dump
        return msgpack.packb(data, use_bin_type=True)
    
    def __repr__(self) -> str:
        TO_PID: str = "to_pid"
        FROM_PID: str = "from_pid"
        d: dict[str, Any] = self.__dict__.copy()
        d[FROM_PID] = base64.b64encode(self.from_pid).decode()

        if self.to_pid == EVERYONE:
            d[TO_PID] = "EVERYONE"
        elif self.to_pid is None:
            d[TO_PID] = d[FROM_PID]
        elif isinstance(self.to_pid, list):
            d[TO_PID] = [
                base64.b64encode(x).decode()
                if x else 
                f"{base64.b64encode(self.from_pid).decode()}'s client"
                for x in self.to_pid
            ]
        else:
            d[TO_PID] = base64.b64encode(self.to_pid).decode()
        return f"{self.__class__.__name__}{d}"
    
    def __str__(self) -> str:
        return self.__repr__()
    
class DisconnectPacket(BasePacket):
    """
    A packet that is broadcasted to all protocols when one protocol disconnects from the server.
    """
    reason: str

class MalformedPacketError(ValueError):
    pass

class UnknownPacketError(ValueError):
    pass

def register_packet(packet: Type[BasePacket]) -> None:
    """
    Injects a user-defined packet into the engine's global namespace so that it can be deserialized.
    """
    globals()[packet.__name__] = packet

def deserialize(packet_: bytes) -> BasePacket:
    """
    Converts a MessagePack-encoded byte string to a packet object. The returned object will be an 
    instance of the specific packet class that the packet data corresponds to.
    """
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
    
    # PIDs are sent as b64-encoded strings, but we need them as bytes
    for _pid_key in ["to_pid", "from_pid"]:
        if _pid_key in packet_data:
            packet_data[_pid_key] = base64.b64decode(packet_data[_pid_key])


    class_name: str = packet_name.title() + "Packet"

    try:
        packet_class: Type[BasePacket] = globals()[class_name]
    except KeyError:
        raise UnknownPacketError(f"Packet name not recognized: {packet_name}")
    
    try:
        packet_class.model_validate(packet_data)
    except ValidationError as e:
        raise MalformedPacketError(f"Packet data {packet_data} does not match expected schema: {e}")

    try:
        return packet_class(**packet_data)
    except TypeError as e:
        raise MalformedPacketError(f"Packet data does not match expected signature: {e}")
