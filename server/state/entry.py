import logging
from server.state import BaseState
from server.packet import LoginPacket, RegisterPacket, OkPacket, PIDPacket, DenyPacket
from server.database.model import User, Entity, InstancedEntity, Player
from sqlalchemy import select
from dataclasses import dataclass
from server.constants import EVERYONE
from random import randint

class EntryState(BaseState):
    @dataclass
    class View(BaseState.View):
        username: str

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._username: str | None = None

    async def on_transition(self, *args, **kwargs) -> None:
        await self._queue_local_client_send(PIDPacket(from_pid=self._pid))

    async def handle_login(self, p: LoginPacket) -> None:
        async with self._get_db_session() as session:
            user: User = (await session.execute(select(User).where(User.username == p.username))).scalar_one_or_none()
            if user and user.password == p.password:
                from server.state import LoggedState
                self._username = p.username
                await self._queue_local_client_send(OkPacket(from_pid=self._pid))
                await self._change_states(LoggedState(self._pid, self._change_states, self._queue_local_protos_send, self._queue_local_client_send, self._get_db_session), self.view)
            else:
                await self._queue_local_client_send(DenyPacket(from_pid=self._pid, reason="Invalid username or password"))

    async def handle_register(self, p: RegisterPacket) -> None:
        async with self._get_db_session() as session:
            if (await session.execute(select(User).where(User.username == p.username))).scalar_one_or_none():
                await self._queue_local_client_send(DenyPacket(from_pid=self._pid, reason="Username already taken"))
            else:
                user: User = User(username=p.username, password=p.password)
                logging.info(f"Registering new user {user}")
                entity: Entity = Entity(name=p.username)
                
                session.add(user)
                session.add(entity)
                await session.commit()

                instanced_entity: InstancedEntity = InstancedEntity(entity_id=entity.id, x=randint(16, 304), y=randint(16, 224))
                
                session.add(instanced_entity)
                await session.commit()

                player: Player = Player(entity_id=entity.id, instanced_entity_id=instanced_entity.entity_id, user_id=user.id)

                session.add(player)
                await session.commit()
                
                await self._queue_local_client_send(OkPacket(from_pid=self._pid))