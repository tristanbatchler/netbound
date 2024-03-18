# `server/__main__.py`
```python
import asyncio
import logging
import traceback
from server import app

async def main() -> None:
    logging.info("Starting server")

    server_app: app.ServerApp = app.ServerApp("localhost", 8081, 10)
    async with asyncio.TaskGroup() as tg:
        tg.create_task(server_app.start())
        tg.create_task(server_app.run())


    logging.info("Server stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server stopped by user")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        traceback.print_exc() 
```

# `server/app/__init__.py`
```python
from server.app.server import ServerApp
```

# `server/app/protocol.py`
```python
from __future__ import annotations
import asyncio
import logging
import websockets as ws
import server.packet as pck
import server.state as st
from server.state.base import BaseState
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing import Callable, Coroutine, Any, Optional
from server.constants import EVERYONE
from base64 import b64encode

class GameProtocol:
    def __init__(
            self, 
            websocket: ws.WebSocketServerProtocol, 
            pid: bytes, 
            disconnect_callback: Callable[[GameProtocol, str], Coroutine[Any, Any, None]], 
            db_session_callback: async_sessionmaker
        ) -> None:
        """WARNING: This class must only be instantiated from within the server.app.ServerApp class"""
        logging.info(f"Assigned id {b64encode(pid).decode()} to new protocol")
        self._websocket: ws.WebSocketServerProtocol = websocket
        self._pid: bytes = pid
        self._local_receive_packet_queue: asyncio.Queue[pck.BasePacket] = asyncio.Queue()
        self._local_protos_send_packet_queue: asyncio.Queue[pck.BasePacket] = asyncio.Queue()
        self._local_client_send_packet_queue: asyncio.Queue[pck.BasePacket] = asyncio.Queue()
        self._disconnect: Callable[[GameProtocol, str], Coroutine[Any, Any, None]] = disconnect_callback
        self._get_db_session: async_sessionmaker = db_session_callback
        self._state: Optional[st.BaseState] = None

    def __repr__(self) -> str:
        return f"GameProtocol({b64encode(self._pid).decode()})"
    
    def __str__(self) -> str:
        return self.__repr__()

    async def _start(self) -> None:
        await self._change_state(st.EntryState(self._pid, self._change_state, self._local_protos_send_packet_queue.put, self._local_client_send_packet_queue.put, self._get_db_session))
        try:
            await self._listen_websocket()
        except ws.ConnectionClosedError:
            logging.debug(f"Connection closed for id {b64encode(self._pid).decode()}")
            await self._disconnect(self, "Client disconnected")

    async def _listen_websocket(self) -> None:
        logging.debug(f"Starting protocol for id {b64encode(self._pid).decode()}")

        async for message in self._websocket:
            if not isinstance(message, bytes):
                logging.error(f"Received non-bytes message: {message}")
                continue
            
            try:
                p: pck.BasePacket = pck.deserialize(message)
            except pck.MalformedPacketError as e:
                logging.error(f"Malformed packet: {e}")
                continue
            except pck.UnknownPacketError as e:
                logging.error(f"Unknown packet: {e}")
                continue
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                continue

            logging.debug(f"Received packet: {p}")
            
            # Store the packet in our local receive queue for processing next tick
            await self._local_receive_packet_queue.put(p)

        logging.debug(f"{self} stopped")
        await self._disconnect(self, "Client disconnected")

    async def _change_state(self, new_state: st.BaseState, previous_state_view: Optional[BaseState.View]=None) -> None:
        self._state = new_state
        await self._state.on_transition(previous_state_view)

    async def _process_packets(self) -> None:
        while not self._local_receive_packet_queue.empty():
            p: pck.BasePacket = await self._local_receive_packet_queue.get()
            if self._state:
                await self._state.handle_packet(p)
            logging.debug(f"Processed packet: {p}")
```

# `server/app/server.py`
```python
import logging
import asyncio
import traceback
from datetime import datetime
import websockets as ws
from uuid import uuid4
from server.packet import BasePacket, DisconnectPacket
from server.app.protocol import GameProtocol
from server.constants import EVERYONE
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from server.database.model import Base

class ServerApp:
    def __init__(self, host: str, port: int, ticks_per_second: int) -> None:
        self._host: str = host
        self._port: int = port
        self._tick_rate: float = 1 / ticks_per_second
        self._connected_protocols: dict[bytes, GameProtocol] = {}
        self._global_protos_packet_queue: asyncio.Queue[BasePacket] = asyncio.Queue()
    
        self._async_engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///server/database/netbound.db", echo=True)
        self._async_session: async_sessionmaker = async_sessionmaker(bind=self._async_engine, class_=AsyncSession, expire_on_commit=False)

    async def start(self) -> None:
        logging.info(f"Starting server on {self._host}:{self._port}")
        async with ws.serve(self.handle_connection, self._host, self._port):
            await asyncio.Future()

    async def run(self) -> None:
        logging.info("Running server tick loop")
        while True:
            start_time: float = datetime.now().timestamp()
            try:
                await self.tick()
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                traceback.print_exc()
            elapsed: float = datetime.now().timestamp() - start_time
            diff: float = self._tick_rate - elapsed
            if diff > 0:
                await asyncio.sleep(diff)
            elif diff < 0:
                logging.warning("Tick time budget exceeded by %s seconds", -diff)


    async def handle_connection(self, websocket: ws.WebSocketServerProtocol) -> None:
        logging.info(f"New connection from {websocket.remote_address}")
        proto: GameProtocol = GameProtocol(websocket, uuid4().bytes, self._disconnect_protocol, self._async_session)
        self._connected_protocols[proto._pid] = proto
        await proto._start()


    async def _dispatch_packets(self) -> None:
        while not self._global_protos_packet_queue.empty():
            p: BasePacket = await self._global_protos_packet_queue.get()
            logging.debug(f"Dispatching {p.__class__.__name__} packet")
            
            to_pids: list[Optional[bytes]] = p.to_pid if isinstance(p.to_pid, list) else [p.to_pid]

            for to_pid in to_pids:
                if to_pid is None:
                    logging.error(f"Packet {p} in the global protos queue was dropped because its "
                                  "destination PID is None. If you are trying to send to the "
                                  "client, use the local client queue instead")
                    continue

                if to_pid == p.from_pid:
                    logging.error(f"Packet {p} was dropped because its direction is ambiguous in the proto-to-proto queue")
                    continue

                elif p.from_pid == EVERYONE:
                    logging.error(f"Packet {p} was dropped because its source PID must be specific")
                    continue

                elif p.exclude_sender and p.to_pid != EVERYONE:
                    logging.error(f"Packet {p} was dropped because exclude_sender is only compatible with the EVERYONE destination")
                    continue

                elif to_pid == EVERYONE:
                    for _, proto in self._connected_protocols.items():
                        if p.exclude_sender and proto._pid == p.from_pid:
                            continue
                        await proto._local_receive_packet_queue.put(p)
                        logging.debug(f"Added {p.__class__.__name__} packet to {proto}'s receive queue")
                
                # If we get to here, destination should be a specific PID
                elif specific_to_proto  := self._connected_protocols.get(to_pid):
                    await specific_to_proto._local_receive_packet_queue.put(p)
                else:
                    logging.error(f"Packet {p} was sent to a disconnected protocol")


    async def tick(self) -> None:
        # Grab the top outbound packet from each protocol and put it in the global queue
        for _, proto in self._connected_protocols.copy().items():
            if not proto._local_protos_send_packet_queue.empty():
                p_to_other: BasePacket = await proto._local_protos_send_packet_queue.get()
                logging.debug(f"Popped {p_to_other.__class__.__name__} packet from {proto}'s proto-to-proto send queue")
                await self._global_protos_packet_queue.put(p_to_other)
            
            if not proto._local_client_send_packet_queue.empty():
                p_to_client: BasePacket = await proto._local_client_send_packet_queue.get()
                logging.debug(f"Popped {p_to_client.__class__.__name__} packet from {proto}'s client send queue")
                await self._send_to_client(proto, p_to_client)

        # Dispatch all packets in the global proto-to-proto queue to their respective protocols' inbound queues
        await self._dispatch_packets()
        
        # Process all inbound packets for each protocol
        for _, proto in self._connected_protocols.copy().items():
            await proto._process_packets()

    async def _disconnect_protocol(self, proto: GameProtocol, reason: str) -> None:
        logging.info(f"Disconnecting {proto}: {reason}")
        self._connected_protocols.pop(proto._pid)
        await self._global_protos_packet_queue.put(DisconnectPacket(reason=reason, from_pid=proto._pid, to_pid=EVERYONE))

    async def _send_to_client(self, proto: GameProtocol, p: BasePacket) -> None:
        try:
            await proto._websocket.send(p.serialize())
        except ws.ConnectionClosed as e:
            logging.error(f"Connection closed: {e}")
            await self._disconnect_protocol(proto, "Connection closed")
```

# `server/constants.py`
```python
EVERYONE: bytes = (0).to_bytes(16, "big")
```

# `server/database/migrations/env.py`
```python
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from server.database.model import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

# `server/database/model.py`
```python
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import DeclarativeBase
from typing import Type

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)

class Entity(Base):
    __tablename__ = 'entities'
    id = Column(Integer, primary_key=True)
    name = Column(String)

class Player(Base):
    __tablename__ = 'players'
    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey('entities.id'), unique=True)
    instanced_entity_id = Column(Integer, ForeignKey('instanced_entities.entity_id'), unique=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True)
    image_index = Column(Integer, default=0)

class InstancedEntity(Base):
    __tablename__ = 'instanced_entities'
    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey('entities.id'))
    x = Column(Integer)
    y = Column(Integer)
```

# `server/packet.py`
```python
import json
import msgpack
from server.constants import EVERYONE
from pydantic import BaseModel, ValidationError
from typing import Any, Type, Optional
import base64
import logging

DEFINITIONS_FILE: str = "shared/packet/definitions.json"

class BasePacket(BaseModel):
    from_pid: bytes
    # If to_pid is None, it is either from the client to its protocol or vice-versa
    to_pid: Optional[bytes | list[Optional[bytes]]] = None
    exclude_sender: Optional[bool] = False

    def serialize(self) -> bytes:
        data = {}
        packet_name = self.__class__.__name__.removesuffix("Packet").title()
        m_dump = self.model_dump()

        data[packet_name] = m_dump
        return msgpack.packb(data, use_bin_type=True)
    
    def __repr__(self) -> str:
        TO_PID: str = "to_pid"
        FROM_PID: str = "from_pid"
        d: dict[str, Any] = self.__dict__.copy()
        d[FROM_PID] = base64.b64encode(self.from_pid).decode()

        if self.to_pid == EVERYONE:
            d[TO_PID] = "EVERYONE"
        elif self.to_pid is None:
            d[TO_PID] = d[FROM_PID]
        elif isinstance(self.to_pid, list):
            d[TO_PID] = [
                base64.b64encode(x).decode()
                if x else 
                f"{base64.b64encode(self.from_pid).decode()}'s client"
                for x in self.to_pid
            ]
        else:
            d[TO_PID] = base64.b64encode(self.to_pid).decode()
        return f"{self.__class__.__name__}{d}"
    
    def __str__(self) -> str:
        return self.__repr__()

class OkPacket(BasePacket):
    ...

class DenyPacket(BasePacket):
    reason: Optional[str] = None

class PIDPacket(BasePacket):
    ...
    
class HelloPacket(BasePacket):
    state_view: dict[str, Any]

class MovePacket(BasePacket):
    dx: int
    dy: int

class LoginPacket(BasePacket):
    username: str
    password: str

class RegisterPacket(BasePacket):
    username: str
    password: str

class DisconnectPacket(BasePacket):
    reason: str

class ChatPacket(BasePacket):
    message: str

class MalformedPacketError(ValueError):
    pass

class UnknownPacketError(ValueError):
    pass

def deserialize(packet_: bytes) -> BasePacket:
    try:
        packet_dict: dict[str, Any] = msgpack.unpackb(packet_, raw=False)
    except msgpack.StackError:
        raise MalformedPacketError("Packet too nested to unpack")
    except msgpack.ExtraData:
        raise MalformedPacketError("Extra data was sent with the packet")
    except msgpack.FormatError:
        raise MalformedPacketError("Packet is malformed")
    except msgpack.UnpackValueError:
        raise MalformedPacketError("Packet has missing data")

    if len(packet_dict) == 0:
        raise MalformedPacketError("Empty packet")

    packet_name: Any = list(packet_dict.keys())[0]
    if not isinstance(packet_name, str):
        raise MalformedPacketError(f"Invalid packet name (not a string): {packet_name}")

    packet_data: dict = packet_dict[packet_name]
    
    # PIDs are sent as b64-encoded strings, but we need them as bytes
    for _pid_key in ["to_pid", "from_pid"]:
        if _pid_key in packet_data:
            packet_data[_pid_key] = base64.b64decode(packet_data[_pid_key])


    class_name: str = packet_name.title() + "Packet"

    try:
        packet_class: Type[BasePacket] = globals()[class_name]
    except KeyError:
        raise UnknownPacketError(f"Packet name not recognized: {packet_name}")
    
    try:
        packet_class.model_validate(packet_data)
    except ValidationError as e:
        raise MalformedPacketError(f"Packet data {packet_data} does not match expected schema: {e}")

    try:
        return packet_class(**packet_data)
    except TypeError as e:
        raise MalformedPacketError(f"Packet data does not match expected signature: {e}")


schema: dict[str, Any] = {}
for item, type_ in globals().copy().items():
    if isinstance(type_, type) and issubclass(type_, BasePacket):
        schema[item] = type_.model_json_schema()
        schema[item].pop("title")

with open(DEFINITIONS_FILE, "w") as f:
    json.dump(schema, f, indent=4)
```

# `server/state/__init__.py`
```python
from server.state.base import BaseState
from server.state.entry import EntryState
from server.state.logged import LoggedState
```

# `server/state/base.py`
```python
from __future__ import annotations
from server.packet import BasePacket
from typing import Callable, Optional, Coroutine, Any
from sqlalchemy.ext.asyncio import async_sessionmaker
import logging
from dataclasses import dataclass

class BaseState:
    @dataclass
    class View:
        pass

    def __init__(
            self, 
            pid: bytes, 
            change_state_callback: Callable[[BaseState, BaseState.View], Coroutine[Any, Any, None]], 
            queue_local_protos_send_callback: Callable[[BasePacket], Coroutine[Any, Any, None]],
            queue_local_client_send_callback: Callable[[BasePacket], Coroutine[Any, Any, None]], 
            get_db_session_callback: async_sessionmaker
        ) -> None:
        self._pid: bytes = pid
        self._change_states: Callable[[BaseState, BaseState.View], Coroutine[Any, Any, None]] = change_state_callback
        self._queue_local_protos_send: Callable[[BasePacket], Coroutine[Any, Any, None]] = queue_local_protos_send_callback
        self._queue_local_client_send: Callable[[BasePacket], Coroutine[Any, Any, None]] = queue_local_client_send_callback
        self._get_db_session: async_sessionmaker = get_db_session_callback

    
    @property
    def view(self) -> View:
        params: dict[str, Any] = {}
        for k in self.View.__dataclass_fields__:
            value: Any = getattr(self, k, None) or getattr(self, f"_{k}", None)
            if value is not None:
                params[k] = value
            else:
                logging.error(f"State {self.__class__.__name__} has no value for {k}")

        return self.View(**params)

    @property
    def view_dict(self) -> dict[str, Any]:
        return self.view.__dict__
    
    async def on_transition(self, previous_state_view: Optional[BaseState.View]=None) -> None:
         pass

    async def handle_packet(self, p: BasePacket) -> None:
        packet_name: str = p.__class__.__name__.removesuffix("Packet").lower()
        handler_name: str = f"handle_{packet_name}"
        if handler := getattr(self, handler_name, None):
            await handler(p)
        else:
            logging.warning(f"State {self.__class__.__name__} does not have a handler for {packet_name} packets")            
```

# `server/state/entry.py`
```python
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

                room_width: int = 320
                room_height: int = 240
                grid_size: int = 16
                random_x: int = grid_size * randint(1, room_width // grid_size - 1)
                random_y: int = grid_size * randint(1, room_height // grid_size - 1)
                instanced_entity: InstancedEntity = InstancedEntity(entity_id=entity.id, x=random_x, y=random_y)
                
                session.add(instanced_entity)
                await session.commit()

                player: Player = Player(entity_id=entity.id, instanced_entity_id=instanced_entity.entity_id, user_id=user.id, image_index=randint(0, 17))

                session.add(player)
                await session.commit()

                await self._queue_local_client_send(OkPacket(from_pid=self._pid))
```

# `server/state/logged.py`
```python
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
        image_index: int

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._known_others: dict[bytes, LoggedState.View] = {}
        self._entity: Entity | None = None
        self._instanced_entity: InstancedEntity | None = None
        self._player: Player | None = None

        self._name: str | None = None  # This will be set in on_transition (needs to be passed from EntryState)
        self._x: int = 0
        self._y: int = 0
        self._image_index: int = 0
    
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
            self._image_index = self._player.image_index
    

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
            
```


