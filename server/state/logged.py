import logging
from server.state import BaseState
from server.packet import BasePacket, ChatPacket, DisconnectPacket, DenyPacket
from server.constants import ONLY_CLIENT, EVERYONE, ONLY_PROTO

class LoggedState(BaseState):
    async def handle_packet(self, p: BasePacket) -> None:
        if isinstance(p, ChatPacket):
            await self._handle_chat(p)
        elif isinstance(p, DisconnectPacket):
            await self._handle_disconnect(p)
        # elif isinstance(p, DenyPacket):
        #     self._handle_deny(p)

    async def _handle_chat(self, p: ChatPacket) -> None:
        logging.debug(f"HANDLING CHAT FOR {self._pid.hex()[:8]}: {p}")

        # If this came from our own client, forward it on
        if p.from_pid == self._pid:
            if p.to_pid == EVERYONE:
                await self._queue_local_send(ChatPacket(from_pid=self._pid, to_pid=EVERYONE, exclude_sender=True, message=p.message))
            elif p.to_pid == ONLY_PROTO:
                logging.warning(f"I don't know what to do with a chat packet from {self._pid.hex()} to ONLY_PROTO")
            elif p.to_pid == ONLY_CLIENT:
                logging.warning(f"I don't know what to do with a chat packet from {self._pid.hex()} to ONLY_CLIENT")

        # If this came from a different protocol, forward it to our client
        else:
            await self._queue_local_send(ChatPacket(from_pid=p.from_pid, to_pid=self._pid, message=p.message))

        
    async def _handle_disconnect(self, p: DisconnectPacket) -> None:
        # Forward the disconnect packet to the client
        await self._queue_local_send(DisconnectPacket(from_pid=p.from_pid, to_pid=ONLY_CLIENT, reason=p.reason))
        
        