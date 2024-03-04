from server.packet import BasePacket

class BaseState:
    def __init__(self, pid: bytes) -> None:
        self._pid: bytes = pid

    def handle_packet(self, p: BasePacket) -> None:
        raise NotImplementedError("Subclasses must implement this method")
