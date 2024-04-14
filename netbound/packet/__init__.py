from netbound.constants import EVERYONE
from pydantic import BaseModel
from typing import *
from abc import ABC
import base64

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
    
    def __repr__(self) -> str:
        TO_PID: str = "to_pid"
        FROM_PID: str = "from_pid"
        d: dict[str, Any] = self.__dict__.copy()
        d[FROM_PID] = base64.b64encode(self.from_pid).decode()

        if self.to_pid == EVERYONE:
            d[TO_PID] = "EVERYONE"
        elif self.to_pid is None:
            d[TO_PID] = d[FROM_PID]
        elif isinstance(self.to_pid, Recipient):
            d[TO_PID] = base64.b64encode(self.to_pid).decode()
        else:
            d[TO_PID] = [
                base64.b64encode(x).decode()
                if x else 
                f"{base64.b64encode(self.from_pid).decode()}'s client"
                for x in self.to_pid
            ]
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

