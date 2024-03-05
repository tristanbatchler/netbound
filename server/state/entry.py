from server.state import LoggedState
from server.state.base import BaseState
from server.packet import BasePacket, LoginPacket, RegisterPacket, OkPacket
from server.constants import ONLY_CLIENT

class EntryState(BaseState):
    async def handle_packet(self, p: BasePacket) -> None:
        if isinstance(p, LoginPacket):
            await self._handle_login(p)
        elif isinstance(p, RegisterPacket):
            self._handle_register(p)
        
    async def _handle_login(self, p: LoginPacket) -> None:
        await self._queue_local_send(OkPacket(from_pid=self._pid, to_pid=ONLY_CLIENT))
        self._change_states(LoggedState(self._pid, self._change_states, self._queue_local_send))

    def _handle_register(self, p: RegisterPacket) -> None:
        ...
