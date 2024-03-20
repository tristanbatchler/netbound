`server/__main__.py`
```py
import asyncio
import logging
import traceback
from server.engine.app import ServerApp
from server.core.state import EntryState
from server.core import packet
from server.core.database import model
async def main() -> None:
    logging.info("Starting server")
    server_app: ServerApp = ServerApp("localhost", 443, 10)
    server_app.register_packets(packet)
    server_app.register_db_models(model)
    async with asyncio.TaskGroup() as tg:
        tg.create_task(server_app.start(EntryState))
        tg.create_task(server_app.run())
    logging.info("Server stopped")
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sqlalchemy_engine_logger = logging.getLogger('sqlalchemy.engine')
    sqlalchemy_engine_logger.setLevel(logging.WARNING)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server stopped by user")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        traceback.print_exc() 
```
`server/core/database/model.py`
```py
from server.engine.database.model import Base
from sqlalchemy import Column as mapped_column
from sqlalchemy import Integer, String, ForeignKey
class User(Base):
    __tablename__ = 'users'
    id = mapped_column(Integer, primary_key=True)
    username = mapped_column(String, unique=True)
    password = mapped_column(String)
class Entity(Base):
    __tablename__ = 'entities'
    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String)
class Player(Base):
    __tablename__ = 'players'
    id = mapped_column(Integer, primary_key=True)
    entity_id = mapped_column(Integer, ForeignKey('entities.id'), unique=True)
    instanced_entity_id = mapped_column(Integer, ForeignKey('instanced_entities.entity_id'), unique=True)
    user_id = mapped_column(Integer, ForeignKey('users.id'), unique=True)
    image_index = mapped_column(Integer, default=0)
class InstancedEntity(Base):
    __tablename__ = 'instanced_entities'
    id = mapped_column(Integer, primary_key=True)
    entity_id = mapped_column(Integer, ForeignKey('entities.id'))
    x = mapped_column(Integer)
    y = mapped_column(Integer)
```
`server/core/packet.py`
```py
import json
from typing import Any
from server.engine.packet import BasePacket
# ... (all my packet defininitions from before) ...
```
`server/core/state/entry.py`
```py
from server.core.state import BaseState
from server.core.packet import OkPacket, DenyPacket, LoginPacket, RegisterPacket, PIDPacket, WhichUsernamesPacket, MyUsernamePacket, MotdPacket
from server.core.database.model import User, Entity, InstancedEntity, Player
from sqlalchemy import select
from dataclasses import dataclass
from server.engine.constants import EVERYONE
from random import randint
import bcrypt
from time import time
from datetime import datetime as dt
class EntryState(BaseState):
    # ... (same as before) ...
```
`server/core/state/logged.py`
```py
from __future__ import annotations
import logging
from server.engine.state import BaseState
from dataclasses import dataclass
from server.core.packet import ChatPacket, DisconnectPacket, HelloPacket, MovePacket, MyUsernamePacket, WhichUsernamesPacket
from server.engine.constants import EVERYONE
from typing import Optional
from server.core.state import EntryState
from server.engine.state import TransitionError
from server.core.database.model import User, Entity, InstancedEntity, Player
from sqlalchemy import select
class LoggedState(BaseState):
    # ... (same as before) ...
```
`server/engine/app/logging_adapter.py`
```py
import logging
class StateLoggingAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        pid = self.extra.get('pid', 'Unknown')
        state_name = self.extra.get('state', 'None')
        return f"[{pid.hex()}][{state_name}] {msg}", kwargs
class ProtocolLoggingAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        pid = self.extra.get('pid', 'Unknown')
        return f"[{pid.hex()}] {msg}", kwargs
class ServerLoggingAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f"[Server] {msg}", kwargs
```
`server/engine/app/protocol.py`
```py
from __future__ import annotations
import asyncio
import logging
import websockets as ws
import server.engine.packet as pck
import server.engine.state as st
from server.engine.state.base import BaseState
from sqlalchemy.ext.asyncio import async_sessionmaker
from typing import Callable, Coroutine, Any, Optional
from server.engine.constants import EVERYONE
from base64 import b64encode
from server.engine.app.logging_adapter import ProtocolLoggingAdapter
class GameProtocol:
    def __init__(
            self, 
            websocket: ws.WebSocketServerProtocol, 
            pid: bytes, 
            disconnect_callback: Callable[[GameProtocol, str], Coroutine[Any, Any, None]], 
            db_session_callback: async_sessionmaker
        ) -> None:
        """WARNING: This class must only be instantiated from within the server.app.ServerApp class"""
        self._websocket: ws.WebSocketServerProtocol = websocket
        self._pid: bytes = pid
        self._local_receive_packet_queue: asyncio.Queue[pck.BasePacket] = asyncio.Queue()
        self._local_protos_send_packet_queue: asyncio.Queue[pck.BasePacket] = asyncio.Queue()
        self._local_client_send_packet_queue: asyncio.Queue[pck.BasePacket] = asyncio.Queue()
        self._disconnect: Callable[[GameProtocol, str], Coroutine[Any, Any, None]] = disconnect_callback
        self._get_db_session: async_sessionmaker = db_session_callback
        self._state: Optional[st.BaseState] = None
        self._logger: ProtocolLoggingAdapter = ProtocolLoggingAdapter(logging.getLogger(__name__), {
            'pid': pid
        })
    def __repr__(self) -> str:
        return f"GameProtocol({b64encode(self._pid).decode()})"
    def __str__(self) -> str:
        return self.__repr__()
    async def _start(self, initial_state: st.BaseState) -> None:
        await self._change_state(initial_state(self._pid, self._change_state, self._local_protos_send_packet_queue.put, self._local_client_send_packet_queue.put, self._get_db_session))
        try:
            await self._listen_websocket()
        except ws.ConnectionClosedError:
            self._logger.debug(f"Connection closed")
            await self._disconnect(self, "Client disconnected")
    async def _listen_websocket(self) -> None:
        self._logger.debug(f"Starting protocol")
        async for message in self._websocket:
            if not isinstance(message, bytes):
                self._logger.error(f"Received non-bytes message: {message}")
                continue
            try:
                p: pck.BasePacket = pck.deserialize(message)
            except pck.MalformedPacketError as e:
                self._logger.error(f"Malformed packet: {e}")
                continue
            except pck.UnknownPacketError as e:
                self._logger.error(f"Unknown packet: {e}")
                continue
            except Exception as e:
                self._logger.error(f"Unexpected error: {e}")
                continue
            self._logger.debug(f"Received packet: {p}")
            await self._local_receive_packet_queue.put(p)
        self._logger.debug(f"{self} stopped")
        await self._disconnect(self, "Client disconnected")
    async def _change_state(self, new_state: st.BaseState, previous_state_view: Optional[BaseState.View]=None) -> None:
        self._state = new_state
        await self._state.on_transition(previous_state_view)
    async def _process_packets(self) -> None:
        while not self._local_receive_packet_queue.empty():
            p: pck.BasePacket = await self._local_receive_packet_queue.get()
            if self._state:
                await self._state.handle_packet(p)
            self._logger.debug(f"Processed packet: {p}")
```
`server/engine/app/server.py`
```py
import logging
import asyncio
import traceback
from datetime import datetime
from typing import Optional
import websockets as ws
import ssl
from uuid import uuid4
from server.engine.packet import BasePacket, DisconnectPacket, register_packet
from server.engine.database.model import register_model
from server.engine.app.protocol import GameProtocol
from server.engine.constants import EVERYONE
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from server.engine.app.logging_adapter import ServerLoggingAdapter
from server.engine.state import BaseState
from types import ModuleType
class ServerApp:
    def __init__(self, host: str, port: int, ticks_per_second: int) -> None:
        self._host: str = host
        self._port: int = port
        self._tick_rate: float = 1 / ticks_per_second
        self._connected_protocols: dict[bytes, GameProtocol] = {}
        self._global_protos_packet_queue: asyncio.Queue[BasePacket] = asyncio.Queue()
        self._async_engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///server/core/database/netbound.db")
        self._async_session: async_sessionmaker = async_sessionmaker(bind=self._async_engine, class_=AsyncSession, expire_on_commit=False)
        self._logger: ServerLoggingAdapter = ServerLoggingAdapter(logging.getLogger(__name__))
        self._initial_state: BaseState | None = None  # This will be set by the the start method
    async def start(self, initial_state: BaseState) -> None:
        self._initial_state = initial_state
        ssl_context: ssl.SSLContext = self._get_ssl_context("server/core/app/ssl/localhost.crt", "server/core/app/ssl/localhost.key")
        self._logger.info(f"Starting server on {self._host}:{self._port}")
        async with ws.serve(self.handle_connection, self._host, self._port, ssl=ssl_context):
            await asyncio.Future()
    def register_packets(self, packet_module: ModuleType) -> None:
        for packet_name in dir(packet_module):
            if packet_name.endswith("Packet"):
                packet_class = getattr(packet_module, packet_name)
                if issubclass(packet_class, BasePacket):
                    register_packet(packet_class)
    def register_db_models(self, model_module: ModuleType) -> None:
        for model_name in dir(model_module):
            if model_name.endswith("Model"):
                model_class = getattr(model_module, model_name)
                if hasattr(model_class, "__table__"):
                    register_model(model_class)
    async def run(self) -> None:
        self._logger.info("Running server tick loop")
        while True:
            start_time: float = datetime.now().timestamp()
            try:
                await self.tick()
            except Exception as e:
                self._logger.error(f"Unexpected error: {e}")
                traceback.print_exc()
            elapsed: float = datetime.now().timestamp() - start_time
            diff: float = self._tick_rate - elapsed
            if diff > 0:
                await asyncio.sleep(diff)
            elif diff < 0:
                self._logger.warning("Tick time budget exceeded by %s seconds", -diff)
    def _get_ssl_context(self, certpath: str, keypath: str) -> ssl.SSLContext:
        self._logger.info("Loading encryption key")
        ssl_context: ssl.SSLContext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            ssl_context.load_cert_chain(certpath, keypath)
        except FileNotFoundError:
            raise FileNotFoundError(f"No encryption key or certificate found. Please generate a pair and save them to {certpath} and {keypath}")
        return ssl_context
    async def handle_connection(self, websocket: ws.WebSocketServerProtocol) -> None:
        self._logger.info(f"New connection from {websocket.remote_address}")
        proto: GameProtocol = GameProtocol(websocket, uuid4().bytes, self._disconnect_protocol, self._async_session)
        self._connected_protocols[proto._pid] = proto
        await proto._start(self._initial_state)
    async def _dispatch_packets(self) -> None:
        while not self._global_protos_packet_queue.empty():
            p: BasePacket = await self._global_protos_packet_queue.get()
            self._logger.debug(f"Dispatching {p.__class__.__name__} packet")
            to_pids: list[Optional[bytes]] = p.to_pid if isinstance(p.to_pid, list) else [p.to_pid]
            for to_pid in to_pids:
                if to_pid is None:
                    self._logger.error(f"Packet {p} in the global protos queue was dropped because its "
                                  "destination PID is None. If you are trying to send to the "
                                  "client, use the local client queue instead")
                    continue
                if to_pid == p.from_pid:
                    self._logger.error(f"Packet {p} was dropped because its direction is ambiguous in the proto-to-proto queue")
                    continue
                elif p.from_pid == EVERYONE:
                    self._logger.error(f"Packet {p} was dropped because its source PID must be specific")
                    continue
                elif p.exclude_sender and p.to_pid != EVERYONE:
                    self._logger.error(f"Packet {p} was dropped because exclude_sender is only compatible with the EVERYONE destination")
                    continue
                elif to_pid == EVERYONE:
                    for _, proto in self._connected_protocols.items():
                        if p.exclude_sender and proto._pid == p.from_pid:
                            continue
                        await proto._local_receive_packet_queue.put(p)
                        self._logger.debug(f"Added {p.__class__.__name__} packet to {proto}'s receive queue")
                elif specific_to_proto  := self._connected_protocols.get(to_pid):
                    await specific_to_proto._local_receive_packet_queue.put(p)
                else:
                    self._logger.error(f"Packet {p} was sent to a disconnected protocol")
    async def tick(self) -> None:
        for _, proto in self._connected_protocols.copy().items():
            if not proto._local_protos_send_packet_queue.empty():
                p_to_other: BasePacket = await proto._local_protos_send_packet_queue.get()
                self._logger.debug(f"Popped {p_to_other.__class__.__name__} packet from {proto}'s proto-to-proto send queue")
                await self._global_protos_packet_queue.put(p_to_other)
            if not proto._local_client_send_packet_queue.empty():
                p_to_client: BasePacket = await proto._local_client_send_packet_queue.get()
                self._logger.debug(f"Popped {p_to_client.__class__.__name__} packet from {proto}'s client send queue")
                await self._send_to_client(proto, p_to_client)
        await self._dispatch_packets()
        for _, proto in self._connected_protocols.copy().items():
            await proto._process_packets()
    async def _disconnect_protocol(self, proto: GameProtocol, reason: str) -> None:
        self._logger.info(f"Disconnecting {proto}: {reason}")
        self._connected_protocols.pop(proto._pid)
        await self._global_protos_packet_queue.put(DisconnectPacket(from_pid=proto._pid, to_pid=EVERYONE, reason=reason))
    async def _send_to_client(self, proto: GameProtocol, p: BasePacket) -> None:
        try:
            await proto._websocket.send(p.serialize())
        except ws.ConnectionClosed as e:
            self._logger.error(f"Connection closed: {e}")
            await self._disconnect_protocol(proto, "Connection closed")
```
`server/engine/database/model.py`
```py
from sqlalchemy.orm import DeclarativeBase
from typing import Type
class Base(DeclarativeBase):
    pass
def register_model(model: Type[Base]) -> None:
    globals()[model.__name__] = model
```
`server/engine/packet.py`
```py
import msgpack
from server.engine.constants import EVERYONE
from pydantic import BaseModel, ValidationError
from typing import Any, Type, Optional
import base64
class BasePacket(BaseModel):
    from_pid: bytes
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
class DisconnectPacket(BasePacket):
    reason: str
class MalformedPacketError(ValueError):
    pass
class UnknownPacketError(ValueError):
    pass
def register_packet(packet: Type[BasePacket]) -> None:
    globals()[packet.__name__] = packet
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
```
`server/engine/state/base.py`
```py
from __future__ import annotations
from server.engine.packet import BasePacket
from typing import Callable, Optional, Coroutine, Any
from sqlalchemy.ext.asyncio import async_sessionmaker
from server.engine.app.logging_adapter import StateLoggingAdapter
from dataclasses import dataclass
import logging
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
        self._logger: StateLoggingAdapter = StateLoggingAdapter(logging.getLogger(__name__), {
            'pid': pid,
            'state': self.__class__.__name__
        })
    @property
    def view(self) -> View:
        params: dict[str, Any] = {}
        for k in self.View.__dataclass_fields__:
            value: Any = getattr(self, k, None) or getattr(self, f"_{k}", None)
            if value is not None:
                params[k] = value
            else:
                self._logger.error(f"State {self.__class__.__name__} has no value for {k}")
        return self.View(**params)
    @property
    def view_dict(self) -> dict[str, Any]:
        return self.view.__dict__
    async def change_states(self, new_state: type[BaseState]) -> None:
        await self._change_states(new_state(self._pid, self._change_states, self._queue_local_protos_send, self._queue_local_client_send, self._get_db_session), self.view)
    async def on_transition(self, previous_state_view: Optional[BaseState.View]=None) -> None:
         pass
    async def handle_packet(self, p: BasePacket) -> None:
        packet_name: str = p.__class__.__name__.removesuffix("Packet").lower()
        handler_name: str = f"handle_{packet_name}"
        if handler := getattr(self, handler_name, None):
            await handler(p)
        else:
            self._logger.warning(f"State {self.__class__.__name__} does not have a handler for {packet_name} packets")            
```