import logging
from server.state import BaseState
from server.packet import BasePacket, LoginPacket, RegisterPacket, PIDPacket

class EntryState(BaseState):
    def handle_packet(self, p: BasePacket) -> None:
        if isinstance(p, LoginPacket):
            self._handle_login(p)
        elif isinstance(p, RegisterPacket):
            self._handle_register(p)
        
    def _handle_login(self, p: LoginPacket) -> None:
        logging.debug(f"HANDLING LOGIN FOR {self._pid.hex()}: {p}")

    def _handle_register(self, p: RegisterPacket) -> None:
        logging.debug(f"HANDLING REGISTER FOR {self._pid.hex()}: {p}")
