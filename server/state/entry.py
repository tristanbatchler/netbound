from server.state import LoggedState
from server.state.base import BaseState
from server.packet import BasePacket, LoginPacket, RegisterPacket, OkPacket

class EntryState(BaseState):
    async def handle_login(self, p: LoginPacket) -> None:
        await self._queue_local_client_send(OkPacket(from_pid=self._pid))
        self._change_states(LoggedState(self._pid, self._change_states, self._queue_local_protos_send, self._queue_local_client_send))

    def handle_register(self, p: RegisterPacket) -> None:
        ...
