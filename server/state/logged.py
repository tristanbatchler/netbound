import logging
from server.state import BaseState
from server.packet import BasePacket, ChatPacket, DisconnectPacket, DenyPacket
from server.constants import EVERYONE

class LoggedState(BaseState):
    async def handle_packet(self, p: BasePacket) -> None:
        if isinstance(p, ChatPacket):
            await self._handle_chat(p)
        elif isinstance(p, DisconnectPacket):
            await self._handle_disconnect(p)
        # elif isinstance(p, DenyPacket):
        #     self._handle_deny(p)

    async def _handle_chat(self, p: ChatPacket) -> None:
        # If this came from our own client, forward it on
        if p.from_pid == self._pid:
                await self._queue_local_protos_send(ChatPacket(from_pid=self._pid, to_pid=p.to_pid, exclude_sender=p.to_pid==EVERYONE, message=p.message))

        # If this came from a different protocol, forward it directly to our client
        else:
            await self._queue_local_client_send(ChatPacket(from_pid=p.from_pid, message=p.message))

    async def _handle_disconnect(self, p: DisconnectPacket) -> None:
        # Forward the disconnect packet to the client
        await self._queue_local_client_send(DisconnectPacket(from_pid=p.from_pid, reason=p.reason))
