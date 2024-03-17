from __future__ import annotations
import logging
from server.state import BaseState
from dataclasses import dataclass
from server.packet import ChatPacket, DisconnectPacket, HelloPacket, MovePacket
from server.constants import EVERYONE
from typing import Optional
from server.state import EntryState

class LoggedState(BaseState):
    @dataclass
    class View(BaseState.View):
        name: str
        x: int
        y: int

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._known_others: dict[bytes, LoggedState.View] = {}

        self._name: str | None = None  # This will be set in on_transition (needs to be passed from EntryState)
        self._x: int = 0
        self._y: int = 0
    
    async def on_transition(self, previous_state_view: Optional[BaseState.View]=None) -> None:
        assert isinstance(previous_state_view, EntryState.View)
        if previous_state_view.username:
            self._name = previous_state_view.username
        else:
            err: str = "LoggedState requires a username but EntryState did not have one"
            logging.error(err)
            raise ValueError(err)
        await self._queue_local_protos_send(HelloPacket(from_pid=self._pid, to_pid=EVERYONE, state_view=self.view_dict))

    async def handle_chat(self, p: ChatPacket) -> None:
        logging.info(f"Received {p}")
        # If this came from our own client, forward it on
        if p.from_pid == self._pid:
            logging.info("GOT THE MESSAGE FROM OUR OWN CLIENT")
            await self._queue_local_protos_send(ChatPacket(from_pid=self._pid, to_pid=p.to_pid, exclude_sender=True, message=p.message))
            await self._queue_local_client_send(ChatPacket(from_pid=self._pid, message=p.message))

        # If this came from a different protocol, forward it directly to our client
        else:
            await self._queue_local_client_send(ChatPacket(from_pid=p.from_pid, message=p.message))

    async def handle_disconnect(self, p: DisconnectPacket) -> None:
        # Forward the disconnect packet to the client
        await self._queue_local_client_send(DisconnectPacket(from_pid=p.from_pid, reason=p.reason))
        self._known_others.pop(p.from_pid, None)

    async def handle_hello(self, p: HelloPacket) -> None:
        # Forward the information straight to the client
        await self._queue_local_client_send(HelloPacket(from_pid=p.from_pid, state_view=p.state_view))

        if p.from_pid != self._pid and p.from_pid not in self._known_others:
            # Record information about the other protocol
            self._known_others[p.from_pid] = LoggedState.View(**p.state_view)

            # Tell the other protocol about us
            await self._queue_local_protos_send(HelloPacket(from_pid=self._pid, to_pid=p.from_pid, state_view=self.view_dict))

    async def handle_move(self, p: MovePacket) -> None:
        logging.info(f"RECEIVED A MOVE PACKET: {p}")
        await self._queue_local_client_send(MovePacket(from_pid=p.from_pid, dx=p.dx, dy=p.dy))
        if p.from_pid == self._pid:
            self._x += p.dx
            self._y += p.dy
            await self._queue_local_protos_send(MovePacket(from_pid=self._pid, to_pid=EVERYONE, exclude_sender=True, dx=p.dx, dy=p.dy))
        elif p.from_pid in self._known_others:
            other: LoggedState.View = self._known_others[p.from_pid]
            other.x += p.dx
            other.y += p.dy
            