from __future__ import annotations
import logging
from server.state import BaseState
from dataclasses import dataclass
from server.packet import ChatPacket, DisconnectPacket, HelloPacket, MovePacket
from server.constants import EVERYONE
from typing import Optional
from server.state import EntryState
from server.database.model import User, Entity, InstancedEntity, Player
from sqlalchemy import select

class LoggedState(BaseState):
    @dataclass
    class View(BaseState.View):
        name: str
        x: int
        y: int

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._known_others: dict[bytes, LoggedState.View] = {}
        self._entity: Entity | None = None
        self._instanced_entity: InstancedEntity | None = None
        self._player: Player | None = None

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
        
        async with self._get_db_session() as session:
            user: User = (await session.execute(select(User).where(User.username == self._name))).scalar_one_or_none()
            self._player = (await session.execute(select(Player).where(Player.user_id == user.id))).scalar_one_or_none()
            self._entity = (await session.execute(select(Entity).where(Entity.id == self._player.entity_id))).scalar_one_or_none()
            self._instanced_entity = (await session.execute(select(InstancedEntity).where(InstancedEntity.entity_id == self._player.instanced_entity_id))).scalar_one_or_none()

            self._name = self._entity.name
            self._x = self._instanced_entity.x
            self._y = self._instanced_entity.y
    

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
        await self._queue_local_client_send(MovePacket(from_pid=p.from_pid, dx=p.dx, dy=p.dy))
        if p.from_pid == self._pid:
            self._x += p.dx
            self._y += p.dy
            await self._queue_local_protos_send(MovePacket(from_pid=self._pid, to_pid=EVERYONE, exclude_sender=True, dx=p.dx, dy=p.dy))

            async with self._get_db_session() as session:
                instanced_entity = await session.get(InstancedEntity, self._instanced_entity.id)
                instanced_entity.x = self._x
                instanced_entity.y = self._y
                await session.commit()

        elif p.from_pid in self._known_others:
            other: LoggedState.View = self._known_others[p.from_pid]
            other.x += p.dx
            other.y += p.dy
            