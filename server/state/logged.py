import logging
from server.state import BaseState
from server.packet import ChatPacket, DisconnectPacket, HelloPacket, WhoPacket
from server.constants import EVERYONE
from random import randint

class LoggedState(BaseState):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._favourite_number: int = randint(0, 100)
        self._known_others: dict[bytes, int] = {}

    async def on_transition(self) -> None:
        await self._queue_local_protos_send(HelloPacket(from_pid=self._pid, to_pid=EVERYONE, exclude_sender=True, favourite_number=self._favourite_number))

    async def handle_chat(self, p: ChatPacket) -> None:
        # If this came from our own client, forward it on
        if p.from_pid == self._pid:
                await self._queue_local_protos_send(ChatPacket(from_pid=self._pid, to_pid=p.to_pid, exclude_sender=p.to_pid==EVERYONE, message=p.message))

        # If this came from a different protocol, forward it directly to our client
        else:
            await self._queue_local_client_send(ChatPacket(from_pid=p.from_pid, message=p.message))

    async def handle_disconnect(self, p: DisconnectPacket) -> None:
        # Forward the disconnect packet to the client
        await self._queue_local_client_send(DisconnectPacket(from_pid=p.from_pid, reason=p.reason))

    async def handle_hello(self, p: HelloPacket) -> None:
        if p.from_pid == self._pid:
            logging.warning(f"Received a HelloPacket from our own client")
            return

        if p.from_pid not in self._known_others:
            # Record information about the other protocol
            await self._queue_local_client_send(HelloPacket(from_pid=p.from_pid, favourite_number=p.favourite_number))
            self._known_others[p.from_pid] = p.favourite_number

            # Tell the other protocol about us
            await self._queue_local_protos_send(HelloPacket(from_pid=self._pid, to_pid=p.from_pid, favourite_number=self._favourite_number))
